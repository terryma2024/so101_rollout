#!/usr/bin/env python3
"""Freeze the approved v2 24-trial screening; preparation never opens devices."""
import argparse
from collections import Counter
from contextlib import redirect_stdout
import csv
import io
import json
from pathlib import Path
import shlex
import sys
import tempfile

import prepare_smolvla_baseline_collection as baseline

MODEL = Path('/data/work/so101-policies/real-smolvla-red-green-v2-local-20261103/checkpoints/020000/pretrained_model')
MODEL_SHA = '16d9116230bf5bb8eba4f6a9c9bbf635df9f3d93869b04da3f66252ce3e44b85'
OUTPUT = Path('/data/work/so101-evidence/real-robot/smolvla-v2-generalization24-20261104/collection-package')
LAYOUTS = [('C2', 'C3'), ('C3', 'C2'), ('B2', 'B3'), ('B3', 'B2'), ('B1', 'C3'), ('C3', 'B1')]
ORDER = [1, 3, 4, 2, 5, 6]  # Baselines interspersed in both complete rounds.


def prepare(out):
    out = out.resolve()
    if out.exists():
        raise FileExistsError(f'Refuse overwrite: {out}')
    # Reuse the original generator's frozen inputs, environment and launcher;
    # only this task's manifest, result columns and operator text differ.
    original_model, original_sha, original_argv = baseline.MODEL, baseline.MODEL_SHA, sys.argv
    try:
        with tempfile.TemporaryDirectory(prefix='smolvla-v2-generalization24-') as temp:
            template = Path(temp) / 'template'
            baseline.MODEL, baseline.MODEL_SHA = MODEL, MODEL_SHA
            sys.argv = [str(Path(baseline.__file__)), '--output', str(template), '--suite', 'other-positions', '--session', '20261104']
            with redirect_stdout(io.StringIO()):
                baseline.main()
            plan = json.loads((template / 'plan.json').read_text())
            launcher = (template / 'collect.py').read_text()
    finally:
        baseline.MODEL, baseline.MODEL_SHA, sys.argv = original_model, original_sha, original_argv
    seed = plan['trials'][0]
    trials = []
    for repeat in (1, 2):
        for position, layout_id in enumerate(ORDER):
            colors = ['green', 'red'] if (position + repeat) % 2 else ['red', 'green']
            for color in colors:
                identifier = len(trials) + 1
                green, red = LAYOUTS[layout_id - 1]
                name = f'eval-smolvla-v2-generalization24-l{layout_id}-{color}-r{repeat}-20261104'
                recording = out / 'recordings' / f'trial-{identifier:02d}'
                env = dict(seed['env'], INFERENCE_RECORDING_PATH=str(recording), TASK=f'Put the {color} cube into the paper bowl')
                argv = [seed['argv'][0], name, '1', str(MODEL)]
                trials.append(dict(id=identifier, round=repeat, trial=repeat, group='baseline' if layout_id <= 2 else 'novel', layout_id=layout_id, layout=f'G {green}/R {red}', green=green, red=red, color=color, target=green if color == 'green' else red, green_dx_mm=0, green_dy_mm=0, green_yaw_deg=0, red_dx_mm=0, red_dy_mm=0, red_yaw_deg=0, dataset=name, dataset_path='/data/work/so101-datasets/' + name, episode_index=0, recording_path=str(recording), env=env, argv=argv, command=shlex.join(['env', *[k + '=' + v for k, v in env.items()], *argv])))
    assert len(trials) == 24
    assert Counter((t['layout_id'], t['color']) for t in trials) == {(layout, color): 2 for layout in range(1, 7) for color in ['green', 'red']}
    for t in trials:
        for path in [t['dataset_path'], t['recording_path'], out / f"trial-{t['id']:02d}-execution.json"]:
            if Path(path).exists():
                raise FileExistsError(f'Fresh path required: {path}')
    plan.update(suite='v2-generalization24', status='not_run', purpose='24-trial composition-generalization screening; 8 baseline and 16 novel-combination attempts; not a reliability estimate or training demonstrations', source_plan=str(Path(__file__).resolve().parents[1] / 'docs/superpowers/plans/2026-11-04-smolvla-v2-generalization24.md'), trials=trials)
    for path in [Path(__file__).resolve(), Path(plan['source_plan'])]:
        plan['sha256'][str(path)] = baseline.digest(path)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    (out / 'collect.py').write_text(launcher)
    fields = ['id', 'round', 'group', 'layout_id', 'layout', 'color', 'trial', 'dataset', 'episode_index', 'status', 'initial_pose', 'target_correct', 'first_contact', 'first_stable_lift_color', 'no_lift', 'first_attempt_lift', 'retries', 'target_final_in_bowl', 'wrong_color_deposit', 'elapsed_time_s', 'safety_stop', 'aborted', 'reason', 'recording_path', 'preflight_path', 'notes']
    with (out / 'results.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({**{k: t[k] for k in fields if k in t}, 'status': 'not_run'} for t in trials)
    md = '''# v2 泛化24条：操作者执行包

v2 20k；两轮各12条，8条原布局基线、16条新组合。每个布局/目标色两次，第二轮反转同布局双色顺序；基线穿插。全部格中心0mm、方块0°；纸碗、相机、光照固定，恢复同一批准机械臂初姿、腕部姿态和夹爪开度。仅筛查组合泛化，不宣称超出训练空间范围的外推或可靠率；不是训练示范。所有真实任务尚未执行，results.csv 为 not_run。

```bash
'''
    md += f'python3 {shlex.quote(str(out / "collect.py"))}  # 仅打印24条计划\npython3 {shlex.quote(str(out / "collect.py"))} --execute  # 用户在场、本地前台终端执行\n```\n\n'
    md += '''collect.py自动切换到固定so101-smolvla-061环境，无需activate。整轮仅加载一次模型，无需手动加载；每条独立新dataset（episode0），20Hz hard async、horizon50/prefetch10/MAX_REL30、30秒。每条前本地Enter确认；上一worker停止、设备断连后才等待下一条，不会自动进入下一条。每条（含相邻双色）都重新摆好两块、碗及批准初姿。正常teardown默认约3秒回该条startup姿态后断连，等动作结束再伸手。不能将异常后的回初姿视作已完成或安全保证。

原有预检/停止逻辑保持：相机锁定并通过预检后才接机器人；操作者核对双相机640×480、映射、对齐、光照、校准、初姿、空间和本地停止入口。→提前结束当前条，Esc停本轮并保留当前条；←会丢弃重录，勿用于保留失败。Ctrl-C结束整个包。按键依赖现有listener及本地桌面焦点/pynput，SSH按键不保证生效。异常阶跃、碰推、错目标、无效折叠、持续顶紧或过载时本地停止并保留失败，排查后再决定后续；不要盲目续跑，不要求带电硬掰或自动开爪。

只在条间输入q正常退出且前序完整回执齐全时，才用 `--execute --start-trial N` 从明确未执行条恢复。恢复核验plan SHA、记录、dataset meta、终端日志；剩余路径必须全新。Esc/异常/半条不自动覆盖或跳过。首次准备和执行均拒绝覆盖已有数据。

| ID | 轮 | 组 | 布局（绿/红） | 目标 | 目标格 | dataset（episode0） |
|---:|---:|---|---|---|---|---|
'''
    for t in trials:
        md += f'| {t["id"]:02d} | {t["round"]} | {"基线" if t["group"] == "baseline" else "新组合"} | {t["layout"]} | {"绿" if t["color"] == "green" else "红"} | {t["target"]} | `{t["dataset"]}` |\n'
    md += '''
整轮执行用上方collect.py；plan.json逐条命令仅作参数审计，逐条运行会重复加载模型。结果位于 `/data/work/so101-datasets/<dataset>/`，诊断在本包 `recordings/trial-XX/`，执行回执 `trial-XX-execution.json`，原输出 `terminal-logs/`，预检路径写入回执。`status.json.complete=false`或缺失表示记录不完整，不可当完整重放。

填写results.csv：最终目标色入碗/全部尝试；首次稳定夹起颜色/有稳定夹起尝试，另报no_lift；首次夹起、重试次数、错色入碗、耗时、安全停止。基线和每个新布局/目标色分别报告，失败保留在分母，unknown如实填写。执行完整、记录完整、人工任务结果分别判断。全部完成后一次性交回包路径与CSV；本包不生成PDF、不打印。
'''
    (out / 'INSTRUCTIONS.md').write_text(md)
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    print(prepare(parser.parse_args().output))
