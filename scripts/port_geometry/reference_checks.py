"""Retained-image registration inspection; no fitting or accuracy inflation.

The manually selected image pixels below were chosen on the dated reference
before querying nearest OSM vertices. Correspondence is a screening candidate,
not a surveyed control point. Report every selection, including mismatches.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.portwatch_os.geospatial.geometry import to_local, accuracy_report

PIXELS=[(20,585),(51,615),(55,542),(194,335),(215,318),(281,171),(292,179),(221,307),(118,404),(140,414)]


def run(release, output):
    catalogue=json.loads((release/'footprints.geojson').read_text())
    receipt=json.loads((release/'reference/receipt.json').read_text())
    west,south,east,north=receipt['bounds']; width,height=receipt['width'],receipt['height']
    def ll(x,y): return [west+(x+.5)/width*(east-west),north-(y+.5)/height*(north-south)]
    def pixel(p): return ((p[0]-west)/(east-west)*width-.5,(north-p[1])/(north-south)*height-.5)
    origin=catalogue['origin']
    candidates=[]
    for feature in catalogue['features']:
        if not feature['id'].startswith('osm-') or feature['properties']['kind']!='berth': continue
        points=feature['geometry']['coordinates'][0] if feature['geometry']['type']=='Polygon' else feature['geometry']['coordinates']
        for i,p in enumerate(points[:-1] if feature['geometry']['type']=='Polygon' else points):
            candidates.append((feature['id'],i,p,to_local(p,origin)[:2]))
    image=Image.open(release/'reference/reference.png').convert('RGB'); draw=ImageDraw.Draw(image)
    for feature in catalogue['features']:
        if feature['properties']['kind'] not in ('berth','coastline'): continue
        points=feature['geometry']['coordinates'][0] if feature['geometry']['type']=='Polygon' else feature['geometry']['coordinates']
        draw.line([pixel(p) for p in points],fill='#ff5f65' if feature['id'].startswith('jnpa-') else '#59d5ff',width=1)
    rows=[]
    for index,(x,y) in enumerate(PIXELS):
        ref=ll(x,y); en=to_local(ref,origin)[:2]
        match=min(candidates,key=lambda c:math.dist(c[3],en))
        row={'id':'image-screen-'+str(index+1),'role':'check','referenceSourceId':receipt['itemId'],
            'referencePixel':[x,y],'referenceLonLat':ref,'referenceEN':list(en),'featureId':match[0],
            'vertexIndex':match[1],'modelLonLat':match[2],'modelEN':list(match[3]),'discrepancyM':math.dist(match[3],en),
            'correspondenceStatus':'nearest-vertex screening candidate; independent expert review pending'}
        rows.append(row)
        mx,my=pixel(match[2]); draw.line((x,y,mx,my),fill='#ffe76b',width=1)
        draw.ellipse((x-3,y-3,x+3,y+3),outline='#ffe76b',width=2); draw.text((x+4,y),str(index+1),fill='#ffe76b')
    output.mkdir(parents=True,exist_ok=True)
    image.save(output/'registration-overlay.png')
    report={'schemaVersion':'port-geometry-reference-checks/1','portCode':'INNSA','geometryVersion':catalogue['geometryVersion'],
        'referenceSource':receipt['itemId'],'acquisitionAt':receipt['acquisitionAt'],'referenceNativeResolutionM':10,
        'registrationMethod':'Native georeferencing; zero fitted translations, rotations or scale changes',
        'calibrationPointCount':0,'screeningPointCount':len(rows),'independentlyVerifiedCorrespondenceCount':0,
        'pixelSelectionUncertaintyM':'At least one native pixel (~10 m), plus unpublished product geolocation uncertainty and correspondence uncertainty',
        'screeningDiscrepancies':accuracy_report(rows),'absoluteAccuracyStatus':'unverified',
        'provisionalGoal':{'medianM':5,'p95M':10,'supportedByReference':False},
        'heightErrorM':None,'unverifiedCoverage':'All absolute positions, heights and asset identity correspondences remain unverified.',
        'limitations':['Nearest-vertex matching is a screening procedure, not independent surveyed validation.',
            'Reference pixel selections may include quay edges, shadows or nearby vessels at this resolution.',
            'Report all points without cherry-picking. Do not call these discrepancies absolute positional errors.',
            'A March 2026 image cannot establish current occupancy or distinguish every later construction change.'],
        'checks':rows,'referenceDisplaySha256':receipt['displaySha256']}
    (output/'reference-checks.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report['screeningDiscrepancies'],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--release',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); run(args.release,args.output)
