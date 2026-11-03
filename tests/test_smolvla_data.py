import pytest

from tools.prepare_smolvla_data import validate_split, origin_episode


def records():
    return [dict(split=s, color=c, group=s+c, origin=s+c, numeric_sha256=s+c)
            for s in ('train', 'validation') for c in ('green', 'red')]


def test_source_folder_cannot_straddle_train_validation():
    rows = records()
    rows[2]['group'] = rows[0]['group']
    with pytest.raises(ValueError, match='group'):
        validate_split(rows)


def test_duplicate_trajectory_cannot_leak_between_splits():
    rows = records()
    rows[2]['numeric_sha256'] = rows[0]['numeric_sha256']
    with pytest.raises(ValueError, match='trajectory'):
        validate_split(rows)


def test_both_instructions_required_in_each_split():
    with pytest.raises(ValueError, match='both colors'):
        validate_split(records()[:-1])
    assert validate_split(records()) is None


def test_excluded_raw_episodes_stay_excluded_in_origin_mapping():
    assert origin_episode('real-cube-bowl-red-clean-20261028', 9) == 9
    assert origin_episode('real-cube-bowl-red-clean-20261028', 10) == 11
    assert origin_episode('real-cube-bowl-p2-green-extra-clean-20261030', 1) == 1
    assert origin_episode('real-cube-bowl-p2-green-extra-clean-20261030', 2) == 3
