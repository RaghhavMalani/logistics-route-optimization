"""Correct evaluated metadata, retaining the exact earlier experiment bytes."""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from src.portwatch_os.twin.constrained_rl import MaskedQLearningPolicy, save_evaluated_policy
from src.utils.config import FORECASTS_DIR


def amend(directory=FORECASTS_DIR, archive=Path("work/current-inputs-review/rl-before-metadata-amendment")):
    paths = [directory/"constrained_rl.json", directory/"constrained_rl_report.json"]
    original = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    payload, report = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
    if payload.get("status") == report["status"] and payload.get("experimentId") and payload.get("experimentId") == report.get("experimentId"):
        if payload.get("evaluationReportSha256") == original["constrained_rl_report.json"]:
            return {"alreadyConsistent": True}
        # Preserve the first metadata amendment too, before repairing platform
        # newline translation. Never replace the original experiment backup.
        repair_archive = archive/"before-report-byte-hash-repair"
        repair_archive.mkdir(parents=True,exist_ok=True)
        for path in paths:
            target = repair_archive/path.name
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != original[path.name]:
                raise ValueError("The byte-hash repair archive already holds different evidence")
            shutil.copy2(path,target)
        report = save_evaluated_policy(directory,MaskedQLearningPolicy(payload["table"]),report)
        receipt = {"repairedAt":datetime.now(timezone.utc).isoformat(),"experimentId":report["experimentId"],
            "previousSha256":original,"archive":str(repair_archive),
            "reason":"Write and hash identical UTF-8 bytes across platforms; fitted values, scores and seeds unchanged."}
        (archive/"report-byte-hash-repair.json").write_text(json.dumps(receipt,indent=2),encoding="utf-8")
        return receipt
    archive.mkdir(parents=True, exist_ok=True)
    for path in paths:
        target = archive/path.name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != original[path.name]:
            raise ValueError("The preservation archive already holds different evidence")
        shutil.copy2(path, target)
    report = save_evaluated_policy(directory, MaskedQLearningPolicy(payload["table"]), report)
    receipt = {"amendedAt": datetime.now(timezone.utc).isoformat(), "experimentId": report["experimentId"],
               "originalSha256": original, "archive": str(archive),
               "reason": "Serialization status/identity correction only; no retraining, score, seed or fitted table changes."}
    (archive/"amendment.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    print(json.dumps(amend(), indent=2))
