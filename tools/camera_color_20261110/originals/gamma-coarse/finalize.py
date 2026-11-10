"""Recompute condition summaries from all-frame arrays, excluding audited JPEG warnings."""
from pathlib import Path
import json
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent

def main():
    summary=json.loads((ROOT/'statistics.json').read_text())
    manifest=json.loads((ROOT/'manifest.json').read_text())
    warnings=json.loads((ROOT/'jpeg-warning-frames.json').read_text())
    excluded={x['index'] for x in warnings}
    for name in ['wrist','side']:
        arrays=np.load(ROOT/name/'all-frame-metrics.npz')
        times=arrays['times'];med=arrays['median_rgb'];keys=arrays['keys'].tolist()
        valid=np.ones(len(times),bool)
        if name=='side':
            for idx in excluded:valid[idx]=False
        summary[name]['excluded_decode_warning_frames']=sorted(excluded) if name=='side' else []
        for c in manifest['conditions']:
            mask=(times>=c['start'])&(times<c['end'])&valid
            early=mask&(times<c['start']+5);late=mask&(times>=c['end']-5)
            condition=summary[name]['conditions'][c['name']]
            condition['captured_condition_frames']=int(((times>=c['start'])&(times<c['end'])).sum())
            condition['frames']=int(mask.sum())
            for j,key in enumerate(keys):
                roi=condition['rois'][key];m=med[mask,j]
                roi.update(median_rgb=np.median(m,0).tolist(),temporal_p05_rgb=np.percentile(m,5,axis=0).tolist(),
                    temporal_p95_rgb=np.percentile(m,95,axis=0).tolist(),temporal_std_rgb=m.std(0).tolist(),
                    drift_first5_to_last5_rgb=(np.median(med[late,j],0)-np.median(med[early,j],0)).tolist())
                for metric in ['zero_fraction','le2_fraction','ge253_fraction']:
                    roi[metric]=arrays[metric][mask,j].mean(0).tolist()
                for output,input_key in [('max_channel_lt32_fraction','max_lt32_fraction'),('max_channel_lt16_fraction','max_lt16_fraction')]:
                    roi[output]=float(arrays[input_key][mask,j].mean())
            condition['global_ge253_fraction']=arrays['global_ge253_fraction'][mask].mean(0).tolist()
            red=med[mask,keys.index('cube_red')];green=med[mask,keys.index('cube_green')]
            condition['cube_separation']=dict(rgb_centroid_distance=float(np.linalg.norm(np.median(red,0)-np.median(green,0))),
                red_R_minus_G_median=float(np.median(red[:,0]-red[:,1])),green_G_minus_R_median=float(np.median(green[:,1]-green[:,0])),
                red_dominance_reversal_frames=int((red[:,0]<=red[:,1]).sum()),green_dominance_reversal_frames=int((green[:,1]<=green[:,0]).sum()))
    for c in manifest['conditions']:
        cn=c['name']
        for key in summary['paired_observation'][cn]:
            w=np.array(summary['wrist']['conditions'][cn]['rois'][key]['median_rgb'])
            s=np.array(summary['side']['conditions'][cn]['rois'][key]['median_rgb'])
            summary['paired_observation'][cn][key]=dict(wrist_rgb=w.tolist(),side_rgb=s.tolist(),rgb_distance=float(np.linalg.norm(w-s)))
    summary['decode_quality']={'audited_mjpeg_frames':summary['side']['total_complete_frames'],'excluded_warning_frames':warnings,'note':'All complete frames retained. The warned frame is excluded from condition summaries; no sensor or driver dropped-frame rate is claimed.'}
    (ROOT/'statistics.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    roi=json.loads((ROOT/'roi.json').read_text());tiles=[]
    for c in manifest['conditions']:
        row=[]
        for name in ['wrist','side']:
            im=cv2.imread(str(ROOT/name/f"{c['name']}-original.png"))
            assert im.shape==(480,640,3)
            for key in ['cube_red','cube_green','chart_r0_c0','chart_r4_c0','paper']:
                cv2.polylines(im,[np.array(roi[name][key]['polygon'],np.int32)],True,(0,255,255),1)
            header=np.zeros((28,640,3),np.uint8)
            cv2.putText(header,name+' / '+c['name'],(8,20),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),1)
            row.append(np.vstack([header,im]))
        tiles.append(np.hstack(row))
    image=cv2.resize(np.vstack(tiles),(1000,1588),interpolation=cv2.INTER_AREA)
    assert cv2.imwrite(str(ROOT/'gamma-comparison-preview.png'),image)
    print('Final summaries: 1 side MJPEG warning frame excluded; all originals preserved. Preview 1000x1588.')
    for c in manifest['conditions']:
        cn=c['name'];w=summary['wrist']['conditions'][cn];s=summary['side']['conditions'][cn]
        print(cn,'usable frames',w['frames'],s['frames'],'red/green distance',summary['paired_observation'][cn]['cube_red']['rgb_distance'],summary['paired_observation'][cn]['cube_green']['rgb_distance'])

if __name__=='__main__':main()
