"""Offline overlap mathematics; no runtime scheduler or hardware involved."""
import numpy as np
import pytest
from tools.smolvla_offline_diagnosis import replay, summarize


def test_trim_alignment_body_blend_and_raw_gripper():
    old = np.tile(np.arange(10.)[:, None], (1, 6))
    new = np.tile((100 + np.arange(10.))[:, None], (1, 6))
    events = [dict(request_tick=0, installed_tick=0, trimmed=0),
              dict(request_tick=4, installed_tick=6, trimmed=2)]
    hard, _ = replay([old, new], events, 10, 0)
    blend, windows = replay([old, new], events, 10, 4)
    assert hard[6, 0] == 102
    assert blend[6, 0] == pytest.approx(6 * .75 + 102 * .25)
    assert blend[9, 0] == 105
    np.testing.assert_array_equal(blend[:, 5], hard[:, 5])
    assert windows[0]['available_old'] == 4
    assert windows[0]['end_tick'] == 9


def test_short_old_future_shrinks_window_without_hold_or_extrapolation():
    old = np.zeros((8, 6)); new = np.full((10, 6), 10.)
    events = [dict(request_tick=0, installed_tick=0, trimmed=0),
              dict(request_tick=4, installed_tick=6, trimmed=2)]
    a, windows = replay([old, new], events, 12, 6)
    assert windows[0]['used_window'] == 2
    assert a[6, 0] == 5 and a[7, 0] == 10 and a[8, 0] == 10


def test_empty_old_future_hard_switch_and_missing_actions_fail():
    events = [dict(request_tick=0, installed_tick=0, trimmed=0),
              dict(request_tick=2, installed_tick=4, trimmed=2)]
    a, windows = replay([np.zeros((4, 6)), np.ones((8, 6))], events, 8, 6)
    assert windows[0]['used_window'] == 0 and a[4, 0] == 1
    with pytest.raises(ValueError, match='missing'):
        replay([np.zeros((2, 6))], events[:1], 4, 0)


def test_end_jump_is_measured_and_d2_boundary_mask_covers_both_differences():
    a = np.zeros((30, 6)); a[14:, 0] = 30
    m = summarize(a, np.zeros_like(a), a, [10], [13])
    assert m['transition_end_d1']['max'] == 30
    assert m['boundary_plusminus10_d1']['max'] == 30
    assert m['full_d2']['max'] == 30


def test_pooling_uses_individual_boundary_samples_and_retains_end_spike():
    from tools.smolvla_offline_diagnosis import pooled_metrics
    events = [dict(installed_tick=0), dict(installed_tick=10)]
    seq, windows = {}, []
    for seed in [1000, 2000, 3000]:
        for w in [0, 4, 6]:
            x = np.zeros((30, 6)); x[14:, 0] = 30
            seq[f'e0_{seed}_w{w}'] = x
            windows.append(dict(episode=0, seed=seed, window=w,
                                transitions=[dict(end_tick=13)]))
    result = pooled_metrics(seq, [dict(events=events)], windows)
    assert result[4]['boundary_d1']['count'] == 3
    assert result[4]['boundary_d1']['max'] == 0
    assert result[4]['end_d1']['max'] == 30
    assert result[4]['near10_d2']['max'] == 30
