#!/usr/bin/env python3
"""Read-only source audit; writes evidence only. Run with so101-smolvla-061 python."""
import argparse, csv, hashlib, json, collections
from pathlib import Path
import cv2
import av
import numpy as np
import pandas as pd
from tools.prepare_smolvla_data import numeric_digest
B=Path('/data/work/so101-evidence/real-robot')
D=Path('/data/work/so101-datasets')
O=None
OLD=B/'smolvla-finetune-20261030/antzb-completed/data/build-01'
def read(p):return json.loads(p.read_text())
def save(n,x):(O/n).write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def tables(root,sub):return pd.concat([pd.read_parquet(p) for p in sorted((root/sub).rglob('*.parquet'))],ignore_index=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()
def main():
 O.mkdir(exist_ok=True);(O/'first').mkdir(exist_ok=True);(O/'sheets').mkdir(exist_ok=True)
 records=read(OLD/'episode-map.json')
 cells=read(B/'prep-20261026/layout/placement-list.json')['cells']
 cal=B/'calib-20261027-r3';intr=read(cal/'intrinsics-side.json');ext=read(cal/'extrinsics-side.json')
 flip=np.array([-1.,1,1]);C=np.array(ext['position_cm'])*flip;z=np.array(ext['forward'])*flip;z/=np.linalg.norm(z)
 up=np.mean([f['image_up'] for f in ext['frames']],axis=0)*flip;y=-(up-up@z*z);y/=np.linalg.norm(y);R=np.vstack([np.cross(y,z),y,z])
 px={}
 for k,v in cells.items():
  cam=R@(np.array([*v,2.])*flip-C)
  out,_=cv2.projectPoints(cam.reshape(1,1,3),np.zeros(3),np.zeros(3),np.array(intr['K']),np.array(intr['D']))
  px[k]=tuple(np.round(out.ravel()).astype(int))
 plans={}
 for batch in read(Path('tools/plans/p2-20261030.json'))['batches']:
  for i,e in enumerate(batch['episodes']):plans[(batch['dataset_name'],i)]={'green':e['target'] if batch['color']=='green' else e['distractor'],'red':e['target'] if batch['color']=='red' else e['distractor']}
 for name,file in [('real-cube-bowl-pilot-20261027','prep-20261026/layout/placement-list.json'),('real-cube-bowl-adjacent-20261028','prep-20261028-adjacent/actual-placement.json'),('real-cube-bowl-red-20261028','prep-20261028-red/recorded-placement.json')]:
  for i,e in enumerate(read(B/file)['episodes']):plans[(name,i)]={c:e[c] for c in ('green','red')}
 known={}
 for name,file in [('real-cube-bowl-adjacent-20261028','prep-20261028-adjacent/check/cell-check.json'),('real-cube-bowl-red-20261028','prep-20261028-red/check/cell-check.json')]:
  for i,e in enumerate(read(B/file)):
   known[(name,i)]={c:(e[c+'_cells'][0] if len(e[c+'_cells'])==1 else 'unknown') for c in ('green','red')}
 for i,e in enumerate(read(B/'pilot-check-20261027/full-r3/full-summary.json')['episodes']):
  known[('real-cube-bowl-pilot-20261027',i)]={c:e[c+'_start']['cell'] if e.get(c+'_start') else 'unknown' for c in ('green','red')}
 groupdata={};meta={};caps={};checks=[];tiles={};dimensions=[]
 for split in ('train','validation'):
  root=D/f'real-cube-bowl-smolvla-{split}-20261030';data=tables(root,'data');eps=tables(root,'meta/episodes');tasks=pd.read_parquet(root/'meta/tasks.parquet')
  assert tasks.to_dict('index')=={'Put the green cube into the paper bowl':{'task_index':0},'Put the red cube into the paper bowl':{'task_index':1}}
  for r in [r for r in records if r['split']==split]:
   ei=r['derived_episode_index'];fr=data[data.episode_index==ei];e=eps[eps.episode_index==ei].iloc[0]
   assert len(fr)==r['frames'] and numeric_digest(fr)==r['numeric_sha256']
   assert set(fr.task_index)=={0 if r['color']=='green' else 1}
   r['task_metadata_verified']=True
   name=r['source_dataset'].replace('-clean-','-');oi=r['original_episode_index'];p=plans.get((name,oi),{})
   r['planned_green']=p.get('green','unknown');r['planned_red']=p.get('red','unknown')
   key='observation.images.side';fi=int(e[f'videos/{key}/file_index']);ch=int(e[f'videos/{key}/chunk_index']);t=float(e[f'videos/{key}/from_timestamp'])
   vp=root/f'videos/{key}/chunk-{ch:03d}/file-{fi:03d}.mp4'
   if str(vp) not in caps:caps[str(vp)]=av.open(str(vp))
   cap=caps[str(vp)];stream=cap.streams.video[0];w=stream.width;h=stream.height;assert max(w,h)<=1600
   dimensions.append({'split':split,'episode':ei,'width':w,'height':h})
   cap.seek(int(t/stream.time_base),stream=stream,backward=True)
   frame=next(f for f in cap.decode(video=0) if float(f.pts*f.time_base)>=t-.005);img=frame.to_ndarray(format='bgr24')
   cv2.imwrite(str(O/f'first/{split}-{ei:03d}.jpg'),img)
   hsv=cv2.cvtColor(img,cv2.COLOR_BGR2HSV);med={k:np.median(hsv[v-3:v+4,u-3:u+4].reshape(-1,3),axis=0) for k,(u,v) in px.items()};paper=np.median([v[2] for v in med.values()])
   detected={'green':[],'red':[]}
   for k,(hu,s,val) in med.items():
    if (hu<=5 or hu>=160) and s>150:detected['red'].append(k)
    elif val<.55*paper:detected['green'].append(k)
   blob={}
   for c in ('green','red'):
    mask=((hsv[:,:,0]>=40)&(hsv[:,:,0]<=100)&(hsv[:,:,1]>50)&(hsv[:,:,2]<200)) if c=='green' else (((hsv[:,:,0]>=160)|(hsv[:,:,0]<=5))&(hsv[:,:,1]>140))
    roi=np.zeros_like(mask);roi[145:320,205:440]=True;mask=(mask&roi).astype('uint8')*255
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    candidates=[]
    for contour in contours:
     if cv2.contourArea(contour)<45:continue
     m=cv2.moments(contour);center=np.array([m['m10']/m['m00'],m['m01']/m['m00']]);near=min(px,key=lambda k:np.linalg.norm(center-px[k]));dist=float(np.linalg.norm(center-px[near]))
     if dist<17:candidates.append((near,round(dist,2)))
    blob[c]=candidates
   actual=known.get((name,oi),{})
   for c in ('green','red'):
    r[c+'_position']=actual.get(c,blob[c][0][0] if len(blob[c])==1 else (detected[c][0] if len(detected[c])==1 else 'unknown'))
   r['position_basis']='prior first-frame cell audit + current frame cross-check' if actual else 'current first-frame r3 projected-cell classifier; contact sheet review'
   r['current_cell_candidates']={'cell':detected,'blob':blob}
   r['target_position']=r[r['color']+'_position'];r['distractor_position']=r['red_position' if r['color']=='green' else 'green_position']
   r['planned_match']={c:r[c+'_position']==p.get(c) for c in ('green','red')}
   thumb=cv2.resize(img[140:330,190:445],(255,190));canvas=np.full((220,255,3),255,np.uint8);canvas[:190]=thumb
   label=f"{ei} {r['color'][0]} G{r['green_position']} R{r['red_position']}"
   cv2.putText(canvas,label,(4,209),cv2.FONT_HERSHEY_SIMPLEX,.48,(0,0,0),1)
   tiles.setdefault(r['source_dataset'],[]).append(canvas)
  checks.append({'split':split,'episodes':len(eps),'frames':len(data),'tasks':tasks.to_dict('index')})
 for cap in caps.values():cap.close()
 for group,ts in tiles.items():
  for page,start in enumerate(range(0,len(ts),24)):
   tt=ts[start:start+24];tt += [np.zeros_like(tt[0])]*(24-len(tt));sheet=np.vstack([np.hstack(tt[i:i+4]) for i in range(0,24,4)])
   assert max(sheet.shape[:2])<=1600
   cv2.imwrite(str(O/f'sheets/{group}-{page}.jpg'),sheet)
 save('image-dimensions.json',dimensions);save('episodes.json',records);save('dataset-checks.json',checks)
 leaks={}
 for k in ('origin','numeric_sha256','group'):
  owners=collections.defaultdict(set)
  for r in records:owners[r[k]].add(r['split'])
  leaks[k]=[v for v,s in owners.items() if len(s)>1]
 save('leakage.json',leaks)
 counts=collections.Counter((r['split'],r['color'],r['target_position'],r['distractor_position']) for r in records)
 save('coverage.json',[dict(zip(['split','color','target','distractor','episodes'],[*k,v])) for k,v in sorted(counts.items())])
 with (O/'episodes.csv').open('w') as f:
  fields=[k for k in records[0] if k not in ('current_cell_candidates','planned_match')];w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(records)
 # Verify the frozen file manifest, including video bytes, against the local datasets.
 frozen=read(OLD/'dataset-files-sha256.json');verified=[]
 for split,files in frozen.items():
  root=D/f'real-cube-bowl-smolvla-{split}-20261030'
  for rel,expected in files.items():
   p=root/rel;actual=sha(p);verified.append({'split':split,'file':rel,'matches':actual==expected['sha256'],'sha256':actual})
 save('frozen-files-verification.json',verified)
 print(json.dumps({'checks':checks,'unknown':sum('unknown' in (r['target_position'],r['distractor_position']) for r in records),'frozen_files':len(verified),'all_match':all(v['matches'] for v in verified)},default=str))
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--evidence',type=Path,required=True,help='Fresh output directory; existing evidence is never overwritten')
 args=parser.parse_args()
 O=args.evidence.resolve()
 if O.exists():parser.error('Evidence directory already exists; use a fresh output path')
 main()
