"""Selectable research rules over a common sampled option set."""

from __future__ import annotations

from typing import Literal

import numpy as np
from pydantic import Field, model_validator

from .cargo_risk import cvar
from .cargo_sampling import (
    Futures, OptionLoss, RiskStudy, Sampling, comparable, map_futures,
    replicate_ci, sample_losses, worlds_for,
)
from .commercial import Strict


class RuleSettings(Strict):
    rule: Literal["R1", "R2", "R3", "R4", "R5"] = "R1"
    epsilon: float | None = Field(default=None, ge=0, le=1)
    q: float = Field(default=.65, gt=0, le=1)
    regretMetric: Literal["cost", "hours"] = "cost"
    allowWait: bool = False
    allowKnownSubtotal: bool = True

    @model_validator(mode="after")
    def epsilon_required(self):
        if self.rule == "R2" and self.epsilon is None:
            raise ValueError("R2 requires an explicit priority-1 miss limit")
        return self


def _rank(row: OptionLoss, score, keep: str):
    return float(score), row.option.id != keep, row.option.id


def _decision(settings, option, reason, **extra):
    return {
        "rule": settings.rule, "optionId": option.option.id if option else None,
        "action": option.option.action if option else None, "reason": reason, **extra,
    }


def _explanation(winner: OptionLoss, baseline: OptionLoss, scope: str) -> str:
    hours = float(np.median(winner.arrival) - np.median(baseline.arrival))
    change = f"{hours:+.1f} h at the median" if abs(hours) >= .05 else "similar median arrival"
    before = {row.consignment_id: row.spoilage for row in baseline.consignments}
    improvements = []
    for item in winner.consignments:
        keep = before.get(item.consignment_id)
        if item.spoilage is not None and keep is not None:
            improvements.append((float(keep.mean() - item.spoilage.mean()), item.consignment_id,
                                 float(keep.mean()), float(item.spoilage.mean())))
    best = max(improvements, default=None)
    if best and best[0] >= .005:
        return f"{change} versus keep and {best[1]} modelled spoilage falls from {best[2]:.1%} to {best[3]:.1%} · {scope}"
    return f"{change} versus keep · {scope}"


def value_of_information(study: RiskStudy, rows: list[OptionLoss], futures: Futures) -> dict | None:
    """Cross-fit a policy that can learn only the refresh-time reopening status."""
    refresh = study.nextRefreshHour
    if refresh is None or not comparable(rows):
        return None
    eligible = [
        row for row in rows if row.option.id == study.keepOptionId
        or (row.option.latestStartHour is not None and row.option.latestStartHour >= refresh)
    ]
    if len(eligible) < 2:
        return None
    waited = [sample_losses(study, row.option, futures, wait_hours=refresh) for row in eligible]
    if not comparable(rows + waited):
        return None
    signal = study.closure.startedHour + futures.closure_hours <= refresh
    if np.all(signal) or not np.any(signal):
        return None
    labels = (False, True)
    complete = rows[0].costs.unknown == {}
    length = futures.samples // futures.scrambles
    folds = np.repeat(np.arange(futures.scrambles), length)
    choices = {label: [] for label in labels}
    wait_loss, act_loss = np.zeros(futures.samples), np.zeros(futures.samples)

    def rank(group, mask):
        return min(group, key=lambda row: _rank(
            row, row.costs.known_subtotal[mask].mean(), study.keepOptionId,
        ))

    for fold in range(futures.scrambles):
        train, test = folds != fold, folds == fold
        immediate = rank(rows, train)
        act_loss[test] = immediate.costs.known_subtotal[test]
        for label in labels:
            conditioned = train & (signal == label)
            winner = rank(waited, conditioned if conditioned.any() else train)
            selected = test & (signal == label)
            wait_loss[selected] = winner.costs.known_subtotal[selected]
            choices[label].append(winner.option.id)

    return {
        "refreshHour": refresh,
        "observation": "Whether the closure has reopened by the next refresh",
        "expectedActCost": replicate_ci(act_loss, futures.scrambles),
        "expectedWaitCost": replicate_ci(wait_loss, futures.scrambles),
        "savingsFromWaiting": replicate_ci(act_loss - wait_loss, futures.scrambles),
        "actionIfOpen": sorted(set(choices[True])),
        "actionIfStillClosed": sorted(set(choices[False])),
        "scope": "complete declared cost" if complete else "known subtotal; excludes unknowns",
        "basis": "Cross-fitted on independent scrambled replicates; delaying shifts arrival and preserves only options open at refresh.",
    }


def decide(study: RiskStudy, rows: list[OptionLoss], futures: Futures, settings: RuleSettings,
           *, evaluate_wait: bool = True) -> dict:
    keep = next(row for row in rows if row.option.id == study.keepOptionId)
    time_only = settings.rule == "R4" and settings.regretMetric == "hours"
    complete = all(not row.costs.unknown for row in rows)
    scope = "hours" if time_only else "complete declared cost" if complete else "known subtotal; excludes unknowns"
    if not time_only and (not comparable(rows) or (not complete and not settings.allowKnownSubtotal)):
        return _decision(settings, None, "Cost scopes differ or lack a comparable basis.", scope=scope, status="ABSTAIN")
    costs = {row.option.id: row.arrival if time_only else row.costs.known_subtotal for row in rows}
    means = {oid: float(loss.mean()) for oid, loss in costs.items()}
    candidates = rows
    rule = settings.rule
    if rule == "R2":
        candidates = [row for row in rows if row.priority_miss is not None
                      and float(row.priority_miss.mean()) <= settings.epsilon]
        if not candidates:
            return _decision(settings, None, "No option has a known priority-1 miss probability within the declared limit.",
                             scope=scope, status="ABSTAIN")
    winner = min(candidates, key=lambda row: _rank(row, means[row.option.id], study.keepOptionId))
    keep_cost = costs[keep.option.id]
    if rule == "R1":
        explanation = "has the lowest expected cost"
    elif rule == "R2":
        explanation = f"minimizes expected cost within the {settings.epsilon:.0%} priority-1 miss limit"
    elif rule == "R3":
        winner = min(rows, key=lambda row: _rank(row, cvar(costs[row.option.id]), study.keepOptionId))
        explanation = "has the lowest CVaR95"
    elif rule == "R4":
        best = np.minimum.reduce(list(costs.values()))
        winner = min(rows, key=lambda row: _rank(row, (costs[row.option.id] - best).max(), study.keepOptionId))
        explanation = f"minimizes the worst sampled regret in {settings.regretMetric}"
    else:
        keep_tail = cvar(keep_cost)
        qualifies = [
            row for row in rows if row.option.id != keep.option.id
            and float((costs[row.option.id] < keep_cost).mean()) >= settings.q
            and cvar(costs[row.option.id]) <= keep_tail
            and (settings.epsilon is None or (row.priority_miss is not None
                 and float(row.priority_miss.mean()) <= settings.epsilon))
        ]
        winner = min(qualifies, key=lambda row: _rank(row, means[row.option.id], study.keepOptionId), default=keep)
        chance = " within the declared chance limit" if settings.epsilon is not None else ""
        explanation = (
            f"beats keep in {(costs[winner.option.id] < keep_cost).mean():.1%} of paired futures with no higher CVaR95"
            if winner is not keep else
            f"stays in place because no intervention beats keep in at least {settings.q:.0%} of futures without a higher CVaR95{chance}"
        )
    reason = f"{winner.option.label} {explanation} ({_explanation(winner, keep, scope)})."
    decision = _decision(settings, winner, reason, scope=scope,
                         status="KEEP" if winner is keep else "SHADOW_CANDIDATE",
                         expectedImprovementVsKeep=replicate_ci(keep_cost - costs[winner.option.id], futures.scrambles),
                         shareBeatingKeep=float((costs[winner.option.id] < keep_cost).mean()))
    if settings.allowWait and not time_only and evaluate_wait:
        information = value_of_information(study, candidates, futures) if keep in candidates else None
        decision["valueOfInformation"] = information
        if information and information["savingsFromWaiting"]["estimate"] > 0:
            estimate = information["savingsFromWaiting"]["estimate"]
            decision.update(status="WAIT", action="wait",
                            reason=f"Wait {information['refreshHour']:g} h for the reopening update because the conditional policy saves an estimated {study.reportingCurrency} {estimate:,.0f} on {scope}.")
    return decision


def closure_sweep(study: RiskStudy, config: Sampling, settings: RuleSettings,
                  *, hours: list[float] | None = None) -> dict:
    """Intervene on closure duration, holding all other latent draws fixed."""
    if hours is None:
        span = max(48, min(1500, 3 * study.closure.medianHours))
        hours = np.linspace(0, span, 33).tolist()
    futures = map_futures(study, worlds_for(config, config.minPower))
    grid, flips = [], []
    previous = None
    for hour in hours:
        values = np.full(futures.samples, hour)
        rows = [sample_losses(study, option, futures, closure_hours=values) for option in study.options]
        result = decide(study, rows, futures, settings, evaluate_wait=False)
        pick = result["optionId"]
        difference = result.get("expectedImprovementVsKeep")
        grid.append({"closureHours": hour, "optionId": pick, "benefitVsKeep": difference})
        if previous is not None and previous["optionId"] != pick:
            flips.append({"lowerHours": previous["closureHours"], "upperHours": hour,
                          "fromOptionId": previous["optionId"], "toOptionId": pick})
        previous = grid[-1]
    return {"grid": grid, "flips": flips, "basis": "Conditional closure-duration grid; other futures held common.",
            "samplesPerGridPoint": futures.samples}
