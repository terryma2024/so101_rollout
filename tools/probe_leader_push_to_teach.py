#!/usr/bin/env python3
"""Leader-only raw telemetry experiment; --help needs only the standard library."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
from statistics import median
import time
import uuid

REGISTERS = ('Present_Position', 'Present_Load', 'Present_Current', 'Torque_Enable')
JOINTS = ('shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper')
ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    enable_release: bool = False
    trigger_mode: str = 'gripper-motion'
    gripper_displacement: float = 30
    gripper_baseline_seconds: float = .5
    duration_seconds: float = 30
    teaching_seconds: float = 8
    baseline_seconds: float = 3
    settle_seconds: float = 2
    baseline_timeout_seconds: float = 12
    sustain_seconds: float = .25
    max_gap_seconds: float = .5
    poll_hz: float = 20
    load_delta: float = 30
    current_delta: float = 30
    position_delta: float = 4
    baseline_position_span: float = 8
    baseline_load_span: float = 30
    baseline_current_span: float = 30

    def validate(self):
        if self.trigger_mode not in ('gripper-motion', 'effort'):
            raise ValueError('unknown trigger mode')
        for key, value in asdict(self).items():
            if key not in ('enable_release', 'trigger_mode') and (not math.isfinite(value) or value < 0 or (value == 0 and key != 'settle_seconds')):
                raise ValueError(f'{key} must be finite and positive')
        window = self.gripper_baseline_seconds if self.trigger_mode == 'gripper-motion' else self.baseline_seconds
        if self.baseline_timeout_seconds <= window:
            raise ValueError('baseline timeout must exceed baseline window duration')
        if self.enable_release and self.duration_seconds <= self.settle_seconds + self.baseline_timeout_seconds:
            raise ValueError('duration must exceed settling plus baseline timeout')
        if 1 / self.poll_hz >= self.max_gap_seconds:
            raise ValueError('poll interval must be shorter than max gap')


class Detector:
    """Fixed-baseline gripper motion, or legacy same-joint effort, held over time."""
    def __init__(self, settings):
        self.settings = settings
        self.history = []
        self.baseline = None
        self.previous = None
        self.candidates = {}
        self.state = 'settling' if settings.settle_seconds else 'baseline'
        self.started = None
        self.diagnostics = []
        self.gripper_delta = None

    def observe(self, now, feedback):
        if self.previous is not None and (now <= self.previous or now - self.previous > self.settings.max_gap_seconds):
            raise RuntimeError('telemetry gap or non-monotonic timestamp')
        self.previous = now
        if self.state == 'released':
            return self.state
        if self.started is None:
            self.started = now
        gripper_mode = self.settings.trigger_mode == 'gripper-motion'
        monitored = {'gripper': feedback['gripper']} if gripper_mode else feedback
        window = self.settings.gripper_baseline_seconds if gripper_mode else self.settings.baseline_seconds
        if self.baseline is None:
            baseline_elapsed = now - self.started - self.settings.settle_seconds
            if baseline_elapsed < -1e-9:
                self.state = 'settling'
                return self.state
            self.history.append((now, feedback))
            # Keep the sample just before the window boundary so its duration
            # covers at least the requested interval despite serial jitter.
            cutoff = now - window
            while len(self.history) > 1 and self.history[1][0] <= cutoff + 1e-9:
                self.history.pop(0)
            candidate = {}
            self.diagnostics = []
            for motor in monitored:
                candidate[motor] = {}
                limits = [('Present_Position', self.settings.baseline_position_span)]
                if not gripper_mode:
                    limits += [('Present_Load', self.settings.baseline_load_span),
                               ('Present_Current', self.settings.baseline_current_span)]
                for register, limit in limits:
                    values = [f[motor][register] for _, f in self.history]
                    span = max(values) - min(values)
                    self.diagnostics.append(dict(motor=motor, register=register, span=span, limit=limit))
                    candidate[motor][register] = median(values)
            complete = len(self.history) >= 3 and now - self.history[0][0] + 1e-9 >= window
            unstable = [d for d in self.diagnostics if d['span'] > d['limit']]
            if complete and not unstable:
                self.baseline = candidate
                self.history.clear()
                self.state = 'armed'
                return self.state
            self.state = 'baseline_pending' if complete else 'baseline'
            if baseline_elapsed + 1e-9 >= self.settings.baseline_timeout_seconds:
                details = '; '.join(f"{d['motor']} {d['register']} span={d['span']} limit={d['limit']}"
                                    for d in unstable or self.diagnostics)
                raise RuntimeError('baseline timeout: ' + details)
            return self.state
        for motor, values in monitored.items():
            base = self.baseline[motor]
            delta = values['Present_Position'] - base['Present_Position']
            if gripper_mode:
                self.gripper_delta = delta
                displacement = abs(delta) > self.settings.gripper_displacement
                effort = True
            else:
                displacement = abs(delta) >= self.settings.position_delta
                effort = (abs(values['Present_Load'] - base['Present_Load']) >= self.settings.load_delta or
                          abs(values['Present_Current'] - base['Present_Current']) >= self.settings.current_delta)
            if displacement and effort:
                start = self.candidates.setdefault(motor, now)
                if now - start + 1e-9 >= self.settings.sustain_seconds:
                    self.state = 'released'
                    return self.state
            else:
                self.candidates.pop(motor, None)
        self.state = 'candidate' if self.candidates else 'armed'
        return self.state


def read_feedback(bus):
    result = {}
    for motor in bus.motors:
        result[motor] = {}
        for register in REGISTERS:
            value = bus.read(register, motor, normalize=False)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise RuntimeError(f'invalid telemetry: {motor} {register} {value!r}')
            if register == 'Torque_Enable' and value not in (0, 1):
                raise RuntimeError(f'invalid torque state: {motor} {value}')
            result[motor][register] = value
    return result


def release(bus):
    """Try every motor even when one fails; never report release without readback."""
    errors = []
    for motor in bus.motors:
        try:
            bus.write('Torque_Enable', motor, 0, normalize=False)
            if bus.read('Torque_Enable', motor, normalize=False) != 0:
                raise RuntimeError('torque disable readback nonzero')
        except Exception as exc:
            errors.append(f'{motor}: {exc}')
    if errors:
        raise RuntimeError('release not verified; SUPPORT ARM: ' + '; '.join(errors))


def run_probe(bus, settings, evidence_dir, *, clock=time.monotonic, sleep=time.sleep, arm=None):
    settings.validate()
    evidence_dir = Path(evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    detector = Detector(settings)
    torque_touched = False
    state = 'monitor'
    with (evidence_dir / 'events.jsonl').open('x', buffering=1) as stream:
        def log(event, **values):
            stream.write(json.dumps(dict(event=event, monotonic=clock(),
                                         utc=datetime.now(timezone.utc).isoformat(), **values)) + '\n')
        log('metadata', settings=asdict(settings), motors=list(bus.motors),
            port=getattr(bus, 'port', None), raw_units='LeRobot sign-decoded register counts; no physical force units')
        try:
            bus.connect()  # Feetech handshake only pings and reads firmware; no SOLeader.configure().
            if settings.enable_release:
                if settings.trigger_mode == 'gripper-motion' and 'gripper' not in bus.motors:
                    raise RuntimeError('gripper-motion requires gripper motor')
                held_motors = [m for m in bus.motors if settings.trigger_mode == 'effort' or m != 'gripper']
                initial = read_feedback(bus)
                log('precheck', feedback=initial)
                if any(v['Torque_Enable'] != 0 for v in initial.values()):
                    raise RuntimeError('torque already enabled; start supported, torque OFF')
                for motor in held_motors:
                    if bus.read('Operating_Mode', motor, normalize=False) != 0:
                        raise RuntimeError(f'{motor}: position mode required; no mode writes are performed')
                if arm is None or not arm():
                    log('cancelled')
                    return 'cancelled'
                # Re-read after the operator prompt; arm may have moved while supported.
                initial = read_feedback(bus)
                if any(v['Torque_Enable'] != 0 for v in initial.values()):
                    raise RuntimeError('torque already enabled after arming')
                for motor in held_motors:
                    values = initial[motor]
                    bus.write('Goal_Position', motor, values['Present_Position'], normalize=False)
                    if bus.read('Goal_Position', motor, normalize=False) != values['Present_Position']:
                        raise RuntimeError(f'{motor}: hold target readback failed')
                torque_touched = True  # Include partially successful enable writes in cleanup.
                for motor in held_motors:
                    bus.write('Torque_Enable', motor, 1, normalize=False)
                    if bus.read('Torque_Enable', motor, normalize=False) != 1:
                        raise RuntimeError(f'{motor}: enable readback failed')
                print('Holding current pose. Gradually remove supporting force; keep hands nearby. Do not move the gripper or push until Ready.', flush=True)
                state = detector.state
            start = clock()
            previous_end = start
            released_at = None
            next_display = start
            while clock() - start < settings.duration_seconds:
                before = clock()
                feedback = read_feedback(bus)
                now = clock()
                if now - before > settings.max_gap_seconds or now - previous_end > settings.max_gap_seconds:
                    raise RuntimeError('telemetry gap: read cycle too slow')
                previous_end = now
                if settings.enable_release and released_at is None:
                    if any(v['Torque_Enable'] != int(motor in held_motors) for motor, v in feedback.items()):
                        raise RuntimeError('unexpected torque state while holding')
                    old_state = state
                    try:
                        state = detector.observe(now, feedback)
                    except BaseException:
                        log('sample', state=detector.state, cycle_seconds=now-before, feedback=feedback,
                            baseline_diagnostics=detector.diagnostics)
                        raise
                    if state == 'baseline_pending' and old_state != state:
                        log('baseline_pending', diagnostics=detector.diagnostics)
                        print('Baseline still changing; wait for Ready before moving the gripper or pushing.', flush=True)
                    if state == 'armed' and old_state in ('settling', 'baseline', 'baseline_pending'):
                        log('baseline_ready', baseline=detector.baseline)
                        action = 'open or close the torque-free gripper' if settings.trigger_mode == 'gripper-motion' else 'lightly push the leader'
                        print(f'Ready: support the arm and {action}. Ctrl+C releases torque.', flush=True)
                    if state == 'candidate' and old_state != 'candidate':
                        print('Trigger candidate; waiting for sustained signal.', flush=True)
                    if state == 'released':
                        log('trigger', trigger_mode=settings.trigger_mode, baseline=detector.baseline,
                            gripper_delta=detector.gripper_delta, feedback=feedback)
                        release(bus)
                        released_at = now
                        log('release_verified')
                        print('Torque OFF verified. Teaching positions are being logged; support the arm.', flush=True)
                elif released_at is not None and any(v['Torque_Enable'] != 0 for v in feedback.values()):
                    raise RuntimeError('unexpected torque re-enabled externally')
                log('sample', state=state, cycle_seconds=now-before, feedback=feedback)
                if now >= next_display:
                    print(f'{state}: ' + ' | '.join(
                        f"{motor} pos={v['Present_Position']} load={v['Present_Load']} "
                        f"current={v['Present_Current']} torque={v['Torque_Enable']}"
                        for motor, v in feedback.items()), flush=True)
                    next_display = now + 1
                if released_at is not None and now - released_at >= settings.teaching_seconds:
                    break
                sleep(1 / settings.poll_hz)
            log('finished', state=state, reason='duration_or_teaching_limit')
            return state
        except BaseException as exc:
            log('error', state=state, error=repr(exc))
            raise
        finally:
            # Never restore pre-existing torque. Only active sessions that attempted enable release.
            try:
                if torque_touched:
                    try:
                        release(bus)
                    except BaseException as exc:
                        log('cleanup_release_failed', error=repr(exc))
                        raise
                    log('cleanup_release_verified')
            finally:
                if bus.is_connected:
                    bus.disconnect(disable_torque=False)
                    log('disconnected')
                elif getattr(bus, 'port_handler', None) is not None:
                    bus.port_handler.closePort()  # Handshake can fail after opening the serial port.


def config_ports():
    values = {}
    path = ROOT / 'config' / 'arms.env'
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep and key in ('LEADER_PORT', 'FOLLOWER_PORT'):
                values[key] = value.strip().strip('\"\'')
    return values


def make_bus(port):
    from lerobot.motors import Motor, MotorNormMode
    from lerobot.motors.feetech import FeetechMotorsBus
    return FeetechMotorsBus(port=port, motors={
        name: Motor(index, 'sts3215', MotorNormMode.RANGE_M100_100)
        for index, name in enumerate(JOINTS, 1)})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    ports = config_ports()
    parser.add_argument('--port', default=os.environ.get('LEADER_PORT', ports.get('LEADER_PORT')))
    parser.add_argument('--trigger-mode', choices=('gripper-motion', 'effort'), default='gripper-motion')
    parser.add_argument('--enable-release', action='store_true', help='Explicit active holding/release experiment; interactive arming required')
    parser.add_argument('--evidence-dir', type=Path, default=Path('/data/work/so101-evidence/real-robot') / ('leader-push-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]))
    for name, default, help_text in [
        ('duration', 30., 'Total session deadline in seconds, including teaching'),
        ('teaching-seconds', 8., 'Continue raw position logging after verified release'),
        ('gripper-displacement', 30., 'Opening or closing displacement in raw ticks; unvalidated starting threshold'),
        ('gripper-baseline-seconds', .5, 'Stable gripper-position window after settling'),
        ('baseline-seconds', 3., 'Contiguous stable rolling baseline duration'),
        ('settle-seconds', 2., 'Initial support-transfer settling interval; zero disables'),
        ('baseline-timeout-seconds', 12., 'Maximum baseline wait after settling'),
        ('sustain-seconds', .25, 'Continuous same-joint candidate duration'),
        ('max-gap-seconds', .5, 'Abort on stale/slow telemetry'),
        ('poll-hz', 20., 'Requested sampling frequency; serial reads may be slower'),
        ('load-delta', 30., 'Absolute raw load deviation from median baseline'),
        ('current-delta', 30., 'Absolute raw current deviation from median baseline'),
        ('position-delta', 4., 'Required raw tick displacement on the same joint'),
        ('baseline-position-span', 8., 'Maximum baseline peak-to-peak raw ticks'),
        ('baseline-load-span', 30., 'Maximum baseline peak-to-peak raw load'),
        ('baseline-current-span', 30., 'Maximum baseline peak-to-peak raw current')]:
        parser.add_argument('--' + name, type=float, default=default, help=help_text)
    args = parser.parse_args(argv)
    if not args.port:
        parser.error('--port or config/arms.env LEADER_PORT is required')
    follower = ports.get('FOLLOWER_PORT')
    if follower and Path(args.port).resolve() == Path(follower).resolve():
        parser.error('refusing configured follower port; this probe is leader-only')
    values = vars(args).copy()
    values['duration_seconds'] = values.pop('duration')
    for key in ('port', 'evidence_dir'):
        values.pop(key)
    settings = Settings(**values)
    try:
        settings.validate()
    except ValueError as exc:
        parser.error(str(exc))
    def arm():
        print('SUPPORT THE LEADER ARM. Hold current pose; default mode leaves the light gripper torque OFF. Move it only after Ready; support arm before release. Torque drops on error, Ctrl+C or exit.')
        return input('Keep supporting it; type ARM to enable current-pose holding: ').strip() == 'ARM'
    def terminate(signum, frame):
        raise KeyboardInterrupt('SIGTERM')
    old_handler = signal.signal(signal.SIGTERM, terminate)
    try:
        print(f'Leader port: {args.port}\nEvidence: {args.evidence_dir}', flush=True)
        run_probe(make_bus(args.port), settings, args.evidence_dir, arm=arm)
    except KeyboardInterrupt:
        print('Stopped. Support arm; inspect evidence for verified torque release.', flush=True)
        return 130
    finally:
        signal.signal(signal.SIGTERM, old_handler)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
