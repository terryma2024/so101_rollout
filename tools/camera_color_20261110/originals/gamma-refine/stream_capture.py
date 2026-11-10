"""Disposable evidence acquisition; V4L2 streaming only, no setters."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import select
import signal
import subprocess
import time
import threading
STOP = threading.Event()

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
DURATION = 180.0
DEVICES = {
    'wrist': ('/dev/v4l/by-id/usb-icSpring_icspring_camera-video-index0', 'YUYV'),
    'side': ('/dev/v4l/by-id/usb-icSpring_icspring_camera_202404160005-video-index0', 'MJPG'),
}

def query(dev):
    p = subprocess.run(['v4l2-ctl', '-d', dev, '--info', '--get-fmt-video',
                        '--get-parm', '--list-ctrls-menus'], capture_output=True, text=True, timeout=8)
    p.check_returncode()
    return p.stdout

def capture(name, dev, fmt):
    target = ROOT / name
    target.mkdir(exist_ok=False)
    (target / 'png').mkdir()
    before = query(dev)
    (target / 'before.txt').write_text(before)
    if '640/480' not in before or f"'{fmt}'" not in before:
        raise RuntimeError(f'{name}: unexpected format')
    command = ['v4l2-ctl', '-d', dev, '--stream-mmap=3', '--stream-poll', '--stream-no-query', '--stream-to=-']
    frames = 0
    saved = 0
    pending = bytearray()
    offset = 0
    next_save = 0.0
    first_mono = None
    error = None
    started = time.monotonic()
    proc = None
    with (target / 'stream.bin').open('wb') as raw, (target / 'frames.jsonl').open('w') as metadata, (target / 'capture.stderr').open('wb') as stderr:
        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=stderr, bufsize=0)
            while True:
                if STOP.is_set():
                    break
                elapsed = time.monotonic() - started
                if elapsed >= DURATION:
                    break
                ready, _, _ = select.select([proc.stdout], [], [], min(1.0, DURATION-elapsed))
                if not ready:
                    if proc.poll() is not None:
                        raise RuntimeError(f'{name}: capture exited early: {proc.returncode}')
                    continue
                chunk = os.read(proc.stdout.fileno(), 1024*1024)
                if not chunk:
                    raise RuntimeError(f'{name}: early end of stream')
                raw.write(chunk)
                pending.extend(chunk)
                while True:
                    if fmt == 'YUYV':
                        length = 640*480*2
                        if len(pending) < length:
                            break
                    else:
                        if len(pending) < 2:
                            break
                        if pending[:2] != b'\xff\xd8':
                            start = pending.find(b'\xff\xd8')
                            if start < 0:
                                # A complete next SOI may arrive in a later pipe read.
                                if len(pending) > 65536:
                                    raise RuntimeError(f'{name}: missing MJPEG boundary')
                                break
                            if any(pending[:start]):
                                raise RuntimeError(f'{name}: nonzero bytes between JPEG frames')
                            del pending[:start]
                            offset += start
                        end = pending.find(b'\xff\xd9', 2)
                        if end < 0:
                            break
                        length = end+2
                    received = time.monotonic()
                    if first_mono is None:
                        first_mono = received
                    rel = received-started
                    record = dict(index=frames, offset=offset, bytes=length,
                                  host_monotonic=received, host_unix=time.time(), elapsed=rel,
                                  phase='startup' if rel < 30 else 'analysis')
                    if rel >= next_save:
                        data = bytes(pending[:length])
                        if fmt == 'YUYV':
                            frame = cv2.cvtColor(np.frombuffer(data, np.uint8).reshape(480,640,2), cv2.COLOR_YUV2BGR_YUY2)
                        else:
                            frame = cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
                        if frame is None or frame.shape != (480,640,3):
                            raise RuntimeError(f'{name}: decode failed')
                        filename = f'png/{frames:05d}-{rel:06.2f}.png'
                        if not cv2.imwrite(str(target/filename),frame):
                            raise RuntimeError(f'{name}: PNG save failed')
                        record['png'] = filename
                        saved += 1
                        next_save = rel + 0.2
                    metadata.write(json.dumps(record)+'\n')
                    frames += 1
                    offset += length
                    del pending[:length]
        except Exception as exc:
            error = repr(exc)
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.send_signal(signal.SIGINT)
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)
                proc.stdout.close()
    after = query(dev)
    (target/'after.txt').write_text(after)
    summary = dict(camera=name, device=dev, resolved_device=os.path.realpath(dev), format=fmt,
                   width=640, height=480, frames=frames, saved_png=saved,
                   duration_requested=DURATION, first_frame_delay=None if first_mono is None else first_mono-started,
                   full_frame_bytes=offset, trailing_incomplete_bytes=len(pending),
                   controls_format_and_device_unchanged=before==after,
                   command=command, error=error, process_returncode=proc.returncode if proc else None,
                   timestamp_definition='Host reception of a complete frame; not exposure time or hardware synchronization.')
    (target/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)
    return summary

if __name__ == '__main__':
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(capture,name,*spec) for name,spec in DEVICES.items()]
        results = [future.result() for future in futures]
    manifest = dict(created=datetime.now().astimezone().isoformat(),duration_seconds=DURATION,
                    phases=dict(startup=[0,30],analysis=[30,45]),results=results,
                    constraints='No control setters, no format setters, no robot connection. Raw stream retained for all-frame ROI analysis; decoded PNG about 5 Hz. Not sensor RAW.')
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    if any(r['error'] or not r['controls_format_and_device_unchanged'] or r['frames']<600 for r in results):
        raise SystemExit('Acquisition incomplete or before/after changed: inspect evidence.')
