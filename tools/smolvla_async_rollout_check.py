#!/usr/bin/env python3
"""Exercise the *real rollout backend* on recordings, with no hardware access.

This measures inference/CPU action availability, excluding cameras, serial,
visualization, image recording, and physical motion. It is not a success test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

from tools.smolvla_smoke import CAMERA_MAP, TASKS, latency_stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--green-dataset', type=Path, required=True)
    parser.add_argument('--red-dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ticks-per-color', type=int, default=400)
    args = parser.parse_args()
    if args.output.exists() or args.ticks_per_color < 120:
        parser.error('Require fresh output and >=120 ticks per color')
    args.output.mkdir(parents=True)
    import numpy as np
    import torch
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.policies import make_pre_post_processors
    from lerobot.rollout.context import _load_pretrained_policy
    from so101_rollout.smolvla.rollout import SO101AsyncConfig, create_async_engine

    torch.set_num_threads(4)
    torch.manual_seed(1000)
    cfg = PreTrainedConfig.from_pretrained(args.policy, local_files_only=True)
    cfg.pretrained_path = args.policy
    cfg.device = 'cuda'
    policy = _load_pretrained_policy(cfg).cuda().eval()
    pre, post = make_pre_post_processors(
        policy_cfg=cfg, pretrained_path=str(args.policy),
        preprocessor_overrides={'device_processor': {'device': 'cuda'},
                                'rename_observations_processor': {'rename_map': CAMERA_MAP}})
    observations, sources = {}, []
    for color in TASKS:
        root = getattr(args, f'{color}_dataset')
        info = json.loads((root / 'meta/info.json').read_text())
        for key in CAMERA_MAP:
            if info['features'][key]['shape'] != [480, 640, 3]:
                raise ValueError(f'Check source dimensions before decoding: {key}')
        dataset = LeRobotDataset('local/' + root.name, root=root, download_videos=False, video_backend='pyav')
        observations[color] = []
        for frame in range(0, 400, 25):
            item = dataset[frame]
            obs = {'observation.state': item['observation.state'].numpy().copy()}
            for key in CAMERA_MAP:
                obs[key] = item[key].permute(1, 2, 0).contiguous().numpy().copy()
            observations[color].append(obs)
            sources.append(dict(color=color, dataset=str(root), frame=frame))
        del dataset
    engine = create_async_engine(
        SO101AsyncConfig(prefetch=10, telemetry_path=str(args.output / 'telemetry.json')),
        policy=policy, preprocessor=pre, postprocessor=post,
        dataset_features=info['features'], ordered_action_keys=info['features']['action']['names'],
        task=TASKS['green'], device='cuda', robot_wrapper=SimpleNamespace(robot_type='so101_follower'),
        fps=20, use_torch_compile=False)
    phases = {}
    engine.start()

    def wait_for_action(color):
        start = time.perf_counter()
        while True:
            action = engine.get_action(observations[color][0])
            if action is not None:
                assert tuple(action.shape) == (6,) and torch.isfinite(action).all()
                return time.perf_counter() - start
            if time.perf_counter() - start > 30:
                raise RuntimeError('Initial chunk timeout')
            time.sleep(0.05)

    try:
        for color in TASKS:
            engine.reset(task=TASKS[color])
            engine.resume()
            startup = wait_for_action(color)
            epoch = time.perf_counter()
            calls, sent_times, actions, missed = [], [epoch], [], 0
            for tick in range(1, args.ticks_per_color):
                time.sleep(max(0, epoch + tick * 0.05 - time.perf_counter()))
                begin = time.perf_counter()
                action = engine.get_action(observations[color][tick % len(observations[color])])
                end = time.perf_counter()
                calls.append((end - begin) * 1000)
                if action is None:
                    missed += 1
                else:
                    assert tuple(action.shape) == (6,) and torch.isfinite(action).all()
                    sent_times.append(end)
                    actions.append(action.numpy())
            engine.pause()
            np.save(args.output / f'{color}-actions.npy', np.array(actions))
            phases[color] = dict(task=TASKS[color], ticks=args.ticks_per_color,
                                 actions_available=len(sent_times), starved_ticks=missed,
                                 first_chunk_wait_s=startup,
                                 observed_hz=(len(sent_times) - 1) / (sent_times[-1] - sent_times[0]),
                                 control_call=latency_stats(calls),
                                 successful_action_intervals=latency_stats([(b-a)*1000 for a,b in zip(sent_times,sent_times[1:])]))
        # Force a task reset with a real request still pending. A fresh green
        # request must be required before any action from the new generation.
        engine.reset(task=TASKS['red'])
        engine.resume()
        while engine._future is not None:
            engine.get_action(None)
            time.sleep(0.01)
        assert engine.get_action(observations['red'][0]) is None
        deadline = time.perf_counter() + 10
        while not engine._future.running():
            assert time.perf_counter() < deadline and not engine.result_ready
            time.sleep(0.001)
        old_id = engine._request.identifier
        engine.pause()
        engine.reset(task=TASKS['green'])
        engine.resume()
        deadline = time.perf_counter() + 10
        while not engine.result_ready:
            assert time.perf_counter() < deadline
            time.sleep(0.01)
        assert engine.get_action(None) is None
        before = engine.stats['actions']
        wait_for_action('green')
        assert engine.stats['actions'] == before + 1
        barrier = dict(passed=True, worker_started_before_reset=True, invalidated_request_id=old_id,
                       new_generation=engine.generation, stale_results=engine.stats['stale_results'])
    finally:
        engine.stop()
    report = dict(passed=all(v['starved_ticks'] == 0 for v in phases.values()),
                  hardware_access=False, recorded_observations_only=True,
                  checkpoint=str(args.policy),
                  model_sha256=hashlib.sha256((args.policy / 'model.safetensors').read_bytes()).hexdigest(),
                  backend='so101_async', fps=20, prefetch=10, horizon=cfg.n_action_steps,
                  task_reset_barrier=barrier, phases=phases, stats=engine.stats, sources=sources,
                  limits='No camera acquisition, serial send, visualization, dataset writes, physical motion or grasp success measured.')
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
