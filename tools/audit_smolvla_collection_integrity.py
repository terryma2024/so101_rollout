#!/usr/bin/env python3
"""Read-only dataset/video/task/reset audit; no hardware or model imports."""
import sys,json,subprocess,hashlib,concurrent.futures,argparse
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,'tools');from smolvla_recording_check import load_records
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args();p=args.package;out=args.output;out.mkdir(parents=True,exist_ok=True);plan=json.loads((p/'plan.json').read_text());rows=[];jobs=[]
for t in plan['trials']:
 root=Path(t['dataset_path']);info=json.loads((root/'meta/info.json').read_text());table=pd.concat([pd.read_parquet(f) for f in (root/'data').rglob('*.parquet')]);r=json.loads((p/f"trial-{t['id']:02d}-execution.json").read_text());pre=json.loads((Path(r['preflight_path'])/'result.json').read_text());records=load_records(Path(t['recording_path']));resets=[m for k,m,f in records if k=='reset'];requests=[m for k,m,f in records if k=='request'];outputs=[m for k,m,f in records if k=='output'];tasks=pd.read_parquet(root/'meta/tasks.parquet').reset_index().to_dict('records')
 assert info['total_episodes']==1 and info['total_frames']==len(table) and info['total_tasks']==1
 assert table.task_index.unique().tolist()==[0] and tasks[0]['task']==t['env']['TASK']
 np.testing.assert_allclose(table.timestamp,np.arange(len(table))/20,rtol=0,atol=2e-6)
 assert requests[0]['request_id']==0 and requests[0]['request_tick']==0
 assert all(x['task']==t['env']['TASK'] for x in resets+requests)
 assert all(x['generation']==requests[0]['generation'] for x in requests+outputs)
 rows.append(dict(id=t['id'],tasks=tasks,preflight=pre,resets=resets,request_generation=requests[0]['generation'],model_timings=r['model_timings'],actual_receipt_error=r.get('error'),recovery=r.get('recovery'),runtime_normal=not bool(r.get('error')),first_output_host_time=outputs[0]['time'],last_output_host_time=outputs[-1]['time']))
 for f in root.rglob('*.mp4'):jobs.append((t['id'],f,len(table)))
def video(job):
 i,f,n=job
 probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,nb_frames,avg_frame_rate,duration','-of','json',str(f)],capture_output=True,text=True,check=True)
 meta=json.loads(probe.stdout)['streams'][0]
 decode=subprocess.run(['ffmpeg','-v','error','-i',str(f),'-map','0:v:0','-f','null','-','-progress','pipe:1','-nostats'],capture_output=True,text=True)
 frame=int([x.split('=')[1] for x in decode.stdout.splitlines() if x.startswith('frame=')][-1]);assert decode.returncode==0 and not decode.stderr.strip() and frame==n and int(meta['nb_frames'])==n
 print(f'video {i:02d} {f.parts[-3]} {frame} OK',flush=True)
 return dict(id=i,path=str(f),metadata=meta,full_decode_returncode=decode.returncode,full_decode_frames=frame,stderr=decode.stderr,sha256=hashlib.sha256(f.read_bytes()).hexdigest())
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:videos=list(ex.map(video,jobs))
(out/'integrity-extra.json').write_text(json.dumps(dict(trials=rows,videos=videos),indent=2))
