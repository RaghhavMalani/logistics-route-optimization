"""Refresh public weather/hazards without rebuilding lagging port activity."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd
from src.utils import port_registry
from src.portwatch_os.intelligence.current_environment import refresh, bundle, ROOT
from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.learning.weather_feedback import WeatherFeedback
from src.utils.config import PORT_ID, DATE


def collect(port):
    states = {kind: refresh(kind, port, force=True) for kind in ("surface", "marine")}
    return {"portCode": port.locode, **{kind: {k: v.get(k) for k in ("status", "snapshotId", "availableAt")}
                                       for kind, v in states.items()}}


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as workers:
        result = list(workers.map(collect, port_registry.PORTS))
    hazards = refresh("hazards", port_registry.resolve("INNSA"), force=True)
    ledger = SqliteLedgerStore(Path("work/capability-upgrades/learning-state/portwatch_ledger.db"))
    feedback = WeatherFeedback(ledger)
    for port in port_registry.PORTS:
        data = bundle(port, allow_fetch=False)
        frame = pd.DataFrame([{PORT_ID: port.model_id, DATE: r["date"], **r} for r in data["daily"]])
        if frame.empty: continue
        for kind, provider, variables in (("surface", "Open-Meteo surface", ("wind_speed", "wind_gust", "rainfall", "visibility")),
                                          ("marine", "Open-Meteo marine", ("wave_height",))):
            source = data["sources"][kind]
            if source["status"] == "CURRENT":
                feedback.record_frame(frame, issued_at=datetime.fromisoformat(source["availableAt"]),
                    provider=provider, source_state="CACHED_LIVE", variables=variables, now=datetime.now(timezone.utc))
    report = feedback.report(limit=10000, public_only=True)
    report["scope"] = "Public Open-Meteo forecast archive; origin is receipt availability because provider issue/observation times are unavailable. Outcomes remain unmatched until valid observations exist."
    (ROOT.parent/"public_weather_feedback.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    receipt = {"refreshedAt": datetime.now(timezone.utc).isoformat(), "ports": result,
               "hazards": {k: hazards.get(k) for k in ("status", "availableAt", "snapshotId")},
               "hazardCount": len(hazards["rows"]), "weatherForecasts": report["total"], "matchedOutcomes": report["resolved"]}
    target = Path("work/current-inputs-review/source-refresh.json"); target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(receipt,indent=2),encoding="utf-8")
    print(json.dumps(receipt,indent=2))
