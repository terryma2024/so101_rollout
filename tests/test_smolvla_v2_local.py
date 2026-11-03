import copy
import pytest


def config():
    return {'steps':20000,'batch_size':32,'seed':1000,'save_freq':5000,'eval_steps':5000,'max_eval_samples':0,
            'num_workers':4,'prefetch_factor':2,'persistent_workers':True,
            'policy':{'use_amp':False,'freeze_vision_encoder':True,'train_expert_only':True,'train_state_proj':True},
            'optimizer':{'lr':1e-4,'betas':[.9,.95],'eps':1e-8,'weight_decay':1e-10,'grad_clip_norm':10.0},
            'dataset':{'root':'train','image_transforms':{'enable':False}}}


def smoke():
    return {'passed':True,'steps':100,'batch_size':32,'train_stats_sha256':'stats',
            'split_manifest_sha256':'split','parameters_updated':True,'strict_reload':True,
            'full_validation_verified':True,'same_checkpoint_weights_as_full_validation_probe':True}


def approval():
    return {'passed':True,'datasets':{'train':{'root':'train','episodes':262},'validation':{'episodes':76}},
            'normalization':{'stats_sha256':'stats'},'split_manifest_sha256':'split'}


def test_local_approval_needs_no_fictitious_remote_transfer():
    from tools.guard_smolvla_v2_local import check_local_contract
    check_local_contract(config(),approval(),smoke())


@pytest.mark.parametrize('damage',['batch','steps','update','stats','split','eval','amp','lr','counts'])
def test_local_guard_rejects_unexercised_or_changed_contract(damage):
    from tools.guard_smolvla_v2_local import check_local_contract
    c,a,s=config(),approval(),smoke()
    if damage=='batch':s['batch_size']=8
    if damage=='steps':s['steps']=99
    if damage=='update':s['parameters_updated']=False
    if damage=='stats':s['train_stats_sha256']='other'
    if damage=='split':s['split_manifest_sha256']='other'
    if damage=='eval':s['full_validation_verified']=False
    if damage=='amp':c['policy']['use_amp']=True
    if damage=='lr':c['optimizer']['lr']=1e-3
    if damage=='counts':a['datasets']['train']['episodes']=263
    with pytest.raises(RuntimeError):check_local_contract(c,a,s)


def test_official_mixed_dtype_base_is_promoted_before_optimization():
    import torch
    from tools.train_smolvla_v2 import fp32_policy_factory
    module=torch.nn.Linear(2,2,dtype=torch.bfloat16)
    original=module.weight.detach().float().clone()
    policy=fp32_policy_factory(lambda:module)()
    assert all(p.dtype==torch.float32 for p in policy.parameters())
    assert torch.equal(policy.weight,original)
    policy(torch.ones(1,2)).sum().backward()
    assert policy.weight.grad.dtype==torch.float32


def test_final_verification_requires_each_full_validation_pass():
    from tools.verify_smolvla_v2_training import verify_validation_counts
    expected={'green':14229,'red':8916}
    r={'evaluation':{str(s):{'green':{'samples':14229},'red':{'samples':8916}} for s in [5000,10000,15000,20000]},
       'seen':{'validation':{'green':56916,'red':35664}}}
    verify_validation_counts(r,expected,20000)
    del r['evaluation']['10000']
    with pytest.raises(RuntimeError):verify_validation_counts(r,expected,20000)


def test_final_verification_rejects_partial_color_coverage():
    from tools.verify_smolvla_v2_training import verify_validation_counts
    r={'evaluation':{'5000':{'green':{'samples':14228},'red':{'samples':8916}}},
       'seen':{'validation':{'green':14228,'red':8916}}}
    with pytest.raises(RuntimeError):verify_validation_counts(r,{'green':14229,'red':8916},5000)


def test_full_validation_reuse_requires_identical_checkpoint_weights():
    from tools.guard_smolvla_v2_local import check_local_contract
    s=smoke();s['same_checkpoint_weights_as_full_validation_probe']=False
    with pytest.raises(RuntimeError):check_local_contract(config(),approval(),s)


def test_environment_freeze_can_be_compared_after_json_roundtrip():
    import json
    from tools.guard_smolvla_v2_local import environment_inventory
    original=environment_inventory()
    assert json.loads(json.dumps(original))==original
