#!/usr/bin/env python3
"""Prepare only the 16 novel cases; keep the frozen 24-case package intact."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import shlex

SOURCE = Path('/data/work/so101-evidence/real-robot/smolvla-v2-generalization24-20261104/collection-package')
HISTORY = Path('/data/work/so101-evidence/real-robot/smolvla-v2-v3-comparison-20261104/v2')
OUTPUT = Path('/data/work/so101-evidence/real-robot/smolvla-v2-generalization16-20261104/collection-package')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(out):
    out = out.resolve()
    if out.exists():
        raise FileExistsError(f'Refuse overwrite: {out}')
    source_hashes = {str(p): digest(p) for p in sorted(SOURCE.rglob('*')) if p.is_file()}
    plan = json.loads((SOURCE/'plan.json').read_text())
    historical = json.loads((HISTORY/'plan.json').read_text())
    assert len(historical['trials']) == 12
    assert historical['model_sha256'] == plan['model_sha256'] == '16d9116230bf5bb8eba4f6a9c9bbf635df9f3d93869b04da3f66252ce3e44b85'
    history_sources = [HISTORY/'plan.json', HISTORY/'results.csv', HISTORY.parent/'v2-visual-analysis'/'visual_results.csv', HISTORY.parent/'v2-visual-analysis'/'report.md']
    for t in historical['trials']:
        receipt = HISTORY/f"trial-{t['id']:02d}-execution.json"
        assert json.loads(receipt.read_text())['complete']
        history_sources.extend([receipt,Path(t['recording_path'])/'status.json',Path(t['dataset_path'])/'meta/info.json'])
        history_sources.extend(sorted((Path(t['dataset_path'])/'videos').rglob('*.mp4')))
    visual = list(csv.DictReader((HISTORY.parent/'v2-visual-analysis'/'visual_results.csv').open()))
    assert len(visual) == 12 and sum(r['target_in_bowl']=='visually_confirmed' for r in visual)==11
    historical_hashes = {str(p):digest(p) for p in history_sources}
    originals = [t for t in plan['trials'] if t['group']=='novel']
    trials=[]
    for identifier, old in enumerate(originals,1):
        t = dict(old, id=identifier, original24_trial_id=old['id'])
        name = old['dataset'].replace('generalization24','generalization16')
        recording = str(out/'recordings'/f'trial-{identifier:02d}')
        env = dict(old['env'],INFERENCE_RECORDING_PATH=recording)
        argv = [old['argv'][0],name,'1',plan['model']]
        t.update(dataset=name,dataset_path='/data/work/so101-datasets/'+name,recording_path=recording,env=env,argv=argv,command=shlex.join(['env',*[k+'='+v for k,v in env.items()],*argv]))
        trials.append(t)
    assert len(trials)==16
    assert trials[0]['layout']=='G B2/R B3' and trials[0]['color']=='red'
    assert Counter((t['layout_id'],t['color']) for t in trials)=={(layout,color):2 for layout in range(3,7) for color in ['green','red']}
    for t in trials:
        for key in ['dataset_path','recording_path']:
            if Path(t[key]).exists():
                raise FileExistsError(f'Fresh path required: {t[key]}')
    plan.update(suite='v2-generalization16',status='not_run',purpose='User correction: execute only 16 novel-combination cases; reuse all 12 historical v2 baseline cases separately. No new C2/C3 baseline trials.',source24_plan=str(SOURCE/'plan.json'),source24_sha256=source_hashes,trials=trials)
    plan.pop('source_plan',None)
    plan['analysis_cohorts'] = dict(current_novel=dict(count=16,status='not_run',trial_ids=list(range(1,17)),in_current_attempt_denominator=True),historical_baseline=dict(count=12,path=str(HISTORY),trial_ids=list(range(1,13)),include_all_trials=True,selection='all 12; no eight-trial subset',in_current_attempt_denominator=False,video_visual_review=dict(target_in_bowl=11,total=12,source=str(HISTORY.parent/'v2-visual-analysis'/'report.md'),operator_confirmation='not provided; not new human acceptance'),original_results_csv_status='not_run; not used as outcome evidence',sha256=historical_hashes),comparison_limit='Historical reference only; no contemporaneous control, time/environment differences cannot be fully eliminated. Keep preflight and approved setup.')
    plan['sha256'].update({str(p):digest(p) for p in [Path(__file__).resolve(),SOURCE/'plan.json',SOURCE/'collect.py',*history_sources]})
    out.mkdir(parents=True,exist_ok=False)
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    (out/'collect.py').write_text((SOURCE/'collect.py').read_text())
    with (SOURCE/'results.csv').open() as stream:
        fields=list(csv.DictReader(stream).fieldnames)
    fields.insert(1,'original24_trial_id')
    with (out/'results.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        writer.writerows({**{k:t[k] for k in fields if k in t},'status':'not_run'} for t in trials)
    old_md=(SOURCE/'INSTRUCTIONS.md').read_text()
    safety=old_md[old_md.index('collect.py自动切换'):old_md.index('| ID |')]
    md='''# v2 泛化16条：只执行新组合

用户已纠正：C2/C3已测，取消原24计划的8条新基线。旧24包原封保留作审计，不再执行；本包只按旧顺序筛出16条新组合，重新编号01–16，original24_trial_id保留来源。两轮各8条，四个新布局各目标色重复两次，第二轮反转双色顺序。首条是绿B2/红B3，抓红。

历史参照使用 `/data/work/so101-evidence/real-robot/smolvla-v2-v3-comparison-20261104/v2` 全部12条，不挑8条、不加入本次16条样本分母。离线视频视觉复核为11/12入碗（07失败）；这是已保存视频的视觉判断，不是新增人工验收。历史results.csv原为not_run，不能当作结论；报告、visual_results、原计划、全部执行回执/记录状态/dataset meta/视频均按来源SHA绑定。analysis_cohorts将历史基线和本次新组合独立列出。

这次没有同期控制，无法完全消除时间和环境差异；每条预检仍照常进行。v2 20k及SHA沿用，全部格中心0mm、方块0°；纸碗、相机、光照和批准机械臂/腕部/夹爪初姿固定。仅筛查组合泛化，不宣称超出训练空间范围的外推或可靠率；不是训练示范。本次16条真实任务均未执行，results.csv为not_run。

```bash
'''
    md+=f'python3 {shlex.quote(str(out/"collect.py"))}  # 仅打印16条计划\npython3 {shlex.quote(str(out/"collect.py"))} --execute  # 用户在场、本地前台执行\n```\n\n'+safety
    md+='| ID | 原24 ID | 轮 | 布局（绿/红） | 目标 | 目标格 | dataset（episode0） |\n|---:|---:|---:|---|---|---|---|\n'
    for t in trials:
        md+=f'| {t["id"]:02d} | {t["original24_trial_id"]:02d} | {t["round"]} | {t["layout"]} | {"绿" if t["color"]=="green" else "红"} | {t["target"]} | `{t["dataset"]}` |\n'
    md+='\n'+old_md[old_md.index('整轮执行用上方collect.py；'):]
    md+='\n历史12条仅作独立参照，不和本次16条合并成功率。上述每新布局/目标色各两条只是快速筛查；失败保留，不自动补跑或删去。\n'
    (out/'INSTRUCTIONS.md').write_text(md)
    assert {str(p):digest(p) for p in sorted(SOURCE.rglob('*')) if p.is_file()}==source_hashes
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUTPUT)
    print(prepare(parser.parse_args().output))
