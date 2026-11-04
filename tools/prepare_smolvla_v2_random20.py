#!/usr/bin/env python3
"""Freeze 20 random grid-centre tests and a one-page card; never access devices."""
import argparse
from collections import Counter
import csv
import hashlib
import itertools
import json
from pathlib import Path
import random
import shlex

from PIL import Image, ImageDraw, ImageFont

SOURCE = Path('/data/work/so101-evidence/real-robot/smolvla-v2-generalization16-20261104/collection-package')
OUTPUT = Path('/data/work/so101-evidence/real-robot/smolvla-v2-random20-20261104/collection-package')
SEED = 20261104
CELLS = ['B1', 'B2', 'B3', 'C2', 'C3', 'D3', 'D4']
MODEL_SHA = '16d9116230bf5bb8eba4f6a9c9bbf635df9f3d93869b04da3f66252ce3e44b85'
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
BOLD = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sampled_cases():
    rng = random.Random(SEED)
    layouts = rng.sample(list(itertools.permutations(CELLS, 2)), 20)
    colors = ['green'] * 10 + ['red'] * 10
    rng.shuffle(colors)
    return [(g, r, c) for (g, r), c in zip(layouts, colors)]


def render_cards(out, trials):
    # Match the existing paper orientation: D at top, A at bottom; columns 1..4.
    w, h = 2480, 3508
    image = Image.new('RGB', (w, h), 'white')
    draw = ImageDraw.Draw(image)

    def text(x, y, label, size=30, bold=False, fill='#202938', right=2390):
        font = ImageFont.truetype(BOLD if bold else FONT, size)
        if draw.textbbox((x, y), label, font=font)[2] > right:
            raise ValueError('Card text overflow: ' + label)
        draw.text((x, y), label, font=font, fill=fill)

    text(90, 35, 'SmolVLA v2 · 随机位置20例 · 单模型20k', 55, True)
    text(90, 120, '执行顺序：左列01-10自上而下，再右列11-20自上而下；与collect.py一致。', 32)
    text(90, 177, '范围：B1 / B2 / B3 / C2 / C3 / D3 / D4；两块不同格，20个不同双色布局。', 31)
    text(90, 231, '全部格中心：列偏移0 mm、行偏移0 mm、角度0°；碗、相机、灯光及批准初姿固定。', 30)
    text(90, 286, '红绿各10例；每条重新摆好两块、清空碗。结果填是/否/未知，所有失败保留。', 30)
    for i, trial in enumerate(trials):
        x = 90 + (i // 10) * 1170
        y = 360 + (i % 10) * 294
        width, height = 1135, 282
        draw.rounded_rectangle((x, y, x + width, y + height), 10, outline='#a6afbb', width=2)
        cn = '绿' if trial['color'] == 'green' else '红'
        text(x + 18, y + 7, f"{trial['id']:02d}  抓{cn}  ·  目标{trial['target']}", 38, True, right=x + 790)
        text(x + 18, y + 67, f"绿 {trial['green']}    红 {trial['red']}    格心0 / 0°", 33, right=x + 790)
        text(x + 18, y + 123, '稳定抓起____  首次抓起颜色____', 30, right=x + 790)
        text(x + 18, y + 172, '正确色抓起____  正确入碗____', 30, right=x + 790)
        text(x + 18, y + 222, '备注：____________________', 29, right=x + 790)
        gx, gy, s = x + 835, y + 35, 55
        # The bowl is a fixed-position reminder, not a new physical coordinate.
        draw.ellipse((gx - 74, gy + 84, gx - 18, gy + 140), outline='#667080', width=2)
        for rr, row in enumerate('DCBA'):
            for cc in range(4):
                cell = row + str(cc + 1)
                bx, by = gx + cc * s, gy + rr * s
                fill = '#148841' if cell == trial['green'] else '#cf3036' if cell == trial['red'] else '#ffffff'
                draw.rectangle((bx, by, bx + s, by + s), fill=fill, outline='#7e8795', width=2)
            text(gx + 225, gy + rr * s + 8, row, 23, right=x + width)
        for cc in range(4):
            text(gx + cc * s + 19, gy - 33, str(cc + 1), 24, right=x + width)
    text(90, 3320, '整批一次启动、模型只加载一次；每条前Enter确认。等回位并断连后再伸手重摆。', 30)
    text(90, 3375, '→结束当前条；Esc停止本轮并保留当前条；Ctrl-C结束整包。不要用←丢弃失败重录。', 29)
    text(90, 3430, f'seed={SEED}；七格离散域无放回抽样，非全工作区连续随机；本包尚未执行。', 28)
    image.save(out / 'random20-layout-cards.png')
    image.save(out / 'random20-layout-cards.pdf', resolution=300)
    preview = image.copy()
    preview.thumbnail((1600, 1600))
    preview.save(out / 'random20-layout-cards-preview.png')


def prepare(out):
    out = out.resolve()
    if out.exists():
        raise FileExistsError(f'Refuse overwrite: {out}')
    source = json.loads((SOURCE / 'plan.json').read_text())
    assert source['model_sha256'] == MODEL_SHA
    assert digest(Path(source['model']) / 'model.safetensors') == MODEL_SHA
    source_files = [SOURCE / 'plan.json', SOURCE / 'collect.py', SOURCE / 'INSTRUCTIONS.md']
    source_hashes = {str(p): digest(p) for p in source_files}
    seed = source['trials'][0]
    trials = []
    for identifier, (green, red, color) in enumerate(sampled_cases(), 1):
        name = f'eval-smolvla-v2-random20-t{identifier:02d}-{color}-20261104'
        recording = str(out / 'recordings' / f'trial-{identifier:02d}')
        env = dict(seed['env'], INFERENCE_RECORDING_PATH=recording, TASK=f'Put the {color} cube into the paper bowl')
        argv = [seed['argv'][0], name, '1', source['model']]
        trials.append(dict(id=identifier, trial=1, group='random-grid-centres', layout_id=identifier,
                           layout=f'G {green}/R {red}', green=green, red=red, color=color,
                           target=green if color == 'green' else red,
                           green_dx_mm=0, green_dy_mm=0, green_yaw_deg=0,
                           red_dx_mm=0, red_dy_mm=0, red_yaw_deg=0,
                           dataset=name, dataset_path='/data/work/so101-datasets/' + name,
                           episode_index=0, recording_path=recording, env=env, argv=argv,
                           command=shlex.join(['env', *[k + '=' + v for k, v in env.items()], *argv])))
    assert len(trials) == len({(t['green'], t['red']) for t in trials}) == 20
    assert Counter(t['color'] for t in trials) == {'green': 10, 'red': 10}
    for trial in trials:
        for key in ('dataset_path', 'recording_path'):
            if Path(trial[key]).exists():
                raise FileExistsError(f'Fresh path required: {trial[key]}')
    hashes = {path: digest(path) for path in source['sha256']}
    hashes.update(source_hashes)
    hashes[str(Path(__file__).resolve())] = digest(Path(__file__).resolve())
    plan = dict(suite='v2-random20', status='not_run', repo=source['repo'], model=source['model'],
                model_sha256=MODEL_SHA, sha256=hashes, parameters=source['parameters'],
                purpose='20 distinct random grid-centre layouts, balanced target colors; position screening, not training demonstrations',
                sampling=dict(seed=SEED, implementation='Python random.Random: sample(permutations(cells,2),20), then shuffle([green]*10+[red]*10)',
                              cells=CELLS, candidate_order='itertools.permutations(CELLS,2)', candidate_count=42,
                              layouts='uniform sample without replacement of 20 ordered (green, red) layouts',
                              colors='balanced random permutation, 10 green and 10 red, assigned after layout draw',
                              offsets_mm=[0, 0], yaw_deg=0, paired_repeats=False,
                              limitation='Seven previously exercised grid centres only; not continuous full-workspace iid; grid combinations may be new'),
                source_plan=str(SOURCE / 'plan.json'), trials=trials)
    out.mkdir(parents=True, exist_ok=False)
    (out / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    (out / 'collect.py').write_text((SOURCE / 'collect.py').read_text())
    fields = ['id', 'layout', 'green', 'red', 'color', 'target', 'dataset', 'episode_index', 'status',
              'initial_pose', 'any_stable_lift', 'first_stable_lift_color', 'first_stable_lift_target_correct',
              'correct_color_stable_lift', 'no_lift', 'first_attempt_lift', 'retries', 'target_final_in_bowl',
              'wrong_color_deposit', 'elapsed_time_s', 'safety_stop', 'aborted', 'reason', 'recording_path', 'preflight_path', 'notes']
    with (out / 'results.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({**{k: t[k] for k in fields if k in t}, 'status': 'not_run'} for t in trials)
    source_md = (SOURCE / 'INSTRUCTIONS.md').read_text()
    safety = source_md[source_md.index('collect.py自动切换'):source_md.index('| ID |')]
    md = f'''# v2 随机位置20例：操作者执行包

固定seed={SEED}，在已实际测试的七格 B1/B2/B3/C2/C3/D3/D4 中，将绿、红放在不同格。按上述格列表构造42个有序双色布局，Python random.Random(seed).sample无放回抽20个；随后同一随机数流shuffle红绿各10条的目标序列。20个布局全部不同，不做同布局双色配对或重复；不是全工作区连续均匀iid，不覆盖七格外或格内偏移的成功率。

全部格中心列/行偏移0 mm、角度0°，方块边平行格线。七格分别有历史实测证据，新的跨格组合仍可能失败。碗、相机、灯光、纸垫及同一批准机械臂/腕部/夹爪初姿沿用。只随机位置，保留位置与颜色分别可分析；不声称统计可靠率或未经验证的空间外推。v2 final20k SHA256={MODEL_SHA}。本包尚未真机执行，结果均not_run。

```bash
python3 {shlex.quote(str(out / 'collect.py'))}  # 只显示20条计划，不接设备
python3 {shlex.quote(str(out / 'collect.py'))} --execute  # 操作者在场，本地前台一次执行整批
```

''' + safety
    md += '| ID | 绿块 | 红块 | 目标色 | 目标格 | dataset（episode0） |\n|---:|---|---|---|---|---|\n'
    for t in trials:
        md += f'| {t["id"]:02d} | {t["green"]} | {t["red"]} | {"绿" if t["color"] == "green" else "红"} | {t["target"]} | `{t["dataset"]}` |\n'
    md += '''
PDF一页20条：左列01-10从上往下，再右列11-20从上往下，与命令完全同序。图在每卡右侧，D在上、A在下，列号1至4；圆圈只提醒碗位固定，不重新定义碗坐标。本轮没有非零偏移或角度，若以后改变条件，必须另建计划并在卡片上红色加粗，不能临场修改本计划。

填写results.csv时区分：any_stable_lift为任意色是否稳定抓起；first_stable_lift_color记录首次稳定抓起颜色（green/red/none/unknown）；first_stable_lift_target_correct记录首次稳定抓起颜色是否匹配目标；correct_color_stable_lift为整条是否曾稳定抓起正确色；target_final_in_bowl为正确目标最终是否入碗。稳定抓起须明确离桌并由夹爪持续持住，瞬间接触、推块或夹空不能算；不确定填unknown。首次颜色判断与整条曾抓对颜色不能混为一项。另保留无抓起、首次尝试、重试、错色入碗、用时、中止和安全停止。

报告任意色稳定抓起/全部尝试、正确色稳定抓起/全部尝试、正确入碗/全部尝试（全批完成为20，分色各10），另报首次稳定抓起颜色正确/有首次稳定抓起的尝试及no_lift。失败、错色和安全停止必须保留，unknown单列，不删失败、不用成功补跑替代、不与旧批合并；提前停止则同时报告已开始条数与未执行条数，不伪称20条完成。执行完整、记录完整和人工任务结果分别判断。

整批只用collect.py；plan.json逐条命令用于审计，逐条运行会重复加载模型。每条独立新dataset episode0，recordings/trial-XX存诊断，trial-XX-execution.json存回执，terminal-logs存原输出，预检路径见回执。status.json.complete=false或缺失不可当完整重放。全部完成后一次性交回包路径及CSV；仅生成文件，不自动执行或打印。
'''
    (out / 'INSTRUCTIONS.md').write_text(md)
    render_cards(out, trials)
    assert {str(p): digest(p) for p in source_files} == source_hashes
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    print(prepare(parser.parse_args().output))
