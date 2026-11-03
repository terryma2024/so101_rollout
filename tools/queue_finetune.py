#!/usr/bin/env python3
"""Persistent, fail-closed prerequisite-to-finetune queue (stdlib only).

This file is standalone so the same reviewed artifact can run on the trainer.
The launched run.sh must independently validate its data/model manifests and
exclude other active trainers; this queue validates the frozen approval chain.
"""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def process_identity(pid):
    """Return live Linux PID identity; zombies count as exited, not active."""
    try:
        pid = int(pid)
        if pid <= 1:
            return None
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] == 'Z':
            return None
        return {'pid': pid, 'start_ticks': int(fields[19])}
    except (OSError, ValueError, IndexError):
        return None


def prerequisite_state(evidence, checkpoint, expected_identity=None):
    pidfile = evidence / 'run.pid'
    if not pidfile.is_file():
        return 'blocked', 'prerequisite run.pid missing'
    try:
        pid = int(pidfile.read_text().strip())
        if pid <= 1:
            raise ValueError('invalid PID')
    except ValueError:
        return 'blocked', 'prerequisite PID invalid'
    if expected_identity and pid != expected_identity['pid']:
        return 'blocked', 'prerequisite run.pid changed'
    identity = process_identity(pid)
    still_running = identity is not None and (expected_identity is None or identity == expected_identity)
    receipt = evidence / 'exit_code.txt'
    if receipt.exists():
        if receipt.read_text().strip() != 'exit_code=0':
            return 'blocked', 'prerequisite did not finish successfully'
        for name in ('config.json', 'model.safetensors'):
            path = checkpoint / name
            if not path.is_file() or not path.stat().st_size:
                return 'blocked', f'prerequisite final checkpoint missing: {path}'
        if still_running:
            return 'waiting_prerequisite', 'success receipt present; prerequisite process still active'
        return 'ready', 'prerequisite succeeded, final checkpoint complete, process exited'
    if still_running:
        return 'waiting_prerequisite', 'prerequisite process active'
    return 'blocked', 'prerequisite disappeared without successful completion evidence'


def checked_file(record, label):
    path = Path(record['path'])
    if not path.is_absolute() or not path.is_file() or digest(path) != record['sha256']:
        raise ValueError(f'{label} file missing or hash changed: {path}')
    return path


def verify_approval(path, expected_sha256):
    if digest(path) != expected_sha256:
        raise ValueError('approval hash changed')
    approved = json.loads(path.read_text())
    if approved.get('passed') is not True:
        raise ValueError('approval did not pass')
    for name in ('dataset', 'environment', 'model', 'local_smoke'):
        receipt = checked_file(approved['checks'][name], name)
        if json.loads(receipt.read_text()).get('passed') is not True:
            raise ValueError(f'{name} receipt did not pass')
    script = checked_file(approved['run_script'], 'run_script')
    checked_file(approved['config'], 'config')
    return script


def write_json(path, payload):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, indent=2) + '\n')
    temporary.replace(path)


@contextlib.contextmanager
def locked(path):
    with path.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def detach(args, pinned_hash):
    evidence = args.evidence
    previous = ('queue.log', 'queue.pid', 'queue_start.json', 'queue_launch.json', 'started.txt')
    if any((evidence / name).exists() for name in previous):
        print('Prior queue/run evidence exists; inspect before retrying', file=sys.stderr)
        return 73
    # Durable exclusive receipt prevents concurrent duplicate launch and retries.
    try:
        with (evidence / 'queue_start.json').open('x') as handle:
            json.dump({'requested_at': now(), 'approval_sha256': pinned_hash}, handle)
    except FileExistsError:
        return 73
    command = [sys.executable, str(Path(__file__).resolve()), '--evidence', str(evidence),
               '--prerequisite-evidence', str(args.prerequisite_evidence),
               '--prerequisite-checkpoint', str(args.prerequisite_checkpoint),
               '--approval', str(args.approval), '--approval-sha256', pinned_hash,
               '--poll-seconds', str(args.poll_seconds)]
    with (evidence / 'queue.log').open('xb') as log:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
    with (evidence / 'queue.pid').open('x') as handle:
        handle.write(str(child.pid) + '\n')
    print(f'Detached finetune queue pid={child.pid}; evidence={evidence}')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--prerequisite-evidence', type=Path, required=True)
    parser.add_argument('--prerequisite-checkpoint', type=Path, required=True)
    parser.add_argument('--approval', type=Path, required=True)
    parser.add_argument('--approval-sha256', help='pin reviewed approval; otherwise freeze its initial hash')
    parser.add_argument('--poll-seconds', type=float, default=15)
    parser.add_argument('--detach', action='store_true')
    args = parser.parse_args()
    if not math.isfinite(args.poll_seconds) or args.poll_seconds <= 0:
        parser.error('poll interval must be finite and positive')
    if not args.evidence.is_dir():
        parser.error('evidence directory must already exist')
    args.approval = args.approval.resolve()
    expected_identity = None

    def status(state, reason):
        payload = {'state': state, 'reason': reason, 'pid': os.getpid(),
                   'updated_at': now(), 'prerequisite_identity': expected_identity}
        write_json(args.evidence / 'queue_status.json', payload)
        print(json.dumps(payload), flush=True)

    if args.detach and any((args.evidence / name).exists() for name in
                           ('queue.log', 'queue.pid', 'queue_start.json', 'queue_launch.json', 'started.txt')):
        print('Prior queue/run evidence exists; inspect before retrying', file=sys.stderr)
        return 73
    try:
        if args.detach:
            pinned_hash = args.approval_sha256 or digest(args.approval)
            verify_approval(args.approval, pinned_hash)
            return detach(args, pinned_hash)
        with locked(args.evidence / 'queue.lock'):
            if any((args.evidence / name).exists() for name in ('queue_launch.json', 'started.txt')):
                return 73
            pinned_hash = args.approval_sha256 or digest(args.approval)
            verify_approval(args.approval, pinned_hash)
            pidfile = args.prerequisite_evidence / 'run.pid'
            if pidfile.is_file():
                expected_identity = process_identity(pidfile.read_text().strip())
            while True:
                state, reason = prerequisite_state(args.prerequisite_evidence,
                                                   args.prerequisite_checkpoint, expected_identity)
                status(state, reason)
                if state == 'blocked':
                    return 74
                if state == 'ready':
                    break
                time.sleep(args.poll_seconds)
            script = verify_approval(args.approval, pinned_hash)
            with (args.evidence / 'queue_launch.json').open('x') as marker:
                json.dump({'launched_at': now(), 'approval_sha256': pinned_hash,
                           'script': str(script)}, marker)
            status('launching', 'prerequisite exited successfully; running guarded script')
            child = subprocess.Popen(['bash', str(script)], cwd=script.parent)
            status('running', f'finetune run pid={child.pid}')
            code = child.wait()
            status('completed' if code == 0 else 'blocked', f'finetune run exit_code={code}')
            return code
    except BlockingIOError:
        print('Duplicate queue refused: queue.lock held', file=sys.stderr)
        return 73
    except Exception as exc:
        status('blocked', f'{type(exc).__name__}: {exc}')
        return 74


if __name__ == '__main__':
    raise SystemExit(main())
