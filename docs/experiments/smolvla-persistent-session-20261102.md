# SmolVLA persistent finite session — 2026-11-02

终端监听器兼容修复（同日）：LeRobot TerminalKeyListener不是Thread，没有ident/join/is_alive接口；现在对listener执行stop，并仅对实际线程对象join，保留native teardown前取得的内部线程引用。测试覆盖真实TerminalKeyListener、Thread接口和封装线程，以及native两case清理路径。首次真实case01已完成返初姿和断连才触发旧ident访问错误；独立recovery-audit.json确认1条311帧、双视频完整解码、348条推理记录完整、action重放一致。原错误receipt/plan/log留在包内failed-attempts/listener-cleanup-error-20261102；当前回执明确标记runtime_completed_without_error=false和恢复依据，仅接受完整采集记录用于继续case02，不声称任务成功。恢复命令使用 --start-trial 2，不覆盖或重跑case01。

启动链修复（同日）：生成器的 `os.execve` 现将完整venv解释器路径同时用作可执行文件和argv[0]，避免CPython错误发现系统环境。配置解析提取为实际入口使用的 `parse_case_config`，显式给LeRobot parser.wrap提供真实RolloutConfig类；本模块的future annotations原先产生字符串，而0.6.1的getfullargspec不会自动解析它。此前dry-run及独立解析片段未覆盖这两处实际启动差异。新增回归验证真实venv导入torch、所有16条结构化配置通过实际解析函数；真机用户的失败回执和日志已归档于测试包 `failed-attempts/parser-type-error-20261102/`，没有删除失败证据，没有生成dataset或inference记录。

目标：人工有限采集整轮只加载一次20k模型，同时每条独立native context、dataset、scheduler、worker、recorder和任务。未进行任何真机动作、相机连接或训练。

入口：生成包的 `python3 <package>/collect.py` 默认只打印；本地在场操作者显式加 `--execute` 才执行。也可 `scripts/rollout_smolvla_session.sh --plan <package>/plan.json --execute`。每条结束完成native返初姿及断连，worker退出屏障通过后等待下一条Enter。q结束有限会话。policy/pre/post在case之间reset，下一worker的首请求仍会再次按generation reset，不继承旧future/queue/task/recorder。

实现仅在当前进程scoped绑定LeRobot0.6.1 `context._load_pretrained_policy` 与 `make_pre_post_processors`；调用官方 `build_rollout_context` 和官方episodic strategy setup/run/teardown，不复制控制循环、不改安装包。模型和processor cache配置发生变化会拒绝。robot/camera每条重连；`STRUCTURED_ARGS_PATH`通过原shell以JSON数组导出参数，不执行stdout文本、不加载模型或触硬件。配置解析沿用native parser.wrap，保留policy.path加载语义。

每条锁相机、独立preflight成功后才构建native context并连接机器人。20Hz、hard horizon50、prefetch10、MAX_REL30不变，检查单条单episode、正常返初姿和无torch.compile。独立录制保留request/observation/noise/chunk/install/output与任务；terminal-logs/trial-XX.log保留native warnings、preflight输出和异常。native setup/build/teardown失败停止会话，已创建设备逐个断连；不跳失败、不覆盖。异常路径可能不能完成正常返初姿，必须现场检查，不能自动进入下一条。

恢复：新进程显式 `--start-trial N`，允许重新加载一次模型。N之前每条回执必须complete、绑定当前plan SHA/id/dataset/recording_path，实际完整recording status、dataset meta单episode和terminal log必须存在；N之后任何已有dataset/recording/log/receipt均拒绝。因此失败条不会被覆盖或自动跳过。回执是采集完整性，不等同任务成功，错选色/抓取失败仍由人工填写results.csv。

无硬件验证：`tests/test_smolvla_session.py`覆盖fake policy两任务缓存load1/reset、独立真实scheduler队列和task、worker退出与设备断连、build异常清理、processor变更拒绝以及恢复门槛。`tests/test_smolvla_collection_package.py`验证16条包default dry-run不启动硬件。初始RED为缺失persistent_session模块，随后GREEN。原生结构化参数解析已用真实0.6.1环境确认，没有创建robot/context。

主线程完成真实20k无硬件2-case smoke：证据 `/data/work/so101-evidence/real-robot/smolvla-persistent-session-20261102/offline-smoke/verification.json`，工具 `tools/smolvla_session_smoke.py`。GPU使用前检查空闲；loader计数1，processor同一实例，两个独立engine/worker/recorder，各记录15个实际output，任务tokens不同。第一次模型+processor阶段13.247499s，第二case缓存获取0.000138s；首action分别1.352s和1.152s（含日志manifest hashing等，非纯推理延迟）。上一独立进程方案每条都会重复cold load；本次没有重跑旧方案真机启动，不能把上述离线差值说成完整硬件每条节省时间。无真机全流程通过结论。

全套pytest与最终包冻结由主线程和other-positions agent在整合后记录；此文中的离线smoke不是相机、机械臂、键盘/显示流程的验收替代。
