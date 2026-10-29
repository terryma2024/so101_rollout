"""语音/键盘指令的关键词意图识别（不用大模型）。

返回值是下面几个常量之一：
  RED / GREEN   抓红色 / 绿色方块（含"红"或 red；含"绿"或 green）
  STOP          停（停、停止、别动、stop），任何时候都有效，优先级最高
  HOME          回休息位（回去、复位、home），只在没有颜色词时生效（"把红色的放回去"仍然是红色）
  UNCLEAR       同时含红绿两个颜色，或什么关键词都没有
"""
import re

RED, GREEN, STOP, HOME, UNCLEAR = "red", "green", "stop", "home", "unclear"

_STOP_ZH = ("停", "别动", "不要动")
_HOME_ZH = ("回去", "复位", "回家", "回到休息")
_RED_ZH = ("红", "紅")
_GREEN_ZH = ("绿", "綠")


def _word(w: str) -> "re.Pattern[str]":
    """English keyword as a whole word, so 'bored' / 'greenhouse' / 'homework' do not match."""
    return re.compile(rf"(?<![a-z]){w}(?![a-z])")


_STOP_EN, _HOME_EN, _RED_EN, _GREEN_EN = _word("stop"), _word("home"), _word("red"), _word("green")

UNCLEAR_HINT = "没听清，请说红色或绿色"


def parse_intent(text) -> str:
    """把一句话变成意图。"""
    t = (text or "").strip().lower()
    if not t:
        return UNCLEAR
    if any(k in t for k in _STOP_ZH) or _STOP_EN.search(t):   # "停止" contains "停"
        return STOP
    red = any(k in t for k in _RED_ZH) or bool(_RED_EN.search(t))
    green = any(k in t for k in _GREEN_ZH) or bool(_GREEN_EN.search(t))
    if red and green:
        return UNCLEAR
    if red:
        return RED
    if green:
        return GREEN
    if any(k in t for k in _HOME_ZH) or _HOME_EN.search(t):
        return HOME
    return UNCLEAR
