"""Thin LeRobot 0.6.1 training adapter for an immutable external session split.

Run as a module. Only the dataset factory and audit hooks are scoped replacements;
optimization, batching, evaluation, and checkpointing remain LeRobot's implementation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import time

CAMERA_MAP = {'observation.images.wrist': 'observation.images.camera1',
              'observation.images.side': 'observation.images.camera2'}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_stats_reference(train, validation):
    stats = Path(train) / 'meta/stats.json'
    ref = json.loads((Path(validation) / 'meta/normalization-reference.json').read_text())
    if (ref.get('fitted_split') != 'train' or Path(ref.get('stats_path', '')) != stats
            or ref.get('stats_sha256') != sha256(stats)):
        raise ValueError('Validation must reference the approved train-fitted statistics')
    return ref


def checked_split_manifest(train, validation, manifest):
    """Verify an external split against real derived and original numeric data.

    Sources live alongside derived roots, as in the approved data exporter.
    This is a CPU check; it does not substitute for full video/file-tree approval.
    """
    from tools.prepare_smolvla_data import TASKS, numeric_digest, origin_episode, read_tables, validate_split
    manifest = Path(manifest)
    records = json.loads(manifest.read_text())['records']
    if any(r.get('split') not in ('train', 'validation') for r in records):
        raise ValueError('Unknown manifest split')
    source_groups = {}
    for row in records:
        source = row['source_dataset'].replace('extra-clean-', 'extra-').replace('red-clean-', 'red-')
        if not isinstance(row['group'], str) or not row['group']:
            raise ValueError('Missing source capture group')
        if source_groups.setdefault(source, row['group']) != row['group']:
            raise ValueError('One source folder cannot claim multiple capture groups')
    validate_split(records)
    reference = checked_stats_reference(train, validation)
    summary = {}
    sources = {}
    for split, root in [('train', Path(train)), ('validation', Path(validation))]:
        rows = [r for r in records if r['split'] == split]
        ids = [r['derived_episode_index'] for r in rows]
        if sorted(ids) != list(range(len(rows))):
            raise ValueError(f'{split} manifest episode mapping is not unique and contiguous')
        frame = read_tables(root, 'data')
        info = json.loads((root / 'meta/info.json').read_text())
        if (set(frame.episode_index) != set(ids) or info['total_episodes'] != len(rows)
                or info['total_frames'] != len(frame)):
            raise ValueError(f'{split} actual episode/frame counts differ from manifest')
        import pandas as pd
        tasks = pd.read_parquet(root / 'meta/tasks.parquet')
        task_map = {int(row.task_index): str(index) for index, row in tasks.iterrows()}
        for row in rows:
            actual = frame[frame.episode_index == row['derived_episode_index']]
            if type(row['frames']) is not int or row['frames'] <= 0 or len(actual) != row['frames']:
                raise ValueError(f'{split} episode frames differ from manifest')
            if (row['task'] != TASKS[row['color']]
                    or any(task_map.get(int(i)) != row['task'] for i in actual.task_index)):
                raise ValueError(f'{split} episode task differs from manifest')
            if numeric_digest(actual) != row['numeric_sha256']:
                raise ValueError(f'{split} episode numeric trajectory differs from manifest')
            name = row['source_dataset']
            original_name = name.replace('extra-clean-', 'extra-').replace('red-clean-', 'red-')
            if (not name or Path(name).name != name or name in ('.', '..')
                    or type(row['source_episode_index']) is not int or row['source_episode_index'] < 0
                    or type(row['original_episode_index']) is not int or row['original_episode_index'] < 0
                    or row['original_episode_index'] != origin_episode(name, row['source_episode_index'])
                    or row['origin'] != f"{original_name}:{row['original_episode_index']}"):
                raise ValueError('Invalid source identity/episode mapping')
            source_root = root.parent / name
            if source_root not in sources:
                sources[source_root] = read_tables(source_root, 'data')
            source = sources[source_root]
            original = source[source.episode_index == row['source_episode_index']]
            if len(original) != row['frames'] or numeric_digest(original) != row['numeric_sha256']:
                raise ValueError('Manifest source episode differs from actual source trajectory')
        summary[split] = {'episodes': len(rows), 'frames': len(frame)}
    return {'manifest': str(manifest.resolve()), 'manifest_sha256': sha256(manifest),
            'train_root': str(Path(train).resolve()), 'validation_root': str(Path(validation).resolve()),
            'train_stats_sha256': reference['stats_sha256'], 'splits': summary}


def checked_training_split(config_path, train, validation):
    """Require a content-bound split receipt, except for the exact legacy v1."""
    sidecar = Path(config_path).with_suffix('.split.json')
    if sidecar.exists():
        expected = json.loads(sidecar.read_text())
        if sha256(expected['manifest']) != expected['manifest_sha256']:
            raise ValueError('Split manifest changed after configuration freeze')
        actual = checked_split_manifest(train, validation, expected['manifest'])
        if actual != expected:
            raise ValueError('Split contract changed after configuration freeze')
        return actual
    reference = checked_stats_reference(train, validation)
    if (Path(train).name != 'real-cube-bowl-smolvla-train-20261030'
            or Path(validation).name != 'real-cube-bowl-smolvla-validation-20261030'
            or reference['stats_sha256'] != 'a894ea726894265d450f20acb9382be79a8372bbf6a7648a74735675720e5842'):
        raise ValueError('Only approved v1 may omit the split manifest sidecar')
    splits = {}
    for label, root, episodes, frames in [('train', train, 214, 63732),
                                         ('validation', validation, 52, 17864)]:
        info = json.loads((Path(root) / 'meta/info.json').read_text())
        if info['total_episodes'] != episodes or info['total_frames'] != frames:
            raise ValueError('Legacy v1 dataset counts differ from approval')
        splits[label] = {'episodes': episodes, 'frames': frames}
    return {'splits': splits, 'legacy_v1': True}


@contextmanager
def scoped_overrides(module, **overrides):
    before = {name: getattr(module, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(module, name, value)
        yield
    finally:
        for name, value in before.items():
            setattr(module, name, value)


def bootstrap_config(base, vlm):
    cfg = copy.deepcopy(base)
    cfg.update(vlm_model_name=str(vlm), load_vlm_weights=False, push_to_hub=False,
               empty_cameras=0, use_amp=False)
    cfg['input_features'] = {
        'observation.state': {'type': 'STATE', 'shape': [6]},
        'observation.images.camera1': {'type': 'VISUAL', 'shape': [3, 480, 640]},
        'observation.images.camera2': {'type': 'VISUAL', 'shape': [3, 480, 640]},
    }
    cfg['output_features'] = {'action': {'type': 'ACTION', 'shape': [6]}}
    return cfg


def valid_weighted_mean(values, valid_counts):
    """Match native SmolVLA mean: weight samples by their valid action timesteps."""
    if len(values) != len(valid_counts):
        raise ValueError('Loss and valid-count lengths differ')
    return sum(v * n for v, n in zip(values, valid_counts)) / max(sum(valid_counts), 1)


def run(config_path, validation_root, audit_dir):
    import torch
    from lerobot.configs.train import TrainPipelineConfig
    from lerobot.datasets.factory import make_dataset
    from lerobot.scripts import lerobot_train as trainer
    from lerobot.utils.constants import OBS_LANGUAGE_TOKENS

    cfg = TrainPipelineConfig.from_pretrained(config_path, cli_args=[])
    reference = checked_stats_reference(cfg.dataset.root, validation_root)
    split_contract = checked_training_split(config_path, cfg.dataset.root, validation_root)
    audit_dir.mkdir(parents=True, exist_ok=False)
    records, eval_records = [], []
    seen = {'train': Counter(), 'validation': Counter()}
    tokens = {}
    initial = {'reference': reference, 'train_root': str(cfg.dataset.root),
               'validation_root': str(validation_root), 'adapter': str(Path(__file__).resolve()),
               'adapter_sha256': sha256(__file__), 'config_sha256': sha256(config_path),
               'split_contract': split_contract,
               'dataset_eval_split_semantics': 'informational fraction; external immutable split loaded directly'}
    (audit_dir / 'adapter.json').write_text(json.dumps(initial, indent=2) + '\n')
    train_stats = json.loads((Path(cfg.dataset.root) / 'meta/stats.json').read_text())
    original_factory = trainer.make_policy
    original_processors = trainer.make_pre_post_processors
    original_update = trainer.update_policy
    step_number = 0

    def datasets(c):
        train_cfg = copy.deepcopy(c)
        train_cfg.dataset.eval_split = 0
        val_cfg = copy.deepcopy(train_cfg)
        val_cfg.dataset.root = str(validation_root)
        val_cfg.dataset.repo_id = 'local/' + validation_root.name
        val_cfg.dataset.image_transforms.enable = False
        train, val = make_dataset(train_cfg), make_dataset(val_cfg)
        for label, dataset in [('train', train), ('validation', val)]:
            expected = split_contract['splits'][label]
            if dataset.num_episodes != expected['episodes'] or dataset.num_frames != expected['frames']:
                raise ValueError(f'External {label} membership differs from approved split')
        return train, val

    def processors(*args, **kwargs):
        pre, post = original_processors(*args, **kwargs)
        checked = {}
        for label, pipeline, feature in [('pre-state', pre, 'observation.state'),
                                         ('pre-action', pre, 'action'), ('post-action', post, 'action')]:
            steps = [s for s in pipeline.steps if hasattr(s, '_tensor_stats')]
            if len(steps) != 1:
                raise RuntimeError('Expected exactly one saved normalization processor')
            for key in ('mean', 'std'):
                actual = steps[0]._tensor_stats[feature][key].detach().cpu()
                expected = torch.as_tensor(train_stats[feature][key], dtype=actual.dtype)
                if not torch.equal(actual, expected):
                    raise RuntimeError(f'{label} {feature}/{key} does not use train statistics')
            checked[label] = feature
        (audit_dir / 'processor-stats.json').write_text(json.dumps({
            'passed': True, 'shared_for_training_and_validation': True,
            'train_stats_sha256': reference['stats_sha256'], 'checked': checked}, indent=2) + '\n')
        return pre, post

    def make_policy(*args, **kwargs):
        policy = original_factory(*args, **kwargs)
        forward = policy.forward

        def audited_forward(batch, *a, **kw):
            phase = 'train' if policy.training else 'validation'
            task_values = batch['task']
            task_values = [task_values] if isinstance(task_values, str) else task_values
            colors = ['green' if 'green cube' in t else 'red' if 'red cube' in t else 'unknown' for t in task_values]
            if 'unknown' in colors:
                raise ValueError('Unexpected task instruction')
            seen[phase].update(colors)
            for i, color in enumerate(colors):
                values = batch[OBS_LANGUAGE_TOKENS][i].detach().cpu().tolist()
                tokens.setdefault(color, values)
            if phase == 'train':
                return forward(batch, *a, **kw)
            # Native SmolVLA mean weights each sample by its valid action entries.
            # Attribute those same numerators/denominators to each task.
            per_sample, info = forward(batch, reduction='none')
            vals = per_sample.detach().cpu().tolist()
            counts = ((~batch['action_is_pad']).sum(dim=1).detach().cpu().tolist()
                      if 'action_is_pad' in batch else [1] * len(vals))
            if not all(math.isfinite(v) for v in vals):
                raise RuntimeError('Nonfinite validation loss')
            for color, value, count in zip(colors, vals, counts):
                eval_records.append({'step': step_number, 'color': color,
                                     'loss': value, 'valid_steps': count})
            return per_sample.new_tensor(valid_weighted_mean(vals, counts)), info

        policy.forward = audited_forward
        return policy

    def update(*args, **kwargs):
        nonlocal step_number
        started = time.perf_counter()
        result = original_update(*args, **kwargs)
        step_number += 1
        metrics = result[0]
        row = {'step': step_number, 'loss': metrics.loss.val, 'gradient_norm': metrics.grad_norm.val,
               'lr': metrics.lr.val, 'update_seconds': time.perf_counter() - started,
               'gpu_peak_bytes': torch.cuda.max_memory_allocated()}
        if not all(math.isfinite(float(row[k])) for k in ('loss', 'gradient_norm', 'lr')):
            raise RuntimeError('Nonfinite training loss/gradient/lr')
        records.append(row)
        with (audit_dir / 'steps.jsonl').open('a') as f:
            f.write(json.dumps(row) + '\n')
        return result

    original_argv = sys.argv
    try:
        sys.argv = [sys.argv[0]]
        with scoped_overrides(trainer, make_train_eval_datasets=datasets, make_policy=make_policy,
                              make_pre_post_processors=processors, update_policy=update):
            trainer.train(cfg)
        if set(tokens) != {'green', 'red'} or tokens['green'] == tokens['red']:
            raise RuntimeError('Both distinct language inputs must be observed in training')
        result = {'passed': True, 'steps': step_number, 'batch_size': cfg.batch_size,
                  'split_contract': split_contract,
                  'seen': {k: dict(v) for k, v in seen.items()}, 'tokens': tokens,
                  'peak_gpu_bytes': max(r['gpu_peak_bytes'] for r in records),
                  'effective_epochs': cfg.steps * cfg.batch_size / split_contract['splits']['train']['frames'],
                  'normalization_stats_sha256': reference['stats_sha256'],
                  'evaluation': {}}
        by_key = defaultdict(list)
        for row in eval_records:
            by_key[(row['step'], row['color'])].append(row)
        for (step, color), values in by_key.items():
            result['evaluation'].setdefault(str(step), {})[color] = {
                'samples': len(values), 'valid_steps': sum(v['valid_steps'] for v in values),
                'loss': valid_weighted_mean([v['loss'] for v in values], [v['valid_steps'] for v in values])}
        (audit_dir / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        (audit_dir / 'validation-losses.json').write_text(json.dumps(eval_records) + '\n')
    finally:
        sys.argv = original_argv


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--validation-root', type=Path, required=True)
    p.add_argument('--audit', type=Path, required=True)
    a = p.parse_args()
    run(a.config, a.validation_root, a.audit)


if __name__ == '__main__':
    main()
