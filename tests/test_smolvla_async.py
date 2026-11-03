import threading
import time

import pytest

from tools.smolvla_async import ActionTimeline, AsyncWorker, ChunkRequest, ChunkResult, aligned_tick, successful_intervals


def request(identifier=1, generation=0, tick=10):
    return ChunkRequest(identifier, generation, tick, "green", tick, time.perf_counter(), {})


def result(req, length=5):
    return ChunkResult(req, [[float(i)] * 6 for i in range(length)], time.perf_counter())


def test_late_chunk_discards_past_prefix_and_replaces_future():
    timeline = ActionTimeline()
    assert timeline.install(result(request(tick=10)), current_tick=12)["trimmed"] == 2
    assert timeline.pop(11) is None
    action = timeline.pop(12)
    assert action["action"] == [2.0] * 6
    assert action["request_tick"] == 10
    timeline.install(result(request(identifier=2, tick=13)), current_tick=14)
    assert timeline.pop(14)["action"] == [1.0] * 6
    assert timeline.remaining(14) == 3


def test_out_of_order_and_all_expired_results_cannot_replace_new_actions():
    timeline = ActionTimeline()
    timeline.install(result(request(identifier=3)), 10)
    assert timeline.install(result(request(identifier=2)), 11)["reason"] == "out_of_order"
    assert timeline.pop(11)["request_id"] == 3
    assert timeline.install(result(request(identifier=4)), 15)["reason"] == "fully_expired"


def test_reset_rejects_inflight_previous_task_even_when_tick_restarts():
    timeline = ActionTimeline()
    old = request()
    timeline.install(result(old), 10)
    assert timeline.reset() == 1
    assert timeline.remaining(0) == 0
    assert timeline.install(result(old), 0)["reason"] == "stale_generation"
    fresh = request(identifier=2, generation=1, tick=0)
    timeline.install(result(fresh), 0)
    assert timeline.pop(0)["generation"] == 1


def test_single_inflight_stays_bounded_until_completed_result_is_polled():
    entered, release = threading.Event(), threading.Event()

    def infer(req):
        entered.set()
        assert release.wait(2)
        return result(req)

    worker = AsyncWorker(infer)
    try:
        assert worker.submit(request())
        assert entered.wait(2)
        assert not worker.submit(request(identifier=2))
        assert worker.poll() is None
        release.set()
        deadline = time.perf_counter() + 2
        while not worker.has_result() and time.perf_counter() < deadline:
            time.sleep(0.001)
        assert not worker.submit(request(identifier=2))
        assert worker.poll().request.identifier == 1
        assert worker.submit(request(identifier=2))
    finally:
        release.set()
        worker.close()


def test_worker_exception_is_reported_without_waiting_in_tick_thread():
    def infer(req):
        raise ValueError("inference broke")

    worker = AsyncWorker(infer)
    try:
        worker.submit(request())
        deadline = time.perf_counter() + 2
        while not worker.has_result() and time.perf_counter() < deadline:
            time.sleep(0.001)
        with pytest.raises(RuntimeError, match="inference broke"):
            worker.poll()
    finally:
        worker.close()


def test_scheduler_skips_elapsed_ticks_instead_of_catching_up():
    tick, skipped = aligned_tick(5, epoch=10.0, now=10.361, period=0.05)
    assert (tick, skipped) == (8, 3)
    assert 0 <= (10.0 + tick * 0.05) - 10.361 < 0.05


def test_99ms_delay_skips_to_future_tick_instead_of_sending_1ms_apart():
    assert aligned_tick(0, epoch=10, now=10.099, period=0.05) == (2, 2)


def test_49ms_delay_does_not_allow_next_action_only_1ms_later():
    assert aligned_tick(0, epoch=10, now=10.049, period=0.05) == (1, 1)


def test_scheduler_tolerates_4ms_jitter_but_skips_6ms_late_tick():
    assert aligned_tick(0, epoch=10, now=10.004, period=0.05) == (0, 0)
    assert aligned_tick(0, epoch=10, now=10.006, period=0.05) == (1, 1)


def test_action_gap_includes_starved_ticks():
    rows = [{"starved":False,"action_ready":10.0},
            {"starved":True,"action_ready":10.05},
            {"starved":True,"action_ready":10.1},
            {"starved":False,"action_ready":10.15}]
    assert successful_intervals(rows) == pytest.approx([150])
