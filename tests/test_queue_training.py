import importlib.util
import json
import pathlib
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('queue_training', pathlib.Path(__file__).resolve().parents[1] / 'tools' / 'queue_training.py')
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.green = self.root / 'green'; self.green.mkdir()
        self.red = self.root / 'red'; self.red.mkdir()
        self.ckpt = self.root / 'checkpoint'; self.ckpt.mkdir()
        (self.green / 'run.pid').write_text('123')
    def success(self):
        (self.green / 'exit_code.txt').write_text('exit_code=0\n')
        for f in ('config.json', 'model.safetensors'):
            (self.ckpt / f).write_text('ok')
    def test_running(self):
        with patch.object(q, 'alive', return_value=True):
            self.assertEqual(q.green_state(self.green, self.ckpt)[0], 'waiting_green')
    def test_failed(self):
        (self.green / 'exit_code.txt').write_text('exit_code=1\n')
        self.assertEqual(q.green_state(self.green, self.ckpt)[0], 'blocked')
    def test_missing(self):
        with patch.object(q, 'alive', return_value=False):
            self.assertEqual(q.green_state(self.green, self.ckpt)[0], 'blocked')
    def test_incomplete_success(self):
        (self.green / 'exit_code.txt').write_text('exit_code=0\n')
        self.assertEqual(q.green_state(self.green, self.ckpt)[0], 'blocked')
    def test_completed(self):
        self.success()
        self.assertEqual(q.green_state(self.green, self.ckpt)[0], 'ready')
    def test_duplicate_lock(self):
        with q.lock(self.red / 'queue.lock'):
            with self.assertRaises(BlockingIOError):
                with q.lock(self.red / 'queue.lock'): pass
    def test_launch_and_duplicate(self):
        with patch.object(q.subprocess, 'Popen') as run:
            run.return_value.wait.return_value = 0
            q.launch(self.red, lambda *args: None)
            run.assert_called_once_with(['bash', str(self.red / 'run.sh')])
            with self.assertRaises(FileExistsError): q.launch(self.red, lambda *args: None)
    def test_launch_failure(self):
        with patch.object(q.subprocess, 'Popen') as run:
            run.return_value.wait.return_value = 17
            self.assertEqual(q.launch(self.red, lambda *args: None), 17)
            self.assertTrue((self.red / 'queue_launch.json').exists())

class QueueIntegrationTests(QueueTests):
    def command(self):
        return [sys.executable, str(pathlib.Path(q.__file__)), '--evidence', str(self.red), '--green-evidence', str(self.green), '--green-checkpoint', str(self.ckpt), '--poll-seconds', '0.05']
    def test_end_to_end_success(self):
        self.success()
        (self.red / 'run.sh').write_text('echo launched > "' + str(self.red / 'actual_launch') + '"\n')
        result = subprocess.run(self.command(), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.red / 'actual_launch').exists())
        self.assertEqual(json.loads((self.red / 'queue_status.json').read_text())['state'], 'completed')
        second = subprocess.run(self.command(), capture_output=True, text=True, timeout=5)
        self.assertEqual(second.returncode, 73)
    def test_end_to_end_wait_then_success(self):
        child = subprocess.Popen(['sleep', '10'])
        self.addCleanup(child.wait)
        self.addCleanup(lambda: child.poll() is None and child.terminate())
        (self.green / 'run.pid').write_text(str(child.pid))
        (self.red / 'run.sh').write_text('exit 0\n')
        queue = subprocess.Popen(self.command(), stdout=subprocess.DEVNULL)
        self.addCleanup(queue.wait)
        self.addCleanup(lambda: queue.poll() is None and queue.terminate())
        deadline = time.monotonic() + 3
        while not (self.red / 'queue_status.json').exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(json.loads((self.red / 'queue_status.json').read_text())['state'], 'waiting_green')
        duplicate = subprocess.run(self.command(), capture_output=True, timeout=5)
        self.assertEqual(duplicate.returncode, 73)
        self.success()
        self.assertEqual(queue.wait(timeout=5), 0)
    def test_end_to_end_missing(self):
        (self.green / 'run.pid').write_text('99999999')
        result = subprocess.run(self.command(), capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 74)
        self.assertEqual(json.loads((self.red / 'queue_status.json').read_text())['state'], 'blocked')
        self.assertFalse((self.red / 'queue_launch.json').exists())

class QueueReviewTests(QueueIntegrationTests):
    def test_running_red_status(self):
        self.success()
        (self.red / 'run.sh').write_text('sleep .3\n')
        queue = subprocess.Popen(self.command(), stdout=subprocess.DEVNULL)
        self.addCleanup(queue.wait)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status_file = self.red / 'queue_status.json'
            if status_file.exists() and json.loads(status_file.read_text())['state'] == 'running_red': break
            time.sleep(.01)
        self.assertEqual(json.loads(status_file.read_text())['state'], 'running_red')
        self.assertEqual(queue.wait(timeout=5), 0)
    def test_invalid_poll_interval(self):
        for value in ('0', '-1', 'nan', 'inf'):
            command = self.command()
            command[-1] = value
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
    def test_detach_repeat_preserves_log_and_pid(self):
        child = subprocess.Popen(['sleep', '10'])
        self.addCleanup(child.wait)
        self.addCleanup(lambda: child.poll() is None and child.terminate())
        (self.green / 'run.pid').write_text(str(child.pid))
        command = self.command() + ['--detach']
        first = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(first.returncode, 0, first.stderr)
        pid = (self.red / 'queue.pid').read_text()
        self.addCleanup(lambda: q.os.kill(int(pid), 15) if q.alive(pid.strip()) else None)
        log = self.red / 'queue.log'
        deadline = time.monotonic() + 3
        while not log.stat().st_size and time.monotonic() < deadline: time.sleep(.01)
        before = log.read_bytes()
        second = subprocess.run(command, capture_output=True, timeout=5)
        self.assertEqual(second.returncode, 73)
        self.assertEqual((self.red / 'queue.pid').read_text(), pid)
        self.assertTrue(log.read_bytes().startswith(before))

if __name__ == '__main__': unittest.main()
