"""Offline control contracts; no robot, inference, or driver imports."""
import math

import pytest

from so101_rollout.dagger.state import (
    CollectionStateMachine, Event, EventKind, InvalidTransition, State,
)


def send(machine, kind, at=0.0, evidence_ref=None):
    return machine.apply(Event(kind, machine.revision, machine.generation, at, evidence_ref), now=at)


def reach_ready(machine):
    send(machine, EventKind.START_POLICY)
    send(machine, EventKind.PAUSE_REQUESTED)
    send(machine, EventKind.HOLD_CONFIRMED, evidence_ref='offline:hold-fixture')
    send(machine, EventKind.START_ALIGNMENT)
    return send(machine, EventKind.ALIGNMENT_CONFIRMED, evidence_ref='offline:alignment-fixture')


def test_takeover_orders_pause_hold_alignment_ready_and_expert():
    machine = CollectionStateMachine()
    assert machine.state == State.IDLE
    send(machine, EventKind.START_POLICY)
    assert machine.accepts_policy_result(0)
    paused = send(machine, EventKind.PAUSE_REQUESTED)
    assert paused.after == State.PAUSING
    assert paused.generation == 1
    assert paused.effects == ('scheduler_pause_and_invalidate', 'clear_policy_queue', 'hold_follower')
    assert not machine.accepts_policy_result(0)
    assert not machine.accepts_policy_result(1)
    send(machine, EventKind.HOLD_CONFIRMED, evidence_ref='offline:hold-fixture')
    assert machine.state == State.PAUSED_HOLDING
    send(machine, EventKind.START_ALIGNMENT)
    send(machine, EventKind.ALIGNMENT_CONFIRMED, evidence_ref='offline:alignment-fixture')
    assert machine.state == State.READY
    send(machine, EventKind.START_EXPERT, evidence_ref='offline:trigger-and-release-fixture')
    assert machine.state == State.EXPERT_CORRECTING
    result = send(machine, EventKind.FINISH)
    assert result.after == State.WAIT_RELEASE
    assert result.generation == 2
    send(machine, EventKind.RELEASE_CONFIRMED, evidence_ref='offline:supported-release-readback')
    assert machine.state == State.COMPLETED
    assert 'stop_expert_commands' in result.effects
    assert not machine.accepts_policy_result(2)


@pytest.mark.parametrize('kind', [EventKind.START_EXPERT, EventKind.ALIGNMENT_CONFIRMED,
                                EventKind.HOLD_CONFIRMED, EventKind.FINISH])
def test_illegal_first_event_does_not_mutate_state(kind):
    machine = CollectionStateMachine()
    with pytest.raises(InvalidTransition):
        send(machine, kind, evidence_ref='offline:fixture')
    assert (machine.state, machine.revision, machine.generation) == (State.IDLE, 0, 0)


def test_policy_cannot_resume_after_takeover_or_after_completion():
    machine = CollectionStateMachine()
    reach_ready(machine)
    for kind in (EventKind.START_POLICY, EventKind.PAUSE_REQUESTED, EventKind.FINISH):
        with pytest.raises(InvalidTransition):
            send(machine, kind)
    send(machine, EventKind.START_EXPERT, evidence_ref='offline:fixture')
    send(machine, EventKind.FINISH)
    send(machine, EventKind.RELEASE_CONFIRMED, evidence_ref='offline:supported-release-readback')
    for kind in EventKind:
        with pytest.raises(InvalidTransition):
            send(machine, kind, evidence_ref='offline:fixture')


def test_policy_episode_can_finish_without_intervention():
    machine = CollectionStateMachine()
    send(machine, EventKind.START_POLICY)
    result = send(machine, EventKind.FINISH)
    assert result.after == State.WAIT_RELEASE
    assert result.generation == 1
    send(machine, EventKind.RELEASE_CONFIRMED, evidence_ref='offline:supported-release-readback')
    assert machine.state == State.COMPLETED
    assert not machine.accepts_policy_result(0)


@pytest.mark.parametrize('revision,generation', [(0, 0), (2, 0), (1, 1)])
def test_stale_or_future_tokens_rejected(revision, generation):
    machine = CollectionStateMachine()
    send(machine, EventKind.START_POLICY)
    with pytest.raises(InvalidTransition):
        machine.apply(Event(EventKind.PAUSE_REQUESTED, revision, generation, 0), now=0)
    assert machine.state == State.POLICY_EXECUTING
    assert machine.accepts_policy_result(0)


@pytest.mark.parametrize('evidence', [None, '', '  ', True])
def test_hold_confirmation_requires_traceable_evidence_reference(evidence):
    machine = CollectionStateMachine()
    send(machine, EventKind.START_POLICY)
    send(machine, EventKind.PAUSE_REQUESTED)
    with pytest.raises(InvalidTransition):
        send(machine, EventKind.HOLD_CONFIRMED, evidence_ref=evidence)
    assert machine.state == State.PAUSING


@pytest.mark.parametrize('kind', [EventKind.ALIGNMENT_CONFIRMED, EventKind.START_EXPERT])
def test_alignment_and_release_trigger_require_evidence(kind):
    machine = CollectionStateMachine()
    reach_ready(machine) if kind == EventKind.START_EXPERT else None
    if kind == EventKind.ALIGNMENT_CONFIRMED:
        send(machine, EventKind.START_POLICY)
        send(machine, EventKind.PAUSE_REQUESTED)
        send(machine, EventKind.HOLD_CONFIRMED, evidence_ref='offline:fixture')
        send(machine, EventKind.START_ALIGNMENT)
    before = machine.state
    with pytest.raises(InvalidTransition):
        send(machine, kind)
    assert machine.state == before


@pytest.mark.parametrize('occurred_at,now', [(0, .501), (1, 0), (math.nan, 0), (0, math.inf)])
def test_expired_future_and_nonfinite_events_are_rejected(occurred_at, now):
    machine = CollectionStateMachine()
    with pytest.raises(InvalidTransition):
        machine.apply(Event(EventKind.START_POLICY, 0, 0, occurred_at), now=now)
    assert machine.state == State.IDLE


def test_freshness_boundary_and_monotonic_control_clock():
    machine = CollectionStateMachine()
    machine.apply(Event(EventKind.START_POLICY, 0, 0, 1), now=1.5)
    with pytest.raises(InvalidTransition):
        send(machine, EventKind.PAUSE_REQUESTED, at=1.4)
    assert machine.state == State.POLICY_EXECUTING


@pytest.mark.parametrize('phase', ['policy', 'pausing', 'ready', 'expert'])
def test_failure_always_requests_safe_termination(phase):
    machine = CollectionStateMachine()
    if phase in ('ready', 'expert'):
        reach_ready(machine)
        if phase == 'expert':
            send(machine, EventKind.START_EXPERT, evidence_ref='offline:fixture')
    else:
        send(machine, EventKind.START_POLICY)
        if phase == 'pausing':
            send(machine, EventKind.PAUSE_REQUESTED)
    generation = machine.generation
    result = machine.fail('offline:injected-exception', now=1)
    assert result.after == State.ABORTED
    assert result.generation == generation + 1
    assert result.effects == ('scheduler_pause_and_invalidate', 'clear_policy_queue',
                              'stop_expert_commands', 'hold_follower', 'request_safe_cleanup')
    assert not machine.accepts_policy_result(generation)
    with pytest.raises(InvalidTransition):
        send(machine, EventKind.START_POLICY, at=1)


def test_timed_out_alignment_cannot_be_confirmed_and_watchdog_aborts():
    machine = CollectionStateMachine()
    send(machine, EventKind.START_POLICY)
    send(machine, EventKind.PAUSE_REQUESTED)
    send(machine, EventKind.HOLD_CONFIRMED, evidence_ref='offline:fixture')
    send(machine, EventKind.START_ALIGNMENT)
    with pytest.raises(InvalidTransition):
        send(machine, EventKind.ALIGNMENT_CONFIRMED, at=45, evidence_ref='offline:late')
    assert machine.state == State.LEADER_ALIGNING
    result = machine.check_timeout(now=45)
    assert result.after == State.ABORTED
    assert machine.check_timeout(now=46) is None


def test_watchdog_does_not_abort_before_deadline():
    machine = CollectionStateMachine()
    reach_ready(machine)
    assert machine.check_timeout(now=29.999) is None
    assert machine.check_timeout(now=30).after == State.ABORTED


def test_release_confirmation_requires_evidence_and_cannot_be_skipped():
    machine = CollectionStateMachine()
    reach_ready(machine)
    send(machine, EventKind.START_EXPERT, evidence_ref='offline:trigger-release')
    send(machine, EventKind.FINISH)
    assert machine.state == State.WAIT_RELEASE
    with pytest.raises(InvalidTransition):
        send(machine, EventKind.RELEASE_CONFIRMED)
    with pytest.raises(InvalidTransition):
        send(machine, EventKind.START_POLICY)
    send(machine, EventKind.RELEASE_CONFIRMED, evidence_ref='offline:operator-support-and-torque-readback')
    assert machine.state == State.COMPLETED


def test_urgent_failure_uses_current_tokens_even_after_stale_event_rejection():
    machine = CollectionStateMachine()
    send(machine, EventKind.START_POLICY)
    send(machine, EventKind.PAUSE_REQUESTED)
    with pytest.raises(InvalidTransition):
        machine.apply(Event(EventKind.HOLD_CONFIRMED, 1, 0, 0, 'offline:stale'), now=0)
    assert machine.fail('offline:urgent-stop', now=0).after == State.ABORTED


def test_normal_finish_holds_without_cleanup_or_operator_release_deadline():
    machine = CollectionStateMachine()
    reach_ready(machine)
    send(machine, EventKind.START_EXPERT, evidence_ref='offline:fixture')
    result = send(machine, EventKind.FINISH)
    assert result.effects == ('scheduler_pause_and_invalidate', 'clear_policy_queue',
                              'stop_expert_commands', 'hold_follower')
    assert machine.check_timeout(now=3600) is None
    assert machine.state == State.WAIT_RELEASE
    send(machine, EventKind.RELEASE_CONFIRMED, at=3600,
         evidence_ref='offline:operator-request-supported-release-verified')
    assert machine.state == State.COMPLETED
