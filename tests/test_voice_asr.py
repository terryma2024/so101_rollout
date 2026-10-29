import wave

import numpy as np

from so101_rollout.voice.voice_asr import SAMPLE_RATE, EnergySegmenter, MicListener, read_wav_16k_mono


def tone(seconds, amp=0.2, freq=300.0):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def quiet(seconds, amp=0.001):
    rng = np.random.default_rng(0)
    return (amp * rng.standard_normal(int(seconds * SAMPLE_RATE))).astype(np.float32)


def feed_all(seg, audio, chunk=480):
    out = []
    for i in range(0, len(audio), chunk):
        out += seg.feed(audio[i:i + chunk])
    return out


def test_one_utterance_ends_after_silence():
    seg = EnergySegmenter()
    out = feed_all(seg, np.concatenate([quiet(1.0), tone(1.0), quiet(1.0)]))
    assert len(out) == 1
    assert 1.0 < len(out[0]) / SAMPLE_RATE < 2.2   # speech + 0.6 s tail + pre-roll


def test_not_ended_before_silence_elapsed():
    seg = EnergySegmenter()
    assert feed_all(seg, np.concatenate([quiet(0.5), tone(1.0), quiet(0.4)])) == []


def test_short_pause_inside_a_sentence_does_not_split():
    seg = EnergySegmenter()
    out = feed_all(seg, np.concatenate([quiet(0.5), tone(0.6), quiet(0.4), tone(0.6), quiet(1.0)]))
    assert len(out) == 1


def test_two_utterances():
    seg = EnergySegmenter()
    out = feed_all(seg, np.concatenate([quiet(0.5), tone(0.8), quiet(1.0), tone(0.8), quiet(1.0)]))
    assert len(out) == 2


def test_click_is_dropped():
    seg = EnergySegmenter()
    assert feed_all(seg, np.concatenate([quiet(0.5), tone(0.06), quiet(1.5)])) == []


def test_silence_only_gives_nothing():
    assert feed_all(EnergySegmenter(), quiet(3.0)) == []


def test_max_length_forces_close():
    seg = EnergySegmenter(max_s=2.0)
    assert len(feed_all(seg, tone(3.0))) >= 1


class FakeTranscriber:
    def __init__(self, texts):
        self.texts, self.calls = list(texts), []

    def transcribe(self, audio):
        self.calls.append(len(audio))
        t = self.texts.pop(0)
        if isinstance(t, Exception):
            raise t
        return t


def test_listener_transcribes_in_its_own_thread_and_survives_errors():
    import threading
    audio = np.concatenate([quiet(0.5), tone(0.8), quiet(1.0), tone(0.8), quiet(1.0), tone(0.8), quiet(1.0)])
    chunks = [audio[i:i + 480] for i in range(0, len(audio), 480)]
    got, errors, threads = [], [], []
    fake = FakeTranscriber(["红色", RuntimeError("boom"), "停"])
    orig = fake.transcribe

    def spy(a):
        threads.append(threading.current_thread().name)
        return orig(a)
    fake.transcribe = spy
    listener = MicListener(fake, got.append, source=chunks, on_error=errors.append)
    listener.start()
    listener.join(5)
    assert got == ["红色", "停"]
    assert len(errors) == 1
    assert set(threads) == {"asr-worker"}


def test_read_wav_resamples_and_mixes(tmp_path):
    path = tmp_path / "x.wav"
    sr = 48000
    t = np.arange(sr) / sr
    stereo = np.stack([np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 440 * t)], axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((stereo * 0.5 * 32767).astype("<i2").tobytes())
    x = read_wav_16k_mono(path)
    assert x.dtype == np.float32 and abs(len(x) - SAMPLE_RATE) <= 1
    assert 0.45 < float(np.abs(x).max()) < 0.55
