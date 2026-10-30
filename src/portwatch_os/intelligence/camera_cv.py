"""Evaluated, fixed-viewpoint foreground occupancy from authorized local frames.

This is deliberately a bounded CV task, not vessel identity, calibrated queue
length or whole-port occupancy. A surveyed/operator ROI and an empty reference
frame are required. Threshold selection uses earlier reviewed frames; later
reviewed frames supply independent precision/recall. Candidates need review.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from src.portwatch_os.clock import world_now
import numpy as np
from PIL import Image
from src.portwatch_os.learning.weather_feedback import instant


def gray(path, roi):
    with Image.open(path) as image:
        if image.width < roi[2] or image.height < roi[3]:
            raise ValueError("ROI is outside frame geometry")
        return np.asarray(image.convert("L").crop(tuple(roi)),dtype=float)


def analyse(manifest_path: Path, *, now=None):
    query_at = instant(world_now() if now is None else now)
    manifest_path = manifest_path.resolve()
    spec = json.loads(manifest_path.read_text())
    if not spec.get("rightsBasis") or not spec.get("cameraId") or not spec.get("coverage"):
        raise ValueError("camera id, coverage and authorization basis are required")
    roi = spec["roi"]
    if len(roi)!=4 or min(roi)<0 or roi[2]<=roi[0] or roi[3]<=roi[1]:
        raise ValueError("ROI must be a valid rectangle")
    root = manifest_path.parent
    reference_path = (root/spec["emptyReference"]).resolve()
    reference = gray(reference_path,roi)
    reference_at = instant(spec["referenceAt"])
    frames = sorted(spec["frames"],key=lambda f:instant(f["observedAt"]))
    cutoff = instant(spec["validationFrom"])
    observations=[]
    for frame in frames:
        at = instant(frame["observedAt"])
        if not reference_at < at <= query_at:
            raise ValueError("frames must follow the empty reference and be in the past")
        path = (root/frame["path"]).resolve()
        pixels = gray(path,roi)
        if pixels.shape != reference.shape:
            raise ValueError("frame/ROI geometry changed")
        foreground = float((np.abs(pixels-reference)>spec.get("pixelThreshold",30)).mean())
        observations.append({"observedAt":at.isoformat(),"foregroundFraction":foreground,
            "truth":frame.get("berthOccupied"),"frameSha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    train=[o for o in observations if instant(o["observedAt"])<cutoff and o["truth"] is not None]
    test=[o for o in observations if instant(o["observedAt"])>=cutoff and o["truth"] is not None]
    if min(len(train),len(test))<8 or any(len({bool(o["truth"]) for o in group})<2 for group in (train,test)):
        raise ValueError("at least 8 reviewed frames and both occupancy classes required on each side of the chronological split")
    thresholds=np.linspace(.02,.75,50)
    threshold=min(thresholds,key=lambda t:sum((o["foregroundFraction"]>=t)!=bool(o["truth"]) for o in train))
    tp=sum(o["foregroundFraction"]>=threshold and o["truth"] for o in test)
    fp=sum(o["foregroundFraction"]>=threshold and not o["truth"] for o in test)
    fn=sum(o["foregroundFraction"]<threshold and o["truth"] for o in test)
    precision=tp/max(1,tp+fp); recall=tp/max(1,tp+fn)
    return {"version":"fixed-roi-foreground-v1","cameraId":spec["cameraId"],"coverage":spec["coverage"],"roi":roi,
        "rightsBasis":spec["rightsBasis"],"threshold":float(threshold),"trainingFrames":len(train),"testFrames":len(test),
        "precision":precision,"recall":recall,"falsePositives":int(fp),"falseNegatives":int(fn),
        "status":"CANDIDATE" if precision>=.9 and recall>=.9 else "REJECTED",
        "observations":[{**o,"occupied":o["foregroundFraction"]>=threshold,"operationalUse":"needs_review"} for o in observations],
        "referenceSha256":hashlib.sha256(reference_path.read_bytes()).hexdigest(),
        "manifestSha256":hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "limitations":"Foreground can be caused by shadows, rain or viewpoint changes. Fixed ROI only; no vessel identity, counts, or whole-port coverage claim."}


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument("manifest",type=Path); parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(); result=analyse(args.manifest)
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,indent=2))
    print(f'{result["status"]}: precision={result["precision"]:.3f}, recall={result["recall"]:.3f}; {result["testFrames"]} held-out frames')
