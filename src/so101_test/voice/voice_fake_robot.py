"""离线演练用的假机器人：从录好的 LeRobotDataset 回放 side/wrist 画面和关节状态，接受指令但不动硬件。

get_observation() 每调用一次前进一帧（控制循环每拍调一次，即按 20 Hz 回放一整条 episode）；回放到末尾后停在最后一帧。
send_action() 只记录（并统计与回放状态的最大偏差），不影响回放。on_run_start(colour) 把对应颜色的数据集回放倒回开头。
接口和 SO101Follower 一致：observation_features / action_features / name / cameras / disconnect()。
"""
import numpy as np

from .voice_runner import KEYS


def _load_episode(root, episode, max_frames):
    import torch  # noqa: F401 - LeRobotDataset returns tensors
    from lerobot.datasets import LeRobotDataset

    ds = LeRobotDataset(f"local/{root.rstrip('/').split('/')[-1]}", root=root)
    meta = ds.meta.episodes[episode]
    lo, hi = int(meta["dataset_from_index"]), int(meta["dataset_to_index"])
    hi = min(hi, lo + max_frames)
    frames = []
    for i in range(lo, hi):
        item = ds[i]
        frame = {k: float(v) for k, v in zip(KEYS, item["observation.state"].tolist())}
        for cam in ("wrist", "side"):
            img = item[f"observation.images.{cam}"]                       # float32 CHW in [0, 1]
            frame[cam] = (img.permute(1, 2, 0).numpy() * 255.0 + 0.5).astype(np.uint8)
        frames.append(frame)
    return frames


class DatasetReplayRobot:
    name = "so_follower"
    cameras = {"wrist": None, "side": None}

    def __init__(self, roots, episode=2, max_frames=900):
        """roots: {colour: dataset root}. Each colour replays `episode` of its dataset."""
        self.replays = {c: _load_episode(r, episode, max_frames) for c, r in roots.items()}
        self.colour = next(iter(self.replays))
        self.idx = 0
        self.sent = []
        self.max_dev = 0.0
        self.connected = True

    @property
    def observation_features(self):
        return {**{k: float for k in KEYS}, "wrist": (480, 640, 3), "side": (480, 640, 3)}

    @property
    def action_features(self):
        return {k: float for k in KEYS}

    def start_replay(self, colour):
        self.colour, self.idx = (colour if colour in self.replays else self.colour), 0

    def peek_first(self):
        return dict(self.replays[self.colour][0])

    def get_observation(self):
        frames = self.replays[self.colour]
        obs = frames[min(self.idx, len(frames) - 1)]
        self.idx += 1
        return dict(obs)

    def send_action(self, action):
        frames = self.replays[self.colour]
        cur = frames[min(max(self.idx - 1, 0), len(frames) - 1)]
        self.max_dev = max([self.max_dev] + [abs(action[k] - cur[k]) for k in KEYS if k in action])
        self.sent.append(dict(action))
        return action

    def disconnect(self):
        self.connected = False
