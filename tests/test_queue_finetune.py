import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from tools import queue_finetune as q


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def job(tmp_path):
    predecessor, checkpoint, evidence = (tmp_path / x for x in ('prior', 'checkpoint', 'queue'))
    for path in (predecessor, checkpoint, evidence):
        path.mkdir()
    (predecessor / 'run.pid').write_text('99999999')
    script = tmp_path / 'run.sh'
    script.write_text('printf launched > ' + str(tmp_path / 'launched') + '\n')
    config = tmp_path / 'config.json'
    config.write_text('{}')
    checks = {}
    for name in ('dataset', 'environment', 'model', 'local_smoke'):
        path = tmp_path / (name + '.json')
        path.write_text(json.dumps({'passed': True}))
        checks[name] = {'path': str(path), 'sha256': digest(path)}
    approval = tmp_path / 'approved.json'
    approval.write_text(json.dumps({'passed': True, 'checks': checks,
                                   'run_script': {'path': str(script), 'sha256': digest(script)},
                                   'config': {'path': str(config), 'sha256': digest(config)}}))
    return dict(root=tmp_path, prior=predecessor, checkpoint=checkpoint, evidence=evidence,
                approval=approval, script=script)


def succeed(job):
    (job['prior'] / 'exit_code.txt').write_text('exit_code=0\n')
    for name in ('config.json', 'model.safetensors'):
        (job['checkpoint'] / name).write_text('ok')


def command(job):
    return [sys.executable, str(Path(q.__file__)), '--evidence', str(job['evidence']),
            '--prerequisite-evidence', str(job['prior']), '--prerequisite-checkpoint', str(job['checkpoint']),
            '--approval', str(job['approval']), '--poll-seconds', '0.03']


def wait_status(path, state):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        if path.exists() and json.loads(path.read_text())['state'] == state:
            return
        time.sleep(.01)
    raise AssertionError(f'No {state} state: {path.read_text() if path.exists() else "missing"}')


def test_success_receipt_does_not_bypass_live_predecessor(job):
    succeed(job)
    (job['prior'] / 'run.pid').write_text(str(os.getpid()))
    assert q.prerequisite_state(job['prior'], job['checkpoint'])[0] == 'waiting_prerequisite'


def test_reused_pid_does_not_count_as_original_live_process(job):
    succeed(job)
    (job['prior'] / 'run.pid').write_text(str(os.getpid()))
    identity = q.process_identity(os.getpid())
    identity['start_ticks'] -= 1
    assert q.prerequisite_state(job['prior'], job['checkpoint'], identity)[0] == 'ready'


@pytest.mark.parametrize('case', ['failed', 'disappeared', 'missing_checkpoint'])
def test_predecessor_failure_never_launches(job, case):
    if case == 'failed':
        (job['prior'] / 'exit_code.txt').write_text('exit_code=1')
    elif case == 'missing_checkpoint':
        (job['prior'] / 'exit_code.txt').write_text('exit_code=0')
    result = subprocess.run(command(job), capture_output=True, timeout=5)
    assert result.returncode == 74
    assert not (job['root'] / 'launched').exists()
    assert not (job['evidence'] / 'queue_launch.json').exists()


@pytest.mark.parametrize('kind', ['dataset', 'environment', 'model', 'local_smoke'])
def test_unapproved_or_modified_receipt_is_rejected(job, kind):
    succeed(job)
    (job['root'] / (kind + '.json')).write_text(json.dumps({'passed': False}))
    result = subprocess.run(command(job), capture_output=True, timeout=5)
    assert result.returncode == 74
    assert not (job['root'] / 'launched').exists()


def test_reviewed_approval_and_script_must_remain_unchanged(job):
    with pytest.raises(ValueError, match='approval'):
        q.verify_approval(job['approval'], '0' * 64)
    pinned = digest(job['approval'])
    job['script'].write_text('exit 0\n')
    with pytest.raises(ValueError, match='run_script'):
        q.verify_approval(job['approval'], pinned)


def test_matching_hash_does_not_turn_a_failed_receipt_into_approval(job):
    document = json.loads(job['approval'].read_text())
    receipt = job['root'] / 'environment.json'
    receipt.write_text(json.dumps({'passed': False}))
    document['checks']['environment']['sha256'] = digest(receipt)
    job['approval'].write_text(json.dumps(document))
    with pytest.raises(ValueError, match='environment receipt did not pass'):
        q.verify_approval(job['approval'], digest(job['approval']))


def test_finetune_failure_remains_blocked_and_cannot_silently_retry(job):
    succeed(job)
    job['script'].write_text('exit 17\n')
    document = json.loads(job['approval'].read_text())
    document['run_script']['sha256'] = digest(job['script'])
    job['approval'].write_text(json.dumps(document))
    result = subprocess.run(command(job), capture_output=True, timeout=5)
    assert result.returncode == 17
    assert json.loads((job['evidence'] / 'queue_status.json').read_text())['state'] == 'blocked'
    assert (job['evidence'] / 'queue_launch.json').exists()
    assert subprocess.run(command(job), capture_output=True, timeout=5).returncode == 73


def test_wait_then_launch_once_after_success_and_actual_exit(job):
    child = subprocess.Popen(['sleep', '30'])
    queue = None
    try:
        (job['prior'] / 'run.pid').write_text(str(child.pid))
        queue = subprocess.Popen(command(job), stdout=subprocess.DEVNULL)
        status = job['evidence'] / 'queue_status.json'
        wait_status(status, 'waiting_prerequisite')
        succeed(job)
        time.sleep(.08)
        assert not (job['root'] / 'launched').exists()
        child.terminate(); child.wait(timeout=5)
        assert queue.wait(timeout=5) == 0
        assert (job['root'] / 'launched').read_text() == 'launched'
        assert json.loads(status.read_text())['state'] == 'completed'
        assert subprocess.run(command(job), capture_output=True, timeout=5).returncode == 73
    finally:
        for proc in (queue, child):
            if proc is not None and proc.poll() is None:
                proc.terminate(); proc.wait(timeout=5)


def test_detach_duplicate_preserves_log_pid_and_receipts(job):
    child = subprocess.Popen(['sleep', '30'])
    pid = None
    try:
        (job['prior'] / 'run.pid').write_text(str(child.pid))
        first = subprocess.run(command(job) + ['--detach'], capture_output=True, timeout=5)
        assert first.returncode == 0, first.stderr
        pidfile = job['evidence'] / 'queue.pid'
        pid = int(pidfile.read_text())
        wait_status(job['evidence'] / 'queue_status.json', 'waiting_prerequisite')
        snapshot = {name: (job['evidence'] / name).read_bytes()
                    for name in ('queue.pid', 'queue_start.json', 'queue.log')}
        again = subprocess.run(command(job) + ['--detach'], capture_output=True, timeout=5)
        assert again.returncode == 73
        for name in ('queue.pid', 'queue_start.json'):
            assert (job['evidence'] / name).read_bytes() == snapshot[name]
        assert (job['evidence'] / 'queue.log').read_bytes().startswith(snapshot['queue.log'])
        # An unrelated repeated CLI must not overwrite the active queue status,
        # even if someone has since changed its reviewed approval file.
        job['approval'].write_text('{}')
        assert subprocess.run(command(job) + ['--detach'], capture_output=True, timeout=5).returncode == 73
        state = json.loads((job['evidence'] / 'queue_status.json').read_text())
        assert state['state'] == 'waiting_prerequisite'
        assert state['pid'] == pid
    finally:
        if pid is not None and q.process_identity(pid):
            os.kill(pid, 15)
        child.terminate(); child.wait(timeout=5)


def test_approval_changed_while_waiting_cannot_launch(job):
    child = subprocess.Popen(['sleep', '30'])
    queue = None
    try:
        (job['prior'] / 'run.pid').write_text(str(child.pid))
        queue = subprocess.Popen(command(job), stdout=subprocess.DEVNULL)
        wait_status(job['evidence'] / 'queue_status.json', 'waiting_prerequisite')
        # The replacement remains superficially valid, but is no longer the
        # approved immutable artifact the running queue pinned at startup.
        document = json.loads(job['approval'].read_text())
        document['review_note'] = 'changed after launch'
        job['approval'].write_text(json.dumps(document))
        succeed(job)
        child.terminate(); child.wait(timeout=5)
        assert queue.wait(timeout=5) == 74
        assert not (job['root'] / 'launched').exists()
    finally:
        for proc in (queue, child):
            if proc is not None and proc.poll() is None:
                proc.terminate(); proc.wait(timeout=5)


@pytest.mark.parametrize('poll', ['0', '-1', 'nan', 'inf'])
def test_invalid_poll_never_detaches(job, poll):
    cmd = command(job); cmd[-1] = poll
    assert subprocess.run(cmd + ['--detach'], capture_output=True, timeout=5).returncode == 2
    assert not (job['evidence'] / 'queue_start.json').exists()
