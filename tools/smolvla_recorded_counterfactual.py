#!/usr/bin/env python3
"""Frozen 32-cell diagnosis: 12 paired task flips and two 2x2 noise crossovers.

Never imports hardware. Observations/noise are actual recorded inputs. Action
response is not evidence of physical color selection or task success.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from smolvla_recording_check import load_records
from smolvla_offline_diagnosis import sha,stats

PACKAGE=Path('/data/work/so101-evidence/real-robot/smolvla-hard-recording-20261102/collection-package')


def freeze(package,contacts,out):
    plan=json.loads((package/'plan.json').read_text());trials={t['id']:t for t in plan['trials']};runs={};cells=[];source_sha={}
    for tid,t in trials.items():
        records=load_records(Path(t['recording_path']));runs[tid]=dict(manifest=next(m for k,m,f in records if k=='manifest'),requests={m['request_id']:m for k,m,f in records if k=='request'},observations={m['request_id']:(m,f) for k,m,f in records if k=='observation'},inferences={m['request_id']:(m,f) for k,m,f in records if k=='inference'},installs={m['request_id']:m for k,m,f in records if k=='install'})
    def cell(name,tid,obsid,noiseid,task,baseline,**extra):
        run=runs[tid];om,of=run['observations'][obsid];im,iff=run['inferences'][obsid];nm,nf=run['inferences'][noiseid]
        source_sha[str(of)]=sha(of);source_sha[str(iff)]=sha(iff);source_sha[str(nf)]=sha(nf)
        return dict(key=name,trial=tid,observation_request_id=obsid,noise_request_id=noiseid,request_tick=om['request_tick'],generation=om['generation'],task=task,baseline=baseline,observation_file=str(of),inference_file=str(iff),noise_file=str(nf),observation_schema=om['schema'],inference_schema=im['schema'],noise_schema=nm['schema']['items']['noise'],**extra)
    selections=[]
    for tid in range(1,13):
        contact=contacts[str(tid)];frame=contact['first_possible_frame'];run=runs[tid]
        ri=max((ri for ri,m in run['requests'].items() if m['request_tick']<frame),key=lambda ri:run['requests'][ri]['request_tick'])
        req=run['requests'][ri];original=req['task'];other='Put the red cube into the paper bowl' if 'green' in original else 'Put the green cube into the paper bowl';install=run['installs'].get(ri)
        common=dict(first_contact=contact,installed_tick=install['tick'] if install else None,installed_before_contact=bool(install and install['tick']<frame),forecast_contact_index=frame-req['request_tick'])
        selections.append(dict(trial=tid,request_id=ri,request_tick=req['request_tick'],**common))
        cells.append(cell(f'language_t{tid:02d}_original',tid,ri,ri,original,True,group='language',condition='original',**common))
        cells.append(cell(f'language_t{tid:02d}_swap',tid,ri,ri,other,False,group='language',condition='swap',**common))
    for tid,boundary in [(7,484),(4,164)]:
        run=runs[tid];newid=next(ri for ri,m in run['installs'].items() if m['tick']==boundary);ordered=sorted(run['installs'],key=lambda ri:run['installs'][ri]['tick']);oldid=ordered[ordered.index(newid)-1]
        for obslabel,obsid in [('old',oldid),('new',newid)]:
            for noiselabel,noiseid in [('old',oldid),('new',newid)]:
                cells.append(cell(f'noise_t{tid:02d}_obs{obslabel}_noise{noiselabel}',tid,obsid,noiseid,run['requests'][obsid]['task'],obsid==noiseid,group='noise',observation_condition=obslabel,noise_condition=noiselabel,boundary_tick=boundary,aligned_index=boundary-run['requests'][obsid]['request_tick']))
    assert len(cells)==32
    manifest=dict(total_cells=32,language_cells=24,noise_cells=8,selections=selections,cells=cells,source_sha256=source_sha,model_manifest=runs[1]['manifest'],contact_annotation=contacts,design='Frozen before model loading/prediction. No new noise. Original pairing must reproduce every element exactly; language pair permits task/token/attention changes only.',limitations='Raw target differences do not establish correct color selection, physical tracking or grasp success. Observation crossover also changes effective forecast horizon.')
    (out/'frozen-manifest.json').write_text(json.dumps(manifest,indent=2));return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,default=PACKAGE);p.add_argument('--contacts',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=False)
    contacts=json.loads(a.contacts.read_text());manifest=freeze(a.package,contacts,out);print('Frozen 32 cells before model load',flush=True)
    import torch
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.rollout.context import _load_pretrained_policy
    from lerobot.policies import make_pre_post_processors
    from lerobot.policies.utils import prepare_observation_for_inference
    from so101_rollout.smolvla.recording import restore_tree
    torch.set_num_threads(4);mm=manifest['model_manifest'];root=Path(mm['model_path']);assert sha(root/'model.safetensors')==mm['model_files_sha256']['model.safetensors']
    cfg=PreTrainedConfig.from_pretrained(root,local_files_only=True);cfg.pretrained_path=root;cfg.device='cuda';policy=_load_pretrained_policy(cfg).cuda().eval()
    overrides={}
    for step in mm['parameters']['preprocessor']['steps']:
        name=step.get('registry_name')
        if name in ['rename_observations_processor','device_processor']:overrides[name]=step['config']
    pre,post=make_pre_post_processors(policy_cfg=cfg,pretrained_path=str(root),preprocessor_overrides=overrides)
    predictions={};noises={};checks=[];timings=[];prepared_original={}
    def equal(x,y):
        if torch.is_tensor(x):return torch.equal(x,y)
        if isinstance(x,dict):return x.keys()==y.keys() and all(equal(x[k],y[k]) for k in x)
        if isinstance(x,(list,tuple)):return len(x)==len(y) and all(equal(a,b) for a,b in zip(x,y))
        return x==y
    for cell in manifest['cells']:
        for k,node in cell['observation_schema']['items'].items():
            if 'image' in k:assert node['shape']==[480,640,3]
        with np.load(cell['observation_file'],allow_pickle=False) as z:obs=restore_tree(cell['observation_schema'],z)
        with np.load(cell['inference_file'],allow_pickle=False) as z:reference=restore_tree(cell['inference_schema'],z,'cuda')
        with np.load(cell['noise_file'],allow_pickle=False) as z:noise=restore_tree(cell['noise_schema'],z,'cuda')
        policy.reset();pre.reset();post.reset()
        batch=pre(prepare_observation_for_inference(deepcopy(obs),torch.device('cuda'),cell['task'],mm['parameters']['robot_type']))
        allowed={'task','observation.language.tokens','observation.language.attention_mask'}
        differences=[k for k in batch if not equal(batch[k],reference['model_input'][k])]
        if cell['group']=='language' and cell['condition']=='swap':assert set(differences)<=allowed
        else:assert not differences
        noise_np=noise.cpu().numpy().copy();noises[cell['key']]=noise_np
        torch.cuda.synchronize();t=time.perf_counter()
        with torch.inference_mode():prediction=post(policy.predict_action_chunk(batch,noise=noise.clone())).detach().cpu().numpy()[0]
        torch.cuda.synchronize();timings.append(time.perf_counter()-t)
        assert prediction.shape==(50,6) and np.isfinite(prediction).all()
        diff=float(abs(prediction-reference['raw_actions'][0].cpu().numpy()).max())
        if cell['baseline']:assert diff==0,f'Original pairing failed: {cell["key"]}: {diff}'
        predictions[cell['key']]=prediction
        checks.append(dict(key=cell['key'],baseline=cell['baseline'],baseline_maxdiff=diff if cell['baseline'] else None,changed_model_input_keys=differences,noise_sha256=hashlib.sha256(noise_np.tobytes()).hexdigest(),raw_state_sha256=hashlib.sha256(obs['observation.state'].tobytes()).hexdigest(),raw_image_sha256={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in obs.items() if 'image' in k}))
        print(cell['key'],f'baseline_diff={diff:.9f}' if cell['baseline'] else 'counterfactual',flush=True)
    language=[]
    for tid in range(1,13):
        original=predictions[f'language_t{tid:02d}_original'];swap=predictions[f'language_t{tid:02d}_swap'];pair=[c for c in checks if c['key'].startswith(f'language_t{tid:02d}_')]
        assert len({c['noise_sha256'] for c in pair})==len({c['raw_state_sha256'] for c in pair})==1
        assert pair[0]['raw_image_sha256']==pair[1]['raw_image_sha256']
        selection=manifest['selections'][tid-1];idx=int(selection['forecast_contact_index']);lo=max(0,idx-5);hi=min(50,idx+5)
        language.append(dict(trial=tid,selection=selection,body_mae=float(abs(original[:,:5]-swap[:,:5]).mean()),body_max_difference=float(abs(original[:,:5]-swap[:,:5]).max()),first10_body_mae=float(abs(original[:10,:5]-swap[:10,:5]).mean()),original_pan_first10=float(original[:10,0].mean()),swap_pan_first10=float(swap[:10,0].mean()),pan_mean_difference_first10=float((swap[:10,0]-original[:10,0]).mean()),contact_window_indices=[lo,hi],original_contact_window_pan=float(original[lo:hi,0].mean()),swap_contact_window_pan=float(swap[lo:hi,0].mean()),contact_window_body_mae=float(abs(original[lo:hi,:5]-swap[lo:hi,:5]).mean())))
    cross=[]
    for tid,b in [(7,484),(4,164)]:
        vals={}
        for obslabel in ['old','new']:
            cells=[c for c in manifest['cells'] if c['group']=='noise' and c['trial']==tid and c['observation_condition']==obslabel];idx=cells[0]['aligned_index']
            oldnoise=predictions[f'noise_t{tid:02d}_obs{obslabel}_noiseold'];newnoise=predictions[f'noise_t{tid:02d}_obs{obslabel}_noisenew']
            vals[obslabel]=dict(index=idx,old_noise_aligned=oldnoise[idx].tolist(),new_noise_aligned=newnoise[idx].tolist(),noise_aligned_body_difference_max=float(abs(oldnoise[idx,:5]-newnoise[idx,:5]).max()),noise_chunk_body_mae=float(abs(oldnoise[:,:5]-newnoise[:,:5]).mean()))
        cross.append(dict(trial=tid,boundary_tick=b,by_observation=vals,old_noise_old_new_aligned_gap=float(abs(np.array(vals['old']['old_noise_aligned'][:5])-vals['new']['old_noise_aligned'][:5]).max()),new_noise_old_new_aligned_gap=float(abs(np.array(vals['old']['new_noise_aligned'][:5])-vals['new']['new_noise_aligned'][:5]).max())))
    np.savez_compressed(out/'predictions.npz',**predictions);np.savez_compressed(out/'used-noise.npz',**noises)
    for name,data in [('invariant-checks',checks),('language-metrics',language),('noise-cross-metrics',cross)]:
        (out/f'{name}.json').write_text(json.dumps(data,indent=2))
    result=dict(passed=True,total_predictions=len(predictions),baseline_reproductions=sum(c['baseline'] for c in checks),baseline_maxdiff=max(c['baseline_maxdiff'] for c in checks if c['baseline']),language_invariant_pairs=12,timing_seconds=stats(timings),model_path=str(root),model_sha256=sha(root/'model.safetensors'),frozen_manifest_sha256=sha(out/'frozen-manifest.json'),predictions_sha256=sha(out/'predictions.npz'),noise_sha256=sha(out/'used-noise.npz'),gpu=torch.cuda.get_device_name(),hardware_access=False,training=False,config_changes=False,limits=manifest['limitations'])
    (out/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
