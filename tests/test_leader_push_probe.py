"""Offline tests: never open a real serial device."""
import importlib
import json
import subprocess
import sys

import pytest


def module():
    return importlib.import_module('tools.probe_leader_push_to_teach')


def sample(position=1000, load=10, current=20, torque=1):
    return {'joint': {'Present_Position': position, 'Present_Load': load,
                      'Present_Current': current, 'Torque_Enable': torque}}


def detector():
    m = module()
    d = m.Detector(m.Settings(trigger_mode='effort', settle_seconds=0, baseline_timeout_seconds=.6, baseline_seconds=.2, sustain_seconds=.2,
                             max_gap_seconds=.15, load_delta=5, current_delta=5,
                             position_delta=2))
    for t in (0, .1, .2):
        d.observe(t, sample())
    return d


def test_detector_rejects_spike_then_accepts_sustained_same_joint_push_once():
    d = detector()
    assert d.observe(.3, sample(1003, 20)) == 'candidate'
    assert d.observe(.4, sample()) == 'armed'
    assert d.observe(.5, sample(1003, 20)) == 'candidate'
    assert d.observe(.6, sample(1003, 20)) == 'candidate'
    assert d.observe(.71, sample(1003, 20)) == 'released'
    assert d.observe(.8, sample()) == 'released'


def test_detector_does_not_trigger_without_displacement_or_after_gap():
    d = detector()
    assert d.observe(.3, sample(load=20)) == 'armed'
    d.observe(.4, sample(1003, 20))
    with pytest.raises(RuntimeError, match='gap'):
        d.observe(.7, sample(1003, 20))


def test_unstable_baseline_refuses_arming():
    m = module()
    d = m.Detector(m.Settings(trigger_mode='effort', settle_seconds=0, baseline_timeout_seconds=.6, baseline_seconds=.2, baseline_position_span=2))
    d.observe(0, sample())
    d.observe(.1, sample(1005))
    assert d.observe(.2, sample()) == 'baseline_pending'
    assert d.baseline is None


class Clock:
    def __init__(self): self.now = 0.
    def __call__(self): return self.now
    def sleep(self, duration): self.now += duration


class Bus:
    def __init__(self, clock, fail=False, torque=0):
        self.clock, self.fail, self.is_connected = clock, fail, False
        self.motors = {'joint': object()}
        self.values = dict(sample(torque=torque)['joint'], Operating_Mode=0)
        self.events = []
    def connect(self):
        self.is_connected = True
        self.events.append(('connect',))
    def read(self, register, motor, *, normalize):
        assert normalize is False
        if self.fail and self.clock.now > .25:
            raise OSError('telemetry failed')
        if self.clock.now > .4 and register == 'Present_Load': return 50
        if self.clock.now > .4 and register == 'Present_Position': return 1010
        return self.values[register]
    def write(self, register, motor, value, *, normalize):
        assert normalize is False
        self.events.append((register, motor, value))
        self.values[register] = value
    def disconnect(self, *, disable_torque):
        self.events.append(('disconnect', disable_torque))
        self.is_connected = False


def run(bus, clock, tmp_path, active):
    m = module()
    return m.run_probe(bus, m.Settings(trigger_mode='effort', enable_release=active, duration_seconds=1,
                       settle_seconds=0, baseline_timeout_seconds=.6, baseline_seconds=.2, sustain_seconds=.15, poll_hz=10,
                       load_delta=5, position_delta=2), tmp_path,
                       clock=clock, sleep=clock.sleep, arm=lambda: True)


def test_monitor_never_writes_even_if_torque_already_on(tmp_path):
    clock = Clock(); bus = Bus(clock, torque=1)
    run(bus, clock, tmp_path, False)
    assert bus.events == [('connect',), ('disconnect', False)]
    rows = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
    assert any(r['event'] == 'sample' and 'feedback' in r for r in rows)


def test_active_holds_current_pose_before_torque_and_never_reenables(tmp_path):
    clock = Clock(); bus = Bus(clock)
    assert run(bus, clock, tmp_path, True) == 'released'
    writes = bus.events[1:-1]
    assert writes[0] == ('Goal_Position', 'joint', 1000)
    assert writes[1] == ('Torque_Enable', 'joint', 1)
    assert [w for w in writes if w[0] == 'Torque_Enable' and w[2] == 1] == [writes[1]]
    assert ('Torque_Enable', 'joint', 0) in writes
    assert bus.events[-1] == ('disconnect', False)


def test_active_exception_releases_and_closes(tmp_path):
    clock = Clock(); bus = Bus(clock, fail=True)
    with pytest.raises(RuntimeError, match='release not verified'):
        run(bus, clock, tmp_path, True)
    assert ('Torque_Enable', 'joint', 0) in bus.events
    assert bus.events[-1] == ('disconnect', False)


def test_active_refuses_already_enabled_torque_without_writes(tmp_path):
    clock = Clock(); bus = Bus(clock, torque=1)
    with pytest.raises(RuntimeError, match='already enabled'):
        run(bus, clock, tmp_path, True)
    assert bus.events == [('connect',), ('disconnect', False)]


def test_help_works_without_lerobot_import():
    result = subprocess.run([sys.executable, 'tools/probe_leader_push_to_teach.py', '--help'],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert '--enable-release' in result.stdout


def test_current_deviation_can_trigger():
    d = detector()
    assert d.observe(.3, sample(1003, current=30)) == 'candidate'
    d.observe(.4, sample(1003, current=30))
    assert d.observe(.51, sample(1003, current=30)) == 'released'


def test_cancel_arming_has_no_writes(tmp_path):
    m = module(); clock = Clock(); bus = Bus(clock)
    assert m.run_probe(bus, m.Settings(trigger_mode='effort', enable_release=True), tmp_path,
                       clock=clock, sleep=clock.sleep, arm=lambda: False) == 'cancelled'
    assert bus.events == [('connect',), ('disconnect', False)]


def test_release_attempts_every_joint_and_reports_partial_failure():
    m = module(); bus = Bus(Clock())
    bus.motors['other'] = object()
    original = bus.write
    def write(register, motor, value, *, normalize):
        if motor == 'joint': raise OSError('offline joint')
        original(register, motor, value, normalize=normalize)
    bus.write = write
    with pytest.raises(RuntimeError, match='release not verified'):
        m.release(bus)
    assert ('Torque_Enable', 'other', 0) in bus.events


def test_configured_follower_port_is_refused_before_bus_import():
    m = module()
    with pytest.raises(SystemExit) as exc:
        m.main(['--port', m.config_ports()['FOLLOWER_PORT']])
    assert exc.value.code == 2


def test_cleanup_release_failure_is_recorded_as_unverified(tmp_path):
    clock = Clock(); bus = Bus(clock, fail=True)
    with pytest.raises(RuntimeError, match='release not verified'):
        run(bus, clock, tmp_path, True)
    rows = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
    assert any(r['event'] == 'cleanup_release_failed' for r in rows)
    assert not any(r['event'] == 'cleanup_release_verified' for r in rows)


def test_monitor_displays_raw_joint_feedback(tmp_path, capsys):
    clock = Clock(); bus = Bus(clock, torque=1)
    run(bus, clock, tmp_path, False)
    output = capsys.readouterr().out
    assert 'joint' in output and 'pos=1000' in output and 'torque=1' in output
    assert 'load=10' in output and 'current=20' in output


def test_alternating_candidate_joints_do_not_accumulate_sustained_time():
    m = module()
    d = m.Detector(m.Settings(trigger_mode='effort', settle_seconds=0, baseline_timeout_seconds=.6, baseline_seconds=.2, sustain_seconds=.2,
                             max_gap_seconds=.15, load_delta=5, position_delta=2))
    def pair(push_joint=None):
        return {name: sample(1003, 20)['joint'] if name == push_joint else sample()['joint']
                for name in ('left', 'right')}
    for t in (0, .1, .2): d.observe(t, pair())
    for t, name in ((.3, 'left'), (.4, 'right'), (.5, 'left'), (.6, 'right')):
        assert d.observe(t, pair(name)) == 'candidate'


def test_settling_transient_then_rolling_baseline_converges():
    m = module()
    d = m.Detector(m.Settings(trigger_mode='effort', settle_seconds=.2, baseline_seconds=.2,
                             baseline_timeout_seconds=.8, max_gap_seconds=.15,
                             baseline_load_span=5))
    assert d.observe(0, sample(load=100)) == 'settling'
    assert d.observe(.1, sample(load=-100)) == 'settling'
    assert d.observe(.2, sample(load=100)) == 'baseline'
    d.observe(.3, sample(load=10))
    assert d.observe(.4, sample(load=10)) == 'baseline_pending'
    assert d.baseline is None
    assert d.observe(.5, sample(load=10)) == 'armed'
    assert d.baseline['joint']['Present_Load'] == 10


def test_persistent_baseline_drift_times_out_with_spans_and_limits():
    m = module()
    d = m.Detector(m.Settings(trigger_mode='effort', settle_seconds=0, baseline_seconds=.2,
                             baseline_timeout_seconds=.5, max_gap_seconds=.15,
                             baseline_position_span=2))
    for i in range(5):
        assert d.observe(i / 10, sample(position=1000 + i * 10)) != 'armed'
    with pytest.raises(RuntimeError, match=r'baseline timeout.*joint.*Present_Position.*span.*limit'):
        d.observe(.5, sample(position=1050))
    assert d.baseline is None


def test_baseline_timeout_logs_the_offending_feedback_sample(tmp_path):
    m = module(); clock = Clock(); bus = Bus(clock)
    original_read = bus.read
    def read(register, motor, *, normalize):
        if register == 'Present_Position': return 1000 + round(clock.now * 100)
        return original_read(register, motor, normalize=normalize)
    bus.read = read
    settings = m.Settings(trigger_mode='effort', enable_release=True, duration_seconds=1,
                          settle_seconds=0, baseline_seconds=.2,
                          baseline_timeout_seconds=.5, poll_hz=10)
    with pytest.raises(RuntimeError, match='baseline timeout'):
        m.run_probe(bus, settings, tmp_path, clock=clock, sleep=clock.sleep, arm=lambda: True)
    rows = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
    assert any(r['event'] == 'sample' and r['feedback']['joint']['Present_Position'] == 1050 for r in rows)
    assert any(r['event'] == 'cleanup_release_verified' for r in rows)


def test_active_duration_must_allow_settling_and_baseline_timeout():
    m = module()
    with pytest.raises(ValueError, match='duration'):
        m.Settings(trigger_mode='effort', enable_release=True, duration_seconds=14).validate()


def test_recorded_failed_trial_prefix_never_arms():
    from pathlib import Path
    path = Path('/data/work/so101-evidence/real-robot/leader-push-20261105-181028-7e7482f0/events.jsonl')
    if not path.exists(): pytest.skip('local hardware evidence unavailable')
    m = module(); d = m.Detector(m.Settings(trigger_mode='effort', ))
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    samples = [row for row in rows if row['event'] == 'sample']
    assert samples
    for row in samples:
        assert d.observe(row['monotonic'], row['feedback']) not in ('armed', 'candidate', 'released')
    assert d.baseline is None


class GripperBus(Bus):
    def __init__(self, clock, move_gripper=True):
        super().__init__(clock)
        self.motors = {name: object() for name in module().JOINTS}
        self.per_motor = {name: dict(self.values) for name in self.motors}
        self.move_gripper = move_gripper
    def read(self, register, motor, *, normalize):
        if register == 'Present_Position' and self.clock.now > .6:
            if motor == 'gripper' and self.move_gripper: return 1040
            if motor != 'gripper': return 1400
        return self.per_motor[motor][register]
    def write(self, register, motor, value, *, normalize):
        self.events.append((register, motor, value))
        self.per_motor[motor][register] = value


def gripper_settings():
    return module().Settings(enable_release=True, duration_seconds=1.3,
                             settle_seconds=.1, gripper_baseline_seconds=.2,
                             baseline_timeout_seconds=.8, sustain_seconds=.2, poll_hz=10)


def test_default_gripper_trigger_never_enables_gripper_and_releases_five_axes(tmp_path):
    m = module(); clock = Clock(); bus = GripperBus(clock)
    assert m.run_probe(bus, gripper_settings(), tmp_path, clock=clock,
                       sleep=clock.sleep, arm=lambda: True) == 'released'
    enables = [e for e in bus.events if e[0] == 'Torque_Enable' and e[2] == 1]
    assert [e[1] for e in enables] == list(m.JOINTS[:-1])
    rows = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
    pending = [r for r in rows if r['event'] == 'sample' and r['state'] in ('armed', 'candidate')]
    assert pending
    assert all(r['feedback']['gripper']['Torque_Enable'] == 0 for r in pending)
    assert all(r['feedback'][j]['Torque_Enable'] == 1 for r in pending for j in m.JOINTS[:-1])
    assert any(r['event'] == 'trigger' and r['gripper_delta'] == 40 for r in rows)
    assert all(bus.per_motor[j]['Torque_Enable'] == 0 for j in m.JOINTS)


def test_arm_joint_drift_does_not_trigger_gripper_strategy_and_timeout_releases(tmp_path):
    m = module(); clock = Clock(); bus = GripperBus(clock, move_gripper=False)
    assert m.run_probe(bus, gripper_settings(), tmp_path, clock=clock,
                       sleep=clock.sleep, arm=lambda: True) == 'armed'
    assert all(bus.per_motor[j]['Torque_Enable'] == 0 for j in m.JOINTS)


def test_gripper_settling_jitter_and_spikes_never_release_before_sustained_motion():
    m = module(); d = m.Detector(gripper_settings())
    def grip(p): return {'gripper': sample(position=p)['joint']}
    assert d.observe(0, grip(1200)) == 'settling'
    for t in (.1, .2): assert d.observe(t, grip(1000)) == 'baseline'
    assert d.observe(.3, grip(1000)) == 'armed'
    assert d.observe(.4, grip(1002)) == 'armed'
    assert d.observe(.5, grip(1040)) == 'candidate'
    assert d.observe(.6, grip(1000)) == 'armed'
    assert d.observe(.7, grip(960)) == 'candidate'
    d.observe(.8, grip(960))
    assert d.observe(.9, grip(960)) == 'released'
