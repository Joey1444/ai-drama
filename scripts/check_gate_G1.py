#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G1 设定门检查

设计原则：**不做会误判的关键词扫描。**
- 结构完整性（世界观简报必备段落）→ 可机器校验，本脚本负责
- 可拍性（红线）/ 好看度 → **交 producer + audience-proxy**，本脚本只提示

为什么不做关键词红线扫描：实测会把「禁大场面」「避免打斗」这类**否定句**
误判为「含大场面/打斗」。判断类结论必须由 agent/人给出，不机器猜。

用法：python scripts/check_gate_G1.py <世界观简报路径>
"""
import io
import sys
import json
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 世界观必备「概念」及其常见写法（同义组，避免被标题措辞差异误杀）
REQUIRED_CONCEPTS = {
    "一句话设定": ["一句话设定", "一句话", "one-liner"],
    "世界观载体": ["三个载体", "世界观", "社会变化", "设定"],
    "冲突引擎": ["冲突引擎", "戏剧引擎", "冲突从哪"],
    "对立面": ["对立面", "反派", "对手", "有脸的反派"],
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"❌ 文件不存在: {path}")
        sys.exit(1)

    content = path.read_text(encoding="utf-8")
    issues = []

    # 每个概念只要命中其任一写法即算满足
    missing = [name for name, variants in REQUIRED_CONCEPTS.items()
               if not any(v in content for v in variants)]
    for s in missing:
        issues.append(f"❌ 缺失必备概念：{s}（接受写法：{' / '.join(REQUIRED_CONCEPTS[s])}）")

    structurally_ok = len(missing) == 0

    result = {
        "gate": "G1",
        "name": "设定门",
        "passed": structurally_ok,          # 只判结构；可拍性/好看度由 agent 判
        "structural_check": {
            "required_concepts": list(REQUIRED_CONCEPTS.keys()),
            "missing": missing,
        },
        "delegated_checks": {
            "可拍性": "producer（红线复核）",
            "好看度": "audience-proxy（会不会看下去）",
            "_note": "本脚本不做关键词红线扫描——会把『禁大场面』这类否定句误判为违规",
        },
        "issues": issues,
        "checked_file": str(path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if structurally_ok:
        print("\n✅ G1 结构完整；可拍性/好看度仍需 producer + audience-proxy 判定")
        sys.exit(0)
    else:
        print(f"\n❌ G1 结构不完整：缺 {len(missing)} 个必备概念")
        sys.exit(1)


if __name__ == "__main__":
    main()