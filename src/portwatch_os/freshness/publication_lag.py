"""Estimate daily IMF release lag from retained successful collection receipts."""
from datetime import datetime, timedelta, timezone
from statistics import median

IMF_CADENCE = timedelta(days=1)
HISTORY_WINDOW = timedelta(days=90)
# Isolated preview activity receipts, transcribed in the release evidence.
IMF_BASELINE = (
    ("2026-10-30T00:00:00Z", "2026-11-07T09:00:29Z"),
    ("2026-11-06T00:00:00Z", "2026-11-11T01:02:26Z"),
)


def imf_publication_lag(now, receipts):
    first_receipt = {}
    for observation, receipt in (*IMF_BASELINE, *receipts):
        observed_at = datetime.fromisoformat(observation).astimezone(timezone.utc)
        received_at = datetime.fromisoformat(receipt).astimezone(timezone.utc)
        if now - HISTORY_WINDOW <= observed_at <= received_at <= now:
            day = observed_at.replace(hour=0, minute=0, second=0, microsecond=0)
            first_receipt[day] = min(received_at, first_receipt.get(day, received_at))
    seconds = [(receipt - day).total_seconds() for day, receipt in first_receipt.items()]
    return {
        "basis": "first_successful_receipt",
        "samples": len(seconds),
        "medianSeconds": median(seconds) if len(seconds) >= 2 else None,
    }
