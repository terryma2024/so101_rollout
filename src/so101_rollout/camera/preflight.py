"""Fail-closed camera-only recording checks. No robot or servo imports."""
import argparse
import hashlib
import json
import math
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import time

import cv2
import numpy as np
from PIL import Image


def load_config(path):
    path = Path(path)
    cfg = json.loads(path.read_text())
    # Reject malformed numeric configuration, including JSON NaN, before opening devices.
    def finite(value):
        if isinstance(value, dict):
            for v in value.values(): finite(v)
        elif isinstance(value, list):
            for v in value: finite(v)
        elif isinstance(value, (int, float)) and not math.isfinite(value):
            raise ValueError('配置包含非有限数值')
    finite(cfg)
    if cfg['size'] != [640, 480]: raise ValueError('基准尺寸必须为640x480')
    required = {'capture': ('warmup_seconds', 'frames', 'interval_seconds', 'deadline_seconds'),
                'alignment': ('min_inliers',),
                'side_light': ('max_reference_delta', 'max_overexposed_fraction', 'max_range'),
                'wrist_light': ('min_mean', 'max_mean', 'max_overexposed_fraction', 'max_range')}
    for section, keys in required.items():
        for key in keys:
            val = cfg[section][key]
            if isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0:
                raise ValueError(f'无效阈值 {section}.{key}')
    if not 1 <= cfg['capture']['frames'] <= 100 or cfg['capture']['frames'] != int(cfg['capture']['frames']):
        raise ValueError('无效帧数')
    if not 0 < cfg['capture']['deadline_seconds'] <= 15: raise ValueError('无效超时')
    references = {}
    for name in ('alignment_reference', 'lighting_reference'):
        refpath = path.parent / cfg[name]['path']
        if hashlib.sha256(refpath.read_bytes()).hexdigest() != cfg[name]['sha256']:
            raise ValueError(f'{name}基准校验和不匹配')
        with Image.open(refpath) as im:
            if list(im.size) != cfg['size']: raise ValueError(f'{name}基准尺寸错误')
        ref = cv2.imread(str(refpath))
        if ref is None: raise ValueError(f'{name}基准无法解码')
        references[name] = ref
    if cfg['alignment']['min_inliers'] < 10:
        raise ValueError('匹配质量阈值必须至少10个内点')
    cfg['_alignment_reference_path'] = str((path.parent / cfg['alignment_reference']['path']).resolve())
    return cfg, references['lighting_reference']


def masks():
    bg = np.zeros((480, 640), np.uint8)
    bg[20:200, 10:390] = 255
    paper = np.zeros_like(bg)
    cv2.fillPoly(paper, [np.array([[245,225],[395,214],[497,411],[272,450]])], 255)
    cv2.rectangle(paper, (291,230), (440,303), 0, -1)
    cv2.ellipse(paper, (380,356), (90,80), 0, 0, 360, 0, -1)
    return {'background': bg, 'paper': paper}


def evaluate(side_frames, wrist_frames, reference, cfg):
    """Pure offline evaluation; malformed/empty/nonfinite images always fail."""
    result = {'passed': False, 'reasons': [], 'regions': {}}
    try:
        for frames in (side_frames, wrist_frames, [reference]):
            if not len(frames): raise ValueError('空序列')
            for frame in frames:
                if frame is None or frame.shape != (480,640,3) or frame.dtype != np.uint8 or not np.isfinite(frame).all():
                    raise ValueError('图像为空、尺寸/类型错误或包含NaN')
        # Import only during evaluation: align_side's preview/config imports must not affect --help.
        from . import align_side
        alignment_reference = cv2.imread(cfg['_alignment_reference_path'])
        if alignment_reference is None or alignment_reference.shape != (480,640,3):
            raise ValueError('位置基准无法解码或尺寸错误')
        ref_kp, ref_des = align_side.features(alignment_reference)
        measurement = None if ref_des is None else align_side.estimate_median(ref_kp, ref_des, side_frames[-7:])
        valid = measurement is not None and len(measurement) == 5 and np.isfinite(measurement).all()
        if not valid: measurement = None
        quality = valid and measurement[4] >= cfg['alignment']['min_inliers']
        aligned = bool(quality and align_side.within(measurement))
        alignment = {'passed': aligned, 'algorithm': 'camera.align_side ORB+CLAHE/RANSAC estimate_median',
                     'reference': cfg['alignment_reference'], 'roi_y0': align_side.ROI_Y0,
                     'frames': min(7,len(side_frames)),
                     'thresholds': {'abs_dx_lt_px': align_side.TOL_PX, 'abs_dy_lt_px': align_side.TOL_PX,
                                    'abs_rotation_lt_degrees': align_side.TOL_DEG,
                                    'min_median_inliers': cfg['alignment']['min_inliers']},
                     'report': align_side.report(measurement), 'quality_passed': bool(quality)}
        if measurement is not None:
            alignment.update(zip(('dx_px','dy_px','rotation_degrees','scale','inliers'), measurement))
        result['alignment'] = alignment
        result['lighting_reference'] = cfg['lighting_reference']
        if not aligned:
            result['reasons'].append('侧面位置未通过: ' + alignment['report'] +
                                     (f"；匹配质量不足（中值内点至少{cfg['alignment']['min_inliers']}）" if not quality else ''))
        refgray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
        side = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in side_frames]
        wrist = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in wrist_frames]
        for name, mask in masks().items():
            light = [g[mask > 0] for g in side]
            delta = max(abs(float(g.mean()) - float(refgray[mask > 0].mean())) for g in light)
            over = max(float((g >= 250).mean()) for g in light)
            result['regions'][name] = {'brightness_delta': delta, 'overexposed_fraction': over}
            if delta > cfg['side_light']['max_reference_delta'] or over > cfg['side_light']['max_overexposed_fraction']:
                result['reasons'].append(f'{name}光照偏差或灰度过曝')
        for name, frames, limit in [('side',side,cfg['side_light']), ('wrist',wrist,cfg['wrist_light'])]:
            means = [float(g.mean()) for g in frames]
            span = max(means)-min(means)
            result[name] = {'mean_min': min(means), 'mean_max': max(means), 'range': span, 'overexposed_fraction': max(float((g>=250).mean()) for g in frames)}
            if span > limit['max_range']: result['reasons'].append(f'{name}短序列亮度波动过大')
            if name == 'wrist' and (min(means) < limit['min_mean'] or max(means) > limit['max_mean'] or result[name]['overexposed_fraction'] > limit['max_overexposed_fraction']):
                result['reasons'].append('腕部亮度或灰度过曝异常')
        result['passed'] = not result['reasons']
    except Exception as exc:
        result['reasons'].append(f'评估异常: {type(exc).__name__}: {exc}')
    return result


def capture(device, fps, cfg, factory=cv2.VideoCapture, *, mjpg=False):
    settings = cfg['capture']
    start = time.monotonic()
    camera = factory(device, cv2.CAP_V4L2)
    try:
        if not camera.isOpened(): raise RuntimeError(f'相机无法打开: {device}')
        if mjpg: camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        camera.set(cv2.CAP_PROP_FPS, fps)
        frames = []
        while len(frames) < settings['frames']:
            if time.monotonic()-start > settings['deadline_seconds']: raise TimeoutError(f'相机读取超时: {device}')
            ok, frame = camera.read()
            if not ok or frame is None: raise RuntimeError(f'相机空帧: {device}')
            if time.monotonic()-start >= settings['warmup_seconds']: frames.append(frame)
            time.sleep(settings['interval_seconds'])
        return frames
    finally:
        camera.release()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def run_camera_checks(cfg):
    def timed_out(signum, frame):
        raise TimeoutError('相机检查达到总超时')
    previous_alarm = signal.signal(signal.SIGALRM, timed_out)
    previous_term = signal.signal(signal.SIGTERM, timed_out)
    signal.setitimer(signal.ITIMER_REAL, 27)
    try:
        side = capture(os.environ.get('SIDE_CAM', '/dev/v4l/by-id/usb-icSpring_icspring_camera_202404160005-video-index0'), float(os.environ.get('SIDE_CAM_FPS',30)), cfg, mjpg=True)
        wrist = capture(os.environ.get('WRIST_CAM', '/dev/v4l/by-id/usb-icSpring_icspring_camera-video-index0'), float(os.environ.get('WRIST_CAM_FPS',20)), cfg)
        return side, wrist
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_alarm)
        signal.signal(signal.SIGTERM, previous_term)


def main(argv=None):
    parser = argparse.ArgumentParser(description='采集前光照与侧面位置检查（只访问相机）')
    parser.add_argument('--config', type=Path, default=Path(os.environ.get('SO101_CONFIG_DIR', Path.cwd()/'config'))/'preflight.json')
    parser.add_argument('--evidence-dir', type=Path, help='本次证据目录（省略则创建唯一目录）')
    args = parser.parse_args(argv)
    evidence = args.evidence_dir
    if evidence is not None and evidence.exists() and (not evidence.is_dir() or any(evidence.iterdir())):
        print(f'采集前检查未通过：证据目录非空，拒绝覆盖: {evidence}', flush=True)
        return 1
    result = {'passed': False, 'reasons': []}
    try:
        # Evidence must exist even when the configuration is broken.
        if evidence is None:
            root = Path('/data/work/so101-evidence/real-robot')
            root.mkdir(parents=True, exist_ok=True)
            evidence = Path(tempfile.mkdtemp(prefix='record-preflight-', dir=root))
        else: evidence.mkdir(parents=True, exist_ok=True)
        print(f'检查证据目录: {evidence}', flush=True)
        cfg, reference = load_config(args.config)
        side, wrist = run_camera_checks(cfg)
        for name, frames in [('side',side),('wrist',wrist)]:
            for index in sorted({0,len(frames)-1}):
                if not cv2.imwrite(str(evidence/f'{name}-{index}.png'),frames[index]): raise OSError('证据图像保存失败')
        position_reference = cv2.imread(cfg['_alignment_reference_path'])
        preview = np.hstack([position_reference, side[-1]]).copy()
        for x, label in [(0,'Position: training reference'),(640,'Current side camera')]:
            cv2.rectangle(preview,(x,0),(x+640,28),(0,0,0),-1)
            cv2.putText(preview,label,(x+10,20),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1)
        if not cv2.imwrite(str(evidence/'comparison.jpg'),preview): raise OSError('对照预览保存失败')
        result = evaluate(side, wrist, reference, cfg)
        result['alignment_reference'] = cfg['alignment_reference']
        result['lighting_reference'] = cfg['lighting_reference']
        result['capture_counts'] = {'side': len(side), 'wrist': len(wrist)}
    except Exception as exc:
        result['reasons'].append(f'检查异常: {type(exc).__name__}: {exc}')
    result['config_path'] = str(args.config.resolve())
    result['timestamp_utc'] = datetime.now(timezone.utc).isoformat()
    try:
        if evidence is None: raise OSError('证据目录未创建')
        write_json(evidence/'result.json',result)
    except Exception as exc:
        result['passed'] = False
        result['reasons'].append(f'证据保存失败: {exc}')
    print('采集前检查' + ('通过' if result['passed'] else '未通过'), flush=True)
    if 'alignment' in result:
        limits = result['alignment']['thresholds']
        print(result['alignment']['report']
              + f"；标准 |dx|,|dy| < {limits['abs_dx_lt_px']:g} px，|旋转| < {limits['abs_rotation_lt_degrees']:g}°；中值内点 >= {limits['min_median_inliers']}"
              + ('；PASS' if result['alignment']['passed'] else '；FAIL'), flush=True)
    for reason in result['reasons']: print(f'  - {reason}', flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
