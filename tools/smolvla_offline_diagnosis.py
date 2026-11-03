#!/usr/bin/env python3
"""Recorded-observation diagnosis and chunk overlap replay. Never imports hardware.

Run in the SmolVLA environment with HF_HUB_OFFLINE=1, HF_HOME set to local cache.
No scheduler is reused: reset/generation behavior in real runtime is not tested.
"""
from __future__ import annotations
import argparse
import gc
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import time
import numpy as np

SEEDS = [1000, 2000, 3000]
CAMERA_MAP = {'observation.images.wrist': 'observation.images.camera1',
              'observation.images.side': 'observation.images.camera2'}
BASE = Path('/data/work')
EVIDENCE = BASE / 'so101-evidence/real-robot'


def replay(chunks, events, length, window):
    """Absolute tick keyed future queue. Blend only available old predictions.

    Linear new weight (j+1)/W reaches one at final overlap tick. If old future
    has fewer than W contiguous samples, shorten W; never hold/extrapolate it.
    Raw gripper comes directly from new chunk, including inside overlap.
    """
    queue, output, windows = {}, [], []
    installs = {e['installed_tick']: (i, e) for i, e in enumerate(events)}
    if len(installs) != len(events):
        raise ValueError('Duplicate install tick')
    for tick in range(length):
        if tick in installs:
            i, e = installs[tick]
            req, trimmed = e['request_tick'], e['trimmed']
            if trimmed != tick - req:
                raise ValueError('Invalid expired prefix alignment')
            new = {req + k: row.copy() for k, row in enumerate(chunks[i]) if k >= trimmed}
            available = 0
            while tick + available in queue and tick + available in new:
                available += 1
            used = min(window, available)
            if i:
                windows.append(dict(tick=tick, available_old=available, requested_window=window,
                                    used_window=used, end_tick=tick + max(used, 1) - 1))
            for j in range(used):
                alpha = (j + 1) / used
                new[tick+j][:5] = (1-alpha)*queue[tick+j][:5] + alpha*new[tick+j][:5]
            queue = new
        if tick not in queue:
            raise ValueError(f'missing action at tick {tick}')
        output.append(queue.pop(tick))
    return np.asarray(output), windows


def stats(x):
    x = np.asarray(x)
    return dict(count=int(x.size), mean=float(x.mean()), p50=float(np.quantile(x,.5)),
                p95=float(np.quantile(x,.95)), p99=float(np.quantile(x,.99)), max=float(x.max())) if x.size else dict(count=0)


def summarize(a, state, hard, boundaries, ends):
    d1 = np.abs(np.diff(a[:, :5], axis=0)).max(1)
    d2 = np.abs(np.diff(a[:, :5], n=2, axis=0)).max(1)
    t1, t2 = np.arange(1,len(a)), np.arange(2,len(a))
    b1 = np.isin(t1,boundaries)
    b2 = np.isin(t2,boundaries) | np.isin(t2-1,boundaries)
    near = np.array([any(abs(t-b)<=10 for b in boundaries) for t in t1])
    # Include last transition sample and first subsequent raw sample.
    endmask = np.isin(t1,ends) | np.isin(t1,np.asarray(ends)+1)
    end2 = np.isin(t2,ends) | np.isin(t2,np.asarray(ends)+1) | np.isin(t2,np.asarray(ends)+2)
    near2 = np.array([any(abs(t-b)<=10 for b in boundaries) for t in t2])
    return dict(full_d1=stats(d1), full_d2=stats(d2), boundary_d1=stats(d1[b1]),
                boundary_d2=stats(d2[b2]), within_d1=stats(d1[~b1]), within_d2=stats(d2[~b2]),
                boundary_plusminus10_d1=stats(d1[near]), transition_end_d1=stats(d1[endmask]),
                transition_end_d2=stats(d2[end2]), boundary_plusminus10_d2=stats(d2[near2]),
                deviation_hard_body_mae=float(np.abs(a[:,:5]-hard[:,:5]).mean()),
                deviation_hard_body_max=float(np.abs(a[:,:5]-hard[:,:5]).max()),
                recorded_state_body_mae=float(np.abs(a[:,:5]-state[:,:5]).mean()),
                gripper_max_difference_hard=float(np.abs(a[:,5]-hard[:,5]).max()),
                gripper_threshold15_edges=int(np.count_nonzero(np.diff(a[:,5]>15))))


def pooled_metrics(sequences, episodes, windows):
    """Pool individual samples; never average quantiles from separate runs."""
    result = {}
    for w in [0, 4, 6]:
        buf = {k: [] for k in ['boundary_d1', 'boundary_d2', 'near10_d1', 'near10_d2',
                               'full_d2', 'end_d1', 'end_d2', 'within_d2']}
        for ei, episode in enumerate(episodes):
            bs = np.array([e['installed_tick'] for e in episode['events'][1:]])
            for seed in SEEDS:
                x = sequences[f'e{ei}_{seed}_w{w}']
                t1, t2 = np.arange(1, len(x)), np.arange(2, len(x))
                d1 = abs(np.diff(x[:, :5], axis=0)).max(1)
                d2 = abs(np.diff(x[:, :5], n=2, axis=0)).max(1)
                ends = np.array([v['end_tick'] for v in next(z for z in windows if
                    z['episode'] == ei and z['seed'] == seed and z['window'] == w)['transitions']])
                boundary2 = np.isin(t2, bs) | np.isin(t2-1, bs)
                values = dict(boundary_d1=d1[np.isin(t1, bs)], boundary_d2=d2[boundary2],
                    near10_d1=d1[np.min(abs(t1[:, None]-bs), axis=1) <= 10],
                    near10_d2=d2[np.min(abs(t2[:, None]-bs), axis=1) <= 10], full_d2=d2,
                    within_d2=d2[~boundary2], end_d1=d1[np.isin(t1, ends) | np.isin(t1, ends+1)],
                    end_d2=d2[np.isin(t2, ends) | np.isin(t2, ends+1) | np.isin(t2, ends+2)])
                for k, v in values.items():
                    buf[k].extend(v.tolist())
        result[w] = {k: stats(v) for k, v in buf.items()}
    return result


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''): h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args=p.parse_args(); out=args.output
    out.mkdir(parents=True, exist_ok=False)
    import pandas as pd
    import torch
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
    from lerobot.policies import make_pre_post_processors
    torch.set_num_threads(4)
    start=time.perf_counter()
    source_metrics=json.loads((EVIDENCE/'smolvla-four-rollout-analysis-20261102/numeric/metrics.json').read_text())[:4]
    samples=[]; episodes=[]; obs_arrays={}; manifests={}; predictions={}; noises={}; timings=[]
    approach={('green',0):100,('green',1):220,('red',0):120,('red',1):120}
    for m in source_metrics:
        root=BASE/'so101-datasets'/m['dataset']; ep=m['episode_index']; color='green' if '-green-' in root.name else 'red'
        info=json.loads((root/'meta/info.json').read_text())
        table=pd.concat([pd.read_parquet(q) for q in sorted((root/'data').rglob('*.parquet'))],ignore_index=True)
        table=table[table.episode_index==ep].sort_values('frame_index').reset_index(drop=True)
        em=pd.concat([pd.read_parquet(q) for q in (root/'meta/episodes').rglob('*.parquet')]); em=em[em.episode_index==ep].iloc[0]
        tele=Path(m['telemetry']['source'])/'async-telemetry.json'; tx=json.loads(tele.read_text()); events=[e for e in tx['events'] if e['type']=='chunk']
        frames=sorted(set([0,approach[(color,ep)]]+[e['request_tick'] for e in events]))
        decoded={}
        for cam in CAMERA_MAP:
            assert info['features'][cam]['shape']==[480,640,3]
            c=int(em[f'videos/{cam}/chunk_index']); f=int(em[f'videos/{cam}/file_index'])
            video=root/f'videos/{cam}/chunk-{c:03d}/file-{f:03d}.mp4'
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(video)]))['streams'][0]
            assert (probe['width'],probe['height'])==(640,480) # before decode
            select='+'.join(f'eq(n,{i})' for i in frames)
            raw=subprocess.check_output(['ffmpeg','-v','error','-c:v','libdav1d','-i',str(video),'-vf',f'select={select.replace(",", chr(92)+",")}', '-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
            images=np.frombuffer(raw,np.uint8).reshape(-1,480,640,3); assert len(images)==len(frames)
            decoded[cam]=dict(zip(frames,images))
        ids={}
        for frame in frames:
            sid=len(samples); row=table.iloc[frame]; ids[frame]=sid
            obs={'observation.state':np.asarray(row['observation.state'],np.float32)}
            for cam in CAMERA_MAP: obs[cam]=decoded[cam][frame].transpose(2,0,1).astype(np.float32)/255
            for k,v in obs.items(): obs_arrays[f's{sid}_{k}']=v
            samples.append(dict(id=sid,dataset=str(root),episode=ep,frame_index=frame,global_index=int(row['index']),
                                source_color=color,layout='G C2/R C3' if ep==0 else 'R C2/G C3',
                                phases=[x for x,test in [('initial',frame==0),('approach',frame==approach[(color,ep)])] if test],
                                image_shape_hwc=[480,640,3]))
        episodes.append(dict(color=color,episode=ep,length=len(table),telemetry=str(tele),telemetry_sha256=sha(tele),events=events,sample_ids=[ids[e['request_tick']] for e in events],
                             state=np.stack(table['observation.state']),recorded_action=np.stack(table.action)))
    np.savez_compressed(out/'observations.npz',**obs_arrays)
    (out/'samples.json').write_text(json.dumps(samples,indent=2))
    (out/'episodes.json').write_text(json.dumps([{k:v for k,v in e.items() if k not in ('state','recorded_action')} for e in episodes],indent=2))
    print(f'Decoded {len(samples)} exact observations in {time.perf_counter()-start:.1f}s',flush=True)
    for step in ['015000','020000']:
        path=BASE/f'so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/{step}/pretrained_model'
        cfg=PreTrainedConfig.from_pretrained(path,local_files_only=True); cfg.device='cuda'; cfg.load_vlm_weights=False
        model=SmolVLAPolicy.from_pretrained(path,config=cfg,local_files_only=True,strict=True).eval().cuda()
        pre,post=make_pre_post_processors(policy_cfg=cfg,pretrained_path=str(path),preprocessor_overrides={'device_processor':{'device':'cuda'},'rename_observations_processor':{'rename_map':CAMERA_MAP}})
        manifests[step]=dict(path=str(path.resolve()),files={q.name:sha(q) for q in path.iterdir() if q.is_file()},config=asdict(cfg),camera_map=CAMERA_MAP)
        for seed in SEEDS:
            g=torch.Generator(device='cpu').manual_seed(seed)
            noise=torch.randn((1,cfg.chunk_size,cfg.max_action_dim),generator=g)
            noises[f'{step}_{seed}']=noise.numpy(); n=noise.cuda()
            for s in samples:
                colors=['green','red'] if s['phases'] else ([s['source_color']] if step=='020000' else [])
                for color in colors:
                    model.reset();pre.reset();post.reset()
                    batch=pre({k:torch.from_numpy(obs_arrays[f's{s["id"]}_{k}'].copy()) for k in ['observation.state',*CAMERA_MAP]} | {'task':f'Put the {color} cube into the paper bowl'})
                    torch.cuda.synchronize(); t=time.perf_counter()
                    with torch.inference_mode(): a=post(model.predict_action_chunk(batch,noise=n.clone()))[0].cpu().numpy()
                    torch.cuda.synchronize(); timings.append(time.perf_counter()-t)
                    assert a.shape==(50,6) and np.isfinite(a).all()
                    predictions[f'{step}_s{s["id"]}_{color}_{seed}']=a
                    if step=='020000' and seed==SEEDS[0] and s['id']==0 and color=='green':
                        model.reset(); pre.reset();post.reset()
                        with torch.inference_mode(): repeat=post(model.predict_action_chunk(batch,noise=n.clone()))[0].cpu().numpy()
                        manifests[step]['repeat_same_noise_maxdiff']=float(np.abs(a-repeat).max())
            print(f'Predicted {step} seed {seed}, total chunks {len(predictions)}',flush=True)
        np.savez_compressed(out/'raw-predictions.npz',**predictions)
        np.savez_compressed(out/'initial-noise.npz',**noises)
        (out/'model-manifest.json').write_text(json.dumps(manifests,indent=2,default=str))
        del model,pre,post;gc.collect();torch.cuda.empty_cache()
    rows=[]; sequence_arrays={}; overlaps={}; windows_all=[]
    for ei,e in enumerate(episodes):
        for seed in SEEDS:
            chunks=[predictions[f'020000_s{i}_{e["color"]}_{seed}'] for i in e['sample_ids']]
            hard,_=replay(chunks,e['events'],e['length'],0)
            boundaries=[x['installed_tick'] for x in e['events'][1:]]
            for ci,event in enumerate(e['events'][1:],1):
                tick=event['installed_tick']; oldevent=e['events'][ci-1]
                oldstart=tick-oldevent['request_tick']; newstart=event['trimmed']
                overlaps[f'e{ei}_{seed}_b{ci}_old']=chunks[ci-1][oldstart:]
                overlaps[f'e{ei}_{seed}_b{ci}_new']=chunks[ci][newstart:]
            for w in [0,4,6]:
                t=time.perf_counter();a,windows=replay(chunks,e['events'],e['length'],w);elapsed=time.perf_counter()-t
                sequence_arrays[f'e{ei}_{seed}_w{w}']=a
                rows.append(dict(episode=ei,color=e['color'],source_episode=e['episode'],seed=seed,window=w,replay_ms=elapsed*1000,
                                 recorded_action_body_mae=float(abs(a[:,:5]-e['recorded_action'][:,:5]).mean()),
                                 **summarize(a,e['state'],hard,boundaries,[x['end_tick'] for x in windows])))
                windows_all.append(dict(episode=ei,seed=seed,window=w,transitions=windows))
            sequence_arrays[f'e{ei}_recorded_state']=e['state']; sequence_arrays[f'e{ei}_recorded_action']=e['recorded_action']
    np.savez_compressed(out/'replay-sequences.npz',**sequence_arrays);np.savez_compressed(out/'old-new-overlaps.npz',**overlaps)
    (out/'pooled-metrics.json').write_text(json.dumps(pooled_metrics(sequence_arrays,episodes,windows_all),indent=2))
    (out/'continuity-metrics.json').write_text(json.dumps(rows,indent=2));(out/'transition-windows.json').write_text(json.dumps(windows_all,indent=2))
    language=[]
    for s in samples:
        if not s['phases']:continue
        for step in manifests:
            green=np.stack([predictions[f'{step}_s{s["id"]}_green_{seed}'] for seed in SEEDS]);red=np.stack([predictions[f'{step}_s{s["id"]}_red_{seed}'] for seed in SEEDS])
            language.append(dict(sample=s['id'],checkpoint=step,paired_language_body_mae=float(abs(green[:,:,:5]-red[:,:,:5]).mean()),
                                 seed_body_pairwise_mae=float(np.mean([abs(x[i,:,:5]-x[j,:,:5]).mean() for x in [green,red] for i,j in [(0,1),(0,2),(1,2)]])),
                                 green_pan_last10_mean=green[:,-10:,0].mean(1).tolist(),red_pan_last10_mean=red[:,-10:,0].mean(1).tolist(),
                                 pan_red_minus_green_last10=(red[:,-10:,0]-green[:,-10:,0]).mean(1).tolist(),
                                 green_pan_first10_mean=green[:,:10,0].mean(1).tolist(),red_pan_first10_mean=red[:,:10,0].mean(1).tolist(),
                                 green_pan_middle10_mean=green[:,20:30,0].mean(1).tolist(),red_pan_middle10_mean=red[:,20:30,0].mean(1).tolist()))
    (out/'language-metrics.json').write_text(json.dumps(language,indent=2))
    runtime=dict(seconds=time.perf_counter()-start,predicted_chunks=len(predictions),seeds=SEEDS,inference_seconds=stats(timings),
                 hardware_access=False,precision='float32',torch=torch.__version__,cuda=torch.version.cuda,gpu=torch.cuda.get_device_name(),
                 noise_policy='Explicit same CPU generated (1,chunk_size,max_action_dim) Gaussian tensor per seed shared across observations/checkpoints/languages; saved verbatim',
                 limitations='Recorded observations fixed: no closed-loop tracking, physical color/grasp success, runtime scheduler/reset/generation validation. Real request snapshots not recorded; frame request_tick is aligned proxy, not bit-exact original camera input.')
    (out/'runtime.json').write_text(json.dumps(runtime,indent=2));print(json.dumps(runtime,indent=2),flush=True)

if __name__=='__main__':main()
