# SmolVLA v2 Hugging Face 发布状态（2026-11-04）

**已上传并完成远端校验。** 当前登录账号确认为 `zjumty`；以下三个仓库均为 public、非 gated，已验证匿名可读取。全部 62 个发布文件的文件名、大小与 SHA256 均匹配发布清单（不含 Hub 自动生成的 `.gitattributes`）。

| 公开仓库 | 内容 | 原始文件数 / 字节 | 含卡片和溯源的发布文件数 / 字节 |
|---|---|---:|---:|
| [zjumty/real-smolvla-red-green-v2-local-20261103](https://huggingface.co/zjumty/real-smolvla-red-green-v2-local-20261103) | 最终20,000步推理权重和训练配置、处理器 | 7 / 1,800,285,610 | 21 / 1,800,357,653 |
| [zjumty/real-cube-bowl-smolvla-v2-train-20261103](https://huggingface.co/datasets/zjumty/real-cube-bowl-smolvla-v2-train-20261103) | train，262集 / 75,880帧，绿125 / 红137 | 16 / 1,513,691,452 | 24 / 1,514,180,622 |
| [zjumty/real-cube-bowl-smolvla-v2-validation-20261103](https://huggingface.co/datasets/zjumty/real-cube-bowl-smolvla-v2-validation-20261103) | validation，76集 / 23,145帧，绿44 / 红32 | 9 / 476,513,109 | 17 / 476,861,621 |

训练集与验证集保留各自完整的 LeRobot v3.0 `meta/data/videos` 根目录，适用于本项目 LeRobot0.6.1，不合并、不再次随机拆分。数据包含20fps、640×480 wrist/side双视角，state/action各6维。验证集描述性统计仅供审计，推理和验证均使用 train 拟合的模型处理器。原始文件及权重未修改，暂存使用独立副本。

模型原件：`/data/work/so101-policies/real-smolvla-red-green-v2-local-20261103/checkpoints/020000/pretrained_model`。两套数据原件：`/data/work/so101-datasets/real-cube-bowl-smolvla-v2-{train,validation}-20261103`。

权重 SHA256：`16d9116230bf5bb8eba4f6a9c9bbf635df9f3d93869b04da3f66252ce3e44b85`；train stats：`133e284d39c6eb05a96482961b06ec48a6c56fa7de4c26bd71869e2f74c45184`；active corrected split：`a695ba8e056e0f7aa0b75ea5580f6181ba3ea83c71002d717edce0692da499a4`。

active溯源为 `split-b02-corrected.json` / `episode-map-b02-corrected.json` / `dataset-approved-b02-corrected.json`：B02-green ep6/G19被排除，补录ep0归逻辑B02 group，保留其独立physical source/origin。无跨split group/origin/numeric trajectory泄漏。暂存包含明确selection、episode map、批准回执与每个原文件size/SHA256。

训练最终回执 `smolvla-v2-local-training-20261103/training/final-model-verified.json` 已证明step20000、batch32、全F32、CPU strict reload、train统计一致；5000/10000/15000/20000各验证完整23,145帧。训练数据验收含视频完整解码与全部338集首尾真实loader。暂存不包含optimizer、缓存、凭证、无关文件或真实评测录像；许可证未指定，不新增许可声明。

性能边界：历史C2/C3目标色入碗11/12（绿5/6，红6/6）；独立新组合16条为9/16（绿2/8，红7/8）。结果是保存视频离线视觉复核，非新增人工验收；新条件各仅两次，不能外推可靠泛化。参见[比较报告](smolvla-v2-v3-real-comparison-20261104.md)和[新位置报告](smolvla-v2-generalization16-results-20261104.md)。

## 发布记录与固定版本下载

发布工作目录：`/data/work/so101-evidence/real-robot/hf-smolvla-v2-publish-20261104`。其 `upload-plan.json` 含完整暂存清单，`staging/` 含全部文件；`upload.py` 先以 `hf auth whoami --format json` 校验账号，再依次执行 `hf repos create --public --exist-ok` 与 `hf upload`。如账号不是zjumty则停止。只使用本机已存认证，不能把token发到第三方镜像。

```bash
HF_RELEASE=/data/work/so101-evidence/real-robot/hf-smolvla-v2-publish-20261104
/data/models/huggingface/cli/venv/bin/python "$HF_RELEASE/upload.py"
/data/models/huggingface/cli/venv/bin/python "$HF_RELEASE/verify.py"
```

`verify.py` 重新核原始本地文件，匿名访问官方Hub，核公共/非gated、所有远端文件名和大小、大文件LFS SHA256及匿名HEAD、小文件匿名GET SHA256；仅三仓库全部通过才写 `publication-receipt.json` 的 `status=complete`。远端回执已写入 `publication-receipt.json`，状态为 `complete`；以下下载命令固定到已核验的 commit。大文件使用远端 LFS SHA256 元数据和匿名 HEAD 核验，小文件通过匿名 GET 重新计算 SHA256，未重新下载全部大文件。

```bash
hf download zjumty/real-smolvla-red-green-v2-local-20261103 \
  --revision aba1912416a7c485d1175743dd4bc87a3d2ced3a --local-dir /path/to/v2-original
hf download zjumty/real-cube-bowl-smolvla-v2-train-20261103 --type dataset \
  --revision 7828e63f6c071bc1b21a3cffe7b2f5a1875caf4b --local-dir /path/to/v2-train
hf download zjumty/real-cube-bowl-smolvla-v2-validation-20261103 --type dataset \
  --revision b017db1b52178d29fc3163dc95cb71e5a66782a9 --local-dir /path/to/v2-validation
```

模型配置保留训练机器原路径。下载后的 `prepare_runtime.py` 将固定revision的官方VLM/tokenizer配套文件下载到当地缓存，复制出独立runtime模型并仅修正路径，不改原下载文件或权重：

```bash
/data/work/venvs/so101-smolvla-061/bin/python /path/to/v2-original/prepare_runtime.py \
  /path/to/v2-original /path/to/v2-runtime
CHECK_ONLY=1 ./rollout_smolvla.sh eval-v2-preflight 1 /path/to/v2-runtime
```

本机现有v2无需下载/迁移，可显式传原始checkpoint目录；launcher默认仍是v1。本次发布和校验使用CPU及网络，未连接机械臂或相机、未使用GPU。
