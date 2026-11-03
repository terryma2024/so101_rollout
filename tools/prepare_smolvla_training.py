"""Materialize an offline bootstrap and complete LeRobot training configuration."""
import argparse
import json
import os
from pathlib import Path
import shutil

from tools.train_smolvla import (CAMERA_MAP, bootstrap_config, checked_split_manifest,
                                checked_training_split, sha256)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--vlm', type=Path, required=True)
    p.add_argument('--bootstrap', type=Path, required=True)
    p.add_argument('--train', type=Path, required=True)
    p.add_argument('--validation', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--steps', type=int, default=20000)
    p.add_argument('--batch-size', type=int, default=8)
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--max-eval-samples', type=int, default=0)
    p.add_argument('--split-manifest', type=Path,
                   help='Approved split.json with per-episode source identity, frames and numeric SHA')
    a = p.parse_args()
    if a.config.exists() or a.config.with_suffix('.split.json').exists():
        p.error('config already exists; use a fresh path')
    split = (checked_split_manifest(a.train, a.validation, a.split_manifest)
             if a.split_manifest else checked_training_split(a.config, a.train, a.validation))
    expected = bootstrap_config(json.loads((a.base / 'config.json').read_text()), a.vlm)
    if a.bootstrap.exists():
        if json.loads((a.bootstrap / 'config.json').read_text()) != expected:
            raise ValueError('Existing bootstrap differs from requested contract')
    else:
        a.bootstrap.mkdir(parents=True)
        for source in a.base.iterdir():
            if not source.is_file() or source.name in ('config.json', 'policy_preprocessor.json'):
                continue
            try:
                os.link(source.resolve(), a.bootstrap / source.name)
            except OSError:
                shutil.copyfile(source, a.bootstrap / source.name)
        (a.bootstrap / 'config.json').write_text(json.dumps(expected, indent=2) + '\n')
        processor = json.loads((a.base / 'policy_preprocessor.json').read_text())
        for step in processor['steps']:
            if step['registry_name'] == 'tokenizer_processor':
                step['config']['tokenizer_name'] = str(a.vlm)
        (a.bootstrap / 'policy_preprocessor.json').write_text(json.dumps(processor, indent=2) + '\n')
    if sha256(a.bootstrap / 'model.safetensors') != sha256(a.base / 'model.safetensors'):
        raise RuntimeError('Bootstrap model weights differ from official base')
    policy = dict(expected, pretrained_path=str(a.bootstrap))
    raw = {'dataset': {'repo_id': 'local/' + a.train.name, 'root': str(a.train),
                       'video_backend': 'pyav', 'use_imagenet_stats': False,
                       'eval_split': split['splits']['validation']['episodes'] / sum(
                           s['episodes'] for s in split['splits'].values())},
           'policy': policy, 'output_dir': str(a.output),
           'job_name': a.output.name, 'steps': a.steps, 'batch_size': a.batch_size,
           'num_workers': a.workers, 'prefetch_factor': 2, 'persistent_workers': True,
           'seed': 1000, 'save_freq': 5000, 'log_freq': 20,
           'eval_steps': 100 if a.steps <= 100 else 5000,
           'max_eval_samples': a.max_eval_samples, 'env_eval_freq': 0,
           'save_checkpoint_to_hub': False, 'rename_map': CAMERA_MAP,
           'wandb': {'enable': False}, 'use_policy_training_preset': True}
    # Decode and validate using the pinned library so saved defaults and optimizer
    # presets are explicit, not assumptions reconstructed by a later launcher.
    import draccus
    from lerobot.configs.train import TrainPipelineConfig
    from lerobot.policies.smolvla.configuration_smolvla import SmolVLAConfig  # registry
    cfg = draccus.decode(TrainPipelineConfig, raw)
    cfg.validate()
    a.config.parent.mkdir(parents=True, exist_ok=True)
    a.config.write_text(json.dumps(cfg.to_dict(), indent=2) + '\n')
    if a.split_manifest:
        a.config.with_suffix('.split.json').write_text(json.dumps(split, indent=2) + '\n')
    print(json.dumps({'config': str(a.config), 'config_sha256': sha256(a.config),
                      'bootstrap': str(a.bootstrap), 'batch': a.batch_size,
                      'epoch_budget': a.steps * a.batch_size / split['splits']['train']['frames']}, indent=2))


if __name__ == '__main__':
    main()
