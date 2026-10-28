"""策略加载、真机构造、评估数据记录。需要 lerobot（voice_runner 本身不需要）。

观测构造和推理与 lerobot-rollout（--inference.type=sync，interpolation_multiplier=1）一致：
  get_observation -> build_dataset_frame -> predict_action（prepare_observation_for_inference + 前处理 +
  select_action + 后处理）-> 按动作名排序成 {"<关节>.pos": float}。
"""
import pathlib
import threading

GREEN_TASK = "Put the green cube into the paper bowl"
RED_TASK = "Put the red cube into the paper bowl"
TASKS = {"green": GREEN_TASK, "red": RED_TASK}
HERE = pathlib.Path(__file__).resolve().parent


def read_arms_env(path=None):
    """Parse arms.env the way calib_capture.py does (KEY=VALUE lines; only literal values are needed)."""
    path = pathlib.Path(path) if path else HERE / "arms.env"
    return dict(line.split("=", 1) for line in path.read_text().splitlines() if "=" in line and not line.startswith("#"))


def observation_hw_features(robot_obs_features):
    """Same filter as rollout/context.py: cameras (tuples) and .pos scalar joints go to the policy."""
    return {k: v for k, v in robot_obs_features.items() if isinstance(v, tuple) or (v is float and k.endswith((".pos", ".vel")))}


class LoadedPolicy:
    """One ACT policy resident on the GPU: policy + pre/post processors + task text."""

    def __init__(self, name, path, task, device="cuda"):
        import torch
        from lerobot.configs import PreTrainedConfig
        from lerobot.policies import get_policy_class, make_pre_post_processors

        self.name, self.path, self.task, self.device = name, str(path), task, device
        cfg = PreTrainedConfig.from_pretrained(self.path)
        cfg.pretrained_path = pathlib.Path(self.path)
        cfg.device = device
        policy = get_policy_class(cfg.type).from_pretrained(self.path, config=cfg)
        self.policy = policy.to(device).eval()
        self.cfg = cfg
        self.pre, self.post = make_pre_post_processors(
            policy_cfg=cfg, pretrained_path=self.path, pretrained_revision=cfg.pretrained_revision,
            dataset_stats=None,
            preprocessor_overrides={"device_processor": {"device": device},
                                    "rename_observations_processor": {"rename_map": {}}})
        self.torch = torch
        self.features = None
        self.action_keys = None
        self.robot_type = ""

    def bind(self, robot):
        """Tie the policy to a robot's feature layout (call once after the robot object exists)."""
        from lerobot.utils.feature_utils import hw_to_dataset_features
        self.features = hw_to_dataset_features(observation_hw_features(robot.observation_features), "observation")
        raw = [k for k in robot.action_features if k.endswith((".pos", ".vel"))]
        names = getattr(self.cfg, "action_feature_names", None)
        self.action_keys = list(names) if names and set(names) == set(raw) else raw
        self.robot_type = robot.name

    def reset(self):
        self.policy.reset()
        self.pre.reset()
        self.post.reset()

    def act(self, obs):
        from lerobot.common.control_utils import predict_action
        from lerobot.utils.feature_utils import build_dataset_frame
        frame = build_dataset_frame(self.features, obs, prefix="observation")
        action = predict_action(frame, self.policy, self.torch.device(self.device), self.pre, self.post,
                                bool(self.cfg.use_amp), task=self.task, robot_type=self.robot_type)
        vals = action.squeeze(0).cpu()
        return {k: float(vals[i]) for i, k in enumerate(self.action_keys)}

    def warmup(self, obs, n=2):
        """Run a few throwaway inferences (cudnn autotune, allocator) so the first real tick is not slow."""
        for _ in range(n):
            self.reset()
            self.act(dict(obs))
        self.reset()


def make_real_follower(env, max_relative_target=30.0):
    """SO101 follower with the same two cameras as rollout.sh / record.sh (opens serial port and cameras)."""
    from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
    from lerobot.robots import make_robot_from_config
    from lerobot.robots.so_follower import SO101FollowerConfig

    cameras = {
        "wrist": OpenCVCameraConfig(index_or_path=env["WRIST_CAM"], width=640, height=480,
                                    fps=int(env.get("WRIST_CAM_FPS", 20))),
        "side": OpenCVCameraConfig(index_or_path=env["SIDE_CAM"], width=640, height=480,
                                   fps=int(env.get("SIDE_CAM_FPS", 30)), fourcc="MJPG"),
    }
    cfg = SO101FollowerConfig(port=env["FOLLOWER_PORT"], id=env["FOLLOWER_ID"], cameras=cameras,
                              max_relative_target=max_relative_target)
    return make_robot_from_config(cfg)


class EpisodeRecorder:
    """--record <name>: every run becomes one LeRobotDataset episode (dataset root /data/work/so101-datasets/<name>,
    repo id local/rollout_<name>, same as rollout.sh). Frames are (observation, commanded action, task)."""

    def __init__(self, robot, name, fps=20, root_base="/data/work/so101-datasets"):
        from lerobot.datasets import LeRobotDataset
        from lerobot.utils.feature_utils import combine_feature_dicts, hw_to_dataset_features

        obs_hw = observation_hw_features(robot.observation_features)
        act_hw = {k: v for k, v in robot.action_features.items() if k.endswith((".pos", ".vel"))}
        self.features = combine_feature_dicts(hw_to_dataset_features(act_hw, "action"),
                                              hw_to_dataset_features(obs_hw, "observation"))
        root = pathlib.Path(root_base) / name
        if root.exists():
            raise FileExistsError(f"{root} 已存在；换一个 --record 名字")
        self.root = root
        self.dataset = LeRobotDataset.create(f"local/rollout_{name}", fps, root=root, robot_type=robot.name,
                                             features=self.features, use_videos=True,
                                             image_writer_threads=4 * len(robot.cameras))
        self.task, self.frames, self.saved = None, 0, 0
        self._saver = None
        self.error = None

    @property
    def busy(self):
        """True while the previous episode is still being encoded/saved (a new run must wait for it)."""
        return self._saver is not None and self._saver.is_alive()

    def begin(self, task):
        self.task, self.frames = task, 0

    def add(self, obs, action):
        from lerobot.utils.feature_utils import build_dataset_frame
        frame = {**build_dataset_frame(self.features, obs, prefix="observation"),
                 **build_dataset_frame(self.features, action, prefix="action"), "task": self.task}
        self.dataset.add_frame(frame)
        self.frames += 1

    def end(self, save=True):
        if self.frames == 0:
            return
        self.frames = 0
        if not save:
            self.dataset.clear_episode_buffer()
            return
        # Video encoding takes seconds: do it off the control thread so the arm keeps returning to rest.
        self._saver = threading.Thread(target=self._save, daemon=False, name="episode-saver")
        self._saver.start()

    def _save(self):
        try:
            self.dataset.save_episode()
            self.saved += 1
        except Exception as error:  # noqa: BLE001
            self.error = error

    def close(self):
        if self._saver is not None:
            self._saver.join()
        self.dataset.finalize()
