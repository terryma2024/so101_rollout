"""lerobot-teleoperate 的包装：限制发往 rerun 的图像数据量，参数与 lerobot-teleoperate 相同。

原版每个控制周期（60 Hz）都发一帧 JPEG（质量 95，约 100 KB），约 6 MB/s，远程查看器处理不过来时
会反压卡住遥操作主循环。这里：
- 图像按摄像头实际帧率（IMAGE_HZ）发送，其余周期只发关节数据；
- JPEG 质量降到 JPEG_QUALITY（约 34 KB/帧）。
关节数据和机械臂控制频率不变。
"""

import functools
import os
import time

import rerun as rr

from lerobot.scripts import lerobot_teleoperate
from lerobot.utils.visualization_utils import log_visualization_data

IMAGE_HZ = float(os.environ.get("WRIST_CAM_FPS", 20))
JPEG_QUALITY = 75

rr.Image.compress = functools.partialmethod(rr.Image.compress, jpeg_quality=JPEG_QUALITY)

_last_image_time = 0.0


def throttled_log_visualization_data(display_mode, observation=None, action=None, compress_images=False):
    global _last_image_time
    now = time.perf_counter()
    if observation is not None and now - _last_image_time < 1 / IMAGE_HZ:
        # 本周期不发图像，只发标量
        observation = {k: v for k, v in observation.items() if getattr(v, "ndim", 0) < 2}
    else:
        _last_image_time = now
    log_visualization_data(display_mode, observation, action, compress_images)


lerobot_teleoperate.log_visualization_data = throttled_log_visualization_data

if __name__ == "__main__":
    lerobot_teleoperate.main()
