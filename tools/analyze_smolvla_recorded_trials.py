#!/usr/bin/env python3
"""Read-only real hard-backend collection audit. Never imports hardware/model APIs."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import numpy as np
from smolvla_recording_check import load_records,verify_queue
from smolvla_offline_diagnosis import stats

DEFAULT=Path('/data/work/so101-evidence/real-robot/smolvla-hard-recording-20261102/collection-package')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def leaf(schema,archive):
    if schema['kind']=='numpy':return archive[schema['key']].copy()
    assert schema['kind']=='tensor'
    return archive[schema['key']].view(np.dtype(schema['dtype'])).reshape(schema['shape']).copy()


def main():
    import pandas as pd
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,default=DEFAULT);p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    plan=json.loads((args.package/'plan.json').read_text());summaries=[];boundaries=[];clamp_rows=[];sequences={};noise_rows=[];manifests=[];sources={};buffers={};model_hashes=set();code_hashes=set()
    for trial in plan['trials']:
        identifier=trial['id'];rp=Path(trial['recording_path']);execution_path=args.package/f'trial-{identifier:02d}-execution.json';execution=json.loads(execution_path.read_text());status=json.loads((rp/'status.json').read_text());records=load_records(rp)
        assert (execution.get('returncode') == 0 if 'returncode' in execution else execution.get('complete') is True)
        # A recovery receipt certifies saved collection integrity only; runtime
        # errors and task results remain present in the source receipt.
        assert not execution.get('error') or execution.get('recovery')
        assert status['complete'] and status['dropped']==0 and not status['errors']
        assert len(records)==status['accepted']==status['written'];assert [int(f.name.split('-')[0]) for _,_,f in records]==list(range(len(records)))
        queue_audit=verify_queue(rp)
        requests={m['request_id']:m for k,m,f in records if k=='request'};obs={m['request_id']:(m,f) for k,m,f in records if k=='observation'};inf={m['request_id']:(m,f) for k,m,f in records if k=='inference'}
        assert requests.keys()==obs.keys()==inf.keys()
        manifest=next(m for k,m,f in records if k=='manifest');manifests.append(dict(id=identifier,**manifest));model_hashes.add(manifest['model_files_sha256']['model.safetensors']);code_hashes.add(json.dumps(manifest['code_sha256'],sort_keys=True))
        assert manifest['model_files_sha256']['model.safetensors']==plan['model_sha256'];assert manifest['model_path']==plan['model']
        argv=manifest['argv']
        if '--execute' in argv:
            assert plan['parameters']['max_relative_target']==30 and plan['parameters']['transition']=='hard'
        else:
            assert '--policy.n_action_steps=50' in argv and '--inference.prefetch=10' in argv and '--robot.max_relative_target=30' in argv
        assert manifest['parameters']['horizon']==50 and manifest['parameters']['prefetch']==10 and manifest['parameters']['fps']==20
        raw={};obs_state={};noises={}
        for ri,req in requests.items():
            om,of=obs[ri];im,iff=inf[ri]
            assert all(req[k]==om[k]==im[k] for k in ['generation','task','request_tick','observed_at'])
            assert req['task']==trial['env']['TASK']
            with np.load(of,allow_pickle=False) as z:obs_state[ri]=leaf(om['schema']['items']['observation.state'],z)
            with np.load(iff,allow_pickle=False) as z:
                nodes=im['schema']['items'];raw[ri]=leaf(nodes['raw_actions'],z)[0];noise=leaf(nodes['noise'],z)
            assert raw[ri].shape==(50,6) and np.isfinite(raw[ri]).all() and np.isfinite(noise).all()
            digest=hashlib.sha256(noise.tobytes()).hexdigest();noises[ri]=noise.reshape(-1)
            noise_rows.append(dict(trial=identifier,request_id=ri,request_tick=req['request_tick'],sha256=digest,mean=float(noise.mean()),std=float(noise.std()),norm=float(np.linalg.norm(noise))))
            sequences[f't{identifier}_r{ri}_raw']=raw[ri];sequences[f't{identifier}_r{ri}_request_state']=obs_state[ri]
        root=Path(trial['dataset_path']);table=pd.concat([pd.read_parquet(f) for f in sorted((root/'data').rglob('*.parquet'))],ignore_index=True).sort_values('frame_index')
        assert table.episode_index.nunique()==1 and int(table.episode_index.iloc[0])==0
        assert np.array_equal(table.frame_index.to_numpy(),np.arange(len(table)))
        state=np.stack(table['observation.state']);action=np.stack(table['action']);output=[m for k,m,f in records if k=='output'];installs=[m for k,m,f in records if k=='install'];a=np.asarray([m['action'] for m in output]);ticks=np.asarray([m['tick'] for m in output]);times=np.asarray([m['time'] for m in output]);n=len(a)
        assert n==len(table) and ticks[0]==0 and np.all(np.diff(ticks)>0);np.testing.assert_array_equal(a,action)
        tick_to_row={int(t):i for i,t in enumerate(ticks)}
        assert np.isfinite(state).all();preflight=Path(execution['preflight_path']);pre=json.loads((preflight/'result.json').read_text());tele=json.loads((preflight/'async-telemetry.json').read_text())
        assert pre['passed'] and pre['alignment']['passed'];assert tele['failed'] is None
        assert tele['stats']['actions']==n
        assert len(installs)==tele['stats']['chunks'];assert all(m['generation']==output[0]['generation'] for m in output)
        for m in installs:
            req=requests[m['request_id']];trim=m['trimmed'];expected={req['request_tick']+i:raw[m['request_id']][i].tolist() for i in range(trim,50)}
            assert expected=={int(k):v for k,v in m['new_future'].items()}
        # Per-tick record/action alignment is exact, but initial request predates
        # startup waiting. Its snapshot is not forced to equal later first state.
        snapshot_differences=[float(abs(obs_state[ri]-state[tick_to_row[req['request_tick']]]).max()) for ri,req in requests.items() if req['request_tick'] in tick_to_row]
        d1=abs(np.diff(a[:,:5],axis=0)).max(1);d2=abs(np.diff(a[:,:5],axis=0,n=2)).max(1);t1=np.arange(1,n);t2=np.arange(2,n);bs=np.asarray([tick_to_row[m['tick']] for m in installs[1:] if m['tick'] in tick_to_row]);mask1=np.isin(t1,bs);mask2=np.isin(t2,bs)|np.isin(t2-1,bs)
        values=dict(full_d1=d1,full_d2=d2,boundary_d1=d1[mask1],boundary_d2=d2[mask2],within_d1=d1[~mask1],within_d2=d2[~mask2],target_state_gap=abs(a[:,:5]-state[:,:5]).max(1),state_d1=abs(np.diff(state[:,:5],axis=0)).max(1))
        for group in ['all',f'{trial["layout"]}_{trial["color"]}',trial['color']]:
            buffer=buffers.setdefault(group,{k:[] for k in values})
            for k,v in values.items():buffer[k].extend(v.tolist())
        terminal=args.package/'terminal-logs'/f'trial-{identifier:02d}.log'
        log=terminal.read_text();marker='Relative goal position magnitude had to be clamped to be safe.'
        cursor=0;clamps=[];names=json.loads((root/'meta/info.json').read_text())['features']['action']['names']
        while marker in log[cursor:]:
            start=log.index('{',log.index(marker,cursor));depth=0;end=start
            for end in range(start,len(log)):
                depth+=(log[end]=='{')-(log[end]=='}')
                if depth==0:break
            values_logged=ast.literal_eval(log[start:end+1]);cursor=end+1
            mask=np.ones(n,bool)
            for key,pair in values_logged.items():mask &= abs(a[:,names.index(key+'.pos')]-pair['original goal_pos'])<1e-7
            matches=np.flatnonzero(mask);assert len(matches)==1
            frame=int(matches[0]);row=dict(trial=identifier,tick=int(ticks[frame]),frame_index=frame,time_s=frame/20,control_time_s=int(ticks[frame])/20,logged_targets=values_logged)
            clamps.append(row);clamp_rows.append(row)
        # Numeric markers are for pairing future visual annotations, not labels.
        above20=np.flatnonzero(state[:,1]>20);first20=int(above20[0]) if len(above20) else None
        gripper_edges=np.flatnonzero(np.diff(a[:,5]>15)!=0)+1
        for ii,m in enumerate(installs[1:],1):
            tick=m['tick'];b=tick_to_row[tick];ri=m['request_id'];old=installs[ii-1];oldri=old['request_id'];firstold=np.asarray(m['old_future'].get(str(tick),[float('nan')]*6));firstnew=np.asarray(m['new_future'][str(tick)]);previous=a[b-1];current=state[b];gap=abs(firstold[:5]-firstnew[:5]);joint=int(abs(firstnew[:5]-previous[:5]).argmax());window=list(range(b,min(b+10,n)))
            bounds=dict(trial=identifier,layout=trial['layout'],color=trial['color'],replicate=trial['trial'],tick=tick,frame_index=b,time_s=b/20,control_time_s=tick/20,request_id=ri,request_tick=m['request_tick'],old_request_id=oldri,old_request_tick=old['request_tick'],new_age_ticks=m['trimmed'],old_age_ticks=tick-old['request_tick'],remaining_old=len(m['old_future']),d1=float(d1[b-1]),d2_at_b=float(d2[b-2]),d2_at_b_plus1=float(d2[b-1]) if b+1<n else None,old_new_first_max=float(gap.max()),joint_d1=joint,old_state_gap_max=float(abs(firstold[:5]-current[:5]).max()),new_state_gap_max=float(abs(firstnew[:5]-current[:5]).max()),previous_state_gap_max=float(abs(previous[:5]-current[:5]).max()),old_request_state=obs_state[oldri].tolist(),new_request_state=obs_state[ri].tolist(),current_state=current.tolist(),previous_output=previous.tolist(),new_first=firstnew.tolist(),old_first=firstold.tolist(),old_future=m['old_future'],new_first10={t:m['new_future'][str(ticks[t])] for t in window if str(ticks[t]) in m['new_future']},old_observation_to_current_state_max=float(abs(obs_state[oldri][:5]-current[:5]).max()),new_observation_to_current_state_max=float(abs(obs_state[ri][:5]-current[:5]).max()),recorded_state_d1_at_b=float(abs(state[b,:5]-state[b-1,:5]).max()),first10_state=state[window].tolist(),first10_target=a[window].tolist(),near_gripper_edge_1s=bool(len(gripper_edges) and min(abs(gripper_edges-b))<=20),noise_cosine=float(np.dot(noises[oldri],noises[ri])/(np.linalg.norm(noises[oldri])*np.linalg.norm(noises[ri]))))
            boundaries.append(bounds)
        first=raw[0];request_ticks=[requests[i]['request_tick'] for i in sorted(requests)];lift=state[:,1]
        def first_cross(threshold):
            idx=np.flatnonzero(lift>threshold);return int(idx[0]) if len(idx) else None
        summary=dict(execution_receipt=execution,output_control_ticks=ticks.tolist(),control_tick_gaps=[dict(after_frame=int(i),from_tick=int(ticks[i]),to_tick=int(ticks[i+1])) for i in np.flatnonzero(np.diff(ticks)!=1)],clamp_warning_count=len(clamps),first_above_lift20_tick=first20,pan_median_next20_after_lift20=float(np.median(state[first20:first20+20,0])) if first20 is not None else None,id=identifier,layout=trial['layout'],color=trial['color'],replicate=trial['trial'],dataset=trial['dataset'],frames=n,duration_s=(n-1)/20,observed_hz=float((n-1)/(times[-1]-times[0])),interval_ms=stats(np.diff(times)*1000),inference_ms=stats([(m['inference_end']-m['inference_start'])*1000 for m in installs]),warm_inference_ms=stats([(m['inference_end']-m['inference_start'])*1000 for m in installs[1:]]),chunks=len(installs),boundaries=len(bs),first_output_wait_s=float(times[0]-requests[0]['observed_at']),request_state_vs_frame_max=max(snapshot_differences),noninitial_request_state_vs_frame_max=max(snapshot_differences[1:],default=0),initial_state=state[0].tolist(),first_above_lift_minus60_tick=first_cross(-60),first_above_lift_minus20_tick=first_cross(-20),first_above_lift_0_tick=first_cross(0),target_state_gap_gt30_ticks=int(np.count_nonzero(values['target_state_gap']>30)),first_chunk_pan_first10_mean=float(first[:10,0].mean()),first_chunk_lift_last10_mean=float(first[-10:,1].mean()),first_chunk_pan_last10_mean=float(first[-10:,0].mean()),preflight=dict(passed=pre['passed'],brightness_background_delta=pre['regions']['background']['brightness_delta'],brightness_paper_delta=pre['regions']['paper']['brightness_delta'],dx_px=pre['alignment']['dx_px'],dy_px=pre['alignment']['dy_px'],rotation_degrees=pre['alignment']['rotation_degrees'],inliers=pre['alignment']['inliers']),recording=status,telemetry_stats=tele['stats'],queue_audit=queue_audit,request_ticks=request_ticks,gripper_edges_threshold15_ticks=gripper_edges.tolist(),**{k:stats(v) for k,v in values.items()})
        summaries.append(summary);sequences[f't{identifier}_output']=a;sequences[f't{identifier}_recorded_state']=state;sequences[f't{identifier}_times']=times;sequences[f't{identifier}_ticks']=ticks
        sources[str(terminal)]=sha(terminal);sources[str(execution_path)]=sha(execution_path);sources[str(preflight/'result.json')]=sha(preflight/'result.json');sources[str(preflight/'async-telemetry.json')]=sha(preflight/'async-telemetry.json')
        for _,_,f in records:sources[str(f)]=sha(f)
        for f in (root/'data').rglob('*.parquet'):sources[str(f)]=sha(f)
        print(f'Trial {identifier:02d}: frames={n}, boundary d1 max={summary["boundary_d1"]["max"]:.3f}, exact archive/data alignment',flush=True)
    assert len(model_hashes)==len(code_hashes)==1
    pooled={g:{k:stats(v) for k,v in values.items()} for g,values in buffers.items()}
    initial=np.asarray([s['initial_state'] for s in summaries]);verification=dict(trials=len(summaries),frames=sum(s['frames'] for s in summaries),requests=len(noise_rows),boundaries=len(boundaries),all_archive_complete=True,all_preflight_passed=True,all_output_dataset_exact=True,all_actual_queue_replay_exact=True,model_sha256=list(model_hashes)[0],unique_runtime_code_manifests=len(code_hashes),clamp_warnings=len(clamp_rows),adjacent_request_noise_cosine=stats([b['noise_cosine'] for b in boundaries]),remaining_old_histogram={str(k):sum(b['remaining_old']==k for b in boundaries) for k in sorted({b['remaining_old'] for b in boundaries})},new_age_ticks_histogram={str(k):sum(b['new_age_ticks']==k for b in boundaries) for k in sorted({b['new_age_ticks'] for b in boundaries})},noise_tensors=len(noise_rows),noise_unique=len({r['sha256'] for r in noise_rows}),initial_state_peak_to_peak=np.ptp(initial,axis=0).tolist(),manual_results_csv=dict(path=str(args.package/'results.csv'),status_counts=pd.read_csv(args.package/'results.csv')['status'].value_counts().to_dict(),limits='Read current CSV statuses; no task success inferred from numerical joint data; CSV unchanged by this audit.'),hardware_access=False,limits='Actual CPU targets before relative-target clamp/serial, not motor commands or physical success. Time is host request/control/inference time, not camera exposure. No counterfactual noise/language evaluation performed.')
    def clean_json(value):
        if isinstance(value,float) and not np.isfinite(value):return None
        if isinstance(value,dict):return {k:clean_json(v) for k,v in value.items()}
        if isinstance(value,list):return [clean_json(v) for v in value]
        return value
    verification.update(runtime_normal_cases=[s['id'] for s in summaries if not s['execution_receipt'].get('error')],recovered_error_cases=[s['id'] for s in summaries if s['execution_receipt'].get('error')],starved_ticks=sum(s['telemetry_stats']['starved_ticks'] for s in summaries),skipped_ticks=sum(s['telemetry_stats']['skipped_ticks'] for s in summaries))
    for name,data in [('trials',summaries),('boundaries',boundaries),('clamp-events',clamp_rows),('pooled',pooled),('noise',noise_rows),('verification',verification),('run-manifests',manifests),('source-sha256',sources)]:
        (out/f'{name}.json').write_text(json.dumps(clean_json(data),indent=2,allow_nan=False))
    np.savez_compressed(out/'recorded-sequences-and-chunks.npz',**sequences)
    print(json.dumps(verification,indent=2))

if __name__=='__main__':main()
