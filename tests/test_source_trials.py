from datetime import datetime, timedelta, timezone

import pytest

from scripts.verify_live_ais import coastal_coverage
from src.portwatch_os.fabric.ais.messages import AisObservation
from src.portwatch_os.freshness import trial_collectors as trial

NOW = datetime(2026, 11, 4, 15, tzinfo=timezone.utc)


def test_ecb_requires_both_reference_rates_and_keeps_older_reference_date(monkeypatch):
    rates = [
        {"base": "EUR", "quote": "INR", "date": "2026-11-04", "rate": 104},
        {"base": "EUR", "quote": "USD", "date": "2026-11-03", "rate": 1.15},
    ]

    def fetch(url, params):
        assert url.endswith("/providers/ecb/rates")
        assert params == {"base": "EUR", "quotes": "INR,USD"}
        return rates

    monkeypatch.setattr(trial, "fetch_json", fetch)
    url = "https://api.frankfurter.dev/v2/providers/ecb/rates"
    sample = trial.ecb_rates(url)
    assert sample.payload["rates"] == rates
    assert sample.payload["precision"] == "DATE_ONLY"
    assert sample.observed_at == datetime(2026, 11, 3, tzinfo=timezone.utc)
    rates.pop()
    with pytest.raises(ValueError, match="both EUR"):
        trial.ecb_rates(url)


def test_gdelt_trial_uses_small_window_and_retains_only_qualified_links(monkeypatch):
    def fetch(url, params):
        assert params["timespan"] == "24h" and params["maxrecords"] == 30
        return {"articles": [
            {"url": "https://example.org/a", "seendate": "20261104T140000Z", "title": "Third-party headline"},
            {"url": "https://example.org/a", "seendate": "20261104T140000Z"},
            {"url": "https://example.org/future", "seendate": "20261105T140000Z"},
            {"url": "javascript:noop", "seendate": "20261104T140000Z"},
        ]}

    monkeypatch.setattr(trial, "fetch_json", fetch)
    monkeypatch.setattr(trial, "wall_now", lambda: NOW)
    sample = trial.gdelt_discovery()
    assert sample.observed_at == NOW - timedelta(hours=1)
    assert sample.payload["coverage"] == {"https://example.org/a": "2026-11-04T14:00:00+00:00"}
    assert "Third-party headline" not in str(sample.payload)


def test_coastal_acceptance_counts_unique_position_reports_and_ignores_unknown_lag():
    reports = [
        AisObservation("aisstream", kind, mmsi, lat, lon, NOW - timedelta(seconds=lag), NOW,
                       provenance={"source_time_known": known})
        for kind, mmsi, lat, lon, lag, known in (
            ("PositionReport", "419000001", 18.9, 72.8, 10, True),
            ("PositionReport", "419000001", 18.9, 72.8, 30, True),
            ("ShipStaticData", "419000002", 18.9, 72.8, 30, True),
            ("PositionReport", "419000003", 20.3, 86.7, 0, False),
        )
    ]
    coverage = coastal_coverage(reports, [NOW] * len(reports))
    assert coverage["JNPA"] == {"hulls": 1, "reports": 2, "medianLagSeconds": 20}
    assert coverage["Paradip"] == {"hulls": 0, "reports": 0, "medianLagSeconds": None}
