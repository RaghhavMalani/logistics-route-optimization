"""Isolated, real API/database QA server. Public fixture credentials never enter production state."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    qa_root = root/"work"/"verified-qa"
    qa_root.mkdir(parents=True, exist_ok=True)
    state = Path(tempfile.mkdtemp(prefix="run-", dir=qa_root))
    os.environ["PORTWATCH_STATE_DIR"] = str(state)
    os.environ["PORTWATCH_AUTH_DB"] = str(state/"identity.db")
    os.environ["PORTWATCH_IDENTITY_MODE"] = "verified"
    os.environ["PORTWATCH_FRESHNESS_SCHEDULER"] = "0"
    os.environ.pop("AISSTREAM_API_KEY", None)
    from datetime import timedelta
    import pandas as pd
    import uvicorn
    from backend.app.auth_store import AuthStore
    from src.portwatch_os.clock import world_now
    from src.portwatch_os.learning.weather_feedback import WeatherFeedback
    from src.portwatch_os.ledger.store import get_ledger
    from src.utils import port_registry

    store = AuthStore(state/"identity.db")
    for name, role, ports in (("admin", "NATIONAL_ADMIN", ()), ("port", "PORT_AUTHORITY", ("INNSA",)),
                              ("other", "PORT_AUTHORITY", ("INMAA",)), ("paradip", "PORT_AUTHORITY", ("INPRT",)), ("company", "SHIPPING_COMPANY", ())):
        store.provision(f"{name}@qa.invalid", "qa-only-verified-password", role=role, display_name=f"QA {name}",
                        ports=ports, organisation="QA Shipping" if name == "company" else "QA Authority")
    issue = world_now()-timedelta(minutes=5)
    start = issue.replace(hour=0, minute=0, second=0, microsecond=0)
    frame = pd.DataFrame([{"port_id": p.locode, "date": (start+timedelta(days=d)).date().isoformat(), "wind_speed": 17.0}
                          for p in port_registry.all_ports() for d in range(1,6)])
    feedback = WeatherFeedback(get_ledger())
    feedback.record_frame(frame, issued_at=issue, provider="QA wind fixture", source_state="LIVE", now=issue)
    feedback.record_frame(frame.drop(columns="wind_speed").assign(wave_height=2.0), issued_at=issue+timedelta(minutes=1),
                          provider="QA wave fixture", source_state="LIVE", now=issue+timedelta(minutes=1))
    old_issue = start-timedelta(days=3)
    feedback.record_frame(pd.DataFrame([{"port_id": "INNSA", "date": (start-timedelta(days=1)).date().isoformat(), "wind_gust": 20.0}]),
                          issued_at=old_issue, provider="QA matured gust fixture", source_state="LIVE", now=old_issue)
    if os.getenv("PW_QA_ARRIVALS") == "1":
        from scripts.arrival_qa_fixtures import seed, tracks
        seed(get_ledger(), world_now())
        tracks(get_ledger(), world_now())
    if os.getenv("PW_QA_PUBLIC_ARRIVALS") == "1":
        from scripts.public_port_qa_fixtures import seed as seed_public
        seed_public(state)
    print(f"Isolated QA state: {state}; forecasts and accounts are test inputs, not operational observations", flush=True)
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=int(os.getenv("PW_QA_API_PORT") or "9281"))


if __name__ == "__main__":
    main()
