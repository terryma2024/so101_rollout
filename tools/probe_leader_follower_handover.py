#!/usr/bin/env python3
"""Standalone calibrated leader/follower takeover experiment (no policy integration)."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import select
import signal
import sys
import time
import uuid

try:
    from tools.probe_leader_push_to_teach import Detector, Settings as DetectorSettings, JOINTS
except ModuleNotFoundError:  # Direct script execution.
    from probe_leader_push_to_teach import Detector, Settings as DetectorSettings, JOINTS

ARM_JOINTS = JOINTS[:-1]
ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    elbow_compensation: bool = False
    approximate_alignment: bool = False
    poll_hz: float = 20
    max_gap: float = .5
    command_timeout: float = 60
    align_timeout: float = 45
    ready_timeout: float = 30
    teaching_seconds: float = 8
    align_speed: float = 8  # degrees/second
    follow_speed: float = 30  # degrees/second; gripper uses percent/second
    max_step: float = 1.5  # degrees or gripper percentage points per update
    converge_tolerance: float = .75  # degrees
    converge_seconds: float = .5
    tracking_error: float = 8  # degrees, or gripper percentage points
    baseline_seconds: float = .5
    gripper_closing_lead: float = 3  # percentage points below measured follower opening
    gripper_displacement: float = 30  # raw ticks, proven local starting threshold
    sustain_seconds: float = .25

    def validate(self):
        for key, value in asdict(self).items():
            if key in ('elbow_compensation', 'approximate_alignment'):
                if type(value) is not bool:
                    raise ValueError(f'{key} must be boolean')
                continue
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{key} must be finite and positive')
        if self.approximate_alignment and self.elbow_compensation:
            raise ValueError('approximate_alignment and elbow_compensation are mutually exclusive')
        if 1 / self.poll_hz >= self.max_gap:
            raise ValueError('poll interval must be shorter than max_gap')
        if self.ready_timeout <= self.baseline_seconds or self.align_timeout <= self.converge_seconds:
            raise ValueError('timeouts must exceed baseline/convergence windows')




class ApproximateAlignment:
    """Fixed per-joint error limits plus a contiguous, all-axis stable window."""
    SECONDS = 1.
    SPAN = .35
    TOLERANCES = {j: 4. if j == 'elbow_flex' else 1.5 for j in ARM_JOINTS}

    def __init__(self):
        self.history = []

    def observe(self, now, positions, target, nominal_done):
        if nominal_done:
            self.history.append((now, positions.copy()))
            # Retain the sample immediately before the one-second boundary.
            while len(self.history) > 1 and self.history[1][0] <= now - self.SECONDS:
                self.history.pop(0)
        else:
            self.history.clear()
        window = self.history or [(now, positions)]
        elapsed = now - window[0][0]
        joints = {}
        for j in ARM_JOINTS:
            values = [p[j] for _, p in window]
            tolerance = self.TOLERANCES[j]
            span = max(values) - min(values)
            joints[j] = dict(residual_degrees=positions[j] - target[j], tolerance_degrees=tolerance,
                span_degrees=span, within_limits=all(abs(v - target[j]) <= tolerance for v in values),
                stable=span <= self.SPAN)
        stable = elapsed >= self.SECONDS - 1e-9 and all(v['stable'] for v in joints.values())
        within_limits = all(v['within_limits'] for v in joints.values())
        return dict(ready=nominal_done and stable and within_limits, nominal_ramp_done=nominal_done,
            elapsed_seconds=elapsed, required_seconds=self.SECONDS, span_limit_degrees=self.SPAN,
            stable=stable, within_limits=within_limits, joints=joints)


class ElbowCompensation:
    """One bounded, position-only alignment experiment; never a persistent integrator."""
    MAX_DEGREES = 3.
    RATE = .5
    STABLE_SECONDS = 1.
    STABLE_SPAN = .35
    PROBE_DEGREES = 1.
    PROBE_SECONDS = 3.
    MIN_PROGRESS = .25
    WORSENING = .5

    def __init__(self, settings):
        self.tolerance = settings.converge_tolerance
        self.offset = 0.
        self.phase = 'waiting_stable'
        self.started = False
        self.previous = None
        self.history = []
        self.direction = None
        self.initial_sign = None
        self.initial_error = None
        self.probe_started = None
        self.probe_error = None
        self.probe_origin = 0.

    def observe(self, now, error, nominal_done, step):
        if not all(math.isfinite(v) for v in (now, error, step)) or step < 0:
            raise RuntimeError('invalid elbow compensation telemetry')
        dt = 0. if self.previous is None else now - self.previous
        if dt < 0:
            raise RuntimeError('non-monotonic elbow compensation timestamp')
        self.previous = now
        if not nominal_done:
            self.history.clear()
            return self.offset
        if not self.started:
            if abs(error) <= self.tolerance:
                self.history.clear()
                return self.offset
            self.history.append((now, error))
            while len(self.history) > 1 and self.history[1][0] <= now - self.STABLE_SECONDS:
                self.history.pop(0)
            stable = (now - self.history[0][0] >= self.STABLE_SECONDS - 1e-9 and
                      max(e for _, e in self.history) - min(e for _, e in self.history) <= self.STABLE_SPAN)
            if not stable:
                return self.offset
            self.initial_error = abs(error)
            self.initial_sign = 1 if error > 0 else -1
            self.direction = -self.initial_sign
            self.probe_started = now
            self.probe_error = abs(error)
            self.started = True
            self.phase = 'trial'
        if error * self.initial_sign < -self.tolerance:
            raise RuntimeError('elbow compensation overshoot/wrong sign; support both arms')
        if abs(error) > self.probe_error + self.WORSENING:
            raise RuntimeError('elbow compensation measured error worsened; support both arms')
        # Freeze once inside the ORIGINAL tolerance; outer code still requires its dwell.
        if abs(error) <= self.tolerance:
            return self.offset
        if now - self.probe_started >= self.PROBE_SECONDS - 1e-9:
            details = (f'last probe improvement={self.probe_error - abs(error):.3f}°, '
                       f'initial error={self.initial_error:.3f}°, '
                       f'overall improvement={self.initial_error - abs(error):.3f}°, '
                       f'offset={self.offset:+.3f}°, residual={error:+.3f}°')
            if abs(self.offset) >= self.MAX_DEGREES - 1e-9:
                raise RuntimeError('elbow compensation limit exhausted before nominal convergence; ' + details)
            if self.probe_error - abs(error) < self.MIN_PROGRESS:
                raise RuntimeError('elbow compensation no measured improvement after bounded probe; ' + details)
            self.probe_started = now
            self.probe_error = abs(error)
            self.probe_origin = self.offset
        target = self.direction * min(self.MAX_DEGREES, abs(self.probe_origin) + self.PROBE_DEGREES)
        limit = min(step, self.RATE * dt)
        self.offset += max(-limit, min(limit, target - self.offset))
        return self.offset


def validate_calibration(cal):
    if set(cal) != set(JOINTS):
        raise ValueError('calibration must contain exactly the six SO101 joints')
    for expected_id, joint in enumerate(JOINTS, 1):
        entry = cal[joint]
        for field in ('id', 'drive_mode', 'homing_offset', 'range_min', 'range_max'):
            if type(entry.get(field)) is not int:
                raise ValueError(f'{joint}: calibration {field} must be integer')
        if entry['id'] != expected_id:
            raise ValueError(f'{joint}: calibration id must be {expected_id}')
        if entry['drive_mode'] != 0:
            raise ValueError(f'{joint}: only verified drive_mode=0 convention is supported')
        if not 0 <= entry['range_min'] < entry['range_max'] <= 4095:
            raise ValueError(f'{joint}: invalid calibrated range')
        if not -2047 <= entry['homing_offset'] <= 2047:
            raise ValueError(f'{joint}: invalid homing offset')


def to_normal(cal, joint, raw):
    """Match installed LeRobot DEGREES and RANGE_0_100; offset is already in raw telemetry."""
    c = cal[joint]
    if joint == 'gripper':
        return (raw - c['range_min']) * 100 / (c['range_max'] - c['range_min'])
    return (raw - (c['range_min'] + c['range_max']) / 2) * 360 / 4095


def to_raw(cal, joint, value):
    c = cal[joint]
    raw = (value / 100 * (c['range_max'] - c['range_min']) + c['range_min'] if joint == 'gripper'
           else value * 4095 / 360 + (c['range_min'] + c['range_max']) / 2)
    if not math.isfinite(raw) or raw < c['range_min'] - 1e-8 or raw > c['range_max'] + 1e-8:
        raise ValueError(f'{joint}: target outside calibrated range: {value}')
    return max(c['range_min'], min(c['range_max'], round(raw)))



def gripper_command(previous_goal, previous_leader, leader, measured, *, step, closing_lead):
    """Bound one incremental opening command; rejected travel is never accumulated.

    This is a position lead cap, not contact detection or a physical force limit.
    Opening input always raises (or preserves) the commanded opening, including
    when a prior closing goal still leads the measured follower position.
    """
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)
           or not 0 <= v <= 100 for v in (previous_goal, previous_leader, leader, measured)):
        raise ValueError('invalid/out-of-range gripper telemetry or previous goal')
    if not math.isfinite(step) or not math.isfinite(closing_lead) or step <= 0 or closing_lead <= 0:
        raise ValueError('gripper step and closing lead must be finite and positive')
    reasons = []
    desired = previous_goal + leader - previous_leader
    target = max(0., min(100., desired))
    if target != desired:
        reasons.append('range')
    floor = max(0., measured - closing_lead)
    if target < floor:
        target = floor
        reasons.append('closing_lead')
    value = previous_goal + max(-step, min(step, target - previous_goal))
    if abs(value - target) > 1e-10:
        reasons.append('step')
    return value, reasons


def distinct_ports(leader, follower):
    a, b = Path(leader).resolve(), Path(follower).resolve()
    if a == b or (a.exists() and b.exists() and os.path.samefile(a, b)):
        raise ValueError('leader and follower ports overlap')
    if a.exists() and b.exists() and a.stat().st_rdev and a.stat().st_rdev == b.stat().st_rdev:
        raise ValueError('leader and follower ports refer to same device')


def read_sample(bus, cal):
    pos = bus.sync_read('Present_Position', normalize=False)
    torque = bus.sync_read('Torque_Enable', normalize=False)
    if set(pos) != set(JOINTS) or set(torque) != set(JOINTS):
        raise RuntimeError('incomplete telemetry')
    result = {}
    for j in JOINTS:
        p, t = pos[j], torque[j]
        if (isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p)
                or not cal[j]['range_min'] <= p <= cal[j]['range_max']
                or type(t) not in (int, float) or t not in (0, 1)):
            raise RuntimeError(f'invalid/out-of-range telemetry: {j} position={p} torque={t}')
        result[j] = dict(Present_Position=p, Torque_Enable=t, normalized=to_normal(cal, j, p))
    return result


def checked_write(bus, register, joint, value):
    bus.write(register, joint, value, normalize=False)
    if bus.read(register, joint, normalize=False) != value:
        raise RuntimeError(f'{joint}: {register} write readback failed')


def prompt(title, message):
    print(f'\n========== {title} ==========\n{message}\n', flush=True)


def console_command():
    """Poll stdin without blocking safety telemetry/deadlines while energized."""
    if not select.select([sys.stdin], [], [], 0)[0]:
        return None
    line = sys.stdin.readline()
    if not line:
        raise RuntimeError('console EOF')
    return line.strip()


def run_probe(leader, follower, leader_cal, follower_cal, settings, evidence_dir, *,
              clock=time.monotonic, sleep=time.sleep, command=console_command):
    settings.validate()
    alignment_mode = ('approximate' if settings.approximate_alignment else
                      'elbow_compensation' if settings.elbow_compensation else 'strict')
    tolerances = (ApproximateAlignment.TOLERANCES.copy() if settings.approximate_alignment else
                  {j: settings.converge_tolerance for j in ARM_JOINTS})
    validate_calibration(leader_cal)
    validate_calibration(follower_cal)
    distinct_ports(leader.port, follower.port)
    for bus in (leader, follower):
        if set(bus.motors) != set(JOINTS) or any(bus.motors[j].id != i for i, j in enumerate(JOINTS, 1)):
            raise ValueError('bus motor names/ids must match the six calibrated joints')
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    touched = False
    state = 'wait_arm'
    buses = (leader, follower)
    cals = (leader_cal, follower_cal)
    with (evidence_dir / 'events.jsonl').open('x', buffering=1) as stream:
        def log(event, **values):
            stream.write(json.dumps(dict(event=event, monotonic=clock(),
                utc=datetime.now(timezone.utc).isoformat(), **values), allow_nan=False) + '\n')

        def snapshot():
            before = clock()
            values = [read_sample(b, c) for b, c in zip(buses, cals)]
            if clock() - before > settings.max_gap:
                raise RuntimeError('telemetry read cycle too slow')
            return values

        def enable_at_pose(bus, raw, joints):
            nonlocal touched
            touched = True  # Before any potentially partial write.
            started = clock()
            cal = leader_cal if bus is leader else follower_cal
            for j in joints:
                checked_write(bus, 'Goal_Position', j, raw[j])
            for j in joints:
                measured = bus.read('Present_Position', j, normalize=False)
                if (not isinstance(measured, (int, float)) or not math.isfinite(measured)
                        or abs(to_normal(cal, j, measured) - to_normal(cal, j, raw[j])) > settings.converge_tolerance
                        or clock() - started > settings.max_gap):
                    raise RuntimeError(f'{j}: pose moved or arming telemetry stale; keep arm supported')
                checked_write(bus, 'Torque_Enable', j, 1)

        def require_torque(samples):
            for index, s in enumerate(samples):
                for j in JOINTS:
                    expected = int(index == 1 and state != 'wait_arm' or
                                   index == 0 and state in ('align', 'ready') and j in ARM_JOINTS)
                    if s[j]['Torque_Enable'] != expected:
                        raise RuntimeError(f'unexpected torque state: bus={index} joint={j}')

        def check_tracking(sample, target, joints, limit):
            if any(abs(sample[j]['normalized'] - target[j]) > limit for j in joints):
                raise RuntimeError('measured tracking error exceeded; support both arms')

        log('metadata', settings=asdict(settings), alignment_mode=alignment_mode,
            alignment_tolerances_degrees=tolerances, ports=[b.port for b in buses],
            calibration=[leader_cal, follower_cal], units='arm degrees; gripper percent; detector raw ticks')
        try:
            for bus in buses:
                bus.connect()  # Raw handshake only; no configure, auto-calibration or EEPROM writes.
            initial = snapshot()
            log('precheck', leader=initial[0], follower=initial[1])
            if any(v['Torque_Enable'] for s in initial for v in s.values()):
                raise RuntimeError('torque already enabled; refusing all writes; restart supported and torque OFF')
            for bus, cal in zip(buses, cals):
                actual = bus.read_calibration()
                for j in JOINTS:
                    if j not in actual or any(getattr(actual[j], k) != cal[j][k] for k in ('id', 'homing_offset', 'range_min', 'range_max')):
                        raise RuntimeError(f'{j}: live/file calibration mismatch; recalibrate separately')
                    if bus.read('Operating_Mode', j, normalize=False) != 0:
                        raise RuntimeError(f'{j}: position mode required; no mode edits performed')
            prompt('1/5 摆放 follower → ARM', f'两臂已卸力。摆好并托住 follower，输入 ARM 后回车，保持当前位置。\n请在 {settings.command_timeout:g} 秒内操作；STOP + 回车或 Ctrl+C 退出。')
            state_start = previous = clock()
            converged = None
            last_alignment_diagnostic = -math.inf
            detector = None
            leader_goal = follower_goal = None
            nominal_leader_goal = None
            elbow = ElbowCompensation(settings) if settings.elbow_compensation else None
            approximate = ApproximateAlignment() if settings.approximate_alignment else None
            while True:
                samples = snapshot()
                now = clock()
                dt = now - previous
                if dt < 0 or dt > settings.max_gap:
                    raise RuntimeError('telemetry gap or clock reversal')
                previous = now
                require_torque(samples)
                log('sample', state=state, leader=samples[0], follower=samples[1], cycle_seconds=dt)
                if state != 'wait_arm':
                    check_tracking(samples[1], follower_goal, JOINTS, settings.tracking_error)
                cmd = command()
                if cmd in ('QUIT', 'STOP'):
                    log('cancelled', state=state)
                    return 'cancelled'
                if state in ('wait_arm', 'wait_go'):
                    if now - state_start > settings.command_timeout:
                        raise RuntimeError('command timeout')
                    expected = 'ARM' if state == 'wait_arm' else 'GO'
                    if cmd == expected:
                        # Fresh telemetry at the explicit command boundary.
                        samples = snapshot()
                        require_torque(samples)
                        if state == 'wait_arm':
                            follower_raw = {j: samples[1][j]['Present_Position'] for j in JOINTS}
                            follower_goal = {j: samples[1][j]['normalized'] for j in JOINTS}
                            # Fail before holding if follower pose cannot be represented by leader.
                            for j in ARM_JOINTS:
                                to_raw(leader_cal, j, follower_goal[j])
                            enable_at_pose(follower, follower_raw, JOINTS)
                            state = 'wait_go'
                            prompt('2/5 follower 已保持 → GO', f'确认 leader 路径畅通并托住 leader。输入 GO 后回车，开始缓慢对齐。\n请在 {settings.command_timeout:g} 秒内操作。')
                        else:
                            leader_goal = {j: samples[0][j]['normalized'] for j in ARM_JOINTS}
                            nominal_leader_goal = leader_goal.copy()
                            enable_at_pose(leader, {j: samples[0][j]['Present_Position'] for j in ARM_JOINTS}, ARM_JOINTS)
                            state = 'align'
                            alignment_message = f'leader 正在运动；先不要活动夹爪。最长等待 {settings.align_timeout:g} 秒。\n等待下方明确出现 READY 提示。'
                            if settings.approximate_alignment:
                                alignment_message += '\n本次使用稳定近似对齐：肘部误差 ≤4°，其余轴 ≤1.5°，五轴稳定至少 1 秒；不做目标补偿。'
                            if settings.elbow_compensation:
                                alignment_message += '\nleader 开始加力移动后，请撤去托举，不要碰 leader；READY 后再托住。紧急情况请立即停止并托住。'
                            prompt('3/5 正在对齐，请等待', alignment_message)
                        state_start = clock()
                        log('transition', state=state)
                    elif cmd:
                        print(f'Waiting for exact {expected}; QUIT exits.', flush=True)
                elif state == 'align':
                    if now - state_start > settings.align_timeout:
                        details = ', '.join(
                            f"{j}: actual={samples[0][j]['normalized']:.2f}°, "
                            f"target={follower_goal[j]:.2f}°, "
                            f"error={samples[0][j]['normalized'] - follower_goal[j]:+.2f}° (limit={tolerances[j]:g}°)"
                            for j in ARM_JOINTS
                            if abs(samples[0][j]['normalized'] - follower_goal[j]) > tolerances[j]
                        ) or 'position did not remain within tolerance for the required dwell'
                        raise RuntimeError(f'alignment timeout; measured convergence not achieved '
                                           f'(mode={alignment_mode}): {details}')
                    if now - last_alignment_diagnostic >= 1:
                        # Raw counts only: no force/current-unit interpretation or control changes.
                        diagnostic = {register: leader.sync_read(register, normalize=False)
                                      for register in ('Goal_Position', 'Present_Load', 'Present_Current')}
                        log('alignment_diagnostic', leader=diagnostic, nominal_goal=follower_goal.copy(),
                            elbow_compensation_degrees=elbow.offset if elbow else 0., position={j: samples[0][j]['Present_Position'] for j in JOINTS})
                        last_alignment_diagnostic = now
                    # Abort gross tracking errors, but allow the bounded ramp to lead measured pose.
                    check_tracking(samples[0], leader_goal, ARM_JOINTS, settings.tracking_error)
                    step = min(settings.max_step, settings.align_speed * dt)
                    nominal_was_done = all(abs(nominal_leader_goal[j] - follower_goal[j]) < 1e-8 for j in ARM_JOINTS)
                    for j in ARM_JOINTS:
                        delta = max(-step, min(step, follower_goal[j] - nominal_leader_goal[j]))
                        nominal_leader_goal[j] += delta
                    goals_done = all(abs(nominal_leader_goal[j] - follower_goal[j]) < 1e-8 for j in ARM_JOINTS)
                    offset = 0.
                    if elbow is not None:
                        was_started = elbow.started
                        signed_error = samples[0]['elbow_flex']['normalized'] - follower_goal['elbow_flex']
                        # Use command-time spacing so slow diagnostic reads cannot accelerate the next offset step.
                        offset = elbow.observe(clock(), signed_error, goals_done, step)
                        if elbow.started:
                            log('elbow_compensation', phase=elbow.phase, nominal_goal=follower_goal['elbow_flex'],
                                offset_degrees=offset, actual=samples[0]['elbow_flex']['normalized'],
                                signed_error_degrees=signed_error,
                                commanded_goal=nominal_leader_goal['elbow_flex'] + offset)
                        if elbow.started and not was_started:
                            prompt('肘部小幅目标补偿开始', '原目标保持不变：只对 elbow 缓慢试探，最多 3°、0.5°/秒。\n请勿托举或推动 leader，以免影响进展判断；必要时立即停止并托住。')
                    leader_goal = nominal_leader_goal.copy()
                    leader_goal['elbow_flex'] += offset
                    # Validate ALL resulting goals before any write in this cycle.
                    raw_goals = {j: to_raw(leader_cal, j, leader_goal[j]) for j in ARM_JOINTS}
                    for j in ARM_JOINTS:
                        checked_write(leader, 'Goal_Position', j, raw_goals[j])
                    error = max(abs(samples[0][j]['normalized'] - follower_goal[j]) for j in ARM_JOINTS)
                    residuals = {j: samples[0][j]['normalized'] - follower_goal[j] for j in ARM_JOINTS}
                    gate = (approximate.observe(now, {j: samples[0][j]['normalized'] for j in ARM_JOINTS},
                                               follower_goal, goals_done and nominal_was_done) if approximate else None)
                    log('alignment', error_degrees=error, goal=leader_goal.copy(), nominal_goal=follower_goal.copy(),
                        elbow_compensation_degrees=offset, alignment_mode=alignment_mode, residuals_degrees=residuals,
                        tolerances_degrees=tolerances, alignment_gate=gate)
                    eligible = gate['ready'] if approximate else goals_done and error <= settings.converge_tolerance
                    if eligible:
                        converged = now if converged is None else converged
                        if approximate or now - converged >= settings.converge_seconds:
                            state = 'ready'
                            state_start = clock()
                            detector = Detector(DetectorSettings(settle_seconds=0, gripper_baseline_seconds=settings.baseline_seconds,
                                baseline_timeout_seconds=settings.ready_timeout, max_gap_seconds=settings.max_gap,
                                gripper_displacement=settings.gripper_displacement, sustain_seconds=settings.sustain_seconds,
                                poll_hz=settings.poll_hz))
                            log('aligned', error_degrees=error, elbow_compensation_degrees=offset,
                                alignment_mode=alignment_mode, residuals_degrees=residuals, tolerances_degrees=tolerances,
                                alignment_gate=gate)
                            if elbow is not None and elbow.started:
                                prompt('肘部补偿完成并保持', f'已按原目标验证收敛；补偿 {offset:+.2f}° 将保持到夹爪触发卸力。')
                            prompt('对齐完成，正在建立夹爪基线', '请保持夹爪静止。尚不能触发，请继续等待 READY。')
                    else:
                        converged = None
                elif state == 'ready':
                    if now - state_start > settings.ready_timeout:
                        raise RuntimeError('ready timeout; no sustained gripper trigger')
                    if approximate:
                        gate = approximate.observe(now, {j: samples[0][j]['normalized'] for j in ARM_JOINTS},
                                                   follower_goal, True)
                        log('ready_alignment_check', alignment_mode=alignment_mode, alignment_gate=gate)
                        if not gate['ready']:
                            failed = [j for j, v in gate['joints'].items() if not v['within_limits'] or not v['stable']]
                            raise RuntimeError('approximate alignment lost: bounds/stability failed for ' + ', '.join(failed))
                    else:
                        check_tracking(samples[0], follower_goal, ARM_JOINTS, settings.converge_tolerance)
                    old = detector.state
                    result = detector.observe(now, samples[0])
                    if result == 'armed' and old in ('baseline', 'baseline_pending'):
                        log('ready', baseline=detector.baseline, alignment_mode=alignment_mode)
                        if approximate:
                            print('近似对齐仍持续检查稳定性：请只托住，不要托抬或推动手臂，否则立即退出卸力。', flush=True)
                        prompt('4/5 READY：现在可以动夹爪', f'托住 leader，再开合夹爪并保持至少 {settings.sustain_seconds:g} 秒（位移超过 {settings.gripper_displacement:g} ticks）。\n触发后 leader 手臂将卸力，follower 保持加力。')
                    if result == 'released':
                        leader_reference = {j: samples[0][j]['normalized'] for j in JOINTS}
                        follower_reference = follower_goal.copy()
                        previous_leader_gripper = leader_reference['gripper']
                        # References capture trigger movement, so first follower gripper goal stays unchanged.
                        for j in ARM_JOINTS:
                            checked_write(leader, 'Torque_Enable', j, 0)
                        state = 'teaching'
                        state_start = clock()
                        log('takeover', leader_reference=leader_reference, follower_reference=follower_reference,
                            alignment_mode=alignment_mode,
                            gripper_delta=detector.gripper_delta)
                        for j in JOINTS:
                            checked_write(follower, 'Goal_Position', j, follower_raw[j])
                        log('follower_command', raw=follower_raw.copy(), normalized=follower_goal.copy())
                        prompt('5/5 已进入示教：主从同步中', f'leader 已卸力，可以轻缓操作。示教持续 {settings.teaching_seconds:g} 秒。\n示教结束后将停止跟随，等待你托住两臂并按回车再卸力退出；STOP + 回车或 Ctrl+C 可立即退出。')
                elif state == 'teaching':
                    if now - state_start >= settings.teaching_seconds:
                        state = 'wait_release'
                        state_start = now
                        log('teaching_stopped', follower_goal=follower_goal.copy())
                        prompt('示教结束：等待回车卸力', '已停止跟随；follower 仍保持最后目标，leader 已卸力。\n请先托住两臂，再按回车卸力退出。此等待没有自动卸力倒计时。\n故障、STOP + 回车或 Ctrl+C 仍会立即卸力退出。')
                        sleep(1 / settings.poll_hz)
                        continue
                    step = min(settings.max_step, settings.follow_speed * dt)
                    raw = {}
                    for j in ARM_JOINTS:
                        target = follower_reference[j] + samples[0][j]['normalized'] - leader_reference[j]
                        # Arm protections remain strict: no range saturation or wrapping.
                        to_raw(follower_cal, j, target)
                        follower_goal[j] += max(-step, min(step, target - follower_goal[j]))
                        raw[j] = to_raw(follower_cal, j, follower_goal[j])
                    current_leader_gripper = samples[0]['gripper']['normalized']
                    follower_goal['gripper'], gripper_caps = gripper_command(
                        follower_goal['gripper'], previous_leader_gripper, current_leader_gripper,
                        samples[1]['gripper']['normalized'], step=step,
                        closing_lead=settings.gripper_closing_lead)
                    # Advance even when capped: no stored range/lag/speed-limited travel.
                    previous_leader_gripper = current_leader_gripper
                    raw['gripper'] = to_raw(follower_cal, 'gripper', follower_goal['gripper'])
                    for j in JOINTS:
                        checked_write(follower, 'Goal_Position', j, raw[j])
                    log('follower_command', raw=raw, normalized=follower_goal.copy(), gripper_caps=gripper_caps)
                elif state == 'wait_release':
                    # No timeout or new goals; safety telemetry and follower tracking
                    # are still checked at the top of every polling cycle.
                    if cmd == '':
                        log('release_confirmed')
                        log('finished')
                        return 'finished'
                sleep(1 / settings.poll_hz)
        except BaseException as exc:
            log('error', state=state, error=repr(exc))
            raise
        finally:
            errors = []
            cleanup_events = []
            # Pre-existing torque rejection intentionally makes no writes. After first own
            # write, every joint on BOTH buses gets an independent disable/readback attempt.
            if touched:
                for index, bus in enumerate(buses):
                    for j in JOINTS:
                        try:
                            checked_write(bus, 'Torque_Enable', j, 0)
                            cleanup_events.append(('cleanup_joint_verified', dict(bus=index, joint=j)))
                        except BaseException as exc:
                            errors.append(f'bus={index} {j}: {exc}')
            for index, bus in enumerate(buses):
                try:
                    if bus.is_connected:
                        bus.disconnect(disable_torque=False)
                    elif getattr(bus, 'port_handler', None) is not None:
                        bus.port_handler.closePort()
                    cleanup_events.append(('disconnected', dict(bus=index)))
                except BaseException as exc:
                    errors.append(f'bus={index} close: {exc}')
            # Finish all motor/port operations before any potentially failing log writes.
            for event, values in cleanup_events:
                log(event, **values)
            if errors:
                log('cleanup_failed', errors=errors)
                raise RuntimeError('cleanup unverified; SUPPORT BOTH ARMS: ' + '; '.join(errors))
            if touched:
                log('cleanup_verified')
                prompt('已结束：两臂卸力已确认', '串口已关闭。完整反馈保存在本次 events.jsonl。')


def defaults():
    result = {}
    path = ROOT / 'config/arms.env'
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep and key in ('LEADER_PORT', 'FOLLOWER_PORT', 'LEADER_ID', 'FOLLOWER_ID'):
                result[key] = value.strip().strip('\"\'')
    return {k: os.environ.get(k, v) for k, v in result.items()}


def make_bus(port, cal):
    from lerobot.motors import Motor, MotorCalibration, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus
    return FeetechMotorsBus(port=port, motors={j: Motor(i, 'sts3215',
        MotorNormMode.RANGE_0_100 if j == 'gripper' else MotorNormMode.DEGREES)
        for i, j in enumerate(JOINTS, 1)}, calibration={j: MotorCalibration(**v) for j, v in cal.items()})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    config = defaults()
    base = Path(os.environ.get('HF_HOME', '~/.cache/huggingface')).expanduser() / 'lerobot/calibration'
    for role, subdir in (('leader', 'teleoperators/so_leader'), ('follower', 'robots/so_follower')):
        parser.add_argument(f'--{role}-port', default=config.get(role.upper() + '_PORT'))
        parser.add_argument(f'--{role}-id', default=config.get(role.upper() + '_ID'))
        parser.add_argument(f'--{role}-calibration', type=Path)
    parser.add_argument('--evidence-dir', type=Path, default=Path('/data/work/so101-evidence/real-robot') /
        ('handover-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]))
    for name, value in asdict(Settings()).items():
        if type(value) is bool:
            parser.add_argument('--' + name.replace('_', '-'), action='store_true', default=value)
        else:
            parser.add_argument('--' + name.replace('_', '-'), type=float, default=value)
    args = parser.parse_args(argv)
    try:
        if not args.leader_port or not args.follower_port:
            raise ValueError('both leader/follower ports required')
        if (not args.leader_id or not args.follower_id or args.leader_id == args.follower_id or
                any(Path(v).name != v or v in ('.', '..') for v in (args.leader_id, args.follower_id))):
            raise ValueError('distinct leader/follower ids required, without path components')
        distinct_ports(args.leader_port, args.follower_port)
        settings = Settings(**{k: getattr(args, k) for k in asdict(Settings())})
        settings.validate()
        lpath = args.leader_calibration or base / f'teleoperators/so_leader/{args.leader_id}.json'
        fpath = args.follower_calibration or base / f'robots/so_follower/{args.follower_id}.json'
        if lpath.resolve() == fpath.resolve():
            raise ValueError('leader/follower calibration paths overlap')
        lcal, fcal = [json.loads(p.read_text()) for p in (lpath, fpath)]
        for cal in (lcal, fcal):
            validate_calibration(cal)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    def terminate(signum, frame):
        raise KeyboardInterrupt(f'signal {signum}')
    old = {s: signal.signal(s, terminate) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        print(f'Leader: {args.leader_port} ({lpath})\nFollower: {args.follower_port} ({fpath})\nEvidence: {args.evidence_dir}', flush=True)
        run_probe(make_bus(args.leader_port, lcal), make_bus(args.follower_port, fcal), lcal, fcal, settings, args.evidence_dir)
    except KeyboardInterrupt:
        print('Stopped; support both arms. Check evidence for cleanup_verified.', flush=True)
        return 130
    except Exception as exc:
        print(f'Aborted: {exc}. Support both arms; inspect evidence.', file=sys.stderr, flush=True)
        return 1
    finally:
        for s, handler in old.items():
            signal.signal(s, handler)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
