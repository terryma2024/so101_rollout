from pathlib import Path
import json,cv2,numpy as np
ROOT=Path(__file__).resolve().parent
m=json.loads((ROOT/'manifest.json').read_text())
out={'method':'Phase correlation on fixed grayscale chart crop and Hanning window; proxy only, gamma can affect response. Crop and DFT dimensions are even.','cameras':{}}
for cam,rect in [('wrist',(135,65,325,365)),('side',(230,230,350,350))]:
 x0,y0,x1,y1=rect
 assert cv2.getOptimalDFTSize(x1-x0)%2==0 and cv2.getOptimalDFTSize(y1-y0)%2==0
 def crop(path):
  im=cv2.imread(str(path),cv2.IMREAD_GRAYSCALE)
  assert im.shape==(480,640)
  return im[y0:y1,x0:x1].astype(np.float32)
 ref=crop(ROOT/cam/'g67_initial-original.png')
 win=cv2.createHanningWindow((x1-x0,y1-y0),cv2.CV_32F);checks=[]
 for c in m['conditions']:
  shift,response=cv2.phaseCorrelate(ref.copy(),crop(ROOT/cam/(c['name']+'-original.png')),win)
  checks.append({'condition':c['name'],'shift_xy_pixels':list(shift),'response':response})
 old=crop(ROOT.parent/'camera-gamma-trial-20261110'/cam/'g67_initial-original.png')
 shift,response=cv2.phaseCorrelate(old,ref.copy(),win)
 out['cameras'][cam]={'crop_xyxy':rect,'within_trial':checks,'versus_coarse_initial':{'shift_xy_pixels':shift,'response':response}}
(ROOT/'roi-placement-check.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
