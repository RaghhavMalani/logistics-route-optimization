"""Publish only the public weather subset from the separate collection run."""
import json
from pathlib import Path
from src.portwatch_os.ledger.store import SqliteLedgerStore
from src.portwatch_os.learning.weather_feedback import WeatherFeedback
from backend.app.services.cache_service import CACHE_DIR

root=Path(__file__).resolve().parents[1]
ledger=SqliteLedgerStore(root/"work/capability-upgrades/learning-state/portwatch_ledger.db")
report=WeatherFeedback(ledger).report(limit=6000,public_only=True)
report["scope"]="Public Open-Meteo forecast archive and explicitly labelled ERA5 reanalysis"
target=CACHE_DIR/"public_weather_feedback.json"
tmp=target.with_suffix(".json.tmp"); tmp.write_text(json.dumps(report,indent=2)); tmp.replace(target)
print(f'Published {report["total"]} public forecasts; {report["resolved"]} matched outcomes')
