"""语音 agent 的控制状态机：idle -> running(颜色) -> returning -> idle。

不依赖 lerobot：机器人、策略、时钟、记录器都是鸭子类型，测试用假对象。
  robot:    get_observation() -> dict（"<关节>.pos" 浮点 + 相机图像），send_action(dict)
  policy:   reset()，act(obs) -> {"<关节>.pos": float}（策略对象见 voice_policy.py）
  recorder: begin(task) / add(obs, action) / end(save: bool) / close()（可选，见 voice_policy.EpisodeRecorder）
结束一次执行的原因（先到先算）：stop（语音/键盘"停"）、home、quit、timeout（默认 30 s）、done（完成判定）、error。
结束后用 return_s（默认 2 s）线性插值回休息位，期间忽略新指令。
"""
import collections
import queue
import threading
import time

JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
KEYS = tuple(f"{j}.pos" for j in JOINTS)
ARM_KEYS = KEYS[:5]
GRIPPER_KEY = "gripper.pos"

IDLE, RUNNING, RETURNING = "idle", "running", "returning"
COLOUR_ZH = {"red": "红色", "green": "绿色"}


class DoneDetector:
    """完成判定：夹爪 张开 -> 抓住（合到 closed_thr 以下，方块撑着所以不会是 0）-> 再张开（放下），
    之后 5 个手臂关节都在休息位 tol 度以内并保持 hold_s 秒。

    阈值依据演示数据：张开 15-26，抓着方块 10-12，休息位约 2。夹爪不参与"回到休息位"的距离判断。
    """

    def __init__(self, rest, tol=10.0, hold_s=1.0, open_thr=14.0, closed_thr=13.0):
        self.rest, self.tol, self.hold_s = rest, tol, hold_s
        self.open_thr, self.closed_thr = open_thr, closed_thr
        self.phase = 0              # 0 等第一次张开, 1 等抓住, 2 等放下（再张开）, 3 等回到休息位
        self._near_since = None

    def near_rest(self, state):
        return all(abs(state[k] - self.rest[k]) <= self.tol for k in ARM_KEYS)

    def update(self, t, state):
        g = state[GRIPPER_KEY]
        if self.phase == 0 and g >= self.open_thr:
            self.phase = 1
        elif self.phase == 1 and g <= self.closed_thr:
            self.phase = 2
        elif self.phase == 2 and g >= self.open_thr:
            self.phase = 3
        if self.phase < 3:
            return False
        if self.near_rest(state):
            if self._near_since is None:
                self._near_since = t
            return t - self._near_since >= self.hold_s
        self._near_since = None
        return False


class RunStats:
    def __init__(self):
        self.latencies = []
        self.overruns = 0
        self.ticks = 0

    def summary(self):
        if not self.latencies:
            return {"ticks": self.ticks}
        s = sorted(self.latencies)
        pick = lambda q: s[min(len(s) - 1, int(q * len(s)))] * 1000  # noqa: E731
        return {"ticks": self.ticks, "infer_p50_ms": round(pick(0.5), 2), "infer_p99_ms": round(pick(0.99), 2),
                "infer_max_ms": round(s[-1] * 1000, 2), "overruns": self.overruns}


class VoiceRunner:
    def __init__(self, robot, policies, tasks, rest, fps=20, timeout_s=30.0, return_s=2.0, done_tol=10.0,
                 done_hold_s=1.0, clock=time.perf_counter, say=print, event=None, recorder=None, on_run_start=None,
                 chain=None):
        self.robot, self.policies, self.tasks, self.rest = robot, policies, tasks, dict(rest)
        self.period = 1.0 / fps
        self.timeout_s, self.return_s = timeout_s, return_s
        self.done_tol, self.done_hold_s = done_tol, done_hold_s
        self.clock, self.say = clock, say
        self.event = event or (lambda e: None)
        self.recorder, self.on_run_start = recorder, on_run_start
        self.chain = chain          # optional voice_verify.VerifyChain (--verify)
        if chain is not None:
            chain.attach(self)
        self.state = IDLE
        self.finished = False
        self.last_reason = None
        self.last_stats = None
        self._cmds = queue.Queue()
        self._count_lock = threading.Lock()
        self._submitted = 0
        self._processed = 0
        self._quit = False
        self._colour = None
        self._start = 0.0
        self._detector = None
        self._stats = None
        self._ret_t0 = 0.0
        self._ret_from = None
        self._last_obs = None
        self.history = collections.deque(maxlen=50)

    # --- thread-safe entry points -------------------------------------------------
    def submit(self, kind, colour=None, token=None):
        """kind: run (colour) | stop | home | quit。可在任意线程调用。

        token 只给 --verify 的自动重试用（链的 epoch，过期就忽略）。停/回去/退出在调用线程里立刻取消整条重试链，
        不用等下一个控制拍，所以验证答案和随后的自动重试都来不及插进去。"""
        cancelled = False
        if self.chain is not None and kind in ("stop", "home", "quit"):
            cancelled = self.chain.cancel(kind)
        with self._count_lock:
            self._submitted += 1
        self._cmds.put((kind, colour, token, cancelled))

    def is_settled(self):
        """True when every submitted command has been fully handled and the runner is idle.

        Unlike "queue empty and state == IDLE", this is not fooled by a command that was already dequeued but
        has not changed the state yet (a "run" popped from the queue while state is still IDLE).
        """
        with self._count_lock:
            done = self._submitted == self._processed
        return done and self.state == IDLE and (self.chain is None or not self.chain.active)

    # --- state machine --------------------------------------------------------------
    def step(self):
        """One control tick (call at fps Hz)."""
        self._drain()
        if self.state == RUNNING:
            self._run_tick()
        elif self.state == RETURNING:
            self._return_tick()
        elif self._quit:
            self.finished = True

    def run_forever(self, sleep=time.sleep):
        while not self.finished:
            t0 = self.clock()
            self.step()
            dt = self.clock() - t0
            if self.state == RUNNING and self._stats is not None and dt > 1.5 * self.period:
                self._stats.overruns += 1
            sleep(max(self.period - dt, 0.0))

    def _drain(self):
        while True:
            try:
                kind, colour, token, cancelled = self._cmds.get_nowait()
            except queue.Empty:
                return
            try:
                self._handle(kind, colour, token, cancelled)
            finally:
                with self._count_lock:
                    self._processed += 1

    def _handle(self, kind, colour, token=None, cancelled=False):
        if kind == "quit":
            self._quit = True
            if self.state == RUNNING:
                self._end_run("quit")
            return
        if kind == "stop":
            if self.state == RUNNING:
                self._end_run("stop")
            elif self.state == IDLE and not cancelled:
                self.say("当前没有在执行")
            return
        if kind == "home":
            if self.state == RUNNING:
                self._end_run("home")
            elif self.state == IDLE:
                self._begin_return()
            return
        if kind == "run":
            auto = token is not None
            if auto and not (self.chain is not None and self.chain.accepts(token)):
                return              # a retry that a stop / home / quit already voided
            if self.state != IDLE:
                if auto:
                    self.chain.finish("busy", "自动重试时机器人不空闲，不再重试。")
                what = "复位中" if self.state == RETURNING else f"正在执行{COLOUR_ZH.get(self._colour, self._colour)}"
                self.say(f"{what}，忽略新的颜色指令；要打断请说“停”")
                self.event({"event": "refused", "colour": colour, "state": self.state})
                return
            if not auto and self.chain is not None and self.chain.active:
                self.say("验证重试中，忽略新的颜色指令；要打断请说“停”")
                self.event({"event": "refused", "colour": colour, "state": "verify_chain"})
                return
            if self._quit:
                return
            if self.recorder is not None and getattr(self.recorder, "busy", False):
                if auto:
                    self.chain.finish("recorder_busy", "评估数据还没保存完，不再自动重试。")
                self.say("正在保存上一条评估数据，请稍后再说")
                self.event({"event": "refused", "colour": colour, "state": "saving"})
                return
            self._begin_run(colour, auto)

    def _begin_run(self, colour, auto=False):
        policy = self.policies.get(colour)
        if policy is None:
            self.say(f"没有加载 {colour} 的策略")
            if auto:
                self.chain.finish("no_policy", "没有这个颜色的策略，不再重试。")
            return
        attempt = None
        if self.chain is not None:
            if auto:
                attempt = self.chain.begin_auto_run()
            else:
                self.chain.begin_user_run(colour)
                attempt = 1
        policy.reset()
        if self.on_run_start:
            self.on_run_start(colour)
        self._colour = colour
        self._detector = DoneDetector(self.rest, self.done_tol, self.done_hold_s)
        self._stats = RunStats()
        self._start = self.clock()
        self.state = RUNNING
        if self.recorder:
            self.recorder.begin(self.tasks[colour])
        self.say(f"开始执行：{COLOUR_ZH.get(colour, colour)}（任务：{self.tasks[colour]}）"
                 + (f"，第 {attempt} 次" if attempt is not None and attempt > 1 else ""))
        ev = {"event": "run_start", "colour": colour, "task": self.tasks[colour]}
        if attempt is not None:
            ev["attempt"] = attempt
        self.event(ev)

    def _run_tick(self):
        now = self.clock()
        elapsed = now - self._start
        if elapsed >= self.timeout_s:
            self._end_run("timeout")
            return
        try:
            obs = self.robot.get_observation()
            self._last_obs = obs
            t0 = self.clock()
            action = self.policies[self._colour].act(obs)
            self._stats.latencies.append(self.clock() - t0)
            self.robot.send_action(action)
            if self.recorder:
                self.recorder.add(obs, action)
            self._stats.ticks += 1
            done = self._detector.update(elapsed, obs)
        except Exception as error:  # noqa: BLE001 - any failure must lead to a safe return, not a crash
            self.say(f"执行出错：{error!r}")
            self._end_run("error", error=repr(error))
            return
        if done:
            self._end_run("done")

    def _end_run(self, reason, error=None):
        elapsed = self.clock() - self._start
        stats = self._stats.summary() if self._stats else {}
        self.last_reason, self.last_stats = reason, stats
        if self.recorder:
            try:
                self.recorder.end(save=reason != "error")
            except Exception as err:  # noqa: BLE001
                self.say(f"保存评估数据出错：{err!r}")
        text = {"stop": "已停止", "home": "已中止", "quit": "退出，已中止", "timeout": f"超时 {self.timeout_s:.0f} 秒",
                "done": "完成", "error": "出错"}[reason]
        self.say(f"结束（{text}），用时 {elapsed:.1f} 秒，推理 p50/p99 = {stats.get('infer_p50_ms', '-')}/"
                 f"{stats.get('infer_p99_ms', '-')} ms；回休息位")
        ev = {"event": "run_end", "colour": self._colour, "reason": reason, "elapsed_s": round(elapsed, 2), **stats}
        if error:
            ev["error"] = error
        self.history.append(ev)
        self.event(ev)
        if self.chain is not None:
            self.chain.on_run_end(reason)
        self._begin_return()

    def _begin_return(self):
        try:
            obs = self.robot.get_observation()
            self._last_obs = obs
        except Exception as error:  # noqa: BLE001
            self.say(f"读取当前位置失败：{error!r}；用上一次的位置开始复位")
            obs = self._last_obs
        if obs is None:
            self.state = IDLE
            return
        self._ret_from = {k: obs[k] for k in KEYS}
        self._ret_t0 = self.clock()
        self.state = RETURNING

    def _return_tick(self):
        frac = 1.0 if self.return_s <= 0 else min((self.clock() - self._ret_t0) / self.return_s, 1.0)
        target = {k: self._ret_from[k] * (1 - frac) + self.rest[k] * frac for k in KEYS}
        try:
            self.robot.send_action(target)
        except Exception as error:  # noqa: BLE001
            self.say(f"复位出错：{error!r}")
            frac = 1.0
        if frac >= 1.0:
            self.state = IDLE
            self.event({"event": "returned"})
            self.say("已回到休息位，等待指令（红色 / 绿色 / 停 / q 退出）")
            if self._quit:
                self.finished = True
            elif self.chain is not None and self.chain.active:
                self.chain.on_rested(self._fresh_obs())

    def _fresh_obs(self):
        """Latest observation at rest (for the verification frame); falls back to the last one we have."""
        try:
            self._last_obs = self.robot.get_observation()
        except Exception as error:  # noqa: BLE001
            self.say(f"读取验证画面失败：{error!r}；用上一帧")
        return self._last_obs
