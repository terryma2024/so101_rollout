import pytest

from voice_intent import GREEN, HOME, RED, STOP, UNCLEAR, parse_intent


@pytest.mark.parametrize("text,expected", [
    ("红", RED), ("红色", RED), ("把红色方块放进碗里", RED), ("请抓红色的", RED), ("Red.", RED), ("red cube", RED),
    ("绿", GREEN), ("绿色", GREEN), ("绿色的方块", GREEN), ("Green!", GREEN), ("pick the green one", GREEN),
    ("停", STOP), ("停止", STOP), ("别动", STOP), ("Stop", STOP), ("stop!", STOP),
    ("回去", HOME), ("复位", HOME), ("home", HOME), ("Go home.", HOME),
    ("红色和绿色", UNCLEAR), ("red and green", UNCLEAR), ("红色 green", UNCLEAR),
    ("你好", UNCLEAR), ("", UNCLEAR), ("   ", UNCLEAR), ("blue", UNCLEAR),
])
def test_keywords(text, expected):
    assert parse_intent(text) == expected


def test_stop_beats_colour():
    assert parse_intent("红色，停") == STOP
    assert parse_intent("stop the green one") == STOP


def test_colour_beats_home():
    assert parse_intent("把红色的放回去") == RED
    assert parse_intent("绿色 home") == GREEN


def test_english_needs_whole_words():
    for text in ("bored", "hundred", "greenhouse", "homework", "stopwatch"):
        assert parse_intent(text) == UNCLEAR


def test_none_is_unclear():
    assert parse_intent(None) == UNCLEAR
