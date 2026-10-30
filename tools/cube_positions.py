"""Estimate cube table coordinates from review_dataset first/last side frames.

The historical HSV/component heuristic assumes the supplied calibration matches
image pixels and cube centres lie 1 cm above the table. Nearest cell and bowl
distance are estimates, never evidence of grasp success or final bowl outcome.
"""
import argparse
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .common import new_output, read_json, write_json

MASKS = {'green': [((40, 60, 20), (90, 255, 200))],
         'red': [((0, 90, 60), (10, 255, 255)), ((170, 90, 60), (180, 255, 255))]}
NOTICE = ('Heuristic position estimates only: HSV/component detection and a 1 cm '
          'table-plane projection do not establish grasp success or bowl outcomes. '
          'Calibration must match the original side-frame pixel coordinates.')


class Calibration:
    def __init__(self, directory):
        directory = Path(directory)
        intr = read_json(directory / 'intrinsics-side.json')
        ext = read_json(directory / 'extrinsics-side.json')
        self.K, self.D = np.array(intr['K'], float), np.array(intr['D'], float).ravel()
        self.flip = np.array([-1., 1., 1.])
        self.C = np.array(ext['position_cm'], float) * self.flip
        z = np.array(ext['forward'], float) * self.flip
        up = np.mean([np.array(f['image_up'], float) for f in ext['frames']], axis=0) * self.flip
        if self.K.shape != (3, 3) or self.C.shape != (3,) or z.shape != (3,) or up.shape != (3,):
            raise ValueError('invalid calibration dimensions')
        if not all(np.isfinite(v).all() for v in [self.K, self.D, self.C, z, up]) or np.linalg.norm(z) == 0:
            raise ValueError('invalid calibration values')
        z /= np.linalg.norm(z)
        y = -(up - up @ z * z)
        if np.linalg.norm(y) == 0:
            raise ValueError('calibration up and forward are parallel')
        y /= np.linalg.norm(y)
        self.R = np.vstack([np.cross(y, z), y, z])

    def to_table(self, pixel, height_cm=1.):
        u = cv2.undistortPoints(np.array([[pixel]], np.float64), self.K, self.D).ravel()
        ray = self.R.T @ np.array([u[0], u[1], 1.])
        if abs(ray[2]) < 1e-12:
            raise ValueError('pixel ray is parallel to table')
        return ((self.C + (height_cm - self.C[2]) / ray[2] * ray) * self.flip)[:2]


def find(image, color, calibration):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = sum(cv2.inRange(hsv, np.array(a), np.array(b)) for a, b in MASKS[color])
    n, _, stats, centers = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8))
    candidates = []
    for k in range(1, n):
        if 40 < stats[k, cv2.CC_STAT_AREA] < 3000:
            xy = calibration.to_table(centers[k])
            if -14 <= xy[0] <= 22 and 9 <= xy[1] <= 33:
                candidates.append((stats[k, cv2.CC_STAT_AREA], xy))
    return None if not candidates else max(candidates, key=lambda candidate: candidate[0])[1]


def estimate(review_dir, calibration_dir, layout_path, output):
    review_dir, calibration_dir, layout_path = map(Path, [review_dir, calibration_dir, layout_path])
    calibration = Calibration(calibration_dir)
    layout = read_json(layout_path)
    cells = {key: np.asarray(value, float) for key, value in layout['cells'].items()}
    bowl = np.asarray(layout['bowl'], float)
    if not cells or any(v.shape != (2,) or not np.isfinite(v).all() for v in [*cells.values(), bowl]):
        raise ValueError('layout requires finite two-dimensional cells and bowl')
    frames = {}
    for path in review_dir.glob('ep*-side-*.jpg'):
        match = re.fullmatch(r'ep([1-9][0-9]*)-side-(first|last)\.jpg', path.name)
        if match:
            frames.setdefault(int(match[1]), {})[match[2]] = path
    if not frames or any(set(pair) != {'first', 'last'} for pair in frames.values()):
        raise ValueError('review requires paired first/last side frames for every episode')
    output = Path(output).resolve()
    for source in [review_dir.resolve(), calibration_dir.resolve(), layout_path.resolve()]:
        if output == source or output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError('output and inputs must not overlap')
    file_output = output.suffix.lower() == '.json'
    if output.exists():
        raise FileExistsError(output)
    rows, previews = [], []
    for episode, pair in sorted(frames.items()):
        row, images = {'episode': episode}, []
        for when in ['first', 'last']:
            # Inspect dimensions before decoding; retain original pixels for calibration.
            with Image.open(pair[when]) as header:
                size = header.size
            if size[0] <= 0 or size[1] <= 0:
                raise ValueError('invalid frame dimensions')
            image = cv2.imread(str(pair[when]))
            if image is None:
                raise ValueError(f'cannot decode {pair[when]}')
            images.append(image)
            for color in ['green', 'red']:
                xy = find(image, color, calibration)
                row[f'{color}_{when}'] = None if xy is None else dict(
                    cm=np.round(xy, 1).tolist(),
                    cell=min(cells, key=lambda key: np.linalg.norm(cells[key] - xy)),
                    bowl_dist=round(float(np.linalg.norm(xy - bowl)), 1))
        rows.append(row)
        if not file_output:
            if images[0].shape != images[1].shape:
                raise ValueError('first/last frame dimensions differ')
            preview = Image.fromarray(cv2.cvtColor(np.hstack(images), cv2.COLOR_BGR2RGB))
            preview.thumbnail((1600, 1600))
            previews.append((episode, preview))
    result = dict(notice=NOTICE, review_dir=str(review_dir.resolve()),
                  calibration_dir=str(calibration_dir.resolve()), layout=str(layout_path.resolve()), rows=rows)
    if file_output:
        output.parent.mkdir(parents=True, exist_ok=True)
        import json
        with output.open('x') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    else:
        new_output(output)
        write_json(output / 'cubes.json', result)
        for episode, preview in previews:
            preview.save(output / f'ep{episode}-first-last-preview.jpg')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-dir', required=True, type=Path)
    parser.add_argument('--calibration-dir', required=True, type=Path)
    parser.add_argument('--layout', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='fresh directory or .json file')
    args = parser.parse_args()
    result = estimate(args.review_dir, args.calibration_dir, args.layout, args.output)
    print(f"{len(result['rows'])} episodes; {NOTICE}")


if __name__ == '__main__':
    main()
