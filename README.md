# AI 短剧制作框架

> 用 AI 从剧本跑到成片的**可复现流水线**：剧本 → 分镜 → 提示词 → 云生成 → 自动剪辑 → 成片。
> 默认技术栈 **MiniMax H3（本地/RunPod）+ 本机 ffmpeg**，零 GPU 也能跑（生成上云，剪辑在本机 CPU）。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 这是什么

一套**面向个人创作者的 AI 短剧生产框架**，包含三层：

| 层 | 内容 | 位置 |
|---|---|---|
| **知识** | 爆款结构模板（10 题材）· 模型方言速查 · 平台分发策略 · 成本合规 · 避坑指南 | `docs/知识库/` |
| **技能** | 创作链路（`short-drama-*`）+ 制作流水线（`drama-pipeline`）+ 一致性（`short-drama-consistency`） | `.claude/skills/` |
| **工具** | 流水线 driver、门禁校验、成本计算、漂移检测、剪辑脚本 | `scripts/` |

## 快速开始

```bash
# 1) 装依赖
pip install -r requirements.txt
# 系统依赖（非 pip）：ffmpeg / ffprobe（Windows: winget install Gyan.FFmpeg）

# 2) 零成本校验一集（不花任何钱）
python scripts/run_pipeline.py --series <系列> --episode <EP> --dry-run

# 3) 全流程（会在花钱前停下要你确认）
python scripts/run_pipeline.py --series <系列> --episode <EP>
```

`--dry-run` 会：发现本集文件 → 跑免费门禁（剧本/提示词/结构）→ 校验输入齐备 → 打印送发命令序列。**一分钱不花**。

## 目录结构

```
.
├── CLAUDE.md             项目总则（索引）
├── 验收标准.md           三层验收（项目级/阶段门/单集评分）
├── 项目状态.md           团队记忆
├── docs/
│   ├── 知识库/           ★ 结构模板/模型方言/平台策略/成本合规/避坑
│   ├── 方案/             执行手册 + 系列方案（如《符》）
│   ├── 调研/             分环调研 + H3 RunPod 实操手册
│   └── 政策/             平台扶持政策（保质期 1 个月）
├── .claude/
│   ├── rules/            项目规则（制作红线/事实基线/H3提示词/合规…）
│   ├── agents/           角色（制片人/编剧/观众代言人…）
│   └── skills/           技能
├── scripts/              ★ 流水线工具
│   ├── run_pipeline.py       流水线 driver
│   ├── check_gate_G*.py      阶段门校验
│   ├── cost_calculator.py    成本预估
│   ├── check_drift.py        跨镜漂移检测
│   ├── make_payload.py       送发工作流（Pod 内）
│   ├── collect_shots.py      素材拉回
│   ├── make_edit.py/make_srt.py/build.py  剪辑链
│   └── ...
└── templates/            agent 输出模板
```

## 核心设计

**三层制作约束**（`docs/知识库/…` + `.claude/rules/制作红线.md`）——把「模型限制 / 本地部署约束 / 项目默认」分开，不把保守默认当成模型天花板。

**花钱卡点前置**——任何产生费用的阶段之前，先要用户显式确认；`--dry-run` 保证零成本跑通流程。

**委托优先，不重造轮子**——门禁脚本调用已被验证的解析器（`check_script.py` / `check_prompts.py`），不各写一套对不上的正则。

**证据分级**——知识库里每条数字标来源等级（已确认 / 二手转述 / 无来源·待重查），策略类信息标注保质期。

## 制作一集的最小闭环

```
剧本(06-E<EP>剧本-定稿.md)
  → 分镜(08-E<EP>分镜.md)
  → 视频提示词(09-E<EP>视频提示词.md)
  → [run_pipeline.py --dry-run 校验]
  → 送 Pod 生成(逐镜 T2VA / Ref2VA)
  → 拉回 → 自动剪辑(edit.json + 字幕 + 成片)
  → G4 成片门 → 收尾留证
```

## 状态与路线

- **当前**：跑通最小闭环，系列《符》E1 已出片 v2（T2VA 链路）。
- **已知约束**：跨镜一致性是 T2VA 的固有短板；升级方案（关键帧链路）见 `docs/方案/升级路线.md`，**属后续升级，前置条件未满足前不执行**。
- **成本基线**：RunPod 单集现金 ≈ ¥5–8；云 API 口径存疑（见知识库成本卡）。

## 合规提示

- AI 生成内容**必须显式标识**；微短剧需备案。
- **不得**将未授权小说原文喂给模型（已有判赔案例）。
- 详见 `docs/知识库/成本合规/合规核查清单.md`。

## 许可

[MIT](LICENSE)。第三方组件（如 MiniMax H3 权重、各技能）遵循各自许可；
使用 MiniMax H3 须遵守其 Community License（商用需显著标注模型名）。
