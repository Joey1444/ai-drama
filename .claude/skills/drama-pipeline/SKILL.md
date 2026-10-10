---
name: drama-pipeline
description: 短剧制作流水线——把一集从「分镜」做成「成片」的完整流程。用 scripts/run_pipeline.py 线性驱动，串联免费门禁 → 花钱卡点 → 送发 → 拉回 → 剪辑 → 成片门 → 收尾。用户说「出片」「生成这一集」「从分镜做到成片」「继续做下一集」时使用。默认技术栈 MiniMax H3 + RunPod + 本机 ffmpeg。
license: MIT
---

# 短剧制作流水线（分镜 → 成片）

**入口是一条命令**，不是一堆手工步骤：

```bash
# 零成本校验（输入齐备？免费门禁过？）
python scripts/run_pipeline.py --series <系列> --episode <EP> --dry-run

# 全流程（会在花钱前停下要你确认）
python scripts/run_pipeline.py --series <系列> --episode <EP>
```

> **设计原则（2026-10-10 重写）**：只编排**已验证**的脚本，不重造解析/生成逻辑。
> 早期版本自造了一套声明式 YAML DSL 与批量入口，实测**跑不通**（`{ep:02d}` 对 `"E1"` 崩、shots.json 格式与下游冲突），已删除。

## 流程与门

| 阶段 | 做什么 | 工具 | 花钱 |
|---|---|---|---|
| 0 | 剧本合法性 | `scripts/check_script.py` | 否 |
| 1 | 提示词合规 + 台词逐字 | `scripts/check_prompts.py` | 否 |
| 2 | G1 结构门（提示）/ G2 机器项 | `scripts/check_gate_G1.py` / `_G2.py` | 否 |
| ⛔ | **SPEND 卡点：用户显式确认** | —— | —— |
| 3 | 送 Pod 生成 | RunPod + 4 个脚本（见下） | **是** |
| 4 | 拉回素材 | `scripts/collect_shots.py` | 否 |
| 5 | 剪辑成片 | `scripts/pipeline_edit.py` | 否 |
| 6 | G4 成片门 | `scripts/check_gate_G4.py` | 否 |
| 7 | 收尾留证 | `scripts/finalize_episode.py` | 否 |

**⚠️ 花钱卡点前置于生成之前**——不允许"预览即确认"（`工作流与门.md` 硬规则）。

## 阶段 3：Pod 内生成（已验证序列）

`run_pipeline.py` 只**打印**这段命令序列（不在本机重造实现——Pod 侧脚本必须**在 Pod 内**跑）：

## 阶段 3：Pod 内生成（**已验证序列 · 2026-10-10**）

> ⚠️ Pod 侧脚本必须**在 Pod 内**跑：`comfy_ui2api.py` 读 `/tmp/oi.json`、`comfy_patch.py` 读
> `/workspace/ComfyUI/models`，这两个路径只在本机（Pod）存在。

```bash
export COMFYUI_PASSWORD=<ComfyUI 登录密码>          # 密钥走环境变量，不进代码

# 0) 开机自检（登录 / 拉 oi.json / 盘点资产 / 确认 turbo 开关）
scp scripts/pod_boot_check.sh  root@<ip>:/workspace/ -P <port>
ssh -p <port> root@<ip> "cd /workspace && bash pod_boot_check.sh"

# 1) 抽清单（**由提示词单一真相生成**，别手工维护）
python scripts/make_shots_json.py "docs/方案/<系列>/09-<EP>视频提示词.md" -o _validate/batch/shots.json
scp _validate/batch/shots.json root@<ip>:/workspace/ -P <port>

# 2) 批量生成（脚本内置 turbo 开关 + 逐镜轮询）
scp scripts/{make_payload.py,comfy_ui2api.py,comfy_patch.py,pod_batch_generate.sh} root@<ip>:/workspace/ -P <port>
ssh -p <port> root@<ip> "cd /workspace && bash pod_batch_generate.sh shots.json"

# 3) 拉回（本机）
python scripts/collect_shots.py --host <ip> --port <port> --out _validate/shots_real
```

### ★ turbo：不打开就白等 3.7 倍

r2v 工作流（`video_minimax_h3_r2v.json`）有 **turbo 总开关 = 节点 `146`（PrimitiveBoolean）**：

| `146` | 效果 | 实测 |
|---|---|---|
| `False`（**默认**） | 裸模型 + **20 步** | 双参考 **13 分钟/镜** |
| **`True`** | `ref2v_turbo_4step` LoRA + **4 步** | 双参考 **3.5 分钟/镜** |

`pod_batch_generate.sh` **已内置**（提交前自动设 `146.value = True`）。想对比画质：`NO_TURBO=1 bash …`。

### 参考式速度（决定怎么排兵）

| 配置 | 采样式 | 用途 |
|---|---|---|
| 双参考（身份+场景） | 39 秒/步 | **出脸镜** |
| 单参考（仅场景） | 9 秒/步 | **环境镜** |

→ **环境镜只挂场景锚**（不需要身份），比双参考快 4 倍。
→ ⚠️ fl2va ↔ ref2va 切换会**重载 20GB 模型**（+1–2 分钟）→ **同模式的镜批在一起跑**。

---

**先读** `docs/调研/H3-RunPod-实操手册.md`（8 个坑 + 参数映射）与 `docs/调研/H3能力地图-2026-10-10.md`（772 个可用节点）。

## 关键坑速查

| 坑 | 指向 |
|---|---|
| 标称时长≠实际（17 帧网格，4s→4.459s） | `.claude/rules/事实基线.md` |
| 字幕 `original_size` 不生效、MarginV≥300 静默不画 | `.claude/rules/code.md` Windows 段 |
| xfade 提前时间轴 | `CLAUDE.md` 易忘三件事 |
| ComfyUI 进度条 `\r` 误判卡死 | 实操手册 §六 |
| `/tmp/oi.json` 重启即丢 | `pod_boot_check.sh` 已自动拉 |
| `podResume` 报"宿主机无空闲 GPU" | 30 秒轮询重试（`_validate/pod_resume_loop.sh`） |
| 送发前必跑 `--dry-run` | 本 skill |

## 与 `short-drama-*` 的关系

`short-drama-*` 管**内容怎么写**（剧本/分镜/提示词应该长什么样）；本 skill 管**怎么跑出来**（技术栈参数、云操作、脚本调用、成片）。写提示词内容 → `short-drama-video-prompts`；变成成片 → 本 skill。

## 一致性（升级路线，**非当前主线**）

跨镜一致性问题（T2VA 无跨镜记忆）的解法（关键帧链路）见 `.claude/skills/short-drama-consistency/SKILL.md`——
⚠️ **它属"后续升级"，当前前置条件未满足**（Pod 缺 Ref2VA 权重、未装 Qwen-Image），详见该 skill 顶部的"前置条件"。
当前唯一零成本可用的是一致性**自锚定**（H3 出正脸镜 → `pick_frame.py` 抽帧 → 绑 Ref2VA identity）。
