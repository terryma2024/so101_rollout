"""lerobot-record 的包装：和 teleop_viz.py 一样，限制发往 rerun 的图像数据量，参数与 lerobot-record 相同。

图像按摄像头帧率（IMAGE_HZ）发给 rerun，其余周期只发关节数据，避免查看器反压卡住录制主循环。
录进数据集的内容不受影响。
"""

import os
import time

from lerobot.scripts import lerobot_record
from lerobot.utils.visualization_utils import log_visualization_data

IMAGE_HZ = float(os.environ.get("WRIST_CAM_FPS", 20))

_last_image_time = 0.0


def throttled_log_visualization_data(*args, observation=None, **kwargs):
    global _last_image_time
    if observation is not None:
        now = time.perf_counter()
        if now - _last_image_time >= 1 / IMAGE_HZ:
            _last_image_time = now
        else:
            observation = {k: v for k, v in observation.items() if getattr(v, "ndim", 0) < 2}
    return log_visualization_data(*args, observation=observation, **kwargs)


lerobot_record.log_visualization_data = throttled_log_visualization_data

if __name__ == "__main__":
    lerobot_record.main()
