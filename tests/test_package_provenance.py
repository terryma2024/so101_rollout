"""Check installed imports away from checkout cwd without loading runtime SDKs."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[1]

# Also used verbatim for readback with the real and voice interpreters. All
# expected paths come from the caller, never from the observed installation.
PROVENANCE_PROBE = r'''
import importlib
import importlib.metadata
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse
import zipfile

expected_python, expected_package, mode, expected_source, *expected_hash = sys.argv[1:]
assert sys.executable == expected_python, ('interpreter mismatch', sys.executable, expected_python)
package = Path(expected_package).resolve()
assert not package.is_relative_to(Path.cwd().resolve()), 'probe cwd contains expected package'
origins = {name: str(Path(importlib.import_module(name).__file__).resolve())
           for name in ('so101_rollout.config', 'so101_rollout.voice.voice_intent',
                        'so101_rollout.voice.voice_runner')}
dist = importlib.metadata.distribution('so101-rollout')
direct_url = json.loads(dist.read_text('direct_url.json') or '{}')
files = sorted(str(path) for path in dist.files or [])
for name, origin in origins.items():
    expected = package.joinpath(*name.split('.')[1:]).with_suffix('.py')
    assert Path(origin) == expected, ('module origin mismatch', name, origin, str(expected))
source = Path(unquote(urlparse(direct_url.get('url', '')).path)).resolve()
if mode == 'editable':
    assert direct_url.get('dir_info', {}).get('editable') is True, 'installation is not editable'
    assert source == Path(expected_source).resolve(), ('editable source mismatch', str(source), expected_source)
elif mode == 'wheel':
    assert not direct_url.get('dir_info', {}).get('editable'), 'runtime installation is editable'
    assert source == Path(expected_source).resolve(), ('wheel source mismatch', str(source), expected_source)
    assert expected_hash and hashlib.sha256(source.read_bytes()).hexdigest() == expected_hash[0], 'wheel SHA256 mismatch'
    recorded_hash = direct_url.get('archive_info', {}).get('hashes', {}).get('sha256')
    if recorded_hash is not None:
        assert recorded_hash == expected_hash[0], 'installed metadata wheel SHA256 mismatch'
    groups = {
        'voice': ('voice_agent', 'voice_runner', 'voice_policy', 'voice_intent',
                  'voice_llm_intent', 'voice_verify', 'voice_asr', 'voice_fake_robot', 'voice_latency_check'),
        'camera': ('calib_capture', 'calib_intrinsics', 'calib_extrinsics', 'calib_targets', 'align_side'),
        'operations': ('record_viz', 'teleop_viz', 'check_bus', 'read_pose'),
    }
    required = {'so101_rollout/config.py'} | {
        f'so101_rollout/{group}/{name}.py' for group, names in groups.items() for name in names}
    assert required <= set(files), ('wheel is missing application files', sorted(required - set(files)))
    assert all(Path(dist.locate_file(path)).is_file() for path in required), 'installed wheel files missing'
    # uv may omit archive hashes for local wheels. Compare actual installed
    # package bytes with the independently hashed wheel, including every group.
    with zipfile.ZipFile(source) as archive:
        package_files = {path for path in archive.namelist()
                         if path.startswith('so101_rollout/') and not path.endswith('/')}
        assert required <= package_files, 'wheel archive is missing application files'
        for path in package_files:
            assert Path(dist.locate_file(path)).read_bytes() == archive.read(path), ('installed wheel bytes mismatch', path)
else:
    raise AssertionError('unknown installation mode: ' + mode)
print(json.dumps({'python': sys.executable, 'origins': origins,
                  'direct_url': direct_url, 'files': files, 'cwd': str(Path.cwd())}))
'''


def installed_probe(cwd, *, python=None, package=None, source=None):
    env = {key: value for key, value in os.environ.items()
           if key not in ('PYTHONPATH', 'AMENT_PREFIX_PATH', 'COLCON_PREFIX_PATH')}
    return subprocess.run(
        [sys.executable, '-P', '-c', PROVENANCE_PROBE,
         python or sys.executable, str(package or REPO / 'src' / 'so101_rollout'),
         'editable', str(source or REPO)],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=15)


def test_installed_package_origin_outside_cwd(tmp_path):
    result = installed_probe(tmp_path)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed['cwd'] == str(tmp_path)
    assert observed['origins']['so101_rollout.config'] == str(REPO / 'src/so101_rollout/config.py')


@pytest.mark.parametrize('boundary,expected_message', [
    ('python', 'interpreter mismatch'),
    ('package', 'module origin mismatch'),
    ('source', 'editable source mismatch'),
])
def test_provenance_rejects_wrong_installation(tmp_path, boundary, expected_message):
    result = installed_probe(tmp_path, **{boundary: str(tmp_path.parent / 'wrong installation')})
    assert result.returncode != 0, f'provenance accepted wrong {boundary}'
    assert expected_message in result.stderr, result.stderr
