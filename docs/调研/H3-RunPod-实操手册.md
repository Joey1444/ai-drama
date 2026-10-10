# H3 on RunPod · 实操手册

> 2026-10-09 首次跑通 ｜ **这份是踩出来的，不是查出来的**——每一步都有真实报错对应。

---

## 一、总流程（六步）

```
1. 建卷/选机器 → 2. 用模板起 Pod（强制 CUDA 13.0）→ 3. 等 provision（约 15–25 分钟）
4. SSH 进去 → 5. 设 ComfyUI 密码 → 6. 转 UI→API 格式 → 提交 → 取片
```

---

## 二、每一步的坑（全部实测踩过）

### 1. 模板怎么用 API 部署

**`templateId` 可以填 hub 模板 ID**——虽然 `GET /v1/templates/<id>` 返回 404，但 `POST /v1/pods` 认。

```json
{"name":"h3","computeType":"GPU","cloudType":"COMMUNITY","templateId":"a1nkufhzxq",
 "gpuTypeIds":["NVIDIA GeForce RTX 5090","NVIDIA RTX 6000 Ada Generation","NVIDIA L40S"],
 "gpuTypePriority":"availability","gpuCount":1,
 "allowedCudaVersions":["13.0"]}
```

- 模板自带 **110GB 卷**，不用另外建网络卷（网络卷**停机也计费**，能不用就不用）
- 计费：Community 云 5090 **$0.69/h**；Secure 云 4090 $0.89/h

### 2. ⚠️ 必须强制 CUDA 13.0（第一个大坑）

**症状**：ComfyUI 起不来，日志报
```
CUDA initialization: The NVIDIA driver on your system is too old (found version 12090)
PyTorch: 2.12.1+cu130 → CUDA available: False
❌ ERROR: PyTorch CUDA driver mismatch or unavailable, ComfyUI not started
```
**原因**：镜像装的是 **cu130** 的 PyTorch，宿主驱动只有 12.9。
**解法**：建 Pod 时加 `"allowedCudaVersions":["13.0"]`（或控制台选 CUDA 13.0 过滤）。

### 3. ⚠️ SSH 密钥必须在**创建时**注入（第二个大坑）

- RunPod **只在创建 Pod 时**注入 SSH 公钥，**重启不算**
- 验证方法：查 `PUBLIC_KEY` 环境变量长度，**0 = 没注入**
- 所以要**先配密钥再建 Pod**；密钥已配好后重建即可

### 4. ComfyUI 有认证（ComfyUI-Login）

**症状**：任何接口都返回 `{"error": "Authentication required."}`，**连容器内 localhost 也一样**。
**原因**：custom node `ComfyUI-Login`，密码存在 `<ComfyUI>/login/PASSWORD`（bcrypt 哈希 + 用户名两行）。**文件不存在就一律拒绝**。
**解法（不用重建 Pod）**：
```bash
curl -s -c ck.txt http://127.0.0.1:8188/login -o /dev/null
curl -s -b ck.txt -c ck.txt -X POST \
  -d "username=root&password=<你的密码>" http://127.0.0.1:8188/login
# 密码文件不存在时，这一步就是「首次设置」——它自己写哈希
```
之后所有请求带 `-b ck.txt` 即可。

### 5. ⚠️ UI 格式 → API 格式：三个必须处理的坑（第三个大坑）

ComfyUI 的 `/prompt` **只吃 API 格式**；模板内置的 18 个工作流全是 **UI 格式**。转换要处理：

| # | 坑 | 现象 | 解法 |
|---|---|---|---|
| a | **widgets_values 里，被转成连线的控件值仍在原位** | 整体错位一格（如 `denoise` 拿到 `steps` 的值） | 控件名列表**不要过滤已连线者**，全量按序映射 |
| b | **`control_after_generate` 会多占一个值槽** | `PrimitiveInt.value` 拿到 `'fixed'` | 该控件后**跳过一槽** |
| c | **部分自定义控件在头部塞描述对象** | LoraManager 的 `text` 拿到 `{...}` | 该节点**从尾部对齐** |

另：`scheduler` 这类新版 spec 的类型是**字符串 `"COMBO"`** 而非数组——判定"是不是控件"要两者都认。
`GetNode`/`SetNode` 是前端虚拟节点，要**解析成上游真实来源**。

### 6. ⚠️ 模板下的模型 ≠ 工作流引用的模型（第四个坑）

**症状**：
```
clip_name 'qwen3vl_32b_h3_ultra_uncensored_heretic_int8_convrot.safetensors'
not in ['qwen3vl_32b_heretic_minimax_h3_nvfp4.safetensors']
```
**原因**：模板按机器架构下模型（Blackwell 下 NVFP4 版），但工作流 JSON 里写的是另一版文件名。
**解法**：按**目录类别**自动替换——`text_encoders/` → `clip_name`，`diffusion_models/` → `model_name`，`vae/` → `vae_name`。

### 7. LoraManager 空 `loras` 会让校验失败

`loras: []` 被 ComfyUI 当成"连线"解析 → `bad_linked_input`。
**解法**：该节点在 `loras` 为空时**等于直通**，直接**摘掉节点**，下游改接它的上游。

### 8. FL2V 必须有输入图；T2V 不需要

`fl2v-pod.json` 是"首尾帧生视频"，没图会算出 **宽高 = 0** → `ZeroDivisionError: float division by zero`（在 `comfy/ldm/minimax/model.py: _axis_from_sqrt_area`）。
**验证链路请用 `t2v-pod.json`。**

---

## 三、可复用脚本（已固化到 `scripts/`）

| 脚本 | 作用 |
|---|---|
| `comfy_ui2api.py` | UI 格式工作流 → API 格式（已处理上面 5 里的三个坑） |
| `comfy_patch.py` | 按目录替换模型文件名 + 强制 9:16 + 摘除空 LoraManager |

用法（在 Pod 内）：
```bash
curl -s ... /object_info -o /tmp/oi.json      # 先取节点定义
python3 comfy_ui2api.py <workflow.json> -o /tmp/api.json
python3 comfy_patch.py  /tmp/api.json  /tmp/payload.json
curl -s -b ck.txt -X POST -H "Content-Type: application/json" \
     --data-binary @/tmp/payload.json http://127.0.0.1:8188/prompt
```

---

## 四、实时看结果

| 地方 | 看什么 |
|---|---|
| **ComfyUI 网页**（`:8188`，账号 root / 见 Pod 内 `login/PASSWORD` 对应的密码） | **实时 latents 预览 + 队列**（模板开了 `--preview-method latent2rgb`） |
| Code-server（`:9000`） | `/workspace/ComfyUI/output/` 文件 |
| RunPod 控制台 → Logs | step 进度、报错 |
| SSH | `tail /workspace/ComfyUI/user/comfyui.log`、`nvidia-smi` |

---

## 五、成本实测

| 项 | 值 |
|---|---|
| Community 云 5090 | **$0.69/h** |
| 首次 provision | **约 15–25 分钟**（下 ~70–100GB 模型） |
| 盘占用 | ~69GB / 110GB |
| 一次 5 秒竖屏生成 | 见 `项目状态.md` 的实测记录 |

**止损要点**：不跑就 `Stop`；**网络卷停机仍计费**，所以能不用就不用。

---

## 六、实测参数与两个新坑（2026-10-09 晚，实测）

### 1. ⚠️ 进度条走 `\r`，`tail` 看不到——**别据此判断"卡死"**

**实测**：一条 **20 秒**任务全程约 **30 分钟**（`Prompt executed in 00:14:08`，其中采样 20 步占 9:30），**期间 `output` 一直为空**——但它在**正常推进**。

> ❌ **踩过的误判**：看到「日志不增长 + output 为空 + 跑了 25 分钟」就断定可疑、准备杀任务。
> **这是错的。** 差点杀掉一个正在正常跑的任务。

**确认在不在推进**（二选一）：
```bash
# a) 看 ComfyUI 网页的进度条（最直观）
# b) 日志里把 \r 转成 \n 再 grep
tail -c 3000 /workspace/ComfyUI/user/comfyui.log | tr '\r' '\n' | grep -E '[0-9]+/[0-9]+ \['
```

### 2. `t2v-pod.json` 参数映射表（实测）

| 想改什么 | 改哪个节点 | 说明 |
|---|---|---|
| **时长（秒）** | **`134 PrimitiveFloat`** | 经 `133 ComfyMathExpression` 换算成帧：`max(5, round(秒×24)) + (5 − (…)％17)％17`。**填 20 → 481 帧 → 成片 `20.042s`** ✅ 公式吻合 |
| **画面尺寸** | **`172 ResolutionSelector`** | ⚠️ `132.width/height` 的 widgets 里那对值（1344×768）是**废值**，**被 172 连线接管**——改尺寸必须改 **172**，改 132 没用 |
| **提示词** | `132 MiniMaxH3ImageToVideo` 第 1 个 widget | 收 H3 官方**三段/六段结构正文** |
| **采样步数** | 不在这里 | 进度条的 `x/20` 是采样步数，**与时长无关**。20 步 = **9 分 30 秒** |

> **易混淆点**：`PrimitiveFloat=20` 和进度条 `x/20` 里的两个「20」**是两回事**——前者是秒数、后者是步数。

### 3. 产物规格实测

`auto_00001_.mp4`：**`736×1280`**（`0.9 MP` / 9:16 竖屏）、**`481 帧`**、**`20.042s`**、**27 MB**，原生带音轨。

### 4. ⚠️ **Ref2VA 权重不在 Pod 上**（会撞上的墙）

`models/diffusion_models/` 里**只有**：

```
minimax_h3_fl2va_pruned_int8_convrot.safetensors
```

- **FL2VA 覆盖 文生 / 首帧 / 尾帧 / 首尾帧** → **够跑 T2VA 定妆镜**
- ❌ **没有 `ref2va`** → **参考式（Ref2VA）跑不了**

> 影响：`09-E1视频提示词.md` 里 **M02 / M08 是 full-reference（要「身份」参考图）**，
> **依赖 Ref2VA 权重**。要跑这两镜，**得先补下 Ref2VA**。

其余实际文件名（供 `comfy_patch.py` 对照）：

| 目录 | 实际文件 |
|---|---|
| `diffusion_models/` | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| `text_encoders/` | `qwen3vl_32b_heretic_minimax_h3_nvfp4.safetensors` |
| `vae/` | `minimax_h3_video_vae_fp16.safetensors` · `minimax_h3_audio_vae_fp32.safetensors` · `minimax_h3_video_vae_int8_convrot.safetensors` |
| `vae_approx/` | `taeh3.safetensors` |

### 5. 取当前 Pod 的 SSH 端口（重建/重启后会变）

```bash
KEY=$(grep -m1 RUNPOD_API_KEY ~/.claude/token.txt | cut -d= -f2-)
curl -s "https://api.runpod.io/graphql?api_key=$KEY" -H 'Content-Type: application/json' \
  -d '{"query":"query { pod(input:{podId:\"<podId>\"}) { desiredStatus costPerHr runtime { uptimeInSeconds ports { ip isIpPublic privatePort publicPort type } } } }"}'
```

> ⚠️ `desiredStatus` 与 `costPerHr` 字段名**大小写敏感**；`gpuDisplayName` **不在 `PodRuntime` 上**，会报 `GRAPHQL_VALIDATION_FAILED`。
> SSH 走 `type:tcp` 且 `privatePort:22` 的那个 `publicPort`。

```bash
# SSH 私钥在本机（公钥已注册在 RunPod 账号）；端口用上一步查到的 publicPort
ssh -i ~/.ssh/runpod_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=25 -p <publicPort> root@<ip>
```

| 凭据 | 在哪 | 能不能写进项目文件 |
|---|---|---|
| **RunPod API Key** | 本机 `~/.claude/token.txt` 的 `RUNPOD_API_KEY` | ❌ **绝不能**——只引用路径 |
| **SSH 私钥** | 本机 `~/.ssh/runpod_ed25519` | ❌ 只引用路径 |
| **ComfyUI 密码** | **Pod 内**存着，**机器一删就没了**，属临时凭据 | ❌ 不写进项目文件 |

---

## 七、模板元数据（从 RunPod API 的 Pod 响应里读出来的，2026-10-09）

**`GET` 一个 Pod 会把它的全部环境变量吐出来**——里面有模板的模型清单与工作流来源，很有用：

```bash
curl -s -X POST -H "Authorization: Bearer $KEY" https://rest.runpod.io/v1/pods/<podId>/stop
# 返回体里带 env / imageName / volumeInGb / VRAM_THRESHOLD 等
```

### 1. ⚠️ **Ref2VA 缺失是模板层面的，不是"下漏了"**

模板环境变量里**只有 `HF_MODEL_*_DIFFUSION_MODELS*` 指向 `Comfy-Org/MiniMax-H3` 的 `fl2va`**（HVRAM / LVRAM 两档），**没有任何 ref2va 条目**。

> 所以：**这个模板开箱就只有 FL2VA**，参考式（Ref2VA）要自己补下，不是"下载没跑完"。

### 2. `VRAM_THRESHOLD = 40` —— 显存决定用哪档模型

模板按 `VRAM_THRESHOLD`（40GB）二选一：

| 显存 | 用哪个 |
|---|---|
| **≥ 40GB** | `diffusion_models/minimax_h3_fl2va_int8_convrot.safetensors`（HVRAM 档） |
| **< 40GB**（5090 的 32GB 属这档） | `diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors`（LVRAM 剪枝档） |

> 所以 5090 上跑的是 **pruned 版**——这是模板的自动选择，换了更高显存的卡会自动换成非剪枝版。

### 3. 💡 模板还自带 **turbo / 8-step LoRA**（以后提速可评估）

环境变量里列了这些 LoRA：

```
minimax_h3_turbo_v4_step600_ema.safetensors
minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_bf16.safetensors
minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors
```

**我们现在跑的是 20 步采样（4 秒任务 86 秒）。换成 8 步 turbo LoRA，理论上能砍掉六成采样时间。**
⚠️ **未验证**——代价是画质与一致性可能下降，要做 A/B 才能定。**登记为候选提速手段，不擅自动**。

### 4. 工作流可以直接从这里取

```
https://provisioning.rozenlaan.site/minimax/<name>.json
```

例如 `t2v-pod.json`、`fl2v-pod.json`、`turbo-t2v-pod.json`、`Hyperflow-t2v-pod.json`。
**不必非从 Pod 里把工作流拉出来**——本地就能拿到，做转换时更方便。

> ⚠️ 实测：直接 `curl` 这个域名会 **403 Forbidden**（可能要 Referer 或限 IP）。**取不到就还从 Pod 里拿。**

---

## 八、批量出片流程（E1 的 13 镜）

### 前置：把所有镜的提示词抽成机器可读清单

```bash
python scripts/extract_shots.py "docs/方案/符/09-E1视频提示词.md"
# -> _validate/batch/shots.json   每镜 { id, seconds, mode, reference, prompt }
```

实测输出：**13 镜 / 合计 60s / H3 区间全部合法**；`t2va` 11 镜、`ref2va` 2 镜。

### 每一镜怎么出（这条路径**已在真机验证过**）

| 步 | 做什么 |
|---|---|
| 1 | 从 `shots.json` 取该镜的 `prompt` / `seconds` |
| 2 | 改工作流：`132.prompt` ← 提示词；`134.PrimitiveFloat` ← 秒数；`172.ResolutionSelector` ← `9:16` + `1.05 MP` |
| 3 | `comfy_ui2api.py <workflow>` → `comfy_patch.py` → `POST /prompt` |
| 4 | 等 → 从 `/workspace/ComfyUI/output/auto_*.mp4` 取片 → 改名成 `M<xx>.mp4` |

> **单镜实测耗时**：**4 秒镜 2 分 48 秒**（采样 86 秒 + 模型加载与解码）；20 秒镜 14 分 08 秒。
> 13 镜约 **40–50 分钟 GPU**。

### ⚠️ 参考式（M02 / M08）的解法（**已查清，只剩开机执行**）

之前写"要自己搭工作流"是**错的**——官方有现成的。**`Comfy-Org/workflow_templates` 仓库里的 `templates/video_minimax_h3_r2v.json`**（已下载到 `_validate/batch/`）就是参考式本地工作流，不用自己造。

| # | 要补什么 | 具体 | 状态 |
|---|---|---|---|
| 1 | **权重** | `Comfy-Org/MiniMax-H3` → **`diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors`（19.53 GB）** | 与已有 FL2VA **同档**；Pod 余 42G **装得下**。**开机后下** |
| 2 | **工作流** | 官方 `video_minimax_h3_r2v.json` | ✅ **已下载本地**，不用自己搭 |

**官方 r2v 工作流的关键节点**（实测读出来的）：

| 节点 | 作用 | 值 |
|---|---|---|
| `127 UNETLoader` | 加载 Ref2VA 权重 | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` |
| `136 MiniMaxH3ReferenceToVideo` | **核心**：参考式生成 | 输入含 **`ref_images.ref_image_0` / `ref_image_1`** 两个参考图槽位 + `clip`/`vae`/`audio_vae`/`prompt`/`width`/`height`/`length` |
| `137` / `139 LoadImage` | 两张参考图 | 对应 `ref_image_0` / `ref_image_1` |
| `138 PrimitiveStringMultiline` | 提示词 | 收六段 full-reference 正文，用 `<Picture 1>`/`<Picture 2>` 标签引用参考图 |
| `132 PrimitiveFloat` | 时长（秒） | 填镜长 |

**M02 / M08 的映射**：我们的六段提示词（`09-E1视频提示词.md` 里 `subject_definitions` 写了 `<Subject 1> is the ... in <Picture 1>`）→ 塞进 `138`；陈默定妆图 → `ref_image_0`。

**⚠️ 三个开机后才能验证的点**：
1. **Pod 上有没有 `MiniMaxH3ReferenceToVideo` 节点**——模板 `a1nkufhzxq` 的 t2v 工作流用的是 `MiniMaxH3ImageToVideo`，**不保证有 ReferenceToVideo**。开机后先 `curl /object_info` 查。
2. **CLIP 文件名不同**——官方用 `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`，Pod 上是 `qwen3vl_32b_heretic_minimax_h3_nvfp4.safetensors`。`comfy_patch.py` 会按目录自动替换，**但换了 CLIP 对参考式的影响未验证**。
3. **官方 r2v 挂了两个参考图**（`ref_images.ref_image_0` + `ref_image_1`，对应 `137`/`139` 两个 `LoadImage`），**而我们每镜只有一张定妆图**。三条备选：① 两个槽位喂同一张图 ② 摘掉 `139` 与 `ref_image_1` 的连线 ③ 查 `/object_info` 看 `ref_image_1` 是否可选。**开机后实测哪个可行**。

### 逐镜产 payload 的工具（已写好，本地可跑）

```bash
python scripts/make_payload.py --shot M02 --out _validate/batch/wf_M02.json
# t2va  -> 用 t2v-pod.json（模板自带；本地没有就开机后从 Pod 取）
# ref2va-> 用 video_minimax_h3_r2v.json（已在 _validate/batch/）
```
按 `mode` 自动选工作流与节点映射（**两套节点号不一样，脚本里已分别写死**）：

| mode | 提示词 | 时长 | 尺寸 | 参考图 |
|---|---|---|---|---|
| `t2va` | `132[0]` | `134[0]` | `172[0]` | — |
| `ref2va` | `138[0]` | `132[0]` | `115[0]` | `137[0]` |

> ⚠️ **本机 Git Bash 的坑**：给 Python 传 `--out /tmp/xxx` 会被 MSYS **自动改写成 `C:/Users/.../Temp/xxx`**。传相对路径或显式 Windows 路径。

### 停机

```bash
curl -s -X POST -H "Authorization: Bearer $KEY" https://rest.runpod.io/v1/pods/<podId>/stop
```
实测：返回体里 `desiredStatus: "EXITED"` 即成功；**110GB 卷保留**，重开机不用重下模型。

### 删除（terminate）—— **与停机完全不同，别搞混**

停机保卷；**删除会连卷一起清掉**，重开必须重下 ~70GB 模型（15–25 分钟）。

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE \
  -H "Authorization: Bearer $KEY" https://rest.runpod.io/v1/pods/<podId>    # 204 = 成功
```

⚠️ **两件必须知道的事**：

1. **SSH 公钥只在创建 Pod 时注入** → 重开要**新建** Pod 并重新注入，不能"重启旧的"
2. 重建照本手册「部署」走：模板 `a1nkufhzxq` + **`allowedCudaVersions:["13.0"]`**（否则 CUDA 起不来）

**删完自查**（费用归零 = 两项都为 0）：

```bash
curl -s "https://api.runpod.io/graphql?api_key=$KEY" -H "Content-Type: application/json" \
  -d '{"query":"{ myself { pods { id } networkVolumes { id } } }"}'
```

> **实测记录（2026-10-10）**：删前先核对本地产物齐全 —— `_validate/out/final.mp4`（36M）、
> `_validate/shots_v3/` 与 `shots_real/`（各 13 镜）、`docs/生成留证/符/EP001/`（5 文件）。
> 确认都在本地后才 terminate；删后 pods 与 networkVolumes 均为 0。

