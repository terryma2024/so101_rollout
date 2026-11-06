"""Pure collection lifecycle and adapter requests, not a robot safety controller.

Only an adapter can fulfill effects and provide real readback evidence. In
particular, a transition or an evidence reference never verifies physical hold,
alignment, torque release, or scheduler invalidation. This module does no I/O.
Callers must serialize apply/check_timeout and execute termination effects even
when their own inference, telemetry, recording, or command operation raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class State(str, Enum):
    IDLE = 'idle'
    POLICY_EXECUTING = 'policy_executing'
    PAUSING = 'pausing'
    PAUSED_HOLDING = 'paused_holding'
    LEADER_ALIGNING = 'leader_aligning'
    READY = 'ready'
    EXPERT_CORRECTING = 'expert_correcting'
    WAIT_RELEASE = 'wait_release'
    COMPLETED = 'completed'
    ABORTED = 'aborted'


class EventKind(str, Enum):
    START_POLICY = 'start_policy'
    PAUSE_REQUESTED = 'pause_requested'
    HOLD_CONFIRMED = 'hold_confirmed'
    START_ALIGNMENT = 'start_alignment'
    ALIGNMENT_CONFIRMED = 'alignment_confirmed'
    START_EXPERT = 'start_expert'
    FINISH = 'finish'
    # Adapter has already received operator release request, supported the arm,
    # performed release, and verified readback. Never a request to release.
    RELEASE_CONFIRMED = 'release_confirmed'
    ABORT = 'abort'


class InvalidTransition(ValueError):
    """Rejected event; lifecycle state, revision, and generation are unchanged."""


@dataclass(frozen=True)
class Event:
    kind: EventKind
    expected_revision: int
    generation: int
    occurred_at: float
    evidence_ref: str | None = None


@dataclass(frozen=True)
class Transition:
    before: State
    after: State
    revision: int
    generation: int
    occurred_at: float
    event: EventKind
    evidence_ref: str | None
    effects: tuple[str, ...]


@dataclass(frozen=True)
class AlignmentReference:
    """Probe reference only; an adapter must independently measure every gate.

    Arm joints exclude gripper. This configuration does not evaluate telemetry,
    move a motor, or authorize expert commands; release/trigger readback remains
    a separate requirement after READY.
    """
    elbow_tolerance_degrees: float = 4.0
    other_joint_tolerance_degrees: float = 1.5
    stable_seconds: float = 1.0
    span_degrees: float = 0.35


_PAUSE_EFFECTS = ('scheduler_pause_and_invalidate', 'clear_policy_queue', 'hold_follower')
_FINISH_EFFECTS = ('scheduler_pause_and_invalidate', 'clear_policy_queue',
                   'stop_expert_commands', 'hold_follower')
_TERMINATE_EFFECTS = ('scheduler_pause_and_invalidate', 'clear_policy_queue',
                      'stop_expert_commands', 'hold_follower', 'request_safe_cleanup')
_EDGES = {
    (State.IDLE, EventKind.START_POLICY): State.POLICY_EXECUTING,
    (State.POLICY_EXECUTING, EventKind.PAUSE_REQUESTED): State.PAUSING,
    (State.PAUSING, EventKind.HOLD_CONFIRMED): State.PAUSED_HOLDING,
    (State.PAUSED_HOLDING, EventKind.START_ALIGNMENT): State.LEADER_ALIGNING,
    (State.LEADER_ALIGNING, EventKind.ALIGNMENT_CONFIRMED): State.READY,
    (State.READY, EventKind.START_EXPERT): State.EXPERT_CORRECTING,
    (State.POLICY_EXECUTING, EventKind.FINISH): State.WAIT_RELEASE,
    (State.EXPERT_CORRECTING, EventKind.FINISH): State.WAIT_RELEASE,
    (State.WAIT_RELEASE, EventKind.RELEASE_CONFIRMED): State.COMPLETED,
}
_EVIDENCE_EVENTS = frozenset((EventKind.HOLD_CONFIRMED, EventKind.ALIGNMENT_CONFIRMED,
                              EventKind.START_EXPERT, EventKind.RELEASE_CONFIRMED, EventKind.ABORT))
_TERMINAL = frozenset((State.COMPLETED, State.ABORTED))


def _finite_time(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


class CollectionStateMachine:
    """One episode, with no policy resumption after the first intervention.

    Local generation is a rejection token, not the scheduler's generation.
    An adapter must capture both, call scheduler.pause() (which increments its
    own generation and clears its queue), reject any pending policy command,
    and persist that mapping with readback evidence before HOLD_CONFIRMED.
    Current scheduler pause alone does not issue a physical hold command.
    """

    def __init__(self, *, event_max_age_seconds=0.5):
        if not _finite_time(event_max_age_seconds) or event_max_age_seconds <= 0:
            raise ValueError('event_max_age_seconds must be finite and positive')
        self.event_max_age_seconds = event_max_age_seconds
        self.state = State.IDLE
        self.revision = 0
        self.generation = 0
        self._last_now = None
        self._entered_at = None
        # Bounded operator/adapter waits, following existing probe defaults.
        self._timeouts = {State.PAUSING: 60.0, State.PAUSED_HOLDING: 60.0,
                          State.LEADER_ALIGNING: 45.0, State.READY: 30.0}

    def _validate_now(self, now):
        if not _finite_time(now) or (self._last_now is not None and now < self._last_now):
            raise InvalidTransition('control time must be finite and monotonic')

    def _expired(self, now):
        timeout = self._timeouts.get(self.state)
        return timeout is not None and now - self._entered_at >= timeout

    def accepts_policy_result(self, generation):
        """Offline eligibility only; never a hardware/scheduler guarantee."""
        return (type(generation) is int and generation == self.generation
                and self.state == State.POLICY_EXECUTING)

    def apply(self, event: Event, *, now: float) -> Transition:
        self._validate_now(now)
        if not isinstance(event, Event) or not isinstance(event.kind, EventKind):
            raise InvalidTransition('typed event required')
        if (type(event.expected_revision) is not int or event.expected_revision != self.revision
                or type(event.generation) is not int or event.generation != self.generation):
            raise InvalidTransition('stale or future revision/generation')
        if (not _finite_time(event.occurred_at) or event.occurred_at > now
                or now - event.occurred_at > self.event_max_age_seconds
                or (self._last_now is not None and event.occurred_at < self._last_now)):
            raise InvalidTransition('event time is stale, future, or nonfinite')
        if self.state in _TERMINAL:
            raise InvalidTransition('episode is terminal')
        if event.kind != EventKind.ABORT and self._expired(now):
            raise InvalidTransition('state deadline expired; abort/timeout cleanup required')
        if event.kind in _EVIDENCE_EVENTS:
            if not isinstance(event.evidence_ref, str) or not event.evidence_ref.strip():
                raise InvalidTransition('nonempty evidence reference required, not a boolean guarantee')
        after = State.ABORTED if event.kind == EventKind.ABORT else _EDGES.get((self.state, event.kind))
        if after is None:
            raise InvalidTransition(f'{event.kind.value} is illegal in {self.state.value}')
        effects = ()
        if event.kind == EventKind.PAUSE_REQUESTED:
            effects = _PAUSE_EFFECTS
        elif after == State.WAIT_RELEASE:
            effects = _FINISH_EFFECTS
        elif after == State.ABORTED:
            effects = _TERMINATE_EFFECTS
        before = self.state
        if effects:
            self.generation += 1
        self.state = after
        self.revision += 1
        self._entered_at = self._last_now = now
        return Transition(before, after, self.revision, self.generation,
                          event.occurred_at, event.kind, event.evidence_ref, effects)

    def fail(self, evidence_ref: str, *, now: float) -> Transition:
        """Record an exception/stop and REQUEST cleanup; execute it in the adapter."""
        return self.apply(Event(EventKind.ABORT, self.revision, self.generation, now,
                                evidence_ref), now=now)

    def check_timeout(self, *, now: float) -> Transition | None:
        """Explicit watchdog; callers must invoke it during waits, even without events."""
        self._validate_now(now)
        if self.state not in _TERMINAL and self._expired(now):
            return self.fail(f'timeout:{self.state.value}', now=now)
        self._last_now = now
        return None
