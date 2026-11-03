"""Fail-closed local-only preflight for the frozen SmolVLA v2 experiment."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from tools.guard_smolvla_training import check_tree, digest
from tools.train_smolvla import checked_training_split


def environment_inventory():
    return {'python':str(Path(sys.executable).absolute()),'version':sys.version,
            'packages':sorted([d.metadata['Name'].lower(),d.version] for d in importlib.metadata.distributions())}


def check_local_contract(cfg, approved, smoke):
    if not approved.get('passed') or not smoke.get('passed'):
        raise RuntimeError('Local dataset and smoke approval required')
    for name, value in {'steps':20000,'batch_size':32,'seed':1000,'save_freq':5000,
                        'eval_steps':5000,'max_eval_samples':0,'num_workers':4,
                        'prefetch_factor':2,'persistent_workers':True}.items():
        if cfg.get(name) != value:
            raise RuntimeError(f'Formal training contract differs: {name}')
    if (cfg['policy'].get('use_amp') is not False
            or any(cfg['policy'].get(k) is not True for k in
                   ['freeze_vision_encoder','train_expert_only','train_state_proj'])
            or cfg['dataset']['image_transforms']['enable'] is not False):
        raise RuntimeError('FP32/frozen-VLM/no augmentation contract differs')
    for key, value in {'lr':1e-4,'betas':[.9,.95],'eps':1e-8,'weight_decay':1e-10,'grad_clip_norm':10.0}.items():
        if cfg['optimizer'].get(key) != value:
            raise RuntimeError('Optimizer contract differs: '+key)
    if (smoke.get('batch_size') != cfg['batch_size'] or smoke.get('steps',0)<100
            or not all(smoke.get(k) is True for k in ['parameters_updated','strict_reload','full_validation_verified','same_checkpoint_weights_as_full_validation_probe'])):
        raise RuntimeError('Smoke did not exercise batch/steps/update/reload/full validation')
    if smoke.get('train_stats_sha256') != approved['normalization']['stats_sha256']:
        raise RuntimeError('Smoke train statistics differ')
    if smoke.get('split_manifest_sha256') != approved['split_manifest_sha256']:
        raise RuntimeError('Smoke split differs')
    if (approved['datasets']['train']['episodes'] != 262
            or approved['datasets']['validation']['episodes'] != 76
            or cfg['dataset']['root'] != approved['datasets']['train']['root']):
        raise RuntimeError('Selected dataset contract differs')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);a=p.parse_args();e=a.evidence
    cfg=json.loads((e/'config.json').read_text());approved=json.loads((e/'data-approval.json').read_text());smoke=json.loads((e/'local_smoke_approved.json').read_text())
    check_local_contract(cfg,approved,smoke)
    probe=json.loads((e/'full-validation-probe-approved.json').read_text())
    if (not probe.get('passed') or not probe.get('full_validation_verified')
            or probe.get('files_manifest_sha256')!=approved['files_manifest_sha256']
            or probe.get('train_stats_sha256')!=approved['normalization']['stats_sha256']
            or probe.get('probe_checkpoint_model_sha256')!=smoke.get('checkpoint_model_sha256')
            or probe.get('full_validation_counts')!={c:v['frames'] for c,v in approved['datasets']['validation']['colors'].items()}):
        raise RuntimeError('Full validation probe does not cover the same exact datasets')
    bound=json.loads((e/'bundle-approved.json').read_text())
    if not bound.get('passed') or digest(e/'bundle-files.json') != bound['manifest_sha256']:
        raise RuntimeError('Bundle approval missing or changed')
    for path,expected in json.loads((e/'bundle-files.json').read_text()).items():
        if digest(path) != expected:
            raise RuntimeError('Frozen artifact changed: '+path)
    if json.loads((e/'environment_approved.json').read_text()) != {'passed':True,'inventory':environment_inventory()}:
        raise RuntimeError('Python environment changed')
    file_manifest=Path(approved['files_manifest'])
    if digest(file_manifest)!=approved['files_manifest_sha256']:
        raise RuntimeError('Dataset files manifest changed')
    files=json.loads(file_manifest.read_text())
    for split,ds in approved['datasets'].items():check_tree(ds['root'],files[split])
    source_files=json.loads((e.parent/'data/sources-before.json').read_text())
    source_parent=Path(approved['datasets']['train']['root']).parent
    for name,tree in source_files.items():check_tree(source_parent/name,tree)
    for item in json.loads((e/'model-files.json').read_text()).values():check_tree(item['root'],item['files'])
    split=checked_training_split(e/'config.json',approved['datasets']['train']['root'],approved['datasets']['validation']['root'])
    if (split['manifest_sha256']!=approved['split_manifest_sha256']
            or split['train_stats_sha256']!=smoke['train_stats_sha256']):
        raise RuntimeError('Split or normalization differs after freeze')
    if digest(e/'source/tools/train_smolvla_v2.py')!=smoke['v2_entrypoint_sha256']:
        raise RuntimeError('V2 FP32 entrypoint differs from smoke')
    if digest(e/'source/tools/train_smolvla.py')!=smoke['adapter_sha256']:
        raise RuntimeError('Adapter differs from smoke')
    if Path(cfg['output_dir']).exists():raise RuntimeError('Fresh formal output required')
    for proc in Path('/proc').glob('[0-9]*'):
        try:cmd=(proc/'cmdline').read_bytes().decode(errors='replace').split('\0')
        except OSError:continue
        if ('tools.train_smolvla' in cmd or 'tools.train_smolvla_v2' in cmd or 'lerobot.scripts.lerobot_train' in cmd
                or any(s.endswith('/lerobot-train') or s.endswith('/train_smolvla.py') for s in cmd)):
            raise RuntimeError('Another trainer active: '+proc.name)
    gpu=subprocess.run(['nvidia-smi','--query-compute-apps=pid,process_name,used_gpu_memory','--format=csv,noheader'],capture_output=True,text=True,check=True)
    if gpu.stdout.strip():raise RuntimeError('GPU compute processes active: '+gpu.stdout.strip())
    print(json.dumps({'passed':True,'mode':'local','output':cfg['output_dir'],'split':split},indent=2))


if __name__=='__main__':main()
