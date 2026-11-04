"""Company-scoped retained snapshots for the derived fleet worklist.

No engine/store constructors, provider calls or recovery writes run here.
The caller authenticates membership and holds the existing visitor mutation
lock; repeated read snapshots detect writers outside that boundary.
"""
from src.utils.settings import get_settings

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3


def _json(raw, default=None):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        return value if isinstance(value, (dict, list)) else default
    except (ValueError, TypeError):
        return default


def _connect(path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def _decisions(root, world, identity):
    from backend.app.identity import may_see_decision
    path = root / "ledger.sqlite3"
    if not path.exists():
        return [], []
    owned = {v["id"] for v in world.get("fleet", []) if isinstance(v, dict) and isinstance(v.get("id"), str)}
    if not owned:
        return [], []
    connection = _connect(path)
    try:
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "decision_problems" not in tables:
            return [], []
        # Membership is checked from server-owned columns before loading any
        # payload. Port representations are admitted only by explicit Company
        # proposal links after their body has been checked below.
        placeholders = ",".join("?" for _ in owned)
        rows = connection.execute(f"SELECT * FROM decision_problems WHERE subject IN ({placeholders}) AND actor IN (?,?)",
            [*sorted(owned), "SHIPPING_COMPANY", "PORT_AUTHORITY"]).fetchall()
        company, port, malformed = [], [], []
        for row in rows:
            frozen = _json(row["problem"], {})
            saved = connection.execute("SELECT state FROM decision_continuations WHERE problem_id=?", (row["problem_id"],)).fetchone() if "decision_continuations" in tables else None
            continuation = _json(saved[0], {}) if saved else {}
            bad_continuation = saved is not None and (not isinstance(continuation, dict) or not continuation)
            if bad_continuation:
                malformed.append({"decisionId": row["problem_id"], "vesselId": row["subject"], "code": "MALFORMED_RETAINED_CONTINUATION"})
                continuation = {}
            body = continuation or frozen
            if not isinstance(body, dict) or not body:
                malformed.append({"decisionId": row["problem_id"], "vesselId": row["subject"], "code": "MALFORMED_RETAINED_COMPARISON"})
                continue
            if (not isinstance(body.get("subject"), dict) or not isinstance(body.get("actor"), dict)
                    or not isinstance(body.get("evidence"), dict)
                    or body.get("decisionId") != row["problem_id"] or body["subject"].get("id") != row["subject"]
                    or body["actor"].get("role") != row["actor"]):
                malformed.append({"decisionId": row["problem_id"], "vesselId": row["subject"], "code": "INCONSISTENT_RETAINED_COMPARISON"})
                continue
            body = deepcopy(body)
            if bad_continuation:
                body["_triageContinuationUnavailable"] = True
            body.update(workflow=row["workflow"], humanChoice=row["human_choice"])
            if row["observed_outcome"]:
                body["observedOutcome"] = _json(row["observed_outcome"], {})
            actor = body.get("actor") or {}
            if any(actor.get(key) is not None and not isinstance(actor.get(key), str) for key in ("role", "organisation", "portCode")):
                malformed.append({"decisionId": row["problem_id"], "vesselId": row["subject"], "code": "MALFORMED_RETAINED_ACTOR"})
                continue
            if row["actor"] == "SHIPPING_COMPANY" and may_see_decision(identity, actor, body["subject"], body.get("domain") or ""):
                company.append(body)
            elif row["actor"] == "PORT_AUTHORITY" and actor.get("role") == "PORT_AUTHORITY":
                port.append(body)
        source_ids = {body["decisionId"] for body in company}
        linked = []
        for body in port:
            proposal = body["evidence"].get("companyProposal")
            if not isinstance(proposal, dict) or not isinstance(proposal.get("decisionId"), str):
                malformed.append({"decisionId": body["decisionId"], "vesselId": body["subject"]["id"], "code": "MALFORMED_RETAINED_PORT_LINK"})
            elif proposal["decisionId"] in source_ids:
                linked.append(body)
        return company + linked, malformed
    finally:
        connection.close()


def _advisories(root, world, decision_ids):
    path = root / "advisories.sqlite3"
    if not path.exists():
        return []
    owned = {v["id"] for v in world.get("fleet", []) if isinstance(v, dict) and isinstance(v.get("id"), str)}
    if not owned:
        return []
    connection = _connect(path)
    try:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='advisories'").fetchone():
            return []
        placeholders = ",".join("?" for _ in owned)
        rows = connection.execute(f"SELECT * FROM advisories WHERE recipient_vessel_id IN ({placeholders})", sorted(owned)).fetchall()
        result = []
        for row in rows:
            evidence = _json(row["evidence"], {})
            if not isinstance(evidence, dict):
                continue
            if not isinstance(evidence.get("decisionId"), str) or evidence["decisionId"] not in decision_ids:
                continue
            result.append({"advisoryId": row["advisory_id"], "kind": row["kind"], "state": row["state"],
                "portCode": row["port_code"], "recipientVesselId": row["recipient_vessel_id"],
                "validUntil": row["valid_until"], "issuedAt": row["issued_at"], "respondedAt": row["responded_at"],
                "evidence": evidence, "recommendation": _json(row["recommendation"], {})})
        return result
    finally:
        connection.close()


def _fingerprint(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()


def retained_snapshot(scoped, store, credential, identity):
    """Two complete equal reads, with at most one bounded retry.

    Uses the same root selected by the authenticated demo dependency. A reset
    must first bind its new generation in a new request, never redirect this
    request into a caller-chosen namespace.
    """
    def read():
        world = store.read(credential)
        if world.get("organisation") != identity.organisation:
            raise ValueError("The authenticated Company does not own this visitor fleet")
        if world.get("epoch") != scoped.world.get("epoch"):
            raise ValueError("The visitor world was reset while reading; refresh the worklist")
        from backend.app.services.demo_terminal import demo_hulls
        world = {**world, "fleet": demo_hulls(world, identity)}
        decisions, malformed = _decisions(scoped.root, world, identity)
        advisories = _advisories(scoped.root, world, {d["decisionId"] for d in decisions})
        return {"world": world, "decisions": sorted(decisions, key=lambda d: d["decisionId"]),
            "advisories": sorted(advisories, key=lambda a: a["advisoryId"]), "malformed": malformed}
    before = read()
    for _ in range(2):
        after = read()
        if _fingerprint(before) == _fingerprint(after):
            return after, True
        before = after
    return before, False


def cached_source_leads(world, environment_root, as_of):
    """Bounded regional warning context over retained catalogue bytes only."""
    coverage = {"status": "MISSING", "checkedAt": None,
        "reason": "No retained source catalogue available; missing coverage does not establish a clear route"}
    try:
        from src.portwatch_os.global_eye.exposure import TRADE_LANES
        from src.portwatch_os.intelligence.indian_review import exposure
        from src.portwatch_os.intelligence.notice_catalogue import retained
        from src.portwatch_os.intelligence.timestamps import instant
        from src.portwatch_os.intelligence.voyage_exposure import source_validity
        catalogue = retained(environment_root, as_of)
        notices = catalogue.get("notices")
        if not isinstance(notices, list):
            raise ValueError()
        if not notices: return [], coverage
        vessels_by_area = {"NHO_NAVAREA_VIII": [], "NHO_NAVAREA_IX": []}
        for vessel in world.get("fleet", []):
            if str(vessel.get("portCode") or "").startswith("IN"):
                vessels_by_area["NHO_NAVAREA_VIII"].append(vessel)
            lane = TRADE_LANES.get(vessel.get("laneCode"))
            if lane and {"BAB_EL_MANDEB", "HORMUZ"}.intersection(lane.chokepoints):
                vessels_by_area["NHO_NAVAREA_IX"].append(vessel)

        candidates = []
        malformed = 0
        for notice in notices:
            if not isinstance(notice, dict) or not isinstance(notice.get("title"), str):
                malformed += 1
                continue
            vessels = vessels_by_area.get(notice.get("sourceFamily"))
            if (not vessels or notice.get("status") != "REVIEW_CONTEXT"
                    or source_validity(notice, as_of) != "CURRENT_PRODUCT_DATE"):
                continue
            try:
                issued = instant(notice["providerIssueAt"])
                if issued > as_of:
                    continue
                for vessel in vessels:
                    row = exposure(notice, vessel, as_of)
                    candidates.append((row, issued))
            except (KeyError, ValueError, TypeError, AttributeError):
                malformed += 1
        relevance = {"DECLARED_REVIEW_CONTEXT": 0, "POSSIBLE_EXPOSURE": 1}
        candidates.sort(key=lambda item: (relevance.get(item[0]["status"], 2),
            -item[1].timestamp(), item[0]["noticeId"], item[0]["vesselId"]))
        rows, seen = [], {}
        for row, _ in candidates:
            vessel_notices = seen.setdefault(row["vesselId"], set())
            if len(vessel_notices) < 5 and row["noticeId"] not in vessel_notices:
                vessel_notices.add(row["noticeId"])
                row["priority"]["rank"] = len(rows) + 1
                rows.append(row)
        return rows, {"status": "MALFORMED" if malformed else "RETAINED", "checkedAt": catalogue.get("checkedAt") if isinstance(catalogue.get("checkedAt"), str) else None,
            "reason": f"Up to five current NAVAREA VIII/IX warnings per voyage; {malformed} malformed catalogue records excluded. Regional context does not establish a crossing or a clear route."}
    except (OSError, ValueError, TypeError, AttributeError):
        return [], {**coverage, "status": "MALFORMED", "reason": "Retained source catalogue could not be read; source coverage is unknown"}


def project_snapshot(snapshot, *, as_of: datetime, clock_mode, consistent):
    from src.portwatch_os.decision.fleet_triage import project_fleet_triage
    from src.portwatch_os.decision.triage_freshness import collect_retained_dependencies, evaluate_freshness
    project_root = Path(__file__).resolve().parents[3]
    environment_root = Path(get_settings().PORTWATCH_CURRENT_ENVIRONMENT_DIR or project_root / "data/cache/current_environment")
    public_db = Path(get_settings().PORTWATCH_PUBLIC_FEEDBACK_DB or Path(get_settings().PORTWATCH_STATE_DIR or project_root / "outputs") / "portwatch_ledger.db")
    world, decisions, advisories = snapshot["world"], snapshot["decisions"], snapshot["advisories"]
    retained = collect_retained_dependencies(decisions, environment_root=environment_root, public_feedback_db=public_db, as_of=as_of)
    freshness = {d["decisionId"]: evaluate_freshness(d, world, as_of=as_of, clock_mode=clock_mode, retained=retained) for d in decisions}
    for decision in decisions:
        if decision.get("_triageContinuationUnavailable"):
            check = freshness[decision["decisionId"]]
            check["reasons"].append({"code": "MALFORMED_RETAINED_CONTINUATION", "text": "The immutable comparison is retained, but its workflow continuation cannot be fully verified.", "basis": "retained continuation", "decisionId": decision["decisionId"]})
            if check["status"] == "CURRENT":
                check["status"] = "UNKNOWN"
    result = project_fleet_triage(world, decisions, advisories, as_of=as_of, freshness=freshness, snapshot_consistent=consistent)
    from src.portwatch_os.intelligence.indian_notices import retained as indian_retained
    from src.portwatch_os.intelligence.indian_review import annotate_worklist
    try: indian = retained.get('indianNotices') if 'indianNotices' in retained else indian_retained(root=environment_root/'indian_notices',as_of=as_of)['notices']
    except (ValueError,TypeError,KeyError,AttributeError): indian=[]
    annotate_worklist(result,world,decisions,indian,at=as_of)
    from src.portwatch_os.intelligence import port_context_review
    port_context=port_context_review.view(world,as_of)
    port_context_review.annotate(result,world,decisions,port_context,at=as_of)
    result['portContextCoverage']={k:port_context.get(k) for k in ('sourceFamily','status','reportDate','revisionId','reason')}
    leads, lead_coverage = cached_source_leads(world, environment_root, as_of)
    result.update(sourceLeads=leads, sourceLeadCoverage=lead_coverage)
    result["coverage"]["malformedRetainedRecords"] = len(snapshot["malformed"])
    return result
