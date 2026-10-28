"""--verify：一次执行结束、手臂回到休息位后，用 DeepSeek 视觉模型看侧面相机的一帧，判断方块有没有进碗，没进就自动重试。

安全约定：
  - 视觉请求在后台线程里做，永远不阻塞 20 Hz 控制循环；
  - 任何验证失败（超时、HTTP 错误、JSON 坏了、字段缺失或类型不对）都停止重试，只报错误类名/状态码，不盲目重试；
  - “停 / 回去 / 退出”（任何输入通道）立刻取消整条重试链，正在进行的验证请求的答案作废（epoch，同 LlmWorker）；
  - 链进行中，新的颜色指令像执行中一样被拒绝（见 voice_runner）。
API key 只从环境变量 DEEPSEEK_API_KEY 读，不写日志、不进错误信息。
"""
import base64
import datetime
import io
import json
import pathlib
import threading
import time
from dataclasses import dataclass
from typing import Optional

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MAX_ATTEMPTS = 10
SIDE_KEY = "side"
COLOUR_ZH = {"red": "红色", "green": "绿色"}

PROMPT = ("这是桌面机械臂侧边相机的一帧。桌上有一张白纸、一个纸碗，可能有一个红色方块和一个绿色方块"
          "（灯光偏暖时，绿色方块可能看起来很暗）。"
          "判断{colour}方块的位置。只输出 JSON：{{\"visible\": true|false, \"in_bowl\": true|false, \"note\": \"一句中文\"}}。"
          "visible=画面里能看到{colour}方块；in_bowl={colour}方块在纸碗里面。")


@dataclass
class VerifyResult:
    visible: Optional[bool]
    in_bowl: Optional[bool]
    note: str
    latency_ms: float
    error: Optional[str] = None
    raw: Optional[str] = None


def parse_answer(content):
    """Return (visible, in_bowl, note) or raise ValueError(reason)."""
    try:
        obj = json.loads(content)
    except (TypeError, ValueError):
        raise ValueError("bad_json") from None
    if not isinstance(obj, dict):
        raise ValueError("not_object")
    for key in ("visible", "in_bowl"):
        if not isinstance(obj.get(key), bool):
            raise ValueError(f"bad_{key}")
    note = obj.get("note", "")
    if note is None:
        note = ""
    if not isinstance(note, str):
        raise ValueError("bad_note")
    if obj["in_bowl"] and not obj["visible"]:
        raise ValueError("inconsistent")
    return obj["visible"], obj["in_bowl"], " ".join(note.split())


class _Failure(Exception):
    pass


class VisionVerifier:
    """post: callable(url, headers=..., json=..., timeout=...) -> object with .status_code and .json();
    defaults to requests.post. Tests inject a fake so the network is never touched."""

    def __init__(self, api_key, model=DEFAULT_MODEL, timeout=DEFAULT_TIMEOUT_S, post=None, url=API_URL,
                 clock=time.perf_counter):
        if not api_key:
            raise ValueError("api_key is required")
        self._api_key = api_key
        self.model, self.timeout, self.url, self.clock = model, timeout, url, clock
        if post is None:
            import requests
            post = requests.post
        self._post = post

    def verify(self, colour, jpeg) -> VerifyResult:
        t0 = self.clock()
        b64 = base64.b64encode(jpeg).decode()
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": PROMPT.format(colour=COLOUR_ZH.get(colour, colour))}]}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 2000,     # the model reasons before answering; with ~200 the content comes back empty
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        content = None
        try:
            resp = self._post(self.url, headers=headers, json=body, timeout=self.timeout)
            if resp.status_code != 200:
                raise _Failure(f"http_{resp.status_code}")
            try:
                content = resp.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, ValueError):
                raise _Failure("bad_response") from None
            visible, in_bowl, note = parse_answer(content)
        except (_Failure, ValueError) as failure:
            error = str(failure)
        except Exception as exc:  # noqa: BLE001 - timeout / connection errors; class name only (no key leaks)
            error = type(exc).__name__
        else:
            return VerifyResult(visible, in_bowl, note, round((self.clock() - t0) * 1000, 1), None, content)
        raw = content if isinstance(content, str) else None
        return VerifyResult(None, None, "", round((self.clock() - t0) * 1000, 1), error, raw)


def encode_jpeg(frame, quality=90):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(frame).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


class VerifyChain:
    """Retry chain of one colour command: attempt, verify, maybe attempt again, up to max_attempts.

    Thread model: begin_user_run / begin_auto_run / on_run_end / on_rested run on the control thread (cheap, never
    block); the verification runs on its own thread; cancel() may be called from any thread. `active` stays True from
    the user's accepted colour command until the chain ends, so VoiceRunner refuses new colours and is_settled()
    waits for the whole chain."""

    def __init__(self, verifier, max_attempts=DEFAULT_MAX_ATTEMPTS, say=print, event=None, save_dir=None,
                 encode=encode_jpeg, sleep=time.sleep, recorder_wait_s=120.0):
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.verifier, self.max_attempts, self.say = verifier, max_attempts, say
        self.event = event or (lambda e: None)
        self.save_dir = pathlib.Path(save_dir) if save_dir else None
        self.encode, self.sleep, self.recorder_wait_s = encode, sleep, recorder_wait_s
        self.runner = None
        self._lock = threading.Lock()
        self._epoch = 0
        self._active = False
        self._colour = None
        self._attempt = 0
        self.outcome = None

    def attach(self, runner):
        self.runner = runner

    @property
    def active(self):
        with self._lock:
            return self._active

    @property
    def attempt(self):
        with self._lock:
            return self._attempt

    # --- control thread -------------------------------------------------------------
    def begin_user_run(self, colour):
        with self._lock:
            self._epoch += 1
            self._active, self._colour, self._attempt, self.outcome = True, colour, 1, None
        self.event({"event": "verify_chain_start", "colour": colour, "max_attempts": self.max_attempts})

    def accepts(self, token):
        with self._lock:
            return self._active and token == self._epoch

    def begin_auto_run(self):
        with self._lock:
            self._attempt += 1
            return self._attempt

    def on_run_end(self, reason):
        """A run ended. Only done / timeout continue to verification; anything else ends the chain."""
        if reason not in ("done", "timeout"):
            self.finish(f"run_{reason}", f"这一次{'出错' if reason == 'error' else '被中止'}，不再自动重试。")

    def on_rested(self, obs):
        """The arm is back at rest: grab the side frame (copy) and verify in the background."""
        with self._lock:
            if not self._active:
                return
            epoch, colour, attempt = self._epoch, self._colour, self._attempt
        frame = obs.get(SIDE_KEY) if isinstance(obs, dict) else None
        if frame is None:
            self.finish("no_side_frame", "验证出错（没有侧面相机画面），不再重试。")
            return
        try:
            frame = frame.copy()
        except AttributeError:
            pass
        self.say(f"验证第 {attempt} 次结果 ...")
        threading.Thread(target=self._verify, args=(epoch, colour, attempt, frame), daemon=True,
                         name="verify").start()

    # --- any thread -----------------------------------------------------------------
    def cancel(self, why="cancel"):
        """Cancel the whole chain now (and void any verification in flight). Returns True if a chain was active."""
        with self._lock:
            was = self._active
            self._epoch += 1
            self._active = False
            colour, attempt = self._colour, self._attempt
            if was:
                self.outcome = f"cancelled_{why}"
        if was:
            self.say("已取消自动重试")
            self.event({"event": "verify_chain_end", "colour": colour, "attempt": attempt,
                        "outcome": f"cancelled_{why}"})
        return was

    def finish(self, outcome, message, epoch=None):
        with self._lock:
            if not self._active or (epoch is not None and epoch != self._epoch):
                return False
            self._active = False
            self.outcome = outcome
            colour, attempt = self._colour, self._attempt
        self.say(message)
        self.event({"event": "verify_chain_end", "colour": colour, "attempt": attempt, "outcome": outcome})
        return True

    # --- verification thread --------------------------------------------------------
    def _verify(self, epoch, colour, attempt, frame):
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        jpeg = None
        try:
            jpeg = self.encode(frame)
            result = self.verifier.verify(colour, jpeg)
        except Exception as exc:  # noqa: BLE001
            result = VerifyResult(None, None, "", 0.0, type(exc).__name__)
        saved = self._save(stamp, colour, attempt, jpeg, result)
        with self._lock:
            stale = (not self._active) or epoch != self._epoch
        ev = {"event": "verify", "colour": colour, "attempt": attempt, "visible": result.visible,
              "in_bowl": result.in_bowl, "note": result.note, "latency_ms": result.latency_ms,
              "error": result.error, "saved": saved, "dropped": stale}
        self.event(ev)
        zh = COLOUR_ZH.get(colour, colour)
        if stale:
            self.say(f"验证第 {attempt} 次的答案已作废（之后收到了停止/回去/退出）")
            return
        if result.error:
            self.finish("verify_error", f"验证出错（{result.error}），不再重试。", epoch)
        elif result.in_bowl:
            self.finish("success", f"成功：{zh}方块在碗里（第 {attempt} 次）。{result.note}", epoch)
        elif not result.visible:
            self.finish("not_visible", f"目标方块不见了（可能被碰出了画面），不再重试。{result.note}", epoch)
        elif attempt >= self.max_attempts:
            self.finish("gave_up", f"已尝试 {attempt} 次，{zh}方块仍不在碗里，放弃。{result.note}", epoch)
        else:
            self.say(f"第 {attempt} 次没成功（{result.note}），自动重试第 {attempt + 1} 次（最多 {self.max_attempts} 次）")
            self._retry(epoch)

    def _retry(self, epoch):
        recorder = getattr(self.runner, "recorder", None)
        waited = 0.0
        while recorder is not None and getattr(recorder, "busy", False) and waited < self.recorder_wait_s:
            if not self.accepts(epoch):
                return
            self.sleep(0.1)
            waited += 0.1
        if not self.accepts(epoch):
            return
        self.runner.submit("run", self._colour, token=epoch)

    def _save(self, stamp, colour, attempt, jpeg, result):
        if self.save_dir is None:
            return None
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            base = self.save_dir / f"{stamp}-{colour}-a{attempt}"
            if jpeg is not None:
                base.with_suffix(".jpg").write_bytes(jpeg)
            base.with_suffix(".json").write_text(json.dumps(
                {"colour": colour, "attempt": attempt, "visible": result.visible, "in_bowl": result.in_bowl,
                 "note": result.note, "latency_ms": result.latency_ms, "error": result.error, "raw": result.raw},
                ensure_ascii=False, indent=1))
            return str(base)
        except Exception as exc:  # noqa: BLE001 - saving evidence must never break the chain
            return f"save_failed:{type(exc).__name__}"
