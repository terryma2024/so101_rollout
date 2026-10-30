"""Audit planned red/green instruction pairs sharing the same physical cube placement.

This audits plan annotations, not image equivalence or successful robot behaviour.
"""
import argparse
from collections import defaultdict
from pathlib import Path

from .common import read_json, write_json
from .render_collection import validate


def coverage(episodes, cells_only=False):
    conditions = defaultdict(lambda: {'green': [], 'red': []})
    for index, e in enumerate(episodes):
        color = e['color']
        if color not in ['green', 'red']:
            raise ValueError('invalid color')
        scene = []
        # A red task swaps target/distractor roles, not physical red/green positions.
        for physical in ['green', 'red']:
            role = 'target' if physical == color else 'distractor'
            pose = (e[role],)
            if not cells_only:
                pose += tuple(e[role + suffix] for suffix in ['_dx_mm', '_dy_mm', '_yaw_deg'])
            scene.append(pose)
        conditions[tuple(scene)][color].append(e.get('id', index + 1))
    pairs = []
    for scene, labels in sorted(conditions.items()):
        pairs.append(dict(green_pose=scene[0], red_pose=scene[1], instructions=labels,
                          paired=bool(labels['green'] and labels['red'])))
    return {'mode': 'cells_only' if cells_only else 'cells_offsets_angles',
            'scope': 'planned conditions only; not verified camera scenes or outcomes',
            'conditions': len(pairs), 'paired_conditions': sum(p['paired'] for p in pairs),
            'demonstrations': sum(len(p['instructions'][c]) for p in pairs for c in ['green', 'red']),
            'paired_demonstrations': sum(len(p['instructions'][c]) for p in pairs if p['paired'] for c in ['green', 'red']),
            'rows': pairs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cells-only', action='store_true')
    args = parser.parse_args()
    plan = validate(read_json(args.plan))
    if args.output.exists():
        raise FileExistsError(args.output)
    result = coverage([e for b in plan['batches'] for e in b['episodes']], args.cells_only)
    write_json(args.output, result)
    print({k: v for k, v in result.items() if k != 'rows'})


if __name__ == '__main__':
    main()
