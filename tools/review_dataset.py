"""Validate LeRobot v3 parquet/video alignment; render bounded visual review sheets.

Outcomes are deliberately unknown until a person reviews the videos.
"""
import argparse
from pathlib import Path

import av
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from .common import new_output, read_json, write_json


def parquet_rows(path):
    paths = sorted(Path(path).rglob('*.parquet'))
    if not paths:
        raise ValueError(f'no parquet files: {path}')
    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)


def review(dataset, output, cameras=('side', 'wrist')):
    dataset = Path(dataset).resolve()
    info = read_json(dataset / 'meta/info.json')
    fps = float(info['fps'])
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError('invalid dataset fps')
    data = parquet_rows(dataset / 'data')
    episodes = parquet_rows(dataset / 'meta/episodes').sort_values('episode_index')
    if data.empty or episodes.empty:
        raise ValueError('empty dataset')
    if not np.isfinite(data.timestamp.to_numpy()).all():
        raise ValueError('nonfinite timestamp')
    if not np.isfinite(episodes.length.to_numpy()).all() or (episodes.length < 1).any() or (episodes.length % 1 != 0).any():
        raise ValueError('invalid metadata length')
    if not np.isfinite(episodes.episode_index.to_numpy()).all() or (episodes.episode_index < 0).any() or (episodes.episode_index % 1 != 0).any():
        raise ValueError('invalid episode index')
    if not cameras or len(set(cameras)) != len(cameras):
        raise ValueError('camera list must be nonempty and unique')
    if episodes.episode_index.duplicated().any():
        raise ValueError('duplicate episode metadata')
    if set(data.episode_index) != set(episodes.episode_index):
        raise ValueError('episode metadata/data membership differs')
    output = new_output(output, dataset)
    records = {}
    for _, e in episodes.iterrows():
        ei = int(e.episode_index)
        dd = data[data.episode_index == ei].sort_values('frame_index')
        records[ei] = dict(recorded_episode=ei + 1, frames=len(dd), seconds=len(dd) / fps,
                           metadata_length_ok=len(dd) == int(e.length),
                           dt_ok=bool(np.allclose(np.diff(dd.timestamp), 1 / fps, atol=.001)),
                           indices_ok=bool(np.array_equal(dd.frame_index, np.arange(len(dd)))),
                           short_record=len(dd) <= 1, cameras={}, final_in_bowl=None,
                           first_grasp_success=None)
        for field in ['observation.state', 'action']:
            if field in dd and len(dd):
                values = np.stack(dd[field].to_numpy())
                records[ei][field + '_finite'] = bool(np.isfinite(values).all())
    for cam in cameras:
        key = f'videos/observation.images.{cam}'
        groups = {}
        # Keep only bounded sample thumbnails plus first/last originals per episode.
        # Decoding a long dataset must not retain every full RGB video frame.
        images = {}
        for ei, rec in records.items():
            n = rec['frames']
            wanted = set(np.linspace(0, n - 1, 12).astype(int)) | set(np.linspace(0, n - 1, 6).astype(int))
            images[ei] = dict(count=0, first=None, last=None, picks={}, wanted=wanted)
        for _, e in episodes.iterrows():
            start, end = float(e[key + '/from_timestamp']), float(e[key + '/to_timestamp'])
            if end <= start:
                raise ValueError(f'invalid video interval: {cam} ep{e.episode_index}')
            loc = (int(e[key + '/chunk_index']), int(e[key + '/file_index']))
            groups.setdefault(loc, []).append((int(e.episode_index), start, end))
        for (chunk, file), intervals in groups.items():
            video = dataset / key / f'chunk-{chunk:03d}/file-{file:03d}.mp4'
            with av.open(str(video)) as container:
                for frame in container.decode(video=0):
                    t = float(frame.pts * frame.time_base)
                    for ei, start, end in intervals:
                        if start - .001 <= t < end - .001:
                            state = images[ei]
                            ix = state['count']
                            im = frame.to_image()
                            if state['first'] is None:
                                state['first'] = im
                            state['last'] = im
                            if ix in state['wanted']:
                                small = im.copy(); small.thumbnail((320, 240))
                                state['picks'][ix] = small
                            state['count'] += 1
        tiles = []
        for ei, state in images.items():
            n = state['count']
            rec = records[ei]
            rec['cameras'][cam] = {'frames': n}
            if n == 0:
                continue
            rgb = np.asarray(state['first']).mean((0, 1))
            green = float(rgb[1])
            rec['cameras'][cam].update(size=list(state['first'].size),
                first_luma=float(rgb @ [.299, .587, .114]),
                first_BG=float(rgb[2] / green) if green else None,
                first_RG=float(rgb[0] / green) if green else None)
            for tag, im in [('first', state['first']), ('last', state['last'])]:
                im.save(output / f'ep{ei + 1}-{cam}-{tag}.jpg')
            sheet = Image.new('RGB', (1280, 795), 'white')
            draw = ImageDraw.Draw(sheet)
            for k, ix in enumerate(np.linspace(0, rec['frames'] - 1, 12).astype(int)):
                x, y = (k % 4) * 320, (k // 4) * 265
                sheet.paste(state['picks'].get(ix, state['last']).resize((320, 240)), (x, y))
                draw.text((x + 4, y + 242), f'ep{ei + 1} {ix / fps:.2f}s', fill='black')
            sheet.save(output / f'ep{ei + 1}-{cam}-12-preview.jpg')
            row = Image.new('RGB', (1536, 212), 'white')
            ImageDraw.Draw(row).text((4, 3), f'{dataset.name}: ep{ei + 1} / {rec["seconds"]:.2f}s', fill='black')
            for k, ix in enumerate(np.linspace(0, rec['frames'] - 1, 6).astype(int)):
                row.paste(state['picks'].get(ix, state['last']).resize((256, 192)), (k * 256, 20))
            tiles.append(row)
        for offset in range(0, len(tiles), 5):
            selected = tiles[offset:offset + 5]
            sheet = Image.new('RGB', (1536, len(selected) * 212), 'white')
            for i, tile in enumerate(selected):
                sheet.paste(tile, (0, i * 212))
            sheet.save(output / f'{cam}-page{offset // 5 + 1}-preview.jpg')
    for rec in records.values():
        rec['integrity_ok'] = (rec['metadata_length_ok'] and rec['dt_ok'] and rec['indices_ok']
                               and all(rec.get(k, True) for k in ['action_finite', 'observation.state_finite'])
                               and all(x['frames'] == rec['frames'] for x in rec['cameras'].values()))
    result = dict(dataset=str(dataset), fps=fps, episodes=len(records), frames=len(data),
                  integrity_ok=all(x['integrity_ok'] for x in records.values()), rows=list(records.values()))
    write_json(output / 'integrity-light.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cameras', nargs='+', default=['side', 'wrist'])
    args = parser.parse_args()
    result = review(args.dataset, args.output, args.cameras)
    print({k: v for k, v in result.items() if k != 'rows'})
    raise SystemExit(0 if result['integrity_ok'] else 1)


if __name__ == '__main__':
    main()
