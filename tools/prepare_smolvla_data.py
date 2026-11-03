#!/usr/bin/env python3
"""Prepare audited two-task SO101 data using whole source-folder holdouts.

This experiment-specific exporter uses LeRobot 0.6.1 aggregation. Sources remain
read-only; all repairs affect independent copies. Validation's descriptive stats
are retained; its normalization reference explicitly points to training stats.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import re


TASKS = {'green': 'Put the green cube into the paper bowl',
         'red': 'Put the red cube into the paper bowl'}
SOURCES = [
    ('train', 'real-cube-bowl-pilot-20261027', 'green', 0),
    ('train', 'real-cube-bowl-p2-green-20261030', 'green', 93),
    ('train', 'real-cube-bowl-p2-green-extra-clean-20261030', 'green', 103),
    ('train', 'real-cube-bowl-red-clean-20261028', 'red', 0),
    ('train', 'real-cube-bowl-p2-red-extra-20261030', 'red', 112),
    ('validation', 'real-cube-bowl-adjacent-20261028', 'green', 61),
    ('validation', 'real-cube-bowl-p2-red-20261030', 'red', 92),
]
REMAPPED_FIELDS = {'index', 'episode_index', 'frame_index', 'task_index'}


def origin_episode(name, index):
    if name == 'real-cube-bowl-red-clean-20261028':
        return index + (index >= 10)
    if name == 'real-cube-bowl-p2-green-extra-clean-20261030':
        return index + (index >= 2)
    return index


def validate_split(records):
    for key, label in [('group', 'group'), ('origin', 'origin'),
                       ('numeric_sha256', 'trajectory')]:
        owners = {}
        for row in records:
            old = owners.setdefault(row[key], row['split'])
            if old != row['split']:
                raise ValueError(f'{label} crosses train/validation: {row[key]}')
    for split in ('train', 'validation'):
        if {r['color'] for r in records if r['split'] == split} != set(TASKS):
            raise ValueError(f'{split} must contain both colors')


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def manifest(root):
    return {str(p.relative_to(root)): {'size': p.stat().st_size, 'sha256': sha256(p)}
            for p in sorted(root.rglob('*')) if p.is_file()}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def read_tables(root, sub):
    import pandas as pd
    return pd.concat([pd.read_parquet(p) for p in sorted((root/sub).rglob('*.parquet'))],
                     ignore_index=True)


def numeric_digest(frame):
    import numpy as np
    h = hashlib.sha256()
    for key in sorted(set(frame.columns) - REMAPPED_FIELDS):
        values = np.stack(frame[key].to_numpy()).astype('<f8')
        if not np.isfinite(values).all():
            raise ValueError(f'Nonfinite {key}')
        h.update(json.dumps([key, list(values.shape)]).encode())
        h.update(values.tobytes())
    return h.hexdigest()


def repair_self_pointers(root):
    import pandas as pd
    changes = []
    for path in sorted((root/'meta/episodes').rglob('*.parquet')):
        data = pd.read_parquet(path)
        chunk = int(re.fullmatch(r'chunk-(\d+)', path.parent.name)[1])
        file = int(re.fullmatch(r'file-(\d+)\.parquet', path.name)[1])
        for key, value in [('meta/episodes/chunk_index', chunk),
                           ('meta/episodes/file_index', file)]:
            bad = data[key] != value
            if bad.any():
                changes.append({'file': str(path.relative_to(root)), 'field': key,
                                'episodes': data.loc[bad, 'episode_index'].tolist(), 'new': value})
                data[key] = value
        data.to_parquet(path, index=False)
    return changes


def recompute_stats(root):
    import numpy as np
    import pandas as pd
    from lerobot.datasets.compute_stats import aggregate_stats, compute_episode_stats
    from lerobot.datasets.io_utils import write_stats
    info = json.loads((root/'meta/info.json').read_text())
    features = {k: v for k, v in info['features'].items()
                if v['dtype'] not in ('video', 'image', 'string')}
    frame = read_tables(root, 'data')
    episode_stats = {}
    for index, rows in frame.groupby('episode_index'):
        episode_stats[int(index)] = compute_episode_stats(
            {k: np.stack(rows[k].to_numpy()).astype(np.float64) for k in features}, features)
    for path in (root/'meta/episodes').rglob('*.parquet'):
        data = pd.read_parquet(path)
        for index, row in data.iterrows():
            for key, stats in episode_stats[int(row.episode_index)].items():
                for stat, value in stats.items():
                    data.at[index, f'stats/{key}/{stat}'] = np.asarray(value).tolist()
        data.to_parquet(path, index=False)
    # Image summaries already contain only the corresponding split's episodes.
    stats = json.loads((root/'meta/stats.json').read_text())
    stats.update(aggregate_stats(list(episode_stats.values())))
    write_stats(stats, root)
    return frame


def verify_statistics(root):
    """Check every numeric feature directly and split-local image summaries."""
    import numpy as np
    from lerobot.datasets.compute_stats import aggregate_stats
    frame = read_tables(root, 'data')
    info = json.loads((root/'meta/info.json').read_text())
    stats = json.loads((root/'meta/stats.json').read_text())
    checked = []
    for key, feature in info['features'].items():
        if feature['dtype'] in ('video', 'image', 'string'):
            continue
        values = np.stack(frame[key].to_numpy()).astype(np.float64)
        for name, actual in [('mean', values.mean(0)), ('std', values.std(0)),
                             ('min', values.min(0)), ('max', values.max(0))]:
            assert np.allclose(stats[key][name], actual, rtol=1e-6, atol=1e-6), (key, name)
        assert int(stats[key]['count'][0]) == len(frame)
        checked.append(key)
    def nested(value):
        if isinstance(value, (list, tuple, np.ndarray)):
            return [nested(v) for v in value]
        return value
    summaries = []
    for _, row in read_tables(root, 'meta/episodes').iterrows():
        summary = {}
        for key, value in row.items():
            if key.startswith('stats/observation.images.'):
                _, feature, stat = key.split('/')
                summary.setdefault(feature, {})[stat] = np.asarray(nested(value), dtype=float)
        summaries.append(summary)
    images = aggregate_stats(summaries)
    for key, values in images.items():
        for stat, value in values.items():
            assert np.allclose(stats[key][stat], value, rtol=1e-5, atol=1e-6), (key, stat)
    return {'passed': True, 'numeric_features': checked, 'image_features': list(images),
            'image_episode_summaries': len(summaries),
            'method': 'direct float64 numeric fit and split-local image summary aggregate'}


def verify_dataset(root, records, approved):
    import numpy as np
    import av
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    frame = read_tables(root, 'data').sort_values('index').reset_index(drop=True)
    episodes = read_tables(root, 'meta/episodes').sort_values('episode_index')
    info = json.loads((root/'meta/info.json').read_text())
    if len(records) != len(episodes) or info['fps'] != 20:
        raise ValueError('Episode count or fps mismatch')
    assert np.array_equal(frame['index'], np.arange(len(frame)))
    assert np.array_equal(episodes.episode_index, np.arange(len(records)))
    tasks = __import__('pandas').read_parquet(root/'meta/tasks.parquet')
    task_map = {int(row.task_index): str(index) for index, row in tasks.iterrows()}
    for new_index, record in enumerate(records):
        data = frame[frame.episode_index == new_index]
        expected = approved[record['color']]
        expected = expected[expected.episode_index == record['approved_episode_index']]
        assert numeric_digest(data) == record['numeric_sha256'] == numeric_digest(expected)
        assert all(task_map[int(i)] == TASKS[record['color']] for i in data.task_index)
        assert np.array_equal(data.frame_index, np.arange(len(data)))
        meta = episodes.iloc[new_index]
        assert int(meta.dataset_to_index - meta.dataset_from_index) == len(data)
        record['derived_episode_index'] = new_index
        record['frames'] = len(data)
    statistics = verify_statistics(root)
    videos = []
    for key, feature in info['features'].items():
        if feature['dtype'] != 'video':
            continue
        for (chunk, file), rows in episodes.groupby(
                [f'videos/{key}/chunk_index', f'videos/{key}/file_index']):
            path = root/info['video_path'].format(video_key=key, chunk_index=int(chunk), file_index=int(file))
            timestamps = []
            with av.open(str(path)) as container:
                stream = container.streams.video[0]
                assert (stream.width, stream.height) == (640, 480)
                for image in container.decode(video=0):
                    timestamps.append(float(image.pts * image.time_base))
            pts = np.asarray(timestamps)
            for _, row in rows.iterrows():
                start, end = row[f'videos/{key}/from_timestamp'], row[f'videos/{key}/to_timestamp']
                valid = pts[(pts >= start-1e-5) & (pts < end-1e-5)]
                assert len(valid) == row.length
                assert abs(valid[0]-start) < .001 and abs(valid[-1]-(end-.05)) < .001
            assert len(pts) == rows.length.sum()
            videos.append({'path': str(path.relative_to(root)), 'frames': len(pts)})
            print('decoded', root.name, key, file, len(pts), flush=True)
    dataset = LeRobotDataset('local/'+root.name, root=root, video_backend='pyav', download_videos=False)
    for _, row in episodes.iterrows():
        for index in (int(row.dataset_from_index), int(row.dataset_to_index)-1):
            sample = dataset[index]
            assert sample['action'].shape == sample['observation.state'].shape == (6,)
            assert sample['task'] in TASKS.values()
            for cam in ('wrist', 'side'):
                assert sample['observation.images.'+cam].shape == (3, 480, 640)
    colors = {color: {'episodes': sum(r['color'] == color for r in records),
                      'frames': sum(r['frames'] for r in records if r['color'] == color)} for color in TASKS}
    return {'passed': True, 'root': str(root), 'episodes': len(records), 'frames': len(frame),
            'colors': colors, 'tasks': task_map, 'videos': videos,
            'all_loader_boundaries': len(records)*2, 'numeric_exact': True,
            'descriptive_numeric_stats_verified': True, 'statistics': statistics}


def main():
    from lerobot.datasets.aggregate import aggregate_datasets
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datasets-root', type=Path, default=Path('/data/work/so101-datasets'))
    parser.add_argument('--train-root', type=Path, required=True)
    parser.add_argument('--validation-root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    outputs = {'train': args.train_root, 'validation': args.validation_root}
    if args.evidence.exists() or any(p.exists() for p in outputs.values()):
        parser.error('Use fresh evidence and dataset output paths')
    if len({p.resolve() for p in outputs.values()}) != 2:
        parser.error('Train and validation output paths must differ')
    args.evidence.mkdir(parents=True)
    base, evidence = args.datasets_root, args.evidence
    approved = {c: read_tables(base/f'real-cube-bowl-{c}-p2-merged-20261030', 'data') for c in TASKS}
    sources_before = {name: manifest(base/name) for _, name, _, _ in SOURCES}
    save(evidence/'sources-before.json', sources_before)
    records = []
    for split, name, color, offset in SOURCES:
        data = read_tables(base/name, 'data')
        for old_index, frame in data.groupby('episode_index', sort=True):
            old_index = int(old_index)
            digest = numeric_digest(frame)
            accepted = approved[color]
            accepted = accepted[accepted.episode_index == offset+old_index]
            assert digest == numeric_digest(accepted), (name, old_index)
            original_name = name.replace('extra-clean-', 'extra-').replace('red-clean-', 'red-')
            origin = origin_episode(name, old_index)
            records.append({'split': split, 'color': color, 'group': original_name,
                            'source_dataset': name, 'source_episode_index': old_index,
                            'origin': f'{original_name}:{origin}', 'original_episode_index': origin,
                            'approved_dataset': f'real-cube-bowl-{color}-p2-merged-20261030',
                            'approved_episode_index': offset+old_index,
                            'numeric_sha256': digest, 'frames': len(frame), 'task': TASKS[color]})
    validate_split(records)
    save(evidence/'split.json', {'records': records,
         'group_basis': 'whole source recording dataset/folder; not layout/day held-out',
         'cross_split_numeric_duplicates': 0, 'approved_episodes': 266})
    print('split frozen', {s: sum(r['split']==s for r in records) for s in outputs}, flush=True)
    views = evidence/'source-views'
    repairs = {}
    for _, name, _, _ in SOURCES:
        view = views/name
        shutil.copytree(base/name, view)
        repairs[name] = repair_self_pointers(view)
    save(evidence/'source-view-repairs.json', repairs)
    reports = {}
    for split, out in outputs.items():
        names = [name for s, name, _, _ in SOURCES if s == split]
        aggregate_datasets(['local/'+n for n in names], 'local/'+out.name,
                           roots=[views/n for n in names], aggr_root=out)
        save(evidence/(split+'-final-pointer-repairs.json'), repair_self_pointers(out))
        recompute_stats(out)
        selected = [r for r in records if r['split'] == split]
        reports[split] = verify_dataset(out, selected, approved)
        save(evidence/(split+'-verification.json'), reports[split])
        print('verified', split, flush=True)
    reference = {'fitted_split': 'train', 'stats_path': str(args.train_root/'meta/stats.json'),
                 'stats_sha256': sha256(args.train_root/'meta/stats.json'),
                 'validation_descriptive_stats': 'meta/stats.json retained for auditing only',
                 'validation_forward': 'must reuse the train-fitted pre/post processors'}
    save(args.validation_root/'meta/normalization-reference.json', reference)
    save(evidence/'normalization-reference.json', reference)
    save(evidence/'episode-map.json', records)
    after = {name: manifest(base/name) for _, name, _, _ in SOURCES}
    assert sources_before == after, 'Source file membership or content changed'
    save(evidence/'sources-unchanged.json', {'passed': True, 'files': sum(map(len, after.values()))})
    files = {s: manifest(root) for s, root in outputs.items()}
    save(evidence/'dataset-files-sha256.json', files)
    save(evidence/'dataset-approved.json', {'passed': True, 'datasets': reports,
         'normalization': reference, 'source_files_unchanged': True,
         'split_manifest_sha256': sha256(evidence/'split.json'),
         'files_manifest': str(evidence/'dataset-files-sha256.json'),
         'files_manifest_sha256': sha256(evidence/'dataset-files-sha256.json'),
         'notes': ['No P0 rollout data.', 'No claims of layout/day-independent holdout.',
                   'Validation uses train-fitted processors; its own stats are descriptive.',
                   'Image summaries aggregated only within each split from original accepted episodes.']})
    print('APPROVED', evidence/'dataset-approved.json', flush=True)


if __name__ == '__main__':
    main()
