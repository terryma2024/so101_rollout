"""Offline validation/selection for a proposed DAgger format, not a capture adapter.

Only standard-library imports. Sent actions are returned motor targets, never a
claim that the follower reached that target. See the dated data contract.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import math

SCHEMA_VERSION = 'dagger-draft-1'
ACTION_KEYS = ('shoulder_pan.pos', 'shoulder_lift.pos', 'elbow_flex.pos',
               'wrist_flex.pos', 'wrist_roll.pos', 'gripper.pos')
ACTION_UNITS = ('degree',) * 5 + ('percent_0_100',)
STATES = frozenset(('idle', 'policy_executing', 'pausing', 'paused_holding',
                    'leader_aligning', 'ready', 'expert_correcting',
                    'wait_release', 'completed', 'aborted'))
CONTROL_SOURCES = frozenset(('none', 'policy', 'hold', 'alignment', 'expert'))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _vector(value: object, size: int) -> bool:
    return isinstance(value, (list, tuple)) and len(value) == size and all(_number(v) for v in value)


def validate_capture(manifest: Mapping, frames: Sequence[Mapping]) -> None:
    """Reject incomplete/unmapped draft captures and malformed control records.

    Ineligible but well-formed policy/hold/failed frames remain in the audit log.
    Unknown camera exposure times are permitted and must stay explicitly unknown.
    """
    _require(manifest.get('schema_version') == SCHEMA_VERSION, 'Unsupported draft schema')
    for key in ('source_session_id', 'episode_id', 'task', 'layout_id', 'case_id',
                'case_source', 'model_revision', 'mapping_evidence_ref'):
        _require(_text(manifest.get(key)), f'Missing manifest {key}')
    for key in ('capture_complete', 'action_mapping_verified', 'use_degrees'):
        _require(manifest.get(key) is True, f'{key} must be explicitly true')
    _require(manifest.get('clock') == 'host_monotonic_seconds', 'Unsupported clock')
    _require(manifest.get('action_semantics') == 'absolute_joint_target', 'Unproven action semantics')
    keys, units = manifest.get('action_keys'), manifest.get('action_units')
    _require(isinstance(keys, (list, tuple)) and tuple(keys) == ACTION_KEYS,
             'SO101 action keys must match canonical six-axis order')
    _require(isinstance(units, (list, tuple)) and tuple(units) == ACTION_UNITS,
             'SO101 action units must match body degrees and gripper percent')
    _require(manifest.get('observation_state_keys') == list(ACTION_KEYS),
             'Observation state ordering must match action ordering')
    previous_index, previous_time = -1, -math.inf
    segment_reviews = {}
    for frame in frames:
        index = frame.get('frame_index')
        _require(type(index) is int and index > previous_index, 'Frame indices must strictly increase')
        previous_index = index
        for key in ('segment_id', 'state', 'control_source', 'segment_review', 'segment_outcome'):
            _require(_text(frame.get(key)), f'Missing frame {key}')
        _require(frame['state'] in STATES, 'Unknown control state')
        _require(frame['control_source'] in CONTROL_SOURCES, 'Unknown control source')
        _require(frame['segment_review'] in ('pending', 'accepted', 'rejected'), 'Unknown review status')
        _require(frame['segment_outcome'] in ('unknown', 'success', 'failure', 'aborted'), 'Unknown segment outcome')
        review = (frame['segment_review'], frame['segment_outcome'], frame.get('review_evidence_ref'))
        segment_id = frame['segment_id']
        _require(segment_id not in segment_reviews or segment_reviews[segment_id] == review,
                 'Conflicting review/outcome within one segment')
        segment_reviews[segment_id] = review
        for key in ('state_revision', 'generation'):
            _require(type(frame.get(key)) is int and frame[key] >= 0, f'Invalid {key}')
        for key in ('boundary', 'send_succeeded', 'quality_valid'):
            _require(type(frame.get(key)) is bool, f'Missing boolean {key}')
        times = [frame.get(k) for k in ('observation_at', 'dispatch_started_at', 'dispatch_returned_at')]
        _require(all(_number(t) for t in times), 'Invalid host timestamps')
        _require(previous_time <= times[0] <= times[1] <= times[2], 'Invalid observation/dispatch ordering')
        previous_time = times[2]
        _require(frame.get('camera_time_kind') in ('unknown', 'measured_exposure'), 'Declare camera time kind')
        if frame['camera_time_kind'] == 'measured_exposure':
            _require(_text(frame.get('camera_timestamp_evidence_ref')), 'Exposure timestamp needs clock evidence')
            _require(_number(frame.get('camera_exposure_at')), 'Missing measured exposure timestamp')
        else:
            _require(frame.get('camera_exposure_at') is None, 'Unknown exposure cannot assert a timestamp')
            _require(frame.get('camera_timestamp_evidence_ref') is None, 'Unknown exposure cannot assert evidence')
        for key in ('observation_state', 'requested_action', 'processed_action'):
            _require(_vector(frame.get(key), len(keys)), f'Invalid {key}')
        if frame['send_succeeded']:
            _require(_vector(frame.get('sent_action'), len(keys)), 'Missing actual returned sent target')
        else:
            _require(frame.get('sent_action') is None, 'Failed dispatch cannot assert sent target')
        if frame['segment_review'] == 'accepted':
            _require(_text(frame.get('review_evidence_ref')), 'Acceptance needs review evidence')


def select_expert_chunks(manifest: Mapping, frames: Sequence[Mapping], *, horizon: int) -> list[tuple[int, ...]]:
    """Return overlapping full-horizon frame-index windows, without padding.

    Windows cannot cross a rejected frame, dropped index, transition revision,
    invalidation generation, or segment. This does not build a training dataset.
    """
    _require(type(horizon) is int and horizon > 0, 'horizon must be a positive integer')
    validate_capture(manifest, frames)
    chunks: list[tuple[int, ...]] = []
    run: list[int] = []
    previous_key = None
    for frame in frames:
        eligible = (frame['state'] == 'expert_correcting' and frame['control_source'] == 'expert'
                    and not frame['boundary'] and frame['send_succeeded'] and frame['quality_valid']
                    and frame['segment_review'] == 'accepted' and frame['segment_outcome'] == 'success')
        key = (frame['segment_id'], frame['state_revision'], frame['generation'])
        index = frame['frame_index']
        if not eligible or previous_key != key or (run and index != run[-1] + 1):
            run = []
        if eligible:
            run.append(index)
            if len(run) >= horizon:
                chunks.append(tuple(run[-horizon:]))
        previous_key = key
    return chunks


def validate_split_groups(assignments: Sequence[tuple[str, Mapping]]) -> None:
    """Reject train/validation/test leakage across episodes of a source session."""
    seen: dict[str, str] = {}
    for split, manifest in assignments:
        _require(split in ('train', 'val', 'test'), 'Unknown split')
        session = manifest.get('source_session_id')
        _require(_text(session), 'Missing source session')
        _require(session not in seen or seen[session] == split, 'Source session crosses dataset splits')
        seen[session] = split
