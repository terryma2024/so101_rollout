import numpy as np
import pytest

from so101_test.voice.voice_runner import ARM_KEYS, IDLE, KEYS, RETURNING, RUNNING, DoneDetector, VoiceRunner

REST = dict(zip(KEYS, [0.0, -104.0, 90.0, 75.0, 5.0, 2.0]))


def state(**over):
    s = dict(REST)
    s.update(over)
    return s


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def tick(self, dt=0.05):
        self.t += dt


class FakeRobot:
    def __init__(self, clock, start=None):
        self.clock, self.pos, self.sent = clock, dict(start or REST), []
        self.fail_obs = False

    def get_observation(self):
        if self.fail_obs:
            raise RuntimeError("bus error")
        return {**self.pos, "wrist": np.zeros((2, 2, 3), np.uint8)}

    def send_action(self, action):
        self.sent.append(dict(action))
        self.pos.update(action)
        return action


class FakePolicy:
    """Plays a gripper trajectory (open, grasp, release) and ends at rest; counts resets."""

    def __init__(self, script=None, fail_at=None):
        self.script, self.i, self.resets, self.fail_at = script, 0, 0, fail_at

    def reset(self):
        self.resets += 1
        self.i = 0

    def act(self, obs):
        if self.fail_at is not None and self.i == self.fail_at:
            raise RuntimeError("policy blew up")
        a = dict(REST) if self.script is None else dict(self.script(self.i))
        self.i += 1
        return a


def good_trajectory(i):
    """20 Hz ticks: 0-9 rest, 10-29 open+reach, 30-49 grasp, 50-69 release, 70+ back at rest."""
    s = dict(REST)
    if 10 <= i < 30:
        s.update({"gripper.pos": 20.0, "shoulder_pan.pos": 30.0, "elbow_flex.pos": 50.0})
    elif 30 <= i < 50:
        s.update({"gripper.pos": 11.0, "shoulder_pan.pos": 30.0, "elbow_flex.pos": 50.0})
    elif 50 <= i < 70:
        s.update({"gripper.pos": 18.0, "shoulder_pan.pos": -30.0, "elbow_flex.pos": 50.0})
    return s


def make(policy_red=None, policy_green=None, **kw):
    clock = FakeClock()
    robot = FakeRobot(clock)
    msgs, events = [], []
    policies = {"red": policy_red or FakePolicy(), "green": policy_green or FakePolicy()}
    tasks = {"red": "Put the red cube into the paper bowl", "green": "Put the green cube into the paper bowl"}
    runner = VoiceRunner(robot, policies, tasks, REST, clock=clock, say=msgs.append, event=events.append, **kw)
    return runner, robot, clock, msgs, events


def tick(runner, clock, n=1):
    for _ in range(n):
        runner.step()
        clock.tick()


# ---------------- DoneDetector ----------------

def traj(det, frames, dt=0.05):
    """frames: list of states; returns the index at which det first says done, or None."""
    for i, s in enumerate(frames):
        if det.update(i * dt, s):
            return i
    return None


def test_done_after_grasp_release_and_rest_hold():
    frames = [good_trajectory(i) for i in range(70)]
    frames += [state()] * 40
    det = DoneDetector(REST)
    i = traj(det, frames)
    assert i is not None and i >= 70 + 19          # needs 1 s (20 ticks) at rest after the release
    assert i <= 70 + 21


def test_not_done_without_release():
    frames = [good_trajectory(i) for i in range(50)] + [state(**{"gripper.pos": 11.0})] * 100
    assert traj(DoneDetector(REST), frames) is None


def test_not_done_when_gripper_never_grasps():
    frames = [state(**{"gripper.pos": 20.0})] * 30 + [state()] * 100
    assert traj(DoneDetector(REST), frames) is None


def test_hold_timer_resets_when_arm_leaves_rest():
    base = [good_trajectory(i) for i in range(70)]
    wobble = [state()] * 10 + [state(shoulder_pan=25.0)] + [state()] * 10 + [state(shoulder_pan=25.0)] + [state()] * 10
    wobble = [dict(w) for w in wobble]
    for w in wobble:
        if "shoulder_pan" in w:
            w["shoulder_pan.pos"] = w.pop("shoulder_pan")
    assert traj(DoneDetector(REST), base + wobble) is None


def test_within_tolerance_counts_as_rest():
    near = state(**{"shoulder_pan.pos": 9.0, "wrist_roll.pos": 5.0 + 9.0})
    frames = [good_trajectory(i) for i in range(70)] + [near] * 40
    assert traj(DoneDetector(REST), frames) is not None
    far = state(**{"shoulder_pan.pos": 11.0})
    frames = [good_trajectory(i) for i in range(70)] + [far] * 40
    assert traj(DoneDetector(REST), frames) is None


def test_gripper_does_not_count_for_rest_distance():
    frames = [good_trajectory(i) for i in range(70)] + [state(**{"gripper.pos": 16.0})] * 40
    assert traj(DoneDetector(REST), frames) is not None


# ---------------- state machine ----------------

def test_run_resets_policy_and_sends_actions():
    runner, robot, clock, msgs, events = make()
    runner.submit("run", "green")
    tick(runner, clock, 3)
    assert runner.state == RUNNING
    assert runner.policies["green"].resets == 1 and runner.policies["red"].resets == 0
    assert len(robot.sent) == 3
    assert any("Put the green cube into the paper bowl" in m for m in msgs)
    assert events[0]["event"] == "run_start" and events[0]["colour"] == "green"


def test_stop_returns_to_rest_in_two_seconds_then_idle():
    pol = FakePolicy(lambda i: {**REST, "shoulder_pan.pos": 40.0})
    runner, robot, clock, msgs, events = make(policy_red=pol)
    runner.submit("run", "red")
    tick(runner, clock, 5)
    robot.pos["shoulder_pan.pos"] = 40.0
    runner.submit("stop")
    tick(runner, clock, 1)
    assert runner.state == RETURNING and runner.last_reason == "stop"
    sent_before = len(robot.sent)
    tick(runner, clock, 19)
    assert runner.state == RETURNING
    mid = robot.sent[sent_before + 9]["shoulder_pan.pos"]
    assert 5 < mid < 35                              # interpolating, not jumping
    tick(runner, clock, 25)                          # 2 s = 40 ticks at 20 Hz in total
    assert runner.state == IDLE
    assert robot.sent[-1]["shoulder_pan.pos"] == pytest.approx(REST["shoulder_pan.pos"])
    assert robot.sent[-1]["gripper.pos"] == pytest.approx(REST["gripper.pos"])
    assert [e["event"] for e in events][-2:] == ["run_end", "returned"]


def test_timeout():
    runner, robot, clock, msgs, events = make(timeout_s=30.0)
    runner.submit("run", "red")
    for _ in range(700):
        tick(runner, clock)
        if runner.state != RUNNING:
            break
    assert runner.last_reason == "timeout"
    assert 29.5 <= events[1]["elapsed_s"] <= 30.5


def test_done_ends_run_and_returns():
    runner, robot, clock, msgs, events = make(policy_green=FakePolicy(good_trajectory))
    runner.submit("run", "green")
    for _ in range(200):
        tick(runner, clock)
        if runner.state != RUNNING:
            break
    assert runner.last_reason == "done"
    tick(runner, clock, 60)
    assert runner.state == IDLE


def test_new_colour_while_running_is_refused_and_does_not_interrupt():
    runner, robot, clock, msgs, events = make()
    runner.submit("run", "green")
    tick(runner, clock, 3)
    runner.submit("run", "red")
    tick(runner, clock, 2)
    assert runner.state == RUNNING
    assert runner.policies["red"].resets == 0
    assert any("绿色" in m and "忽略" in m for m in msgs)
    assert {"event": "refused", "colour": "red", "state": RUNNING} in events


def test_new_colour_while_returning_is_refused():
    runner, robot, clock, msgs, events = make()
    runner.submit("run", "green")
    tick(runner, clock, 2)
    runner.submit("stop")
    tick(runner, clock, 2)
    assert runner.state == RETURNING
    runner.submit("run", "red")
    tick(runner, clock, 1)
    assert runner.state == RETURNING and runner.policies["red"].resets == 0


def test_second_run_after_idle_switches_policy_without_reload():
    runner, robot, clock, msgs, events = make()
    runner.submit("run", "green")
    tick(runner, clock, 2)
    runner.submit("stop")
    tick(runner, clock, 60)
    assert runner.state == IDLE
    runner.submit("run", "red")
    tick(runner, clock, 2)
    assert runner.state == RUNNING and runner.policies["red"].resets == 1


def test_stop_when_idle_is_harmless():
    runner, robot, clock, msgs, events = make()
    runner.submit("stop")
    tick(runner, clock, 2)
    assert runner.state == IDLE and robot.sent == []
    assert any("没有在执行" in m for m in msgs)


def test_home_from_idle_moves_to_rest():
    runner, robot, clock, msgs, events = make()
    robot.pos["shoulder_pan.pos"] = 30.0
    runner.submit("home")
    tick(runner, clock, 45)
    assert runner.state == IDLE
    assert robot.pos["shoulder_pan.pos"] == pytest.approx(REST["shoulder_pan.pos"])


def test_policy_error_ends_run_and_returns():
    runner, robot, clock, msgs, events = make(policy_red=FakePolicy(fail_at=3))
    runner.submit("run", "red")
    tick(runner, clock, 6)
    assert runner.last_reason == "error" and runner.state in (RETURNING, IDLE)
    tick(runner, clock, 60)
    assert runner.state == IDLE


def test_robot_read_failure_during_return_does_not_crash():
    runner, robot, clock, msgs, events = make()
    runner.submit("run", "red")
    tick(runner, clock, 2)
    robot.fail_obs = True
    runner.submit("stop")
    tick(runner, clock, 1)
    assert runner.state in (RETURNING, IDLE)


def test_quit_while_running_stops_returns_then_finishes():
    runner, robot, clock, msgs, events = make()
    runner.submit("run", "red")
    tick(runner, clock, 3)
    runner.submit("quit")
    for _ in range(80):
        tick(runner, clock)
        if runner.finished:
            break
    assert runner.finished and runner.last_reason == "quit" and runner.state == IDLE


def test_quit_when_idle_finishes_immediately():
    runner, robot, clock, msgs, events = make()
    runner.submit("quit")
    tick(runner, clock, 1)
    assert runner.finished


def test_quit_blocks_new_runs():
    runner, robot, clock, msgs, events = make()
    runner.submit("quit")
    runner.submit("run", "red")
    tick(runner, clock, 2)
    assert runner.policies["red"].resets == 0


def test_recorder_gets_task_frames_and_save_flag():
    class Rec:
        def __init__(self):
            self.log = []

        def begin(self, task):
            self.log.append(("begin", task))

        def add(self, obs, action):
            self.log.append("add")

        def end(self, save):
            self.log.append(("end", save))

    rec = Rec()
    runner, robot, clock, msgs, events = make(recorder=rec)
    runner.submit("run", "red")
    tick(runner, clock, 4)
    runner.submit("stop")
    tick(runner, clock, 1)
    assert rec.log[0] == ("begin", "Put the red cube into the paper bowl")
    assert rec.log.count("add") == 4
    assert rec.log[-1] == ("end", True)


def test_on_run_start_hook_called_with_colour():
    seen = []
    runner, robot, clock, msgs, events = make(on_run_start=seen.append)
    runner.submit("run", "green")
    tick(runner, clock, 1)
    assert seen == ["green"]


def test_run_stats_have_latency_percentiles():
    runner, robot, clock, msgs, events = make()
    runner.submit("run", "red")
    tick(runner, clock, 10)
    runner.submit("stop")
    tick(runner, clock, 1)
    assert "infer_p50_ms" in runner.last_stats and runner.last_stats["ticks"] == 10


def test_new_run_refused_while_recorder_is_still_saving():
    class BusyRec:
        busy = True

        def begin(self, task):
            raise AssertionError("must not start")

        def add(self, obs, action):
            pass

        def end(self, save):
            pass

    runner, robot, clock, msgs, events = make(recorder=BusyRec())
    runner.submit("run", "red")
    tick(runner, clock, 2)
    assert runner.state == IDLE and runner.policies["red"].resets == 0
    assert any("保存" in m for m in msgs)


def test_arm_keys_are_five_and_exclude_gripper():
    assert len(ARM_KEYS) == 5 and "gripper.pos" not in ARM_KEYS


def test_is_settled_not_fooled_by_a_dequeued_run_command():
    runner, robot, clock, msgs, events = make()
    assert runner.is_settled()
    runner.submit("run", "red")
    # queue still holds the command: old check "queue empty and IDLE" is false, settled must be false too
    assert not runner.is_settled()
    # simulate the dequeue-but-not-yet-handled window: queue is empty, state still IDLE, handling not done
    kind, colour, *extra = runner._cmds.get_nowait()
    assert runner._cmds.empty() and runner.state == IDLE
    assert not runner.is_settled()
    runner._handle(kind, colour, *extra)
    with runner._count_lock:
        runner._processed += 1
    assert runner.state == RUNNING and not runner.is_settled()
    runner.submit("stop")
    tick(runner, clock, 1)
    assert runner.state == RETURNING and not runner.is_settled()
    tick(runner, clock, 60)
    assert runner.state == IDLE and runner.is_settled()


def test_is_settled_counts_refused_and_ignored_commands():
    runner, robot, clock, msgs, events = make()
    runner.submit("stop")                 # nothing running: handled with a message
    tick(runner, clock, 1)
    assert runner.is_settled()
