"""Finite operator-paced native rollouts with process-local model reuse.

No robot is accessed unless --execute is present. Factory bindings are restored
on exit; each case owns the complete native strategy/context lifecycle.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from threading import Thread


class ModelCache:
    def __init__(self):
        self.loaded = None
        self.pipelines = None
        self.policy_key = None
        self.processor_key = None
        self.timings = []

    def policy(self, loader, cfg):
        key = repr(vars(cfg))
        if self.loaded is not None and key != self.policy_key:
            raise ValueError('Policy configuration changed inside session')
        started = time.perf_counter()
        if self.loaded is None:
            self.loaded = loader(cfg)
            self.policy_key = key
            loaded = True
        else:
            loaded = False
        self.timings.append(dict(stage='policy', loaded=loaded, seconds=time.perf_counter()-started))
        return self.loaded

    def processors(self, factory, **kwargs):
        # Fresh empty datasets have no statistics; checkpoint processors provide
        # normalization. Refuse divergent runtime overrides instead of silently
        # reusing pipelines configured for another device or rename map.
        key = repr({k: vars(v) if k == 'policy_cfg' else v for k,v in kwargs.items()})
        if self.pipelines is not None and key != self.processor_key:
            raise ValueError('Processor configuration changed inside session')
        if self.pipelines is None:
            self.pipelines = factory(**kwargs)
            self.processor_key = key
        return self.pipelines

    def reset(self):
        for obj in (self.loaded, *(self.pipelines or ())):
            if obj is not None:
                obj.reset()

    @contextmanager
    def bind(self, context):
        load, make = context._load_pretrained_policy, context.make_pre_post_processors
        context._load_pretrained_policy = lambda cfg: self.policy(load, cfg)
        context.make_pre_post_processors = lambda **kw: self.processors(make, **kw)
        try:
            yield self
        finally:
            context._load_pretrained_policy, context.make_pre_post_processors = load, make


def validate_resume(trials, root, start, plan_sha256=None):
    ids = [t['id'] for t in trials]
    if ids != list(range(1, len(trials)+1)) or start not in ids:
        raise ValueError('Finite consecutive case IDs and valid --start-trial required')
    for t in trials:
        receipt = root / f"trial-{t['id']:02d}-execution.json"
        if t['id'] < start:
            if not receipt.is_file():
                raise ValueError(f'Missing previous completed receipt: {receipt}')
            data = json.loads(receipt.read_text())
            expected = dict(id=t['id'], dataset=t.get('dataset'), recording_path=t['recording_path'], complete=True)
            if any(data.get(k) != v for k,v in expected.items()) or (plan_sha256 and data.get('plan_sha256') != plan_sha256):
                raise ValueError(f'Incomplete or mismatched previous receipt: {receipt}')
            status_path = Path(t['recording_path'])/'status.json'
            info_path = Path(t['dataset_path'])/'meta/info.json'
            log_path = root/'terminal-logs'/f"trial-{t['id']:02d}.log"
            if not status_path.is_file() or not info_path.is_file() or not log_path.is_file():
                raise ValueError(f'Missing previous case artifacts: {receipt}')
            if not json.loads(status_path.read_text()).get('complete') or json.loads(info_path.read_text()).get('total_episodes') != 1:
                raise ValueError(f'Incomplete previous artifacts: {receipt}')
        else:
            for path in [receipt, Path(t['dataset_path']), Path(t['recording_path']), root/'terminal-logs'/f"trial-{t['id']:02d}.log"]:
                if path.exists():
                    raise ValueError(f'Fresh path required: {path}')


def structured_args(trial, repo):
    with tempfile.TemporaryDirectory(prefix='smolvla-config-') as directory:
        target = Path(directory)/'args.json'
        env = dict(os.environ, **trial['env'], STRUCTURED_ARGS_PATH=str(target), DRY_RUN='0')
        subprocess.run(trial['argv'], cwd=repo, env=env, check=True)
        return json.loads(target.read_text())


def parse_case_config(argv):
    """Use the native CLI parser with a concrete (not postponed) config type."""
    from lerobot.configs import parser
    from lerobot.rollout import RolloutConfig
    from lerobot.scripts import lerobot_rollout  # noqa: F401 -- config registration
    from .rollout import SO101AsyncConfig  # noqa: F401 -- async registration

    def parse_case(cfg):
        return cfg

    # LeRobot 0.6.1 uses getfullargspec, not get_type_hints. This module's
    # future annotations would otherwise pass the string 'RolloutConfig'.
    parse_case.__annotations__['cfg'] = RolloutConfig
    previous_argv = sys.argv
    try:
        sys.argv = [previous_argv[0], *argv]
        return parser.wrap()(parse_case)()
    finally:
        sys.argv = previous_argv


def stop_keyboard_listener(listener, worker=None):
    """Stop pynput Threads and LeRobot's non-Thread terminal wrapper alike."""
    if listener is None:
        return
    if worker is None:
        worker = listener if isinstance(listener, Thread) else getattr(listener, '_thread', None)
    listener.stop()
    if isinstance(worker, Thread) and worker.ident is not None:
        worker.join(timeout=3)
        if worker.is_alive():
            raise RuntimeError('Previous keyboard listener remains alive')


def run_native_case(cfg, cache, shutdown):
    from lerobot.rollout import context, create_strategy
    from lerobot.utils.visualization_utils import init_visualization, shutdown_visualization
    created = []
    original_robot, original_teleop = context.make_robot_from_config, context.make_teleoperator_from_config
    def track(factory):
        def make(config):
            obj = factory(config)
            created.append(obj)
            return obj
        return make
    context.make_robot_from_config = track(original_robot)
    context.make_teleoperator_from_config = track(original_teleop)
    ctx = None
    strategy = create_strategy(cfg.strategy)
    try:
        if cfg.display_data:
            init_visualization(cfg.display_mode, session_name='rollout', ip=cfg.display_ip, port=cfg.display_port)
        ctx = context.build_rollout_context(cfg, shutdown)
        strategy.setup(ctx)
        strategy.run(ctx)
    finally:
        try:
            if ctx is not None:
                listener = getattr(strategy, '_listener', None)
                listener_worker = listener if isinstance(listener, Thread) else getattr(listener, '_thread', None)
                try:
                    strategy.teardown(ctx)
                finally:
                    # Dataset.finalize or listener errors must not skip worker
                    # barrier. Never reuse a model with a live prior worker.
                    engine = ctx.policy.inference
                    try:
                        if engine._thread is not None and engine._thread.is_alive():
                            engine.stop()
                        if engine._thread is not None and engine._thread.is_alive():
                            raise RuntimeError('Previous inference worker remains alive')
                    finally:
                        stop_keyboard_listener(listener, listener_worker)
        finally:
            context.make_robot_from_config, context.make_teleoperator_from_config = original_robot, original_teleop
            cleanup_errors = []
            for obj in reversed(created):
                try:
                    if obj.is_connected:
                        obj.disconnect()
                except BaseException as exc:
                    cleanup_errors.append(exc)
            try:
                if cfg.display_data:
                    shutdown_visualization(cfg.display_mode)
            except BaseException as exc:
                cleanup_errors.append(exc)
            if cleanup_errors:
                raise RuntimeError('Case device/visualization cleanup failed; session stopped') from cleanup_errors[0]
    if (getattr(strategy, '_events', None) or {}).get('stop_recording'):
        raise RuntimeError('Operator requested stop (Esc); session ended with current artifacts preserved')
    if shutdown.is_set():
        raise RuntimeError('Session interrupted; no next case')
    future = ctx.policy.inference._future
    if future is not None and future.done() and not future.cancelled() and future.exception() is not None:
        raise RuntimeError('Final in-flight inference failed; no next case') from future.exception()
    if ctx.policy.inference.failed:
        raise RuntimeError('Inference failed; no next case')
    if ctx.data.dataset.num_episodes != 1:
        raise RuntimeError('Expected exactly one saved episode; no next case')
    cache.reset()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--start-trial', type=int, default=1)
    args = p.parse_args()
    root = args.plan.resolve().parent
    plan = json.loads(args.plan.read_text())
    plan_sha256 = hashlib.sha256(args.plan.read_bytes()).hexdigest()
    validate_resume(plan['trials'], root, args.start_trial, plan_sha256)
    if not args.execute:
        for trial in plan['trials'][args.start_trial-1:]:
            print(f"# {trial['id']:02d}: {trial['layout']} / {trial['color']}\nDRY_RUN=1 {trial['command']}")
        return
    if not sys.stdin.isatty():
        p.error('Execute requires local foreground operator terminal')
    for path, expected in plan['sha256'].items():
        if hashlib.file_digest(open(path, 'rb'), 'sha256').hexdigest() != expected:
            raise ValueError('Frozen input changed: '+path)
    import torch
    from lerobot.rollout import context
    # Register robot, camera and async configs without invoking official CLI.
    from lerobot.scripts import lerobot_rollout  # noqa: F401
    from lerobot.utils.process import ProcessSignalHandler
    from .rollout import create_async_engine
    from lerobot.utils.utils import init_logging
    init_logging()
    torch.set_num_threads(4)
    cache = ModelCache()
    old_engine = context.create_inference_engine
    context.create_inference_engine = create_async_engine
    old_signals = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT)}
    handler = ProcessSignalHandler(use_threads=True)
    try:
        with cache.bind(context):
            for trial in plan['trials'][args.start_trial-1:]:
                print(f"Case {trial['id']:02d}: {trial['layout']}; {trial['color']}. Restore approved initial pose, gripper, cubes and bowl. Previous worker and devices are stopped.", flush=True)
                answer = input('Ready, local keyboard stop verified? Enter to run, q to end: ')
                if answer.strip().lower() == 'q':
                    break
                if answer.strip() or handler.shutdown_event.is_set():
                    raise RuntimeError('Stopped without starting case')
                started = time.time()
                log_path = root/'terminal-logs'/f"trial-{trial['id']:02d}.log"
                log_path.parent.mkdir(exist_ok=True)
                log = log_path.open('x')
                file_handler = logging.StreamHandler(log)
                file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
                logging.getLogger().addHandler(file_handler)
                receipt = dict(id=trial['id'], dataset=trial['dataset'], recording_path=trial['recording_path'], plan_sha256=plan_sha256, terminal_log=str(log_path), complete=False, started_at=started)
                try:
                    argv = structured_args(trial, plan['repo'])
                    cfg = parse_case_config(argv)
                    if not (cfg.fps == cfg.dataset.fps == 20 and cfg.policy.n_action_steps == 50 and cfg.inference.prefetch == 10 and cfg.robot.max_relative_target == 30 and cfg.dataset.num_episodes == 1 and cfg.return_to_initial_position and not cfg.resume and not cfg.use_torch_compile):
                        raise ValueError('Session requires validated hard20Hz/horizon50/prefetch10/MAX_REL30, fresh single episode and return to initial position')
                    if cfg.task != trial['env']['TASK'] or cfg.dataset.single_task != cfg.task:
                        raise ValueError('Case task mismatch')
                    # Shell check happens before native build can connect robot.
                    evidence = Path(tempfile.mkdtemp(prefix=f"smolvla-session-{trial['id']:02d}-", dir='/data/work/so101-evidence/real-robot'))
                    env = dict(os.environ, **trial['env'])
                    subprocess.run([str(Path(plan['repo'])/'camera_settings.sh'), 'lock'], env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
                    subprocess.run(['timeout','--signal=TERM','--kill-after=2s','30s','/data/work/venvs/so101-real-lerobot-061/bin/python','-m','so101_rollout.camera.preflight','--config',str(Path(trial['env']['SO101_CONFIG_DIR'])/'preflight.json'),'--evidence-dir',str(evidence)], env=env, check=True, stdout=log, stderr=subprocess.STDOUT)
                    cfg.inference.telemetry_path = str(evidence/'async-telemetry.json')
                    receipt['preflight_path'] = str(evidence)
                    run_native_case(cfg, cache, handler.shutdown_event)
                    status = json.loads((Path(trial['recording_path'])/'status.json').read_text())
                    if not status.get('complete'):
                        raise RuntimeError('Incomplete diagnostics; no next case')
                    receipt.update(complete=True, recording=status)
                except BaseException as exc:
                    logging.exception('Case failed; stopping session')
                    receipt['error'] = str(exc)
                    receipt['aborted'] = 'Operator requested stop' in str(exc) or handler.shutdown_event.is_set()
                    raise
                finally:
                    logging.getLogger().removeHandler(file_handler)
                    file_handler.close()
                    log.close()
                    receipt.update(ended_at=time.time(), model_timings=cache.timings)
                    with (root/f"trial-{trial['id']:02d}-execution.json").open('x') as f:
                        json.dump(receipt, f, indent=2)
                print('Case complete and devices disconnected. Fill results.csv; next case waits for Enter.', flush=True)
    finally:
        context.create_inference_engine = old_engine
        for sig, old in old_signals.items():
            signal.signal(sig, old)

if __name__ == '__main__':
    main()
