#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PreToolUse hook（Write|Edit）：改「提示词/分镜」文件前，强制提醒先读现成经验。

为什么需要（2026-10-10 用户明确要求「变成强制命令」）：
本项目已装 `short-drama-*` 与 `h3-prompt-writing` 技能，里面有大量**别人踩过的坑的结晶**
（generability.md 的四类高风险动作、minimax-h3.md 的说话人绑定与多镜条件…）。
我却**先去自己撞墙**——六根手指、否定式写法、场景锚尺度崩，全是文档里早写过的。
用户原话：「所以你为什么不仔细读其他人的经验并变成自己的经验，每次都自己踩坑才知道」。

此 hook 把「先读」从**自觉**变成**每次必经**：只要动提示词/分镜类文件，就把必读清单拍在脸上。
"""
import io
import json
import re
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")

# 触发目标：提示词/分镜/图片提示词类文件
TARGET_RE = re.compile(r"(视频提示词|分镜|图片提示词|剧本)", re.I)

CHECKLIST = (
    "⛔ 【强制】改提示词/分镜之前，必须先读现成经验——**不许先自己撞墙**。\n"
    "按需读（项目已装的技能库，全是别人试出来的）：\n"
    "· `~/.claude/skills/short-drama-video-prompts/references/generability.md`"
    "（四类高风险动作：精确拦截/不可见内部状态/**否定式动作**/精细编排链；改写原则）\n"
    "· `…/references/minimax-h3.md`（六段结构、说话人绑定、多镜要逐切关键帧、地点图会拉宽景别、参考图上限 9）\n"
    "· `…/references/motion-recipe.md`（单镜运动正文最小配方）\n"
    "· `…/references/performance-action-timing.md`（对白预算：中文约 4.1 字/秒）\n"
    "· `…/references/review-and-fixtures.md`（完成前边界检查清单）\n"
    "· `~/.agents/skills/h3-prompt-writing/references/base-en.txt` / `ref-en.txt`（官方）\n"
    "以及本项目 `.claude/rules/H3提示词.md`、`docs/知识库/避坑指南/提示词常见坑.md`。\n"
    "⚠️ 这一步没有例外，跳过就是重蹈已记录的坑。"
)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if payload.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)
    ti = payload.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if not path or not TARGET_RE.search(str(path)):
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": CHECKLIST,
        }
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
