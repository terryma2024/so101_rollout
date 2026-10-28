import json
import threading
import time

import numpy as np
import pytest

import voice_agent
from voice_runner import IDLE, KEYS, VoiceRunner
from voice_verify import PROMPT, VerifyChain, VerifyResult, VisionVerifier

KEY = "sk-test-SECRET-0123456789"
REST = dict(zip(KEYS, [0.0, -104.0, 90.0, 75.0, 5.0, 2.0]))


# ---------------- VisionVerifier ----------------

class FakeResp:
    def __init__(self, status=200, content=None, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {"choices": [{"message": {"content": content}}]}

    def json(self):
        return self._payload


class FakePost:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def answer(visible=True, in_bowl=False, note="在碗外"):
    return FakeResp(content=json.dumps({"visible": visible, "in_bowl": in_bowl, "note": note}, ensure_ascii=False))


def verify_with(*responses, timeout=15.0):
    post = FakePost(*responses)
    return VisionVerifier(KEY, timeout=timeout, post=post).verify("red", b"\xff\xd8jpeg"), post


def test_parse_ok_in_bowl():
    r, post = verify_with(answer(True, True, "红方块在碗里"))
    assert (r.visible, r.in_bowl, r.note, r.error) == (True, True, "红方块在碗里", None)
    assert r.latency_ms >= 0


def test_parse_visible_not_in_bowl_and_not_visible():
    r, _ = verify_with(answer(True, False))
    assert (r.visible, r.in_bowl, r.error) == (True, False, None)
    r, _ = verify_with(answer(False, False, "不见了"))
    assert (r.visible, r.in_bowl, r.error) == (False, False, None)


def test_request_shape():
    _, post = verify_with(answer(), timeout=7.0)
    call = post.calls[0]
    body = call["json"]
    assert body["model"] == "deepseek-flash" and body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] >= 1500          # flash reasons first; a small budget gives empty content
    assert call["timeout"] == 7.0
    content = body["messages"][0]["content"]
    assert content[0]["type"] == "image_url" and content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert content[1] == {"type": "text", "text": PROMPT.format(colour="红色")}
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"


@pytest.mark.parametrize("resp,reason", [
    (FakeResp(content="not json"), "bad_json"),
    (FakeResp(content=None), "bad_json"),
    (FakeResp(content=""), "bad_json"),
    (FakeResp(content="[1]"), "not_object"),
    (FakeResp(content='{"in_bowl": true, "note": "x"}'), "bad_visible"),
    (FakeResp(content='{"visible": true, "note": "x"}'), "bad_in_bowl"),
    (FakeResp(content='{"visible": "yes", "in_bowl": false}'), "bad_visible"),
    (FakeResp(content='{"visible": true, "in_bowl": 1}'), "bad_in_bowl"),
    (FakeResp(content='{"visible": true, "in_bowl": false, "note": 5}'), "bad_note"),
    (FakeResp(content='{"visible": false, "in_bowl": true}'), "inconsistent"),
    (FakeResp(payload={"choices": []}), "bad_response"),
    (FakeResp(payload={"oops": 1}), "bad_response"),
    (FakeResp(status=500), "http_500"),
    (FakeResp(status=401), "http_401"),
])
def test_bad_answers_are_errors(resp, reason):
    r, _ = verify_with(resp)
    assert r.error == reason and r.visible is None and r.in_bowl is None


class Timeout(Exception):
    pass


def test_timeout_and_connection_errors_report_class_name_only():
    r, _ = verify_with(Timeout(f"read timed out talking to api with {KEY}"))
    assert r.error == "Timeout"
    r, _ = verify_with(ConnectionError(f"Bearer {KEY}"))
    assert r.error == "ConnectionError"
    assert KEY not in repr(r)


def test_key_required():
    with pytest.raises(ValueError):
        VisionVerifier("")


# ---------------- chain harness ----------------

class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def tick(self, dt=0.05):
        self.t += dt


class FakeRobot:
    def __init__(self):
        self.pos = dict(REST)
        self.sent = []

    def get_observation(self):
        return {**self.pos, "wrist": np.zeros((2, 2, 3), np.uint8), "side": np.ones((2, 2, 3), np.uint8)}

    def send_action(self, action):
        self.sent.append(dict(action))
        self.pos.update(action)
        return action


class FakePolicy:
    def __init__(self):
        self.resets = 0

    def reset(self):
        self.resets += 1

    def act(self, obs):
        return dict(REST)


class FakeRecorder:
    busy = False
    busy_after_end = False

    def __init__(self):
        self.begun, self.ended = [], []

    def begin(self, task):
        self.begun.append(task)

    def add(self, obs, action):
        pass

    def end(self, save=True):
        self.ended.append(save)
        self.busy = self.busy_after_end

    def close(self):
        pass


class ScriptVerifier:
    """Answers from a script (last one repeats); gate makes verify() block until released."""

    def __init__(self, *results, gate=None):
        self.results, self.calls, self.gate = list(results), [], gate
        self.entered = threading.Event()

    def verify(self, colour, jpeg):
        self.calls.append((colour, jpeg))
        self.entered.set()
        if self.gate is not None:
            assert self.gate.wait(5.0)
        r = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(r, Exception):
            raise r
        return r


def R(visible, in_bowl, note="备注"):
    return VerifyResult(visible, in_bowl, note, 12.0)


FAIL = R(True, False, "方块在碗外")
OK = R(True, True, "方块在碗里")


class Rig:
    def __init__(self, tmp_path, *results, gate=None, max_attempts=3, recorder=None):
        self.clock = FakeClock()
        self.robot = FakeRobot()
        self.msgs, self.events = [], []
        self.verifier = ScriptVerifier(*results, gate=gate)
        self.chain = VerifyChain(self.verifier, max_attempts=max_attempts, say=self.msgs.append,
                                 event=self.events.append, save_dir=tmp_path / "verify",
                                 encode=lambda frame: b"jpg:" + bytes(str(frame.shape), "ascii"))
        self.policies = {"red": FakePolicy(), "green": FakePolicy()}
        tasks = {"red": "Put the red cube into the paper bowl", "green": "Put the green cube into the paper bowl"}
        self.recorder = recorder
        self.runner = VoiceRunner(self.robot, self.policies, tasks, REST, clock=self.clock, say=self.msgs.append,
                                  event=self.events.append, timeout_s=1.0, recorder=recorder, chain=self.chain)

    def step(self, n=1):
        for _ in range(n):
            self.runner.step()
            self.clock.tick()

    def drive(self, until, limit=4000):
        for _ in range(limit):
            if until():
                return
            self.step()
            time.sleep(0.001)
        raise AssertionError(f"condition not reached; msgs={self.msgs[-6:]}")

    def settle(self):
        self.drive(lambda: self.runner.is_settled())

    def kinds(self, name):
        return [e for e in self.events if e.get("event") == name]

    def said(self, text):
        return any(text in m for m in self.msgs)

    def wait_event(self, name, count=1):
        self.drive(lambda: len(self.kinds(name)) >= count)


# ---------------- chain behaviour ----------------

def test_success_on_first_attempt(tmp_path):
    rig = Rig(tmp_path, OK)
    rig.runner.submit("run", "red")
    rig.settle()
    assert rig.policies["red"].resets == 1 and len(rig.verifier.calls) == 1
    assert rig.chain.outcome == "success" and not rig.chain.active
    assert rig.said("成功")
    v = rig.kinds("verify")[0]
    assert v["attempt"] == 1 and v["colour"] == "red" and v["in_bowl"] is True and v["dropped"] is False
    assert rig.kinds("run_start")[0]["attempt"] == 1


def test_fail_fail_then_success_on_third_attempt(tmp_path):
    rig = Rig(tmp_path, FAIL, FAIL, OK, max_attempts=5)
    rig.runner.submit("run", "red")
    rig.settle()
    assert rig.policies["red"].resets == 3 and len(rig.verifier.calls) == 3
    assert [e["attempt"] for e in rig.kinds("run_start")] == [1, 2, 3]
    assert [e["attempt"] for e in rig.kinds("verify")] == [1, 2, 3]
    assert rig.chain.outcome == "success"
    saved = sorted(p.name for p in (tmp_path / "verify").iterdir())
    assert len([n for n in saved if n.endswith(".jpg")]) == 3
    assert any(n.endswith("-red-a3.jpg") for n in saved)
    info = json.loads(next(p for p in (tmp_path / "verify").iterdir() if p.name.endswith("-red-a3.json")).read_text())
    assert info["in_bowl"] is True and info["attempt"] == 3 and info["latency_ms"] == 12.0
    # frame handed to the verifier is the side camera (the fake encoder prints its shape)
    assert rig.verifier.calls[0] == ("red", b"jpg:(2, 2, 3)")


def test_gives_up_at_max_attempts(tmp_path):
    rig = Rig(tmp_path, FAIL, max_attempts=2)
    rig.runner.submit("run", "red")
    rig.settle()
    assert rig.policies["red"].resets == 2 and len(rig.verifier.calls) == 2
    assert rig.chain.outcome == "gave_up" and rig.said("放弃")


def test_not_visible_stops_chain(tmp_path):
    rig = Rig(tmp_path, R(False, False, "看不到红色方块"), max_attempts=5)
    rig.runner.submit("run", "red")
    rig.settle()
    assert rig.policies["red"].resets == 1 and rig.chain.outcome == "not_visible"
    assert rig.said("不见了")


@pytest.mark.parametrize("bad", [
    VerifyResult(None, None, "", 5.0, "Timeout"),
    VerifyResult(None, None, "", 5.0, "http_500"),
    VerifyResult(None, None, "", 5.0, "bad_json"),
    RuntimeError("verifier crashed"),
])
def test_verify_error_stops_without_retry(tmp_path, bad):
    rig = Rig(tmp_path, bad, max_attempts=5)
    rig.runner.submit("run", "red")
    rig.settle()
    assert rig.policies["red"].resets == 1 and rig.chain.outcome == "verify_error"
    assert rig.said("验证出错")


def test_key_never_in_msgs_events_or_saved_files(tmp_path):
    post = FakePost(Timeout(f"boom {KEY}"))
    rig = Rig(tmp_path, FAIL)
    rig.chain.verifier = VisionVerifier(KEY, post=post)
    rig.runner.submit("run", "red")
    rig.settle()
    blob = json.dumps(rig.msgs + rig.events, ensure_ascii=False)
    for p in (tmp_path / "verify").iterdir():
        blob += p.read_text(errors="ignore")
    assert KEY not in blob and "Timeout" in blob


def test_stop_during_run_cancels_chain_and_no_verify(tmp_path):
    rig = Rig(tmp_path, FAIL)
    rig.runner.submit("run", "red")
    rig.step(3)
    assert rig.chain.active
    rig.runner.submit("stop")
    rig.settle()
    assert rig.verifier.calls == [] and rig.policies["red"].resets == 1
    assert rig.chain.outcome == "cancelled_stop" and not rig.chain.active


def test_stop_during_later_attempt_prevents_further_retries(tmp_path):
    rig = Rig(tmp_path, FAIL, max_attempts=5)
    rig.runner.submit("run", "red")
    rig.drive(lambda: rig.policies["red"].resets == 2 and rig.runner.state != IDLE)
    rig.runner.submit("stop")
    rig.settle()
    assert rig.policies["red"].resets == 2 and len(rig.verifier.calls) == 1


@pytest.mark.parametrize("kind", ["stop", "quit", "home"])
def test_cancel_while_verify_in_flight_drops_the_answer(tmp_path, kind):
    gate = threading.Event()
    rig = Rig(tmp_path, FAIL, gate=gate, max_attempts=5)
    rig.runner.submit("run", "red")
    rig.drive(lambda: rig.verifier.entered.is_set())
    assert rig.runner.state == IDLE and rig.chain.active and not rig.runner.is_settled()
    rig.runner.submit(kind)
    assert not rig.chain.active                       # cancelled synchronously, before the next control tick
    gate.set()
    rig.wait_event("verify")
    rig.drive(lambda: rig.runner.is_settled() or rig.runner.finished)
    rig.step(5)
    assert rig.kinds("verify")[0]["dropped"] is True
    assert rig.policies["red"].resets == 1 and rig.policies["green"].resets == 0   # no retry
    assert rig.said("作废")
    assert rig.chain.outcome == f"cancelled_{kind}"
    if kind == "quit":
        assert rig.runner.finished


def test_new_colour_during_verify_is_refused(tmp_path):
    gate = threading.Event()
    rig = Rig(tmp_path, OK, gate=gate)
    rig.runner.submit("run", "red")
    rig.drive(lambda: rig.verifier.entered.is_set())
    rig.runner.submit("run", "green")
    rig.step(2)
    assert rig.policies["green"].resets == 0 and rig.said("忽略新的颜色指令")
    assert rig.kinds("refused")[-1]["state"] == "verify_chain"
    gate.set()
    rig.settle()
    assert rig.chain.outcome == "success" and rig.policies["green"].resets == 0


def test_new_colour_during_run_still_uses_the_old_refusal(tmp_path):
    rig = Rig(tmp_path, OK)
    rig.runner.submit("run", "red")
    rig.step(2)
    rig.runner.submit("run", "green")
    rig.step(2)
    assert rig.said("正在执行红色") and rig.policies["green"].resets == 0
    rig.settle()


def test_colour_command_accepted_again_after_chain_ends(tmp_path):
    rig = Rig(tmp_path, OK)
    rig.runner.submit("run", "red")
    rig.settle()
    rig.runner.submit("run", "green")
    rig.settle()
    assert rig.policies["green"].resets == 1 and [e["attempt"] for e in rig.kinds("run_start")] == [1, 1]


def test_wait_until_settled_waits_for_the_whole_chain(tmp_path):
    rig = Rig(tmp_path, FAIL, FAIL, OK, max_attempts=5)
    rig.runner.submit("run", "red")

    def pump(_dt):
        rig.step()
        time.sleep(0.001)

    voice_agent.wait_until_settled(rig.runner, None, sleep=pump)
    assert rig.policies["red"].resets == 3 and rig.chain.outcome == "success" and not rig.chain.active
    rig.runner.submit("quit")
    rig.step(3)
    assert rig.runner.finished


def test_each_attempt_is_its_own_episode(tmp_path):
    rec = FakeRecorder()
    rig = Rig(tmp_path, FAIL, FAIL, OK, max_attempts=5, recorder=rec)
    rig.runner.submit("run", "red")
    rig.settle()
    assert len(rec.begun) == 3 and rec.ended == [True, True, True]


def test_retry_waits_for_a_recorder_that_is_still_saving(tmp_path):
    rec = FakeRecorder()
    rec.busy_after_end = True
    rig = Rig(tmp_path, FAIL, OK, max_attempts=3, recorder=rec)
    rig.runner.submit("run", "red")
    rig.wait_event("verify")
    rig.step(10)
    assert rig.policies["red"].resets == 1          # still waiting for the previous episode to be saved
    rec.busy = False
    rig.settle()
    assert rig.policies["red"].resets == 2 and rig.chain.outcome == "success"


def test_without_chain_nothing_changes(tmp_path):
    rig = Rig(tmp_path, OK)
    runner = VoiceRunner(rig.robot, rig.policies, {"red": "t", "green": "t"}, REST, clock=rig.clock,
                         say=rig.msgs.append, event=rig.events.append, timeout_s=1.0)
    runner.submit("run", "red")
    for _ in range(200):
        runner.step()
        rig.clock.tick()
    assert runner.is_settled() and rig.verifier.calls == []


def test_missing_side_frame_ends_chain(tmp_path):
    rig = Rig(tmp_path, OK)
    rig.robot.get_observation = lambda: dict(rig.robot.pos)
    rig.runner.submit("run", "red")
    rig.settle()
    assert rig.verifier.calls == [] and rig.chain.outcome == "no_side_frame"


def test_max_attempts_must_be_positive():
    with pytest.raises(ValueError):
        VerifyChain(ScriptVerifier(OK), max_attempts=0)


# ---------------- CLI ----------------

def test_main_exits_without_key_before_loading_policies(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(SystemExit) as e:
        voice_agent.main(["--verify"])
    assert "DEEPSEEK_API_KEY" in str(e.value)


def test_cli_defaults_and_validation(capsys):
    args = voice_agent.build_parser().parse_args([])
    assert (args.verify, args.max_attempts, args.verify_model, args.verify_timeout) == (False, 10, "deepseek-flash", 15.0)
    with pytest.raises(SystemExit):
        voice_agent.main(["--max-attempts", "0"])
