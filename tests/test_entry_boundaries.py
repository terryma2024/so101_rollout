"""Exercise public entry boundaries without loading robot or model runtimes."""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_voice_patch_targets_canonical_module(monkeypatch):
    # A root forwarding module must never receive patches intended for the implementation.
    assert importlib.util.find_spec('so101_rollout.voice') is not None, 'canonical voice package is missing'
    from so101_rollout.voice import voice_agent

    assert voice_agent is importlib.import_module('so101_rollout.voice.voice_agent')
    messages, commands, events = [], [], []
    monkeypatch.setattr(voice_agent, 'say', messages.append)

    class Runner:
        def submit(self, kind, colour=None):
            commands.append((kind, colour))

    voice_agent.handle_text(Runner(), events.append, '红', 'keyboard')
    assert commands == [('run', 'red')]
    assert messages == ["[keyboard] '红' -> red"]
    assert events == [{'event': 'input', 'source': 'keyboard', 'text': '红',
                       'intent': 'red', 'intent_source': 'rules'}]


VOICE_HELP_PROBE = r'''
import contextlib
import importlib.abc
import io
import json
import os
from pathlib import Path
import runpy
import sys

entry, repo = sys.argv[1:]
attempts = []
blocked = {'voice_policy', 'voice_fake_robot', 'voice_asr', 'lerobot', 'torch',
           'cv2', 'sounddevice', 'faster_whisper', 'feetech_servo_sdk', 'serial', 'requests'}

class DenyRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(part in blocked for part in fullname.split('.')):
            attempts.append(fullname)
            raise AssertionError('forbidden runtime import: ' + fullname)

def audit(event, args):
    if event in {'socket.connect', 'socket.bind', 'subprocess.Popen', 'os.system', 'ctypes.dlopen'}:
        attempts.append(event)
        raise AssertionError('forbidden runtime action: ' + event)
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0])
        if path.startswith(('/dev/', '/data/work/models/', '/data/work/so101-policies/', '/data/models/')) or Path(path).name in {'arms.env', 'camera.env'}:
            attempts.append(path)
            raise AssertionError('forbidden runtime read: ' + path)

sys.meta_path.insert(0, DenyRuntime())
sys.addaudithook(audit)
output = io.StringIO()
with contextlib.redirect_stdout(output):
    if entry.endswith('.py'):
        # Importing the compatibility file must not dispatch main.
        runpy.run_path(str(Path(repo) / entry), run_name='stub_import_probe')
        assert not output.getvalue(), output.getvalue()
        assert not any(name.startswith('so101_rollout.voice.') for name in sys.modules)
    sys.argv = [entry, '--help']
    try:
        if entry.endswith('.py'):
            runpy.run_path(str(Path(repo) / entry), run_name='__main__')
        else:
            # This is the same module dispatch Python uses for its -m option.
            runpy._run_module_as_main(entry)
    except SystemExit as exc:
        assert exc.code == 0, exc.code
    else:
        raise AssertionError('--help did not exit')

assert not attempts, attempts
assert not any(any(part in blocked for part in name.split('.')) for name in sys.modules)
print(json.dumps({'help': output.getvalue(), 'attempts': attempts,
                  'config': os.environ.get('SO101_CONFIG_DIR'), 'python': sys.executable}))
'''


def voice_help_probe(entry, cwd, config=None):
    env = {key: value for key, value in os.environ.items()
           if key not in ('PYTHONPATH', 'AMENT_PREFIX_PATH', 'COLCON_PREFIX_PATH',
                          'SO101_CONFIG_DIR', 'VOICE_GREEN_POLICY', 'VOICE_RED_POLICY',
                          'VOICE_LOG_DIR', 'MAX_REL')}
    if config is not None:
        env['SO101_CONFIG_DIR'] = config
    return subprocess.run([sys.executable, '-I', '-c', VOICE_HELP_PROBE, entry, str(REPO)],
                          cwd=cwd, env=env, text=True, capture_output=True, timeout=15)


@pytest.mark.parametrize('entry', ['so101_rollout.voice.voice_agent', 'voice_agent.py',
                                 'so101_rollout.voice.voice_latency_check', 'voice_latency_check.py'])
@pytest.mark.parametrize('config', [None, '', 'missing selected config'])
def test_voice_help_stays_inert(tmp_path, entry, config):
    result = voice_help_probe(entry, tmp_path, config)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert 'usage:' in payload['help'] and '--green-policy' in payload['help']
    assert payload['attempts'] == []
    assert payload['python'] == sys.executable
    expected_config = str(REPO / 'config') if config is None and entry.endswith('.py') else config
    assert payload['config'] == expected_config


def isolated_probe(code, tmp_path, *args, config=None):
    env = {key: value for key, value in os.environ.items()
           if key not in ('PYTHONPATH', 'AMENT_PREFIX_PATH', 'COLCON_PREFIX_PATH',
                          'SO101_CONFIG_DIR', 'HF_HOME', 'WRIST_CAM_FPS', 'SIDE_CHECK_EVERY')}
    if config is not None:
        env['SO101_CONFIG_DIR'] = config
    result = subprocess.run([sys.executable, '-I', '-c', code, str(REPO), *args],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


DIAGNOSTIC_IMPORT_PROBE = r'''
import importlib.abc, importlib.util, json, os, pathlib, runpy, sys
repo, name = sys.argv[1:]
attempts = []
class DenyRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'scservo_sdk', 'lerobot', 'serial', 'feetech_servo_sdk'}:
            attempts.append(fullname)
            raise AssertionError('forbidden SDK import: ' + fullname)
def audit(event, args):
    if event in {'socket.connect', 'subprocess.Popen', 'ctypes.dlopen'}:
        attempts.append(event)
        raise AssertionError(event)
    if event == 'open' and isinstance(args[0], (str, bytes)):
        p = os.fsdecode(args[0])
        if p.startswith('/dev/') or pathlib.Path(p).name in {'arms.env', 'camera.env'} or '/calibration/' in p:
            attempts.append(p)
            raise AssertionError('forbidden config/cache/device read')
sys.meta_path.insert(0, DenyRuntime())
sys.addaudithook(audit)
# Before migration load the actual legacy file to expose its eager SDK boundary.
try:
    if importlib.util.find_spec('so101_rollout.operations') is None:
        runpy.run_path(str(pathlib.Path(repo) / (name + '.py')), run_name='legacy_diagnostic_probe')
    else:
        __import__('so101_rollout.operations.' + name)
        runpy.run_path(str(pathlib.Path(repo) / (name + '.py')), run_name='root_diagnostic_probe')
except AssertionError:
    pass
print(json.dumps(attempts))
'''


@pytest.mark.parametrize('name', ['check_bus', 'read_pose'])
def test_diagnostic_import_is_inert(tmp_path, name):
    # Moving SDK/config/device work back to module scope must fail this consumer assertion.
    assert isolated_probe(DIAGNOSTIC_IMPORT_PROBE, tmp_path, name,
                          config=str(tmp_path / 'missing config')) == []


DIAGNOSTIC_MAIN_PROBE = r'''
import contextlib, importlib, io, json, os, pathlib, sys, types
repo, name, arguments = sys.argv[1:]
args = json.loads(arguments)
events = []
config = pathlib.Path.cwd() / 'selected config'
config.mkdir()
(config / 'arms.env').write_text('LEADER_PORT=leader-port\nFOLLOWER_PORT=follower-port\nLEADER_ID=leader-identity\nFOLLOWER_ID=follower-identity\n')
os.environ['SO101_CONFIG_DIR'] = str(config)
os.environ['FOLLOWER_PORT'] = 'overridden-follower-port'
def module(name):
    value = types.ModuleType(name)
    value.__path__ = []
    sys.modules[name] = value
    return value
if name == 'check_bus':
    sdk = module('scservo_sdk')
    sdk.COMM_SUCCESS = 0
    class Port:
        def __init__(self, port): events.append(['port', port])
        def openPort(self): events.append(['open'])
        def setBaudRate(self, rate): events.append(['baud', rate])
        def closePort(self): events.append(['close'])
    class Packet:
        def __init__(self, protocol): events.append(['packet', protocol])
        def read2ByteTxRx(self, port, ident, address):
            events.append(['read', ident, address])
            return 0, (1 if ident == 3 else 0), 0
    sdk.PortHandler, sdk.PacketHandler = Port, Packet
else:
    module('lerobot')
    motors = module('lerobot.motors')
    feetech = module('lerobot.motors.feetech')
    class Calibration:
        def __init__(self, **kwargs): self.data = kwargs
    class Motor:
        def __init__(self, ident, model, mode): self.data = [ident, model, mode]
    motors.Motor, motors.MotorCalibration = Motor, Calibration
    motors.MotorNormMode = types.SimpleNamespace(RANGE_0_100='range', DEGREES='degrees')
    class Bus:
        def __init__(self, *, port, motors, calibration):
            self.port = port
            events.append(['bus', port, {n: m.data for n, m in motors.items()},
                           {n: c.data for n, c in calibration.items()}])
        def connect(self): events.append(['connect', self.port])
        def sync_read(self, address):
            events.append(['read', self.port, address])
            return {n: i + (10 if self.port == 'overridden-follower-port' else 0)
                    for i, n in enumerate(['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper'])}
        def disconnect(self, *, disable_torque): events.append(['disconnect', self.port, disable_torque])
    feetech.FeetechMotorsBus = Bus
    cache = pathlib.Path.cwd() / 'hf-cache'
    os.environ['HF_HOME'] = str(cache)
    for group, ident, value in [('teleoperators/so_leader', 'leader-identity', 17),
                                ('robots/so_follower', 'follower-identity', 29)]:
        p = cache / 'lerobot/calibration' / group / (ident + '.json')
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'shoulder_pan': {'id': value}}))
impl = importlib.import_module('so101_rollout.operations.' + name)
assert events == [], events
sys.argv = [name + '.py', *args]
if name == 'check_bus':
    # Exactly one poll, with one failed joint, then duration expiry.
    clock = iter([0.0, 0.0, 0.5, 100.0])
    impl.time = types.SimpleNamespace(time=lambda: next(clock))
output = io.StringIO()
with contextlib.redirect_stdout(output):
    impl.main()
print(json.dumps({'events': events, 'output': output.getvalue()}))
'''


@pytest.mark.parametrize('args,arm,port,duration', [([], 'leader', 'leader-port', '30'),
    (['follower', '2'], 'follower', 'overridden-follower-port', '2'),
    (['other', '2'], 'other', 'overridden-follower-port', '2')])
def test_check_bus_main_preserves_poll_order(tmp_path, args, arm, port, duration):
    assert importlib.util.find_spec('so101_rollout.operations') is not None, 'canonical diagnostics missing'
    result = isolated_probe(DIAGNOSTIC_MAIN_PROBE, tmp_path, 'check_bus', json.dumps(args))
    assert result['events'] == [['port', port], ['packet', 0], ['open'], ['baud', 1_000_000],
                               *[['read', i, 56] for i in range(1, 7)], ['close']]
    assert f'检查 {arm}（{port}），{duration} 秒' in result['output']
    assert '共读取 1 轮' in result['output']
    assert '舵机 3: 失败 1 次' in result['output']
    assert all(f'舵机 {i}: 失败 0 次' in result['output'] for i in (1, 2, 4, 5, 6))


def test_read_pose_main_preserves_calibration_identity_and_disconnect(tmp_path):
    assert importlib.util.find_spec('so101_rollout.operations') is not None, 'canonical diagnostics missing'
    result = isolated_probe(DIAGNOSTIC_MAIN_PROBE, tmp_path, 'read_pose', '[]')
    events = result['events']
    assert [event[:2] for event in events] == [
        ['bus', 'leader-port'], ['connect', 'leader-port'], ['read', 'leader-port'], ['disconnect', 'leader-port'],
        ['bus', 'overridden-follower-port'], ['connect', 'overridden-follower-port'],
        ['read', 'overridden-follower-port'], ['disconnect', 'overridden-follower-port']]
    names = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper']
    expected = {n: [i + 1, 'sts3215', 'range' if n == 'gripper' else 'degrees'] for i, n in enumerate(names)}
    assert events[0][2:] == [expected, {'shoulder_pan': {'id': 17}}]
    assert events[4][2:] == [expected, {'shoulder_pan': {'id': 29}}]
    assert events[2][2] == events[6][2] == 'Present_Position'
    assert events[3][2] is events[7][2] is False
    lines = result['output'].splitlines()
    assert lines[0].split() == ['joint', 'leader', 'follower', 'diff']
    assert [line.split() for line in lines[1:]] == [[n, f'{i:.1f}', f'{i + 10:.1f}', '10.0'] for i, n in enumerate(names)]


ADAPTER_PROBE = r'''
import contextlib, importlib, io, json, logging, os, pathlib, runpy, sys, types
repo, name, entry = sys.argv[1:]
events = []
class Watched(types.ModuleType):
    def __setattr__(self, key, value):
        if key in {'log_visualization_data', 'apply_recording_control', 'record_loop'}:
            events.append(self.__name__.split('.')[-1] + '.' + key)
        super().__setattr__(key, value)
def module(name, watched=False):
    value = (Watched if watched else types.ModuleType)(name)
    value.__path__ = []
    sys.modules[name] = value
    return value
module('lerobot'); module('lerobot.scripts'); module('lerobot.utils'); module('lerobot.datasets')
record = module('lerobot.scripts.lerobot_record', True)
teleop = module('lerobot.scripts.lerobot_teleoperate', True)
visual = module('lerobot.utils.visualization_utils')
keyboard = module('lerobot.utils.keyboard_input', True)
dataset = module('lerobot.datasets.lerobot_dataset')
calls = []
def original_visual(*args, **kwargs): calls.append(['visual', args, kwargs]); return 'visual-result'
def original_apply(control, state): calls.append(['apply', control, state.copy()])
def original_loop(*args, **kwargs): calls.append(['loop', kwargs['events'].copy()]); return 'loop-result'
def original_save(self, *args, **kwargs): calls.append(['save']); return 'save-result'
class DatasetType(type):
    def __setattr__(self, key, value):
        if key == 'save_episode': events.append('dataset.save_episode')
        super().__setattr__(key, value)
class Dataset(metaclass=DatasetType):
    save_episode = original_save
    meta = types.SimpleNamespace(total_episodes=5)
    def has_pending_frames(self): return self.pending
visual.log_visualization_data = original_visual
record.log_visualization_data = teleop.log_visualization_data = original_visual
keyboard.apply_recording_control = original_apply
record.record_loop = original_loop
dataset.LeRobotDataset = Dataset
cv2 = module('cv2')
cv2.NORM_HAMMING = 6
cv2.ORB_create = lambda n: object()
cv2.BFMatcher = lambda *a, **k: object()
module('numpy')
import so101_rollout.config as config
config_calls = []
config.load_arms_env = lambda: config_calls.append('capture-config') or {'WRIST_CAM': 'fake-wrist', 'SIDE_CAM': 'fake-side'}
# Fail closed if unstubbed runtime imports/actions are attempted.
import importlib.abc
class DenyRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'lerobot', 'cv2', 'numpy', 'rerun', 'serial', 'scservo_sdk', 'torch'}:
            raise AssertionError('unstubbed runtime import: ' + fullname)
def audit(event, args):
    if event in {'socket.connect', 'socket.bind', 'subprocess.Popen', 'ctypes.dlopen'}:
        raise AssertionError(event)
    if event == 'open' and isinstance(args[0], (str, bytes)):
        p = os.fsdecode(args[0])
        if p.startswith(('/dev/', '/data/models/', '/data/work/models/', '/data/work/so101-policies/')) or pathlib.Path(p).name in {'arms.env', 'camera.env'}:
            raise AssertionError('real runtime read: ' + p)
sys.meta_path.insert(0, DenyRuntime()); sys.addaudithook(audit)
os.environ['WRIST_CAM_FPS'] = '20'; os.environ['SIDE_CHECK_EVERY'] = '10'
events.clear()
impl = importlib.import_module('so101_rollout.operations.' + name)
if name == 'record_viz':
    assert events == ['lerobot_record.log_visualization_data', 'keyboard_input.apply_recording_control',
                      'lerobot_record.record_loop', 'dataset.save_episode'], events
    assert impl.log_visualization_data is original_visual
    assert impl._original_apply is original_apply and impl._original_record_loop is original_loop
    assert impl._original_save_episode is original_save
    assert impl.align_side is sys.modules['so101_rollout.camera.align_side']
    assert impl.align_side.open_cam is sys.modules['so101_rollout.camera.calib_capture'].open_cam
    assert config_calls == ['capture-config'], config_calls
else:
    assert events == ['lerobot_teleoperate.log_visualization_data'], events
    assert impl.log_visualization_data is original_visual
    assert config_calls == []
installed = list(events)
main_calls = []
def external_main():
    assert events == installed, events
    target = record if name == 'record_viz' else teleop
    assert target.log_visualization_data is impl.throttled_log_visualization_data
    if name == 'record_viz':
        assert keyboard.apply_recording_control is impl.debounced_apply_recording_control
        assert record.record_loop is impl.record_loop_fresh
        assert Dataset.save_episode is impl.save_episode_nonempty
    main_calls.append(list(sys.argv))
record.main = teleop.main = external_main
root = pathlib.Path(repo) / (name + '.py')
runpy.run_path(str(root), run_name='root_import_probe')
assert main_calls == [] and events == installed
sys.argv = [name + '.py', '--argument=with spaces', '']
if entry == 'root': runpy.run_path(str(root), run_name='__main__')
else: impl.main()
assert main_calls == [[str(root) if entry == 'root' else name + '.py', '--argument=with spaces', '']], main_calls
assert events == installed
impl.time = types.SimpleNamespace(perf_counter=lambda: 0.01, monotonic=lambda: 2.0)
scalar, image = types.SimpleNamespace(ndim=1), types.SimpleNamespace(ndim=3)
with contextlib.redirect_stdout(io.StringIO()):
    if name == 'record_viz':
        assert impl.throttled_log_visualization_data('mode', observation={'joint': scalar, 'image': image}) == 'visual-result'
        assert calls[-1][2]['observation'] == {'joint': scalar}
        state = {}
        keyboard.apply_recording_control('right', state)
        keyboard.apply_recording_control('right', state)
        assert [c[0] for c in calls].count('apply') == 1
        impl.side_camera_check = lambda when: calls.append(['side', when])
        state = {'exit_early': True}
        assert record.record_loop(events=state) == 'loop-result'
        assert state['exit_early'] is False and calls[-1] == ['loop', {'exit_early': False}]
        item = Dataset(); item.pending = False
        assert item.save_episode() is None
        assert not any(c[0] == 'save' for c in calls)
        item.pending = True
        assert item.save_episode() == 'save-result'
        assert impl._session['saved'] == 1
    else:
        impl.throttled_log_visualization_data('mode', {'joint': scalar, 'image': image}, {'action': 1}, True)
        assert calls[-1][1] == ('mode', {'joint': scalar}, {'action': 1}, True)
print(json.dumps({'install_order': installed, 'main_calls': main_calls, 'config_calls': config_calls}))
'''


@pytest.mark.parametrize('name', ['record_viz', 'teleop_viz'])
@pytest.mark.parametrize('entry', ['root', 'module'])
def test_adapter_patches_precede_main_once(tmp_path, name, entry):
    assert importlib.util.find_spec('so101_rollout.operations') is not None, 'canonical adapters missing'
    result = isolated_probe(ADAPTER_PROBE, tmp_path, name, entry)
    assert len(result['main_calls']) == 1


DELEGATE_PROBE = r'''
import json, os, pathlib, runpy, sys, types
repo, group, name = sys.argv[1:]
canonical = 'so101_rollout.' + group + '.' + name
module = types.ModuleType(canonical)
def main():
    print(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'config': os.environ['SO101_CONFIG_DIR']}))
    raise SystemExit(29)
module.main = main
sys.modules[canonical] = module
root = pathlib.Path(repo) / (name + '.py')
# Importing a delegate must neither call main nor change cwd.
before = os.getcwd()
runpy.run_path(str(root), run_name='inert_stub_import')
assert os.getcwd() == before
sys.argv = [str(root), 'relative reference.png', '--image', 'relative image.png', '']
try: runpy.run_path(str(root), run_name='__main__')
except SystemExit as exc: assert exc.code == 29, exc.code
else: raise AssertionError('delegate swallowed main exit')
'''


@pytest.mark.parametrize('group,name', [('camera', name) for name in
    ('calib_capture', 'calib_intrinsics', 'calib_extrinsics', 'calib_targets', 'align_side')] +
    [('operations', name) for name in ('check_bus', 'read_pose', 'record_viz', 'teleop_viz')])
@pytest.mark.parametrize('config', [None, '', 'explicit selected config'])
def test_calibration_and_operation_delegates_preserve_argv_cwd_exit(tmp_path, group, name, config):
    assert importlib.util.find_spec('so101_rollout.' + group) is not None, 'canonical delegate target missing'
    result = isolated_probe(DELEGATE_PROBE, tmp_path, group, name, config=config)
    assert result['argv'] == ['relative reference.png', '--image', 'relative image.png', '']
    assert result['cwd'] == str(REPO if name == 'align_side' else tmp_path)
    assert result['config'] == (str(REPO / 'config') if config is None else config)


CAMERA_MAIN_PROBE = r'''
import importlib, json, sys, types
repo, name, arguments = sys.argv[1:]
sys.modules['cv2'] = types.ModuleType('cv2')
sys.modules['numpy'] = types.ModuleType('numpy')
import so101_rollout.config as config
config.load_arms_env = lambda: {'WRIST_CAM': 'fake-wrist', 'SIDE_CAM': 'fake-side'}
impl = importlib.import_module('so101_rollout.camera.' + name)
calls = []
for key in ('snap', 'aruco', 'charuco'):
    setattr(impl, key, lambda *args, key=key: calls.append([key, *args]))
sys.argv = [name + '.py', *json.loads(arguments)]
try: impl.main()
except SystemExit as exc:
    assert exc.code == impl.__doc__, exc.code
    print(json.dumps({'calls': calls, 'usage': True}))
else: print(json.dumps({'calls': calls, 'usage': False}))
'''


@pytest.mark.parametrize('name,args,calls,usage', [
    ('calib_capture', ['snap'], [['snap']], False),
    ('calib_capture', ['aruco'], [['aruco']], False),
    ('calib_capture', ['charuco', 'side'], [['charuco', 'side']], False),
    ('calib_capture', ['charuco', 'wrist'], [['charuco', 'wrist']], False),
    ('calib_capture', [], [], True), ('calib_capture', ['charuco', 'other'], [], True),
    ('calib_intrinsics', [], [], True), ('calib_intrinsics', ['other'], [], True),
    ('calib_extrinsics', [], [], True),
])
def test_camera_main_keeps_dispatch_and_usage(tmp_path, name, args, calls, usage):
    assert importlib.util.find_spec('so101_rollout.camera') is not None, 'canonical camera package missing'
    assert isolated_probe(CAMERA_MAIN_PROBE, tmp_path, name, json.dumps(args)) == {'calls': calls, 'usage': usage}


ALIGNMENT_CWD_PROBE = r'''
import contextlib, importlib, io, json, os, pathlib, runpy, sys, types
repo, entry = sys.argv[1:]
cv2 = types.ModuleType('cv2')
cv2.NORM_HAMMING = 6
cv2.ORB_create = lambda n: object()
cv2.BFMatcher = lambda *a, **k: object()
reads = []
def imread(path):
    reads.append([path, os.getcwd()])
    return path
cv2.imread = imread
sys.modules['cv2'] = cv2
sys.modules['numpy'] = types.ModuleType('numpy')
import so101_rollout.config as config
config.load_arms_env = lambda: {'WRIST_CAM': 'fake-wrist', 'SIDE_CAM': 'fake-side'}
impl = importlib.import_module('so101_rollout.camera.align_side')
impl.features = lambda image: ('reference-keypoints', 'reference-descriptors')
impl.estimate = lambda *args: 'estimated'
impl.report = lambda result: result
sys.argv = ['align_side.py', 'relative reference.png', '--image', 'relative image.png']
with contextlib.redirect_stdout(io.StringIO()):
    if entry == 'root': runpy.run_path(str(pathlib.Path(repo) / 'align_side.py'), run_name='__main__')
    else: impl.main()
print(json.dumps(reads))
'''


@pytest.mark.parametrize('entry', ['root', 'module'])
def test_alignment_stub_preserves_root_cwd(tmp_path, entry):
    result = isolated_probe(ALIGNMENT_CWD_PROBE, tmp_path, entry)
    expected_cwd = str(REPO if entry == 'root' else tmp_path)
    assert result == [['relative reference.png', expected_cwd], ['relative image.png', expected_cwd]]
