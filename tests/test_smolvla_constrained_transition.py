"""Offline policy constraints, alignment, and reproducible independent noise."""
import numpy as np
import pytest
from tools.smolvla_constrained_transition import constrained_replay, noise_seed


def test_projected_transition_caps_new_deviation_and_state_distance():
    old = np.full((10, 6), -100.)
    new = np.zeros((10, 6)); new[:, 5] = np.arange(10)
    events = [dict(request_tick=0, installed_tick=0, trimmed=0),
              dict(request_tick=4, installed_tick=6, trimmed=2)]
    state = np.full((12, 6), -10.)
    a, windows = constrained_replay([old, new], events, state, 12, 'project4', cap=5)
    assert a[6, 0] == -5
    assert np.max(np.abs(a[6:, :5])) <= 5
    assert np.all(np.abs(a[6:, :5]-state[6:, :5]) <= np.abs(state[6:, :5]))
    np.testing.assert_array_equal(a[6:, 5], new[2:8, 5])
    np.testing.assert_array_equal(a[9:, :5], new[5:8, :5])
    assert windows[0]['degraded']


def test_state_constraint_rejects_wrong_way_old_target_and_gate_fallback():
    old = np.full((10, 6), -100.); new = np.zeros((10, 6))
    e = [dict(request_tick=0, installed_tick=0, trimmed=0),
         dict(request_tick=4, installed_tick=6, trimmed=2)]
    for policy in ['project4', 'gate4']:
        a, w = constrained_replay([old,new], e, np.ones((12,6)), 12, policy, cap=5)
        np.testing.assert_array_equal(a[6:], 0)
        assert w[0]['degraded']


def test_no_old_future_and_nonfinite_and_missing_are_not_held():
    e = [dict(request_tick=0, installed_tick=0, trimmed=0),
         dict(request_tick=2, installed_tick=4, trimmed=2)]
    a, w = constrained_replay([np.zeros((4,6)),np.ones((8,6))], e, np.zeros((8,6)),8,'project4')
    assert w[0]['available_old'] == 0 and a[4,0] == 1
    with pytest.raises(ValueError, match='Nonfinite'):
        constrained_replay([np.full((4,6), np.nan)], e[:1], np.zeros((4,6)),4,'project4')
    with pytest.raises(ValueError, match='missing'):
        constrained_replay([np.zeros((2,6))],e[:1],np.zeros((4,6)),4,'project4')


def test_noise_stream_seed_is_deterministic_unique_and_fixed_control_reuses():
    seeds=[noise_seed(1101,e,r,'independent') for e in range(4) for r in range(15)]
    assert len(set(seeds)) == len(seeds)
    assert seeds[2] == noise_seed(1101,0,2,'independent')
    assert noise_seed(1101,0,1,'fixed') == noise_seed(1101,3,9,'fixed')
    assert noise_seed(1101,0,1,'independent') != noise_seed(3303,0,1,'independent')


def test_unconstrained_controls_match_previous_replay_exactly():
    from tools.smolvla_offline_diagnosis import replay
    rng=np.random.default_rng(18)
    old=rng.normal(size=(12,6)); new=rng.normal(size=(12,6))
    events=[dict(request_tick=0,installed_tick=0,trimmed=0),
            dict(request_tick=6,installed_tick=8,trimmed=2)]
    for policy,window in [('hard',0),('blend4',4),('blend6',6)]:
        a,_=constrained_replay([old,new],events,np.zeros((15,6)),15,policy)
        expected,_=replay([old,new],events,15,window)
        np.testing.assert_array_equal(a,expected)


def test_small_valid_gate_preserves_linear_blend_and_raw_terminal():
    old=np.full((10,6),-2.);new=np.zeros((10,6));new[:,5]=7.
    e=[dict(request_tick=0,installed_tick=0,trimmed=0),
       dict(request_tick=4,installed_tick=6,trimmed=2)]
    a,w=constrained_replay([old,new],e,np.full((12,6),-10.),12,'gate4')
    np.testing.assert_allclose(a[6:10,0],[-1.5,-1.,-.5,0.])
    assert not w[0]['degraded']
    np.testing.assert_array_equal(a[6:,5],7.)


def test_invalid_expired_prefix_is_rejected():
    with pytest.raises(ValueError,match='alignment'):
        constrained_replay([np.zeros((10,6))],[dict(request_tick=0,installed_tick=0,trimmed=1)],np.zeros((10,6)),10,'project4')
