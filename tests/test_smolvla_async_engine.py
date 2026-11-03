"""Concurrency contracts for the real rollout backend, without robot/model I/O."""
import importlib
import threading
import time

import pytest


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


def wait_until(predicate):
    deadline = time.monotonic() + 2
    while not predicate():
        assert time.monotonic() < deadline, "worker did not complete"
        time.sleep(0.001)


def scheduler(infer, clock, **kwargs):
    module = importlib.import_module('so101_rollout.smolvla.async_engine')
    return module.AsyncChunkScheduler(infer, fps=20, horizon=6, prefetch=3, clock=clock, **kwargs)


def test_new_chunk_runs_while_existing_actions_are_consumed_and_trims_elapsed_prefix():
    clock = Clock()
    entered, release = threading.Event(), threading.Event()
    calls = []

    def infer(req):
        calls.append(req)
        if len(calls) == 2:
            entered.set()
            assert release.wait(2)
        return [[req.observation['offset'] + i] for i in range(6)]

    engine = scheduler(infer, clock)
    engine.start()
    engine.resume()
    try:
        assert engine.get_action({'offset': 0}) is None
        wait_until(lambda: engine.result_ready)
        assert engine.get_action({'offset': 100}) == [0]
        clock.now += 0.05
        assert engine.get_action({'offset': 100}) == [1]
        clock.now += 0.05
        assert engine.get_action({'offset': 100}) == [2]
        clock.now += 0.05
        assert engine.get_action({'offset': 100}) == [3]
        assert entered.wait(2)
        clock.now += 0.05
        assert engine.get_action({'offset': 100}) == [4]
        release.set()
        wait_until(lambda: engine.result_ready)
        clock.now += 0.05
        # Observation at tick3; ticks3/4 elapsed during inference, no replay.
        assert engine.get_action({'offset': 100}) == [102]
    finally:
        release.set()
        engine.stop()


def test_pause_and_reset_discard_inflight_results_and_old_observations():
    clock = Clock()
    entered, release = threading.Event(), threading.Event()

    def infer(req):
        if req.observation['task'] == 'green':
            entered.set()
            assert release.wait(2)
        return [[req.observation['value']] for _ in range(6)]

    engine = scheduler(infer, clock)
    engine.start()
    engine.resume()
    try:
        engine.get_action({'task': 'green', 'value': 1})
        assert entered.wait(2)
        engine.pause()
        engine.reset()
        engine.resume()
        release.set()
        wait_until(lambda: engine.result_ready)
        assert engine.get_action(None) is None
        assert engine.get_action({'task': 'red', 'value': 2}) is None
        wait_until(lambda: engine.result_ready)
        assert engine.get_action({'task': 'red', 'value': 2}) == [2]
        assert engine.stats['stale_results'] == 1
    finally:
        release.set()
        engine.stop()


def test_slow_control_skips_expired_actions_instead_of_replaying_backlog():
    clock = Clock()
    engine = scheduler(lambda req: [[i] for i in range(6)], clock)
    engine.start()
    engine.resume()
    try:
        engine.get_action({})
        wait_until(lambda: engine.result_ready)
        assert engine.get_action({}) == [0]
        clock.now += 0.16
        assert engine.get_action({}) == [3]
        assert engine.stats['skipped_ticks'] == 2
    finally:
        engine.stop()


def test_worker_failure_propagates_in_control_thread_and_no_future_actions_escape():
    clock = Clock()

    def broken(req):
        raise ValueError('model failure')

    engine = scheduler(broken, clock)
    engine.start()
    engine.resume()
    try:
        engine.get_action({})
        wait_until(lambda: engine.result_ready)
        with pytest.raises(RuntimeError, match='model failure'):
            engine.get_action({})
        assert engine.failed
        with pytest.raises(RuntimeError, match='model failure'):
            engine.get_action({})
    finally:
        engine.stop()


def test_starvation_returns_no_action_and_is_not_counted_as_a_successful_tick():
    clock = Clock()
    entered, release = threading.Event(), threading.Event()
    calls = []

    def infer(req):
        calls.append(req)
        if len(calls) == 2:
            entered.set()
            assert release.wait(2)
        return [[i] for i in range(6)]

    engine = scheduler(infer, clock)
    engine.start()
    engine.resume()
    try:
        engine.get_action({})
        wait_until(lambda: engine.result_ready)
        assert engine.get_action({}) == [0]
        for i in range(1, 6):
            clock.now += 0.05
            assert engine.get_action({}) == [i]
        assert entered.wait(2)
        clock.now += 0.05
        assert engine.get_action({}) is None
        assert engine.stats['starved_ticks'] == 1
        assert engine.stats['actions'] == 6
    finally:
        release.set()
        engine.stop()


@pytest.mark.parametrize('actions', [[[float('nan')]] * 6, [[1]] * 5, [[1], [1, 2], [1], [1], [1], [1]]])
def test_invalid_prediction_aborts_instead_of_sending_commands(actions):
    clock = Clock()
    engine = scheduler(lambda req: actions, clock)
    engine.start()
    engine.resume()
    try:
        engine.get_action({})
        wait_until(lambda: engine.result_ready)
        with pytest.raises(RuntimeError):
            engine.get_action({})
        assert engine.stats['actions'] == 0
    finally:
        engine.stop()


def test_observation_is_frozen_at_request_time():
    clock = Clock()
    entered, release = threading.Event(), threading.Event()

    def infer(req):
        entered.set()
        assert release.wait(2)
        return [[req.observation['state'][0]]] * 6

    engine = scheduler(infer, clock)
    engine.start()
    engine.resume()
    try:
        observation = {'state': [7]}
        engine.get_action(observation)
        assert entered.wait(2)
        observation['state'][0] = 99
        release.set()
        wait_until(lambda: engine.result_ready)
        assert engine.get_action({}) == [7]
    finally:
        release.set()
        engine.stop()


def test_extended_starvation_aborts_without_sending_last_action_again():
    clock = Clock()
    calls = []
    release = threading.Event()

    def infer(req):
        calls.append(req)
        if len(calls) > 1:
            assert release.wait(2)
        return [[i] for i in range(6)]

    engine = scheduler(infer, clock, starvation_timeout_s=0.1)
    engine.start()
    engine.resume()
    try:
        engine.get_action({})
        wait_until(lambda: engine.result_ready)
        for i in range(6):
            assert engine.get_action({}) == [i]
            clock.now += 0.05
        assert engine.get_action({}) is None
        clock.now += 0.11
        with pytest.raises(RuntimeError, match='queue starved'):
            engine.get_action({})
        assert engine.stats['actions'] == 6
    finally:
        release.set()
        engine.stop()


def test_reset_during_stuck_inference_still_has_a_startup_timeout():
    clock = Clock()
    entered, release = threading.Event(), threading.Event()

    def infer(req):
        entered.set()
        assert release.wait(2)
        return [[1]] * 6

    engine = scheduler(infer, clock, startup_timeout_s=1)
    engine.start()
    engine.resume()
    try:
        engine.get_action({})
        assert entered.wait(2)
        engine.reset()
        assert engine.get_action({}) is None
        clock.now += 1.1
        with pytest.raises(RuntimeError, match='first chunk timed out'):
            engine.get_action({})
    finally:
        release.set()
        engine.stop()
