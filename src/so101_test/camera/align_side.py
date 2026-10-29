"""侧面相机对准：把实时画面和参考画面（采集时的视角）比较，打印偏差像素，帮你把相机调回原位。只用摄像头，不碰机械臂。

  python align_side.py [参考图]          实时对比，rerun 里看叠加图（红 = 参考，青 = 实时），Ctrl+C 结束
  python align_side.py [参考图] --once   只算一次（也可用来比较两张图：--image 某张图）

偏差用 ORB 特征 + RANSAC 估计，只用桌面和放置纸区域（床上的布会被挪动，不用），平移 < 6 px、旋转 < 2.5° 算对准。
参考图默认是正式采集第 41-61 条首帧的中值图。
"""
import os
import pathlib
import sys
import time

import cv2
import numpy as np

from .calib_capture import Preview, open_cam

DEFAULT_REF = '/data/work/so101-evidence/real-robot/pilot-check-20261027/full/side-ref-ep41-61.png'
# 和训练参考图比（绝对位置）：2026-10-28 用户要求放宽。单帧旋转估计本身会跳 ±0.5°，0.3° 手调不到。
TOL_PX, TOL_DEG = 6.0, 2.5
# 和本次录制开始时的画面比（录制中被碰到）：7 帧中值的噪声约 ±0.2°
DRIFT_PX, DRIFT_DEG = 3.0, 0.8
# 只用桌面和放置纸区域（图像第 170 行以下）的特征：上半部分是床上的布，会被挪动，2026-10-28 它让估计在
# 同一相机位置下跳 ±1.5°。桌子和纸相对机械臂不动，这才是策略关心的相机位置。
ROI_Y0 = 170
orb = cv2.ORB_create(3000)
bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)


def gray(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(2.0, (8, 8)).apply(g)          # evens out the day/evening light


def features(img):
    mask = np.zeros(img.shape[:2], np.uint8)
    mask[ROI_Y0:, :] = 255
    return orb.detectAndCompute(gray(img), mask)


def estimate_median(ref_kp, ref_des, imgs):
    """Median of estimate() over several frames (single-frame estimates jitter by a few tenths of a degree)."""
    rs = [r for r in (estimate(ref_kp, ref_des, im) for im in imgs) if r is not None]
    if not rs:
        return None
    a = np.array(rs, dtype=float)
    med = np.median(a, axis=0)
    return (float(med[0]), float(med[1]), float(med[2]), float(med[3]), int(med[4]))


def estimate(ref_kp, ref_des, img):
    """Returns (dx, dy, rot_deg, scale, inliers) of img relative to the reference, or None."""
    kp, des = features(img)
    if des is None:
        return None
    m = bf.match(ref_des, des)
    if len(m) < 20:
        return None
    a = np.float32([ref_kp[x.queryIdx].pt for x in m])
    b = np.float32([kp[x.trainIdx].pt for x in m])
    M, inl = cv2.estimateAffinePartial2D(a, b, method=cv2.RANSAC, ransacReprojThreshold=2.0)
    if M is None:
        return None
    centre = np.array([320.0, 240.0])
    moved = M[:, :2] @ centre + M[:, 2] - centre            # shift of the image centre
    return (float(moved[0]), float(moved[1]), float(np.degrees(np.arctan2(M[1, 0], M[0, 0]))),
            float(np.hypot(M[0, 0], M[1, 0])), int(inl.sum()))


def within(r, tol_px=TOL_PX, tol_deg=TOL_DEG):
    return r is not None and abs(r[0]) < tol_px and abs(r[1]) < tol_px and abs(r[2]) < tol_deg


def report(r, tol_px=TOL_PX, tol_deg=TOL_DEG):
    if r is None:
        return '匹配点太少，算不出偏差（画面是否被挡住、太暗？）'
    dx, dy, rot, s, n = r
    ok = within(r, tol_px, tol_deg)
    hint = []
    if abs(dx) >= tol_px:
        # content moves right when the lens turns left, so turn the lens toward the side the content went
        hint.append(f'画面内容偏{"右" if dx > 0 else "左"} {abs(dx):.1f} px（镜头朝画面{"右" if dx > 0 else "左"}边转一点）')
    if abs(dy) >= tol_px:
        hint.append(f'画面内容偏{"下" if dy > 0 else "上"} {abs(dy):.1f} px（镜头{"往下压" if dy > 0 else "往上抬"}一点）')
    if abs(rot) >= tol_deg:
        hint.append(f'画面旋转 {rot:+.2f}°')
    return (f'平移 ({dx:+.1f}, {dy:+.1f}) px  旋转 {rot:+.2f}°  缩放 {s:.3f}  内点 {n}  '
            + ('已对准' if ok else '；'.join(hint)))


def main():
    argv = sys.argv[1:]
    if '--image' in argv:
        k = argv.index('--image')
        argv = argv[:k] + argv[k + 2:]
    args = [a for a in argv if not a.startswith('--')]
    ref_path = args[0] if args else DEFAULT_REF
    ref = cv2.imread(ref_path)
    if ref is None:
        sys.exit(f'读不到参考图 {ref_path}')
    ref_kp, ref_des = features(ref)
    if '--image' in sys.argv:
        img = cv2.imread(sys.argv[sys.argv.index('--image') + 1])
        print(report(estimate(ref_kp, ref_des, img)))
        return
    cap = open_cam('side')
    preview = None if '--once' in sys.argv else Preview('align-side')
    last = 0.0
    recent = []  # last 7 estimates: print their median, single frames jitter by ±0.5°
    try:
        while True:
            ok, img = cap.read()
            if not ok:
                continue
            if time.time() - last < 0.5 and preview is not None:
                continue
            last = time.time()
            r = estimate(ref_kp, ref_des, img)
            if r is not None:
                recent = (recent + [r])[-7:]
                med = np.median(np.array(recent, dtype=float), axis=0)
                r = (float(med[0]), float(med[1]), float(med[2]), float(med[3]), int(med[4]))
            print(report(r) + f'  （近 {len(recent)} 帧中值）', flush=True)
            if preview is None:
                break
            view = np.zeros_like(img)
            view[..., 2] = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
            view[..., 0] = view[..., 1] = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            preview.show(view)
    except KeyboardInterrupt:
        print('\n已停止')
    cap.release()


if __name__ == '__main__':
    main()
