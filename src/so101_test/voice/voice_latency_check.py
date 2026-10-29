"""P6：两个策略同时在 GPU 上，用数据集回放的画面测单步推理耗时（不连硬件）。

用法（语音 venv）：
  /data/work/venvs/so101-voice-lerobot-061/bin/python voice_latency_check.py \
      --green-policy ... --red-policy ... --green-root ... --red-root ... [--repeats 3]
ACT 每 n_action_steps 步才真正算一次（其余步骤只从队列取动作），所以分开报告：
  all steps（每个控制拍）、chunk steps（真正跑网络的那拍）、queue steps（只取队列的那拍）。
"""
import argparse
import json
import statistics
import time


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))] * 1000 if s else float("nan")


def summarize(values):
    return {"n": len(values), "p50_ms": round(pct(values, 0.5), 2), "p99_ms": round(pct(values, 0.99), 2),
            "max_ms": round(max(values) * 1000, 2) if values else None,
            "mean_ms": round(statistics.fmean(values) * 1000, 2) if values else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--green-policy", required=True)
    ap.add_argument("--red-policy", required=True)
    ap.add_argument("--green-root", required=True)
    ap.add_argument("--red-root", required=True)
    ap.add_argument("--episode", type=int, default=2)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import torch
    from .voice_fake_robot import DatasetReplayRobot
    from .voice_policy import TASKS, LoadedPolicy

    policies = {c: LoadedPolicy(c, p, TASKS[c], "cuda") for c, p in (("green", args.green_policy), ("red", args.red_policy))}
    robot = DatasetReplayRobot({"green": args.green_root, "red": args.red_root}, episode=args.episode)
    for p in policies.values():
        p.bind(robot)
    robot.start_replay("green")
    for p in policies.values():
        p.warmup(robot.peek_first())
    mem = {"allocated_mib": round(torch.cuda.memory_allocated() / 2**20, 1),
           "reserved_mib": round(torch.cuda.memory_reserved() / 2**20, 1),
           "max_allocated_mib": round(torch.cuda.max_memory_allocated() / 2**20, 1)}

    result = {"memory_both_loaded": mem, "n_action_steps": {c: p.cfg.n_action_steps for c, p in policies.items()}}
    switch_first_step = {}
    order = ["green", "red"] * args.repeats
    per = {c: {"all": [], "chunk": [], "queue": []} for c in policies}
    for colour in order:
        pol = policies[colour]
        robot.start_replay(colour)
        n_chunk = pol.cfg.n_action_steps
        t0 = time.perf_counter()
        pol.reset()                       # what the runner does at the start of every run
        obs = robot.get_observation()
        pol.act(obs)
        switch_first_step.setdefault(colour, []).append(time.perf_counter() - t0)
        robot.start_replay(colour)
        pol.reset()
        for i in range(len(robot.replays[colour])):
            obs = robot.get_observation()
            torch.cuda.synchronize()
            t = time.perf_counter()
            pol.act(obs)
            torch.cuda.synchronize()
            dt = time.perf_counter() - t
            per[colour]["all"].append(dt)
            per[colour]["chunk" if i % n_chunk == 0 else "queue"].append(dt)
    result["per_policy"] = {c: {k: summarize(v) for k, v in d.items()} for c, d in per.items()}
    result["first_step_after_switch_ms"] = {c: [round(x * 1000, 1) for x in v] for c, v in switch_first_step.items()}
    result["budget_ms_at_20hz"] = 50.0
    result["memory_after_runs"] = {"max_allocated_mib": round(torch.cuda.max_memory_allocated() / 2**20, 1)}
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.out:
        open(args.out, "w").write(text + "\n")


if __name__ == "__main__":
    main()
