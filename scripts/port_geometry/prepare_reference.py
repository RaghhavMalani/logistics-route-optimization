"""Rebuild a north-up reference display from retained native pixels or STAC COG.

Use --native-window for offline reproduction. Rasterio is an optional preparation
dependency; neither the browser nor the public API needs GDAL credentials.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main():
    import numpy as np
    from PIL import Image
    import rasterio
    from rasterio.warp import transform_bounds, reproject, Resampling
    from rasterio.windows import from_bounds
    from rasterio.transform import from_bounds as grid_transform
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--item',type=Path,required=True)
    parser.add_argument('--native-window',type=Path)
    parser.add_argument('--bounds',nargs=4,type=float,required=True)
    parser.add_argument('--size',nargs=2,type=int,default=[750,950])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--received',required=True)
    args=parser.parse_args()
    item=json.loads(args.item.read_text()); width,height=args.size
    if width<=0 or height<=0 or width*height>16000000: raise ValueError('Invalid display dimensions')
    out=args.output; out.mkdir(parents=True,exist_ok=True)
    (out/'stac-item.json').write_text(json.dumps(item,indent=2)+'\n')
    source=str(args.native_window) if args.native_window else item['assets']['visual']['href']
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif'):
        with rasterio.open(source) as src:
            if args.native_window:
                data=src.read([1,2,3]); transform=src.transform
                if args.native_window.resolve()!=(out/'original-window.tif').resolve(): shutil.copyfile(args.native_window,out/'original-window.tif')
            else:
                window=from_bounds(*transform_bounds('EPSG:4326',src.crs,*args.bounds),transform=src.transform).round_offsets().round_lengths()
                data=src.read([1,2,3],window=window); transform=src.window_transform(window)
                with rasterio.open(out/'original-window.tif','w',driver='GTiff',height=data.shape[1],width=data.shape[2],count=3,dtype=data.dtype,crs=src.crs,transform=transform,compress='deflate') as dst: dst.write(data)
            target=np.zeros((3,height,width),dtype=np.uint8)
            reproject(data,target,src_transform=transform,src_crs=src.crs,dst_transform=grid_transform(*args.bounds,width,height),dst_crs='EPSG:4326',resampling=Resampling.nearest)
            Image.fromarray(target.transpose(1,2,0)).save(out/'reference.png')
            receipt={'itemId':item['id'],'acquisitionAt':item['properties']['datetime'],'firstAvailableAt':args.received,
                'sourceAsset':item['assets']['visual']['href'],'sourceCrs':str(src.crs),'sourceResolutionM':list(src.res),
                'bounds':args.bounds,'width':width,'height':height,'resampling':'nearest','processingVersion':'port-reference-crop/1',
                'sourceSubsetSha256':hashlib.sha256((out/'original-window.tif').read_bytes()).hexdigest(),
                'displaySha256':hashlib.sha256((out/'reference.png').read_bytes()).hexdigest(),
                'originalMetadataSha256':hashlib.sha256((out/'stac-item.json').read_bytes()).hexdigest(),
                'originalScope':'Retained native pixel window; full remote COG is not retained.'}
            (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
            print(json.dumps(receipt,indent=2))


if __name__=='__main__': main()
