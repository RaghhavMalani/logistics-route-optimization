"""Teammate-side example: use the geometry API to export one dated GEE display.

Requires the teammate's authorized earthengine-api environment. Does not run in
the PortWatch frontend or expose service credentials. Publish the two generated
display files on an approved HTTPS host; configure the layer catalogue pull URL.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.request import urlopen


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--geometry-api',required=True,help='Full public manifest URL, including /api/public/port-geometry/INNSA')
    p.add_argument('--project',required=True,help='Your authorized GEE project')
    p.add_argument('--from-date',required=True)
    p.add_argument('--through-date',required=True,help='Exclusive collection end date')
    p.add_argument('--display-url',required=True,help='HTTPS URL where you will publish display.png')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    import ee
    ee.Initialize(project=args.project)
    with urlopen(args.geometry_api,timeout=30) as response: manifest=json.load(response)
    if manifest.get('schemaVersion')!='port-twin-geospatial-api/1' or manifest.get('horizontalCrs')!='EPSG:4326': raise ValueError('Unsupported geometry API')
    bounds=manifest['bounds']; west,south,east,north=bounds
    region=ee.Geometry.Rectangle(bounds,proj='EPSG:4326',geodesic=False)
    collection=(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(region)
        .filterDate(args.from_date,args.through_date).filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE',20)).sort('CLOUDY_PIXEL_PERCENTAGE'))
    if collection.size().getInfo()==0: raise ValueError('No suitable image; do not substitute fabricated imagery')
    image=ee.Image(collection.first())
    source_id=image.get('system:id').getInfo()
    acquired=datetime.fromtimestamp(image.get('system:time_start').getInfo()/1000,timezone.utc).isoformat()
    native_resolution=image.select('B4').projection().nominalScale().getInfo()
    width=max(1,round((east-west)*111320*math.cos(math.radians((south+north)/2))/native_resolution))
    height=max(1,round((north-south)*111320/native_resolution))
    rendered=image.visualize(bands=['B4','B3','B2'],min=0,max=3000)
    temporary_url=rendered.getThumbURL({'region':region,'dimensions':f'{width}x{height}','crs':'EPSG:4326','format':'png'})
    # Retain the bytes instead of shipping an expiring GEE URL with unknown TTL.
    with urlopen(temporary_url,timeout=120) as response: png=response.read()
    if not png.startswith(b'\x89PNG'): raise ValueError('Expected a PNG display export')
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'display.png').write_bytes(png)
    receipt={'sourceProduct':source_id,'acquisitionAt':acquired,'bounds':bounds,'horizontalCrs':'EPSG:4326',
        'nativeResolutionM':native_resolution,'processingVersion':'gee-s2-rgb/1','bands':['B4','B3','B2'],'displayStretch':[0,3000],
        'firstAvailableAt':datetime.now(timezone.utc).isoformat(),'displaySha256':hashlib.sha256(png).hexdigest(),
        'originalScope':'Provider image identity and display export retained; analytical source pixels are not retained.'}
    raw=(json.dumps(receipt,indent=2)+'\n').encode(); (args.output/'source-receipt.json').write_bytes(raw)
    descriptor={'schemaVersion':'geospatial-layer/1','layerId':manifest['portCode'].lower()+'-gee-'+acquired[:10],
        'portCode':manifest['portCode'],'kind':'raster','bounds':bounds,'horizontalCrs':'EPSG:4326','verticalDatum':None,
        'acquisitionFrom':acquired,'acquisitionThrough':acquired,'firstAvailableAt':receipt['firstAvailableAt'],
        'nativeResolutionM':native_resolution,'resamplingMethod':'GEE visualization/export default; no accuracy gain claimed',
        'noDataDefinition':'No data/clouds are not negative operational observations','sourceProduct':source_id,'processingVersion':'gee-s2-rgb/1',
        'sourceHashes':[hashlib.sha256(raw).hexdigest(),hashlib.sha256(png).hexdigest()],
        'attribution':'Contains modified Copernicus Sentinel data; processed in Google Earth Engine','quality':'Imagery-derived',
        'displayResource':{'url':args.display_url,'valueKind':'display','format':'image/png','expiresAt':None},
        'analyticalResource':None,'assetIds':[]}
    (args.output/'layers.json').write_text(json.dumps({'schemaVersion':'geospatial-layer-catalogue/1','portCode':manifest['portCode'],'layers':[descriptor]},indent=2)+'\n')
    print('Publish display.png and layers.json on your approved host; validate the descriptor at',manifest['validateLayerUrl'])


if __name__=='__main__': main()
