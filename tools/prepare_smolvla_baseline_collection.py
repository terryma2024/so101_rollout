#!/usr/bin/env python3
"""Prepare a finite hard-baseline collection package; never run hardware."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shlex

MODEL=Path('/data/work/so101-policies/real-smolvla-red-green-v1-20261030/checkpoints/020000/pretrained_model')
MODEL_SHA='e96afce7f7bcb27237714421aa4f2e4360bc816ad3e89047363a0871ab0126bc'


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--session',default='20261102');p.add_argument('--suite',choices=['hard-diagnostic','other-positions'],default='hard-diagnostic');args=p.parse_args()
    if not args.session.replace('-','').replace('_','').isalnum():p.error('Simple alphanumeric session required')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);repo=Path(__file__).resolve().parents[1]
    files=[repo/x for x in ['src/so101_rollout/smolvla/recording.py','src/so101_rollout/smolvla/async_engine.py','src/so101_rollout/smolvla/rollout.py','src/so101_rollout/smolvla/persistent_session.py','scripts/rollout_smolvla_session.sh','scripts/rollout_smolvla.sh','rollout_smolvla.sh','tools/prepare_smolvla_baseline_collection.py','config/arms.env','config/camera.env','config/preflight.json']]
    hashes={str(f):digest(f) for f in [*files,*MODEL.iterdir()] if f.is_file()};assert hashes[str(MODEL/'model.safetensors')]==MODEL_SHA
    trials=[]
    layouts=['G C2/R C3','R C2/G C3'] if args.suite=='hard-diagnostic' else ['G B1/R B2','G B2/R B1','G D3/R D4','G D4/R D3']
    if args.suite=='hard-diagnostic':
        conditions=[(layout,color,rep) for layout in range(1,3) for color in ['green','red'] for rep in [1,2,3]]
    else:
        # Two complete repeat rounds; alternate task order across layouts and rounds.
        conditions=[(layout,color,rep) for rep in [1,2] for layout in range(1,5) for color in (['green','red'] if (layout+rep)%2==0 else ['red','green'])]
    for layout,color,rep in conditions:
        identifier=len(trials)+1;name=f'eval-smolvla-{args.suite}-l{layout}-{color}-r{rep}-{args.session}'
        recording=out/'recordings'/f'trial-{identifier:02d}'
        env=dict(SO101_CONFIG_DIR=str(repo/'config'),HF_HOME='/data/models/huggingface',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',INFERENCE_RECORDING_PATH=str(recording),TASK=f'Put the {color} cube into the paper bowl',MAX_REL='30',N_ACTION_STEPS='50',PREFETCH_STEPS='10',RESUME='0',TE='0',CHECK_ONLY='0')
        command=[str(repo/'rollout_smolvla.sh'),name,'1',str(MODEL)]
        trials.append(dict(id=identifier,layout=layouts[layout-1],color=color,trial=rep,dataset=name,dataset_path='/data/work/so101-datasets/'+name,episode_index=0,recording_path=str(recording),env=env,argv=command,command=shlex.join(['env',*[k+'='+v for k,v in env.items()],*command])))
    manifest=dict(suite=args.suite,status='Original hard baseline diagnostics, not an accepted smoothing candidate. User executes after main review.',repo=str(repo),model=str(MODEL),model_sha256=MODEL_SHA,sha256=hashes,parameters=dict(transition='hard',fps=20,horizon=50,prefetch=10,max_relative_target=30,episode_time_s=30,num_episodes=1,recording_max_items=256,recording_max_bytes=134217728),trials=trials)
    (out/'plan.json').write_text(json.dumps(manifest,indent=2))
    with (out/'results.csv').open('w') as f:
        fields=['id','layout','color','trial','dataset','episode_index','status','initial_pose','target_correct','first_contact','picked','in_bowl','pushed','aborted','reason','recording_path','preflight_path','notes'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for t in trials:w.writerow({k:t[k] for k in fields if k in t}|{'status':'not_run'})
    source='''#!/usr/bin/env python3
"""Finite session launcher: dry-run by default, --execute requires operator."""
import json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent
plan=json.loads((root/'plan.json').read_text())
env=dict(os.environ, HF_HOME='/data/models/huggingface',TORCH_HOME='/data/models/torch',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
env['PYTHONPATH']=str(Path(plan['repo'])/'src')+os.pathsep+env.get('PYTHONPATH','')
python='/data/work/venvs/so101-smolvla-061/bin/python'
os.execve(python,[python,'-m','so101_rollout.smolvla.persistent_session','--plan',str(root/'plan.json'),*sys.argv[1:]],env)
'''
    (out/'collect.py').write_text(source)
    md=f'# {len(trials)}条原hard基线诊断采集\n\n不是已通过的优化策略。按plan.json固定布局/任务/重复，整轮单进程仅加载一次模型，每条独立dataset（episode0），一次性交付，无需逐条向agent汇报。每条前本地Enter确认恢复完成；上一worker退出和设备断连后才等待下一条；不会20秒后自动开始下一条，不无限循环。中断后显式 `--start-trial N` 恢复，前序必须有complete回执且剩余路径全新；失败条不自动覆盖或跳过。\n\n'
    md+='```bash\n'+f'python3 {shlex.quote(str(out/"collect.py"))}  # 仅打印命令\n'+f'python3 {shlex.quote(str(out/"collect.py"))} --execute  # 主审后用户在场执行\n'+'```\n\n'
    md+='每条前恢复同一批准初姿和夹爪、当条计划格方块与纸碗位置（格中心0mm，方块0°）；每条连接会捕获其startup姿态。每条正常teardown默认用约3秒回startup姿态，再断开；等动作结束再伸手重摆。每条30秒，→可提前结束当前条，Esc停本轮并保留当前条，←会丢弃重录当前条故不要用来保存失败。Ctrl-C可结束整个包；键盘监听依赖本地桌面焦点/pynput，不能假设SSH按键可控制。\n\n'
    md+='每次launcher先锁相机并作预检，成功后接机器人。操作者确认双相机640×480/映射/对齐/光照、校准、初姿、空间与停止入口。异常阶跃/碰推/错目标/无效折叠持续时中止，保留失败。记录选色、首次接触位置、夹起/入碗/碰推/中止原因。\n\n'
    md+='| ID | 布局 | 目标 | 重复 | dataset（episode0） |\n|---|---|---|---:|---|\n'
    for t in trials:md+=f'| {t["id"]:02d} | {t["layout"]} | {t["color"]} | {t["trial"]} | `{t["dataset"]}` |\n'
    md+='\n整轮请使用上方collect.py --execute；plan.json中的逐条launcher命令只保留作参数审计，逐条运行会重新加载模型。\n\n'
    md+='结果在`/data/work/so101-datasets/<dataset>/`；完整request/noise/chunk/安装/output记录在包内`recordings/trial-XX/`。预检/遥测随机路径由终端打印，驱动写入`trial-XX-execution.json`，原输出在`terminal-logs/`。`status.json.complete=false`或缺失表示记录不完整，不能当完整重放。`results.csv`填人工结果；全部完成后一次性交回包路径和CSV即可。\n'
    md+='\n仅在两条之间输入q正常退出、之前编号都有完整执行回执时，使用`python3 collect.py --execute --start-trial N`从明确尚未执行编号继续。恢复会核验plan SHA、id/dataset/recording、实际完整记录、dataset meta及终端日志，剩余路径必须全新。Esc/异常/半条保留证据，不得盲目跳到下一条、覆盖或删除后重试。执行完成、记录完整和人工任务结果分别判断；CSV如实保留错色/碰推/未入碗和unknown。\n'
    (out/'INSTRUCTIONS.md').write_text(md)
    print(out)

if __name__=='__main__':main()
