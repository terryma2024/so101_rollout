"""由 ArUco 定位纸计算侧面相机在机械臂坐标里的位姿。

  python calib_extrinsics.py <aruco-sheet-layout.json>

需要先有 $CALIB_DIR/intrinsics-side.json 和 $CALIB_DIR/aruco-side/*.png（calib_capture.py aruco）。
坐标系与平面图相同（cm）：原点 = 从臂转轴在桌面上的点，+x 机械臂左侧，+y 前，+z 上。
输出 $CALIB_DIR/extrinsics-side.json 和一张标注图。
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
    layout = json.load(open(sys.argv[1]))
    # The plan frame (+x left, +y forward, +z up) is left-handed. Solve in the right-handed frame (+x right) and
    # convert back, otherwise PnP on the table plane returns the mirrored camera below the table.
    flip = np.array([-1.0, 1.0, 1.0])
    world = {int(k): np.array(v, float) * flip for k, v in layout['markers'].items()}   # cm, right-handed
    intr = json.load(open(OUT / 'intrinsics-side.json'))
    K, D = np.array(intr['K']), np.array(intr['D'])
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100))
    poses = []
    for f in sorted((OUT / 'aruco-side').glob('*.png')):
        img = cv2.imread(str(f))
        corners, ids, _ = det.detectMarkers(img)
        if ids is None:
            continue
        obj, pix = [], []
        for c, i in zip(corners, ids.ravel()):
            if int(i) in world:
                obj.extend(world[int(i)])
                pix.extend(c[0])
        if len(obj) < 24:
            continue
        obj, pix = np.array(obj, np.float64), np.array(pix, np.float64)
        ok, rvec, tvec = cv2.solvePnP(obj, pix, K, D, flags=cv2.SOLVEPNP_ITERATIVE)
        rvec, tvec = cv2.solvePnPRefineLM(obj, pix, K, D, rvec, tvec)
        err = float(np.sqrt(np.mean(np.sum((cv2.projectPoints(obj, rvec, tvec, K, D)[0].reshape(-1, 2) - pix) ** 2, 1))))
        R, _ = cv2.Rodrigues(rvec)
        pos = (-R.T @ tvec).ravel() * flip          # camera centre, back in the plan frame (cm)
        fwd = (R.T @ np.array([0, 0, 1.0])) * flip  # optical axis in the plan frame
        up = (R.T @ np.array([0, -1.0, 0])) * flip  # image up in the plan frame
        poses.append(dict(image=f.name, markers=len(obj) // 4, reproj_px=err, position_cm=pos.tolist(),
                          forward=fwd.tolist(), image_up=up.tolist()))
        vis = img.copy()
        cv2.aruco.drawDetectedMarkers(vis, corners, ids)
        cv2.drawFrameAxes(vis, K, D, rvec, tvec, 10)   # axes drawn in the right-handed frame (+x = robot right)
        cv2.imwrite(str(OUT / 'extrinsics-side-annotated.png'), vis)
    if not poses:
        sys.exit('没有可用的定位纸图片（每张至少 6 个标记）')
    P = np.array([p['position_cm'] for p in poses])
    F = np.array([p['forward'] for p in poses]).mean(0)
    F /= np.linalg.norm(F)
    yaw = math.degrees(math.atan2(F[1], F[0]))
    pitch = math.degrees(math.asin(-F[2]))
    res = dict(frame=layout['frame'], camera='side', intrinsics=str(OUT / 'intrinsics-side.json'),
               position_cm=P.mean(0).tolist(), position_spread_cm=P.std(0).tolist(), forward=F.tolist(),
               yaw_deg_from_plus_x=yaw, pitch_down_deg=pitch, frames=poses,
               date=datetime.datetime.now().isoformat(timespec='seconds'))
    json.dump(res, open(OUT / 'extrinsics-side.json', 'w'), indent=1)
    x, y, z = P.mean(0)
    print(f'侧面相机位置：左 {x:.1f} cm，前 {y:.1f} cm，高 {z:.1f} cm（相对从臂转轴/桌面）')
    print(f'朝向：水平方位 {yaw:.1f}°（0° = 机械臂左方，90° = 前方），俯角 {pitch:.1f}°')
    print(f'帧间位置标准差 {P.std(0).round(2).tolist()} cm；重投影误差 {[round(p["reproj_px"], 2) for p in poses]} px')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main()
