"""Generate the API-independent frontend geography from the canonical registry."""

import json
from pathlib import Path
import sys

frontend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(frontend.parent))
from src.utils.port_registry import PORTS

output = frontend / "src/components/miniature/ports.generated.json"
data = [
    {"code": port.locode, "name": port.name, "lat": port.lat, "lon": port.lon}
    for port in PORTS
]
serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
if "--check" in sys.argv:
    if output.read_text(encoding="utf-8") != serialized:
        raise SystemExit("Regenerate ports.generated.json with qa/sync-port-registry.py")
else:
    output.write_text(serialized, encoding="utf-8", newline="\n")
