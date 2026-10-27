"""由 ChArUco 图片计算相机内参。

  python calib_intrinsics.py wrist|side [--rational]

读 $CALIB_DIR/charuco-<cam>/*.png，输出 $CALIB_DIR/intrinsics-<cam>.json：K、畸变系数、重投影误差，以及去畸变后
等效针孔相机的视场（仿真里相机 fovy 用这个值）和一张去畸变示例图。广角的侧面相机建议加 --rational（8 参数模型）。
"""
import datetime
import json
import math
import os
import pathlib
import sys

import cv2
import numpy as np

OUT = pathlib.Path(os.environ.get('CALIB_DIR', f'/data/work/so101-evidence/real-robot/calib-{datetime.date.today():%Y%m%d}'))


def main():
    cam = sys.argv[1]
    rational = '--rational' in sys.argv
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    board = cv2.aruco.CharucoBoard((7, 5), 0.035, 0.026, d)
    det = cv2.aruco.CharucoDetector(board)
    files = sorted((OUT / f'charuco-{cam}').glob('*.png'))
    obj, img_pts, used, size = [], [], [], None
    for f in files:
        img = cv2.imread(str(f))
        size = img.shape[1::-1]
        corners, ids, _, _ = det.detectBoard(img)
        if ids is None or len(ids) < 8:
            continue
        o, p = board.matchImagePoints(corners, ids)
        obj.append(o)
        img_pts.append(p)
        used.append(f.name)
    if len(obj) < 10:
        sys.exit(f'可用图片只有 {len(obj)} 张，至少需要 10 张')
    flags = cv2.CALIB_RATIONAL_MODEL if rational else 0

    def calibrate(o, p):
        return cv2.calibrateCamera(o, p, size, None, None, flags=flags)

    rms, K, D, rvecs, tvecs = calibrate(obj, img_pts)
    per = [float(np.sqrt(np.mean(np.sum((cv2.projectPoints(o, r, t, K, D)[0] - p) ** 2, axis=2))))
           for o, p, r, t in zip(obj, img_pts, rvecs, tvecs)]
    keep = [i for i, e in enumerate(per) if e <= 3 * float(np.median(per))]
    dropped = [used[i] for i in range(len(used)) if i not in keep]
    if dropped:
        rms, K, D, rvecs, tvecs = calibrate([obj[i] for i in keep], [img_pts[i] for i in keep])
    w, h = size
    newK, _ = cv2.getOptimalNewCameraMatrix(K, D, size, alpha=0)
    fovy_raw = 2 * math.degrees(math.atan(h / 2 / K[1, 1]))
    fovx_raw = 2 * math.degrees(math.atan(w / 2 / K[0, 0]))
    fovy_undist = 2 * math.degrees(math.atan(h / 2 / newK[1, 1]))
    sample = cv2.imread(str(OUT / f'charuco-{cam}' / used[keep[0]]))
    cv2.imwrite(str(OUT / f'undistorted-sample-{cam}.png'), cv2.undistort(sample, K, D, None, newK))
    res = dict(camera=cam, image_size=[w, h], model='rational' if rational else 'standard', rms_px=float(rms),
               views_used=len(keep), views_dropped=dropped, K=K.tolist(), D=D.ravel().tolist(),
               fovx_deg=fovx_raw, fovy_deg=fovy_raw, undistorted_K=newK.tolist(), undistorted_fovy_deg=fovy_undist,
               board=dict(type='charuco', squares=[7, 5], square_m=0.035, marker_m=0.026, dictionary='DICT_4X4_50'),
               date=datetime.datetime.now().isoformat(timespec='seconds'))
    path = OUT / f'intrinsics-{cam}.json'
    json.dump(res, open(path, 'w'), indent=1)
    print(f'{cam}: rms {rms:.3f} px（< 0.5 好，> 1 需重拍），用 {len(keep)} 张，剔除 {len(dropped)} 张')
    print(f'  fovx {fovx_raw:.1f}°  fovy {fovy_raw:.1f}°  去畸变后 fovy {fovy_undist:.1f}°  -> {path}')


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('wrist', 'side'):
        sys.exit(__doc__)
    main()
