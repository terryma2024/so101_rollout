"""Verify recorded data, lossless PNG saves, and fresh original-state readback."""
from pathlib import Path
import json
import subprocess
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parent

def main():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    assert manifest['error'] is None and manifest['restore_error'] is None
    assert manifest['sequence']==[67,90,120,67]
    assert [c['gamma'] for c in manifest['conditions']]==[67,90,120,67]
    assert all(manifest['final_state_matches'].values())
    result={}
    for name,dev in [('wrist','/dev/v4l/by-id/usb-icSpring_icspring_camera-video-index0'),('side','/dev/v4l/by-id/usb-icSpring_icspring_camera_202404160005-video-index0')]:
        rows=[json.loads(l) for l in (ROOT/name/'frames.jsonl').read_text().splitlines()]
        assert len(rows)==next(r['frames'] for r in manifest['results'] if r['camera']==name)
        assert (ROOT/f'{name}-before.txt').read_bytes()==(ROOT/f'{name}-after.txt').read_bytes()
        verified=0
        with (ROOT/name/'stream.bin').open('rb') as f:
            for row in rows:
                if 'png' not in row:continue
                f.seek(row['offset']);data=f.read(row['bytes'])
                if name=='wrist':
                    decoded=cv2.cvtColor(np.frombuffer(data,np.uint8).reshape(480,640,2),cv2.COLOR_YUV2BGR_YUY2)
                else:
                    decoded=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
                saved=cv2.imread(str(ROOT/name/row['png']))
                assert decoded.shape==saved.shape==(480,640,3)
                assert np.array_equal(decoded,saved)
                verified+=1
        current=subprocess.run(['v4l2-ctl','-d',dev,'--info','--get-fmt-video','--get-parm','--list-ctrls-menus'],capture_output=True,text=True,check=True).stdout
        assert current==(ROOT/f'{name}-before.txt').read_text()
        (ROOT/f'{name}-final-live-verification.txt').write_text(current)
        result[name]=dict(complete_frames=len(rows),png_lossless_roundtrip_checked=verified,
            live_state_matches_original=True,host_receipt_duration=rows[-1]['host_monotonic']-rows[0]['host_monotonic'],
            captured_condition_frames={c['name']:sum(c['start']<=r['host_monotonic']<c['end'] for r in rows) for c in manifest['conditions']})
    (ROOT/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
