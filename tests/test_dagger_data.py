"""Pure offline draft-format tests; no capture adapter is implied."""
from copy import deepcopy
import pytest
from so101_rollout.dagger.data import ACTION_KEYS, ACTION_UNITS, validate_capture, select_expert_chunks, validate_split_groups


def fixture():
    manifest = dict(schema_version='dagger-draft-1', source_session_id='session-a',
        episode_id='ep-1', task='green cube to bowl', layout_id='layout-1',
        case_id='case-1', case_source='frozen-baseline:trial-1',
        model_revision='sha256:checkpoint', capture_complete=True,
        action_mapping_verified=True, action_keys=list(ACTION_KEYS), observation_state_keys=list(ACTION_KEYS),
        action_units=list(ACTION_UNITS), use_degrees=True,
        action_semantics='absolute_joint_target', clock='host_monotonic_seconds',
        mapping_evidence_ref='offline:fixture')
    frames = [dict(frame_index=i, segment_id='correction-1', state='expert_correcting',
        state_revision=5, generation=1, control_source='expert', boundary=False,
        observation_at=i * .05, dispatch_started_at=i * .05 + .01,
        dispatch_returned_at=i * .05 + .02, camera_time_kind='unknown',
        observation_state=[0.] * 6, requested_action=[2.] * 6,
        processed_action=[2.] * 6, sent_action=[1.] * 6, send_succeeded=True,
        segment_review='accepted', segment_outcome='success',
        review_evidence_ref='offline:review', quality_valid=True) for i in range(6)]
    return manifest, frames


def test_sent_target_is_distinct_from_requested_and_measured_state():
    manifest, frames = fixture()
    validate_capture(manifest, frames)
    assert select_expert_chunks(manifest, frames, horizon=3) == [(0, 1, 2), (1, 2, 3), (2, 3, 4), (3, 4, 5)]


@pytest.mark.parametrize('field,value', [('control_source', 'policy'), ('state', 'paused_holding'),
    ('state', 'leader_aligning'), ('boundary', True), ('quality_valid', False), ('send_succeeded', False)])
def test_excludes_ineligible_frame_and_prevents_crossing_it(field, value):
    manifest, frames = fixture()
    frames[2][field] = value
    if field == 'send_succeeded': frames[2]['sent_action'] = None
    assert select_expert_chunks(manifest, frames, horizon=3) == [(3, 4, 5)]


@pytest.mark.parametrize('field,value', [('segment_id', 'next'), ('state_revision', 6), ('generation', 2)])
def test_chunks_never_cross_control_segment_or_transition(field, value):
    manifest, frames = fixture()
    for frame in frames[3:]: frame[field] = value
    assert select_expert_chunks(manifest, frames, horizon=3) == [(0, 1, 2), (3, 4, 5)]


def test_frame_gap_is_not_filled_or_padded():
    manifest, frames = fixture()
    del frames[2]
    assert select_expert_chunks(manifest, frames, horizon=3) == [(3, 4, 5)]


@pytest.mark.parametrize('field,value', [('capture_complete', False), ('action_mapping_verified', False),
    ('action_semantics', 'raw_ticks'), ('use_degrees', False), ('model_revision', ''),
    ('mapping_evidence_ref', '')])
def test_unproven_mapping_and_incomplete_capture_are_rejected(field, value):
    manifest, frames = fixture()
    manifest[field] = value
    with pytest.raises(ValueError): select_expert_chunks(manifest, frames, horizon=3)


@pytest.mark.parametrize('mutation', ['nan', 'dimensions', 'time_order', 'duplicate_index', 'missing_sent'])
def test_bad_capture_fails_closed(mutation):
    manifest, frames = fixture()
    if mutation == 'nan': frames[0]['sent_action'][0] = float('nan')
    if mutation == 'dimensions': frames[0]['processed_action'] = [0]
    if mutation == 'time_order': frames[0]['dispatch_returned_at'] = -1
    if mutation == 'duplicate_index': frames[1]['frame_index'] = 0
    if mutation == 'missing_sent': del frames[0]['sent_action']
    with pytest.raises(ValueError): validate_capture(manifest, frames)


def test_split_group_is_source_session_not_episode():
    manifest, _ = fixture()
    other = deepcopy(manifest); other['episode_id'] = 'ep-2'
    validate_split_groups([('train', manifest), ('train', other)])
    with pytest.raises(ValueError): validate_split_groups([('train', manifest), ('val', other)])


def test_horizon_must_be_positive_integer():
    manifest, frames = fixture()
    for horizon in [0, -1, True, 1.5]:
        with pytest.raises(ValueError): select_expert_chunks(manifest, frames, horizon=horizon)


@pytest.mark.parametrize('field,value', [('segment_review', 'pending'), ('segment_outcome', 'failure')])
def test_unaccepted_or_failed_segment_is_never_automatically_expert(field, value):
    manifest, frames = fixture()
    for frame in frames: frame[field] = value
    assert select_expert_chunks(manifest, frames, horizon=3) == []
    frames[0][field] = 'conflicting'
    with pytest.raises(ValueError): validate_capture(manifest, frames)


@pytest.mark.parametrize('field,value', [
    ('action_keys', list(ACTION_KEYS[:-1])),
    ('action_keys', list(ACTION_KEYS) + ['extra.pos']),
    ('action_keys', list(reversed(ACTION_KEYS))),
    ('action_keys', ['wrong.pos'] + list(ACTION_KEYS[1:])),
    ('action_units', ['degree'] * 6),
    ('action_units', ['percent_0_100'] * 6),
    ('observation_state_keys', list(reversed(ACTION_KEYS))),
])
def test_so101_mapping_rejects_wrong_units_missing_extra_or_reordered_axes(field, value):
    manifest, frames = fixture()
    manifest[field] = value
    with pytest.raises(ValueError): validate_capture(manifest, frames)


@pytest.mark.parametrize('field,value', [('state', 'expert_correting'),
    ('control_source', 'teleop'), ('camera_exposure_at', 0.01),
    ('camera_timestamp_evidence_ref', 'claimed:exposure')])
def test_unknown_enum_or_exposure_claim_rejected(field, value):
    manifest, frames = fixture()
    frames[0][field] = value
    with pytest.raises(ValueError): validate_capture(manifest, frames)
