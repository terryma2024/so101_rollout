"""Offline per-frame libjpeg warning audit; original bytes remain untouched."""
from pathlib import Path
import json
import subprocess
import sys
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent

def main():
    rows=[json.loads(l) for l in (ROOT/'side/frames.jsonl').read_text().splitlines()]
    if '--decode' in sys.argv:
        with (ROOT/'side/stream.bin').open('rb') as f:
            for row in rows:
                print('FRAME',row['index'],file=sys.stderr,flush=True)
                f.seek(row['offset'])
                image=cv2.imdecode(np.frombuffer(f.read(row['bytes']),np.uint8),cv2.IMREAD_COLOR)
                if image is None or image.shape!=(480,640,3):print('DECODE_FAILED',file=sys.stderr,flush=True)
        return
    p=subprocess.run([sys.executable,__file__,'--decode'],capture_output=True,text=True,check=True)
    (ROOT/'jpeg-decode-audit.log').write_text(p.stderr)
    manifest=json.loads((ROOT/'manifest.json').read_text());last=None;bad=[]
    for line in p.stderr.splitlines():
        if line.startswith('FRAME '):last=int(line.split()[1])
        elif line:
            if last is None:raise RuntimeError('Warning before frame index: '+line)
            condition=next((c['name'] for c in manifest['conditions'] if c['start']<=rows[last]['host_monotonic']<c['end']),'startup_or_settle')
            bad.append(dict(index=last,warning=line,condition=condition))
    (ROOT/'jpeg-warning-frames.json').write_text(json.dumps(bad,indent=2))
    print(json.dumps(dict(audited_frames=len(rows),warnings=bad),indent=2))

if __name__=='__main__':main()
