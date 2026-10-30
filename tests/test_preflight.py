"""Offline camera preflight contracts; never opens hardware."""
import json
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]


def api():
    from so101_rollout.camera import preflight
    return preflight


def inputs():
    p = api()
    cfg, ref = p.load_config(REPO / 'config/preflight.json')
    return p, cfg, ref


def test_module_exists():
    assert (REPO / 'src/so101_rollout/camera/preflight.py').exists()


@pytest.mark.parametrize('delta', [0, 3])
def test_reference_and_small_light_change_pass(delta):
    p, cfg, ref = inputs()
    frame = np.clip(ref.astype(int) + delta, 0, 255).astype(np.uint8)
    assert p.evaluate([frame] * 4, [np.full_like(ref, 140)] * 4, ref, cfg)['passed']


@pytest.mark.parametrize('kind', ['bright', 'flicker', 'black', 'white', 'translate', 'rotate', 'blank', 'wrong_size', 'nan'])
def test_bad_images_fail(kind):
    p, cfg, ref = inputs()
    frame = ref.copy()
    if kind == 'bright': frame = np.clip(frame.astype(int) + 30, 0, 255).astype(np.uint8)
    if kind in ('black', 'white', 'blank'): frame[:] = {'black': 0, 'white': 255, 'blank': 130}[kind]
    if kind == 'translate': frame = cv2.warpAffine(frame, np.float32([[1, 0, 9], [0, 1, 0]]), (640, 480))
    if kind == 'rotate':
        frame = cv2.warpAffine(frame, cv2.getRotationMatrix2D((320, 240), 3.5, 1), (640, 480))
    if kind == 'wrong_size': frame = frame[:400]
    if kind == 'nan': frame = frame.astype(float); frame[0, 0] = np.nan
    frames = [frame] * 4
    if kind == 'flicker': frames = [ref, np.clip(ref.astype(int) + 12, 0, 255).astype(np.uint8)]
    assert not p.evaluate(frames, [np.full_like(ref, 140)] * 4, ref, cfg)['passed']


@pytest.mark.parametrize('kind', ['missing', 'corrupt', 'hash', 'size'])
@pytest.mark.parametrize('reference_name', ['alignment_reference', 'lighting_reference'])
def test_bad_reference_rejected(tmp_path, kind, reference_name):
    import hashlib
    import shutil
    p, cfg, ref = inputs()
    shutil.copytree(REPO/'config',tmp_path/'config')
    path = tmp_path/'config/preflight.json'
    cfg = json.loads(path.read_text())
    target = path.parent/cfg[reference_name]['path']
    if kind == 'missing': target.unlink()
    if kind == 'corrupt':
        target.write_text('not png')
        cfg[reference_name]['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    if kind in ('hash', 'size'):
        changed = ref.copy(); changed[0, 0] = 0
        cv2.imwrite(str(target), changed if kind == 'hash' else ref[:100])
        if kind == 'size': cfg[reference_name]['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    path.write_text(json.dumps(cfg))
    with pytest.raises((ValueError, OSError)): p.load_config(path)


def test_capture_releases_on_read_failure():
    p, cfg, _ = inputs()
    class Camera:
        released = False
        def isOpened(self): return True
        def set(self, *args): return True
        def read(self): return False, None
        def release(self): self.released = True
    camera = Camera()
    with pytest.raises(RuntimeError): p.capture('fake', 20, cfg, factory=lambda *args: camera)
    assert camera.released


def test_help_does_not_open_camera():
    result = subprocess.run([sys.executable, '-m', 'so101_rollout.camera.preflight', '--help'], capture_output=True, text=True)
    assert result.returncode == 0
    assert '--config' in result.stdout


def test_cli_corrupt_config_saves_failure(tmp_path):
    p = api()
    config = tmp_path/'bad.json'
    config.write_text('{broken')
    evidence = tmp_path/'evidence'
    assert p.main(['--config',str(config),'--evidence-dir',str(evidence)]) == 1
    result = json.loads((evidence/'result.json').read_text())
    assert not result['passed'] and result['reasons']


@pytest.mark.parametrize('level', [0, 255])
def test_wrist_black_white_fail(level):
    p,cfg,ref = inputs()
    assert not p.evaluate([ref]*2,[np.full_like(ref,level)]*2,ref,cfg)['passed']


def test_color_highlight_is_not_grayscale_overexposure():
    p,cfg,ref = inputs()
    wrist = np.full_like(ref,140)
    wrist[:,:,2] = 255
    assert p.evaluate([ref]*2,[wrist]*2,ref,cfg)['passed']


def test_capture_deadline_releases(monkeypatch):
    p,cfg,_ = inputs()
    class Camera:
        released = False
        def isOpened(self): return True
        def set(self,*args): pass
        def release(self): self.released=True
    cam=Camera()
    ticks=iter([0,20])
    monkeypatch.setattr(p.time,'monotonic',lambda:next(ticks))
    with pytest.raises(TimeoutError): p.capture('fake',20,cfg,factory=lambda *args:cam)
    assert cam.released


def test_run_camera_checks_has_bounded_signal_timeout(monkeypatch):
    import signal
    p,cfg,_=inputs()
    before=signal.getsignal(signal.SIGALRM)
    def blocked_read(*args, **kwargs):
        signal.raise_signal(signal.SIGALRM)
    monkeypatch.setattr(p,'capture',blocked_read)
    with pytest.raises(TimeoutError): p.run_camera_checks(cfg)
    assert signal.getsignal(signal.SIGALRM) == before
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0


def test_capture_fourcc_only_side():
    p,cfg,ref=inputs()
    cfg['capture'].update(warmup_seconds=0,frames=1,interval_seconds=0)
    class Camera:
        def __init__(self): self.settings=[]; self.released=False
        def isOpened(self): return True
        def set(self,*args): self.settings.append(args)
        def read(self): return True,ref
        def release(self): self.released=True
    for mjpg in [False,True]:
        cam=Camera()
        p.capture('fake',20,cfg,factory=lambda *args:cam,mjpg=mjpg)
        assert any(k==cv2.CAP_PROP_FOURCC for k,v in cam.settings) == mjpg
        assert cam.released


def test_cli_does_not_overwrite_existing_evidence(tmp_path, monkeypatch):
    p=api(); evidence=tmp_path/'evidence';evidence.mkdir()
    monkeypatch.setattr(p,'capture',lambda *a,**k: (_ for _ in ()).throw(AssertionError('camera must not open')))
    target=evidence/'result.json';target.write_text('preserve me')
    assert p.main(['--evidence-dir',str(evidence)]) == 1
    assert target.read_text() == 'preserve me'


def test_cli_default_config_uses_cwd_not_install_location(tmp_path, monkeypatch):
    p=api()
    import shutil
    shutil.copytree(REPO/'config',tmp_path/'config')
    monkeypatch.chdir(tmp_path)
    # Simulate wheel installed far from the checkout.
    monkeypatch.setattr(p,'__file__','/some/site-packages/so101_rollout/camera/preflight.py')
    calls=[]
    def capture(config):
        calls.append(config)
        raise RuntimeError('mock camera')
    monkeypatch.setattr(p,'run_camera_checks',capture)
    assert p.main(['--evidence-dir',str(tmp_path/'evidence')]) == 1
    assert len(calls)==1
    result=json.loads((tmp_path/'evidence/result.json').read_text())
    assert result['config_path']==str(tmp_path/'config/preflight.json')


def test_real_failed_preflight_matches_original_alignment():
    p, cfg, ref = inputs()
    frame = cv2.imread(str(REPO/'tests/fixtures/preflight/side-g7QyMYXO-39.png'))
    result = p.evaluate([frame]*7, [np.full_like(ref,140)]*7, ref, cfg)
    assert result['passed'], result
    assert result['alignment']['passed']


def test_upper_cloth_change_does_not_control_geometry():
    p,cfg,ref=inputs()
    frame=cv2.imread(str(REPO/'tests/fixtures/preflight/side-g7QyMYXO-39.png'))
    changed=frame.copy()
    # Rearrange upper cloth without changing its light ROI mean or overexposure.
    changed[20:160,10:390]=frame[20:160,10:390][::-1,::-1]
    result=p.evaluate([changed]*7,[np.full_like(ref,140)]*7,ref,cfg)
    assert result['passed'],result
    assert result['alignment']['passed']


@pytest.mark.parametrize('measurement,passed', [
    ((5.999,-5.999,2.499,1.2,20),True),
    ((6,0,0,1,20),False),((0,-6,0,1,20),False),((0,0,2.5,1,20),False),
    ((0,0,0,1,9),False),((0,0,0,float('nan'),20),False),
    ((float('nan'),0,0,1,20),False),(None,False),
])
def test_shared_alignment_boundaries_and_invalid_series(monkeypatch,measurement,passed):
    from so101_rollout.camera import align_side
    p,cfg,ref=inputs()
    calls=[]
    def median(kp,des,frames):
        calls.append(len(frames))
        return measurement
    monkeypatch.setattr(align_side,'estimate_median',median)
    result=p.evaluate([ref]*12,[np.full_like(ref,140)]*2,ref,cfg)
    assert result['passed'] == passed,result
    assert calls == [7]
    # JSON evidence must remain serializable when a matcher returns invalid data.
    json.dumps(result,allow_nan=False)


@pytest.mark.parametrize('reference_name', ['alignment_reference','lighting_reference'])
def test_each_reference_is_validated_before_capture(tmp_path,monkeypatch,reference_name):
    import shutil
    p,cfg,ref=inputs()
    shutil.copytree(REPO/'config',tmp_path/'config')
    config=tmp_path/'config/preflight.json'
    raw=json.loads(config.read_text())
    (config.parent/raw[reference_name]['path']).write_bytes(b'corrupted')
    def forbidden_capture(*args):
        pytest.fail('invalid reference must fail before camera access')
    monkeypatch.setattr(p,'run_camera_checks',forbidden_capture)
    assert p.main(['--config',str(config),'--evidence-dir',str(tmp_path/'evidence')]) == 1


def test_cli_reports_alignment_and_references_once(tmp_path,monkeypatch,capsys):
    p,cfg,ref=inputs()
    frame=cv2.imread(str(REPO/'tests/fixtures/preflight/side-g7QyMYXO-39.png'))
    monkeypatch.setattr(p,'run_camera_checks',lambda cfg:([frame]*7,[np.full_like(ref,140)]*7))
    evidence=tmp_path/'evidence'
    assert p.main(['--config',str(REPO/'config/preflight.json'),'--evidence-dir',str(evidence)]) == 0
    output=capsys.readouterr().out
    assert output.count('检查证据目录:') == 1
    assert '旋转' in output and '内点' in output and 'PASS' in output
    result=json.loads((evidence/'result.json').read_text())
    assert result['alignment']['reference']==cfg['alignment_reference']
    assert result['lighting_reference']==cfg['lighting_reference']
    assert result['alignment']['reference']['sha256'] != result['lighting_reference']['sha256']
    from PIL import Image
    with Image.open(evidence/'comparison.jpg') as im:
        assert max(im.size)<=1600
