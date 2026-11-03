"""Register the repository async backend, then run official LeRobot rollout.

No installed package is modified. CLI registration and the context factory
binding are local to this process and pinned to LeRobot 0.6.1.
"""
from dataclasses import dataclass

from lerobot.rollout import context
from lerobot.rollout.inference.factory import InferenceEngineConfig

from .async_engine import SmolVLAAsyncEngine


@InferenceEngineConfig.register_subclass('so101_async')
@dataclass
class SO101AsyncConfig(InferenceEngineConfig):
    prefetch: int = 10
    telemetry_path: str | None = None
    recording_path: str | None = None
    recording_max_items: int = 256
    recording_max_bytes: int = 128*1024*1024


def create_async_engine(config, **kwargs):
    if not isinstance(config, SO101AsyncConfig):
        raise ValueError('SmolVLA async entry requires --inference.type=so101_async')
    if kwargs.get('use_torch_compile'):
        raise ValueError('torch.compile is not validated for this async backend')
    return SmolVLAAsyncEngine(prefetch=config.prefetch, telemetry_path=config.telemetry_path, recording_path=config.recording_path, recording_max_items=config.recording_max_items, recording_max_bytes=config.recording_max_bytes, **kwargs)


def main():
    import torch
    # Match the validated offline backend budget and avoid CPU oversubscription
    # while camera acquisition/encoding runs beside the inference worker.
    torch.set_num_threads(4)
    # build_rollout_context resolves its imported factory in this module.
    context.create_inference_engine = create_async_engine
    from lerobot.scripts.lerobot_rollout import main as official_main
    official_main()


if __name__ == '__main__':
    main()
