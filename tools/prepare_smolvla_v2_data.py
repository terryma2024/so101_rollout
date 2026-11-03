"""Export accepted v1 sources plus audited per-episode v2 selections, read-only at source."""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import re
import shutil
from tools.prepare_smolvla_data import (TASKS, manifest, numeric_digest, origin_episode,
    read_tables, recompute_stats, repair_self_pointers, save, sha256, validate_split, verify_dataset)


def capture_group(name):
    """Red/green folders in the same wide capture batch are one provenance group."""
    if name == 'real-cube-bowl-smolvla-v2-wide-g19-replacement-green-20261103':
        return 'real-cube-bowl-smolvla-v2-wide-b02-20261102'
    return re.sub(r'-(green|red)-', '-', name)


def selected_sources(selection):
    if selection.get('visual_status') != 'pass':
        raise ValueError('Replacement visual acceptance is required')
    excluded, replacement = selection['excluded'], selection['replacement']
    result, seen = [], set()
    for source in selection['sources']:
        name = source['dataset_name']
        if Path(name).name != name or name in ('', '.', '..') or name in seen:
            raise ValueError('Invalid or duplicate source name')
        seen.add(name)
        episodes = source['selected_episode_indices']
        if (not episodes or any(type(i) is not int or i < 0 for i in episodes)
                or len(set(episodes)) != len(episodes) or episodes != sorted(episodes)):
            raise ValueError('Episode selection must be nonempty, unique and ascending')
        split = {'val':'validation','validation':'validation','train':'train'}.get(source['split'])
        if split is None:
            raise ValueError('Unknown split')
        if name == excluded['dataset_name'] and excluded['episode_index'] in episodes:
            raise ValueError('Rejected episode remains selected')
        result.append({'name':name, 'split':split, 'episodes':episodes,
                       'plan_ids':source.get('selected_plan_ids', [])})
    matches = [s for s in result if s['name'] == replacement['dataset_name']]
    if len(matches) != 1 or matches[0]['episodes'] != [replacement['episode_index']] or matches[0]['split'] != 'train':
        raise ValueError('Replacement must be selected once in train')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--datasets-root', type=Path, default=Path('/data/work/so101-datasets'))
    parser.add_argument('--old-manifest', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--train-root', type=Path, required=True)
    parser.add_argument('--validation-root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    a = parser.parse_args()
    outputs = {'train':a.train_root,'validation':a.validation_root}
    if a.evidence.exists() or any(p.exists() for p in outputs.values()):
        parser.error('Fresh evidence and output roots required')
    if len({p.resolve() for p in outputs.values()}) != 2:
        parser.error('Output roots must differ')
    selection = json.loads(a.selection.read_text())
    additions = selected_sources(selection)
    records = copy.deepcopy(json.loads(a.old_manifest.read_text()))
    if len(records) != 266 or {s:sum(r['split']==s for r in records) for s in outputs} != {'train':214,'validation':52}:
        raise ValueError('Expected accepted v1 214/52 source records')
    for r in records:
        r.pop('derived_episode_index', None)
        r['quality'] = {'status':'accepted_v1','evidence':str(a.old_manifest)}
    source_specs = {}
    for r in records:
        source_specs.setdefault(r['source_dataset'], {'split':r['split'],'episodes':[]})['episodes'].append(r['source_episode_index'])
    for spec in additions:
        name = spec['name'];frame = read_tables(a.datasets_root/name,'data')
        color, = [c for c in TASKS if '-'+c+'-' in name]
        for ordinal, index in enumerate(spec['episodes']):
            ep = frame[frame.episode_index==index]
            if ep.empty:
                raise ValueError(f'Missing selected source episode {name}:{index}')
            records.append({'split':spec['split'],'color':color,'group':capture_group(name),
                'source_dataset':name,'source_episode_index':index,'original_episode_index':index,
                'origin':f'{name}:{index}','numeric_sha256':numeric_digest(ep),'frames':len(ep),
                'task':TASKS[color], 'plan_id':spec['plan_ids'][ordinal] if spec['plan_ids'] else None,
                'quality':{'status':'accepted','selection':str(a.selection),'selection_sha256':sha256(a.selection)}})
        source_specs[name] = {'split':spec['split'],'episodes':spec['episodes']}
    validate_split(records)
    if {s:sum(r['split']==s for r in records) for s in outputs} != {'train':262,'validation':76}:
        raise ValueError('Expected final 262/76 episodes')
    a.evidence.mkdir(parents=True)
    save(a.evidence/'selection.json', selection)
    before = {name:manifest(a.datasets_root/name) for name in source_specs}
    save(a.evidence/'sources-before.json', before)
    # Build independent source views; only the mixed shared-video exclusion needs re-encoding.
    from lerobot.datasets.aggregate import aggregate_datasets
    from lerobot.datasets.dataset_tools import delete_episodes
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    import pandas as pd
    views, selected_views = a.evidence/'source-views', {}
    approved_parts = {c:[] for c in TASKS}
    approved_counts = {c:0 for c in TASKS}
    for name, spec in source_specs.items():
        source = a.datasets_root/name
        source_frame = read_tables(source,'data')
        source_records = [r for r in records if r['source_dataset']==name]
        for r in source_records:
            ep = source_frame[source_frame.episode_index==r['source_episode_index']].copy()
            if len(ep) != r['frames'] or numeric_digest(ep) != r['numeric_sha256']:
                raise ValueError('Original source numeric content changed')
            color = r['color'];r['approved_episode_index'] = approved_counts[color]
            ep['episode_index'] = approved_counts[color];approved_counts[color] += 1
            approved_parts[color].append(ep)
        view = views/name
        shutil.copytree(source,view)
        save(a.evidence/(name+'-pointer-repairs.json'), repair_self_pointers(view))
        actual_ids = sorted(int(i) for i in source_frame.episode_index.unique())
        if not set(spec['episodes']) <= set(actual_ids):
            raise ValueError('Selected episode out of range')
        excluded = sorted(set(actual_ids)-set(spec['episodes']))
        if excluded:
            destination = a.evidence/'selected-views'/name
            dataset = LeRobotDataset('local/'+name,root=view,video_backend='pyav',download_videos=False)
            delete_episodes(dataset,excluded,output_dir=destination,repo_id='local/'+name+'-accepted')
            repair_self_pointers(destination)
            selected_views[name] = destination
        else:
            selected_views[name] = view
        print('source accepted',name,len(spec['episodes']),flush=True)
    approved = {c:pd.concat(parts,ignore_index=True) for c,parts in approved_parts.items()}
    reports = {}
    for split, out in outputs.items():
        names = [n for n,s in source_specs.items() if s['split']==split]
        aggregate_datasets(['local/'+n for n in names], 'local/'+out.name,
                           roots=[selected_views[n] for n in names],aggr_root=out)
        repair_self_pointers(out)
        recompute_stats(out)
        selected = [r for r in records if r['split']==split]
        reports[split] = verify_dataset(out,selected,approved)
        save(a.evidence/(split+'-verification.json'), reports[split])
        print('verified',split,reports[split]['episodes'],reports[split]['frames'],flush=True)
    reference = {'fitted_split':'train','stats_path':str(a.train_root/'meta/stats.json'),
                 'stats_sha256':sha256(a.train_root/'meta/stats.json'),
                 'validation_descriptive_stats':'meta/stats.json retained for auditing only',
                 'validation_forward':'must reuse train-fitted pre/post processors'}
    save(a.validation_root/'meta/normalization-reference.json',reference)
    save(a.evidence/'normalization-reference.json',reference)
    save(a.evidence/'episode-map.json',records)
    save(a.evidence/'split.json',{'records':records,'selection_sha256':sha256(a.selection),
          'group_basis':'original recording folder; wide red/green folders share capture batch identity',
          'excluded':[selection['excluded']], 'replacement':selection['replacement'],
          'cross_split_numeric_duplicates':0,'approved_episodes':len(records)})
    after = {name:manifest(a.datasets_root/name) for name in source_specs}
    if before != after:
        raise ValueError('Original sources changed')
    save(a.evidence/'sources-unchanged.json',{'passed':True,'files':sum(map(len,after.values()))})
    files = {s:manifest(p) for s,p in outputs.items()};save(a.evidence/'dataset-files-sha256.json',files)
    save(a.evidence/'dataset-approved.json',{'passed':True,'datasets':reports,'normalization':reference,
        'source_files_unchanged':True,'split_manifest_sha256':sha256(a.evidence/'split.json'),
        'files_manifest':str(a.evidence/'dataset-files-sha256.json'),
        'files_manifest_sha256':sha256(a.evidence/'dataset-files-sha256.json'),
        'selection_sha256':sha256(a.selection),'notes':['No original dataset modified.','B02 ep6 excluded, replacement ep0 accepted.',
        'No claim of date/layout-independent generalization.','All validation uses train-fitted processors.']})
    print('APPROVED',a.evidence/'dataset-approved.json',flush=True)


if __name__=='__main__':
    main()
