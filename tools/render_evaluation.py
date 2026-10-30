"""Render the historical P0 A4 layout and six record sheets; never print.

Red-target rounds swap the physical cube colors, retaining the original green
layout cell as target. Blank forms are a plan, not recorded evaluation results.
"""
import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .common import new_output, read_json, write_json

FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'


def f(size):
    return ImageFont.truetype(FONT, size)


def page(title, subtitle):
    image = Image.new('RGB', (1240, 1754), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((75, 65), title, font=f(38), fill='black')
    size = 21
    while f(size).getlength(subtitle) > 1090 and size > 10:
        size -= 1
    draw.text((75, 125), subtitle, font=f(size), fill='black')
    return image, draw


def txt(draw, y, content, size=23):
    draw.text((75, y), content, font=f(size), fill='black')


def table(draw, top, xs, rows, height, size=23):
    for i, row in enumerate(rows):
        y = top + i * height
        if i == 0:
            draw.rectangle((xs[0], y, xs[-1], y + height), fill='#eeeeee')
        for j, value in enumerate(row):
            draw.text((xs[j] + 10, y + 15), str(value), font=f(size), fill='black')
    for x in xs:
        draw.line((x, top, x, top + len(rows) * height), fill='black', width=2)
    for i in range(len(rows) + 1):
        draw.line((xs[0], top + i * height, xs[-1], top + i * height), fill='black', width=2)


def foot(draw, number):
    txt(draw, 1670, f'P0 基线评估  |  TE=0 · 20 Hz · 每条最长 30 秒  |  {number}/7', 19)


def render(layouts, run_id, output):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', run_id):
        raise ValueError('run-id must be 1–64 letters, digits, hyphens or underscores')
    layouts = Path(layouts).resolve()
    a = read_json(layouts)['episodes']
    if len(a) != 10:
        raise ValueError('P0 requires exactly ten layouts')
    for e in a:
        if any(not re.fullmatch(r'[ABCD][1234]', e[key]) for key in ['green', 'red']):
            raise ValueError('invalid layout cell')
        if e['green'] == e['red']:
            raise ValueError('cube layout cells must differ')
    adjacent = [i for i, e in enumerate(a, 1)
                if abs(ord(e['green'][0]) - ord(e['red'][0]))
                + abs(int(e['green'][1]) - int(e['red'][1])) == 1]
    nonadjacent = [i for i in range(1, 11) if i not in adjacent]
    output_path = Path(output).resolve()
    if output_path == layouts or layouts.is_relative_to(output_path):
        raise ValueError('output and layouts must not overlap')
    # Resolve fonts before creating output, so missing system fonts fail cleanly.
    f(23)
    root = new_output(output_path)
    pages = []
    im,d=page('SO101 红绿方块抓取 — P0 测试布局',f'日期：____________  测试人：____________  测试编号：{run_id}')
    txt(d,195,'共 60 条：红、绿各 3 轮，每轮依次完成以下 10 个布局。')
    txt(d,240,'侧相机画面：最上面为第 4 行；列从左到右为 D、C、B、A。')
    txt(d,285,'红色测试将绿色测试的两块方块互换位置。方块居中，朝向保持一致。')
    rows=[['条目','绿测：绿目标','绿测：红干扰','红测：红目标','红测：绿干扰','类型']]
    for i,e in enumerate(a,1):rows.append([i,e['green'],e['red'],e['green'],e['red'],'相邻' if i in adjacent else '非相邻'])
    table(d,360,[75,165,365,565,765,965,1165],rows,67,22)
    for y,s in [(1150,'执行顺序：绿 r1 → 红 r1 → 红 r2 → 绿 r2 → 绿 r3 → 红 r3。'),(1210,'开跑前：固定相机、定位纸、碗和灯光；清空碗；从臂摆同一折叠休息位。'),(1270,'每条目标入碗、手臂离开碗口后按 n 结束；失败保留并运行到超时。'),(1330,'复位阶段：等手臂回位，再取出方块并摆下一行，按 n 开始。'),(1390,'r 只用于摆错或人员误入等操作失误；不能为抓取失败重录。'),(1450,'同一条内策略自行再次夹取可保留，并在记录表注明首次夹取失败。'),(1510,'第 6、7 条重点核对，避免摆错或漏测。q / Esc 结束并保存。')]:txt(d,y,s,22)
    foot(d,1);pages.append(im)
    order=[('green','绿',1),('red','红',1),('red','红',2),('green','绿',2),('green','绿',3),('red','红',3)]
    for pn,(color,cn,r) in enumerate(order,2):
     im,d=page(f'P0 结果记录 — {cn}色目标 / 第 {r} 轮',f'执行顺序第 {pn-1}/6 组  |  数据集：eval-p0-{run_id}-{color}-r{r}')
     txt(d,190,'日期：____________  开始：________  结束：________  测试人：____________')
     txt(d,240,'灯光 / 窗帘：____________________  相机 / 纸 / 碗是否移动：________________')
     txt(d,290,'填写：首次夹取、最终入碗均填“是 / 否”；耗时填秒；备注写夹空、碰歪等。',21)
     rows=[['条目','目标 / 干扰','首次夹取成功','最终入碗','耗时(s)','失败 / 重试 / 摆放备注']]
     for i,e in enumerate(a,1):rows.append([i,e['green']+' / '+e['red'],'','','',''])
     table(d,355,[75,150,350,550,710,830,1165],rows,92,21)
     txt(d,1410,'本轮汇总：首次夹取成功 ____/10；最终入碗 ____/10；抓错颜色 ____ 次。')
     txt(d,1470,f'相邻入碗 ____/{len(adjacent)}（'+ '、'.join(map(str, adjacent)) + f'）；非相邻入碗 ____/{len(nonadjacent)}（' + '、'.join(map(str, nonadjacent)) + '）。',21)
     txt(d,1530,'操作失误 / 中断 / 其他：________________________________________________',21)
     foot(d,pn);pages.append(im)
    pdf = root / 'so101-p0-layout-and-records.pdf'
    pages[0].save(pdf, 'PDF', resolution=150, save_all=True, append_images=pages[1:])
    for i, image in enumerate(pages, 1):
        preview = image.copy()
        preview.thumbnail((1600, 1600))
        preview.save(root / f'page{i}-preview.png')
    groups = [dict(color=color, round=round_number,
                   dataset=f'eval-p0-{run_id}-{color}-r{round_number}')
              for color, _, round_number in order]
    result = dict(run_id=run_id, layouts=str(layouts), pages=len(pages),
                  pdf=str(pdf), groups=groups, notice='Blank evaluation forms only; no printing or robot actions.')
    write_json(root / 'render-manifest.json', result)
    return result


def main():
    global FONT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layouts', required=True, type=Path)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--font', default=FONT, help='CJK TrueType/OpenType font')
    args = parser.parse_args()
    FONT = args.font
    print(render(args.layouts, args.run_id, args.output))


if __name__ == '__main__':
    main()
