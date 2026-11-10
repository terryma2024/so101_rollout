"""Offline geometry-only ROIs, all captured frames; no camera access."""
from pathlib import Path
import json
import hashlib
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent
# Four corners of the printed color grid, in each camera's displayed orientation.
QUADS={'wrist':[[133,68],[310,50],[325,330],[170,373]],
       'side':[[225,229],[327,217],[356,339],[231,363]]}
CUBE_RECTS={'wrist':{'cube_red':[282,16,299,23],'cube_green':[215,17,233,24]},
            'side':{'cube_red':[249,358,258,364],'cube_green':[305,353,314,358]}}

def rois(name):
    h=cv2.getPerspectiveTransform(np.float32([[0,0],[4,0],[4,6],[0,6]]),np.float32(QUADS[name]))
    result={}
    for row in range(6):
        for col in range(4):
            # IDs follow wrist orientation; the side view is rotated 180 degrees.
            rr,cc=(row,col) if name=='wrist' else (5-row,3-col)
            key=f'chart_r{rr}_c{cc}'
            q=np.float32([[[col+.27,row+.27],[col+.73,row+.27],
                           [col+.73,row+.73],[col+.27,row+.73]]])
            poly=np.round(cv2.perspectiveTransform(q,h)[0]).astype(int)
            result[key]=dict(polygon=poly.tolist(),role='gray' if cc==0 else 'color')
    for key,(x0,y0,x1,y1) in CUBE_RECTS[name].items():
        result[key]=dict(polygon=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],role='independent_cube')
    for key,entry in result.items():
        mask=np.zeros((480,640),np.uint8)
        cv2.fillConvexPoly(mask,np.array(entry['polygon'],np.int32),1)
        entry['mask']=mask.astype(bool)
        entry['pixels']=int(mask.sum())
    return result

def decode(name,data):
    if name=='wrist':
        return cv2.cvtColor(np.frombuffer(data,np.uint8).reshape(480,640,2),cv2.COLOR_YUV2BGR_YUY2)
    return cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)

def main():
    all_rois={name:rois(name) for name in ['wrist','side']}
    roi_document={'method':'Fixed geometric patches; no RGB/HSV threshold or color-based pixel selection.',
        'chart_correspondence':'Same physical color card; side grid row/col reversed relative to wrist.',
        'cube_limitation':'Small manually selected apparent upper-face patches. Faces are not physically marked; translucent material, viewing angle and illumination remain confounders. Cube RGB differences are observational, not isolated camera error.',
        'units':'Decoded display RGB, 0..255; not calibrated colorimetry or sensor RAW.',
        'rois':{n:{k:{a:b for a,b in v.items() if a!='mask'} for k,v in rs.items()} for n,rs in all_rois.items()}}
    (ROOT/'roi.json').write_text(json.dumps(roi_document,indent=2))
    result={}
    comparison=[]
    for name in ['wrist','side']:
        meta=[json.loads(l) for l in (ROOT/name/'frames.jsonl').read_text().splitlines()]
        rs=all_rois[name]
        tracks={key:[] for key in rs}
        representative=None
        with (ROOT/name/'stream.bin').open('rb') as f, (ROOT/name/'roi-frame-statistics.jsonl').open('w') as out:
            for i,rec in enumerate(meta):
                f.seek(rec['offset']); data=f.read(rec['bytes'])
                bgr=decode(name,data)
                if bgr is None or bgr.shape!=(480,640,3): raise RuntimeError(f'bad frame {name}:{i}')
                rgb=bgr[...,::-1]
                if rec['elapsed']>=35 and representative is None: representative=bgr.copy()
                row={'index':i,'elapsed':rec['elapsed'],'host_monotonic':rec['host_monotonic'],'rois':{}}
                for key,roi in rs.items():
                    pixels=rgb[roi['mask']]
                    median=np.median(pixels,axis=0)
                    st=dict(median_rgb=median.tolist(),
                        zero_fraction=(pixels==0).mean(0).tolist(),
                        le2_fraction=(pixels<=2).mean(0).tolist(),
                        ge253_fraction=(pixels>=253).mean(0).tolist(),
                        max_channel_lt16_fraction=float((pixels.max(1)<16).mean()),
                        max_channel_lt32_fraction=float((pixels.max(1)<32).mean()))
                    tracks[key].append(st)
                    row['rois'][key]=st
                out.write(json.dumps(row,separators=(',',':'))+'\n')
        t=np.array([m['elapsed'] for m in meta]); stable=(t>=30)&(t<45)
        startup=t<5; early=(t>=30)&(t<35); late=t>=40
        if stable.sum()<200 or not early.any() or not late.any(): raise RuntimeError('not enough analysis frames')
        summary={}
        for key,series in tracks.items():
            med=np.array([x['median_rgb'] for x in series])
            ss=med[stable]
            record=dict(pixels=rs[key]['pixels'],median_rgb=np.median(ss,axis=0).tolist(),
                temporal_p05_rgb=np.percentile(ss,5,axis=0).tolist(),temporal_p95_rgb=np.percentile(ss,95,axis=0).tolist(),
                temporal_std_rgb=ss.std(0).tolist(),
                drift_30_35_to_40_45_rgb=(np.median(med[late],axis=0)-np.median(med[early],axis=0)).tolist(),
                drift_norm=float(np.linalg.norm(np.median(med[late],axis=0)-np.median(med[early],axis=0))),
                startup_first5s_to_analysis_rgb=(np.median(ss,axis=0)-np.median(med[startup],axis=0)).tolist())
            for metric in ['zero_fraction','le2_fraction','ge253_fraction','max_channel_lt16_fraction','max_channel_lt32_fraction']:
                record[metric]=np.mean(np.array([x[metric] for x in series])[stable],axis=0).tolist()
            summary[key]=record
        red=np.array([r['median_rgb'] for r in tracks['cube_red']])[stable]
        green=np.array([r['median_rgb'] for r in tracks['cube_green']])[stable]
        separation=dict(rgb_centroid_distance=float(np.linalg.norm(np.median(red,0)-np.median(green,0))),
            red_R_minus_G_median=float(np.median(red[:,0]-red[:,1])),
            green_G_minus_R_median=float(np.median(green[:,1]-green[:,0])),
            red_frames_without_R_over_G=int((red[:,0]<=red[:,1]).sum()),
            green_frames_without_G_over_R=int((green[:,1]<=green[:,0]).sum()),
            caveat='Temporal fixed-ROI diagnostic only; not a spatial/background classifier or model accuracy evaluation.')
        result[name]=dict(frames=len(meta),analysis_frames=int(stable.sum()),
            first_elapsed=float(t[0]),last_elapsed=float(t[-1]),
            measured_host_reception_fps=float((len(t)-1)/(t[-1]-t[0])),
            host_interval_p05_p50_p95=np.percentile(np.diff(t),[5,50,95]).tolist(),
            rois=summary,cube_separation=separation)
        if representative is None: raise RuntimeError('missing representative')
        cv2.imwrite(str(ROOT/name/'analysis-original.png'),representative)
        for key,roi in rs.items():
            poly=np.array(roi['polygon'],np.int32)
            cv2.polylines(representative,[poly],True,(0,255,255),1)
            label=key.removeprefix('chart_').replace('cube_','')
            x,y=poly.min(0)
            cv2.putText(representative,label,(int(x),max(10,int(y)-2)),cv2.FONT_HERSHEY_SIMPLEX,.27,(0,255,255),1)
        cv2.putText(representative,name+' - fixed ROIs, t~35s',(8,468),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,255,255),1)
        comparison.append(representative)
    if not cv2.imwrite(str(ROOT/'roi-verification.png'),np.hstack(comparison)): raise RuntimeError('preview failed')
    pairs={}
    for key in result['wrist']['rois']:
        w=np.array(result['wrist']['rois'][key]['median_rgb']);s=np.array(result['side']['rois'][key]['median_rgb'])
        pairs[key]=dict(wrist_rgb=w.tolist(),side_rgb=s.tolist(),rgb_distance=float(np.linalg.norm(w-s)))
    result['paired_observation']=pairs
    result['limitations']=[roi_document['cube_limitation'],'Single position A only; no independent position holdout yet.',
        'Host reception timestamps only; no V4L2 sequence counters, driver exposure times or certified drop-frame counts.',
        'Lab/DeltaE and absolute color accuracy are not reported; unknown printed reference values.',
        'A 45-second stream restart is not a power-on/cold-AWB test; no stability beyond this interval is established.']
    (ROOT/'statistics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    hashes={}
    for p in [ROOT/'capture.py',ROOT/'analyze.py',ROOT/'roi.json',ROOT/'manifest.json',ROOT/'statistics.json']:
        hashes[p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    (ROOT/'artifact-sha256.json').write_text(json.dumps(hashes,indent=2))
    print(json.dumps({n:{k:v for k,v in result[n].items() if k!='rois'} for n in ['wrist','side']},indent=2))
    for n in ['wrist','side']:
        for k in ['cube_red','cube_green']+[f'chart_r{i}_c0' for i in range(6)]:
            print(n,k,json.dumps(result[n]['rois'][k]))

if __name__=='__main__': main()
