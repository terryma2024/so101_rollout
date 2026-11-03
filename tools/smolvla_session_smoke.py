"""Two real-model cases with independent async engines; never opens hardware."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

import numpy as np

from tools.smolvla_recording_check import load_records, verify_queue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path('/data/work/so101-evidence/real-robot/smolvla-12trial-counterfactual-20261102/frozen-manifest.json')
    frozen = json.loads(source.read_text())
    model = Path(frozen['model_manifest']['model_path'])
    with (model / 'model.safetensors').open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == frozen['model_manifest']['model_files_sha256']['model.safetensors']
    import torch
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies import make_pre_post_processors
    from lerobot.rollout.context import _load_pretrained_policy
    from so101_rollout.smolvla.persistent_session import ModelCache
    from so101_rollout.smolvla.async_engine import SmolVLAAsyncEngine
    from so101_rollout.smolvla.recording import restore_tree

    torch.set_num_threads(4)
    cache = ModelCache()
    loads = []
    def load(cfg):
        loads.append(time.time())
        return _load_pretrained_policy(cfg).cuda().eval()
    overrides = {
        step['registry_name']: step['config']
        for step in frozen['model_manifest']['parameters']['preprocessor']['steps']
        if step['registry_name'] in ('device_processor', 'rename_observations_processor')
    }
    rows, identities, tokens = [], [], []
    for color in ('green', 'red'):
        cell = next(c for c in frozen['cells'] if c['group'] == 'language' and c['condition'] == 'original' and color in c['task'])
        for key, node in cell['observation_schema']['items'].items():
            if 'image' in key:
                assert node['shape'] == [480, 640, 3]
        with np.load(cell['observation_file'], allow_pickle=False) as data:
            observation = restore_tree(cell['observation_schema'], data)
        cfg = PreTrainedConfig.from_pretrained(model, local_files_only=True)
        cfg.pretrained_path, cfg.device = model, 'cuda'
        started = time.perf_counter()
        policy = cache.policy(load, cfg)
        pre, post = cache.processors(make_pre_post_processors, policy_cfg=cfg,
                                    pretrained_path=str(model), preprocessor_overrides=overrides)
        cache.reset()
        torch.cuda.synchronize()
        ready_seconds = time.perf_counter() - started
        identities.append((id(policy), id(pre), id(post)))
        recording = args.output / color
        names = [f'joint_{i}' for i in range(6)]
        engine = SmolVLAAsyncEngine(policy=policy, preprocessor=pre, postprocessor=post,
            dataset_features={'action': {'names': names}}, ordered_action_keys=names,
            task=cell['task'], device='cuda',
            robot_wrapper=SimpleNamespace(robot_type=frozen['model_manifest']['parameters']['robot_type']),
            fps=20, recording_path=str(recording), telemetry_path=str(args.output / f'{color}-telemetry.json'))
        assert not engine._queue and engine._next_id == 0 and engine._model_generation is None
        engine.start()
        engine.reset(task=cell['task'])
        engine.resume()
        count = 0
        start = time.perf_counter()
        first_seconds = None
        try:
            while count < 15:
                tick = time.perf_counter()
                if tick - start > 30:
                    raise TimeoutError('Offline first-case inference timeout')
                action = engine.get_action(observation)
                if action is not None:
                    assert action.shape == (6,) and torch.isfinite(action).all()
                    count += 1
                    if first_seconds is None:
                        first_seconds = time.perf_counter() - start
                time.sleep(max(0, 0.05 - (time.perf_counter() - tick)))
        finally:
            engine.stop()
        assert not engine._thread.is_alive() and not engine._queue
        records = load_records(recording)
        requests = [m for kind, m, _ in records if kind == 'request']
        assert requests and all(m['task'] == cell['task'] for m in requests)
        assert requests[0]['request_id'] == 0 and requests[0]['request_tick'] == 0
        kind, metadata, file = next(r for r in records if r[0] == 'inference')
        with np.load(file, allow_pickle=False) as data:
            inference = restore_tree(metadata['schema'], data)
        tokens.append(inference['model_input']['observation.language.tokens'].tolist())
        queue = verify_queue(recording)
        rows.append(dict(color=color, task=cell['task'], model_and_processors_ready_s=ready_seconds,
                         first_action_after_engine_start_s=first_seconds,
                         cpu_outputs=count, queue=queue, worker_stopped=True))
        cache.reset()
        print(json.dumps(rows[-1]), flush=True)
    assert len(loads) == 1 and identities[0] == identities[1]
    assert tokens[0] != tokens[1]
    result = dict(passed=True, model_load_count=len(loads), object_identity_reused=True,
                  language_tokens_differ=True, cases=rows, cache_timings=cache.timings,
                  hardware_accessed=False,
                  limitations='Offline recorded observations only; excludes preflight, camera, serial, dataset encoding and physical reset time.')
    (args.output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS: real model loaded once; two independent case engines and records.', flush=True)


if __name__ == '__main__':
    main()
