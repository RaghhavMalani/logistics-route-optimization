"""Bounded public research products, retained independently of visitor worlds.

Only the explicit collector writes or fetches. DTOs below are an allowlist;
private fleet, financial, camera and session stores are never consulted.
"""
from __future__ import annotations

from src.utils.settings import get_settings

import csv
import hashlib
import io
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import requests

from src.portwatch_os.clock import LIVE, get_clock, wall_now, world_now
from src.utils.config import STATE_DIR
from src.portwatch_os.intelligence.data_truth import DataTruth

ROOT = Path(get_settings().PORTWATCH_FREE_SOURCE_DIR or STATE_DIR / "public_products")
LOCK = threading.RLock()
# Intervals govern checks, not a promise that the publisher has new data.
PRODUCTS = {
    "jwc": dict(provider="LMA / Joint War Committee", product="JWLA-035 · 16 September 2026", origin="OFFICIAL_REPORT", cadence=7*86400,
        maxAge=None,url="https://lmalloyds.com/wp-content/uploads/2026/09/JWLA-035-Black-Sea.pdf",
        unit="dated geographical notice",geography="Published listed areas",limit="Dated hull war/piracy context. Individual contracts require negotiation; no closure, premium or coverage decision. Geometry remains unqualified."),
    "usgs": dict(provider="USGS", product="All-day earthquakes", origin="REPORTED_EVENT", cadence=300,
        maxAge=86400, url="https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson",
        unit="event", geography="Global", limit="Reported seismic context; no damage, closure or delay inferred."),
    "gdelt": dict(provider="GDELT", product="Maritime discovery", origin="REPORTED_EVENT", cadence=10800,
        maxAge=14*86400, url="https://api.gdeltproject.org/api/v2/doc/doc",
        unit="discovery record", geography="Named maritime topics", limit="Source-linked discovery, not verified disruption. Publisher rights apply."),
    "fred_fx": dict(provider="FRED", product="DEXINUS", origin="OFFICIAL_REPORT", cadence=86400,
        maxAge=7*86400, url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXINUS",
        unit="INR/USD", geography="USD / INR reference series", limit="Dated reference observations; not an executable quote or an ECB cross-rate."),
    "fred_brent": dict(provider="FRED", product="DCOILBRENTEU", origin="OFFICIAL_REPORT", cadence=86400,
        maxAge=7*86400, url="https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU",
        unit="USD/bbl", geography="Brent reference", limit="Reference oil series, not a delivered vessel bunker quote."),
    "imf": dict(provider="IMF PortWatch", product="Daily port activity · Paradip", origin="DERIVED_METRIC", cadence=86400,
        maxAge=7*86400, url="https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/Daily_Ports_Data/FeatureServer/0/query",
        unit="calls / tonnes", geography="Paradip (port883)", limit="Provider aggregate activity; not an individual vessel wait or berth observation."),
    "trade": dict(provider="UN Comtrade", product="Annual India imports · HS 1006 rice", origin="OFFICIAL_REPORT", cadence=7*86400,
        maxAge=None, url="https://comtradeapi.un.org/public/v1/preview/C/A/HS",
        unit="USD trade value / kg when reported", geography="India · world partner · annual", limit="Limited no-key preview. Country trade context does not identify buyers, port demand or invoice prices."),
}


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None: raise ValueError("An aware instant is required")
    return result.astimezone(timezone.utc)


def _load(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return None


def _atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def _request(key):
    if key == "gdelt":
        # Same bounded topic family as the existing events connector; no severity-to-delay conversion.
        from src.ingestion.connectors.events import GDELT_DOC
        return GDELT_DOC, dict(query='("Indian port" OR "Suez Canal" OR "Strait of Hormuz" OR "Malacca") sourcelang:eng',
            mode="artlist", maxrecords=40, format="json", timespan="14d", sort="datedesc")
    if key == "imf":
        return PRODUCTS[key]["url"], dict(where="portid='port883'", outFields="*", orderByFields="year DESC,month DESC,day DESC", returnGeometry="false", resultRecordCount=14, f="json")
    if key == "trade":
        # Last complete calendar year, not a claim that this year has been published.
        return PRODUCTS[key]["url"], dict(period=world_now().year-1, reporterCode=699, cmdCode="1006", flowCode="M", partnerCode=0, maxRecords=12)
    return PRODUCTS[key]["url"], {}


def _parse(key, content):
    if key=='jwc':
        if not content.startswith(b'%PDF'): raise ValueError('Expected original JWC PDF')
        from pypdf import PdfReader
        text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(content)).pages)
        if 'JWLA-035' not in text or 'September 2026' not in text or 'Listed Areas' not in text: raise ValueError('Dated document identity changed; manual review required')
        return [dict(circular='JWLA-035',documentDate='2026-09-16',datePrecision='DATE_ONLY',publishedAt=None,
            areas=['Persian/Arabian Gulf','Gulf of Oman','Indian Ocean','Gulf of Aden','Southern Red Sea','Other areas: inspect original'],
            geometryStatus='REQUIRES_BOUNDARY_REVIEW',applicability='Hull war, piracy, terrorism and related perils; contract-specific negotiation',
            calculationBoundary='Notification/review context only; no probability, premium, closure or payable recovery')]
    if key.startswith("fred_"):
        sid=PRODUCTS[key]["product"]
        rows=[]
        for row in csv.DictReader(io.StringIO(content.decode("utf-8-sig"))):
            day=row.get("observation_date") or row.get("DATE")
            value=row.get(sid)
            if not day or value in (None,".",""): continue
            datetime.strptime(day,"%Y-%m-%d")
            number=float(value)
            if not __import__('math').isfinite(number): raise ValueError("Nonfinite quote")
            rows.append(dict(date=day, value=number, unit=PRODUCTS[key]["unit"]))
        if not rows: raise ValueError("No qualified reference observations")
        return sorted(rows,key=lambda r:r['date'])[-30:]
    data=json.loads(content)
    if key=="usgs":
        if data.get("type")!="FeatureCollection" or not isinstance(data.get("features"),list): raise ValueError("Invalid USGS product")
        return [{"id":f.get("id"),"title":f['properties'].get('title'),"time":f['properties'].get('time'),
            "updated":f['properties'].get('updated'),"url":f['properties'].get('url'),"place":f['properties'].get('place'),"geometry":f.get('geometry'),
            "magnitude":f['properties'].get('mag')} for f in data['features']][:2000]
    if key=="gdelt":
        if not isinstance(data.get('articles'),list): raise ValueError("No qualified discovery response")
        rows={}
        for a in data['articles']:
            if not a.get('url') or not a.get('title'): continue
            # Document dedup only; existing feedback machinery owns independent event verification.
            rows.setdefault(a['url'],{k:a.get(k) for k in ('url','title','seendate','domain','language','sourcecountry')})
        return list(rows.values())[:40]
    if key=="imf":
        if data.get('error') or not isinstance(data.get('features'),list): raise ValueError("Invalid IMF product")
        rows=[f['attributes'] for f in data['features'] if f.get('attributes',{}).get('portid')=='port883']
        if not rows: raise ValueError("No supported Paradip aggregate rows")
        # Explicit public aggregate allowlist, no new model export or unrelated CSV write.
        return [{k:r.get(k) for k in ('portid','date','portcalls','import','export','portcalls_container','portcalls_tanker','portcalls_dry_bulk')} for r in rows]
    if key=="trade":
        if data.get('error') or not isinstance(data.get('data'),list) or not data['data']: raise ValueError("No qualified annual trade rows")
        fields=('period','reporterCode','reporterDesc','partnerCode','partnerDesc','cmdCode','cmdDesc','flowCode','flowDesc','primaryValue','netWgt','qty','qtyUnitAbbr','isReported','classificationCode')
        return [{k:r.get(k) for k in fields} for r in data['data'] if str(r.get('cmdCode'))=='1006' and r.get('partnerCode')==0][:12]
    raise ValueError("Unsupported product")


def collect(key):
    """One fixed-product attempt; failures do not renew last-good evidence."""
    if key not in PRODUCTS: raise ValueError("Unknown public product")
    if get_clock().state.mode != LIVE: raise ValueError("Collection is paused outside the live clock")
    with LOCK:
        # wall-clock: actual request receipt and check time; never provider publication.
        started=wall_now()
        previous=_load(ROOT/f'{key}.json')
        response=None
        try:
            url,params=_request(key)
            response=requests.get(url,params=params,headers={'User-Agent':'PortWatch noncommercial academic research/1.0'},timeout=(4,18))
            response.raise_for_status()
            if len(response.content)>12_000_000: raise ValueError("Response exceeds bounded archive size")
            rows=_parse(key,response.content)
            # wall-clock: the actual successful backend response became available now.
            received=wall_now()
            sha=hashlib.sha256(response.content).hexdigest()
            original=ROOT/'archive'/f'{key}-{sha}.json'
            retained=_load(original)
            snapshot=retained or dict(productId=key,sha256=sha,firstAvailableAt=received.isoformat(),rows=rows,
                request=dict(url=url,params=params),publishedAt=None,timePrecision="DATE_ONLY" if key.startswith('fred_') or key=='trade' else "PROVIDER_FIELDS")
            if not retained:
                _atomic(original,snapshot)
                original.with_suffix('.response').write_bytes(response.content)
            _atomic(ROOT/f'{key}.json',{**snapshot,'lastSuccessfulCheckAt':received.isoformat(),'lastAttemptAt':started.isoformat(),'error':None})
            return dict(productId=key,ok=True,sha256=sha,rows=len(rows),firstAvailableAt=snapshot['firstAvailableAt'],lastSuccessfulCheckAt=received.isoformat())
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            if response is not None and len(response.content)<=12_000_000:
                rejected=ROOT/'unqualified';rejected.mkdir(parents=True,exist_ok=True)
                rejected_sha=hashlib.sha256(response.content).hexdigest()
                (rejected/f'{key}-{rejected_sha}.response').write_bytes(response.content)
            # Error text is deliberately bounded and contains neither request headers nor secret URLs.
            _atomic(ROOT/f'{key}.json',{**(previous or {}),'lastAttemptAt':started.isoformat(),'error':type(exc).__name__})
            return dict(productId=key,ok=False,error=type(exc).__name__)


def public_product(key,at=None):
    """Reviewed public DTO, retained-state read only. No raw path/header/private store."""
    at=at or world_now(); spec=PRODUCTS[key]; latest=_load(ROOT/f'{key}.json') or {}
    # Replay cannot use a latest response whose first availability is later.
    if latest.get('firstAvailableAt') and instant(latest['firstAvailableAt'])>at: latest={}
    rows=latest.get('rows',[])
    age=None
    if key.startswith('fred_') and rows: age=(at-instant(rows[-1]['date']+'T00:00:00Z')).total_seconds()
    elif key=='imf' and rows:
        value=rows[0].get('date')
        if isinstance(value,(int,float)): age=at.timestamp()-value/1000
        elif isinstance(value,str):
            try: age=(at-instant(value[:10]+'T00:00:00Z')).total_seconds()
            except ValueError: pass
    elif key=='usgs' and rows: age=at.timestamp()-max(r.get('time',0) or 0 for r in rows)/1000
    elif key=='gdelt' and rows:
        dates=[]
        for r in rows:
            try: dates.append(datetime.strptime(r['seendate'],'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc))
            except (KeyError,TypeError,ValueError): pass
        age=(at-max(dates)).total_seconds() if dates else None
    elif latest.get('firstAvailableAt'): age=(at-instant(latest['firstAvailableAt'])).total_seconds()
    check=latest.get('lastSuccessfulCheckAt')
    check_age=(at-instant(check)).total_seconds() if check else None
    status='UNAVAILABLE' if not rows else 'HISTORICAL' if spec['maxAge'] is None else 'STALE' if latest.get('error') or age is None or age>spec['maxAge'] or check_age is None or check_age>spec['cadence']*2 else 'CURRENT'
    return DataTruth.model_validate(dict(productId=key,provider=spec['provider'],product=spec['product'],origin=spec['origin'],freshness=status,
        execution='REPORTED_CONTEXT',unit=spec['unit'],geography=spec['geography'],source=spec['url'],limit=spec['limit'],
        firstAvailableAt=latest.get('firstAvailableAt'),publishedAt=latest.get('publishedAt'),timePrecision=latest.get('timePrecision'),
        lastSuccessfulCheckAt=check,lastAttemptAt=latest.get('lastAttemptAt'),error=latest.get('error'),sha256=latest.get('sha256'),
        policy=dict(id='free-research-products-v1',checkCadenceSeconds=spec['cadence'],maxSourceAgeSeconds=spec['maxAge']),
        coverage=dict(retainedRows=len(rows),scope=spec['geography']),rows=rows)).model_dump(mode='json')


def catalogue():
    rows=[public_product(key) for key in PRODUCTS]
    return dict(version='public-product-dto-v1',asOf=world_now().isoformat(),products=rows,
        counts={state:sum(p['freshness']==state for p in rows) for state in ('CURRENT','STALE','HISTORICAL','UNAVAILABLE')},
        denominator=len(rows),scope='Configured public research products; not private fleet coverage or operational readiness')
