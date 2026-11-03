#!/usr/bin/env python3
"""Offline constrained chunk transitions; no hardware imports or robot actions.

Engineering bounds are comparisons against an off-policy recorded trajectory,
not calibrated robot safety limits. Run --infer once; --analyze reuses exact raw.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import time
import numpy as np
try:
    from tools.smolvla_offline_diagnosis import CAMERA_MAP, sha, stats, summarize
except ModuleNotFoundError:
    from smolvla_offline_diagnosis import CAMERA_MAP, sha, stats, summarize

SOURCE = Path('/data/work/so101-evidence/real-robot/smolvla-offline-continuity-20261102')
MODEL = Path('/data/work/so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/020000/pretrained_model')
STREAMS = [1101, 2202, 3303, 4404]
POLICIES = ['hard', 'blend4', 'blend6', 'project4', 'project6', 'gate4']
# Existing manually reviewed contact/approach windows, fixed before this run.
APPROACH = {('green',0):(100,140), ('green',1):(220,260),
            ('red',0):(120,140), ('red',1):(120,140)}


def noise_seed(stream, episode, request, mode):
    """Stable keyed seeds; independent across episode/request, fixed control shared."""
    key = f'{stream}' if mode == 'fixed' else f'{stream}/{episode}/{request}'
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'little') % (2**63-1)


def constrained_replay(chunks, events, state, length, policy, cap=5.):
    """Replaces queues on exact event ticks. Only the existing finite overlap blends.

    Projection clips the linear blend into the intersection of new +/-cap and
    [state-|new-state|, state+|new-state|] per body joint. It reaches raw new at
    the end of the overlap. No holding, extrapolation, delayed gripper or skips.
    Gate rejects the whole overlap if any output violates those same bounds.
    """
    if policy not in POLICIES or cap <= 0:
        raise ValueError('Invalid policy or cap')
    window = 0 if policy == 'hard' else int(policy[-1])
    if any(np.asarray(x).ndim != 2 or np.asarray(x).shape[1] != 6 or
           not np.isfinite(x).all() for x in chunks):
        raise ValueError('Nonfinite or malformed chunk')
    installs = {e['installed_tick']:(i,e) for i,e in enumerate(events)}
    if len(installs) != len(events):
        raise ValueError('Duplicate install tick')
    queue, output, windows = {}, [], []
    for tick in range(length):
        if tick in installs:
            i,e=installs[tick]; req=e['request_tick']; trim=e['trimmed']
            if trim != tick-req:
                raise ValueError('Invalid expired prefix alignment')
            new={req+k:row.copy() for k,row in enumerate(chunks[i]) if k>=trim}
            available=0
            while tick+available in queue and tick+available in new:
                available+=1
            used=min(window,available,length-tick)
            proposed=[]; projected=[]
            for j in range(used):
                t=tick+j; raw=new[t][:5]; s=state[t,:5]
                blend=(1-(j+1)/used)*queue[t][:5]+((j+1)/used)*raw
                radius=abs(raw-s)
                lo=np.maximum(raw-cap,s-radius); hi=np.minimum(raw+cap,s+radius)
                proposed.append(blend); projected.append(np.clip(blend,lo,hi))
            degraded=bool(used and np.max(np.abs(np.asarray(proposed)-projected))>1e-6)
            for j in range(used):
                if policy.startswith('project'):
                    new[tick+j][:5]=projected[j]
                elif policy.startswith('gate'):
                    if not degraded:new[tick+j][:5]=proposed[j]
                else:new[tick+j][:5]=proposed[j]
            if i:
                windows.append(dict(tick=tick,available_old=available,used_window=used,
                    end_tick=tick+max(used,1)-1,degraded=degraded if policy.startswith(('project','gate')) else False,
                    hard_fallback=used==0 or (policy.startswith('gate') and degraded)))
            queue=new
        if tick not in queue:raise ValueError(f'missing action at tick {tick}')
        output.append(queue.pop(tick))
    return np.asarray(output),windows


def lag_observations(samples, episodes, out):
    """Key anomaly: old request40/new request80; +/-100/200ms synchronized proxies."""
    import pandas as pd
    sample=samples[42]; root=Path(sample['dataset']); ep=sample['episode']
    info=json.loads((root/'meta/info.json').read_text())
    table=pd.concat([pd.read_parquet(p) for p in sorted((root/'data').rglob('*.parquet'))])
    table=table[table.episode_index==ep].sort_values('frame_index').reset_index(drop=True)
    em=pd.concat([pd.read_parquet(p) for p in (root/'meta/episodes').rglob('*.parquet')])
    em=em[em.episode_index==ep].iloc[0]
    frames=[f+d for f in [40,80] for d in [-4,-2,0,2,4]]
    arrays={f'lag{f}_observation.state':np.asarray(table.iloc[f]['observation.state'],np.float32) for f in frames}
    for cam in CAMERA_MAP:
        assert info['features'][cam]['shape']==[480,640,3]
        video=root/f'videos/{cam}/chunk-{int(em[f"videos/{cam}/chunk_index"]):03d}/file-{int(em[f"videos/{cam}/file_index"]):03d}.mp4'
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(video)]))['streams'][0]
        assert (probe['width'],probe['height'])==(640,480)
        select='+'.join(f'eq(n,{i})' for i in frames).replace(',',r'\,')
        raw=subprocess.check_output(['ffmpeg','-v','error','-c:v','libdav1d','-i',str(video),'-vf','select='+select,'-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
        images=np.frombuffer(raw,np.uint8).reshape(-1,480,640,3);assert len(images)==len(frames)
        for f,image in zip(frames,images):arrays[f'lag{f}_{cam}']=image.transpose(2,0,1).astype(np.float32)/255
    np.savez_compressed(out/'lag-observations.npz',**arrays)
    return arrays


def infer(source, out):
    import torch
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
    from lerobot.policies import make_pre_post_processors
    samples=json.loads((source/'samples.json').read_text()); episodes=json.loads((source/'episodes.json').read_text())
    # Dimension metadata checked before reading frozen image arrays. No display.
    assert all(s['image_shape_hwc']==[480,640,3] for s in samples)
    observations=np.load(source/'observations.npz');lag=lag_observations(samples,episodes,out)
    torch.set_num_threads(4)
    cfg=PreTrainedConfig.from_pretrained(MODEL,local_files_only=True); cfg.device='cuda';cfg.load_vlm_weights=False
    model=SmolVLAPolicy.from_pretrained(MODEL,config=cfg,local_files_only=True,strict=True).eval().cuda()
    pre,post=make_pre_post_processors(policy_cfg=cfg,pretrained_path=str(MODEL),preprocessor_overrides={'device_processor':{'device':'cuda'},'rename_observations_processor':{'rename_map':CAMERA_MAP}})
    manifest=dict(model=str(MODEL.resolve()),files={p.name:sha(p) for p in MODEL.iterdir() if p.is_file()},config=asdict(cfg),camera_map=CAMERA_MAP,streams=STREAMS,design_streams=STREAMS[:2],heldout_streams=STREAMS[2:],cap=5,policies=POLICIES,noise='CPU Gaussian keyed sha256(stream/episode/request); fixed mode sha256(stream). Same raw across all candidate policies.',source={p:sha(source/p) for p in ['episodes.json','samples.json','observations.npz','raw-predictions.npz']})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,default=str))
    predictions={};noises={};timings=[]
    def predict(obs,color,noise):
        model.reset();pre.reset();post.reset()
        batch=pre({k:torch.from_numpy(obs[k].copy()) for k in ['observation.state',*CAMERA_MAP]}|{'task':f'Put the {color} cube into the paper bowl'})
        torch.cuda.synchronize();t=time.perf_counter()
        with torch.inference_mode():a=post(model.predict_action_chunk(batch,noise=noise.cuda().clone()))[0].cpu().numpy()
        torch.cuda.synchronize();timings.append(time.perf_counter()-t)
        assert a.shape==(50,6) and np.isfinite(a).all()
        return a
    def noise(seed):return torch.randn((1,cfg.chunk_size,cfg.max_action_dim),generator=torch.Generator(device='cpu').manual_seed(seed))
    for mode in ['fixed','independent']:
        for stream in STREAMS:
            for ei,e in enumerate(episodes):
                for ri,sid in enumerate(e['sample_ids']):
                    key=f'{mode}_{stream}_e{ei}_r{ri}';n=noise(noise_seed(stream,ei,ri,mode));noises[key]=n.numpy()
                    obs={k:observations[f's{sid}_{k}'] for k in ['observation.state',*CAMERA_MAP]}
                    predictions[key]=predict(obs,e['color'],n)
            print(f'{mode} stream {stream}: {len(predictions)} chunks',flush=True)
    # Paired observation-shift sensitivity, synchronized state+images, exact same
    # chunk positions req40/req80; changes only input frame, not queue alignment.
    for stream in [1000,1101,2202,3303,4404]:
        for req,ri in [(40,1),(80,2)]:
            for mode in ['fixed','independent']:
                # original seed1000 reproduces legacy noise exactly
                n=noise(1000 if stream==1000 else noise_seed(stream,3,ri,mode))
                for delta in [-4,-2,0,2,4]:
                    key=f'lag_{mode}_{stream}_q{req}_d{delta}'
                    predictions[key]=predict({k:lag[f'lag{req+delta}_{k}'] for k in ['observation.state',*CAMERA_MAP]},'red',n)
    # Repeat an independent request with same saved noise and input.
    key='independent_1101_e0_r0';sid=episodes[0]['sample_ids'][0]
    repeat=predict({k:observations[f's{sid}_{k}'] for k in ['observation.state',*CAMERA_MAP]},'green',torch.from_numpy(noises[key]))
    np.savez_compressed(out/'raw-predictions.npz',**predictions);np.savez_compressed(out/'noise.npz',**noises)
    (out/'inference.json').write_text(json.dumps(dict(chunks=len(predictions),timing_seconds=stats(timings),repeat_maxdiff=float(abs(repeat-predictions[key]).max()),gpu=torch.cuda.get_device_name(),hardware_access=False),indent=2))


def pool_sequences(records, sequences, episodes, legacy):
    pooled={}
    metrics=['full_d1','full_d2','boundary_d1','boundary_d2','end_d1','end_d2','near10_d1','near10_d2','new_deviation','state_deviation','previous_deviation','state_excess','recorded_action_deviation','approach_d1','approach_d2']
    for mode in ['fixed','independent']:
        for split, streams in [('design',STREAMS[:2]),('heldout',STREAMS[2:]),('all',STREAMS)]:
            for policy in POLICIES:
                buffers={k:[] for k in metrics};rows=[r for r in records if r['mode']==mode and r['stream'] in streams and r['policy']==policy]
                for r in rows:
                    e=episodes[r['episode']];a=sequences[r['key']];hard=sequences[r['base']+'_hard'];state=legacy[f'e{r["episode"]}_recorded_state'];record=legacy[f'e{r["episode"]}_recorded_action']
                    t1=np.arange(1,len(a));t2=np.arange(2,len(a));bs=np.asarray([v['installed_tick'] for v in e['events'][1:]]);ends=np.asarray([v['end_tick'] for v in r['transitions']])
                    d1=abs(np.diff(a[:,:5],axis=0)).max(1);d2=abs(np.diff(a[:,:5],axis=0,n=2)).max(1)
                    lo,hi=APPROACH[(e['color'],e['episode'])]
                    vals=dict(approach_d1=d1[(t1>=lo)&(t1<=hi)],approach_d2=d2[(t2>=lo)&(t2<=hi)],full_d1=d1,full_d2=d2,boundary_d1=d1[np.isin(t1,bs)],boundary_d2=d2[np.isin(t2,bs)|np.isin(t2-1,bs)],end_d1=d1[np.isin(t1,ends)|np.isin(t1,ends+1)],end_d2=d2[np.isin(t2,ends)|np.isin(t2,ends+1)|np.isin(t2,ends+2)],near10_d1=d1[np.min(abs(t1[:,None]-bs),axis=1)<=10],near10_d2=d2[np.min(abs(t2[:,None]-bs),axis=1)<=10],new_deviation=abs(a[:,:5]-hard[:,:5]).max(1),state_deviation=abs(a[:,:5]-state[:,:5]).max(1),previous_deviation=d1,state_excess=(abs(a[:,:5]-state[:,:5])-abs(hard[:,:5]-state[:,:5])).max(1),recorded_action_deviation=abs(a[:,:5]-record[:,:5]).max(1))
                    for k,v in vals.items():buffers[k].extend(v.tolist())
                pooled[f'{mode}_{split}_{policy}']={k:stats(v) for k,v in buffers.items()}|dict(transitions=sum(len(r['transitions']) for r in rows),degraded=sum(v['degraded'] for r in rows for v in r['transitions']),hard_fallback=sum(v['hard_fallback'] for r in rows for v in r['transitions']),gripper_exact=all(r['gripper_exact'] for r in rows),max_per_sequence_body_mae_new=max(r['deviation_hard_body_mae'] for r in rows))
    return pooled


def audit_chunks(chunks, e, state, recorded, label):
    hard,_=constrained_replay(chunks,e['events'],state,e['length'],'hard');rows=[]
    for ci,event in enumerate(e['events'][1:],1):
        tick=event['installed_tick'];oldstart=tick-e['events'][ci-1]['request_tick'];newstart=event['trimmed'];old=chunks[ci-1][oldstart:];new=chunks[ci][newstart:];n=min(len(old),len(new),len(state)-tick)
        if not n:continue
        ss=state[tick:tick+n];rr=recorded[tick:tick+n]
        # All raw arrays and preceding emitted targets retained for each boundary.
        divergence=abs(old[:n,:5]-new[:n,:5]);j=int(divergence[0].argmax())
        close=np.flatnonzero(np.diff(recorded[:,5]>15)!=0)+1
        phase='gripper-edge-proxy' if len(close) and min(abs(close-tick))<=20 else 'other'
        rows.append(dict(label=label,request=ci,tick=tick,request_tick=event['request_tick'],old_request_tick=e['events'][ci-1]['request_tick'],remaining_old=n,phase=phase,in_reviewed_approach=APPROACH[(e['color'],e['episode'])][0]<=tick<=APPROACH[(e['color'],e['episode'])][1],old_request_state=state[e['events'][ci-1]['request_tick']].tolist(),old_prediction_first=chunks[ci-1][0].tolist(),nearest_recorded_gripper_edge=int(close[np.argmin(abs(close-tick))]) if len(close) else None,old_new_first_max=float(divergence[0].max()),old_new_overlap_max=float(divergence.max()),old_state_first_max=float(abs(old[0,:5]-ss[0,:5]).max()),new_state_first_max=float(abs(new[0,:5]-ss[0,:5]).max()),old_recorded_action_first_max=float(abs(old[0,:5]-rr[0,:5]).max()),new_recorded_action_first_max=float(abs(new[0,:5]-rr[0,:5]).max()),hard_boundary_d1=float(abs(hard[tick,:5]-hard[tick-1,:5]).max()),joint_max_first=j,old_future=old[:n].tolist(),new_future=new[:n].tolist(),recorded_state=ss.tolist(),recorded_action=rr.tolist(),previous_emitted=hard[max(0,tick-2):tick].tolist(),old_chunk_prediction_at_previous_tick=chunks[ci-1][oldstart-1].tolist()))
    return rows


def analyze(source,out):
    episodes=json.loads((source/'episodes.json').read_text());legacy=np.load(source/'replay-sequences.npz');oldraw=np.load(source/'raw-predictions.npz');raw=np.load(out/'raw-predictions.npz')
    audit=[];records=[];sequences={};replay_times=[]
    for ei,e in enumerate(episodes):
        state=legacy[f'e{ei}_recorded_state']; recorded=legacy[f'e{ei}_recorded_action']
        for seed in [1000,2000,3000]:
            chunks=[oldraw[f'020000_s{sid}_{e["color"]}_{seed}'] for sid in e['sample_ids']]
            audit+=audit_chunks(chunks,e,state,recorded,f'legacy_e{ei}_{seed}')
        for mode in ['fixed','independent']:
            for stream in STREAMS:
                base=f'{mode}_{stream}_e{ei}';chunks=[raw[f'{base}_r{ri}'] for ri in range(len(e['events']))]
                audit+=audit_chunks(chunks,e,state,recorded,base)
                hard,_=constrained_replay(chunks,e['events'],state,e['length'],'hard')
                for policy in POLICIES:
                    t=time.perf_counter();a,w=constrained_replay(chunks,e['events'],state,e['length'],policy);replay_times.append(time.perf_counter()-t)
                    key=f'{base}_{policy}';sequences[key]=a
                    records.append(dict(key=key,base=base,mode=mode,stream=stream,episode=ei,policy=policy,transitions=w,gripper_exact=bool(np.array_equal(a[:,5],hard[:,5])),length=len(a),missing_actions=0,**summarize(a,state,hard,[v['installed_tick'] for v in e['events'][1:]],[v['end_tick'] for v in w])))
    lag=[]
    zero_shift_diffs=[]
    for mode in ['fixed','independent']:
        for stream in [1000,*STREAMS]:
            for req in [40,80]:
                baseline=raw[f'lag_{mode}_{stream}_q{req}_d0']
                reference=oldraw[f'020000_s{41 if req==40 else 42}_red_1000'] if stream==1000 else raw[f'{mode}_{stream}_e3_r{1 if req==40 else 2}']
                zero_shift_diffs.append(float(abs(baseline-reference).max()))
                for delta in [-4,-2,0,2,4]:
                    a=raw[f'lag_{mode}_{stream}_q{req}_d{delta}'];idx=84-req
                    lag.append(dict(mode=mode,stream=stream,request_tick=req,delta_ticks=delta,aligned_shoulder_lift=float(a[idx,1]),aligned_body_difference_from_delta0_max=float(abs(a[idx,:5]-baseline[idx,:5]).max()),chunk_body_difference_from_delta0_mae=float(abs(a[:,:5]-baseline[:,:5]).mean())))
    pooled=pool_sequences(records,sequences,episodes,legacy)
    # Frozen acceptance: robust across each heldout sequence, not just pooled.
    acceptance={}
    for policy in ['project4','project6','gate4']:
        failures=[]
        for r in records:
            if r['policy']!=policy or r['stream'] not in STREAMS[2:]:continue
            h=next(h for h in records if h['base']==r['base'] and h['policy']=='hard')
            for metric in ['full_d2','boundary_d2','transition_end_d2']:
                for quantile in ['p95','max']:
                    if r[metric][quantile]>h[metric][quantile]+1e-5:failures.append(dict(sequence=r['key'],metric=metric,quantile=quantile,candidate=r[metric][quantile],hard=h[metric][quantile]))
            if r['deviation_hard_body_max']>5.0001:failures.append(dict(sequence=r['key'],metric='new_cap'))
        # A retained >30deg hard-fallback step is a stop signal, not safety proof.
        fallback_spikes=[]
        for r in records:
            if r['policy']!=policy or r['stream'] not in STREAMS[2:]:continue
            a=sequences[r['key']]
            for w in r['transitions']:
                t=w['tick'];d=float(abs(a[t,:5]-a[t-1,:5]).max())
                if w['degraded'] and d>30:fallback_spikes.append(dict(sequence=r['key'],tick=t,d1=d,degraded=w['degraded'],hard_fallback=w['hard_fallback']))
        acceptance[policy]=dict(passed=not failures and not fallback_spikes,failures=failures,degraded_boundary_spikes_gt30=fallback_spikes)
    np.savez_compressed(out/'replay-sequences.npz',**sequences)
    for name,data in [('boundary-audit',audit),('sequence-metrics',records),('pooled-metrics',pooled),('lag-sensitivity',lag),('acceptance',acceptance)]:
        (out/f'{name}.json').write_text(json.dumps(data,indent=2))
    (out/'verification.json').write_text(json.dumps(dict(raw_sha256=sha(out/'raw-predictions.npz'),noise_sha256=sha(out/'noise.npz'),zero_shift_redecode_maxdiff=max(zero_shift_diffs),all_gripper_exact=all(r['gripper_exact'] for r in records),sequences=len(records),missing_actions=0,replay_seconds=stats(replay_times),runtime_changed=False,hardware_access=False,limits='Recorded observations are off-policy. State constraint uses per-tick recorded state as ideal fresh-state proxy. Gripper edges are not annotated grasp/contact events. +/-2/4 synchronized shifts measure input sensitivity, not causal attribution or measured camera latency.'),indent=2))
    print(json.dumps({p:{'passed':v['passed'],'metric_failures':len(v['failures']),'degraded_spikes':len(v['degraded_boundary_spikes_gt30'])} for p,v in acceptance.items()},indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=SOURCE);p.add_argument('--output',type=Path,required=True);p.add_argument('--infer',action='store_true');p.add_argument('--analyze',action='store_true');a=p.parse_args()
    if a.infer:a.output.mkdir(parents=True,exist_ok=False);infer(a.source,a.output)
    if a.analyze:analyze(a.source,a.output)

if __name__=='__main__':main()
