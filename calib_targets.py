"""生成可打印的标定板 PDF（A4 横向，按 100% 打印）和 ArUco 定位纸的标记坐标表。

第 1 页：ChArUco 棋盘（内参标定）。7x5 格，格子 35 mm，标记 26 mm，DICT_4X4_50。打印后贴在硬纸板上保持平整。
第 2 页：ArUco 定位纸（侧面相机外参）。DICT_5X5_100，15 个 45 mm 标记。和 A4 定位纸同样大小、同样朝向，
        直接盖在已贴好的定位纸上（四边对齐），标记在机械臂坐标里的位置由 placement-list.json 的贴纸位置算出。

用法：python calib_targets.py <placement-list.json> <输出目录>
"""
import json
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

DPI = 254                     # 10 px per mm
PX = DPI / 25.4               # px per mm
A4_L_MM, A4_W_MM = 297, 210
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
CHARUCO = dict(squares=(7, 5), square_mm=35, marker_mm=26, dictionary='DICT_4X4_50')
ARUCO = dict(dictionary='DICT_5X5_100', marker_mm=45, cols=5, rows=3, gap_mm=12)


def page():
    img = Image.new('L', (round(A4_L_MM * PX), round(A4_W_MM * PX)), 255)
    return img, ImageDraw.Draw(img)


def font(size_mm):
    return ImageFont.truetype(FONT, round(size_mm * PX))


def scale_bar(draw, x_mm, y_mm):
    draw.line([(x_mm * PX, y_mm * PX), ((x_mm + 100) * PX, y_mm * PX)], fill=0, width=4)
    for t in range(11):
        h = 4 if t % 5 == 0 else 2
        draw.line([((x_mm + 10 * t) * PX, y_mm * PX), ((x_mm + 10 * t) * PX, (y_mm - h) * PX)], fill=0, width=3)
    draw.text((x_mm * PX, (y_mm + 1.5) * PX), '比例尺 100 mm（打印后用尺核对）', font=font(3), fill=0)


def charuco_page():
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, CHARUCO['dictionary']))
    board = cv2.aruco.CharucoBoard(CHARUCO['squares'], CHARUCO['square_mm'] / 1000, CHARUCO['marker_mm'] / 1000, d)
    w, h = (round(n * CHARUCO['square_mm'] * PX) for n in CHARUCO['squares'])
    art = board.generateImage((w, h), marginSize=0, borderBits=1)
    img, draw = page()
    x0, y0 = round((A4_L_MM * PX - w) / 2), round(22 * PX)
    img.paste(Image.fromarray(art), (x0, y0))
    draw.text((x0, 6 * PX), 'ChArUco 7x5，格子 35 mm，标记 26 mm，DICT_4X4_50 —— 内参标定用。A4 横向 100% 打印，'
              '贴在硬纸板上保持平整。', font=font(3.2), fill=0)
    scale_bar(draw, 15, A4_W_MM - 8)
    return img


def aruco_page(sheet):
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, ARUCO['dictionary']))
    m, gap, cols, rows = ARUCO['marker_mm'], ARUCO['gap_mm'], ARUCO['cols'], ARUCO['rows']
    grid_w, grid_h = cols * m + (cols - 1) * gap, rows * m + (rows - 1) * gap
    left_mm, top_mm = (A4_L_MM - grid_w) / 2, (A4_W_MM - grid_h) / 2 + 6
    img, draw = page()
    side = round(m * PX)
    markers = {}
    for r in range(rows):
        for c in range(cols):
            mid = r * cols + c
            u0, t0 = left_mm + c * (m + gap), top_mm + r * (m + gap)   # mm from the page's left and top edges
            img.paste(Image.fromarray(cv2.aruco.generateImageMarker(d, mid, side, borderBits=1)),
                      (round(u0 * PX), round(t0 * PX)))
            draw.text((u0 * PX, (t0 + m + 1) * PX), f'id {mid}', font=font(2.5), fill=0)
            # corner order as detected: top-left, top-right, bottom-right, bottom-left (page orientation)
            corners_page = [(u0, t0), (u0 + m, t0), (u0 + m, t0 + m), (u0, t0 + m)]
            markers[mid] = [robot_xy(sheet, u, t) for u, t in corners_page]
    draw.text((8 * PX, 5 * PX), 'ArUco 定位纸（侧面相机外参）DICT_5X5_100，标记 45 mm —— 和 A4 定位纸同向（上方为前，'
              '从机械臂后方阅读），四边对齐盖在定位纸上，拍完拿走。', font=font(3), fill=0)
    scale_bar(draw, 15, A4_W_MM - 6)
    return img, markers


def robot_xy(sheet, u_mm, t_mm):
    """Page point (mm from left edge, mm from top edge) -> robot plan frame (cm): +x left, +y forward, z = 0."""
    u_cm, v_cm = u_mm / 10, (A4_W_MM - t_mm) / 10
    x = sheet['right_edge_x'] + A4_L_MM / 10 - u_cm
    y = sheet['near_edge_y'] + v_cm
    return [round(x, 3), round(y, 3), 0.0]


def main():
    plist, out = sys.argv[1], sys.argv[2]
    sheet = json.load(open(plist))['sheet']
    p1 = charuco_page()
    p2, markers = aruco_page(sheet)
    p1.save(f'{out}/calib-targets.pdf', save_all=True, append_images=[p2], resolution=DPI)
    json.dump(dict(frame='robot plan frame (cm): origin follower pan axis on the table, +x robot left, +y forward, z up',
                   source=plist, sheet=sheet, charuco=CHARUCO, aruco=ARUCO, markers=markers),
              open(f'{out}/aruco-sheet-layout.json', 'w'), indent=1)
    print(f'{out}/calib-targets.pdf', f'{out}/aruco-sheet-layout.json', len(markers), 'markers')


if __name__ == '__main__':
    main()
