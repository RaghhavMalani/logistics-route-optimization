"""Declared NHO review relationships and immutable decision dependencies.

No numerical consequence or operational target is produced here.
"""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json

from . import indian_notices as source
from .timestamps import instant
from .voyage_exposure import passage_for

VERSION = "indian-source-review-v1"
FIELDS = ("status", "areaId", "portCodes", "coordinates", "providerIssueAt", "extractionStatus", "extractionVersion", "semanticId", "restriction")


def declared_match(notice, vessel):
    plan = passage_for(vessel, notice.get("areaId")) if notice.get("areaId") else None
    current = vessel.get("operationalEpisode") or {}
    if not plan or plan.get("sourceFamily") != source.FAMILY: return None
    if not current.get("id") or (plan.get("operationalEpisode") or {}).get("id") != current["id"]: return None
    if notice.get("areaId") not in (plan.get("route") or []) or vessel.get("portCode") not in notice.get("portCodes", []): return None
    try: instant(plan["passageAt"])
    except (KeyError, TypeError, ValueError): return None
    return plan


def exposure(notice, vessel, now):
    plan = declared_match(notice, vessel)
    possible = vessel.get("portCode") in notice.get("portCodes", []) or notice.get("areaId") in (vessel.get("possibleAssetIds") or [])
    status = "DECLARED_REVIEW_CONTEXT" if plan else "POSSIBLE_EXPOSURE" if possible else "NO_DEMONSTRATED_EXPOSURE"
    reason = ("The operator explicitly declared this named navigation-aid passage for this owned call. This is a review relationship, not proof of actual crossing or future aid condition." if plan else
              "Destination/possible-asset association only; it does not establish route crossing. Confirm a declared passage and its time." if possible else "No declared route or reviewed port relationship to this notice is demonstrated.")
    if notice.get("sourceStatus") != "CURRENT_PRODUCT_DATE": reason += " The source product is historical/unqualified for today's condition."
    return {"noticeId": notice["noticeId"], "providerNoticeId": notice.get("providerNoticeId"), "title": notice["title"],
        "vesselId": vessel["id"], "vesselName": vessel.get("name", vessel["id"]), "assetId": notice.get("areaId"), "assetName": notice.get("area"),
        "status": status, "sourceStatus": notice.get("sourceStatus", "UNKNOWN"), "sourceValidity": notice.get("sourceStatus", "UNKNOWN"), "reason": reason,
        "missingInputs": [] if plan else ["explicitRouteMembership", "plannedPassageAt", "currentCallDeclaration"],
        "calculable": False, "calculationReason": "Navigation-aid context has no reviewed closure/waiting calculator. Hours, cost, fuel and safety benefit remain unavailable.",
        "passageAt": plan.get("passageAt") if plan else None,
        "priority": {"rank": 0, "score": 0, "label": "Source review context", "reason": "Separate context lead; no risk or loss score", "hoursToDeclaredPassage": (instant(plan["passageAt"])-now).total_seconds()/3600 if plan else None}}


def freeze(scoped, vessel_id, selections, *, at):
    if selections is None: return []
    if not isinstance(selections, list) or not 1 <= len(selections) <= 16: raise ValueError("Select 1–16 exact Indian-source reviews or omit the field")
    vessel = next(v for v in scoped.world["fleet"] if v["id"] == vessel_id)
    notices = {n["noticeId"]:n for n in source.retained(as_of=at)["notices"]}
    bindings, seen = [], set()
    for selected in selections:
        if not isinstance(selected, dict) or selected.get("acknowledged") is not True: raise ValueError("Explicit source-context review acknowledgement required")
        if not isinstance(selected.get('noticeId'), str) or not isinstance(selected.get('revisionId'), str):
            raise ValueError("Exact retained notice and revision strings required")
        notice = notices.get(selected.get("noticeId"))
        if not notice or notice["noticeId"] in seen or notice.get("revisionId") != selected.get("revisionId"): raise ValueError("Select each exact retained current source revision once")
        seen.add(notice["noticeId"])
        plan = declared_match(notice, vessel)
        if not plan or instant(plan["passageAt"]) <= at: raise ValueError("An explicit future named-aid passage in this owned call is required")
        if notice.get("sourceStatus") != "CURRENT_PRODUCT_DATE" or notice.get("status") not in ("REVIEW_CONTEXT","SOURCE_NOTICE_CANCELLED") or notice.get("extractionStatus") != "CONTEXT_METADATA":
            raise ValueError("Historical, cancelled or unqualified NHO evidence cannot support a new active review binding; numerical consequences remain unavailable")
        sha = notice.get("latestResponseSha256") or notice.get("responseSha256")
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha): raise ValueError("Original source identity unavailable")
        path = source.root_path()/(sha+".response")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha: raise ValueError("Original NHO evidence unavailable or corrupt")
        snapshot = {key:deepcopy(notice.get(key)) for key in FIELDS}
        binding = {"contractVersion": VERSION, "sourceFamily": source.FAMILY, "noticeId": notice["noticeId"], "revisionId": notice["revisionId"],
            "sourceSnapshot": snapshot, "source": notice["source"], "documentPages": notice.get("latestDocumentPages", notice.get("documentPages", [])),
            "productAsOfDate": notice["productAsOfDate"], "productPrecision": "DATE_ONLY", "availableAt": notice["availableAt"],
            "sourceCheckedAt": notice["checkedAt"], "originalSha256": sha, "declaration": deepcopy(plan), "consumedAt": at.isoformat(),
            "calculationRole": "CONTEXT_ONLY_REVIEWED", "numericalEffect": None,
            "meaning": "Operator-reviewed navigation-aid context; hourly weather and declared passage/cargo inputs alone drive numeric options. Future aid condition and actual execution remain unverified."}
        binding["id"] = source.digest(binding); bindings.append(binding)
    return bindings


def assess(bindings, world, notices, *, at):
    current = {n["noticeId"]:n for n in notices}; findings = []
    for binding in bindings or []:
        identity = binding.get("noticeId"); notice = current.get(identity)
        plan = binding.get("declaration") or {}; vessel = next((v for v in world.get("fleet", []) if v.get("id") == plan.get("vesselId")), None)
        changes = []
        if notice:
            for field in FIELDS:
                before, after = (binding.get("sourceSnapshot") or {}).get(field), notice.get(field)
                if before != after: changes.append({"field": field, "before": before, "after": after})
        code, text = None, None
        if not notice: code, text = "INDIAN_SOURCE_UNAVAILABLE", "The consumed NHO identity is unavailable at this query instant."
        elif notice.get("revisionId") != binding.get("revisionId"):
            code, text = "INDIAN_SOURCE_REVISION_CHANGED", "The consumed NHO interpretation/revision changed; review an explicit successor."
        elif notice.get("sourceStatus") != "CURRENT_PRODUCT_DATE" or notice.get("status") not in ("REVIEW_CONTEXT","SOURCE_NOTICE_CANCELLED"):
            code, text = "INDIAN_SOURCE_VALIDITY_CHANGED", "The consumed source is historical, expired, unavailable, cancelled or otherwise unqualified for continuation."
        elif at > instant(binding["sourceCheckedAt"])+source.TTL:
            code, text = "INDIAN_SOURCE_RECEIPT_EXPIRED", "The frozen source check is outside its six-hour continuation window; explicitly review refreshed evidence."
        if vessel is None or (passage_for(vessel, plan.get("areaId")) or {}).get("id") != plan.get("id"):
            code, text = "INDIAN_DECLARATION_CHANGED", "The consumed named-aid route, passage or call declaration changed."
        elif instant(plan["passageAt"]) <= at:
            code, text = "INDIAN_PASSAGE_ELAPSED", "The scheduled passage time elapsed; actual crossing is not established."
        if code:
            findings.append({"code": code, "text": text, "basis": "sourceReviewBindings:"+str(identity), "noticeId": identity,
                "consumedRevisionId": binding.get("revisionId"), "currentRevisionId": notice.get("revisionId") if notice else None,
                "consumedAvailableAt": binding.get("availableAt"), "currentAvailableAt": notice.get("availableAt") if notice else None,
                "changes": changes, "unknown": "Actual aid condition, vessel execution, delay and savings remain unverified.",
                "nextAction": "Review current inputs and explicitly create a linked successor; preserve earlier approvals/advisories."})
    return findings


def annotate_worklist(projection, world, decisions, notices, *, at):
    """Separate Company source review from the existing journey's next role/order."""
    by_id = {d.get('decisionId'):d for d in decisions if isinstance(d,dict)}
    fleet = {v['id']:v for v in world.get('fleet',[]) if isinstance(v,dict) and v.get('id')}
    for row in projection['rows']:
        row['sourceReviews'] = []
        if row['workflow'].get('completed'): continue
        vessel=fleet[row['vessel']['id']]
        decision=by_id.get(row['currentPlan'].get('decisionId'),{})
        evidence=decision.get('evidence') or {};basis=evidence.get('currentEnvironment') or evidence.get('intelligenceBasis') or {}
        consumed={b.get('noticeId') for b in basis.get('sourceReviewBindings',[]) if isinstance(b,dict)}
        for notice in notices:
            if notice.get('noticeId') in consumed or notice.get('sourceStatus')!='CURRENT_PRODUCT_DATE' or notice.get('status')!='REVIEW_CONTEXT' or notice.get('extractionStatus')!='CONTEXT_METADATA':continue
            plan=declared_match(notice,vessel)
            if not plan or instant(plan['passageAt'])<=at:continue
            row['sourceReviews'].append({'noticeId':notice['noticeId'],'revisionId':notice['revisionId'],'title':notice['title'],
                'sourceStatus':notice['sourceStatus'],'responsibleRole':'SHIPPING_COMPANY','passageAt':plan['passageAt'],
                'reason':'This owned call explicitly declares the named-aid passage. The current saved plan has not consumed this source review; workflow next-role remains separate.',
                'action':'Inspect source, then explicitly review current inputs. No numerical delay or closure is inferred.'})
        if row['sourceReviews']:
            row['reasons'].append({'code':'INDIAN_SOURCE_REVIEW_REQUIRED','text':'Company source review is needed for an explicitly declared named-aid context. This does not return an issued advisory to Company approval.',
                'basis':'Operator-declared current-call passage + qualified source product; not yet consumed'})
    reason_counts={}
    for row in projection['rows']:
        for code in {r['code'] for r in row['reasons']}:reason_counts[code]=reason_counts.get(code,0)+1
    projection['reasonCounts']=dict(sorted(reason_counts.items()));projection['sourceReviewPolicyVersion']=VERSION
    return projection
