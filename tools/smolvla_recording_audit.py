#!/usr/bin/env python3
"""Audit archived hard-backend requests, chunks and CPU queues; no hardware.

--replay-model additionally checks model/preprocessor reproduction on local GPU.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import numpy as np
try:
    from tools.smolvla_recording_check import load_records,verify_queue
except ModuleNotFoundError:
    from smolvla_recording_check import load_records,verify_queue


def audit(path,replay=False):
    from so101_rollout.smolvla.recording import restore_tree
    records=load_records(path);status=json.loads((path/'status.json').read_text());assert status['complete']
    assert len(records)==status['written']==status['accepted']
    assert [int(f.name.split('-')[0]) for _,_,f in records]==list(range(len(records)))
    manifest=next(m for k,m,f in records if k=='manifest')
    requests={m['request_id']:m for k,m,f in records if k=='request'}
    observations={m['request_id']:(m,f) for k,m,f in records if k=='observation'}
    inferences={m['request_id']:(m,f) for k,m,f in records if k=='inference'}
    assert requests.keys()==observations.keys()==inferences.keys()
    for identifier,r in requests.items():
        for m,_ in [observations[identifier],inferences[identifier]]:
            assert all(m[k]==r[k] for k in ['generation','task','request_tick','observed_at'])
    install_count=0
    for kind,m,f in records:
        if kind!='install':continue
        im,source=inferences[m['request_id']]
        with np.load(source,allow_pickle=False) as z:payload=restore_tree(im['schema'],z)
        a=payload['raw_actions'][0].numpy()[:,manifest['parameters']['action_order']]
        assert np.isfinite(a).all() and a.shape[1]==6
        expected={m['request_tick']+i:a[i].tolist() for i in range(m['trimmed'],manifest['parameters']['horizon'])}
        assert expected=={int(k):v for k,v in m['new_future'].items()};install_count+=1
    report=dict(passed=True,hardware_access=False,requests=len(requests),inferences=len(inferences),install_raw_alignment_checked=install_count,queue=verify_queue(path),model_replay=False)
    if replay:
        import torch
        from lerobot.configs.policies import PreTrainedConfig
        from lerobot.rollout.context import _load_pretrained_policy
        from lerobot.policies import make_pre_post_processors
        from lerobot.policies.utils import prepare_observation_for_inference
        torch.set_num_threads(4);model_path=Path(manifest['model_path'])
        h=hashlib.sha256()
        with (model_path/'model.safetensors').open('rb') as f:
            for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
        assert h.hexdigest()==manifest['model_files_sha256']['model.safetensors']
        cfg=PreTrainedConfig.from_pretrained(model_path,local_files_only=True);cfg.pretrained_path=model_path;cfg.device='cuda'
        policy=_load_pretrained_policy(cfg).cuda().eval()
        overrides={}
        for step in manifest['parameters']['preprocessor']['steps']:
            name=step.get('registry_name')
            if name in ['rename_observations_processor','device_processor']:overrides[name]=step['config']
        pre,post=make_pre_post_processors(policy_cfg=cfg,pretrained_path=str(model_path),preprocessor_overrides=overrides)
        differences=[]
        def equal_tree(a,b):
            if torch.is_tensor(a):assert torch.equal(a,b)
            elif isinstance(a,dict):
                assert a.keys()==b.keys()
                for k in a:equal_tree(a[k],b[k])
            else:assert a==b
        for identifier,(m,f) in inferences.items():
            om,of=observations[identifier]
            # Inspect saved image dimensions before reading image array payloads.
            for k,v in om['schema']['items'].items():
                if 'image' in k:assert v['shape']==[480,640,3]
            with np.load(of,allow_pickle=False) as z:obs=restore_tree(om['schema'],z)
            with np.load(f,allow_pickle=False) as z:payload=restore_tree(m['schema'],z,'cuda')
            pre.reset();post.reset();policy.reset()
            prepared=pre(prepare_observation_for_inference(deepcopy(obs),torch.device('cuda'),m['task'],manifest['parameters']['robot_type']))
            equal_tree(prepared,payload['model_input'])
            with torch.inference_mode():a=post(policy.predict_action_chunk(payload['model_input'],noise=payload['noise']))
            differences.append(float((a.cpu()-payload['raw_actions'].cpu()).abs().max()))
        assert max(differences)==0
        report.update(model_replay=True,raw_observation_preprocessor_exact=True,replay_maxdiff=max(differences))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--recording',type=Path,required=True);p.add_argument('--replay-model',action='store_true');p.add_argument('--output',type=Path);a=p.parse_args();report=audit(a.recording,a.replay_model);s=json.dumps(report,indent=2);print(s)
    if a.output:a.output.write_text(s)

if __name__=='__main__':main()
