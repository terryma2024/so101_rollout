"""语音/键盘选择红、绿 ACT 抓取策略的常驻 agent（只用 LeRobot，不用 ROS）。

两个策略启动时一次性加载到 GPU，之后说“红色”/“绿色”（或键盘输入 红 / 绿 回车）就切换，不重新加载。
  停 / stop       随时停下并回休息位        回去 / 复位 / home  回休息位
  q / quit        停下、回休息位、断开后退出  （stdin 结束 = 做完手头的任务再退出）
执行中收到新的颜色指令会被拒绝，只有“停”能打断。休息位 = 启动时手臂所在的姿态（可用 --rest 覆盖）。

真机：./voice_agent.sh                      （人必须在机械臂旁边）
离线演练：./voice_agent.sh --fake-robot green=<数据集根> --fake-robot red=<数据集根>   （不碰任何硬件）
"""
import argparse
import datetime
import json
import os
import pathlib
import signal
import sys
import threading
import time

from voice_intent import GREEN, HOME, RED, STOP, UNCLEAR, UNCLEAR_HINT, parse_intent
from voice_runner import IDLE, KEYS, VoiceRunner

POLICIES = "/data/work/so101-policies"
DEFAULT_POLICY = {
    "green": f"{POLICIES}/real-act-002-20261028/checkpoints/100000/pretrained_model",
    # REAL-ACT-RED 还在训练：先用 REAL-ACT-001 顶替，训练完用 --red-policy 或 VOICE_RED_POLICY 指向
    # real-act-red-20261028/checkpoints/100000/pretrained_model
    "red": f"{POLICIES}/real-act-001-20261027T1007Z/checkpoints/100000/pretrained_model",
}
QUIT_WORDS = {"q", "quit", "exit", "退出", "退出程序"}


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--green-policy", default=os.environ.get("VOICE_GREEN_POLICY", DEFAULT_POLICY["green"]))
    p.add_argument("--red-policy", default=os.environ.get("VOICE_RED_POLICY", DEFAULT_POLICY["red"]))
    p.add_argument("--device", default="cuda")
    p.add_argument("--fps", type=int, default=20)
    p.add_argument("--max-rel", type=float, default=float(os.environ.get("MAX_REL", 30)),
                   help="max_relative_target（度），和 rollout.sh 一样默认 30")
    p.add_argument("--timeout", type=float, default=30.0, help="单次执行超时（秒）")
    p.add_argument("--return-s", type=float, default=2.0, help="回休息位的插值时间（秒）")
    p.add_argument("--rest", default=None, help="休息位，6 个数（度，顺序 肩旋转,肩抬,肘,腕弯,腕转,夹爪）；默认启动时的姿态")
    p.add_argument("--record", default=None, metavar="NAME", help="每次执行存成 /data/work/so101-datasets/NAME 的一条评估数据")
    p.add_argument("--record-root", default="/data/work/so101-datasets", help="--record 数据集所在目录")
    p.add_argument("--asr", dest="asr", action="store_true", default=False, help="打开麦克风语音识别")
    p.add_argument("--no-asr", dest="asr", action="store_false")
    p.add_argument("--asr-model", default="/data/work/models/faster-whisper-small")
    p.add_argument("--asr-device", default="cuda")
    p.add_argument("--asr-language", default=None, help="固定识别语言（zh / en）；默认自动判断")
    p.add_argument("--asr-min-rms", type=float, default=0.01, help="能量分段的最低 RMS 阈值（麦克风很轻时调低）")
    p.add_argument("--mic", default=None, help="sounddevice 输入设备名或编号")
    p.add_argument("--fake-robot", action="append", default=[], metavar="[COLOUR=]ROOT",
                   help="离线演练：从数据集回放画面和状态，不连任何硬件；可重复，COLOUR=red|green，不写颜色则两种颜色共用")
    p.add_argument("--fake-episode", type=int, default=2, help="离线演练回放数据集里的第几条 episode")
    p.add_argument("--log-dir", default=os.environ.get("VOICE_LOG_DIR"), help="JSONL 日志目录")
    return p


def parse_fake_roots(specs):
    roots = {}
    for spec in specs:
        colour, sep, root = spec.partition("=")
        if sep and colour in ("red", "green"):
            roots[colour] = root
        else:
            roots.setdefault("green", spec)
            roots.setdefault("red", spec)
    return {c: roots[c] for c in ("green", "red") if c in roots}


def parse_rest(text):
    vals = [float(x) for x in text.split(",")]
    if len(vals) != 6:
        raise SystemExit("--rest 需要 6 个数")
    return dict(zip(KEYS, vals))


class JsonlLog:
    def __init__(self, directory):
        directory = pathlib.Path(directory or f"/data/work/so101-evidence/real-robot/voice-agent-{datetime.date.today():%Y%m%d}/logs")
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"voice-agent-{datetime.datetime.now():%Y%m%dT%H%M%S}.jsonl"
        self._f = open(self.path, "a", buffering=1)
        self._lock = threading.Lock()

    def __call__(self, event):
        with self._lock:
            self._f.write(json.dumps({"t": datetime.datetime.now().isoformat(timespec="milliseconds"), **event},
                                     ensure_ascii=False) + "\n")

    def close(self):
        self._f.close()


def say(msg):
    print(msg, flush=True)


def main(argv=None):
    # LeRobot encodes video in a ProcessPoolExecutor; forking from this multi-threaded, CUDA-holding process
    # deadlocks the workers, so use spawn (found in the P6 --record dry run).
    import multiprocessing
    multiprocessing.set_start_method("spawn", force=True)
    args = build_parser().parse_args(argv)
    from voice_policy import TASKS, EpisodeRecorder, LoadedPolicy, make_real_follower, read_arms_env

    log = JsonlLog(args.log_dir)
    say(f"日志：{log.path}")
    log({"event": "start", "argv": sys.argv[1:], "args": vars(args)})

    fake_roots = parse_fake_roots(args.fake_robot)
    if args.red_policy == DEFAULT_POLICY["red"]:
        say("提示：红色策略目前是 REAL-ACT-001 顶替品；REAL-ACT-RED 训练完用 --red-policy 指定")

    # --- policies first (a bad path fails before touching hardware) ---
    import torch
    policies = {}
    for colour, path in (("green", args.green_policy), ("red", args.red_policy)):
        t0 = time.perf_counter()
        policies[colour] = LoadedPolicy(colour, path, TASKS[colour], args.device)
        dt = time.perf_counter() - t0
        say(f"已加载 {colour} 策略（{dt:.1f} 秒）：{path}")
        log({"event": "policy_loaded", "colour": colour, "path": path, "load_s": round(dt, 2)})
    if args.device.startswith("cuda"):
        mem = torch.cuda.memory_allocated() / 2**20
        say(f"GPU 显存（两个策略）：{mem:.0f} MiB 已分配")
        log({"event": "gpu_memory", "allocated_mib": round(mem, 1)})

    # --- robot ---
    if fake_roots:
        from voice_fake_robot import DatasetReplayRobot
        say("离线演练模式：不连接任何硬件，画面和状态来自数据集")
        robot = DatasetReplayRobot(fake_roots, episode=args.fake_episode)
        robot.start_replay("green")
    else:
        env = read_arms_env()
        robot = make_real_follower(env, args.max_rel)
        robot.connect()
        say("已连接从臂和相机")
    recorder = None
    runner = None
    try:
        for pol in policies.values():
            pol.bind(robot)
        first = robot.get_observation() if not fake_roots else robot.peek_first()
        rest = parse_rest(args.rest) if args.rest else {k: first[k] for k in KEYS}
        say("休息位：" + ", ".join(f"{k}={v:.1f}" for k, v in rest.items()))
        log({"event": "rest", "rest": rest})
        for pol in policies.values():
            pol.warmup(first)
        if args.record:
            recorder = EpisodeRecorder(robot, args.record, fps=args.fps, root_base=args.record_root)
            say(f"评估数据保存到 {recorder.root}")
        runner = VoiceRunner(robot, policies, TASKS, rest, fps=args.fps, timeout_s=args.timeout,
                             return_s=args.return_s, say=say, event=log, recorder=recorder,
                             on_run_start=getattr(robot, "start_replay", None) if fake_roots else None)
        run_loop(args, runner, log, say)
    finally:
        if recorder is not None:
            recorder.close()
        try:
            robot.disconnect()
        except Exception as error:  # noqa: BLE001
            say(f"断开机器人出错：{error!r}")
        log({"event": "exit", "history": list(runner.history) if runner else []})
        log.close()
        say("已退出")


def handle_text(runner, log, text, source):
    text = text.strip()
    if not text:
        return
    if text.lower() in QUIT_WORDS:
        log({"event": "input", "source": source, "text": text, "intent": "quit"})
        runner.submit("quit")
        return
    intent = parse_intent(text)
    log({"event": "input", "source": source, "text": text, "intent": intent})
    say(f"[{source}] {text!r} -> {intent}")
    if intent in (RED, GREEN):
        runner.submit("run", intent)
    elif intent == STOP:
        runner.submit("stop")
    elif intent == HOME:
        runner.submit("home")
    elif intent == UNCLEAR:
        say(UNCLEAR_HINT)


def run_loop(args, runner, log, say):
    from lerobot.utils.robot_utils import precise_sleep

    def stdin_thread():
        for line in sys.stdin:
            handle_text(runner, log, line, "键盘")
        # stdin closed (piped script): finish what is running, then quit
        for _ in range(2):
            while not (runner._cmds.empty() and runner.state == IDLE):
                time.sleep(0.1)
            time.sleep(0.3)
        runner.submit("quit")

    threading.Thread(target=stdin_thread, daemon=True, name="stdin").start()

    listener = None
    if args.asr:
        from voice_asr import EnergySegmenter, MicListener, WhisperTranscriber
        say("加载语音识别模型 ...")
        transcriber = WhisperTranscriber(args.asr_model, args.asr_device, language=args.asr_language)
        listener = MicListener(transcriber, lambda text: handle_text(runner, log, text, "语音"), device=args.mic,
                               segmenter=EnergySegmenter(min_rms=args.asr_min_rms),
                               on_error=lambda e: say(f"识别出错：{e!r}"))
        listener.start()
        say("麦克风已打开，请说“红色”/“绿色”/“停”")

    sigints = []

    def on_sigint(signum, frame):
        sigints.append(1)
        if len(sigints) == 1:
            say("收到 Ctrl-C：停止策略，回休息位，再退出（再按一次强制退出）")
            runner.submit("quit")
        else:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, on_sigint)
    say("就绪。输入 红 / 绿 / 停 / q（回车），或开 --asr 用语音。")
    try:
        runner.run_forever(sleep=precise_sleep)
    finally:
        if listener:
            listener.stop()


if __name__ == "__main__":
    main()
