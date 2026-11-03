#!/usr/bin/env python3
"""Actual hard backend diagnostics on frozen recordings, never hardware.

Verifies model-owned noise capture preserves exact outputs/RNG, runs 20Hz,
and replays every recorded inference and all installed/emitted CPU queues.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import time
from types import SimpleNamespace
import numpy as np

SOURCE=Path('/data/work/so101-evidence/real-robot/smolvla-offline-continuity-20261102')
MODEL=Path('/data/work/so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/020000/pretrained_model')


def load_records(path):
    records=[]
    for f in sorted(path.glob('*.npz')):
        with np.load(f,allow_pickle=False) as z:meta=json.loads(str(z['metadata']))
        records.append((f.name.split('-',1)[1][:-4],meta,f))
    return records


def verify_queue(path):
    queue={};generation=0;installs=0;outputs=0;stale=0
    for kind,m,f in load_records(path):
        if kind=='reset':queue={};generation=m['generation']
        elif kind=='stale':stale+=1
        elif kind=='install':
            assert m['generation']==generation
            tick=m['tick'];queue={k:v for k,v in queue.items() if k>=tick}
            assert {int(k):v for k,v in m['old_future'].items()}==queue
            if m['replaced']:queue={int(k):v for k,v in m['new_future'].items()}
            installs+=1
        elif kind=='output':
            assert m['generation']==generation
            tick=m['tick'];queue={k:v for k,v in queue.items() if k>=tick}
            assert queue.pop(tick)==m['action'];outputs+=1
    status=json.loads((path/'status.json').read_text());assert status['complete']
    return dict(installs=installs,outputs=outputs,stale=stale,complete=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--ticks-per-color',type=int,default=160);args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    assert args.ticks_per_color>=120
    import torch
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies import make_pre_post_processors
    from lerobot.rollout.context import _load_pretrained_policy
    from so101_rollout.smolvla.async_engine import Request
    from so101_rollout.smolvla.recording import restore_tree
    from so101_rollout.smolvla.rollout import SO101AsyncConfig,create_async_engine
    torch.set_num_threads(4)
    cfg=PreTrainedConfig.from_pretrained(MODEL,local_files_only=True);cfg.pretrained_path=MODEL;cfg.device='cuda'
    policy=_load_pretrained_policy(cfg).cuda().eval()
    camera={'observation.images.wrist':'observation.images.camera1','observation.images.side':'observation.images.camera2'}
    pre,post=make_pre_post_processors(policy_cfg=cfg,pretrained_path=str(MODEL),preprocessor_overrides={'device_processor':{'device':'cuda'},'rename_observations_processor':{'rename_map':camera}})
    samples=json.loads((SOURCE/'samples.json').read_text());assert all(s['image_shape_hwc']==[480,640,3] for s in samples)
    archive=np.load(SOURCE/'observations.npz');observations={}
    for color,sid in [('green',0),('red',40)]:
        observations[color]={'observation.state':archive[f's{sid}_observation.state'].copy()}
        for k in camera:observations[color][k]=archive[f's{sid}_{k}'].transpose(1,2,0).copy()
    info=json.loads((Path(samples[0]['dataset'])/'meta/info.json').read_text())
    def engine(recording_path=None):
        return create_async_engine(SO101AsyncConfig(recording_path=str(recording_path) if recording_path else None,telemetry_path=str(recording_path.parent/(recording_path.name+'-telemetry.json')) if recording_path else None),policy=policy,preprocessor=pre,postprocessor=post,dataset_features=info['features'],ordered_action_keys=info['features']['action']['names'],task='Put the green cube into the paper bowl',device='cuda',robot_wrapper=SimpleNamespace(robot_type='so101_follower'),fps=20,use_torch_compile=False)
    # Direct infer comparison isolates numeric/RNG semantics from wall scheduling.
    values=[];rng=[]
    for enabled in [False,True]:
        e=engine(out/'equivalence' if enabled else None)
        torch.manual_seed(123456)
        req=Request(0,0,0,time.perf_counter(),deepcopy(observations['green']),'Put the green cube into the paper bowl')
        values.append(np.asarray(e._infer(req)))
        rng.append((torch.get_rng_state().clone(),torch.cuda.get_rng_state().clone()))
        e.stop()
    np.testing.assert_array_equal(values[0],values[1]);assert all(torch.equal(a,b) for a,b in zip(*rng))
    np.savez_compressed(out/'equivalence-outputs.npz',plain=values[0],recorded=values[1])
    e=engine(out/'smoke');phases={};e.start()
    def ready_action(color):
        start=time.perf_counter()
        while True:
            a=e.get_action(observations[color])
            if a is not None:return time.perf_counter()-start
            assert time.perf_counter()-start<30
            time.sleep(.01)
    try:
        for color in ['green','red']:
            e.reset(task=f'Put the {color} cube into the paper bowl');e.resume();wait=ready_action(color);epoch=time.perf_counter();calls=[];missed=0
            for t in range(1,args.ticks_per_color):
                time.sleep(max(0,epoch+t*.05-time.perf_counter()))
                start=time.perf_counter();a=e.get_action(observations[color]);calls.append((time.perf_counter()-start)*1000)
                missed+=a is None
                if a is not None:assert tuple(a.shape)==(6,) and torch.isfinite(a).all()
            phases[color]=dict(ticks=args.ticks_per_color,startup_wait_s=wait,missing=missed,control_ms_p95=float(np.quantile(calls,.95)),control_ms_max=float(max(calls)))
            e.pause()
        # A running old-generation request must be captured but never installed.
        e.reset(task='Put the red cube into the paper bowl');e.resume()
        deadline=time.perf_counter()+20
        while e._future is not None:
            e.get_action(None);time.sleep(.01);assert time.perf_counter()<deadline
        assert e.get_action(observations['red']) is None
        while not e._future.running():time.sleep(.001);assert time.perf_counter()<deadline
        old=e._request.identifier;e.pause();e.reset(task='Put the green cube into the paper bowl');e.resume()
        while not e.result_ready:time.sleep(.01);assert time.perf_counter()<deadline
        assert e.get_action(None) is None
        ready_action('green');e.pause()
        barrier=dict(stale_request=old,stale_results=e.stats['stale_results'],passed=e.stats['stale_results']>=1)
    finally:e.stop()
    queue_verification=verify_queue(out/'smoke')
    # Recover exact tensor bytes; replay each completed chunk with captured noise.
    maxdiff=[];observed=0;inferred=0
    for path in [out/'equivalence',out/'smoke']:
        for kind,m,f in load_records(path):
            if kind=='observation':
                schema=m['schema'];assert all(schema['items'][k]['shape']==[480,640,3] for k in camera)
                with np.load(f,allow_pickle=False) as z:obs=restore_tree(schema,z)
                assert obs['observation.state'].shape==(6,);observed+=1
            if kind!='inference':continue
            with np.load(f,allow_pickle=False) as z:payload=restore_tree(m['schema'],z,'cuda')
            policy.reset();post.reset()
            with torch.inference_mode():repeated=post(policy.predict_action_chunk(payload['model_input'],noise=payload['noise']))
            torch.cuda.synchronize();diff=float((repeated.cpu()-payload['raw_actions'].cpu()).abs().max());maxdiff.append(diff);inferred+=1
    assert max(maxdiff)==0
    report=dict(passed=all(p['missing']==0 for p in phases.values()) and barrier['passed'] and e.stats['skipped_ticks']==0,hardware_access=False,control='original hard replacement, original random sampling',exact_outputs_with_recording=True,cpu_cuda_rng_equal=True,phase_results=phases,barrier=barrier,queue_verification=queue_verification,inferences_replayed=inferred,observations_saved=observed,replay_maxdiff=max(maxdiff),stats=e.stats,limits='No camera exposure timestamps measured; saved observations are exact dispatch snapshots from recordings. No camera, serial or physical actions.')
    (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));assert report['passed']

if __name__=='__main__':main()
