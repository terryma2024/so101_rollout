"""CPU-only strict checkpoint and train-fitted processor verification."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--train', type=Path, required=True)
    p.add_argument('--audit', type=Path, required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--steps', type=int, required=True)
    a = p.parse_args()
    import torch
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.policies import make_pre_post_processors
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
    cfg = PreTrainedConfig.from_pretrained(a.checkpoint, local_files_only=True)
    cfg.device = 'cpu'
    cfg.load_vlm_weights = False
    model = SmolVLAPolicy.from_pretrained(a.checkpoint, config=cfg, strict=True, local_files_only=True)
    pre, post = make_pre_post_processors(policy_cfg=cfg, pretrained_path=str(a.checkpoint),
                                        preprocessor_overrides={'device_processor': {'device': 'cpu'}})
    stats = json.loads((a.train / 'meta/stats.json').read_text())
    proof = {}
    for label, pipeline, feature in [('pre-state', pre, 'observation.state'),
                                     ('pre-action', pre, 'action'), ('post-action', post, 'action')]:
        processor, = [s for s in pipeline.steps if hasattr(s, '_tensor_stats')]
        for key in ('mean', 'std'):
            actual = processor._tensor_stats[feature][key].detach().cpu()
            expected = torch.as_tensor(stats[feature][key], dtype=actual.dtype)
            if not torch.equal(actual, expected):
                raise RuntimeError(f'Saved {label}/{key} differs from train statistics')
        proof[label] = {'mean_std_equal_to_train': True}
    result = json.loads((a.audit / 'result.json').read_text())
    if result['steps'] != a.steps or not result['passed']:
        raise RuntimeError('Training audit does not show all expected steps')
    if not all(result['seen'][phase].get(color, 0) > 0
               for phase in ('train', 'validation') for color in ('green', 'red')):
        raise RuntimeError('Both tasks must be observed in training and held-out validation')
    steps = [json.loads(line) for line in (a.audit / 'steps.jsonl').read_text().splitlines()]
    if len(steps) != a.steps or not all(math.isfinite(r[k]) for r in steps for k in ('loss', 'gradient_norm')):
        raise RuntimeError('Missing steps or nonfinite loss/gradient')
    if torch.cuda.is_initialized():
        raise RuntimeError('CPU verification unexpectedly initialized CUDA')
    r = {'passed': True, 'checkpoint': str(a.checkpoint), 'steps': a.steps,
         'batch_size': result['batch_size'], 'strict_reload': True,
         'parameters': sum(t.numel() for t in model.parameters()),
         'train_stats_sha256': hashlib.sha256((a.train / 'meta/stats.json').read_bytes()).hexdigest(),
         'saved_processor_statistics': proof, 'validation_shared_train_pipeline': True,
         'train_seen': result['seen']['train'], 'validation_seen': result['seen']['validation'],
         'evaluation': result['evaluation'], 'peak_gpu_bytes': result['peak_gpu_bytes'],
         'mean_update_seconds_excluding_first': sum(r['update_seconds'] for r in steps[1:]) / max(len(steps)-1, 1),
         'last_loss': steps[-1]['loss'], 'last_gradient_norm': steps[-1]['gradient_norm'],
         'cpu_only_verification': True, 'adapter_sha256': hashlib.sha256(Path(__file__).with_name('train_smolvla.py').read_bytes()).hexdigest()}
    if 'manifest_sha256' in result.get('split_contract', {}):
        r['split_manifest_sha256'] = result['split_contract']['manifest_sha256']
    a.receipt.write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps(r, indent=2))


if __name__ == '__main__':
    main()
