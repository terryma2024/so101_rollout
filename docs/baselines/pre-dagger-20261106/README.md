# DAgger 前 ACT / SmolVLA 真机 rollout 冻结档案

归档日期：2026-11-06。此档案保存既有证据的可读结论、194个有效试次及66个失败或协助完成case；本轮只读历史文本/JSON，未重新视觉验收、操作硬件、训练或改写源证据。原录像、截图、大型推理archive和遥测仍在 `/data/work/so101-evidence/real-robot/` 及 `/data/work/so101-datasets/`，不复制进repo。

[批次/模型汇总](batches.json) → [失败case索引](failure-index.json) → 对应 `trials/*.json` 的完整逐条记录。所有有效试次均收录，因此能直接核对成功分母，而非只有失败精选。逐case包含model/hash、batch、编号基数、dataset、计划/实际布局、任务、观察、协助、失败类别及证据路径。外部证据不可用时，repo内仍可阅读布局标签和既有判断；所有原始输入SHA见[来源清单](source-provenance.json)，它不是新做的原始视频全量完整性审计。

|批次及逐条JSON|日期/版本|目标色最终入碗|主要边界|
|---|---|---|---|
|[ACT P0](trials/act-p0.json)|10-29，独立红/绿ACT|46/60：绿26/30、红20/30|61源记录中1条排除；严格计划布局45/59|
|[ACT新绿](trials/act-green-new.json)|10-30，P2新增40示范、133总示范、100k|7/10|失败03/04/07|
|[ACT旧绿](trials/act-green-old.json)|10-30，93示范、100k|6/10|失败01/04/05/10；01错红入碗|
|[SmolVLA同步](trials/smolvla-sync5k.json)|10-31，v1 5k|0/2|绿错红入碗、红抓取失败，严重抖动|
|[SmolVLA异步配对](trials/smolvla-async4.json)|11-02，v1名义20k|2/4：绿0/2、红2/2|名称含20261031，实际日期11-02；早期未冻结权重SHA|
|[v1 hard12](trials/smolvla-hard12.json)|11-02，20k硬切|9/12：绿3/6、红6/6|07无稳定抓起，08/09错红入碗|
|[v1 other16](trials/smolvla-other16.json)|11-02，20k|7/16：绿3/8、红4/8|01/07/08/10错色入碗；09时序异常；15错夹未释放/overload|
|[v2 C2/C3](trials/smolvla-v2-hard12.json)|11-04，20k full262|11/12：绿5/6、红6/6|07无稳定抓起，约25秒可见人手但接触/介入未证实|
|[v3 C2/C3](trials/smolvla-v3-hard12.json)|11-04，8400 balanced112|7/12：绿3/6、红4/6|06/08/09/12错色抓起；08退出时overload；09–12来自独立续测01–04|
|[v2 generalization16](trials/smolvla-v2-generalization16.json)|11-04，20k|9/16：绿2/8、红7/8|03/12错红入碗；05/06/08/14/15无稳定抓起|
|[v2 random20](trials/smolvla-v2-random20.json)|11-04，20k|14/20：绿6/10、红8/10|19错红入碗；05/11/12/14/20无稳定抓起；08/13指令为red，属成功|
|[v2 adhoc20](trials/smolvla-v2-adhoc20.json)|11-04，v2上下文|物理11/20，自主10/20|绿自主7/10、红自主3/10，红另1条经协助；不可删协助条改分母|

“最终入碗”沿用历史标签，不能替代首抓成功、全程无重试或新操作者验收。未知协助的成功条 `autonomous_success=null`；已确认失败为false。`autonomous_success_count=null` 表示无法独立确认全批自主成功数；另列 confirmed 数和unknown数，不能将未知写成0成功。adhoc20的自主10/20另有明确历史标注。各批设计、日期、姿态和版本不同，不汇总为一个总体成功率，不把小样本对照视为显著性或因果证明。

## ACT P0 的编号、排除与计划偏差

完整历史[ledger副本](history/act-p0-ledger.md)、[原聚合summary](p0-original-summary.json)和[排除记录](p0-excluded-records.json)共同保留。`recorded_episode_1based` 是原报告第几条，`episode_index_0based=recorded_episode-1` 是源dataset索引；`layout_row_1based` 是纸面布局行，三者不可混用。

- green-r2 recorded07（episode_index6）只有1帧、0.05秒，开头目标已在碗；保留源记录但不入60有效分母。后续recorded08–11对应布局7–10，不能顺移源episode索引。
- green-r1 recorded04实际A4/C3，计划A4/C2；它最终成功但属于变体。绿含变体26/30，严格布局25/29；总体含变体46/60，严格45/59。缺少的严格布局不能用变体补满。
- red-r1布局顺序1,2,3,4,5,7,8,9,10,6；green-r3为1,2,3,4,5,7,8,6,9,10；其余见逐条JSON。
- 用户2026-10-30确认全部P0无协助。green-r3 recorded09、red-r2/red-r3 recorded01仅收尾摆放/键盘操作，不标协助。green-r3 recorded09初帧手部遮挡仍保留。
- 30秒记录也可能成功，22.1秒记录也可能失败。首抓率、精确完成/停止时间、实际TE/限幅事件均未独立恢复；TE0/MAX_REL30/20Hz/30秒仅为当时指示协议。

[10-30 ACT新旧完整报告](history/act-green-comparison.md)保留7/10与6/10、跨日光照/姿态混杂及新增数据40条审计。不能用主观流畅度或历史26/30覆盖本轮末态；也不能据单轮相差1条断言新版稳定更优或更差。旧版04/05/10只保守记未完成入碗，具体机制待核。P0绿最弱B2/B1为0/3，红A4/C2和D1/C1均0/3、D4/D3为1/3；这些是补采线索。

## SmolVLA 证据入口

- [历史时间线、数据split、训练及检查点证据](../../experiments/smolvla-history-evidence-20261104.md)和[端到端总报告](../../reports/smolvla-so101-end-to-end-report-20261104.md)。同步/异步离线性能实验不是新增真机任务试次：[同步smoke](../../experiments/smolvla-local-smoke-20261030.md)、[异步原型](../../experiments/smolvla-async-20261030.md)、[异步入口](../../experiments/smolvla-async-rollout-20261031.md)。
- [首次同步真机历史报告](history/smolvla-sync-first-rollout.md)、[异步四条](../../experiments/smolvla-paired-rollout-20261102.md)、[hard12视觉副本](history/smolvla-hard12-visual.md)、[hard12数值](../../experiments/smolvla-hard-12trial-numeric-20261102.md)。v1后续硬切记录对应权重SHA以各批plan为证，不能反推早期没有冻结的权重。
- [other16视觉副本](history/smolvla-other16-visual.md)、[位置测试结论](../../experiments/smolvla-other-positions-conclusions-20261102.md)。01的listener清理异常后311帧完整，计有效失败；15超时持物并overload，581帧完整，计有效失败；启动venv/parser失败不新增物理试次。09的29starved/7skipped独立标出，不能纯归因示教覆盖。
- [v2/v3对照](../../experiments/smolvla-v2-v3-real-comparison-20261104.md)、[generalization16](../../experiments/smolvla-v2-generalization16-results-20261104.md)、[random20](../../experiments/smolvla-v2-random20-results-20261104.md)、[adhoc20](../../experiments/smolvla-v2-adhoc-results-20261104.md)。原results模板的not_run/not_recorded不是“未执行”的证据，执行完整也不是任务成功。

v3逐条保留 `trial_id_1based` 原01–12及 `source_trial/source_suite`。原09–12映射 `v3-continuation-original09-12` 的01–04，每个独立dataset仍episode_index0。v2/v3起始夹爪、腕部初姿不同；裁剪数据、采样、stats、步数、schedule同时变化，不能把退步单独归因均衡采样。

adhoc的G1/G2各5条，两个目录都有效；R-01是红第2条（episode_index1），明确人工协助。历史报告约8–9秒只标手进入/协助片段，不是精确恢复接管时刻，本档案所有 `recovery_takeover_time_s=null`。其余adhoc协助字段沿用既有visual JSON；本轮没有新增全程无人介入认证。

## 冻结用途与恢复示教候选

这些rollout是策略测试轨迹，**不属于专家成功示范**，不自动合入任何train split，不把失败后的偶然成功或人工辅助末态改标专家演示。所有精确格位、yaw、初姿、首接触/首抓、重试次数、恢复接管时刻和停止原因，只在来源已证实时填写；`null`为待核。计划layout保存在每条JSON，不代表实摆毫米级认证；actual_layout仅在历史已核实的P0/other16填写。其余可见颜色顺序与计划大致相符也不冒充精确测量。

以下是后续有人监督、重新冻结协议并录制专家纠正的候选，不是已完成恢复示教：

|候选|历史case|待补的专家纠正信息|
|---|---|---|
|抓空后仍空爪运输/反复接近|P0弱布局、v1 hard07、v2/v3 hard07、gen05/06/08/14/15、random05/11/12/14/20、adhoc未入碗条|确认稳定夹持前停止运输；失败检测、重新对齐/抓取、完成释放；逐帧核定可接管状态|
|失败重试后选色漂移/错色抓放|ACT old01、hard08/09、other01/07/08/10/15、v3 06/08/09/12、gen03/12、random19|在实际失败观测上保留原任务，专家重新选择目标；错色持物时的安全纠正需另定协议|
|持物未释放/退出overload|other15、v3 08|独立核查释放与夹爪状态，记录安全终止和人工接管，不把故障清理动作当任务示范|
|供给时序异常|other09|先隔离29starved/7skipped的执行因素；不把技术异常直接当数据不足|
|明确协助片段|adhoc R-01|保留原失败/协助标签；补建真实介入边界及专家动作，不据8–9秒粗观察补造时间戳|

本批布局和失败现已用于开发、补采决策和恢复场景选择。若后续用于DAgger训练/纠正选择，**不得再作为独立测试集**；只能作为冻结历史基线或已知场景回归。DAgger后的独立验收需另建未参与训练/选择的冻结布局或日期/session，保留来源分组，不能把旧validation偷偷移入train。

## 核验与缺口

每批JSON内success计数和失败索引可用以下纯Python离线命令复核（在repo根目录）：

```sh
python3 - <<'PY'
import json
from pathlib import Path
p = Path('docs/baselines/pre-dagger-20261106')
expected = {'act-p0':(46,60), 'act-green-new':(7,10), 'act-green-old':(6,10), 'smolvla-sync5k':(0,2), 'smolvla-async4':(2,4), 'smolvla-hard12':(9,12), 'smolvla-other16':(7,16), 'smolvla-v2-hard12':(11,12), 'smolvla-v3-hard12':(7,12), 'smolvla-v2-generalization16':(9,16), 'smolvla-v2-random20':(14,20), 'smolvla-v2-adhoc20':(11,20)}
cases = {}
for f in (p/'trials').glob('*.json'):
    d = json.loads(f.read_text()); rs = d['trials']
    assert (sum(r['target_final_in_bowl'] for r in rs), len(rs)) == expected[d['batch']]
    assert all(r['recovery_takeover_time_s'] is None for r in rs)
    for r in rs:
        assert r['case_id'] not in cases
        cases[r['case_id']] = r
index = json.loads((p/'failure-index.json').read_text())
assert len(cases) == 194 and index['count'] == len(index['cases']) == 66
assert {r['case_id'] for r in index['cases']} == {k for k,r in cases.items() if not r['target_final_in_bowl'] or r['human_assistance'] is True}
for r in index['cases']:
    source = json.loads((p/r['file']).read_text())['trials'][r['trial_array_index_0based']]
    assert source['case_id'] == r['case_id'] and source['failure_categories'] == r['categories']
adhoc = json.loads((p/'trials/smolvla-v2-adhoc20.json').read_text())
assert adhoc['autonomous_success_count'] == 10
assisted = [r for r in adhoc['trials'] if r['human_assistance'] is True]
assert len(assisted) == 1 and assisted[0]['episode_index_0based'] == 1 and assisted[0]['case_id'].endswith(':R-01')
print('PASS: 12 batches, 194 valid trials, 66 failures/assisted cases; denominators and numbering checked')
PY
```

仍缺：P0实际启动命令/权重完整溯源、早期异步及adhoc实际权重SHA、大多数批次全程人工协助排除、首抓/重试/停止和恢复时间、毫米级实摆。保留未知，不用模板计划或稀疏图像填空。历史报告内短相对路径仍相对其原证据目录；repo内导航使用本README明确链接。归档输入已记SHA，原证据未改变。
