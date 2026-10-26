"""lerobot-teleoperate 的包装：限制发往 rerun 的图像数据量，参数与 lerobot-teleoperate 相同。

原版每个控制周期（60 Hz）都发一帧 640x480 JPEG。这台 Mac 上的 rerun 查看器（0.33.1）
解码 JPEG 时界面会卡死，所以这里：
- 图像不压缩（原始 RGB），缩小到 IMAGE_SIZE，约 230 KB/帧；
- 图像按摄像头实际帧率（IMAGE_HZ）发送，其余周期只发关节数据，合计约 4.6 MB/s。
关节数据和机械臂控制频率不变。
"""

import os
import time

import cv2

from lerobot.scripts import lerobot_teleoperate
from lerobot.utils.visualization_utils import log_visualization_data

IMAGE_HZ = float(os.environ.get("WRIST_CAM_FPS", 20))
IMAGE_SIZE = (320, 240)

_last_image_time = 0.0


def throttled_log_visualization_data(display_mode, observation=None, action=None, compress_images=False):
    global _last_image_time
    if observation is not None:
        now = time.perf_counter()
        send_image = now - _last_image_time >= 1 / IMAGE_HZ
        if send_image:
            _last_image_time = now
        observation = {
            k: cv2.resize(v, IMAGE_SIZE, interpolation=cv2.INTER_AREA) if getattr(v, "ndim", 0) == 3 else v
            for k, v in observation.items()
            if send_image or getattr(v, "ndim", 0) < 2
        }
    log_visualization_data(display_mode, observation, action, compress_images=False)


lerobot_teleoperate.log_visualization_data = throttled_log_visualization_data

if __name__ == "__main__":
    lerobot_teleoperate.main()
