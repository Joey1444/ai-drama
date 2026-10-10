#!/usr/bin/env python3
"""PostToolUse 钩子：写入/编辑剧本后自动跑校验

命中条件：工具是 Write / Edit / MultiEdit，且目标文件以「剧本.md」结尾。
行为：调用 scripts/check_script.py，把结果回喂给模型。
失败安全：任何异常都 exit 0，绝不阻断会话。
"""
import json
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
# Windows 上 stdin 默认按 GBK 读，不强制 UTF-8 会让中文路径的 JSON 解析失败
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    fp = (data.get("tool_input") or {}).get("file_path", "")
    if not fp or not fp.endswith("剧本.md"):
        sys.exit(0)

    # .claude/hooks/xxx.py -> 项目根
    root = Path(__file__).resolve().parents[2]
    checker = root / "scripts" / "check_script.py"
    if not checker.exists():
        sys.exit(0)

    try:
        r = subprocess.run(
            [sys.executable, str(checker), fp],
            capture_output=True, text=True, encoding="utf-8", timeout=60)
        body = ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as e:
        body = f"（校验脚本执行失败：{e}）"

    msg = "【剧本校验 · 项目硬门】\n" + body + \
          "\n\n提醒：剧本未过四维评分（≥14 且无单项 ≤2）不许送生成。"
    print(json.dumps(
        {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}},
        ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
