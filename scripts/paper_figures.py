"""Paper figures and fixed, explicitly illustrative case studies."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from time import perf_counter

import logging

import matplotlib
matplotlib.use("Agg")
logging.getLogger("fontTools").setLevel(logging.WARNING)
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import qmc

from src.portwatch_os.cargo.demo_consignments import assumption
from src.portwatch_os.decision.cargo_policy import RuleSettings, closure_sweep, decide
from src.portwatch_os.decision.cargo_sampling import (
    RiskOption, RiskStudy, Sampling, adaptive, input_key, map_futures, replicate_ci, sample_losses, worlds_for,
)
from src.portwatch_os.decision.cargo_risk import cvar
from src.portwatch_os.decision.commercial import instant
from src.portwatch_os.decision.demonstrations import forecast
from src.portwatch_os.decision.paper_corpus import cargo_mix
from src.portwatch_os.decision.passage import approach_gate, sailing_hours
from src.portwatch_os.decision.passage_finance import evaluate_passage_finance
from src.portwatch_os.missions.catalogue import EVER_GIVEN

PALETTE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#6C6776")
FIXED_DATE = datetime(2026, 11, 12, tzinfo=timezone.utc)
DESIGN_BASIS = "ASSUMPTION · illustrative routing, fuel and handling clocks"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.axisbelow": True})


def save(fig, root, stem):
    for suffix in ("pdf", "png"):
        metadata = {"CreationDate": FIXED_DATE, "ModDate": FIXED_DATE} if suffix == "pdf" else {"Software": "PortWatch paper"}
        fig.savefig(root / f"{stem}.{suffix}", dpi=180, bbox_inches="tight", metadata=metadata)
    plt.close(fig)


def seed_for(master, tag):
    return int(np.random.SeedSequence([master, tag]).generate_state(1)[0])


def studies(master):
    at = datetime(2026, 10, 23, tzinfo=timezone.utc)
    no_route_uncertainty = dict(areas=(), weatherExposure=0, berthExposure=0, dwellHours=20,
                                detentionHours=18, unpoweredHours=1)
    fuel = {"low": 450, "high": 650, "currency": "USD", "source": "ASSUMPTION · illustrative USD/tonne band"}
    handling = {"kind": "TRIANGULAR", "minimum": 0, "mode": 1.2, "maximum": 5,
                "declaration": "ASSUMPTION · additional downstream handling, hours"}
    hourly = forecast(at, "S10")["hourly"]
    requested = at + timedelta(hours=20)
    s10_options = []
    for id_, speed in (("keep", 12), ("slow", 10)):
        sailing = sailing_hours(240, speed)
        physical = at + timedelta(hours=sailing)
        cleared, _, missing = approach_gate(hourly, physical, requested, 15, 5000)
        if missing or cleared is None:
            raise RuntimeError(f"Frozen S10 gate failed: {missing}")
        wait = (cleared - physical).total_seconds() / 3600
        _, modelled_fuel = evaluate_passage_finance(
            {"consumption": {"referenceSpeedKn": 12, "referencePropulsionTonnesPerDay": 24,
                             "auxiliaryTonnesPerDay": 2, "anchorageTonnesPerDay": 2,
                             "departureHoldTonnesPerDay": 2, "minSpeedKn": 8, "maxSpeedKn": 18,
                             "loadCondition": "Unchanged illustrative load", "source": "S10 fixture",
                             "declaredAt": at.isoformat()}},
            sailing_hours=sailing, speed_kn=speed, anchorage_hours=wait, departure_hold_hours=0,
            at=at, port_code="INPRT", calculation_at=at,
        )
        s10_options.append(RiskOption(
            id=id_, action="keep_plan" if id_ == "keep" else "slow_steam", label=f"{speed} kn",
            cleanDeliveryHours=(cleared - at).total_seconds() / 3600,
            fuelTonnes=modelled_fuel["totalTonnes"], **no_route_uncertainty,
            source="SIMULATED · S10 passage fixture and forecast approach gate",
        ))
    s10_cargo, _ = cargo_mix(at, 27, seed_for(master, 510), "reefer")
    yield RiskStudy(
        problemId="s10-meridian", at=at, reportingCurrency="USD", keepOptionId="keep", plannedDeliveryHours=27,
        options=tuple(s10_options), consignments=s10_cargo, fuel=fuel, handling=handling,
        closure={"medianHours": 0, "logSigma": 0, "source": "SIMULATED · S10 has an approach gate only"},
        scope="SIMULATED · PW Meridian S10 with illustrative downstream cargo",
    ), None

    for idx, (name, family, historical) in enumerate((
        ("suez-reefer", "reefer", False), ("suez-time-critical", "deadline", False),
        ("ever-given", "reefer", True),
    )):
        decision_at = instant(EVER_GIVEN.start_timestamp) if historical else at
        reach = EVER_GIVEN.fleet[0].hours_to_chokepoint_at_start["SUEZ"] if historical else 24
        common = dict(dwellHours=20, detentionHours=18, source=DESIGN_BASIS)
        options = (
            RiskOption(id="keep", label="Keep via Suez", action="keep_plan", cleanDeliveryHours=180,
                       reachClosureHour=reach, areas=("RED_SEA",), fuelTonnes=85, unpoweredHours=2, **common),
            RiskOption(id="slow", label="Slow steam via Suez", action="slow_steam", cleanDeliveryHours=204,
                       reachClosureHour=reach + 24, areas=("RED_SEA",), fuelTonnes=68, unpoweredHours=2, **common),
            RiskOption(id="cape", label="Reroute via Cape", action="reroute", cleanDeliveryHours=400,
                       areas=(), fuelTonnes=124, unpoweredHours=1, handlingExposure=.6, **common),
        )
        cargo, _ = cargo_mix(decision_at, 180, seed_for(master, 511 + idx), family)
        scope = ("HISTORICAL TIMELINE · Ever Given 2021 with illustrative hull and cargo"
                 if historical else f"SIMULATED · Suez restriction with {family} cargo")
        blocked = instant(EVER_GIVEN.outcome.blocked_from) if historical else decision_at
        closure = {"startedHour": (blocked - decision_at).total_seconds() / 3600, "medianHours": 144,
                   "logSigma": .55, "source": "ASSUMPTION · ex ante closure prior; no reopening outcome used"}
        realised_duration = ((instant(EVER_GIVEN.outcome.reopened_at) - blocked).total_seconds() / 3600
                             if historical else None)
        yield RiskStudy(problemId=name, at=decision_at, reportingCurrency="USD", keepOptionId="keep",
                        plannedDeliveryHours=180, options=options, consignments=cargo,
                        closure=closure, fuel=fuel, handling=handling, scope=scope), realised_duration


def case_outputs(studies_, master, settings, root, smoke):
    summaries, break_even, exclusions, conditional, choices = [], [], [], [], []
    for idx, (study, historic_hours) in enumerate(studies_):
        config = Sampling(seed=seed_for(master, 530 + idx), minPower=3 if smoke else 6,
                          maxPower=4 if smoke else 11, standardErrorThreshold=25)
        rows, worlds, diag = adaptive(study, config)
        rule = RuleSettings(rule="R1")
        winner = decide(study, rows, worlds, rule, evaluate_wait=False)
        for name in ("R1", "R2", "R3", "R4", "R5"):
            result = decide(study, rows, worlds, RuleSettings(rule=name, **settings), evaluate_wait=False)
            choices.append({"case": study.problemId, "rule": name, "selected": result["optionId"],
                            "reason": result["reason"]})
        sweep = closure_sweep(study, config, rule)
        for flip in sweep["flips"] or [{}]:
            break_even.append({"case": study.problemId, "rule": "R1", **flip,
                               "scope": "flip bracket" if flip else "No flip within the registered grid",
                               "gridMinHours": sweep["grid"][0]["closureHours"],
                               "gridMaxHours": sweep["grid"][-1]["closureHours"],
                               "futuresPerPoint": sweep["samplesPerGridPoint"]})
        arrival_fig, arrival_ax = plt.subplots(figsize=(6.5, 2.7))
        cost_fig, cost_ax = plt.subplots(figsize=(6.5, 3))
        for i, row in enumerate(rows):
            costs = row.costs.known_subtotal
            lower, mid, upper = np.quantile(row.arrival, [.1, .5, .9])
            mean = replicate_ci(costs, worlds.scrambles)
            tail = replicate_ci(costs, worlds.scrambles, cvar)
            arrival_ax.hlines(i, lower, upper, color=PALETTE[i], linewidth=9, alpha=.38)
            arrival_ax.scatter(mid, i, color=PALETTE[i], zorder=3)
            cost_ax.step(np.sort(costs), np.linspace(1 / len(costs), 1, len(costs)), label=row.option.label,
                         where="post", color=PALETTE[i])
            summaries.append({
                "case": study.problemId, "scope": study.scope, "option": row.option.id, "label": row.option.label,
                "selectedR1": row.option.id == winner["optionId"], "reasonR1": winner["reason"],
                "physicalSailingHours": (20 if row.option.id == "keep" else 24) if idx == 0 else None,
                "conditionalApproachHours": row.option.cleanDeliveryHours if idx == 0 else None,
                "modelledFuelTonnes": row.option.fuelTonnes, "arrivalP10Hours": lower,
                "arrivalP50Hours": mid, "arrivalP90Hours": upper, "meanUsd": mean["estimate"],
                "meanLower95Usd": mean["lower95"], "meanUpper95Usd": mean["upper95"], "cvar95Usd": tail["estimate"],
                "cvarLower95Usd": tail["lower95"], "cvarUpper95Usd": tail["upper95"],
                "samples": diag["n"], "seed": config.seed, "inputHash": input_key(study, config),
                "stop": diag["stop"], "unknownCount": len(row.costs.unknown),
            })
            for component, reason in row.costs.unknown.items():
                exclusions.append({"case": study.problemId, "option": row.option.id, "component": component, "reason": reason})
            if historic_hours is not None:
                observed = sample_losses(study, row.option, worlds,
                                         closure_hours=np.full(worlds.samples, historic_hours))
                estimate = replicate_ci(observed.costs.known_subtotal, worlds.scrambles)
                conditional.append({"case": study.problemId, "option": row.option.id, "recordedClosureHours": historic_hours,
                                    "illustrativeMeanUsd": estimate["estimate"], "lower95": estimate["lower95"],
                                    "upper95": estimate["upper95"]})
        arrival_ax.set(yticks=range(len(rows)), yticklabels=[row.option.label for row in rows],
                       xlabel="Modelled delivery time (h after decision)", title="Arrival fan · P10, P50, P90")
        arrival_ax.grid(axis="x", alpha=.2)
        cost_ax.set(xlabel="Modelled known cost subtotal (USD)", ylabel="Cumulative probability", ylim=(0, 1.03))
        cost_ax.legend(frameon=False, loc="lower right")
        cost_ax.grid(alpha=.2)
        save(arrival_fig, root, f"e5-{study.problemId}-arrival")
        save(cost_fig, root, f"e5-{study.problemId}-cost")
    return summaries, break_even, exclusions, conditional, choices


def variance(study, master, root, smoke):
    powers = tuple(range(4, 7 if smoke else 13))
    config = Sampling(seed=seed_for(master, 520), minPower=4, maxPower=powers[-1], scrambles=16)
    pilot = map_futures(study, worlds_for(config, powers[-1], stream=2))
    top = sorted(study.options, key=lambda opt: sample_losses(study, opt, pilot).costs.known_subtotal.mean())[:2]
    modes = ("Independent PRNG", "CRN PRNG", "CRN scrambled Sobol")
    records, stable = [], []
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for color, mode in zip(PALETTE, modes):
        result = []
        first, previous = None, None
        for power in powers:
            method = "sobol" if mode.endswith("Sobol") else "random"
            a = map_futures(study, worlds_for(config, power, method=method))
            b = map_futures(study, worlds_for(config, power, method=method, stream=1)) if mode == modes[0] else a
            costs = [sample_losses(study, opt, world).costs.known_subtotal for opt, world in zip(top, (a, b))]
            gap = replicate_ci(costs[1] - costs[0], config.scrambles)
            sign = 1 if gap["lower95"] > 0 else -1 if gap["upper95"] < 0 else 0
            if sign and sign == previous and first is None:
                first = a.samples
            previous = sign
            result.append({"method": mode, "futuresPerOption": a.samples, "preferredPilotOption": top[0].id,
                           "runnerUpPilotOption": top[1].id, "differenceUsd": gap["estimate"],
                           "standardErrorUsd": gap["standardError"], "lower95": gap["lower95"], "upper95": gap["upper95"]})
        stable.append({"method": mode, "futuresPerOptionToStableRank": first,
                       "criterion": "Two consecutive same-sign 95% intervals excluding zero"})
        records.extend(result)
        ax.loglog([row["futuresPerOption"] for row in result],
                  [row["standardErrorUsd"] or np.nan for row in result], marker="o", label=mode, color=color)
    ax.set(xlabel="Futures per option (16 replicates combined)", ylabel="SE of paired mean cost gap (USD)")
    ax.legend(frameon=False)
    ax.grid(which="both", alpha=.2)
    save(fig, root, "e2-variance")
    return records, stable


FACTORS = ("Closure median", "Penalty rate", "War-risk premium", "Fuel price", "Shelf life", "Handling delay")


def scaled_study(study, factors):
    closure, penalty, war, fuel, shelf, handling = map(float, factors)
    consignments = []
    for cargo in study.consignments:
        terms = cargo.riskTerms.model_dump(mode="json")
        amount = terms["latePenalty"]["value"]["amount"]
        amount["amount"] = (Decimal(amount["amount"]) * Decimal(str(penalty))).quantize(Decimal("0.000001"))
        for area in terms["warRiskAreas"]["value"]:
            premium = area["premiumRate"]
            premium["value"] = (Decimal(premium["value"]) * Decimal(str(war))).quantize(Decimal("0.000001"))
        if terms["remainingShelfLifeHours"]:
            terms["remainingShelfLifeHours"]["value"] = float(terms["remainingShelfLifeHours"]["value"]) * shelf
        # Legacy shelf-life fallback is untouched and subordinate to the new sourced value.
        consignments.append(cargo.model_copy(update={"riskTerms": type(cargo.riskTerms).model_validate(terms)}))
    return study.model_copy(update={
        "closure": study.closure.model_copy(update={"medianHours": study.closure.medianHours * closure}),
        "fuel": study.fuel.model_copy(update={"low": study.fuel.low * fuel, "high": study.fuel.high * fuel}),
        "handling": study.handling.model_copy(update={k: getattr(study.handling, k) * handling
                                                      for k in ("minimum", "mode", "maximum")}),
        "consignments": tuple(consignments),
    })


def sensitivity(study, master, root, smoke):
    config = Sampling(seed=seed_for(master, 521), minPower=3, maxPower=3, scrambles=4)
    uniforms = worlds_for(config, config.minPower)
    options = [next(option for option in study.options if option.id == name) for name in ("keep", "cape")]

    def margin(factors):
        changed = scaled_study(study, factors)
        world = map_futures(changed, uniforms)
        keep, cape = (sample_losses(changed, option, world).costs.known_subtotal for option in options)
        return keep - cape

    base = np.ones(len(FACTORS))
    tornado = []
    for index, name in enumerate(FACTORS):
        low, high = base.copy(), base.copy()
        low[index], high[index] = .5, 1.5
        for tag, values in (("low", low), ("base", base), ("high", high)):
            gap = replicate_ci(margin(values), config.scrambles)
            tornado.append({"factor": name, "endpoint": tag, "multiplier": values[index],
                            "keepMinusCapeUsd": gap["estimate"], "lower95": gap["lower95"], "upper95": gap["upper95"]})

    first, total = [], []
    scrambles = 4 if smoke else 8
    power = 2 if smoke else 7
    for replicate in range(scrambles):
        u = qmc.Sobol(12, scramble=True, seed=np.random.default_rng(
            np.random.SeedSequence([master, 522, replicate]))).random_base2(power) + .5
        a, b = u[:, :6], u[:, 6:]
        f_a, f_b = (np.asarray([margin(row).mean() for row in matrix]) for matrix in (a, b))
        variance_ = np.var(np.r_[f_a, f_b], ddof=1)
        by_factor = []
        for index in range(6):
            mixed = a.copy()
            mixed[:, index] = b[:, index]
            f_ab = np.asarray([margin(row).mean() for row in mixed])
            by_factor.append((1 - np.mean((f_b - f_ab)**2) / (2 * variance_),
                              np.mean((f_a - f_ab)**2) / (2 * variance_)))
        first.append([value[0] for value in by_factor])
        total.append([value[1] for value in by_factor])
    indices = []
    for idx, factor in enumerate(FACTORS):
        for kind, array in (("first", first), ("total", total)):
            estimate = replicate_ci(np.asarray(array)[:, idx], scrambles)
            indices.append({"factor": factor, "index": kind, "estimate": estimate["estimate"],
                            "lower95": estimate["lower95"], "upper95": estimate["upper95"],
                            "outerPairsPerScramble": 2**power, "scrambles": scrambles, "innerFutures": len(uniforms.reshape(-1, 8))})

    fig, ax = plt.subplots(figsize=(6.6, 3.3))
    central = tornado[1]["keepMinusCapeUsd"]
    for idx, name in enumerate(FACTORS):
        for offset, row, color in ((-.17, tornado[3 * idx], PALETTE[0]), (.17, tornado[3 * idx + 2], PALETTE[1])):
            diff = row["keepMinusCapeUsd"] - central
            ax.barh(idx + offset, diff, height=.32, color=color, label=row["endpoint"] if idx == 0 else None)
    ax.axvline(0, color="#444444", linewidth=.7)
    ax.set(yticks=range(len(FACTORS)), yticklabels=FACTORS, xlabel="Change in keep-minus-Cape mean cost (USD)")
    ax.invert_yaxis()
    ax.legend(frameon=False)
    save(fig, root, "e3-tornado")

    fig, ax = plt.subplots(figsize=(6.6, 3.3))
    for idx, row in enumerate(indices):
        x = row["estimate"]
        ax.errorbar(x, idx // 2 + (.16 if idx % 2 else -.16), xerr=[[x - row["lower95"]], [row["upper95"] - x]],
                    fmt="o", color=PALETTE[idx % 2], label=row["index"] if idx < 2 else None)
    ax.set(yticks=range(len(FACTORS)), yticklabels=FACTORS, xlabel="Sobol sensitivity index (95% replicate interval)")
    ax.invert_yaxis()
    ax.legend(frameon=False)
    save(fig, root, "e3-sobol")
    return tornado, indices


def runtime(study, master, smoke):
    cargo = tuple(item.model_copy(update={"id": f"{item.id}-{i}"})
                  for i in range(3) for item in study.consignments)
    stress = study.model_copy(update={"consignments": cargo})
    matched = stress.model_copy(update={"options": tuple(
        option.model_copy(update={"cleanDeliveryHours": 180, "reachClosureHour": None, "areas": (),
                                  "handlingExposure": 1, "unpoweredHours": 2}) for option in study.options
    )})
    rows = []
    for profile, trial in (("matched clocks", matched), ("Suez stress", stress)):
        for idx in range(1 if smoke else 3):
            config = Sampling(seed=seed_for(master, 540 + idx), minPower=3 if smoke else 6,
                              maxPower=4 if smoke else 11, standardErrorThreshold=25)
            started = perf_counter()
            _, _, diag = adaptive(trial, config)
            rows.append({"profile": profile, "seed": config.seed, "seconds": perf_counter() - started,
                         "options": len(trial.options), "consignments": len(cargo), "futures": diag["n"],
                         "stop": diag["stop"], "pairedSeUsd": diag["difference"]["standardError"],
                         "thresholdUsd": config.standardErrorThreshold})
    return rows
