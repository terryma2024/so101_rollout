"""Separate the >=253 warning threshold from exact RGB255 and conversion overflow."""
from pathlib import Path
import json
import numpy as np
import cv2
ROOT=Path(__file__).resolve().parent
TRIAL=ROOT.parent
manifest=json.loads((TRIAL/'manifest.json').read_text())
rows=[json.loads(x) for x in (TRIAL/'wrist/frames.jsonl').read_text().splitlines()]
roi=json.loads((ROOT/'reference-roi.json').read_text())['wrist']['chart_r1_c3']
mask=np.zeros((480,640),np.uint8)
cv2.fillConvexPoly(mask,np.array(roi['polygon'],np.int32),1)
iy,ix=np.where(mask)
result={'roi':'chart_r1_c3','definition':'>=253 is a near-limit warning; ==255 is an output endpoint; pre-clamp R>255 demonstrates conversion overflow, not sensor RAW clipping.','conditions':{}}
with (TRIAL/'wrist/stream.bin').open('rb') as f:
 for c in manifest['conditions']:
  series=[]
  for row in rows:
   if not c['start']<=row['host_monotonic']<c['end']:continue
   f.seek(row['offset']);raw=np.frombuffer(f.read(row['bytes']),np.uint8).reshape(480,640,2)
   y=raw[iy,ix,0].astype(np.int64)
   v=raw[iy,(ix//2)*2+1,1].astype(np.int64)-128
   pre=((np.maximum(y-16,0)*1220542+1673527*v+(1<<19))>>20)
   decoded=cv2.cvtColor(raw,cv2.COLOR_YUV2RGB_YUY2)[iy,ix,0]
   assert np.array_equal(np.clip(pre,0,255).astype(np.uint8),decoded)
   series.append([(decoded>=253).mean(),(decoded==255).mean(),(pre>255).mean()])
  values=np.array(series)
  result['conditions'][c['name']]={'frames':len(series),'R_ge253_fraction':float(values[:,0].mean()),'R_eq255_fraction':float(values[:,1].mean()),'pre_clamp_R_gt255_fraction':float(values[:,2].mean())}
(ROOT/'pink-highlight-audit.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
