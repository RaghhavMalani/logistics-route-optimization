"""Paired held-out analysis. Cases, rather than simulated futures, are resampled."""

from __future__ import annotations

import warnings

import numpy as np
from scipy.stats import wilcoxon

from src.portwatch_os.decision.paper_corpus import DOMAINS, INCUMBENT, POLICIES, cases, evaluate


def score_split(split, seed, settings, smoke):
    rows, errors = [], []
    for domain in DOMAINS:
        for case, failure in cases(split, domain, seed, smoke=smoke):
            if failure:
                errors.append(failure)
                continue
            rows.extend(evaluate(case, seed, **settings, smoke=smoke))
    return rows, errors


def statistics(rows):
    hours = np.asarray([row["hoursRegret"] for row in rows], dtype=float)
    cost = np.asarray([row["costRegret"] for row in rows], dtype=float)
    acts = np.asarray([row["acted"] for row in rows], dtype=float)
    bad = np.asarray([row["unnecessary"] for row in rows], dtype=float)
    eligible = np.asarray([row["actIsBest"] for row in rows], dtype=float)
    captures = np.asarray([row["captured"] for row in rows], dtype=float)
    elapsed = np.asarray([row["decisionMs"] for row in rows], dtype=float)
    return hours, cost, acts, bad, eligible, captures, elapsed


def divide(a, b):
    return np.divide(a, b, out=np.full(np.shape(a), np.nan), where=b > 0)


def metrics(vectors):
    hours, cost, acts, bad, eligible, captures, elapsed = vectors
    result = {}
    for label, values in (("hours", hours), ("costUsd", cost)):
        result[label + "Mean"] = values.mean(axis=-1)
        result[label + "Median"] = np.median(values, axis=-1)
        result[label + "P90"] = np.quantile(values, .9, axis=-1)
        result[label + "Worst"] = values.max(axis=-1)
    result.update(
        zeroRegret=(cost <= 1e-9).mean(axis=-1),
        intervention=acts.mean(axis=-1),
        unnecessary=divide(np.nansum(bad, axis=-1), np.isfinite(bad).sum(axis=-1)),
        capture=divide(captures.sum(axis=-1), eligible.sum(axis=-1)),
        decisionMsMedian=np.median(elapsed, axis=-1),
    )
    return result


def paired(left, right):
    a, b = ({row["case"]: row for row in rows if row["scored"]} for rows in (left, right))
    ids = sorted(a.keys() & b.keys())
    return [a[key] for key in ids], [b[key] for key in ids]


def ci(values):
    finite = np.asarray(values)[np.isfinite(values)]
    return tuple(map(float, np.quantile(finite, [.025, .975]))) if len(finite) else (None, None)


def compare(rows, seed, resamples, offered):
    headlines, intervals, tests = [], [], []
    for domain_index, domain in enumerate(DOMAINS):
        by_policy = {p: [row for row in rows if row["domain"] == domain and row["policy"] == p]
                     for p in POLICIES}
        for policy in POLICIES:
            complete = by_policy[policy]
            valid = [row for row in complete if row["scored"]]
            eligible = sum(row["actIsBest"] for row in complete)
            captured = sum(row["captured"] for row in complete)
            summary = metrics(statistics(valid)) if valid else {}
            summary["capture"] = captured / eligible if eligible else None
            headlines.append({
                "domain": domain, "policy": policy, "offered": offered,
                "scored": len(valid), "interventions": sum(row["acted"] for row in valid),
                "unnecessaryInterventions": sum(row["unnecessary"] is True for row in valid),
                "assessableInterventions": sum(row["unnecessary"] is not None for row in valid),
                "captured": captured, "actIsBest": eligible,
                **{k: (float(v) if v is not None and np.isfinite(v) else None) for k, v in summary.items()},
            })
            left, right = paired(complete, by_policy[INCUMBENT])
            if not left:
                continue
            lv, rv = statistics(left), statistics(right)
            idx = np.random.default_rng(np.random.SeedSequence([seed, 901, domain_index])).integers(
                0, len(left), (resamples, len(left))
            )
            lpoint, rpoint = metrics(lv), metrics(rv)
            lm, rm = metrics(tuple(a[idx] for a in lv)), metrics(tuple(b[idx] for b in rv))
            for metric in lpoint:
                delta = lpoint[metric] - rpoint[metric]
                lower, upper = ci(lm[metric] - rm[metric])
                intervals.append({"domain": domain, "policy": policy, "metric": metric,
                                  "pairedCases": len(left), "differenceVsIncumbent": float(delta) if np.isfinite(delta) else None,
                                  "lower95": lower, "upper95": upper,
                                  "validResamples": int(np.isfinite(lm[metric] - rm[metric]).sum())})
            for metric, a, b in (("hours", lv[0], rv[0]), ("costUsd", lv[1], rv[1])):
                differences = np.round(a - b, 9)
                nonzero = np.count_nonzero(differences)
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message="Sample size too small")
                    p = float(wilcoxon(differences, zero_method="pratt").pvalue) if nonzero else 1.0
                tests.append({"domain": domain, "policy": policy, "regret": metric,
                              "pairedCases": len(left), "nonzeroPairs": nonzero, "pTwoSided": p})
    return headlines, intervals, tests


def promotion(splits, gate, offered):
    checks = []
    for split, rows in splits.items():
        vessel = [row for row in rows if row["domain"] == "vessel" and row["policy"] == "R5"]
        cargo = [row for row in rows if row["domain"] == "cargo" and row["policy"] == "R5"]
        current = [row for row in rows if row["domain"] == "cargo" and row["policy"] == INCUMBENT]
        valid_vessel = [row for row in vessel if row["scored"]]
        captures, eligible = sum(row["captured"] for row in vessel), sum(row["actIsBest"] for row in vessel)
        left, right = paired(cargo, current)
        p90 = float(np.quantile([row["hoursRegret"] for row in valid_vessel], .9)) if valid_vessel else None
        cost = float(np.quantile([row["costRegret"] for row in left], .9)) if left else None
        reference = float(np.quantile([row["costRegret"] for row in right], .9)) if right else None
        for name, observed, limit in (
            ("vesselCoverage", len(valid_vessel) / offered[split], gate["minimumCoverageFraction"]),
            ("cargoCoverage", sum(row["scored"] for row in cargo) / offered[split], gate["minimumCoverageFraction"]),
            ("vesselCapture", captures / eligible if eligible else None, gate["vesselCaptureMinFraction"]),
            ("vesselP90Hours", p90, gate["vesselP90MaxHours"]),
            ("pairedCargoP90CostUsd", cost, reference * gate["cargoP90CostMaxRatioVsIncumbent"]
             if reference is not None else None),
        ):
            maximum = name in ("vesselP90Hours", "pairedCargoP90CostUsd")
            passed = observed is not None and limit is not None and (observed <= limit if maximum else observed >= limit)
            checks.append({"split": split, "metric": name, "observed": observed, "threshold": limit,
                           "comparison": "<=" if maximum else ">=", "passes": passed,
                           "captured": captures if name == "vesselCapture" else None,
                           "eligible": eligible if name == "vesselCapture" else None,
                           "pairedCases": len(left) if name == "pairedCargoP90CostUsd" else None})
    return checks


def time_only_comparison(rows, seed, resamples):
    cargo = [row for row in rows if row["domain"] == "cargo"]
    left, right = paired([r for r in cargo if r["policy"] == "time_only"], [r for r in cargo if r["policy"] == "R1"])
    if not left:
        return []
    difference = np.asarray([a["cost"] - b["cost"] for a, b in zip(left, right)])
    more = difference > 1e-9
    idx = np.random.default_rng(np.random.SeedSequence([seed, 904])).integers(0, len(left), (resamples, len(left)))
    return [
        {"metric": label, "estimate": value, "lower95": ci(draws)[0], "upper95": ci(draws)[1], "pairedCases": len(left)}
        for label, value, draws in (
            ("timeOnlyCostsMoreFraction", more.mean(), more[idx].mean(axis=1)),
            ("meanExtraUsdAllPairs", difference.mean(), difference[idx].mean(axis=1)),
            ("meanExtraUsdWhenMore", difference[more].mean() if more.any() else None,
             divide((difference * more)[idx].sum(axis=1), more[idx].sum(axis=1))),
        )
    ]
