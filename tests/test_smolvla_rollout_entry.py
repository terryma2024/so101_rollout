"""Launcher contracts without camera, serial, CUDA, or model execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.fixture
def launcher(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / 'scripts/lib').mkdir(parents=True)
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/arms.env').write_text('FOLLOWER_PORT=fake\nFOLLOWER_ID=test\nWRIST_CAM=0\nSIDE_CAM=1\nWRIST_CAM_FPS=20\nSIDE_CAM_FPS=30\n')
    shutil.copy(repo / 'scripts/lib/common.sh', tmp_path / 'scripts/lib/common.sh')
    env = tmp_path / 'env/bin'
    env.mkdir(parents=True)
    (env / 'python').symlink_to(sys.executable)
    cli = env / 'lerobot-rollout'
    cli.write_text('#!/bin/sh\necho unexpected-real-invocation >&2\nexit 91\n')
    cli.chmod(0o755)
    script = (repo / 'scripts/rollout_smolvla.sh').read_text().replace('/data/work/venvs/so101-smolvla-061', str(env.parent))
    entry = tmp_path / 'scripts/rollout_smolvla.sh'
    entry.write_text(script)
    policy = tmp_path / 'policy'
    policy.mkdir()
    (policy / 'config.json').write_text(json.dumps({'type': 'smolvla', 'chunk_size': 50, 'input_features': {k: {'shape': [3, 480, 640]} for k in ['observation.images.camera1', 'observation.images.camera2']}}))
    for name in ['model.safetensors', 'policy_preprocessor.json', 'policy_postprocessor.json']:
        (policy / name).write_text('fake')
    def run(**updates):
        environ = {**os.environ, 'DRY_RUN': '1', 'SO101_CONFIG_DIR': str(tmp_path / 'config'), 'TE': '0', **updates}
        return subprocess.run(['bash', str(entry), 'eval-smolvla-unit-test-fresh', '1', str(policy)], env=environ, capture_output=True, text=True)
    return run


def test_dry_run_preserves_training_mapping_and_instruction(launcher):
    result = launcher(TASK='Put the red cube into the paper bowl')
    assert result.returncode == 0, result.stderr
    assert '--inference.type=so101_async' in result.stdout
    assert 'so101_rollout.smolvla.rollout' in result.stdout
    assert '--inference.prefetch=10' in result.stdout
    assert '--policy.n_action_steps=50' in result.stdout
    assert 'observation.images.wrist' in result.stdout and 'observation.images.camera1' in result.stdout
    assert 'observation.images.side' in result.stdout and 'observation.images.camera2' in result.stdout
    assert 'red' in result.stdout and '--dataset.num_episodes=1' in result.stdout


@pytest.mark.parametrize('updates', [{'TASK': 'pick blue'}, {'N_ACTION_STEPS': '51'}, {'TE': '1'},
                                    {'PREFETCH_STEPS': '50'}, {'PREFETCH_STEPS': '0'},
                                    {'N_ACTION_STEPS': '5', 'PREFETCH_STEPS': '10'}])
def test_rejects_wrong_instruction_or_action_schedule(launcher, updates):
    result = launcher(**updates)
    assert result.returncode == 2
    assert 'unexpected-real-invocation' not in result.stderr


def test_optional_recording_is_explicit_and_existing_output_is_rejected(launcher,tmp_path):
    fresh=str(tmp_path/'request-recording')
    result=launcher(INFERENCE_RECORDING_PATH=fresh)
    assert result.returncode==0
    assert f'--inference.recording_path={fresh}' in result.stdout
    assert '--inference.recording_path' not in launcher().stdout
    (tmp_path/'request-recording').mkdir()
    result=launcher(INFERENCE_RECORDING_PATH=fresh)
    assert result.returncode!=0 and 'Recording path already exists' in result.stderr
