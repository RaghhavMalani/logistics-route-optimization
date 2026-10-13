"""Predeclared collection rules; quality counts never impute operational labels."""
from datetime import timedelta

from src.portwatch_os.intelligence import arrival_model
from src.portwatch_os.learning.weather_feedback import instant

PROTOCOL = {"version": "jnpa-prospective-v1", "minimumQualifyingCalls": 60,
    "minimumFit": 24, "minimumCalibration": 10, "minimumHoldout": 10,
    "selection": "All enrolled calls before sealing; no selection by prediction error",
    "target": "confirmed anchorage arrival to confirmed all-fast, hours",
    "split": "60/20/20 by frozen issue time, with availability and recording purge",
    "maximumAisAgeHours": 1, "minimumAisReports": 2,
    "evaluationConfig": {"trees": 40, "depth": 2, "learningRate": 0.05, "seed": 168,
                         "variants": {k: list(v) for k, v in arrival_model.VARIANTS.items()}},
    "bias": "observed minus predicted", "intervalNominal": 0.8}


def baseline_verified(case):
    return bool(case.get("baselineRef") and case.get("baselineEstimatedAt") and case.get("baselineAvailableAt"))


def quality(cases, now):
    active = [c for c in cases if not c.get("disposition")]
    result = []
    for c in cases:
        f = c["features"]
        missing = [k for k in arrival_model.WEATHER if f.get(k) is None]
        flags = []
        if not baseline_verified(c):
            flags.append("MISSING_BASELINE_PROVENANCE")
        if f.get("wind_speed") is None:
            flags.append("MISSING_WIND_FORECAST")
        if f.get("trackCount", 0) < 2:
            flags.append("MISSING_AIS")
        if f.get("trackAgeHours") is not None and f["trackAgeHours"] > 1:
            flags.append("STALE_AIS_AT_ISSUE")
        duplicates = [o["operationId"] for o in active if o["operationId"] != c["operationId"]
                      and o["mmsi"] == c["mmsi"] and o["plannedArrivalAt"] == c["plannedArrivalAt"]]
        if duplicates and not c.get("disposition"):
            flags.append("POSSIBLE_DUPLICATE_CALL")
        if not c["outcome"] and not c.get("disposition"):
            flags.append("UNRESOLVED_CALL")
            if instant(c["plannedArrivalAt"])+timedelta(days=2) < now:
                flags.append("OVERDUE_OUTCOME")
        if c.get("disposition"):
            flags.append("EXCLUDED_"+c["disposition"]["reason"].upper())
        if c["outcome"] and c.get("cohortId") and not all(c["outcome"].get(k) for k in
                    ("arrivalAvailableAt", "allFastAvailableAt", "sourceRef")):
            flags.append("MISSING_OUTCOME_PROVENANCE")
        result.append({"operationId": c["operationId"], "operationRef": c["operationRef"],
                       "flags": flags, "missingWeather": missing, "duplicateCandidates": duplicates, "qualifying": not flags})
    return {"enrolledCount": len(cases), "confirmedCount": sum(bool(c["outcome"]) for c in cases),
            "qualifyingCount": sum(r["qualifying"] for r in result),
            "unresolvedCount": sum("UNRESOLVED_CALL" in r["flags"] for r in result),
            "overdueCount": sum("OVERDUE_OUTCOME" in r["flags"] for r in result),
            "missingEvidenceCount": sum(bool(r["missingWeather"]) or any(f.startswith("MISSING_") for f in r["flags"]) for r in result),
            "staleAisCount": sum("STALE_AIS_AT_ISSUE" in r["flags"] for r in result),
            "duplicateCandidateCount": sum("POSSIBLE_DUPLICATE_CALL" in r["flags"] for r in result),
            "excludedCount": sum(bool(c.get("disposition")) for c in cases), "calls": result}
