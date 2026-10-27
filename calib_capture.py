"""标定采图（只用摄像头，不碰机械臂）。摄像头参数与 record.sh 相同（640x480，手腕 YUYV 20 fps，侧面 MJPG 30）。

  python calib_capture.py charuco wrist|side   拿 ChArUco 板在镜头前慢慢换位置、角度、远近，检测到足够角点且
                                               和已存的图不重复时自动保存，存够 COUNT 张（默认 25）结束
  python calib_capture.py aruco                侧面相机拍 ArUco 定位纸（外参），连续存 5 帧
  python calib_capture.py snap                 两路各存一帧（调曝光、白平衡用）

有图形界面时显示预览（空格手动保存，q 退出）；SSH 无界面时自动模式，终端打印进度。
图片存到 $CALIB_DIR（默认 /data/work/so101-evidence/real-robot/calib-<日期>）。
"""
import datetime
import os
import pathlib
import sys
import time

import cv2
import numpy as np

HERE = pathlib.Path(__file__).parent
ENV = dict(l.split('=', 1) for l in (HERE / 'arms.env').read_text().splitlines() if '=' in l and not l.startswith('#'))
CAMS = {'wrist': (ENV['WRIST_CAM'], None, int(ENV.get('WRIST_CAM_FPS', 20))),
        'side': (ENV['SIDE_CAM'], 'MJPG', int(ENV.get('SIDE_CAM_FPS', 30)))}
OUT = pathlib.Path(os.environ.get('CALIB_DIR', f'/data/work/so101-evidence/real-robot/calib-{datetime.date.today():%Y%m%d}'))
COUNT = int(os.environ.get('COUNT', 25))
GUI = bool(os.environ.get('DISPLAY')) and os.environ.get('NO_GUI') != '1'


def open_cam(name):
    path, fourcc, fps = CAMS[name]
    cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
    if fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, fps)
    if not cap.isOpened():
        sys.exit(f'打不开摄像头 {name}: {path}')
    for _ in range(10):
        cap.read()
    return cap


def stamp():
    return datetime.datetime.now().strftime('%H%M%S_%f')[:-3]


def snap():
    OUT.joinpath('snap').mkdir(parents=True, exist_ok=True)
    for name in CAMS:
        cap = open_cam(name)
        ok, img = cap.read()
        cap.release()
        if not ok:
            print(name, '取帧失败')
            continue
        p = OUT / 'snap' / f'{name}_{stamp()}.png'
        cv2.imwrite(str(p), img)
        b, g, r = (img[..., i].mean() for i in range(3))
        print(f'{name}: {p}  平均亮度 {img.mean():.0f}/255  B/G/R 均值 {b:.0f}/{g:.0f}/{r:.0f}  '
              f'过曝像素 {(img.max(axis=2) >= 250).mean() * 100:.1f}%')


def charuco(name):
    d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    board = cv2.aruco.CharucoBoard((7, 5), 0.035, 0.026, d)
    det = cv2.aruco.CharucoDetector(board)
    out = OUT / f'charuco-{name}'
    out.mkdir(parents=True, exist_ok=True)
    saved = [np.load(p) for p in sorted(out.glob('*.npy'))]
    cap = open_cam(name)
    print(f'{name}: 已有 {len(saved)} 张，目标 {COUNT} 张。慢慢移动标定板：画面中间、四角、边缘，远近和倾斜都要有。')
    last = 0.0
    while len(saved) < COUNT:
        ok, img = cap.read()
        if not ok:
            continue
        corners, ids, _, _ = det.detectBoard(img)
        n = 0 if ids is None else len(ids)
        view = img.copy()
        if n:
            cv2.aruco.drawDetectedCornersCharuco(view, corners, ids)
        new = False
        if n >= 12 and time.time() - last > 1.0:
            c = corners.reshape(-1, 2)
            sig = np.array([*c.mean(0), *c.std(0), cv2.contourArea(cv2.convexHull(c.astype(np.float32)))])
            new = all(np.abs(sig[:2] - s[:2]).max() > 40 or abs(sig[4] - s[4]) > 0.25 * s[4] or
                      np.abs(sig[2:4] - s[2:4]).max() > 15 for s in saved)
        key = -1
        if GUI:
            cv2.putText(view, f'{len(saved)}/{COUNT} corners {n}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow(f'charuco {name}', view)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
        if new or (key == ord(' ') and n >= 6):
            t = stamp()
            cv2.imwrite(str(out / f'{t}.png'), img)
            np.save(out / f'{t}.npy', sig if n >= 12 else np.zeros(5))
            saved.append(sig if n >= 12 else np.zeros(5))
            last = time.time()
            print(f'  保存 {len(saved)}/{COUNT}（角点 {n}）')
    cap.release()
    cv2.destroyAllWindows()
    print(f'完成：{out}')


def aruco():
    out = OUT / 'aruco-side'
    out.mkdir(parents=True, exist_ok=True)
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100))
    cap = open_cam('side')
    n_saved = 0
    while n_saved < 5:
        ok, img = cap.read()
        if not ok:
            continue
        _, ids, _ = det.detectMarkers(img)
        n = 0 if ids is None else len(ids)
        if n >= 6:
            cv2.imwrite(str(out / f'{stamp()}.png'), img)
            n_saved += 1
            print(f'  保存 {n_saved}/5（检测到 {n} 个标记）')
            time.sleep(0.3)
        elif GUI:
            cv2.imshow('aruco side', img)
            cv2.waitKey(1)
    cap.release()
    print(f'完成：{out}')


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'snap':
        snap()
    elif mode == 'charuco' and len(sys.argv) > 2 and sys.argv[2] in CAMS:
        charuco(sys.argv[2])
    elif mode == 'aruco':
        aruco()
    else:
        sys.exit(__doc__)
