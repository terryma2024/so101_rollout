"""本地语音识别：麦克风流 -> 能量分段 -> faster-whisper（独立线程，不阻塞 20 Hz 控制循环）。

- EnergySegmenter：纯 numpy，按帧能量切句，静音 SILENCE_S（默认 0.6 s）结束一句。
- WhisperTranscriber：faster-whisper small，CUDA int8_float16。
- MicListener：sounddevice 16 kHz 单声道输入流，回调只入队；分段和识别都在 worker 线程里做。
sounddevice 只在真正开麦克风时才导入（系统没有 libportaudio 时用 PORTAUDIO_LIB 指向的副本）。
"""
import ctypes.util
import os
import queue
import threading
import wave

import numpy as np

SAMPLE_RATE = 16000
DEFAULT_MODEL_DIR = "/data/work/models/faster-whisper-small"
DEFAULT_PORTAUDIO = "/data/work/models/portaudio/usr/lib/x86_64-linux-gnu/libportaudio.so.2"


class EnergySegmenter:
    """Cut a continuous 16 kHz mono float32 stream into utterances.

    A frame is speech when its RMS exceeds max(min_rms, noise_factor * noise_floor); the noise floor is a slow
    average of non-speech frames. An utterance ends after `silence_s` of non-speech; utterances shorter than
    `min_speech_s` of speech are dropped (clicks); `max_s` force-closes a very long one. `pre_roll_s` of audio
    before the first speech frame is kept so the first syllable is not clipped.
    """

    def __init__(self, sample_rate=SAMPLE_RATE, frame_s=0.03, min_rms=0.01, noise_factor=3.0, silence_s=0.6,
                 min_speech_s=0.25, max_s=15.0, pre_roll_s=0.3):
        self.sr = sample_rate
        self.frame = int(sample_rate * frame_s)
        self.min_rms, self.noise_factor = min_rms, noise_factor
        self.silence_frames = max(1, round(silence_s / frame_s))
        self.min_speech_frames = max(1, round(min_speech_s / frame_s))
        self.max_frames = round(max_s / frame_s)
        self.pre_roll_frames = round(pre_roll_s / frame_s)
        self.noise_floor = 0.0
        self._buf = np.zeros(0, np.float32)
        self._pre = []          # recent non-speech frames
        self._cur = None        # frames of the utterance in progress
        self._speech = 0
        self._quiet = 0

    def _is_speech(self, rms):
        return rms > max(self.min_rms, self.noise_factor * self.noise_floor)

    def feed(self, samples):
        """Add samples, return the list of finished utterances (float32 arrays), possibly empty."""
        self._buf = np.concatenate([self._buf, np.asarray(samples, np.float32).reshape(-1)])
        done = []
        while len(self._buf) >= self.frame:
            fr, self._buf = self._buf[:self.frame], self._buf[self.frame:]
            rms = float(np.sqrt(np.mean(fr * fr)))
            speech = self._is_speech(rms)
            if self._cur is None:
                if speech:
                    self._cur = list(self._pre) + [fr]
                    self._pre, self._speech, self._quiet = [], 1, 0
                else:
                    self.noise_floor = rms if self.noise_floor == 0.0 else 0.95 * self.noise_floor + 0.05 * rms
                    self._pre.append(fr)
                    self._pre = self._pre[-self.pre_roll_frames:] if self.pre_roll_frames else []
                continue
            self._cur.append(fr)
            if speech:
                self._speech += 1
                self._quiet = 0
            else:
                self._quiet += 1
            if self._quiet >= self.silence_frames or len(self._cur) >= self.max_frames:
                if self._speech >= self.min_speech_frames:
                    done.append(np.concatenate(self._cur))
                self._cur, self._speech, self._quiet = None, 0, 0
        return done


CUDA12_LIBS = "/data/work/models/cuda12-libs/nvidia"


def preload_cuda12_libs(base=None):
    """ctranslate2 (faster-whisper) is built against CUDA 12 while this venv's torch ships CUDA 13: load the
    CUDA 12 cublas/cudnn copies (installed with `uv pip install --target`) into the process first."""
    import ctypes
    import glob
    base = base or os.environ.get("VOICE_CUDA12_LIBS", CUDA12_LIBS)
    for pattern in ("cublas/lib/libcublasLt.so.12", "cublas/lib/libcublas.so.12", "cudnn/lib/libcudnn.so.9"):
        for path in glob.glob(os.path.join(base, pattern)):
            ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)


class WhisperTranscriber:
    """faster-whisper wrapper; transcribe(float32 16 kHz mono) -> str."""

    def __init__(self, model_dir=DEFAULT_MODEL_DIR, device="cuda", compute_type="int8_float16", language=None):
        if device == "cuda":
            preload_cuda12_libs()
        from faster_whisper import WhisperModel
        self.model = WhisperModel(model_dir, device=device, compute_type=compute_type)
        self.language = language

    def transcribe(self, audio):
        segments, _info = self.model.transcribe(np.asarray(audio, np.float32), language=self.language,
                                                beam_size=5, vad_filter=False, condition_on_previous_text=False)
        return "".join(s.text for s in segments).strip()


def read_wav_16k_mono(path):
    """Read a PCM wav with the stdlib, mix to mono, linearly resample to 16 kHz, float32 in [-1, 1]."""
    with wave.open(str(path), "rb") as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if sw == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    elif sw == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648.0
    elif sw == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError(f"不支持的 wav 位宽 {sw * 8}")
    x = x.reshape(-1, ch).mean(axis=1)
    if sr != SAMPLE_RATE and len(x):
        t_new = np.arange(int(len(x) * SAMPLE_RATE / sr)) * (sr / SAMPLE_RATE)
        x = np.interp(t_new, np.arange(len(x)), x).astype(np.float32)
    return x.astype(np.float32)


def _import_sounddevice():
    lib = os.environ.get("PORTAUDIO_LIB", DEFAULT_PORTAUDIO)
    original = ctypes.util.find_library
    if os.path.exists(lib):
        ctypes.util.find_library = lambda name: lib if name == "portaudio" else original(name)
    try:
        import sounddevice
        return sounddevice
    finally:
        ctypes.util.find_library = original


class MicListener:
    """Audio in -> segmenter -> transcriber -> on_text(text), all off the caller's thread.

    `source` is only used by tests: an iterable of float32 chunks replacing the microphone. With source=None the
    sounddevice InputStream (16 kHz mono) is opened on start().
    """

    def __init__(self, transcriber, on_text, segmenter=None, device=None, source=None, on_error=None):
        self.transcriber, self.on_text = transcriber, on_text
        self.segmenter = segmenter or EnergySegmenter()
        self.device, self.source, self.on_error = device, source, on_error
        self._q = queue.Queue()
        self._stop = threading.Event()
        self._thread = None
        self._stream = None
        self._feeder = None

    def start(self):
        if self.source is None:
            sd = _import_sounddevice()
            self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", device=self.device,
                                          blocksize=int(SAMPLE_RATE * 0.03),
                                          callback=lambda indata, frames, t, status: self._q.put(indata[:, 0].copy()))
            self._stream.start()
        else:
            self._feeder = threading.Thread(target=self._feed_source, daemon=True, name="asr-source")
            self._feeder.start()
        self._thread = threading.Thread(target=self._work, daemon=True, name="asr-worker")
        self._thread.start()

    def _feed_source(self):
        for chunk in self.source:
            if self._stop.is_set():
                break
            self._q.put(np.asarray(chunk, np.float32))
        self._q.put(None)

    def _work(self):
        while not self._stop.is_set():
            try:
                chunk = self._q.get(timeout=0.1)
            except queue.Empty:
                continue
            if chunk is None:
                break
            for seg in self.segmenter.feed(chunk):
                try:
                    text = self.transcriber.transcribe(seg)
                except Exception as error:  # noqa: BLE001 - a bad utterance must not kill the listener
                    if self.on_error:
                        self.on_error(error)
                    continue
                self.on_text(text)

    def join(self, timeout=None):
        """Wait until a finite `source` is fully processed (tests)."""
        if self._thread:
            self._thread.join(timeout)

    def stop(self):
        self._stop.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
        if self._thread:
            self._thread.join(2.0)
