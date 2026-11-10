import json,cv2,numpy as np
from pathlib import Path
from PIL import Image,ImageDraw
P=Path(__file__).parent
# Display-space RGB exploratory mapping only; paper ratio fitted on trial 1, all other trials held out.
boxes={'wrist':{'paper':[285,195,315,225],'wood':[65,75,95,110]},'side':{'paper':[273,316,289,339],'wood':[204,280,221,312]}}
rows=[]; annotations=[]
for t in range(1,13):
 imgs={c:np.array(Image.open(P/f'trial-{t:02d}-{c}-frame000.png')) for c in boxes}
 for c,a in imgs.items():
  rs={k:a[y0:y1,x0:x1].reshape(-1,3) for k,(x0,y0,x1,y1) in boxes[c].items()}
  # Manually delimited object search windows; color dominance plus erosion removes background/edges.
  if c=='wrist': wins={'green':([500,207,600,298] if t<=6 else [475,275,570,368]),'red':([478,295,570,385] if t<=6 else [495,182,595,270])}
  else:wins={'green':([307,243,334,270] if t<=6 else [301,215,329,245]),'red':([300,215,329,245] if t<=6 else [307,242,337,271])}
  im=Image.fromarray(a);d=ImageDraw.Draw(im)
  for k,b in {**boxes[c],**wins}.items():d.rectangle(b,outline={'red':'red','green':'lime','paper':'blue','wood':'orange'}[k],width=2);d.text((b[0],b[1]-12),k,fill='blue')
  for k,(x0,y0,x1,y1) in wins.items():
   r=a[y0:y1,x0:x1];rr=r.astype(float);R,G,B=rr.transpose(2,0,1)
   m=(R>G*1.5)&(R>B*1.3)&(R>25) if k=='red' else (G>R*1.15)&(G>B*1.05)&(G>12)
   m=cv2.erode(m.astype('uint8'),np.ones((3,3),np.uint8)).astype(bool)
   rs[k]=r[m]
   ov=np.array(im);ov[y0:y1,x0:x1][m]=[0,255,255];im=Image.fromarray(ov);d=ImageDraw.Draw(im)
  for k,v in rs.items():
   hsv=cv2.cvtColor(v.reshape(1,-1,3),cv2.COLOR_RGB2HSV).reshape(-1,3)
   rows.append({'trial':t,'camera':c,'roi':k,'pixels':len(v),'rgb_median':np.median(v,axis=0).tolist(),'hsv_median':np.median(hsv,axis=0).tolist()})
  im.save(P/f'trial-{t:02d}-{c}-roi.png')
  if t in [1,7,12]:annotations.append(im)
# ratio references paper, not red/green fit (prevents fitting object colors into desired class).
r=lambda t,c,k:np.array(next(v['rgb_median'] for v in rows if v['trial']==t and v['camera']==c and v['roi']==k))
gain=r(1,'side','paper')/r(1,'wrist','paper'); results=[]
for t in [1,7,12]:
 canvas=Image.new('RGB',(1280,990),'white'); d=ImageDraw.Draw(canvas)
 for col,c in enumerate(['wrist','side']):
  a=np.array(Image.open(P/f'trial-{t:02d}-{c}-frame000.png'));canvas.paste(Image.fromarray(a),(col*640,20))
  corr=np.clip(a*gain,0,255).astype('uint8') if c=='wrist' else a
  canvas.paste(Image.fromarray(corr),(col*640,510));d.text((col*640,0),f'Trial {t} {c} original',fill='black');d.text((col*640,492),'Paper-only RGB gain preview' if c=='wrist' else 'Side reference unchanged',fill='black')
 canvas.thumbnail((1280,990));canvas.save(P/f'trial-{t:02d}-paper-gain-preview.jpg')
 for k in ['paper','red','green']:
  w=r(t,'wrist',k);s=r(t,'side',k);cw=np.clip(w*gain,0,255)
  results.append({'trial':t,'roi':k,'rgb_distance_before':float(np.linalg.norm(w-s)),'rgb_distance_after':float(np.linalg.norm(cw-s)),'corrected_wrist_rgb':cw.tolist()})
json.dump({'roi_rectangles':boxes,'statistics':rows,'paper_gain_fit_trial':1,'paper_rgb_gain':gain.tolist(),'validation':results,'note':'RGB/HSV are display-space descriptive measurements, not colorimetric accuracy. Different views sample different faces and lighting. Object masks are color-conditioned and not a complete detection benchmark.'},open(P/'statistics.json','w'),indent=2)
contact=Image.new('RGB',(1280,1440),'white')
for i,im in enumerate(annotations):contact.paste(im,((i%2)*640,(i//2)*480))
contact.save(P/'roi-verification.jpg')
print('gain',gain)
for t in [1,7,12]:
 for k in ['paper','red','green','wood']:print(t,k,'wrist',r(t,'wrist',k),'side',r(t,'side',k))
print(results)
