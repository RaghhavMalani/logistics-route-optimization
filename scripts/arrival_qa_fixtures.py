"""Synthetic arrival inputs for isolated QA only; never imported by the production app."""
from datetime import timedelta
from unittest.mock import patch

import pandas as pd

from src.portwatch_os.fabric.ais.messages import AisObservation, POSITION_REPORT
from src.portwatch_os.intelligence.arrivals import ArrivalWorkflow, archive_track, stamp
from src.portwatch_os.learning.weather_feedback import WeatherFeedback


def tracks(ledger, at, mmsi="419000168"):
    for seconds in (120, 30):
        observed = at-timedelta(seconds=seconds)
        archive_track(ledger, AisObservation("QA synthetic AIS", POSITION_REPORT, mmsi, 18.94, 72.94,
            observed, observed+timedelta(seconds=1), sog_knots=2.0, nav_status="under way using engine",
            raw_ref=f"QA:{stamp(observed)}"), recorded_at=observed+timedelta(seconds=2))


def seed(ledger, now, count=60, *, prospective=False):
    service = ArrivalWorkflow(ledger)
    if prospective:
        service.start_collection("QA seed", now=now-timedelta(days=3*count+6))
    for i in range(count):
        issue = (now-timedelta(days=3*(count-i)+5)).replace(hour=10, minute=0, second=0, microsecond=0)
        planned = issue+timedelta(days=1)
        tracks(ledger, issue)
        wind = float(12 + i % 9)
        # The audit clock is historical only in this isolated synthetic fixture.
        with patch("src.portwatch_os.ledger.store.utc_now", return_value=stamp(issue-timedelta(minutes=1))):
            WeatherFeedback(ledger).record_frame(pd.DataFrame([{"port_id": "INNSA", "date": planned.date(), "wind_speed": wind}]),
                issued_at=issue-timedelta(minutes=2), provider="QA synthetic forecast", source_state="QA_FIXTURE", now=issue)
        case = service.create({"operationRef": f"QA-SYNTHETIC-{i}", "mmsi": "419000168", "vesselName": "QA SYNTHETIC VESSEL",
            "recipientOrganisation": "QA Shipping", "plannedArrivalAt": stamp(planned), "baselineWaitHours": 22.0,
            "baselineSource": "QA synthetic incumbent schedule", "routeRevision": "QA route v1",
            "baselineRef": f"QA-scheduler-{i}", "baselineEstimatedAt": stamp(issue-timedelta(minutes=5)),
            "baselineAvailableAt": stamp(issue-timedelta(minutes=4))}, "QA seed", now=issue)
        key = case["operationId"]
        service.approve(key, "QA seed", "Synthetic review", now=issue+timedelta(minutes=1))
        ledger.append_arrival_event(key, "advisory", "INNSA", "QA seed", {"advisoryId": f"QA-fixture-{i}"}, at=stamp(issue+timedelta(minutes=2)))
        service.action(key, "QA seed", {"actualAction": "QA synthetic arrival retained", "actionState": "taken",
            "source": "QA fixture only", "occurredAt": stamp(issue+timedelta(minutes=3)), "availableAt": stamp(issue+timedelta(minutes=3))},
            now=issue+timedelta(minutes=4))
        wait = 8.0 + wind/8 + (i % 3)*0.15
        berth = planned+timedelta(hours=wait)
        service.outcome(key, "QA seed", {"arrivedAt": stamp(planned), "berthedAt": stamp(berth), "availableAt": stamp(berth+timedelta(minutes=1)),
            "source": "QA synthetic outcome; not operational ground truth", "kind": "operator_confirmed", "berthRef": f"QA-{i}",
            "sourceRef": f"QA-outcome-{i}", "arrivalAvailableAt": stamp(planned+timedelta(minutes=1)),
            "allFastAvailableAt": stamp(berth+timedelta(minutes=1))},
            now=berth+timedelta(minutes=2))
    return service.evaluate("QA seed", now=now-timedelta(hours=1))
