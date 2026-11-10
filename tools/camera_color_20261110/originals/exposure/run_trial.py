"""Authorized wrist exposure sequence. All other controls and formats retained."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import json
import re
import signal
import subprocess
import time
import traceback

import stream_capture as stream

ROOT=Path(__file__).resolve().parent
W=stream.DEVICES['wrist'][0]
S=stream.DEVICES['side'][0]
events=[]
futures=[]

def event(kind,**kwargs):
    row=dict(kind=kind,monotonic=time.monotonic(),unix=time.time(),**kwargs)
    events.append(row)
    with (ROOT/'events.jsonl').open('a') as f:
        f.write(json.dumps(row,ensure_ascii=False)+'\n')
    print(json.dumps(row,ensure_ascii=False),flush=True)
    return row

def value(text,name):
    m=re.search(r'^\s*'+re.escape(name)+r'\s+.*?value=(-?\d+)',text,re.M)
    if not m: raise RuntimeError('Missing control '+name)
    return int(m.group(1))

def without_exposure(text):
    return re.sub(r'(^\s*exposure_time_absolute\s+.*?value=)-?\d+',r'\g<1><exposure>',text,flags=re.M)

def set_exposure(v):
    p=subprocess.run(['v4l2-ctl','-d',W,f'--set-ctrl=exposure_time_absolute={v}'],capture_output=True,text=True,timeout=8)
    event('set_control',control='exposure_time_absolute',requested=v,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
    p.check_returncode()
    read=stream.query(W)
    if value(read,'exposure_time_absolute')!=v: raise RuntimeError('Exposure readback mismatch')
    return read

def wait_checked(seconds):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        for future in futures:
            if future.done():
                raise RuntimeError('A capture worker stopped early: '+repr(future.result()))
        time.sleep(min(.25,max(0,end-time.monotonic())))

def abort(signum,frame):
    raise KeyboardInterrupt(f'Received signal {signum}')

def main():
    if (ROOT/'events.jsonl').exists(): raise RuntimeError('Refusing to overwrite previous trial')
    before={'wrist':stream.query(W),'side':stream.query(S)}
    for n,txt in before.items(): (ROOT/f'{n}-before.txt').write_text(txt)
    expected={'wrist':{'auto_exposure':1,'exposure_time_absolute':40,'white_balance_automatic':1,'saturation':25,'gamma':67},
              'side':{'auto_exposure':1,'exposure_time_absolute':40,'white_balance_automatic':0,'white_balance_temperature':3000,'saturation':110,'gamma':115}}
    for n,controls in expected.items():
        for key,v in controls.items():
            if value(before[n],key)!=v: raise RuntimeError(f'Original state changed: {n}/{key}')
    for n,fmt in [('wrist','YUYV'),('side','MJPG')]:
        if '640/480' not in before[n] or f"'{fmt}'" not in before[n]: raise RuntimeError('Unexpected format')
    # An independent recovery command, saved before any control mutation.
    (ROOT/'restore-exposure.sh').write_text('#!/bin/sh\nset -eu\nv4l2-ctl -d '+W+' --set-ctrl=exposure_time_absolute=40\nv4l2-ctl -d '+W+' --get-ctrl=exposure_time_absolute\n')
    conditions=[]
    error=None
    restore_error=None
    results=[]
    executor=ThreadPoolExecutor(2)
    signal.signal(signal.SIGTERM,abort)
    try:
        event('trial_start',authorized_sequence=[40,60,80,40],original_exposure=40,
              note='Host reception timestamps; AWB stays enabled; no format setters or robot connection.')
        for n,spec in stream.DEVICES.items(): futures.append(executor.submit(stream.capture,n,*spec))
        event('startup_begin',seconds=30)
        wait_checked(30)
        for idx,exposure in enumerate([40,60,80,40]):
            name=['e40_initial','e60','e80','e40_repeat'][idx]
            event('condition_begin',condition=name,exposure=exposure)
            read=stream.query(W) if idx==0 else set_exposure(exposure)
            if value(read,'exposure_time_absolute')!=exposure: raise RuntimeError('Unexpected exposure')
            if without_exposure(read)!=without_exposure(before['wrist']): raise RuntimeError('Other wrist control changed')
            side=stream.query(S)
            if side!=before['side']: raise RuntimeError('Side state changed')
            (ROOT/f'{name}-wrist-readback.txt').write_text(read)
            (ROOT/f'{name}-side-readback.txt').write_text(side)
            event('settle_begin',condition=name,seconds=5)
            wait_checked(5)
            start=event('record_begin',condition=name,exposure=exposure,seconds=15)
            wait_checked(15)
            end=event('record_end',condition=name,exposure=exposure)
            conditions.append(dict(name=name,exposure=exposure,start=start['monotonic'],end=end['monotonic']))
    except BaseException as exc:
        error=repr(exc)
        event('trial_error',error=error,traceback=traceback.format_exc())
    finally:
        # Restore before stopping streams, including exceptions and Ctrl+C.
        event('restore_begin',exposure=40)
        try:
            restored=set_exposure(40)
            (ROOT/'wrist-restored-readback.txt').write_text(restored)
            if restored!=before['wrist']: raise RuntimeError('Full wrist state did not restore')
            if stream.query(S)!=before['side']: raise RuntimeError('Side state differs after trial')
            event('restore_verified',exposure=40,all_controls_and_formats_equal_before=True)
        except BaseException as exc:
            restore_error=repr(exc)
            event('restore_error',error=restore_error)
        stream.STOP.set()
        executor.shutdown(wait=True)
        for future in futures:
            try: results.append(future.result())
            except BaseException as exc: results.append(dict(error=repr(exc)))
        after={}
        for n,dev in [('wrist',W),('side',S)]:
            try:
                after[n]=stream.query(dev)
                (ROOT/f'{n}-after.txt').write_text(after[n])
            except Exception as exc:
                event('after_query_error',camera=n,error=repr(exc))
        manifest=dict(created=datetime.now().astimezone().isoformat(),sequence=[40,60,80,40],
            startup_seconds=30,settle_seconds=5,record_seconds=15,conditions=conditions,
            results=results,error=error,restore_error=restore_error,
            final_state_matches={n:after.get(n)==before[n] for n in before},
            time_definition='Host reception; not hardware exposure synchronization. Use record interval host_monotonic boundaries, not legacy phase field in stream_capture metadata.',
            limitations='AWB remains enabled, no isolated AWB/exposure causality; same position A, no independent position holdout.')
        (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    if error or restore_error or len(conditions)!=4 or any(r.get('error') for r in results) or not all(manifest['final_state_matches'].values()):
        raise SystemExit('Trial incomplete; inspect manifest and restore readback.')
    print('TRIAL_COMPLETE_AND_ORIGINAL_CONTROLS_RESTORED',flush=True)

if __name__=='__main__': main()
