import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.train_smolvla import checked_stats_reference, scoped_overrides, bootstrap_config, valid_weighted_mean
from tools.guard_smolvla_training import check_tree, digest


def test_external_validation_cannot_point_at_other_statistics(tmp_path):
    train = tmp_path / 'train'
    val = tmp_path / 'val'
    (train / 'meta').mkdir(parents=True)
    (val / 'meta').mkdir(parents=True)
    (train / 'meta/stats.json').write_text('{}')
    (val / 'meta/normalization-reference.json').write_text(json.dumps({
        'fitted_split': 'validation', 'stats_path': str(train / 'meta/stats.json'), 'stats_sha256': 'wrong'}))
    with pytest.raises(ValueError, match='train-fitted'):
        checked_stats_reference(train, val)


def test_scoped_adapter_restores_factory_after_exception():
    module = SimpleNamespace(factory='original')
    with pytest.raises(RuntimeError):
        with scoped_overrides(module, factory='external-validation'):
            assert module.factory == 'external-validation'
            raise RuntimeError('trainer failed')
    assert module.factory == 'original'


def test_bootstrap_changes_paths_and_feature_contract_without_adding_camera3():
    base = {'load_vlm_weights': True, 'input_features': {'old': {}}, 'push_to_hub': True}
    result = bootstrap_config(base, Path('/fixed/vlm'))
    assert result['input_features']['observation.images.camera1']['shape'] == [3, 480, 640]
    assert result['input_features']['observation.images.camera2']['shape'] == [3, 480, 640]
    assert len(result['input_features']) == 3
    assert not result['load_vlm_weights'] and not result['push_to_hub']
    assert base['load_vlm_weights'] is True


def test_validation_matches_native_valid_entry_weighting():
    # Two samples with losses 1 and 3, but one and three valid timesteps.
    # A padded mean would wrongly return 1.25; unweighted would return 2.
    assert valid_weighted_mean([1, 3], [1, 3]) == 2.5
    assert valid_weighted_mean([1, 3], [0, 0]) == 0


def test_training_preflight_rejects_changed_dataset_or_model_content(tmp_path):
    f = tmp_path / 'weights'
    f.write_text('accepted')
    manifest = {'weights': {'size': f.stat().st_size, 'sha256': digest(f)}}
    check_tree(tmp_path, manifest)
    f.write_text('modified')
    with pytest.raises(RuntimeError, match='content changed'):
        check_tree(tmp_path, manifest)


def test_training_preflight_rejects_extra_members(tmp_path):
    (tmp_path / 'unexpected').write_text('extra')
    with pytest.raises(RuntimeError, match='membership changed'):
        check_tree(tmp_path, {})


@pytest.fixture
def external_split(tmp_path):
    import pandas as pd
    from tools.prepare_smolvla_data import numeric_digest
    records = []
    roots = {}
    for split in ('train', 'validation'):
        root = tmp_path / split
        roots[split] = root
        (root / 'meta').mkdir(parents=True)
        (root / 'data').mkdir()
        (root / 'meta/stats.json').write_text('{}')
        frames = []
        for episode, color in enumerate(('green', 'red')):
            # Different trajectories in all four source groups.
            value = episode + (10 if split == 'validation' else 0)
            frame = pd.DataFrame({'episode_index': [episode]*2, 'index': [episode*2, episode*2+1],
                                  'frame_index': [0, 1], 'task_index': [episode]*2,
                                  'action': [[value]*6, [value+1]*6],
                                  'observation.state': [[value]*6, [value+1]*6]})
            frames.append(frame)
            source = tmp_path / f'{split}-{color}-source'
            (source / 'data').mkdir(parents=True)
            frame.assign(episode_index=0).to_parquet(source / 'data/file.parquet', index=False)
            records.append({'split': split, 'color': color, 'task': f'Put the {color} cube into the paper bowl',
                            'group': source.name, 'origin': f'{source.name}:0',
                            'original_episode_index': 0, 'source_dataset': source.name,
                            'source_episode_index': 0, 'derived_episode_index': episode,
                            'numeric_sha256': numeric_digest(frame), 'frames': 2})
        pd.concat(frames).to_parquet(root / 'data/file.parquet', index=False)
        pd.DataFrame({'task_index': [0, 1]}, index=[f'Put the {c} cube into the paper bowl' for c in ('green', 'red')]).to_parquet(root / 'meta/tasks.parquet')
        (root / 'meta/info.json').write_text(json.dumps({'total_episodes': 2, 'total_frames': 4}))
    (roots['validation'] / 'meta/normalization-reference.json').write_text(json.dumps({
        'fitted_split': 'train', 'stats_path': str(roots['train'] / 'meta/stats.json'),
        'stats_sha256': digest(roots['train'] / 'meta/stats.json')}))
    manifest = tmp_path / 'split.json'
    manifest.write_text(json.dumps({'records': records}))
    return roots, manifest, records


def test_new_split_contract_uses_verified_actual_counts_and_frames(external_split):
    from tools.train_smolvla import checked_split_manifest
    roots, manifest, _ = external_split
    result = checked_split_manifest(roots['train'], roots['validation'], manifest)
    assert result['splits'] == {'train': {'episodes': 2, 'frames': 4},
                                'validation': {'episodes': 2, 'frames': 4}}
    assert result['manifest_sha256'] == digest(manifest)


@pytest.mark.parametrize('damage,match', [('frames', 'frames'), ('empty', 'both colors'),
    ('task', 'task'), ('mapping', 'episode'), ('overlap', 'crosses'), ('source', 'source')])
def test_split_contract_rejects_invalid_manifest(external_split, damage, match):
    from tools.train_smolvla import checked_split_manifest
    roots, manifest, records = external_split
    if damage == 'frames': records[0]['frames'] = 3
    if damage == 'empty': records = [r for r in records if r['split'] != 'validation']
    if damage == 'task': records[0]['task'] = 'Put the red cube into the paper bowl'
    if damage == 'mapping': records[0]['derived_episode_index'] = 9
    if damage == 'overlap': records[2]['group'] = records[0]['group']; records[2]['origin'] = records[0]['origin']
    if damage == 'source': records[0]['source_episode_index'] = 99
    manifest.write_text(json.dumps({'records': records}))
    with pytest.raises(ValueError, match=match):
        checked_split_manifest(roots['train'], roots['validation'], manifest)


def test_split_contract_rejects_actual_task_or_count_drift(external_split):
    import pandas as pd
    from tools.train_smolvla import checked_split_manifest
    roots, manifest, _ = external_split
    path = roots['train'] / 'data/file.parquet'
    frame = pd.read_parquet(path)
    frame.loc[0, 'task_index'] = 1
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match='task'):
        checked_split_manifest(roots['train'], roots['validation'], manifest)


def test_training_sidecar_binds_manifest_content_and_rejects_missing_v2(external_split):
    from tools.train_smolvla import checked_split_manifest, checked_training_split
    roots, manifest, _ = external_split
    config = manifest.parent / 'config.json'
    config.write_text('{}')
    with pytest.raises(ValueError, match='v1'):
        checked_training_split(config, roots['train'], roots['validation'])
    sidecar = config.with_suffix('.split.json')
    sidecar.write_text(json.dumps(checked_split_manifest(roots['train'], roots['validation'], manifest)))
    assert checked_training_split(config, roots['train'], roots['validation'])['splits']['train']['frames'] == 4
    manifest.write_text(manifest.read_text() + ' ')
    with pytest.raises(ValueError, match='manifest changed'):
        checked_training_split(config, roots['train'], roots['validation'])


def test_split_contract_rejects_metadata_count_drift(external_split):
    from tools.train_smolvla import checked_split_manifest
    roots, manifest, _ = external_split
    (roots['train'] / 'meta/info.json').write_text(json.dumps({'total_episodes': 3, 'total_frames': 4}))
    with pytest.raises(ValueError, match='counts'):
        checked_split_manifest(roots['train'], roots['validation'], manifest)


def test_preflight_requires_same_split_in_transfer_and_local_smoke(external_split):
    from tools.guard_smolvla_training import check_split_approval
    from tools.train_smolvla import checked_split_manifest
    roots, manifest, _ = external_split
    config = manifest.parent / 'config.json'
    contract = checked_split_manifest(roots['train'], roots['validation'], manifest)
    config.with_suffix('.split.json').write_text(json.dumps(contract))
    approved = {'split_manifest_sha256': digest(manifest), 'datasets': {
        label: dict(root=str(root), episodes=2, frames=4) for label, root in roots.items()}}
    smoke = {'split_manifest_sha256': digest(manifest)}
    check_split_approval(config, approved, smoke)
    smoke['split_manifest_sha256'] = 'different-smoke-split'
    with pytest.raises(RuntimeError, match='smoke'):
        check_split_approval(config, approved, smoke)
    smoke['split_manifest_sha256'] = digest(manifest)
    approved['split_manifest_sha256'] = 'different-transfer'
    with pytest.raises(RuntimeError, match='transferred'):
        check_split_approval(config, approved, smoke)


def test_shared_capture_group_may_have_separate_color_source_folders(external_split):
    from tools.train_smolvla import checked_split_manifest
    roots, manifest, records = external_split
    for row in records:
        row['group'] = row['split'] + '-shared-capture-session'
    manifest.write_text(json.dumps({'records': records}))
    assert checked_split_manifest(roots['train'], roots['validation'], manifest)['splits']['train']['episodes'] == 2


def test_shared_capture_group_cannot_cross_split(external_split):
    from tools.train_smolvla import checked_split_manifest
    roots, manifest, records = external_split
    records[0]['group'] = records[2]['group'] = 'one-shared-capture-session'
    manifest.write_text(json.dumps({'records': records}))
    with pytest.raises(ValueError, match='crosses'):
        checked_split_manifest(roots['train'], roots['validation'], manifest)


def test_split_contract_rejects_forged_original_episode_identity(external_split):
    from tools.train_smolvla import checked_split_manifest
    roots, manifest, records = external_split
    records[0]['original_episode_index'] = 99
    records[0]['origin'] = records[0]['source_dataset'] + ':99'
    manifest.write_text(json.dumps({'records': records}))
    with pytest.raises(ValueError, match='source identity'):
        checked_split_manifest(roots['train'], roots['validation'], manifest)


def test_source_folder_cannot_claim_two_capture_groups(external_split):
    from tools.train_smolvla import checked_split_manifest
    roots, manifest, records = external_split
    import pandas as pd
    source = manifest.parent / records[0]['source_dataset'] / 'data/file.parquet'
    extra = pd.read_parquet(manifest.parent / records[2]['source_dataset'] / 'data/file.parquet')
    pd.concat([pd.read_parquet(source), extra.assign(episode_index=1)]).to_parquet(source, index=False)
    records[2].update(source_dataset=records[0]['source_dataset'], source_episode_index=1,
                      original_episode_index=1, origin=records[0]['source_dataset'] + ':1')
    manifest.write_text(json.dumps({'records': records}))
    with pytest.raises(ValueError, match='source.*group'):
        checked_split_manifest(roots['train'], roots['validation'], manifest)
