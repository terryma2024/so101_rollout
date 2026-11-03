"""Finite collection must reject unsafe resumes before hardware can start."""
import json
from pathlib import Path
import subprocess
import sys
import os
import runpy
import uuid

REPO = Path(__file__).resolve().parents[1]


def test_generated_launcher_preserves_venv_for_torch(tmp_path, monkeypatch):
    package = tmp_path / 'package'
    subprocess.run([sys.executable, str(REPO / 'tools/prepare_smolvla_baseline_collection.py'),
                    '--output', str(package), '--suite', 'other-positions',
                    '--session', 'test-'+uuid.uuid4().hex], check=True)
    captured = []
    monkeypatch.setattr(os, 'execve', lambda *args: captured.append(args))
    runpy.run_path(str(package / 'collect.py'), run_name='__main__')
    executable, argv, env = captured[0]
    # Exercise CPython's real argv[0]/venv discovery, without invoking rollout.
    probe = 'import sys,torch,json; print(json.dumps([sys.prefix,torch.__version__]))'
    result = subprocess.run([argv[0], '-c', probe], executable=executable,
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0] == '/data/work/venvs/so101-smolvla-061'


def test_real_native_parser_accepts_all_case_configs(tmp_path):
    package = tmp_path / 'package'
    subprocess.run([sys.executable, str(REPO / 'tools/prepare_smolvla_baseline_collection.py'),
                    '--output', str(package), '--suite', 'other-positions',
                    '--session', 'test-'+uuid.uuid4().hex], check=True)
    code = '''
import json, sys
from so101_rollout.smolvla.persistent_session import parse_case_config, structured_args
plan=json.load(open(sys.argv[1]))
for trial in plan['trials']:
    cfg=parse_case_config(structured_args(trial, plan['repo']))
    assert cfg.task == trial['env']['TASK'] == cfg.dataset.single_task
    assert str(cfg.dataset.root) == trial['dataset_path']
    assert cfg.fps == 20 and cfg.policy.n_action_steps == 50
    assert cfg.inference.prefetch == 10 and cfg.dataset.num_episodes == 1
print('PARSED_16_WITHOUT_HARDWARE')
'''
    env = dict(os.environ, PYTHONPATH=str(REPO / 'src'),
               HF_HOME='/data/models/huggingface', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    result = subprocess.run(['/data/work/venvs/so101-smolvla-061/bin/python', '-c', code,
                             str(package / 'plan.json')], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'PARSED_16_WITHOUT_HARDWARE' in result.stdout


def test_other_positions_dry_run_keeps_hardware_unstarted(tmp_path):
    package = tmp_path / 'package'
    made = subprocess.run([sys.executable, str(REPO / 'tools/prepare_smolvla_baseline_collection.py'), '--output', str(package), '--suite', 'other-positions', '--session', 'test-'+uuid.uuid4().hex], capture_output=True, text=True)
    assert made.returncode == 0, made.stderr
    plan = json.loads((package / 'plan.json').read_text())
    assert len(plan['trials']) == 16
    assert len({t['dataset'] for t in plan['trials']}) == 16
    assert {t['layout'] for t in plan['trials']} == {'G B1/R B2','G B2/R B1','G D3/R D4','G D4/R D3'}
    dry = subprocess.run([sys.executable, str(package / 'collect.py')], capture_output=True, text=True)
    assert dry.returncode == 0
    assert dry.stdout.count('DRY_RUN=1') == 16
    assert not (package / 'terminal-logs').exists()
