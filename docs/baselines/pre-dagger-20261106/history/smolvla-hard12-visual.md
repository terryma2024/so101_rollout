# 12条SmolVLA独立视觉审计

**按指令成功9/12（75%）**：01–06、10–12成功；08、09要求绿却将红块入碗；07反复触碰/推移红块，没有确认抓起或入碗。四组分别为3/3、3/3、0/3、3/3。

01、04先空抓撤回再成功；12约6秒短暂空爪撤回后成功；08重试后仍抓错颜色。初姿均大致为右侧折叠、张爪、碗空；侧视颜色顺序符合计划，未量化精确格心偏差。没有在已查看的1fps帧中看到人手帮助，不能排除帧间短暂介入。

首次物理接触颜色保留不确定：相邻块在侧视存在遮挡，腕视显示夹爪路径可能先经过另一块。CSV中的首次触物下界用于保守选择触物前离线输入，不是精确接触时刻。抓起与入碗时间为约±1秒粗标。

独立表：observed-results.csv；原始results.csv没有修改。视频元信息及原始路径见video-metadata.json；原视频保留。全部预览已修复排版，无裁底；单帧为480×360，图表长边≤1560。以下英文方法记录供复核。

# Independent visual audit of 12 SmolVLA trials

Task success: **9/12 (75%)**. G C2/R C3 green: 3/3; same layout red: 3/3; R C2/G C3 green: 0/3; same layout red: 3/3. Trials 08/09 transfer red to bowl despite green task. Trial 07 repeatedly contacts/displaces red, no sustained lift or bowl entry; green remains on paper. These are observations, not proof of a particular policy cause.

Trials 01/04 fail an early grasp and retry before successful transfer. Trial 12 has a brief empty retreat around 6s then succeeds. Trial 08 also retries before wrong-color red transfer. Initial arm posture appears consistently folded on right with gripper open, both blocks on paper and bowl empty. Color order matches planned layouts in side view; exact grid centering was not measured.

## Evidence and limitations

`observed-results.csv` is independent of the original not_run results.csv, which was not modified. `video-metadata.json` stores ffprobe output and source paths for all 24 videos. Original videos retained. Frames extracted with ffmpeg libdav1d at 1fps and scaled to 480px width. All sheet images checked <=1600px per side before viewing. Each per-camera directory includes chronological numbered previews (001 approximately video 0s). Side sheets were inspected throughout; wrist sheets 04/07 and contact montage supplement interpretation. No human assistance is visible in reviewed frames; this does not exclude brief actions between samples. Exact first contact color is conservatively unresolved: adjacent blocks overlap in side view, and wrist view shows approach can span both blocks. First-contact lower bounds are conservative pre-contact sampling choices, not precise event timestamps.

全部逐秒图表已修复排版：每行390px，完整保留480×360帧和时间标签，每页最多12帧（1440×1560）。最终总览也为1440×1560，无裁底。

## Numerical-event correspondence (visual only)

Trial04 8s: empty gripper retracts after initial unsuccessful approach; 9-12s it reapproaches, 13s red is clearly lifted, 14-15s transferred/released into bowl. Trial07 14s: arm folded after unsuccessful sequence; 15s reaches again. Around24s it retracts empty, 25s reaches again toward blocks; 27-28s gripper near red, still no lift or bowl entry. Joint target step magnitudes are supplied by separate numerical audit and do not establish mechanical instantaneous motion or causality.
