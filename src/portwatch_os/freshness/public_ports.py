"""Backend-owned public PDF collectors; one independently retried job per port."""
import os
from datetime import timedelta

from src.portwatch_os.clock import LIVE, get_clock, wall_now
from src.portwatch_os.freshness.job import JobOutcome, RefreshJob
from src.portwatch_os.freshness.policy import ArtifactProbe, FreshnessPolicy
from src.portwatch_os.intelligence.public_collection import collect_port, get_service
from src.portwatch_os.intelligence.public_ports import PORTS
from src.portwatch_os.learning.weather_feedback import instant


def enabled(name, default="1"):
    return (os.getenv(name) or default).strip().lower() not in ("0", "false", "no", "off")


def collection_eligibility():
    if not enabled("PORTWATCH_PUBLIC_PORT_AUTOREFRESH"):
        return "Automatic public-port collection is disabled on this backend"
    if get_clock().state.mode != LIVE:
        return "Public-port collection requires LIVE; paused during replay"
    return None


def public_port_jobs(service_getter=get_service):
    jobs = []
    for port in PORTS:
        def probe(port=port):
            # wall-clock: backend cadence uses actual successful receipts, not PDF first-seen time.
            status = service_getter().collection_status(port, wall_now())
            return ArtifactProbe(observed_at=instant(status["lastSuccessfulCollectionAt"]) if status["lastSuccessfulCollectionAt"] else None,
                detail={"portCode": port, "lastErrors": (status["lastRun"] or {}).get("errors", [])})

        def run(context, port=port):
            result = collect_port(service_getter(), port, "Backend public port collector")
            if result["errors"]:
                raise RuntimeError("; ".join(result["errors"]))
            return JobOutcome(changed=any(r.get("new") or r.get("reparsed") for r in result["refresh"]["results"]),
                observed_at=instant(result["finishedAt"]), detail={"portCode": port, "counts": result["counts"], "receipt": result["receipt"]})

        jobs.append(RefreshJob(policy=FreshnessPolicy(artifact="public_ports_"+port, label=f"Public port reports ({port})",
            provider="Paradip Port Authority" if port == "INPRT" else "Chennai Port Authority",
            fresh_for=timedelta(hours=3), stale_after=timedelta(hours=36), max_attempts=3,
            backoff_base=timedelta(minutes=1), backoff_cap=timedelta(hours=3),
            rationale="Collect official PDFs every three hours using successful receipt times; preserve first-seen evidence, frozen ETAs and fixed cohorts. Failed ports retry independently."),
            probe=probe, run=run, eligibility=collection_eligibility))
    return jobs
