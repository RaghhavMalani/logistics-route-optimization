"""Explicit synthetic cases and real layout samples, only in isolated QA state."""
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from src.portwatch_os.clock import world_now
from src.portwatch_os.intelligence.public_ports import (
    CHENNAI_ETA, CHENNAI_POSITION, IST, PublicPilot, record,
)


def seed(state: Path):
    store = PublicPilot(state/"public_port_pilot")
    now = world_now()
    root = Path(__file__).resolve().parents[1]/"tests"/"fixtures"/"public_ports"
    samples = [
        ("INPRT", "traffic", "https://www.paradipport.gov.in/uploads/2026/10/dtr0610.pdf", "paradip-2026-10-06.pdf"),
        ("INMAA", "position", CHENNAI_POSITION, "chennai-position-2026-10-07.pdf"),
        ("INMAA", "expected", CHENNAI_ETA, "chennai-eta-2026-10-07.pdf"),
    ]
    def raw(value):
        return value.astimezone(IST).strftime("%d/%m/%Y %H:%M")
    expected = [record("expected", name, "190", "32", "9", "QA1", {"etaAt": raw(now-timedelta(minutes=5))}, now.date(), 0)
                for name in ("QA COMPLETE CALL", "QA AMBIGUOUS CALL", "QA CONFLICTING BERTH")]
    outcomes = [record("reported", name, "190", "32", "9", "QA1",
                       {"arrivalAt": raw(now-timedelta(minutes=4)), "berthAt": raw(now-timedelta(minutes=3))}, now.date(), 0)
                for name in ("QA COMPLETE CALL", "QA AMBIGUOUS CALL", "QA CONFLICTING BERTH")]
    conflicting = dict(outcomes[-1], berthRef="QA2")
    outcomes.append(conflicting)
    outcomes.append(record("reported", "QA AMBIGUOUS CALL", "190", "32", "9", "QA1",
                           {"arrivalAt": raw(now-timedelta(minutes=3)), "berthAt": raw(now-timedelta(minutes=2))}, now.date(), 0))
    for rows, kind, at, filename, url in [(expected, "expected", now-timedelta(minutes=7), samples[2][3], CHENNAI_ETA),
                                        (outcomes, "position", now-timedelta(minutes=1), samples[1][3], CHENNAI_POSITION)]:
        for i, row in enumerate(rows):
            row["recordId"] = "qa-synthetic-"+kind+str(i)
        parsed = {"records": rows, "reportDate": now.astimezone(IST).date().isoformat(), "issues": []}
        with patch("src.portwatch_os.intelligence.public_ports.parse_pdf", return_value=parsed):
            store.import_pdf("INMAA", kind, url, (root/filename).read_bytes()+b"\n% QA synthetic case fixture\n",
                             collected=at, actor="QA synthetic fixture only")
    for port, kind, url, filename in samples:
        store.import_pdf(port, kind, url, (root/filename).read_bytes(), collected=now, actor="QA layout sample")
    # A labelled, isolated failure verifies durable Operations diagnostics.
    from src.portwatch_os.intelligence.public_collection import collect_port
    with patch("src.portwatch_os.intelligence.public_ports.fetch", side_effect=OSError("QA collection failure fixture")):
        collect_port(store, "INPRT", "QA collection failure fixture only")
    store.close()
