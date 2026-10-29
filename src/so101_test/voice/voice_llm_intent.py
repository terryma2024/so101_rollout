"""用 DeepSeek 大模型把一句话（中文/英文）变成意图，失败时退回本地关键词规则（voice_intent.parse_intent）。

只用于 `voice_agent.py --llm`。安全约定（见 voice_agent.handle_text）：
  - “停”类指令永远先走本地规则，立刻生效，不等大模型；
  - 大模型输出必须是 {"intent": red|green|stop|home|quit|unclear, "reply": "..."}，其它任何内容都当失败；
  - 超时（默认 3 秒）、HTTP 错误、输出不合格 -> 退回本地规则，source="fallback"。
API key 只从环境变量 DEEPSEEK_API_KEY 读，不写日志、不进错误信息。
"""
import json
import queue
import threading
import time
from dataclasses import dataclass
from typing import Optional

from .voice_intent import GREEN, HOME, RED, STOP, UNCLEAR, parse_intent

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_TIMEOUT_S = 3.0
QUIT = "quit"
INTENTS = (RED, GREEN, STOP, HOME, QUIT, UNCLEAR)

SYSTEM_PROMPT = (
    "你是桌面机械臂的语音指令解析器。操作员用中文或英文说话。机械臂只能做这几件事：\n"
    "- red：把红色方块放进纸碗\n"
    "- green：把绿色方块放进纸碗\n"
    "- stop：立刻停下\n"
    "- home：回到休息位（复位）\n"
    "- quit：退出程序\n"
    "- unclear：听不懂、两种颜色都提到、含糊、或与机械臂无关\n"
    "只输出一个 JSON 对象（JSON only），格式：\n"
    '{"intent": "red|green|stop|home|quit|unclear", "reply": "<给操作员的一句简短中文>"}\n'
    "规则：只有明确要抓一种颜色时才返回 red 或 green；同时提到两种颜色、没说颜色、或无关闲聊，一律 unclear，"
    "并在 reply 里用中文问清楚（例如“请说红色还是绿色？”）。reply 必须是一句短中文，不要换行。"
)


@dataclass
class IntentResult:
    intent: str
    reply: Optional[str]
    source: str            # "rules" | "llm" | "fallback"
    latency_ms: float
    error: Optional[str] = None


def rules_result(text, source="rules", error=None, latency_ms=0.0):
    return IntentResult(parse_intent(text), None, source, round(latency_ms, 1), error)


def validate_output(content):
    """Parse the model's message content; return (intent, reply) or raise ValueError."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty_content")
    try:
        obj = json.loads(content)
    except (TypeError, ValueError):
        raise ValueError("bad_json") from None
    if not isinstance(obj, dict):
        raise ValueError("not_object")
    intent = obj.get("intent")
    if not isinstance(intent, str) or intent not in INTENTS:
        raise ValueError("bad_intent")
    reply = obj.get("reply")
    if reply is None:
        reply = None
    elif isinstance(reply, str):
        reply = reply.strip() or None
    else:
        raise ValueError("bad_reply")
    return intent, reply


class LlmIntentParser:
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

    def _error_name(self, exc):
        # exception class name only: messages/URLs/headers could carry the key
        return type(exc).__name__

    def parse(self, text) -> IntentResult:
        t0 = self.clock()
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 1500,     # deepseek-flash reasons before answering; with ~200 the content comes back empty
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            resp = self._post(self.url, headers=headers, json=body, timeout=self.timeout)
            if resp.status_code != 200:
                raise _Failure(f"http_{resp.status_code}")
            try:
                content = resp.json()["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError, ValueError):
                raise _Failure("bad_response") from None
            intent, reply = validate_output(content)
        except _Failure as failure:
            error = str(failure)
        except ValueError as failure:
            error = str(failure)
        except Exception as exc:  # noqa: BLE001 - timeout / connection errors from any HTTP client
            error = self._error_name(exc)
        else:
            return IntentResult(intent, reply, "llm", round((self.clock() - t0) * 1000, 1), None)
        return rules_result(text, "fallback", error, (self.clock() - t0) * 1000)


class _Failure(Exception):
    pass


class LlmWorker:
    """One background thread processing LLM requests strictly in order.

    handler(text, channel, result) runs on the worker thread. pending() counts requests submitted but not yet
    fully handled (including the handler), so callers can wait for them. cancel() voids every request submitted
    before it: their answers are dropped (on_dropped is called instead of handler), so a "停" typed while a
    request is in flight can never be followed by a stale run."""

    def __init__(self, parser, handler, on_dropped=None):
        self.parser, self.handler, self.on_dropped = parser, handler, on_dropped
        self._q = queue.Queue()
        self._lock = threading.Lock()
        self._pending = 0
        self._epoch = 0
        threading.Thread(target=self._run, daemon=True, name="llm-intent").start()

    def submit(self, text, channel):
        with self._lock:
            self._pending += 1
            epoch = self._epoch
        self._q.put((text, channel, epoch))

    def cancel(self):
        with self._lock:
            self._epoch += 1

    def pending(self):
        with self._lock:
            return self._pending

    def _run(self):
        while True:
            text, channel, epoch = self._q.get()
            try:
                result = self.parser.parse(text)
                with self._lock:
                    stale = epoch != self._epoch
                if stale:
                    if self.on_dropped:
                        self.on_dropped(text, channel, result)
                else:
                    self.handler(text, channel, result)
            except Exception as exc:  # noqa: BLE001 - never let the worker die
                print(f"大模型意图处理出错：{type(exc).__name__}", flush=True)
            finally:
                with self._lock:
                    self._pending -= 1
