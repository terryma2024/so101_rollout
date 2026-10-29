"""Exercise public entry boundaries without loading robot or model runtimes."""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_voice_patch_targets_canonical_module(monkeypatch):
    # A root forwarding module must never receive patches intended for the implementation.
    assert importlib.util.find_spec('so101_test.voice') is not None, 'canonical voice package is missing'
    from so101_test.voice import voice_agent

    assert voice_agent is importlib.import_module('so101_test.voice.voice_agent')
    messages, commands, events = [], [], []
    monkeypatch.setattr(voice_agent, 'say', messages.append)

    class Runner:
        def submit(self, kind, colour=None):
            commands.append((kind, colour))

    voice_agent.handle_text(Runner(), events.append, '红', 'keyboard')
    assert commands == [('run', 'red')]
    assert messages == ["[keyboard] '红' -> red"]
    assert events == [{'event': 'input', 'source': 'keyboard', 'text': '红',
                       'intent': 'red', 'intent_source': 'rules'}]


VOICE_HELP_PROBE = r'''
import contextlib
import importlib.abc
import io
import json
import os
from pathlib import Path
import runpy
import sys

entry, repo = sys.argv[1:]
attempts = []
blocked = {'voice_policy', 'voice_fake_robot', 'voice_asr', 'lerobot', 'torch',
           'cv2', 'sounddevice', 'faster_whisper', 'feetech_servo_sdk', 'serial', 'requests'}

class DenyRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(part in blocked for part in fullname.split('.')):
            attempts.append(fullname)
            raise AssertionError('forbidden runtime import: ' + fullname)

def audit(event, args):
    if event in {'socket.connect', 'socket.bind', 'subprocess.Popen', 'os.system', 'ctypes.dlopen'}:
        attempts.append(event)
        raise AssertionError('forbidden runtime action: ' + event)
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0])
        if path.startswith(('/dev/', '/data/work/models/', '/data/work/so101-policies/', '/data/models/')) or Path(path).name in {'arms.env', 'camera.env'}:
            attempts.append(path)
            raise AssertionError('forbidden runtime read: ' + path)

sys.meta_path.insert(0, DenyRuntime())
sys.addaudithook(audit)
output = io.StringIO()
with contextlib.redirect_stdout(output):
    if entry.endswith('.py'):
        # Importing the compatibility file must not dispatch main.
        runpy.run_path(str(Path(repo) / entry), run_name='stub_import_probe')
        assert not output.getvalue(), output.getvalue()
        assert not any(name.startswith('so101_test.voice.') for name in sys.modules)
    sys.argv = [entry, '--help']
    try:
        if entry.endswith('.py'):
            runpy.run_path(str(Path(repo) / entry), run_name='__main__')
        else:
            # This is the same module dispatch Python uses for its -m option.
            runpy._run_module_as_main(entry)
    except SystemExit as exc:
        assert exc.code == 0, exc.code
    else:
        raise AssertionError('--help did not exit')

assert not attempts, attempts
assert not any(any(part in blocked for part in name.split('.')) for name in sys.modules)
print(json.dumps({'help': output.getvalue(), 'attempts': attempts,
                  'config': os.environ.get('SO101_CONFIG_DIR'), 'python': sys.executable}))
'''


def voice_help_probe(entry, cwd, config=None):
    env = {key: value for key, value in os.environ.items()
           if key not in ('PYTHONPATH', 'AMENT_PREFIX_PATH', 'COLCON_PREFIX_PATH',
                          'SO101_CONFIG_DIR', 'VOICE_GREEN_POLICY', 'VOICE_RED_POLICY',
                          'VOICE_LOG_DIR', 'MAX_REL')}
    if config is not None:
        env['SO101_CONFIG_DIR'] = config
    return subprocess.run([sys.executable, '-I', '-c', VOICE_HELP_PROBE, entry, str(REPO)],
                          cwd=cwd, env=env, text=True, capture_output=True, timeout=15)


@pytest.mark.parametrize('entry', ['so101_test.voice.voice_agent', 'voice_agent.py',
                                 'so101_test.voice.voice_latency_check', 'voice_latency_check.py'])
@pytest.mark.parametrize('config', [None, '', 'missing selected config'])
def test_voice_help_stays_inert(tmp_path, entry, config):
    result = voice_help_probe(entry, tmp_path, config)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert 'usage:' in payload['help'] and '--green-policy' in payload['help']
    assert payload['attempts'] == []
    assert payload['python'] == sys.executable
    expected_config = str(REPO / 'config') if config is None and entry.endswith('.py') else config
    assert payload['config'] == expected_config
