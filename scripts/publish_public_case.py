"""Package one reviewed public study and official originals; no collection/evaluation."""
import argparse
import json
from pathlib import Path

from backend.app.services.public_cases import public_calls
from src.portwatch_os.clock import wall_now
from src.portwatch_os.intelligence.public_collection import get_service
from src.portwatch_os.intelligence.public_ports import digest, stamp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id")
    args = parser.parse_args()
    case = next((c for c in public_calls()["cases"] if c["caseId"] == args.case_id), None)
    if not case or case.get("archivedPublication"):
        raise ValueError("A current visually reviewed public case is required")
    now = stamp(wall_now())  # wall-clock: actual public packaging time, never evidence collection time.
    documents = list({e["sha256"]:{k:e[k] for k in ("sha256","sourceUrl","firstSeenAt")} for e in case["events"]}.values())
    body = json.dumps({"schemaVersion":"public-case-v1", "publishedAt":now, "cases":[case], "documents":documents}, indent=2).encode()
    sha = digest(body)
    root = Path(__file__).resolve().parents[1]/"data/public_port_cases"
    folder = root/("case-publication-"+sha[:16])
    (folder/"evidence").mkdir(parents=True, exist_ok=True)
    for d in documents:
        payload = (get_service().root/"evidence"/(d["sha256"]+".pdf")).read_bytes()
        assert digest(payload) == d["sha256"]
        (folder/"evidence"/(d["sha256"]+".pdf")).write_bytes(payload)
    (folder/"publication.json").write_bytes(body)
    (root/"current.json").write_text(json.dumps({"publicationId":folder.name,"sha256":sha}, indent=2), encoding="utf-8")
    print(json.dumps({"publicationId":folder.name,"publishedAt":now,"vessel":case["vesselName"],"officialPdfs":len(documents)}))


if __name__ == "__main__":
    main()
