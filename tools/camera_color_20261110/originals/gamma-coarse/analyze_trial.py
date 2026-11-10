"""Offline gamma comparison using fixed, pre-existing geometry."""
from pathlib import Path
import json
import cv2
import numpy as np
import baseline_roi_definitions as baseline

ROOT=Path(__file__).resolve().parent
MANIFEST=json.loads((ROOT/'manifest.json').read_text())
CONDITIONS=MANIFEST['conditions']

def get_rois(name):
    rs=baseline.rois(name)
    rect={'wrist':[75,140,100,165],'side':[275,395,300,415]}[name]
    x0,y0,x1,y1=rect;poly=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
    mask=np.zeros((480,640),np.uint8);cv2.fillConvexPoly(mask,np.array(poly,np.int32),1)
    rs['paper']=dict(polygon=poly,mask=mask.astype(bool),pixels=int(mask.sum()),role='paper_highlight_monitor')
    return rs

def main():
    result={};roi_doc={};representatives={}
    for name in ['wrist','side']:
        rows=[json.loads(l) for l in (ROOT/name/'frames.jsonl').read_text().splitlines()]
        rs=get_rois(name);keys=list(rs);roi_doc[name]={k:{a:b for a,b in v.items() if a!='mask'} for k,v in rs.items()}
        # All complete frames, including startup and settling, are analyzed.
        times=np.array([r['host_monotonic'] for r in rows])
        med=np.zeros((len(rows),len(keys),3));zero=np.zeros_like(med);le2=np.zeros_like(med);high=np.zeros_like(med)
        dark=np.zeros((len(rows),len(keys)));verydark=np.zeros_like(dark);globalhigh=np.zeros((len(rows),3))
        with (ROOT/name/'stream.bin').open('rb') as f:
            for i,row in enumerate(rows):
                f.seek(row['offset']);bgr=baseline.decode(name,f.read(row['bytes']))
                if bgr is None or bgr.shape!=(480,640,3):raise RuntimeError(f'Bad frame {name}/{i}')
                rgb=bgr[...,::-1]
                globalhigh[i]=(rgb>=253).mean((0,1))
                for j,key in enumerate(keys):
                    p=rgb[rs[key]['mask']]
                    med[i,j]=np.median(p,0);zero[i,j]=(p==0).mean(0);le2[i,j]=(p<=2).mean(0);high[i,j]=(p>=253).mean(0)
                    dark[i,j]=(p.max(1)<32).mean();verydark[i,j]=(p.max(1)<16).mean()
                for c in CONDITIONS:
                    if row['host_monotonic']>=c['start']+7 and row['host_monotonic']<c['end'] and (name,c['name']) not in representatives:
                        representatives[name,c['name']]=bgr.copy()
                if i%500==0:print(name,'analyzed',i,'/',len(rows),flush=True)
        np.savez_compressed(ROOT/name/'all-frame-metrics.npz',times=times,keys=np.array(keys),median_rgb=med,zero_fraction=zero,le2_fraction=le2,ge253_fraction=high,max_lt32_fraction=dark,max_lt16_fraction=verydark,global_ge253_fraction=globalhigh)
        result[name]=dict(total_complete_frames=len(rows),conditions={})
        for c in CONDITIONS:
            mask=(times>=c['start'])&(times<c['end']);early=mask&(times<c['start']+5);late=mask&(times>=c['end']-5)
            if mask.sum()<200:raise RuntimeError('Insufficient condition frames')
            summary={}
            for j,key in enumerate(keys):
                m=med[mask,j]
                summary[key]=dict(pixels=rs[key]['pixels'],median_rgb=np.median(m,0).tolist(),temporal_p05_rgb=np.percentile(m,5,axis=0).tolist(),temporal_p95_rgb=np.percentile(m,95,axis=0).tolist(),temporal_std_rgb=m.std(0).tolist(),
                    drift_first5_to_last5_rgb=(np.median(med[late,j],0)-np.median(med[early,j],0)).tolist(),
                    zero_fraction=zero[mask,j].mean(0).tolist(),le2_fraction=le2[mask,j].mean(0).tolist(),ge253_fraction=high[mask,j].mean(0).tolist(),
                    max_channel_lt32_fraction=float(dark[mask,j].mean()),max_channel_lt16_fraction=float(verydark[mask,j].mean()))
            red=med[mask,keys.index('cube_red')];green=med[mask,keys.index('cube_green')]
            separation=dict(rgb_centroid_distance=float(np.linalg.norm(np.median(red,0)-np.median(green,0))),red_R_minus_G_median=float(np.median(red[:,0]-red[:,1])),green_G_minus_R_median=float(np.median(green[:,1]-green[:,0])),red_dominance_reversal_frames=int((red[:,0]<=red[:,1]).sum()),green_dominance_reversal_frames=int((green[:,1]<=green[:,0]).sum()))
            result[name]['conditions'][c['name']]=dict(gamma_requested_wrist=c['gamma'],frames=int(mask.sum()),rois=summary,cube_separation=separation,global_ge253_fraction=globalhigh[mask].mean(0).tolist())
            cv2.imwrite(str(ROOT/name/f"{c['name']}-original.png"),representatives[name,c['name']])
    result['paired_observation']={}
    for c in CONDITIONS:
        cn=c['name'];pairs={}
        for key in roi_doc['wrist']:
            w=np.array(result['wrist']['conditions'][cn]['rois'][key]['median_rgb']);s=np.array(result['side']['conditions'][cn]['rois'][key]['median_rgb'])
            pairs[key]=dict(wrist_rgb=w.tolist(),side_rgb=s.tolist(),rgb_distance=float(np.linalg.norm(w-s)))
        result['paired_observation'][cn]=pairs
    result['limitations']=['One position A, no held-out geometry or lighting.','AWB stays enabled; cannot isolate pure gamma vs AWB adaptation.','RGB distance is decoded display RGB, not calibrated DeltaE. Side camera is not absolute ground truth.','Cube patches are small and surfaces unmarked/translucent; same-plane comparison is approximate.','Host receipt timestamps, no hardware synchronization or driver sequence-based drop count.']
    (ROOT/'statistics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (ROOT/'roi.json').write_text(json.dumps(roi_doc,indent=2))
    # Retain unaltered originals; this is an analytical contact sheet, <=1600 px.
    tiles=[]
    for c in CONDITIONS:
        row=[]
        for n in ['wrist','side']:
            im=representatives[n,c['name']].copy()
            header=np.zeros((28,640,3),np.uint8)
            cv2.putText(header,n+' / '+c['name'],(8,20),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),1)
            for key in ['cube_red','cube_green','chart_r0_c0','chart_r4_c0','paper']:
                cv2.polylines(im,[np.array(roi_doc[n][key]['polygon'],np.int32)],True,(0,255,255),1)
            row.append(np.vstack([header,im]))
        tiles.append(np.hstack(row))
    sheet=np.vstack(tiles);sheet=cv2.resize(sheet,(1000,1588),interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(ROOT/'gamma-comparison-preview.png'),sheet)
    for c in CONDITIONS:
        cn=c['name'];print('\n',cn,flush=True)
        for n in ['wrist','side']:
            sc=result[n]['conditions'][cn];print(n,'frames',sc['frames'],'globalhigh',sc['global_ge253_fraction'])
            for k in ['cube_red','cube_green','chart_r0_c0','chart_r3_c0','chart_r4_c0','chart_r5_c0','paper']:
                print(k,json.dumps(sc['rois'][k]))
            print('separation',sc['cube_separation'])
        print('cube distances',{k:result['paired_observation'][cn][k]['rgb_distance'] for k in ['cube_red','cube_green']})
    print('OFFLINE_ANALYSIS_COMPLETE',flush=True)

if __name__=='__main__':main()
