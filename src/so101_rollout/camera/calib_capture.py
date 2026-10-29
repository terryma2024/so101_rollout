"""标定采图（只用摄像头，不碰机械臂）。摄像头参数与 record.sh 相同（640x480，手腕 YUYV 20 fps，侧面 MJPG 30）。

  python calib_capture.py charuco wrist|side   拿 ChArUco 板在镜头前慢慢换位置、角度、远近，检测到足够角点且
                                               和已存的图不重复时自动保存，存够 COUNT 张（默认 25）结束
  python calib_capture.py aruco                侧面相机拍 ArUco 定位纸（外参），连续存 5 帧
  python calib_capture.py snap                 两路各存一帧（调曝光、白平衡用）

预览：OpenCV 有窗口支持时用窗口（空格手动保存，q 退出）；否则用 rerun：优先发到 arms.env 的 RERUN_VIEWER_HOST（Mac），
连不上才在本机桌面开窗口（PREVIEW=remote/local 可强制）；都不可用时只在终端打印进度。rerun 模式下 Ctrl+C 结束。
图片存到 $CALIB_DIR（默认 /data/work/so101-evidence/real-robot/calib-<日期>）。
"""
import datetime
import os
import pathlib
import sys
import time

from ..config import load_arms_env

import cv2
import numpy as np

ENV = load_arms_env()
CAMS = {'wrist': (ENV['WRIST_CAM'], None, int(ENV.get('WRIST_CAM_FPS', 20))),
        'side': (ENV['SIDE_CAM'], 'MJPG', int(ENV.get('SIDE_CAM_FPS', 30)))}
OUT = pathlib.Path(os.environ.get('CALIB_DIR', f'/data/work/so101-evidence/real-robot/calib-{datetime.date.today():%Y%m%d}'))
COUNT = int(os.environ.get('COUNT', 25))
NO_GUI = os.environ.get('NO_GUI') == '1'


class Preview:
    """Live preview: an OpenCV window if this OpenCV build has one, else the rerun viewer, else nothing."""

    def __init__(self, title):
        self.title, self.mode, self.last = title, None, 0.0
        if NO_GUI:
            return
        if os.environ.get('DISPLAY'):
            try:
                cv2.imshow(title, np.zeros((8, 8, 3), np.uint8))
                cv2.waitKey(1)
                self.mode = 'cv2'
                return
            except cv2.error:
                pass   # headless OpenCV build (opencv-python-headless): fall through to rerun
        try:
            import socket
            import subprocess

            import rerun as rr
            rr.init(f'calib-{title}')
            # PREVIEW=remote|local forces the target; by default the remote viewer (arms.env) wins when it answers,
            # because a terminal on this machine often has DISPLAY=:1 while the person watches from the Mac.
            host, port = ENV.get('RERUN_VIEWER_HOST'), int(ENV.get('RERUN_VIEWER_PORT', 9876))
            want = os.environ.get('PREVIEW', 'auto')
            remote_ok = False
            if want in ('auto', 'remote') and host:
                try:
                    socket.create_connection((host, port), timeout=3).close()
                    remote_ok = True
                except OSError:
                    if want == 'remote':
                        raise
            local = not remote_ok and subprocess.run(['xdpyinfo'], capture_output=True).returncode == 0
            if remote_ok:
                rr.connect_grpc(url=f'rerun+http://{host}:{port}/proxy')
            elif local:
                rr.spawn(memory_limit='10%')
            else:
                raise OSError(f'rerun 查看器 {host}:{port} 连不上，本机也没有桌面')
            self.rr, self.mode = rr, 'rerun'
            print(f'预览：rerun（{"本机窗口" if local else ENV.get("RERUN_VIEWER_HOST")}），按 Ctrl+C 结束')
        except Exception as error:  # noqa: BLE001 - no viewer is not fatal; the terminal still shows progress
            print(f'没有可用的预览窗口（{error.__class__.__name__}），只在终端打印进度')

    def show(self, view):
        """Returns the key pressed (OpenCV window only), else -1."""
        if self.mode == 'cv2':
            cv2.imshow(self.title, view)
            return cv2.waitKey(1) & 0xFF
        if self.mode == 'rerun' and time.time() - self.last > 0.2:   # 5 Hz is enough to aim the board
            self.last = time.time()
            self.rr.log('preview', self.rr.Image(view[..., ::-1]).compress(jpeg_quality=80))
        return -1

    def close(self):
        if self.mode == 'cv2':
            cv2.destroyAllWindows()


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
    preview = Preview(f'charuco-{name}')
    print(f'{name}: 已有 {len(saved)} 张，目标 {COUNT} 张。慢慢移动标定板：画面中间、四角、边缘，远近和倾斜都要有。')
    try:
        _charuco_loop(cap, det, out, saved, preview)
    except KeyboardInterrupt:
        print('\n已停止（已保存的图片保留，下次运行会接着存）')
    cap.release()
    preview.close()
    print(f'完成：{out}（{len(saved)} 张）')


def _charuco_loop(cap, det, out, saved, preview):
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
        new, sig = False, np.zeros(5)
        if n >= 12 and time.time() - last > 1.0:
            c = corners.reshape(-1, 2)
            sig = np.array([*c.mean(0), *c.std(0), cv2.contourArea(cv2.convexHull(c.astype(np.float32)))])
            new = all(np.abs(sig[:2] - s[:2]).max() > 40 or abs(sig[4] - s[4]) > 0.25 * s[4] or
                      np.abs(sig[2:4] - s[2:4]).max() > 15 for s in saved)
        cv2.putText(view, f'{len(saved)}/{COUNT} corners {n}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        key = preview.show(view)
        if key == ord('q'):
            break
        if new or (key == ord(' ') and n >= 6):
            t = stamp()
            cv2.imwrite(str(out / f'{t}.png'), img)
            np.save(out / f'{t}.npy', sig if n >= 12 else np.zeros(5))
            saved.append(sig if n >= 12 else np.zeros(5))
            last = time.time()
            print(f'  保存 {len(saved)}/{COUNT}（角点 {n}）')


def aruco():
    out = OUT / 'aruco-side'
    out.mkdir(parents=True, exist_ok=True)
    det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100))
    cap = open_cam('side')
    preview = Preview('aruco-side')
    n_saved, said = 0, 0.0
    try:
        while n_saved < 5:
            ok, img = cap.read()
            if not ok:
                continue
            corners, ids, _ = det.detectMarkers(img)
            n = 0 if ids is None else len(ids)
            view = img.copy()
            if n:
                cv2.aruco.drawDetectedMarkers(view, corners, ids)
            preview.show(view)
            if n >= 6:
                cv2.imwrite(str(out / f'{stamp()}.png'), img)
                n_saved += 1
                print(f'  保存 {n_saved}/5（检测到 {n} 个标记）')
                time.sleep(0.3)
            elif time.time() - said > 3:
                said = time.time()
                print(f'  只检测到 {n} 个标记（至少 6 个）：检查定位纸是否在画面内、有没有被挡住或反光')
    except KeyboardInterrupt:
        print('\n已停止')
    cap.release()
    preview.close()
    print(f'完成：{out}')


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'snap':
        snap()
    elif mode == 'charuco' and len(sys.argv) > 2 and sys.argv[2] in CAMS:
        charuco(sys.argv[2])
    elif mode == 'aruco':
        aruco()
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
