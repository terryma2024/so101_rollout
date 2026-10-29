"""Run launchers only in copied checkouts with all external commands stubbed."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
NAMES = ('voice_agent', 'teleop', 'record', 'rollout', 'calibrate_follower', 'calibrate_leader', 'camera_settings')


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / 'checkout with spaces'
    root.mkdir()
    fake = tmp_path / 'fake-bin'
    fake.mkdir()
    (fake / 'bin').mkdir()
    capture = tmp_path / 'capture.jsonl'
    # Only temporary copies have fixed runtime prefixes redirected.
    for name in NAMES:
        shutil.copy2(REPO / f'{name}.sh', root)
    shutil.copytree(REPO / 'scripts', root / 'scripts')
    config = root / 'config'
    config.mkdir()
    for name in ('arms.env', 'camera.env'):
        shutil.copy2(REPO / 'config' / name, config / name)
    for path in root.rglob('*.sh'):
        value = path.read_text()
        for prefix in ('/data/work/venvs/so101-real-lerobot-061', '/data/work/venvs/so101-voice-lerobot-061'):
            value = value.replace(prefix, str(fake))
        path.write_text(value)
        path.chmod(0o755)
    stub = '#!' + sys.executable + '\n' + '''import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
with open(os.environ['CAPTURE'], 'a') as stream:
    stream.write(json.dumps({'name': name, 'executable': sys.argv[0], 'args': sys.argv[1:], 'cwd': os.getcwd(), 'env': {k: os.environ.get(k) for k in ('FOLLOWER_PORT','LEADER_PORT','WRIST_EXPOSURE','SIDE_WB','RERUN_VIEWER_HOST','RERUN_VIEWER_PORT','SO101_CONFIG_DIR','PYTHONPATH','AMENT_PREFIX_PATH','COLCON_PREFIX_PATH','HF_HOME','TORCH_HOME')}}) + '\\n')
if name == 'xdpyinfo': sys.exit(1)
if name in ('timeout', 'v4l2-ctl'): sys.exit(0)
sys.exit(23)
'''
    for name in ('python', 'lerobot-rollout'):
        (fake / 'bin' / name).write_text(stub)
        (fake / 'bin' / name).chmod(0o755)
    for name in ('uv', 'xdpyinfo', 'timeout', 'v4l2-ctl'):
        (fake / name).write_text(stub)
        (fake / name).chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k not in ('SO101_CONFIG_DIR', 'VENV', 'FOLLOWER_PORT', 'LEADER_PORT', 'RERUN_VIEWER_HOST', 'RERUN_VIEWER_PORT', 'SSH_CONNECTION')}
    env.update(PATH=str(fake) + ':/usr/bin:/bin', CAPTURE=str(capture))
    return root, fake, capture, env


@pytest.mark.parametrize('name', NAMES)
def test_wrapper_forwards_argv_and_exit(checkout, tmp_path, name):
    root, _, capture, env = checkout
    body = root / 'scripts' / f'{name}.sh'
    body.parent.mkdir(exist_ok=True)
    body.write_text('#!/bin/bash\nexec "' + sys.executable + '" -c \'import json,os,sys; print(json.dumps([os.getcwd(),sys.argv[1:]])); sys.exit(23)\' "$@"\n')
    body.chmod(0o755)
    result = subprocess.run([str(root / f'{name}.sh'), 'with spaces', '', 'tail'], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 23, result.stderr
    assert json.loads(result.stdout) == [str(tmp_path), ['with spaces', '', 'tail']]
    assert not capture.exists()  # No legacy body or hardware utility reached.


@pytest.mark.parametrize('name,args,expected', [
    ('voice_agent', ['--fake-robot', 'green=with spaces', ''], ['-m', 'so101_rollout.voice.voice_agent', '--fake-robot', 'green=with spaces', '']),
    ('calibrate_follower', [], ['run', '--no-sync', 'lerobot-calibrate', '--robot.type=so101_follower', '--robot.port=override port', '--robot.id=my_follower']),
    ('calibrate_leader', [], ['run', '--no-sync', 'lerobot-calibrate', '--teleop.type=so101_leader', '--teleop.port=', '--teleop.id=my_leader']),
    ('camera_settings', ['snap'], ['-m', 'so101_rollout.camera.calib_capture', 'snap']),
    ('teleop', [], None), ('record', ['unit-test-unused', '2'], None), ('rollout', None, None),
])
def test_shell_defaults_preserve_environment(checkout, tmp_path, name, args, expected):
    root, _, capture, env = checkout
    env.update(FOLLOWER_PORT='override port', LEADER_PORT='', WRIST_EXPOSURE='override exposure', SIDE_WB='', SSH_CONNECTION='192.0.2.4 12 192.0.2.5 22', PYTHONPATH='must be removed by voice')
    if name == 'rollout':
        policy = tmp_path / 'policy with spaces'
        policy.mkdir()
        (policy / 'model.safetensors').touch()
        args = [str(policy), 'unit-test-unused', '2']
    # Avoid camera utility side effects during lock while still running the real helper/body.
    if name in ('record', 'rollout'):
        (root / 'camera_settings.sh').write_text('#!/bin/bash\nexit 0\n')
    result = subprocess.run([str(root / f'{name}.sh'), *args], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 23, result.stderr
    calls = [json.loads(line) for line in capture.read_text().splitlines()]
    child = calls[-1]
    assert child['cwd'] == str(root)
    assert child['env']['FOLLOWER_PORT'] == 'override port'
    assert child['env']['LEADER_PORT'] == ''
    assert child['env']['SO101_CONFIG_DIR'] == str(root / 'config')
    assert child['env']['RERUN_VIEWER_HOST'] == '192.0.2.4'
    if expected is not None:
        assert child['args'] == expected
    if name == 'camera_settings':
        assert child['env']['WRIST_EXPOSURE'] == 'override exposure'
        assert child['env']['SIDE_WB'] == ''
    if name == 'voice_agent':
        assert child['env']['PYTHONPATH'] is None
    if name in ('teleop', 'record', 'rollout'):
        assert '--display_ip=192.0.2.4' in child['args']
        assert any('--robot.port=override port' == arg for arg in child['args'])


@pytest.mark.parametrize('override', [False, True])
@pytest.mark.parametrize('args', [['--help'], ['-h'], ['--fake-robot', 'green=with spaces', '']])
def test_voice_launcher_preserves_runtime_boundary(checkout, tmp_path, override, args):
    root, fake, capture, env = checkout
    selected = fake
    if override:
        selected = tmp_path / 'overridden voice environment'
        (selected / 'bin').mkdir(parents=True)
        shutil.copy2(fake / 'bin' / 'python', selected / 'bin' / 'python')
        env['VENV'] = str(selected)
    # A camera-lock call would fail before reaching the selected Python.
    (root / 'camera_settings.sh').write_text('#!/bin/bash\nexit 97\n')
    env.update(PYTHONPATH='forbidden overlay', AMENT_PREFIX_PATH='forbidden overlay',
               COLCON_PREFIX_PATH='forbidden overlay')
    env.pop('HF_HOME', None)
    env.pop('TORCH_HOME', None)
    result = subprocess.run([str(root / 'voice_agent.sh'), *args], cwd=tmp_path,
                            env=env, capture_output=True, text=True)
    assert result.returncode == 23, result.stderr
    calls = [json.loads(line) for line in capture.read_text().splitlines()]
    assert len(calls) == 1
    child = calls[0]
    assert child['executable'] == str(selected / 'bin' / 'python')
    assert child['args'] == ['-m', 'so101_rollout.voice.voice_agent', *args]
    assert child['cwd'] == str(root)
    assert child['env']['SO101_CONFIG_DIR'] == str(root / 'config')
    assert all(child['env'][key] is None for key in ('PYTHONPATH', 'AMENT_PREFIX_PATH', 'COLCON_PREFIX_PATH'))
    assert child['env']['HF_HOME'] == '/data/models/huggingface'
    assert child['env']['TORCH_HOME'] == '/data/models/torch'


@pytest.mark.parametrize('host,want', [(None, '100.84.127.95'), ('', ''), ('viewer override', 'viewer override')])
def test_viewer_default_and_empty_override(checkout, tmp_path, host, want):
    root, _, capture, env = checkout
    if host is not None:
        env['RERUN_VIEWER_HOST'] = host
    result = subprocess.run([str(root / 'voice_agent.sh'), '--help'], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 23
    child = json.loads(capture.read_text().splitlines()[-1])
    assert child['env']['RERUN_VIEWER_HOST'] == want


def test_selected_shell_config_and_missing_directory(checkout, tmp_path):
    root, _, capture, env = checkout
    custom = tmp_path / 'custom config'
    custom.mkdir()
    (custom / 'arms.env').write_text('FOLLOWER_PORT=custom\nRERUN_VIEWER_HOST=custom-viewer\n')
    env['SO101_CONFIG_DIR'] = str(custom)
    result = subprocess.run([str(root / 'voice_agent.sh'), '--help'], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 23
    child = json.loads(capture.read_text().splitlines()[-1])
    assert child['env']['FOLLOWER_PORT'] == 'custom'
    assert child['env']['SO101_CONFIG_DIR'] == str(custom)
    assert child['env']['RERUN_VIEWER_HOST'] == 'custom-viewer'
    before = capture.read_bytes()
    env['SO101_CONFIG_DIR'] = str(tmp_path / 'missing')
    result = subprocess.run([str(root / 'voice_agent.sh'), '--help'], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Configuration directory does not exist' in result.stderr
    assert capture.read_bytes() == before


@pytest.mark.parametrize('name,args,prefix,executable', [
    ('teleop', ['ignored extra'], ['run', '--no-sync', 'python', '-m', 'so101_rollout.operations.teleop_viz'], 'uv'),
    ('record', ['unit-test-unused', '2', 'ignored extra'], ['-m', 'so101_rollout.operations.record_viz'], 'python'),
    ('camera_settings', ['snap', 'ignored extra'], ['-m', 'so101_rollout.camera.calib_capture', 'snap'], 'python'),
])
def test_camera_operation_launchers_use_canonical_modules(checkout, tmp_path, name, args, prefix, executable):
    root, fake, capture, env = checkout
    if name == 'record':
        (root / 'camera_settings.sh').write_text('#!/bin/bash\nexit 0\n')
    result = subprocess.run([str(root / f'{name}.sh'), *args], cwd=tmp_path,
                            env=env, capture_output=True, text=True)
    assert result.returncode == 23, result.stderr
    child = json.loads(capture.read_text().splitlines()[-1])
    assert child['executable'] == str(fake / ('uv' if executable == 'uv' else 'bin/python'))
    assert child['args'][:len(prefix)] == prefix
    assert 'ignored extra' not in child['args']
    assert child['cwd'] == str(root)
    assert child['env']['SO101_CONFIG_DIR'] == str(root / 'config')
    if name == 'record':
        assert '--dataset.num_episodes=2' in child['args']
        assert '--dataset.fps=20' in child['args']
        assert '--dataset.episode_time_s=30' in child['args']
        assert '--dataset.reset_time_s=20' in child['args']
