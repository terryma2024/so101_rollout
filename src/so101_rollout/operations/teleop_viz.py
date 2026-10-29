"""lerobot-teleoperate 的包装：限制发往 rerun 的图像数据量，参数与 lerobot-teleoperate 相同。

原版每个控制周期（60 Hz）都发一帧 JPEG，而摄像头只有约 20 fps，2/3 是重复帧（约 6 MB/s）。
这里图像按摄像头实际帧率（IMAGE_HZ）发送，其余周期只发关节数据，约 2 MB/s。
关节数据和机械臂控制频率不变。

查看器需 rerun >= 0.34：0.33.x 查看器加载 static 的 JPEG 图像会卡死（0.34.0 修复）。
"""

import os
import time

from lerobot.scripts import lerobot_teleoperate
from lerobot.utils.visualization_utils import log_visualization_data

IMAGE_HZ = float(os.environ.get("WRIST_CAM_FPS", 20))

_last_image_time = 0.0


def throttled_log_visualization_data(display_mode, observation=None, action=None, compress_images=False):
    global _last_image_time
    if observation is not None:
        now = time.perf_counter()
        if now - _last_image_time >= 1 / IMAGE_HZ:
            _last_image_time = now
        else:
            # 本周期不发图像，只发标量
            observation = {k: v for k, v in observation.items() if getattr(v, "ndim", 0) < 2}
    log_visualization_data(display_mode, observation, action, compress_images)


lerobot_teleoperate.log_visualization_data = throttled_log_visualization_data

def main() -> None:
    lerobot_teleoperate.main()


if __name__ == "__main__":
    main()
