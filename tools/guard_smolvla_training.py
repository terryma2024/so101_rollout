"""CPU-only fail-closed preflight for the reviewed SmolVLA training bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check_tree(root, expected):
    root = Path(root)
    actual = {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if actual != set(expected):
        raise RuntimeError(f'File membership changed in {root}')
    for rel, record in expected.items():
        if (root / rel).stat().st_size != record['size'] or digest(root / rel) != record['sha256']:
            raise RuntimeError(f'File content changed: {root / rel}')


def check_split_approval(config_path, approved, smoke):
    from tools.train_smolvla import checked_training_split
    split = checked_training_split(config_path, approved['datasets']['train']['root'],
                                   approved['datasets']['validation']['root'])
    if not split.get('legacy_v1'):
        if split['manifest_sha256'] != approved['split_manifest_sha256']:
            raise RuntimeError('Configured split manifest is not the transferred approved split')
        if split['manifest_sha256'] != smoke.get('split_manifest_sha256'):
            raise RuntimeError('Local smoke used a different split manifest')
        for label, counts in split['splits'].items():
            if any(approved['datasets'][label][key] != value for key, value in counts.items()):
                raise RuntimeError('Transferred dataset counts differ from configured split')
    return split


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence', type=Path, required=True)
    a = p.parse_args()
    e = a.evidence
    cfg = json.loads((e / 'config.json').read_text())
    for name in ('environment_approved.json', 'model_approved.json', 'local_smoke_approved.json'):
        if json.loads((e / name).read_text()).get('passed') is not True:
            raise RuntimeError(f'Approval missing: {name}')
    smoke = json.loads((e / 'local_smoke_approved.json').read_text())
    if smoke['batch_size'] != cfg['batch_size'] or smoke['steps'] < 100:
        raise RuntimeError('Formal batch was not exercised by the approved local smoke')
    if digest(e / 'source/tools/train_smolvla.py') != smoke['adapter_sha256']:
        raise RuntimeError('Training adapter differs from the locally tested code')
    data = e.parent / 'data/transfer-approved.json'
    approved = json.loads(data.read_text())
    if not approved.get('passed') or not approved.get('transfer', {}).get('passed'):
        raise RuntimeError('Remote dataset transfer approval missing')
    manifest_path = Path(approved['files_manifest'])
    if digest(manifest_path) != approved['files_manifest_sha256']:
        raise RuntimeError('Dataset manifest changed')
    manifests = json.loads(manifest_path.read_text())
    for name, dataset in approved['datasets'].items():
        check_tree(dataset['root'], manifests[name])
    if cfg['dataset']['root'] != approved['datasets']['train']['root']:
        raise RuntimeError('Configured train root is not approved')
    check_split_approval(e / 'config.json', approved, smoke)
    stats = Path(cfg['dataset']['root']) / 'meta/stats.json'
    if digest(stats) != approved['normalization']['stats_sha256']:
        raise RuntimeError('Train-only normalization statistics changed')
    if smoke['train_stats_sha256'] != digest(stats):
        raise RuntimeError('Local smoke used different normalization statistics')
    model = json.loads((e / 'model_approved.json').read_text())
    if (digest(e / 'model-files.json') != model['model_manifest_sha256']
            or digest(e / 'source-files.json') != model['source_manifest_sha256']):
        raise RuntimeError('Model/source manifest changed after approval')
    for entry in json.loads((e / 'model-files.json').read_text()).values():
        check_tree(entry['root'], entry['files'])
    for rel, expected in json.loads((e / 'source-files.json').read_text()).items():
        if digest(e / rel) != expected:
            raise RuntimeError(f'Frozen source changed: {rel}')
    environment = json.loads((e / 'environment_approved.json').read_text())
    freeze = subprocess.run(['/home/lenovo/.local/bin/uv', 'pip', 'freeze', '--python',
                             '/data/work/venvs/so101-smolvla-061/bin/python'],
                            capture_output=True, check=True).stdout
    if hashlib.sha256(freeze).hexdigest() != environment['freeze_sha256']:
        raise RuntimeError('Installed versions changed after approval')
    if cfg['steps'] != 20000 or cfg['save_freq'] != 5000 or cfg['eval_steps'] != 5000 or cfg['max_eval_samples'] != 0:
        raise RuntimeError('Formal budget/evaluation contract changed')
    if Path(cfg['output_dir']).exists():
        raise RuntimeError('Formal output already exists; fresh training required')
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            cmd = (proc / 'cmdline').read_bytes().decode(errors='replace').split('\0')
        except (OSError, ProcessLookupError):
            continue
        if (any(s.endswith('/lerobot-train') for s in cmd)
                or 'lerobot.scripts.lerobot_train' in cmd or 'tools.train_smolvla' in cmd
                or any(s.endswith('/train_smolvla.py') for s in cmd)):
            raise RuntimeError(f'Another trainer is active: pid={proc.name}')
    print(json.dumps({'passed': True, 'data': str(data), 'output': cfg['output_dir']}))


if __name__ == '__main__':
    main()
