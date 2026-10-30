"""Small retained-family read seam. No collectors, writes or domain constructors."""
import json
from pathlib import Path
from .timestamps import instant
from . import indian_notices
from .source_registry import registry
from .voyage_exposure import queue, source_validity
from .indian_review import exposure as indian_exposure


def _read(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return None


def _legacy_history(root, family, now):
    found = {}
    for path in root.glob("*.json"):
        value = _read(path)
        if not isinstance(value, dict) or not value.get("revisionId") or not value.get("availableAt"): continue
        kind = value.get("sourceFamily") or ("PEEL_PORTS" if value.get("noticeRef") == "MNTM 2026-18" else None)
        if kind != family: continue
        try:
            if instant(value["availableAt"]) > now: continue
            identity = value.get("noticeId") or family+":"+str(value.get("noticeRef"))
            old = found.get(identity)
            if old is None or instant(value["availableAt"]) > instant(old["availableAt"]):
                found[identity] = {**value, "sourceFamily":family, "noticeId":identity, "sourceStatus":"CURRENT", "checkedAt":value["availableAt"]}
        except (ValueError, TypeError): continue
    return list(found.values())


def retained(root, as_of):
    root = Path(root); now = indian_notices.aware(as_of); legacy = root/"operational_notices"
    notices, checks, families = [], [], []
    # Eastham retains its dedicated lock/tide endpoint and semantics. It is not
    # fed into the NAVCEN bridge matcher or this metadata-only Indian family.
    for family, filename in (("NAVCEN_MSI","navcen-catalogue-latest.json"),):
        value = _read(legacy/filename)
        if value is None and family == "NAVCEN_MSI": value = _read(legacy/"navcen-53842-latest.json")
        status = "MISSING" if value is None else "MALFORMED" if not isinstance(value, dict) else value.get("sourceStatus", "RETAINED")
        rows = []
        if isinstance(value, dict):
            check = value.get("checkedAt")
            try:
                if check: instant(check)
            except (ValueError, TypeError, AttributeError):
                check = None; status = "MALFORMED"
            if check and instant(check) > now:
                rows = _legacy_history(legacy, family, now); status = "HISTORICAL_QUERY"
            else:
                if check: checks.append(check)
                if family == "NAVCEN_MSI" and "notices" in value: rows = value["notices"] if isinstance(value["notices"],list) else [None]
                else: rows = [value]
        for row in rows:
            if isinstance(row, dict):
                try:
                    if row.get("availableAt") and instant(row["availableAt"]) > now: continue
                except (ValueError, TypeError, AttributeError):
                    notices.append(None); continue
                row = {**row, "sourceFamily":family, "noticeId": row.get("noticeId") or (family+":"+str(row["noticeRef"]) if row.get("noticeRef") else None),
                    "providerNoticeId":row.get("providerNoticeId") or row.get("noticeRef")}
                row = {**row, "retainedSourceStatus":row.get("sourceStatus"), "sourceStatus":source_validity(row, now)}
            notices.append(row)
        families.append({"sourceFamily":family,"status":status,"records":len(rows)})
    try: indian = indian_notices.retained(root=root/"indian_notices",as_of=now)
    except (ValueError, TypeError, KeyError, AttributeError):
        indian = {"notices":[],"sourceStatus":"MALFORMED","checkedAt":None,"reason":"Retained Indian-source metadata cannot be qualified"}
    notices.extend(indian["notices"])
    if indian["checkedAt"]: checks.append(indian["checkedAt"])
    families.append({"sourceFamily":indian_notices.FAMILY,"status":indian["sourceStatus"],"records":len(indian["notices"]),"reason":indian.get("reason")})
    return {"notices":notices,"sourceStatus":"RETAINED" if notices else "MISSING", "checkedAt":max(checks,key=instant) if checks else None,
        "sourceRegistry":registry(),"families":families,"asOf":now.isoformat()}


def exposure_rows(notices, vessels, as_of):
    rows = []
    for notice in notices:
        if not isinstance(notice, dict): continue
        if notice.get("sourceFamily") == indian_notices.FAMILY:
            rows.extend(indian_exposure(notice, vessel, as_of) for vessel in vessels)
        else:
            rows.extend(queue([notice], vessels, as_of))
    rows.sort(key=lambda r:(-r["priority"]["score"],r["noticeId"],r["vesselId"]))
    for rank,row in enumerate(rows,1): row["priority"]["rank"]=rank
    return rows
