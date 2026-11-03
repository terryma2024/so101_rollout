#!/usr/bin/env python3
"""Offline SmolVLA latency probe on recorded observations; never opens robot hardware.

Run with the separate SmolVLA environment. Dataset/video loading is outside the
timed path: the benchmark measures processing + policy + action processing, not
camera acquisition, serial writes, rendering, or the actual robot control loop.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import datetime
import hashlib
import json
import math
import time
from pathlib import Path


TASKS = {
    "green": "Put the green cube into the paper bowl",
    "red": "Put the red cube into the paper bowl",
}
CAMERA_MAP = {
    "observation.images.wrist": "observation.images.camera1",
    "observation.images.side": "observation.images.camera2",
}


def latency_stats(values: list[float], budget_ms: float = 50.0) -> dict:
    """Linear-interpolated quantiles, retaining explicit deadline misses."""
    if not values:
        return {"count": 0}
    ordered = sorted(values)

    def percentile(q: float) -> float:
        index = (len(ordered) - 1) * q
        low = math.floor(index)
        high = math.ceil(index)
        return ordered[low] + (ordered[high] - ordered[low]) * (index - low)

    misses = sum(v > budget_ms for v in values)
    return {
        "count": len(values),
        "mean_ms": sum(values) / len(values),
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
        "max_ms": ordered[-1],
        "budget_ms": budget_ms,
        "over_budget_count": misses,
        "over_budget_fraction": misses / len(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--vlm", type=Path, required=True)
    parser.add_argument("--green-dataset", type=Path, required=True)
    parser.add_argument("--red-dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--precision", choices=["float32", "autocast-bfloat16"], default="float32")
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--chunks", type=int, default=50)
    parser.add_argument("--tick-chunks", type=int, default=4)
    parser.add_argument("--frames-per-color", type=int, default=8)
    parser.add_argument("--paced-ticks-per-color", type=int, default=100)
    args = parser.parse_args()
    if min(args.warmup, args.chunks, args.tick_chunks, args.frames_per_color, args.paced_ticks_per_color) < 1:
        parser.error("sample counts must be positive")
    if args.output.exists():
        parser.error("output already exists; use a fresh evidence directory")
    args.output.mkdir(parents=True)

    import torch
    from lerobot.configs.policies import PreTrainedConfig
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.policies import make_pre_post_processors
    from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required for this local control-budget probe")
    torch.manual_seed(1000)
    torch.set_num_threads(4)
    config = PreTrainedConfig.from_pretrained(args.policy, local_files_only=True)
    config.device = "cuda"
    # The complete policy checkpoint supplies all VLM weights, so avoid fetching
    # and then overwriting a second copy of the upstream VLM model weights.
    config.load_vlm_weights = False
    config.vlm_model_name = str(args.vlm.resolve())
    config.empty_cameras = 0
    config.push_to_hub = False
    config.use_amp = args.precision == "autocast-bfloat16"
    torch.cuda.synchronize()
    load_start = time.perf_counter()
    policy = SmolVLAPolicy.from_pretrained(args.policy, config=config, local_files_only=True, strict=True)
    policy = policy.to(device="cuda", dtype=torch.float32).eval()
    torch.cuda.synchronize()
    load_seconds = time.perf_counter() - load_start
    preprocessor, postprocessor = make_pre_post_processors(
        policy_cfg=config,
        pretrained_path=str(args.policy),
        preprocessor_overrides={
            "rename_observations_processor": {"rename_map": CAMERA_MAP},
            "device_processor": {"device": "cuda"},
            "tokenizer_processor": {"tokenizer_name": str(args.vlm.resolve())},
        },
    )
    observations = []
    source_records = []
    for color in ("green", "red"):
        root = getattr(args, f"{color}_dataset")
        info = json.loads((root / "meta/info.json").read_text())
        for key in CAMERA_MAP:
            shape = info["features"][key]["shape"]
            if shape != [480, 640, 3]:
                raise ValueError(f"Unexpected source image dimensions for {key}: {shape}")
        dataset = LeRobotDataset(
            repo_id=f"local/{root.name}", root=root, download_videos=False, video_backend="pyav"
        )
        # Sample through the beginning of each actual recorded first episode.
        indices = list(range(0, args.frames_per_color * 10, 10))
        for index in indices:
            item = dataset[index]
            obs = {key: item[key].clone() for key in (*CAMERA_MAP, "observation.state")}
            obs["task"] = TASKS[color]
            observations.append((color, obs))
            source_records.append({"color": color, "dataset": str(root), "frame_index": index})
        del dataset

    language_inputs = {}
    from lerobot.utils.constants import OBS_LANGUAGE_TOKENS
    for color_index, color in enumerate(("green", "red")):
        prepared = preprocessor(dict(observations[color_index * args.frames_per_color][1]))
        tokens = prepared[OBS_LANGUAGE_TOKENS].detach().cpu().tolist()
        language_inputs[color] = {"task": TASKS[color], "token_ids": tokens}
    if language_inputs["green"]["token_ids"] == language_inputs["red"]["token_ids"]:
        raise RuntimeError("Red and green instructions produced identical tokens")

    def autocast():
        if args.precision == "autocast-bfloat16":
            return torch.autocast("cuda", dtype=torch.bfloat16)
        return contextlib.nullcontext()

    def measure(kind: str, index: int, select: bool) -> dict:
        color, obs = observations[index % len(observations)]
        torch.cuda.synchronize()
        start = time.perf_counter()
        batch = preprocessor(dict(obs))
        torch.cuda.synchronize()
        processed = time.perf_counter()
        with torch.inference_mode(), autocast():
            action = policy.select_action(batch) if select else policy.predict_action_chunk(batch)
        torch.cuda.synchronize()
        inferred = time.perf_counter()
        # Chunk benchmark performs one CPU action postprocess for the first
        # action, matching a real control tick's output path.
        action_for_post = action if select else action[:, 0]
        result = postprocessor(action_for_post)
        torch.cuda.synchronize()
        end = time.perf_counter()
        if not torch.isfinite(action).all().item():
            raise RuntimeError("Nonfinite value in the complete action chunk")
        if tuple(result.shape) != (1, 6) or not torch.isfinite(result).all().item():
            raise RuntimeError(f"Invalid output action: shape={tuple(result.shape)}")
        return {
            "kind": kind, "index": index, "color": color,
            "preprocess_ms": (processed - start) * 1000,
            "policy_ms": (inferred - processed) * 1000,
            "postprocess_ms": (end - inferred) * 1000,
            "end_to_end_ms": (end - start) * 1000,
            "finite": True,
        }

    torch.cuda.reset_peak_memory_stats()
    rows = [measure("cold_chunk", 0, False)]
    for i in range(args.warmup):
        rows.append(measure("warmup_chunk", i, False))
    print("warmup complete", flush=True)
    for i in range(args.chunks):
        rows.append(measure("steady_chunk", i, False))
        if (i + 1) % 10 == 0:
            print(f"chunk {i + 1}/{args.chunks}", flush=True)
    # Keep each queue on one instruction; changing task while a queue is
    # populated would return stale actions. Reset explicitly at color switch.
    for color_index, color in enumerate(("green", "red")):
        policy.reset()
        count = args.tick_chunks * config.n_action_steps
        for i in range(count):
            boundary = len(policy._queues["action"]) == 0
            frame_index = color_index * args.frames_per_color + i % args.frames_per_color
            row = measure("boundary_tick" if boundary else "queued_tick", frame_index, True)
            row["tick_in_color"] = i
            rows.append(row)
        print(f"{color}: {count} select_action ticks complete", flush=True)

    paced = {}
    for color_index, color in enumerate(("green", "red")):
        policy.reset()
        send_intervals = []
        previous_send = None
        paced_start = time.perf_counter()
        for i in range(args.paced_ticks_per_color):
            tick_start = time.perf_counter()
            boundary = len(policy._queues["action"]) == 0
            frame_index = color_index * args.frames_per_color + i % args.frames_per_color
            row = measure("paced_boundary_tick" if boundary else "paced_queued_tick", frame_index, True)
            sent = time.perf_counter()
            if previous_send is not None:
                send_intervals.append((sent - previous_send) * 1000)
            previous_send = sent
            row["tick_in_color"] = i
            rows.append(row)
            time.sleep(max(0, 0.05 - (time.perf_counter() - tick_start)))
        elapsed = time.perf_counter() - paced_start
        paced[color] = {
            "tick_count": args.paced_ticks_per_color,
            "elapsed_seconds": elapsed,
            "achieved_compute_loop_hz": args.paced_ticks_per_color / elapsed,
            "action_ready_intervals_ms": send_intervals,
            "action_ready_interval_stats": latency_stats(send_intervals),
            "pacing": "sleep remaining tick time; no catch-up bursts after overrun",
        }

    metrics = {}
    for kind in ("cold_chunk", "steady_chunk", "boundary_tick", "queued_tick", "paced_boundary_tick", "paced_queued_tick"):
        selected = [r for r in rows if r["kind"] == kind]
        metrics[kind] = {
            name: latency_stats([r[name] for r in selected])
            for name in ("preprocess_ms", "policy_ms", "postprocess_ms", "end_to_end_ms")
        }
    all_ticks = [r["end_to_end_ms"] for r in rows if r["kind"] in ("boundary_tick", "queued_tick")]
    metrics["all_ticks"] = latency_stats(all_ticks)
    chunk_max = metrics["steady_chunk"]["end_to_end_ms"]["max_ms"]
    tick_max = metrics["all_ticks"]["max_ms"]
    config.save_pretrained(args.output / "effective-policy-config")
    report = {
        "passed_smoke": args.warmup >= 5 and args.chunks >= 30,
        "diagnostic_only": args.warmup < 5 or args.chunks < 30,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "policy": str(args.policy.resolve()), "vlm": str(args.vlm.resolve()),
        "policy_config_sha256": hashlib.sha256((args.policy / "config.json").read_bytes()).hexdigest(),
        "gpu": torch.cuda.get_device_name(), "torch": torch.__version__,
        "precision": args.precision, "weight_storage_dtype": "float32",
        "policy_load_seconds": load_seconds,
        "camera_map": CAMERA_MAP,
        "missing_camera3": "omitted; empty_cameras=0; two valid cameras only",
        "input_dimensions_checked_before_decode": [640, 480],
        "resize_with_padding": config.resize_imgs_with_padding,
        "sources": source_records, "warmup_chunks": args.warmup,
        "language_inputs": language_inputs,
        "steady_chunks": args.chunks, "n_action_steps": config.n_action_steps,
        "chunk_size": config.chunk_size, "num_steps": config.num_steps,
        "stats": "pretrained base stats for load/latency only, not SO101 task deployment",
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        "metrics": metrics,
        "paced_offline_replay": paced,
        "assessment": {
            "target_hz": 20, "tick_budget_ms": 50,
            "chunk_execution_budget_ms": config.n_action_steps * 50,
            "all_measured_chunks_fit_execution_budget": chunk_max < config.n_action_steps * 50,
            "all_measured_synchronous_ticks_fit_50ms": tick_max <= 50,
            "async_or_rtc_validated": False,
            "robot_motion_performed": False,
            "camera_acquisition_and_serial_io_included": False,
        },
    }
    (args.output / "samples.json").write_text(json.dumps(rows, indent=2) + "\n")
    fields = sorted({key for row in rows for key in row})
    with (args.output / "samples.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"metrics": metrics, "assessment": report["assessment"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
