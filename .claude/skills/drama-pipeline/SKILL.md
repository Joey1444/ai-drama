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

```bash
# 1) scp scripts/ 与素材到 Pod
# 2) 抽清单
python scripts/extract_shots.py "docs/方案/<系列>/09-<EP>视频提示词.md"   # -> shots.json
# 3) 逐镜：产 payload -> 转 API -> 打补丁 -> 提交
python scripts/make_payload.py --shots _validate/batch/shots.json \
       --workflow-dir _validate/batch --shot M01 --out /tmp/wf_M01.json
python3 comfy_ui2api.py /tmp/wf_M01.json -o /tmp/api_M01.json
python3 comfy_patch.py   /tmp/api_M01.json /tmp/payload_M01.json
curl -b ck.txt -X POST -H "Content-Type: application/json" \
     --data-binary @/tmp/payload_M01.json http://127.0.0.1:8188/prompt
# 4) 队列空后拉回（本机，需先 export COMFYUI_PASSWORD=...）
python scripts/collect_shots.py --host <ip> --port <port> --out _validate/shots_real
```

**先读** `docs/调研/H3-RunPod-实操手册.md`（8 个坑 + 参数映射）。

## 关键坑速查

| 坑 | 指向 |
|---|---|
| 标称时长≠实际（17 帧网格，4s→4.459s） | `.claude/rules/事实基线.md` |
| 字幕 `original_size` 不生效、MarginV≥300 静默不画 | `.claude/rules/code.md` Windows 段 |
| xfade 提前时间轴 | `CLAUDE.md` 易忘三件事 |
| ComfyUI 进度条 `\r` 误判卡死 | 实操手册 §六 |
| 送发前必跑 `--dry-run` | 本 skill |

## 与 `short-drama-*` 的关系

`short-drama-*` 管**内容怎么写**（剧本/分镜/提示词应该长什么样）；本 skill 管**怎么跑出来**（技术栈参数、云操作、脚本调用、成片）。写提示词内容 → `short-drama-video-prompts`；变成成片 → 本 skill。

## 一致性（升级路线，**非当前主线**）

跨镜一致性问题（T2VA 无跨镜记忆）的解法（关键帧链路）见 `.claude/skills/short-drama-consistency/SKILL.md`——
⚠️ **它属"后续升级"，当前前置条件未满足**（Pod 缺 Ref2VA 权重、未装 Qwen-Image），详见该 skill 顶部的"前置条件"。
当前唯一零成本可用的是一致性**自锚定**（H3 出正脸镜 → `pick_frame.py` 抽帧 → 绑 Ref2VA identity）。
