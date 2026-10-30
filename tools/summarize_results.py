"""Summarize explicit human-reviewed outcome annotations, never durations or motion completion."""
import argparse
import csv
from pathlib import Path
from .common import read_json, write_json, new_output


def summarize(rows):
    seen = set()
    result = {'total': {'success': 0, 'trials': 0, 'unknown': 0}}
    for r in rows:
        color = r['color']
        if color not in ['green', 'red']:
            raise ValueError('invalid color')
        identity = (color, r['round'], r['recorded_episode'])
        if identity in seen:
            raise ValueError(f'duplicate annotation: {identity}')
        seen.add(identity)
        final = r.get('final_in_bowl')
        first = r.get('first_grasp_success')
        if any(x is not None and not isinstance(x, bool) for x in [final, first]):
            raise ValueError('outcome must be boolean or null')
        if not isinstance(r.get('excluded', False), bool):
            raise ValueError('excluded must be boolean')
        if r.get('excluded', False):
            continue
        color_result = result.setdefault(color, {'success': 0, 'trials': 0, 'unknown': 0,
            'rounds': {}, 'layouts': {}, 'first_grasp': {'success': 0, 'labelled': 0}})
        row_key = str(r.get('layout_row')) if r.get('layout_row') is not None else 'variant'
        for group in [result['total'], color_result,
                      color_result['rounds'].setdefault(str(r['round']), {'success': 0, 'trials': 0, 'unknown': 0}),
                      color_result['layouts'].setdefault(row_key, {'success': 0, 'trials': 0, 'unknown': 0})]:
            group['trials'] += 1
            group['success'] += int(final is True)
            group['unknown'] += int(final is None)
        if first is not None:
            color_result['first_grasp']['labelled'] += 1
            color_result['first_grasp']['success'] += int(first)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('annotations', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    rows = read_json(args.annotations)
    result = summarize(rows)
    output = new_output(args.output)
    write_json(output / 'summary.json', result)
    with (output / 'results.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=sorted({k for row in rows for k in row}))
        writer.writeheader(); writer.writerows(rows)
    print(result['total'])


if __name__ == '__main__':
    main()
