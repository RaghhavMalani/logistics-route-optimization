"""Reproduce dimension screening against retained JNPA 2022 plan values.

Values below were visually reviewed on page 102/Table 13. A polygon maximum
chord is explicitly not equated with a surveyed quay-face length.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.portwatch_os.geospatial.geometry import to_local

PLAN_SHA256='be43a656a9806c0658d281b348cd890b589ebda380e5785b1a2d7b4d2003948f'
PLAN_URL='https://www.jnport.gov.in/uploads/content_manager/Report_on_land_Use_Plan_for_JNPA___August_2022__23_2022_10_06_17_04_09.pdf'
PUBLISHED={15:('JNPCT / later NSFPT name requires identity review',680),16:('NSICT',600),12:('NSIGT',330),22:('GTIPL / APM',712)}


def run(release,plan,output):
    digest=hashlib.sha256(plan.read_bytes()).hexdigest()
    if digest!=PLAN_SHA256: raise ValueError('Authority plan changed; retain a new receipt and re-review dimensions')
    catalogue=json.loads((release/'footprints.geojson').read_text()); rows=[]
    for fid,(name,expected) in PUBLISHED.items():
        feature=next(f for f in catalogue['features'] if f['id']==f'jnpa-berth-{fid}')
        points=[to_local(p,catalogue['origin'])[:2] for p in feature['geometry']['coordinates'][0][:-1]]
        a,b=max(((a,b) for a in points for b in points),key=lambda pair:math.dist(*pair))
        length=math.dist(a,b)
        rows.append({'featureId':feature['id'],'name':name,'published2022LengthM':expected,
            'gisLengthAttributeM':feature['properties'].get('publishedLengthM'),'polygonMaximumChordM':length,
            'chordMinusPublishedM':length-expected,'axisBearingDegreesFromNorthModulo180':math.degrees(math.atan2(b[0]-a[0],b[1]-a[1]))%180,
            'publishedOrientationDegrees':None,'orientationDifferenceDegrees':None,
            'interpretation':'Screening only: berth/water polygon maximum chord is not necessarily quay-face length. Epoch and identity may differ.'})
    try: retained=str(plan.resolve().relative_to(ROOT))
    except ValueError: retained=str(plan.resolve())
    report={'schemaVersion':'port-dimension-comparison/1','authorityPlanUrl':PLAN_URL,'authorityPlanSha256':digest,
        'publicationLabel':'August 2022','firstAvailableAt':'2026-10-19','pagesReviewed':[27,102],'table':'Table 13',
        'retainedOriginal':retained,'redistributionPermission':'Not established; full PDF retained in ignored local work directory, not included in the public release.',
        'comparisons':rows,'verticalAccuracyM':None,'positionalAccuracyM':None}
    output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release',type=Path,required=True); parser.add_argument('--plan',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); run(args.release,args.plan,args.output)
