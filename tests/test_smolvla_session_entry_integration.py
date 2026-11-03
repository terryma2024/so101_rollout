"""Real collect.py exec/venv/main/parser, with hardware boundaries denied."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest


REPO = Path(__file__).resolve().parents[1]
VENV = Path('/data/work/venvs/so101-smolvla-061')

# Installed into both the initial python3 and exec'd venv. The profile hook waits
# for the actual module main; neither runpy nor a replacement parser drives it.
HOOK = r'''
import atexit, builtins, json, os, pathlib, signal, subprocess, sys, tempfile
if os.environ.get('SMOLVLA_ENTRY_TEST'):
    root = pathlib.Path(os.environ['SMOLVLA_ENTRY_TEST'])
    mode = os.environ['SMOLVLA_ENTRY_MODE']
    def record(event, **data):
        with (root/'boundary.jsonl').open('a') as f:
            f.write(json.dumps(dict(event=event, **data))+'\n')
    # Last-resort protection against accidental real camera/serial opens.
    def audit(event, args):
        if event == 'open' and args and isinstance(args[0], (str, bytes)):
            p = os.fsdecode(args[0])
            if p.startswith(('/dev/video', '/dev/tty', '/dev/serial')):
                raise AssertionError('Forbidden hardware open: '+p)
    sys.addaudithook(audit)
    def enter(frame, event, arg):
        if event != 'call' or frame.f_code.co_name != 'main' or not frame.f_code.co_filename.endswith('/smolvla/persistent_session.py'):
            return
        sys.setprofile(None)
        import torch
        from lerobot.rollout import context
        record('main', prefix=sys.prefix, executable=sys.executable, torch=torch.__version__, module=frame.f_globals['__name__'])
        def forbidden(*args, **kwargs):
            raise AssertionError('Real robot/teleoperator factory invoked')
        context.make_robot_from_config = forbidden
        context.make_teleoperator_from_config = forbidden
        context.build_rollout_context = forbidden
        context._load_pretrained_policy = forbidden
        context.make_pre_post_processors = forbidden
        old_engine = context.create_inference_engine
        old_signals = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)}
        def restored():
            record('cleanup', engine_restored=context.create_inference_engine is old_engine,
                   factories_restored=context._load_pretrained_policy is forbidden and context.make_pre_post_processors is forbidden,
                   signals_restored=all(signal.getsignal(sig) == old for sig, old in old_signals.items()))
        atexit.register(restored)
        class Terminal:
            def isatty(self): return True
        sys.stdin = Terminal()
        builtins.input = lambda prompt='': ''
        original_run = subprocess.run
        def run(argv, *args, **kwargs):
            if str(argv[0]).endswith('/camera_settings.sh'):
                assert argv[1:] == ['lock']
                record('camera_lock_blocked')
                return subprocess.CompletedProcess(argv, 0)
            if 'so101_rollout.camera.preflight' in argv:
                record('preflight_blocked')
                return subprocess.CompletedProcess(argv, 0)
            # Only the actual read-only structured shell exporter is permitted.
            assert kwargs.get('env', {}).get('STRUCTURED_ARGS_PATH'), argv
            assert kwargs['env']['DRY_RUN'] == '0'
            return original_run(argv, *args, **kwargs)
        subprocess.run = run
        original_mkdtemp = tempfile.mkdtemp
        def mkdtemp(suffix=None, prefix=None, dir=None):
            return original_mkdtemp(suffix=suffix, prefix=prefix, dir=str(root))
        tempfile.mkdtemp = mkdtemp
        plan = json.loads((root/'plan.json').read_text())
        seen = []
        def fake_native(cfg, cache, shutdown):
            trial = plan['trials'][len(seen)]
            assert sys.prefix == '/data/work/venvs/so101-smolvla-061'
            assert cfg.task == cfg.dataset.single_task == trial['env']['TASK']
            assert str(cfg.policy.pretrained_path) == plan['model']
            assert str(cfg.dataset.root) == trial['launch_dataset_path']
            assert cfg.inference.recording_path == trial['recording_path']
            assert cfg.return_to_initial_position is True
            assert cfg.fps == cfg.dataset.fps == 20
            assert cfg.policy.n_action_steps == 50 and cfg.inference.prefetch == 10
            assert cfg.robot.max_relative_target == 30
            assert cfg.dataset.num_episodes == 1 and not cfg.resume and not cfg.use_torch_compile
            assert cfg.inference.telemetry_path.startswith(str(root))
            record('native_boundary', id=trial['id'], task=cfg.task, return_to_initial_position=cfg.return_to_initial_position)
            seen.append(trial['id'])
            if mode == 'abort':
                raise RuntimeError('Operator requested stop (Esc); fake hardware boundary')
            if mode == 'shutdown':
                shutdown.set()
                raise RuntimeError('Session interrupted; no next case')
            p = pathlib.Path(trial['recording_path']); p.mkdir(parents=True)
            (p/'status.json').write_text(json.dumps(dict(complete=True)))
            p = pathlib.Path(trial['dataset_path'])/'meta'; p.mkdir(parents=True)
            (p/'info.json').write_text(json.dumps(dict(total_episodes=1)))
        frame.f_globals['run_native_case'] = fake_native
    sys.setprofile(enter)
'''


@pytest.mark.parametrize('mode', ['complete', 'invariant', 'abort', 'shutdown'])
def test_generated_execute_reaches_real_main_and_native_parser_without_hardware(tmp_path, mode):
    assert (VENV/'bin/python').is_file(), 'The deployment venv is required for this integration test'
    package = tmp_path/'package'
    subprocess.run([sys.executable, str(REPO/'tools/prepare_smolvla_baseline_collection.py'),
                    '--output', str(package), '--suite', 'other-positions',
                    '--session', 'entry-test-'+uuid.uuid4().hex], check=True, capture_output=True, text=True)
    path = package/'plan.json'
    plan = json.loads(path.read_text())
    assert len(plan['trials']) == 16
    for trial in plan['trials']:
        trial['launch_dataset_path'] = trial['dataset_path']
        trial['dataset_path'] = str(package/'fake-datasets'/str(trial['id']))
    if mode == 'invariant':
        plan['trials'][0]['env']['MAX_REL'] = '29'
    path.write_text(json.dumps(plan, indent=2))
    hooks = tmp_path/'hooks'; hooks.mkdir()
    (hooks/'sitecustomize.py').write_text(HOOK)
    env = dict(os.environ, SMOLVLA_ENTRY_TEST=str(package), SMOLVLA_ENTRY_MODE=mode,
               PYTHONPATH=str(hooks)+os.pathsep+os.environ.get('PYTHONPATH', ''))
    result = subprocess.run(['python3', str(package/'collect.py'), '--execute'],
                            env=env, cwd=REPO, capture_output=True, text=True, timeout=180)
    events = [json.loads(line) for line in (package/'boundary.jsonl').read_text().splitlines()]
    main = events[0]
    assert main['event'] == 'main' and main['module'] == '__main__'
    assert main['prefix'] == str(VENV) and main['executable'] == str(VENV/'bin/python')
    assert main['torch']
    cleanup = events.pop()
    assert cleanup == dict(event='cleanup', engine_restored=True, factories_restored=True, signals_restored=True)
    natives = [e for e in events if e['event'] == 'native_boundary']
    receipts = sorted(package.glob('trial-*-execution.json'))
    if mode == 'complete':
        assert result.returncode == 0, result.stdout+result.stderr
        assert [e['id'] for e in natives] == list(range(1, 17))
        assert len(receipts) == 16
        assert all(json.loads(p.read_text())['complete'] for p in receipts)
        assert len([e for e in events if e['event'] == 'camera_lock_blocked']) == 16
        assert len([e for e in events if e['event'] == 'preflight_blocked']) == 16
    else:
        assert result.returncode != 0, result.stdout+result.stderr
        assert len(receipts) == 1
        receipt = json.loads(receipts[0].read_text())
        assert receipt['complete'] is False
        assert receipt['aborted'] is (mode in {'abort', 'shutdown'})
        if mode == 'invariant':
            assert not natives
            assert len(events) == 1, 'Invalid cfg must stop before camera lock/preflight'
            assert 'Session requires validated' in result.stderr
        else:
            assert len(natives) == 1
        assert not (package/'trial-02-execution.json').exists()
    # Only package-local fake artifacts may be created by this test.
    assert all(not Path(t['launch_dataset_path']).exists() for t in plan['trials'])
