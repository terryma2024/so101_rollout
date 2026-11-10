"""Offline inspection of retained YUYV; no camera access or production transforms."""
from pathlib import Path
import csv
import json
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent
TRIAL=ROOT.parent

def main():
    manifest=json.loads((TRIAL/'manifest.json').read_text())
    meta=[json.loads(l) for l in (TRIAL/'wrist/frames.jsonl').read_text().splitlines()]
    rois=json.loads((TRIAL/'roi.json').read_text())['wrist']
    keys=['cube_red','cube_green']+[f'chart_r{i}_c0' for i in range(6)]+['paper']
    indices={}
    for key in keys:
        mask=np.zeros((480,640),np.uint8)
        cv2.fillConvexPoly(mask,np.array(rois[key]['polygon'],np.int32),1)
        indices[key]=np.where(mask)
    output={};csv_rows=[];mismatches=0;checked=0
    with (TRIAL/'wrist/stream.bin').open('rb') as f:
        for c in manifest['conditions']:
            selected=[r for r in meta if c['start']<=r['host_monotonic']<c['end']]
            tracks={key:[] for key in keys}
            for row in selected:
                f.seek(row['offset']);raw=np.frombuffer(f.read(row['bytes']),np.uint8).reshape(480,640,2)
                reference=cv2.cvtColor(raw,cv2.COLOR_YUV2RGB_YUY2)
                for key,(iy,ix) in indices.items():
                    y=raw[iy,ix,0].astype(np.int64)
                    u=raw[iy,(ix//2)*2,1].astype(np.int64)-128
                    v=raw[iy,(ix//2)*2+1,1].astype(np.int64)-128
                    yy=np.maximum(y-16,0)*1220542
                    rgb=np.stack([(yy+1673527*v+(1<<19))>>20,
                                  (yy-852492*v-409993*u+(1<<19))>>20,
                                  (yy+2116026*u+(1<<19))>>20],axis=-1)
                    expected=np.clip(rgb,0,255).astype(np.uint8)
                    mismatches+=int((expected!=reference[iy,ix]).sum());checked+=expected.size
                    tracks[key].append(dict(y_median=float(np.median(y)),y_eq16=float((y==16).mean()),
                        y_le16=float((y<=16).mean()),y_eq232=float((y==232).mean()),
                        pre_saturation_median_rgb=np.median(rgb,0).tolist(),
                        pre_saturation_negative_fraction_rgb=(rgb<0).mean(0).tolist()))
            output[c['name']]={'frames':len(selected),'rois':{}}
            for key,series in tracks.items():
                record={}
                for metric in series[0]:
                    values=np.array([r[metric] for r in series])
                    record[metric]=np.median(values,axis=0).tolist() if 'median' in metric else values.mean(0).tolist()
                output[c['name']]['rois'][key]=record
                csv_rows.append(dict(condition=c['name'],roi=key,y_median=record['y_median'],
                    y_eq16_fraction=record['y_eq16'],y_eq232_fraction=record['y_eq232']))
    output['validation']={'reference':'OpenCV 4.13.0 integer BT.601 packed-YUYV path; source coefficients and rounding.',
        'tested_channel_samples':checked,'mismatched_channel_samples':mismatches,
        'source':'https://github.com/opencv/opencv/blob/4.13.0/modules/imgproc/src/color_yuv.simd.hpp',
        'metadata':'Device declared YUYV/BT.601/limited range. No independent proof of device colorimetry accuracy.'}
    if mismatches:raise RuntimeError('Integer reference does not match installed OpenCV')
    (ROOT/'yuyv-diagnostics.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
    with (ROOT/'gray-y-codes.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(csv_rows[0]));writer.writeheader();writer.writerows(csv_rows)
    print(json.dumps(output['validation'],indent=2))
    for c in manifest['conditions']:
        cn=c['name'];print(cn)
        for key in keys:
            r=output[cn]['rois'][key]
            print(key,'Y',r['y_median'],'Y=16%',round(r['y_eq16']*100,2),'Y=232%',round(r['y_eq232']*100,2),'before RGB clamp',r['pre_saturation_median_rgb'])

if __name__=='__main__':main()
