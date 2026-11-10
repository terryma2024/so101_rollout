"""Validate completed refinement evidence and write its Chinese report."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json, subprocess, hashlib
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parent
s=json.loads((ROOT/'statistics.json').read_text())
m=json.loads((ROOT/'manifest.json').read_text())
v=json.loads((ROOT/'verification.json').read_text())
y=json.loads((ROOT/'followup/yuyv-diagnostics.json').read_text())
h=json.loads((ROOT/'followup/pink-highlight-audit.json').read_text())
assert m['error'] is None and m['restore_error'] is None
assert m['sequence']==[67,100,110,67] and all(m['final_state_matches'].values())
assert json.loads((ROOT/'jpeg-warning-frames.json').read_text())==[]
assert y['validation']['mismatched_channel_samples']==0
for cam,device in [('wrist','/dev/v4l/by-id/usb-icSpring_icspring_camera-video-index0'),('side','/dev/v4l/by-id/usb-icSpring_icspring_camera_202404160005-video-index0')]:
    a=np.load(ROOT/cam/'all-frame-metrics.npz')
    assert a['median_rgb'].shape==(v[cam]['complete_frames'],27,3)
    assert all(np.isfinite(a[k]).all() for k in a.files if k!='keys')
    assert all(c['frames']==c['captured_condition_frames'] for c in s[cam]['conditions'].values())
    cur=subprocess.run(['v4l2-ctl','-d',device,'--info','--get-fmt-video','--get-parm','--list-ctrls-menus'],capture_output=True,text=True,check=True).stdout
    assert cur==(ROOT/f'{cam}-before.txt').read_text()==(ROOT/f'{cam}-after.txt').read_text()
    (ROOT/f'{cam}-final-live-verification.txt').write_text(cur)
    v[cam]['usable_condition_frames']={k:c['frames'] for k,c in s[cam]['conditions'].items()}
    v[cam]['fresh_final_live_state_matches_original']=True
    v[cam]['fresh_final_live_verified_at']=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
assert Image.open(ROOT/'gamma-comparison-preview.png').size==(1000,1588)
(ROOT/'verification.json').write_text(json.dumps(v,indent=2))
p=json.loads((ROOT/'proposal.json').read_text())
p.update(status='executed_and_original_controls_restored',authorization={'user_message':'按这个细测表执行','sequence':[67,100,110,67]},result_manifest='manifest.json',final_live_verified_at=v['wrist']['fresh_final_live_verified_at'])
(ROOT/'proposal.json').write_text(json.dumps(p,ensure_ascii=False,indent=2))
labels={'g67_initial':'67初始','g100':'100','g110':'110','g67_repeat':'67复拍'}
lines=['SO101 腕部 gamma 细测：67→100→110→67','2026-11-10 约21:46:42—21:48:33（Asia/Shanghai）','',
'结论',
'100、110均提升本布局暗部并缩小红绿方块的跨视角RGB距离，但都新增了浅粉色块红通道高值及实际转换截断。110暗部改善更大，亮部代价也明显更高，暂不列为优先候选；100仅可作为有已知代价的折中候选，不能宣称通过“无新增高光截断”的要求。本次不采用任何新生产参数。当前腕部gamma67、曝光40，侧面全部参数保持原值。',
'', '执行与恢复',
'依据用户“按这个细测表执行”的授权，仅临时写腕部gamma。两路连续采集，先等待30秒启动稳定，再依次67、100、110、67，每档等待5秒、记录15秒。曝光40、手动曝光模式1、AWB=1、saturation25不变。每次写入后读回成功。',
'finally恢复gamma67；退出读回以及分析结束时再次只读查询，两路全部控制、格式和声明帧率快照均与实验前一致。没有机器人动作、训练、部署或生产配置变更。',
'', '数据质量',
'腕部2270完整帧、491张PNG；侧面2188完整帧、512张PNG，共4458帧及1003张PNG。全部PNG与相应采集字节重新解码逐像素一致。侧面2188帧逐帧JPEG解码审计无警告，无帧因该项排除。',
'所有完整帧保留并计算27个固定ROI指标，最终汇总仅使用稳定后的15秒窗口。各档有效帧数（腕部/侧面）：']
for cn in labels:
    lines.append(f"{labels[cn]}：{s['wrist']['conditions'][cn]['frames']}/{s['side']['conditions'][cn]['frames']}")
lines += ['主机接收时间不是曝光时间，也不代表硬件同步；没有driver sequence证据，不能宣称零丢帧。流结束后的不完整尾字节不计入完整帧。stream_capture.py的180秒是最长保护上限，实际约110秒后由STOP停止。',
'人工预览及色卡局部相位相关支持沿用原ROI；本批相对初始参考的位移代理小于0.15px。该方法不是几何真值。单路原图640×480，对照图1000×1588，查看前均检查尺寸，原图保留。',
'', '固定ROI结果',
'表中RGB为每帧ROI中位数再取时间中位数，是解码显示空间的0—255码值。低值比例为固定绿块ROI像素max(R,G,B)<32的时均占比。高值比例为固定浅粉色块ROI的R>=253；它是接近上限的警告阈值，不能单独当作截断证明。',
'条件 | 腕部红块RGB | 腕部绿块RGB | 绿块低值 | 浅粉R>=253 | 浅粉R==255 | 转换前R>255']
for cn in labels:
    r=s['wrist']['conditions'][cn]['rois'];hh=h['conditions'][cn]
    assert abs(hh['R_ge253_fraction']-r['chart_r1_c3']['ge253_fraction'][0])<1e-12
    lines.append(f"{labels[cn]} | {r['cube_red']['median_rgb']} | {r['cube_green']['median_rgb']} | {100*r['cube_green']['max_channel_lt32_fraction']:.2f}% | {100*hh['R_ge253_fraction']:.2f}% | {100*hh['R_eq255_fraction']:.2f}% | {100*hh['pre_clamp_R_gt255_fraction']:.3f}%")
lines += ['', '暗灰和亮部',
'两级最暗灰（chart_r4_c0 / chart_r5_c0）的中位RGB及原始Y中位数：']
for cn in labels:
    r=s['wrist']['conditions'][cn]['rois'];yy=y[cn]['rois']
    lines.append(f"{labels[cn]}：{r['chart_r4_c0']['median_rgb']} / {r['chart_r5_c0']['median_rgb']}；Y={yy['chart_r4_c0']['y_median']}/{yy['chart_r5_c0']['y_median']}")
lines += ['100仍有最暗灰压在低值端，110使两级暗灰进一步分开。110白纸RGB=[221,216,232]、Y=205，最浅灰RGB=[214,211,227]、Y=199；未出现先前曝光80试验的Y=232白纸平台，但彩色单通道仍能先发生截断。',
'浅粉色块是主要新增高值区域。100的其余23个色卡中心ROI各通道>=253比例均为0；110另有chart_r5_c2约0.0408%、chart_r2_c2约0.0149%的少量高值通道像素。详见statistics.json。',
'额外针对浅粉色块按原始YUYV重算R通道，并与OpenCV结果逐像素核对。100下0.114%的取样通道在RGB截断前R>255，110下4.306%，确认存在转换到RGB输出时的真实溢出截断；这仍不证明传感器RAW已截断。',
'', '跨视角一致性与红绿可分性',
'红块/绿块两视角RGB中心距离（非标定DeltaE，侧面相机不是颜色真值）：']
for cn in labels:
    pp=s['paired_observation'][cn]
    lines.append(f"{labels[cn]}：{pp['cube_red']['rgb_distance']:.2f} / {pp['cube_green']['rgb_distance']:.2f}")
lines += ['侧面红块约[172—172.5,10,19—19.5]，绿块约[28,65.5—66,36.5—37]，同批变化较小。各档有效帧内两路固定红ROI均保持R>G、绿ROI均保持G>R，优势通道反转计数均为0；腕部红绿RGB中心距离88.28→125.66→126.99，复拍90.09。这不是复杂背景分类准确率或SmolVLA效果验证。',
'固定方块ROI较小，材质透光且面未标记，光照和观察方向仍混入差异；没有标准色卡真值，不能给出绝对颜色误差。',
'', '时间稳定性与复拍',
'每个15秒窗内，方块主要通道首5秒至末5秒变化在0—2码值范围。腕部红R标准差2.83→3.04→3.08，绿G标准差1.38→2.00→2.13，复拍2.87/1.37；提亮没有降低绝对码值的时间波动。不能把低值减少等同于信噪比改善。',
'首尾gamma67红块[87,0,0]→[89,0,0]，绿块[0,15,0]→[0,14,0]；白纸[191,186.5,202]→[191,186,202]，最浅灰[182,179,196]→[182,178,195]。本批恢复接近，但AWB保持开启，仅覆盖同位置约110秒。',
'本批初始亮度高于粗测批（例如白纸[191,186.5,202]，粗测[182,177,194]）；不能把本批110与上一批120的高值比例直接解释为纯gamma曲线关系。候选仍须同批比较和留出验证。',
'', '原始码值复核',
f"对四档有效腕部窗口{sum(y[cn]['frames'] for cn in labels)}帧、9个ROI的{y['validation']['tested_channel_samples']}个通道样本重算OpenCV整数BT.601转换，差异为0。另有浅粉专项复核。设备声明YUYV/BT.601/limited range，未发现RGB/BGR颠倒或所用转换与声明格式不一致的证据；设备元数据本身也不构成传感器色度标定。",
'', '下一步建议（尚未执行）',
'先明确亮部验收：若要求固定亮色ROI完全不新增RGB转换溢出，则100、110均未通过；此前90仅在粗测A位置未见被测ROI高值，仍只是待验证的保守候选。若允许少量截断，100可保留为折中候选，代价必须保留记录；110暂不优先。',
'停止继续密集扫gamma。下一轮应固定候选和亮部容忍阈值，先在B位置比较，再在C位置/倾角留出验证暗部、亮部、红绿区分和时间波动；也应关注两视角照明/反射差异，避免只用gamma追求RGB距离。B/C需要用户调整实物布局，尚未进行；任何下一轮硬件写入仍遵守既定临时实验边界。',
'当前数据不支持最终生产参数或模型收益结论，不改旧数据或rollout输入。',
'', '主要文件',
'manifest.json、events.jsonl、各档readback、before/after、final-live-verification：执行及恢复证据。',
'statistics.json、两路all-frame-metrics.npz、roi.json：最终汇总、全部帧指标及固定几何区域。',
'verification.json、jpeg-warning-frames.json、roi-placement-check.json：保存一致性、JPEG审计及位置检查。',
'gamma-comparison-preview.png：四档双路对照；各档original.png及采集stream.bin保留。',
'followup/yuyv-diagnostics.json、pink-highlight-audit.json：原始码值、整数转换和亮部截断复核。',
'run_trial.py、stream_capture.py、analyze_trial.py、finalize.py、audit_jpeg.py、verify_trial.py、placement_check.py、complete_report.py及followup脚本：证据目录内程序；不写仓库生产文件。',
'artifact-sha256.json：本次证据文件哈希清单。']
(ROOT/'report-zh.txt').write_text('\n'.join(lines)+'\n')
files=[p for p in ROOT.rglob('*') if p.is_file() and p.name!='artifact-sha256.json' and '__pycache__' not in p.parts]
hashes={}
for p in sorted(files):
    digest=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):digest.update(block)
    hashes[str(p.relative_to(ROOT))]=digest.hexdigest()
(ROOT/'artifact-sha256.json').write_text(json.dumps(hashes,indent=2))
print('REPORT_WRITTEN_AND_VERIFIED',len(hashes),'hashed artifacts; fresh device snapshots match original')
