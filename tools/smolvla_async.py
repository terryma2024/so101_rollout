#!/usr/bin/env python3
"""Offline asynchronous SmolVLA probe. No camera, serial, or robot APIs."""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import queue
import threading
import time
import traceback

from tools.smolvla_smoke import CAMERA_MAP, TASKS, latency_stats


def aligned_tick(tick, epoch, now, period=0.05):
    late = now - (epoch + tick * period)
    # Allow normal OS wake-up jitter, but never execute a nearly whole-period
    # late action followed immediately by the next absolute deadline.
    skipped = math.ceil(late / period) if late > 0.005 else 0
    return tick + skipped, skipped


def successful_intervals(ticks):
    sent = [r['action_ready'] for r in ticks if not r['starved']]
    return [(b-a)*1000 for a,b in zip(sent,sent[1:])]


@dataclass(frozen=True)
class ChunkRequest:
    identifier: int
    generation: int
    tick: int
    color: str
    frame: int
    sent: float
    observation: dict = field(repr=False)
    delay_seconds: float = 0.0


@dataclass
class ChunkResult:
    request: ChunkRequest
    actions: list[list[float]]
    ready: float
    inference_start: float = 0.0
    inference_end: float = 0.0


class ActionTimeline:
    """CPU actions indexed by their intended control tick, never by arrival order."""

    def __init__(self):
        self.generation = 0
        self.latest_id = -1
        self.actions: dict[int, dict] = {}

    def reset(self):
        self.generation += 1
        self.actions.clear()
        self.latest_id = -1
        return self.generation

    def install(self, result: ChunkResult, current_tick: int) -> dict:
        req = result.request
        if req.generation != self.generation:
            return {"accepted": False, "reason": "stale_generation"}
        if req.identifier <= self.latest_id:
            return {"accepted": False, "reason": "out_of_order"}
        trimmed = max(0, current_tick - req.tick)
        if trimmed >= len(result.actions):
            return {"accepted": False, "reason": "fully_expired"}
        self.latest_id = req.identifier
        # Replacement only after inference completes. Existing actions continue
        # to execute during inference; elapsed predicted actions are discarded.
        self.actions = {k: v for k, v in self.actions.items() if k < current_tick}
        for i in range(trimmed, len(result.actions)):
            self.actions[req.tick + i] = {
                "action": result.actions[i], "generation": req.generation,
                "request_id": req.identifier, "request_tick": req.tick,
                "observation_time": req.sent, "frame": req.frame,
                "color": req.color, "chunk_index": i,
            }
        return {"accepted": True, "trimmed": trimmed, "remaining": self.remaining(current_tick)}

    def pop(self, tick: int):
        self.actions = {k: v for k, v in self.actions.items() if k >= tick}
        return self.actions.pop(tick, None)

    def remaining(self, tick: int) -> int:
        return sum(k >= tick for k in self.actions)


class AsyncWorker:
    """One in-flight request including its unconsumed result; polling never waits."""

    def __init__(self, infer):
        self.infer = infer
        self.requests = queue.Queue(maxsize=1)
        self.results = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._busy = False
        self.started = threading.Event()
        self.thread = threading.Thread(target=self._run, name="smolvla-inference", daemon=True)
        self.thread.start()

    @property
    def busy(self):
        with self._lock:
            return self._busy

    def submit(self, req):
        with self._lock:
            if self._busy:
                return False
            self._busy = True
            self.started.clear()
            self.requests.put_nowait(req)
            return True

    def _run(self):
        while True:
            req = self.requests.get()
            if req is None:
                return
            self.started.set()
            try:
                value = self.infer(req)
            except BaseException:
                value = RuntimeError(traceback.format_exc())
            self.results.put(value)

    def has_result(self):
        return not self.results.empty()

    def poll(self):
        try:
            value = self.results.get_nowait()
        except queue.Empty:
            return None
        with self._lock:
            self._busy = False
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self):
        self.requests.put(None)
        self.thread.join(timeout=30)
        if self.thread.is_alive():
            raise RuntimeError("Inference worker did not stop")


class ModelInference:
    """All CUDA and mutable policy/processor operations belong to this worker."""

    def __init__(self, args, events):
        self.args, self.events = args, events
        self.policy = None
        self.generation = None

    def __call__(self, req):
        import torch
        if self.policy is None:
            from lerobot.configs.policies import PreTrainedConfig
            from lerobot.policies import make_pre_post_processors
            from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
            self.stream = torch.cuda.Stream()
            with torch.cuda.stream(self.stream):
                cfg = PreTrainedConfig.from_pretrained(self.args.policy, local_files_only=True)
                cfg.device = "cuda"
                cfg.load_vlm_weights = False
                cfg.vlm_model_name = str(self.args.vlm.resolve())
                cfg.empty_cameras = 0
                self.policy = SmolVLAPolicy.from_pretrained(
                    self.args.policy, config=cfg, strict=True, local_files_only=True
                ).to(device="cuda", dtype=torch.float32).eval()
                self.pre, self.post = make_pre_post_processors(
                    policy_cfg=cfg, pretrained_path=str(self.args.policy),
                    preprocessor_overrides={
                        "rename_observations_processor": {"rename_map": CAMERA_MAP},
                        "device_processor": {"device": "cuda"},
                        "tokenizer_processor": {"tokenizer_name": str(self.args.vlm.resolve())},
                    },
                )
                for _ in range(self.args.warmup):
                    with torch.inference_mode():
                        self.policy.predict_action_chunk(self.pre(dict(req.observation)))
                self.stream.synchronize()
                cfg.save_pretrained(self.args.output / "effective-policy-config")
            self.events.append({"type": "model_ready", "time": time.perf_counter(),
                                "gpu": torch.cuda.get_device_name(), "torch": torch.__version__})
        start = time.perf_counter()
        self.events.append({"type": "inference_started", "request_id": req.identifier, "time": start})
        with torch.cuda.stream(self.stream), torch.inference_mode():
            if req.generation != self.generation:
                self.policy.reset()
                self.generation = req.generation
            batch = self.pre(dict(req.observation))
            chunk = self.policy.predict_action_chunk(batch)
            # Unnormalize all 50 actions on the worker, then one CPU transfer.
            actions = self.post(chunk).detach().cpu()
            self.stream.synchronize()
            if tuple(actions.shape) != (1, 50, 6) or not torch.isfinite(actions).all().item():
                raise RuntimeError(f"Invalid complete action chunk: {actions.shape}")
            values = actions[0].tolist()
        end = time.perf_counter()
        if req.delay_seconds:
            time.sleep(req.delay_seconds)
        ready = time.perf_counter()
        self.events.append({"type": "inference", "request_id": req.identifier,
                            "generation": req.generation, "color": req.color,
                            "request_tick": req.tick, "frame": req.frame,
                            "observation_time": req.sent, "start": start, "end": end,
                            "ready": ready, "added_delay_seconds": req.delay_seconds})
        return ChunkResult(req, values, ready, start, end)


def write_csv(path, rows):
    with path.open("w") as f:
        w = csv.DictWriter(f, fieldnames=sorted({k for row in rows for k in row}))
        w.writeheader()
        w.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--vlm", type=Path, required=True)
    parser.add_argument("--green-dataset", type=Path, required=True)
    parser.add_argument("--red-dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=90)
    parser.add_argument("--prefetch", type=int, default=10)
    parser.add_argument("--frames-per-color", type=int, default=32)
    parser.add_argument("--warmup", type=int, default=5)
    args = parser.parse_args()
    if args.output.exists() or args.seconds <= 0 or not 1 <= args.prefetch < 50:
        parser.error("fresh output, positive seconds and prefetch 1..49 required")
    args.output.mkdir(parents=True)
    import torch
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    torch.set_num_threads(4)
    torch.manual_seed(1000)
    observations = {}
    for color in TASKS:
        root = getattr(args, color + "_dataset")
        info = json.loads((root / "meta/info.json").read_text())
        for key in CAMERA_MAP:
            if info["features"][key]["shape"] != [480, 640, 3]:
                raise ValueError("Check source dimensions before decoding")
        ds = LeRobotDataset(f"local/{root.name}", root=root, download_videos=False, video_backend="pyav")
        observations[color] = []
        for i in range(args.frames_per_color):
            item = ds[i]
            obs = {k: item[k].clone() for k in (*CAMERA_MAP, "observation.state")}
            obs["task"] = TASKS[color]
            observations[color].append(obs)
        del ds
    events, phases = [], []
    timeline = ActionTimeline()
    worker = AsyncWorker(ModelInference(args, events))
    next_id = 0

    def submit(color, tick, delay=0):
        nonlocal next_id
        frame = tick % args.frames_per_color
        req = ChunkRequest(next_id, timeline.generation, tick, color, frame,
                           time.perf_counter(), observations[color][frame], delay)
        if worker.submit(req):
            next_id += 1
            events.append({"type": "request", "request_id": req.identifier,
                           "generation": req.generation, "color": color, "tick": tick,
                           "frame": frame, "time": req.sent})
            return req
        return None

    def wait_result():
        deadline = time.perf_counter() + 60
        while time.perf_counter() < deadline:
            result = worker.poll()
            if result is not None:
                return result
            time.sleep(0.001)
        raise TimeoutError("Worker did not produce a result")

    def prefill(color):
        started = time.perf_counter()
        submit(color, 0)
        result = wait_result()
        status = timeline.install(result, 0)
        if not status["accepted"]:
            raise RuntimeError(status)
        return time.perf_counter() - started

    def run_phase(name, color, seconds, injected_delay=0):
        ticks, installs, seams = [], [], []
        total, epoch, tick = math.ceil(seconds * 20), time.perf_counter(), 0
        last_action, last_chunk = None, None
        while tick < total:
            target = epoch + tick * 0.05
            time.sleep(max(0, target - time.perf_counter()))
            started = time.perf_counter()
            tick, skipped = aligned_tick(tick, epoch, started)
            if tick >= total:
                break
            target = epoch + tick * 0.05
            if skipped:
                time.sleep(max(0,target-time.perf_counter()))
                started=time.perf_counter()
            result = worker.poll()
            if result is not None:
                status = timeline.install(result, tick)
                installs.append({"tick": tick, "request_id": result.request.identifier, **status})
            before = timeline.remaining(tick)
            action = timeline.pop(tick)
            sent = time.perf_counter()
            record = {"tick": tick, "scheduled": target, "started": started,
                      "action_ready": sent, "lateness_ms": (started-target)*1000,
                      "skipped": skipped, "queue_before": before,
                      "starved": action is None, "generation": timeline.generation}
            if action is not None:
                if action["generation"] != timeline.generation or action["color"] != color:
                    raise RuntimeError("Cross-task action contamination")
                record.update({k: action[k] for k in ("request_id", "request_tick", "chunk_index", "frame")})
                record["observation_age_ms"] = (sent-action["observation_time"])*1000
                if last_action is not None and last_chunk != action["request_id"]:
                    seams.append({"tick": tick, "from_chunk": last_chunk,
                                  "to_chunk": action["request_id"],
                                  "absolute_joint_jump": [abs(a-b) for a,b in zip(action["action"],last_action)]})
                last_action, last_chunk = action["action"], action["request_id"]
            remaining = timeline.remaining(tick+1)
            if remaining <= args.prefetch and not worker.busy:
                submit(color, tick, injected_delay)
            record["queue_after"] = remaining
            record["cpu_work_ms"] = (time.perf_counter()-started)*1000
            ticks.append(record)
            tick += 1
        time.sleep(max(0, epoch + seconds-time.perf_counter()))
        elapsed = time.perf_counter()-epoch
        if worker.busy:
            result = wait_result()
            installs.append({"tick": total, "request_id": result.request.identifier,
                             **timeline.install(result,total)})
        intervals = successful_intervals(ticks)
        successes = sum(not r["starved"] for r in ticks)
        report = {"name": name, "color": color, "seconds": seconds,
                  "elapsed_seconds": elapsed, "actual_action_hz": successes/elapsed,
                  "control_tick_hz": len(ticks)/elapsed,
                  "ticks": len(ticks), "actions": successes,
                  "distinct_consumed_chunks":len({r['request_id'] for r in ticks if not r['starved']}),
                  "starvation_count": sum(r["starved"] for r in ticks),
                  "skipped_ticks": sum(r["skipped"] for r in ticks),
                  "hold_or_fabricated_actions": 0,
                  "action_intervals": latency_stats(intervals),
                  "scheduler_lateness": latency_stats([r["lateness_ms"] for r in ticks]),
                  "cpu_work": latency_stats([r["cpu_work_ms"] for r in ticks]),
                  "observation_age": latency_stats([r["observation_age_ms"] for r in ticks if not r["starved"]]),
                  "queue_min": min(r["queue_after"] for r in ticks),
                  "queue_max": max(r["queue_after"] for r in ticks),
                  "installs": installs, "seams": seams}
        report["meets_preregistered_offline_budget"] = (
            report["starvation_count"] == report["skipped_ticks"] == 0
            and 19.8 <= report["actual_action_hz"] <= 20.2
            and report["action_intervals"]["p99_ms"] <= 60
            and report["action_intervals"]["max_ms"] <= 75
            and report["cpu_work"]["max_ms"] <= 50)
        (args.output/(name+'-ticks.json')).write_text(json.dumps(ticks,indent=2)+'\n')
        write_csv(args.output/(name+'-ticks.csv'),ticks)
        phases.append(report)
        print(name,json.dumps({k:report[k] for k in ('actual_action_hz','starvation_count','skipped_ticks','meets_preregistered_offline_budget')}),flush=True)

    try:
        cold_start = prefill("green")
        print(f"prefilled after {cold_start:.2f}s",flush=True)
        run_phase("steady-green", "green", args.seconds)
        # Force a genuine model computation to remain in flight across reset.
        old = submit("green", math.ceil(args.seconds*20), 0.05)
        if old is None or not worker.started.wait(5):
            raise RuntimeError("Could not force in-flight task switch")
        start_deadline = time.perf_counter() + 5
        while not any(e['type']=='inference_started' and e['request_id']==old.identifier for e in events):
            if time.perf_counter() > start_deadline:
                raise TimeoutError("Model inference never started before switch")
            time.sleep(0.001)
        switch_time = time.perf_counter()
        timeline.reset()
        stale = wait_result()
        if not stale.inference_start < switch_time < stale.inference_end <= stale.ready:
            raise RuntimeError("Task switch did not actually occur during model computation")
        stale_status = timeline.install(stale,0)
        if stale_status.get("reason") != "stale_generation":
            raise RuntimeError("Old task result was not rejected")
        switch_prefill = prefill("red")
        switch_pause_seconds = time.perf_counter()-switch_time
        run_phase("after-switch-red", "red", 10)
        timeline.reset()
        stress_prefill = prefill("red")
        run_phase("injected-delay-stress", "red", 8, injected_delay=0.8)
        inference = [r for r in events if r["type"] == "inference"]
        report = {
            "passed_execution": True, "precision": "float32", "fps":20,
            "scheduler_start_lateness_grace_ms":5,
            "prefetch_remaining_steps":args.prefetch, "chunk_size":50,
            "warmup_chunks":args.warmup, "cold_prefill_seconds":cold_start,
            "task_switch": {"old_request_id": old.identifier, "result":stale_status,
                            "new_generation":1,"new_prefill_seconds":switch_prefill,
                            "switch_time":switch_time,"old_inference_start":stale.inference_start,
                            "old_inference_end":stale.inference_end,"old_result_ready":stale.ready,
                            "pause_until_new_prefill_seconds":switch_pause_seconds,
                            "old_actions_consumed":0},
            "stress_prefill_seconds":stress_prefill,
            "inference_count":len(inference),
            "inference_compute_ms":latency_stats([(r['end']-r['start'])*1000 for r in inference]),
            "phases":phases,
            "policy":str(args.policy.resolve()),"vlm":str(args.vlm.resolve()),
            "camera_map":CAMERA_MAP,"camera3":"omitted; empty_cameras=0",
            "source_frames":{c:list(range(args.frames_per_color)) for c in TASKS},
            "observation_replay":"CPU-cached recorded consecutive frames, cyclic by control tick; no closed-loop feedback",
            "action_units":"base native output units; not validated SO101 joint commands",
            "rtc_validated":False,"robot_motion":False,
            "camera_serial_recording_included":False,
            "code_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "command":__import__('sys').argv,
        }
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    finally:
        worker.close()
        (args.output/'events.json').write_text(json.dumps(events,indent=2)+'\n')
        write_csv(args.output/'events.csv',events)


if __name__ == '__main__':
    main()
