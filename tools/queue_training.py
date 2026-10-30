#!/usr/bin/env python3
"""Durable, fail-closed queue for an approved training job (stdlib only)."""
import argparse
import contextlib
import datetime
import fcntl
import json
import math
import sys
import os
from pathlib import Path
import subprocess
import time


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


@contextlib.contextmanager
def lock(path):
    with path.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield handle


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return Path(f'/proc/{pid}/stat').read_text().split()[2] != 'Z'
    except (OSError, ValueError):
        return False


def green_state(evidence, checkpoint):
    receipt = evidence / 'exit_code.txt'
    if receipt.exists():
        if receipt.read_text().strip() != 'exit_code=0':
            return 'blocked', 'green failed: ' + receipt.read_text().strip()
        for filename in ('config.json', 'model.safetensors'):
            p = checkpoint / filename
            if not p.is_file() or not p.stat().st_size:
                return 'blocked', 'green final checkpoint missing: ' + str(p)
        return 'ready', 'green succeeded with final checkpoint'
    pidfile = evidence / 'run.pid'
    if pidfile.exists() and alive(pidfile.read_text().strip()):
        return 'waiting_green', 'green process active'
    return 'blocked', 'green disappeared without successful completion evidence'


def launch(evidence, status):
    marker = evidence / 'queue_launch.json'
    # Exclusive creation persists even after failures: never silently retry training.
    with marker.open('x') as handle:
        json.dump({'pid': os.getpid(), 'time': datetime.datetime.now(datetime.timezone.utc).isoformat()}, handle)
    process = subprocess.Popen(['bash', str(evidence / 'run.sh')])
    status('running_red', f'RED run pid={process.pid}')
    return process.wait()


def detach(evidence):
    # A durable exclusive receipt also rejects repeats after an early queue failure.
    if any((evidence / name).exists() for name in ('queue.log', 'queue.pid', 'started.txt', 'queue_launch.json')):
        print('Prior queue/run evidence exists; inspect before retrying', file=sys.stderr)
        return 73
    try:
        with (evidence / 'queue_start.json').open('x') as receipt:
            json.dump({'requested_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}, receipt)
    except FileExistsError:
        print('Duplicate launch refused: queue_start.json exists', file=sys.stderr)
        return 73
    with (evidence / 'queue.log').open('xb') as log:
        command = [sys.executable, str(Path(__file__).resolve())] + [arg for arg in sys.argv[1:] if arg != '--detach']
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    with (evidence / 'queue.pid').open('x') as pidfile:
        pidfile.write(str(process.pid) + '\n')
    print(f'Detached queue pid={process.pid}; evidence={evidence}')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--green-evidence', type=Path, required=True)
    parser.add_argument('--green-checkpoint', type=Path, required=True)
    parser.add_argument('--poll-seconds', type=float, default=60)
    parser.add_argument('--detach', action='store_true', help='start persistent queue once; preserve receipt on failure')
    args = parser.parse_args()
    if not math.isfinite(args.poll_seconds) or args.poll_seconds <= 0:
        parser.error('--poll-seconds must be finite and greater than zero')
    e = args.evidence
    if args.detach:
        return detach(e)
    def status(state, reason):
        payload = dict(state=state, reason=reason, pid=os.getpid(), updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        write_json(e / 'queue_status.json', payload)
        print(json.dumps(payload), flush=True)
    try:
        with lock(e / 'queue.lock'):
            if (e / 'queue_launch.json').exists() or (e / 'started.txt').exists():
                status('blocked', 'prior RED launch evidence exists; refusing repeat')
                return 73
            while True:
                state, reason = green_state(args.green_evidence, args.green_checkpoint)
                status(state, reason)
                if state == 'blocked': return 74
                if state == 'ready': break
                time.sleep(args.poll_seconds)
            # run.sh acquires its own run.lock and validates approval and active trainers.
            status('launching_red', 'green completion verified; running guarded RED launch')
            rc = launch(e, status)
            status('completed' if rc == 0 else 'blocked', f'RED run exit_code={rc}')
            return rc
    except BlockingIOError:
        print('Duplicate queue refused: queue.lock held', flush=True)
        return 73
    except Exception as exc:
        status('blocked', f'{type(exc).__name__}: {exc}')
        return 74


if __name__ == '__main__':
    raise SystemExit(main())
