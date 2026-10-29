import json
import threading
import time

import pytest

from so101_test.voice import voice_agent
from so101_test.voice.voice_intent import GREEN, HOME, RED, UNCLEAR
from so101_test.voice.voice_llm_intent import SYSTEM_PROMPT, LlmIntentParser, LlmWorker

KEY = "sk-test-SECRET-0123456789"


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


def ok(intent, reply="好的"):
    return FakeResp(content=json.dumps({"intent": intent, "reply": reply}, ensure_ascii=False))


def parser(*responses, timeout=3.0):
    post = FakePost(*responses)
    return LlmIntentParser(KEY, timeout=timeout, post=post), post


class FakeRunner:
    def __init__(self):
        self.cmds = []

    def submit(self, kind, colour=None):
        self.cmds.append((kind, colour))


def wait(worker, timeout=5.0):
    t0 = time.time()
    while worker.pending() and time.time() - t0 < timeout:
        time.sleep(0.01)
    assert worker.pending() == 0


def make_worker(p, runner, events):
    return LlmWorker(p, lambda t, c, r: voice_agent.apply_llm_result(runner, events.append, t, c, r))


@pytest.fixture(autouse=True)
def quiet_say(monkeypatch):
    said = []
    monkeypatch.setattr(voice_agent, "say", said.append)
    return said


@pytest.mark.parametrize("intent", ["red", "green", "stop", "home", "quit", "unclear"])
def test_valid_intents(intent):
    p, post = parser(ok(intent, "收到"))
    r = p.parse("随便一句")
    assert (r.intent, r.reply, r.source, r.error) == (intent, "收到", "llm", None)
    assert r.latency_ms >= 0
    call = post.calls[0]
    assert call["json"]["model"] == "deepseek-flash" and call["json"]["temperature"] == 0
    assert call["json"]["response_format"] == {"type": "json_object"}
    assert call["json"]["max_tokens"] >= 1500   # flash reasons first; a small budget gives empty content
    assert call["timeout"] == 3.0 and call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert call["json"]["messages"][0]["content"] == SYSTEM_PROMPT
    assert call["json"]["messages"][1] == {"role": "user", "content": "随便一句"}


def test_missing_reply_is_allowed():
    p, _ = parser(FakeResp(content='{"intent": "red"}'))
    r = p.parse("红")
    assert r.intent == "red" and r.reply is None and r.source == "llm"


@pytest.mark.parametrize("resp,reason", [
    (FakeResp(content="not json"), "bad_json"),
    (FakeResp(content="[1, 2]"), "not_object"),
    (FakeResp(content='{"reply": "x"}'), "bad_intent"),
    (FakeResp(content='{"intent": "blue", "reply": "x"}'), "bad_intent"),
    (FakeResp(content='{"intent": "RED", "reply": "x"}'), "bad_intent"),
    (FakeResp(content='{"intent": ["red"], "reply": "x"}'), "bad_intent"),
    (FakeResp(content='{"intent": "red", "reply": 5}'), "bad_reply"),
    (FakeResp(payload={"choices": []}), "bad_response"),
    (FakeResp(payload={"oops": 1}), "bad_response"),
    (FakeResp(content=None), "empty_content"),
    (FakeResp(content=""), "empty_content"),
    (FakeResp(content="  "), "empty_content"),
])
def test_invalid_output_falls_back_to_rules(resp, reason):
    p, _ = parser(resp)
    r = p.parse("把红色方块放进碗里")
    assert (r.intent, r.source, r.error, r.reply) == (RED, "fallback", reason, None)


def test_timeout_falls_back_with_rule_result():
    class Timeout(Exception):
        pass
    p, _ = parser(Timeout(f"read timed out calling with {KEY}"))
    r = p.parse("绿色")
    assert (r.intent, r.source, r.error) == (GREEN, "fallback", "Timeout")


@pytest.mark.parametrize("status", [401, 500, 429])
def test_http_errors_fall_back(status):
    p, _ = parser(FakeResp(status=status, content="x"))
    r = p.parse("回去")
    assert (r.intent, r.source, r.error) == (HOME, "fallback", f"http_{status}")


def test_fallback_unclear_when_rules_do_not_understand():
    p, _ = parser(FakeResp(status=500))
    assert p.parse("今天天气不错").intent == UNCLEAR


def test_key_never_in_results_or_log_events(quiet_say):
    events = []
    runner = FakeRunner()
    p, _ = parser(RuntimeError(f"boom {KEY}"), FakeResp(status=401, content=KEY), ok("red"))
    worker = make_worker(p, runner, events)
    for text in ("红色", "绿色", "拿那个红的"):
        voice_agent.handle_text(runner, events.append, text, "键盘", worker)
    wait(worker)
    blob = json.dumps(events, ensure_ascii=False) + "\n".join(quiet_say)
    assert KEY not in blob and "Bearer" not in blob and "Authorization" not in blob
    assert [e["source"] for e in events if e["event"] == "llm_intent"] == ["fallback", "fallback", "llm"]


def test_constructor_requires_key():
    with pytest.raises(ValueError):
        LlmIntentParser("", post=FakePost(ok("red")))


def test_stop_bypasses_the_client():
    runner, events = FakeRunner(), []
    p, post = parser(ok("red"))
    worker = make_worker(p, runner, events)
    for text in ("停", "stop", "别动", "停止"):
        voice_agent.handle_text(runner, events.append, text, "键盘", worker)
    assert runner.cmds == [("stop", None)] * 4 and post.calls == [] and worker.pending() == 0


def test_quit_words_bypass_the_client():
    runner = FakeRunner()
    p, post = parser(ok("red"))
    worker = LlmWorker(p, lambda *a: None)
    voice_agent.handle_text(runner, lambda e: None, "q", "键盘", worker)
    assert runner.cmds == [("quit", None)] and post.calls == []


def test_stop_is_immediate_while_a_request_is_in_flight():
    runner, events = FakeRunner(), []
    gate = threading.Event()

    def slow_post(url, headers=None, json=None, timeout=None):
        gate.wait(5)
        return ok("red")

    worker = make_worker(LlmIntentParser(KEY, post=slow_post), runner, events)
    voice_agent.handle_text(runner, events.append, "拿那个红的", "键盘", worker)
    assert worker.pending() == 1 and runner.cmds == []
    voice_agent.handle_text(runner, events.append, "停", "键盘", worker)
    assert runner.cmds == [("stop", None)]            # stop did not wait for the request
    gate.set()
    wait(worker)
    assert runner.cmds == [("stop", None)]            # the in-flight red answer is void after the stop


def test_answers_after_stop_or_quit_are_dropped(quiet_say):
    runner, dropped = FakeRunner(), []
    gate = threading.Event()

    def slow_post(url, headers=None, json=None, timeout=None):
        gate.wait(5)
        return ok("green")

    worker = LlmWorker(LlmIntentParser(KEY, post=slow_post),
                       lambda t, c, r: voice_agent.apply_llm_result(runner, [].append, t, c, r),
                       on_dropped=lambda t, c, r: dropped.append((t, r.intent)))
    voice_agent.handle_text(runner, [].append, "拿绿的", "键盘", worker)
    voice_agent.handle_text(runner, [].append, "q", "键盘", worker)
    gate.set()
    wait(worker)
    assert runner.cmds == [("quit", None)] and dropped == [("拿绿的", "green")]
    # a sentence submitted after the cancel is answered normally
    voice_agent.handle_text(runner, [].append, "再拿绿的", "键盘", worker)
    wait(worker)
    assert runner.cmds[-1] == ("run", "green")


def test_llm_dispatch_in_order_and_mapping(quiet_say):
    runner, events = FakeRunner(), []
    seq = [ok("red"), ok("green"), ok("home"), ok("stop"), ok("quit"), ok("unclear", "请说红色还是绿色？")]
    p, post = parser(*seq)
    worker = make_worker(p, runner, events)
    for i in range(6):
        voice_agent.handle_text(runner, events.append, f"句子{i}", "语音", worker)
    wait(worker)
    assert runner.cmds == [("run", "red"), ("run", "green"), ("home", None), ("stop", None), ("quit", None)]
    assert [c["json"]["messages"][1]["content"] for c in post.calls] == [f"句子{i}" for i in range(6)]
    assert any("请说红色还是绿色" in m for m in quiet_say) and any("llm" in m for m in quiet_say)
    log = [e for e in events if e["event"] == "llm_intent"]
    assert len(log) == 6 and set(log[0]) >= {"text", "intent", "source", "latency_ms", "error", "reply"}


def test_unclear_without_reply_prints_hint(quiet_say):
    runner, events = FakeRunner(), []
    p, _ = parser(FakeResp(content='{"intent": "unclear"}'))
    worker = make_worker(p, runner, events)
    voice_agent.handle_text(runner, events.append, "嗯", "键盘", worker)
    wait(worker)
    assert runner.cmds == [] and voice_agent.UNCLEAR_HINT in quiet_say


def test_without_llm_behaviour_is_rules_only():
    runner, events = FakeRunner(), []
    for text in ("红", "绿", "停", "回去", "你好"):
        voice_agent.handle_text(runner, events.append, text, "键盘")
    assert runner.cmds == [("run", "red"), ("run", "green"), ("stop", None), ("home", None)]


def test_wait_until_settled_waits_for_llm_and_runner():
    class R:
        n = 0

        def is_settled(self):
            self.n += 1
            return self.n > 3

    class W:
        n = 0

        def pending(self):
            self.n += 1
            return 0 if self.n > 2 else 1

    r, w, sleeps = R(), W(), []
    voice_agent.wait_until_settled(r, w, sleep=sleeps.append)
    assert len(sleeps) >= 3 and r.n > 3


def test_main_exits_without_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(SystemExit) as e:
        voice_agent.main(["--llm"])
    assert "DEEPSEEK_API_KEY" in str(e.value)
