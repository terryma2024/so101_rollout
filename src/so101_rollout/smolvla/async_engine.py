"""Asynchronous chunk scheduling with an episode barrier and CPU-only control path.

Only the worker calls model/processor/CUDA APIs. The scheduler itself is stdlib
only so reset, queue expiry, and concurrency can be tested without robot I/O.
"""
from __future__ import annotations

from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass
import json
import math
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
import time


@dataclass(frozen=True)
class Request:
    identifier: int
    generation: int
    tick: int
    observed_at: float
    observation: dict
    task: str | None = None


class AsyncChunkScheduler:
    """One worker, one in-flight chunk, and actions indexed by intended tick.

    Main-thread lifecycle/get_action calls must be serialized, as they are in
    LeRobot's episodic strategy. Reset invalidates output immediately without
    touching worker-owned model state; the next request resets that state on
    the worker. Startup waits for a fresh first chunk before starting its clock.
    After startup, queue starvation emits no command and never replays a hold.
    """

    def __init__(self, infer, *, fps=20, horizon=50, prefetch=10,
                 clock=time.perf_counter, telemetry_path=None,
                 startup_timeout_s=30.0, starvation_timeout_s=0.5, task=None, recorder=None):
        if fps <= 0 or not 1 <= prefetch < horizon:
            raise ValueError('Require fps>0 and 1 <= prefetch < horizon')
        if startup_timeout_s <= 0 or starvation_timeout_s <= 0:
            raise ValueError('Inference timeouts must be positive')
        self.infer, self.period, self.horizon = infer, 1 / fps, horizon
        self.prefetch, self.clock = prefetch, clock
        self.task = task
        self.recorder = recorder
        self.telemetry_path = Path(telemetry_path) if telemetry_path else None
        self.startup_timeout_s = startup_timeout_s
        self.starvation_timeout_s = starvation_timeout_s
        self.generation = 0
        self._next_id = 0
        self._queue = {}
        self._epoch = None
        self._next_tick = 0
        self._active = False
        self._failure = None
        self._future = None
        self._request = None
        self._thread = None
        self._stop = Event()
        self._requests = Queue(maxsize=1)
        self._waiting_since = None
        self._starved_since = None
        self.events = []
        self.stats = dict(actions=0, chunks=0, stale_results=0, starved_ticks=0,
                          startup_wait_ticks=0, skipped_ticks=0, expired_prefix_actions=0)

    def _record(self, kind, **metadata):
        if self.recorder is not None:
            try:
                self.recorder.submit(kind, metadata)
            except Exception as exc:
                self.recorder.error(exc)

    @property
    def result_ready(self):
        return self._future is not None and self._future.done()

    @property
    def ready(self):
        return True

    @property
    def failed(self):
        return self._failure is not None

    def start(self):
        if self._thread is not None:
            raise RuntimeError('Inference engine already started')
        self._stop.clear()
        self._thread = Thread(target=self._run, name='SO101-SmolVLA-async', daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                req, future = self._requests.get(timeout=0.05)
            except Empty:
                continue
            if not future.set_running_or_notify_cancel():
                continue
            try:
                begin = self.clock()
                actions = self.infer(req)
                end = self.clock()
                future.set_result((actions, begin, end))
            except BaseException as exc:
                future.set_exception(exc)

    def reset(self, task=None):
        self.generation += 1
        self._queue.clear()
        self._epoch = None
        self._next_tick = 0
        self._waiting_since = self._starved_since = None
        if task is not None:
            self.task = task
        self.events.append(dict(type='reset', generation=self.generation, time=self.clock()))
        self._record('reset', generation=self.generation, task=self.task, time=self.clock())

    def pause(self):
        self._active = False
        # Also invalidate in-flight work and observations when entering reset.
        self.reset()

    def resume(self):
        self._active = True

    def _fail(self, exc):
        self._failure = RuntimeError(f'Asynchronous SmolVLA inference failed: {exc}')
        self._queue.clear()
        self._active = False
        self._record('failure', generation=self.generation, time=self.clock(), error=str(self._failure))
        raise self._failure from exc

    def _collect(self, tick):
        if not self.result_ready:
            return
        future, req = self._future, self._request
        self._future = self._request = None
        if req.generation != self.generation:
            # Consume any exception as well; an invalidated episode cannot
            # publish a chunk or poison the next episode's model state.
            self.stats['stale_results'] += 1
            self._record('stale', request_id=req.identifier, generation=req.generation, time=self.clock())
            self.events.append(dict(type='stale_result', request_id=req.identifier,
                                    generation=req.generation, time=self.clock(),
                                    error=str(future.exception()) if future.exception() else None))
            return
        try:
            actions, begin, end = future.result()
            if len(actions) != self.horizon or not actions:
                raise ValueError('Unexpected action chunk length')
            width = len(actions[0])
            if width == 0 or any(len(row) != width or any(not math.isfinite(v) for v in row) for row in actions):
                raise ValueError('Nonfinite or malformed action chunk')
        except BaseException as exc:
            self._fail(exc)
        trimmed = max(0, tick - req.tick) if self._epoch is not None else 0
        self.stats['chunks'] += 1
        self.stats['expired_prefix_actions'] += min(trimmed, self.horizon)
        self.events.append(dict(type='chunk', request_id=req.identifier, generation=req.generation,
                                task=req.task,
                                request_tick=req.tick, observed_at=req.observed_at,
                                inference_start=begin, inference_end=end, installed_at=self.clock(),
                                installed_tick=tick, trimmed=trimmed))
        if self.recorder is not None:
            self._record('install', request_id=req.identifier, generation=req.generation,
                         task=req.task, tick=tick, request_tick=req.tick, trimmed=trimmed,
                         observed_at=req.observed_at, inference_start=begin, inference_end=end,
                         installed_at=self.clock(),
                         old_future={k:v for k,v in self._queue.items() if k>=tick},
                         new_future={req.tick+i:actions[i] for i in range(trimmed,self.horizon)},
                         replaced=trimmed<self.horizon)
        if trimmed < self.horizon:
            # A ready prediction replaces future commands; an in-flight one
            # leaves the old commands intact. No blending/trajectory filtering.
            self._queue = {req.tick + i: actions[i] for i in range(trimmed, self.horizon)}

    def get_action(self, obs_frame):
        if self.failed:
            raise self._failure
        if not self._active:
            return None
        if self._thread is None or self._stop.is_set():
            raise RuntimeError('Inference engine is not running')
        now = self.clock()
        if self._epoch is None and obs_frame is not None and self._waiting_since is None:
            # Include waiting for an invalidated but still-running request.
            self._waiting_since = now
        tick = self._next_tick
        if self._epoch is not None:
            # An overrun must not cause stale actions to be replayed later.
            wall_tick = math.floor((now - self._epoch + 1e-6) / self.period)
            tick = max(tick, wall_tick)
            self.stats['skipped_ticks'] += tick - self._next_tick
        self._collect(tick)
        self._queue = {k: v for k, v in self._queue.items() if k >= tick}
        if obs_frame is not None and self._future is None and len(self._queue) <= self.prefetch:
            req = Request(self._next_id, self.generation, tick, now, deepcopy(obs_frame), self.task)
            self._next_id += 1
            self._future, self._request = Future(), req
            self._requests.put_nowait((req, self._future))
            self._record('request', request_id=req.identifier, generation=req.generation, request_tick=req.tick, observed_at=req.observed_at, task=req.task)
            if self._waiting_since is None:
                self._waiting_since = now
        action = self._queue.pop(tick, None)
        if action is not None:
            if self._epoch is None:
                self._epoch = now
            self._starved_since = None
            self._next_tick = tick + 1
            self.stats['actions'] += 1
            self.events.append(dict(type='action', generation=self.generation, tick=tick, time=now))
            self._record('output', generation=self.generation, tick=tick, time=now, action=action)
        elif self._epoch is None:
            self.stats['startup_wait_ticks'] += 1
            if self._waiting_since is not None and now - self._waiting_since > self.startup_timeout_s:
                self._fail(TimeoutError('first chunk timed out'))
        else:
            self._next_tick = tick + 1
            self.stats['starved_ticks'] += 1
            self._record('starvation', generation=self.generation, tick=tick, time=now)
            self.events.append(dict(type='starvation', generation=self.generation, tick=tick, time=now))
            if self._starved_since is None:
                self._starved_since = now
            elif now - self._starved_since > self.starvation_timeout_s:
                self._fail(TimeoutError('action queue starved'))
        return action

    def stop(self):
        self._active = False
        self.reset()
        self._stop.set()
        try:
            if self._thread is not None:
                self._thread.join(timeout=30)
                if self._thread.is_alive():
                    raise RuntimeError('Inference worker did not stop within 30s')
        finally:
            if self.recorder is not None:
                self._record('stop', generation=self.generation, time=self.clock(), stats=self.stats.copy())
                self.recorder.close()
                self.stats['recording'] = self.recorder.status()
            if self.telemetry_path:
                self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
                self.telemetry_path.write_text(json.dumps(dict(
                    backend='so101_async', period_s=self.period, horizon=self.horizon,
                    prefetch=self.prefetch, stats=self.stats,
                    failed=str(self._failure) if self.failed else None,
                    events=self.events), indent=2) + '\n')


class SmolVLAAsyncEngine(AsyncChunkScheduler):
    """Official rollout backend adapter; keeps all CUDA work on one worker."""

    def __init__(self, *, policy, preprocessor, postprocessor, dataset_features,
                 ordered_action_keys, task, device, robot_wrapper, fps,
                 prefetch=10, telemetry_path=None, recording_path=None, recording_max_items=256,
                 recording_max_bytes=128*1024*1024, **unused):
        import torch
        if policy.config.type != 'smolvla' or policy.config.n_obs_steps != 1:
            raise ValueError('Async backend supports SmolVLA with n_obs_steps=1 only')
        if getattr(policy.config, 'rtc_config', None) is not None:
            raise ValueError('This async backend must not enable RTC guidance')
        self._policy = policy
        self._pre, self._post = preprocessor, postprocessor
        self._device = torch.device(device or 'cpu')
        self._robot_type = robot_wrapper.robot_type
        self._model_generation = None
        self._stream = None
        names = list(dataset_features['action']['names'])
        self._order = [names.index(k) for k in ordered_action_keys]
        recorder = None
        if recording_path:
            from .recording import InferenceRecorder
            recorder = InferenceRecorder(recording_path, max_items=recording_max_items, max_bytes=recording_max_bytes)
        self._recording_manifest_done = False
        super().__init__(self._infer, fps=fps, horizon=policy.config.n_action_steps,
                         prefetch=prefetch, telemetry_path=telemetry_path, task=task, recorder=recorder)

    def _infer(self, req):
        from contextlib import nullcontext
        import torch
        from lerobot.policies.utils import prepare_observation_for_inference
        if self.recorder is not None:
            try:
                from .recording import array_tree
                schema, arrays = array_tree(req.observation, prefix='observation')
                self.recorder.submit('observation', dict(request_id=req.identifier, generation=req.generation, request_tick=req.tick, observed_at=req.observed_at, task=req.task, schema=schema), arrays)
            except Exception as exc:self.recorder.error(exc)
        if self.recorder is not None and not self._recording_manifest_done:
            self._recording_manifest_done = True
            try:
                from .recording import model_manifest
                self.recorder.submit('manifest', model_manifest(self._policy, dict(fps=1/self.period, horizon=self.horizon, prefetch=self.prefetch, device=str(self._device), action_order=self._order, robot_type=self._robot_type, preprocessor=self._pre.get_config(), postprocessor=self._post.get_config())))
            except Exception as exc:self.recorder.error(exc)
        if self._stream is None and self._device.type == 'cuda':
            self._stream = torch.cuda.Stream(device=self._device)
            # Model/normalizer tensors were loaded on the context thread.
            self._stream.wait_stream(torch.cuda.default_stream(self._device))
        stream_context = torch.cuda.stream(self._stream) if self._stream is not None else nullcontext()
        autocast = (torch.autocast(device_type='cuda')
                    if self._device.type == 'cuda' and self._policy.config.use_amp else nullcontext())
        with stream_context, torch.inference_mode(), autocast:
            if self._model_generation != req.generation:
                self._policy.reset()
                self._pre.reset()
                self._post.reset()
                self._model_generation = req.generation
            batch = prepare_observation_for_inference(req.observation, self._device, req.task, self._robot_type)
            model_input = self._pre(batch)
            captured = []
            recorded_input = None
            if self.recorder is not None:
                try:
                    recorded_input = {k:v.clone() if torch.is_tensor(v) else deepcopy(v) for k,v in model_input.items()}
                except Exception as exc:self.recorder.error(exc)
            if self.recorder is not None:
                # Worker-private instance hook delegates to the ORIGINAL method;
                # no new randn, seed, noise argument, or RNG state changes.
                target = self._policy.model
                original = target.sample_noise
                had_override = 'sample_noise' in vars(target)
                def capture_noise(*args, **kwargs):
                    noise = original(*args, **kwargs)
                    captured.append(noise)
                    return noise
                target.sample_noise = capture_noise
                try:
                    chunk = self._policy.predict_action_chunk(model_input)
                finally:
                    if had_override:target.sample_noise = original
                    else:delattr(target, 'sample_noise')
            else:
                chunk = self._policy.predict_action_chunk(model_input)
            actions = self._post(chunk).detach().cpu()
            if self._stream is not None:
                self._stream.synchronize()
            if tuple(actions.shape) != (1, self._policy.config.chunk_size, len(self._order)) or not torch.isfinite(actions).all().item():
                raise ValueError(f'Invalid action chunk shape/values: {tuple(actions.shape)}')
            ordered = actions[0, :self.horizon, self._order].tolist()
            if self.recorder is not None:
                try:
                    from .recording import array_tree
                    if len(captured)!=1:raise ValueError(f'Expected one actual noise sample, got {len(captured)}')
                    schema, arrays = array_tree(dict(model_input=recorded_input, noise=captured[0], raw_actions=actions), prefix='inference')
                    self.recorder.submit('inference', dict(request_id=req.identifier,
                        generation=req.generation, request_tick=req.tick, observed_at=req.observed_at,
                        task=req.task, captured_at=self.clock(), schema=schema,
                        observation_time_semantics='Exact dispatch snapshot. Dataset/camera exposure timestamp only if provided inside observation; host observed_at is not exposure time.'), arrays)
                except Exception as exc:self.recorder.error(exc)
            return ordered

    def get_action(self, obs_frame):
        import torch
        action = super().get_action(obs_frame)
        return torch.tensor(action, dtype=torch.float32) if action is not None else None

    def notify_observation(self, obs):
        # get_action receives the already-built current dataset frame. Keeping
        # no second observation holder also prevents reuse after reset.
        pass
