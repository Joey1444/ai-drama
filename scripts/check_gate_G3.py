#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G3 生产门检查

设计原则：**委托现成校验器，不重造解析器。**
- 提示词合规 + 台词逐字 → scripts/check_prompts.py（已实测 E1 通过）
- 分镜/剧本合法性 → scripts/check_script.py
- 成本预估 → scripts/cost_calculator.py（可选）
- **用户显式确认**（花钱前）→ 交互式，或 --approve 跳过

用法：python scripts/check_gate_G3.py <视频提示词> <剧本> [--storyboard <分镜>] [--approve]
"""
import io
import sys
import json
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


def run(cmd, timeout=180):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           timeout=timeout, cwd=ROOT)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"超时 {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)

    prompts = Path(sys.argv[1])
    script = Path(sys.argv[2])
    storyboard = None
    if "--storyboard" in sys.argv:
        storyboard = Path(sys.argv[sys.argv.index("--storyboard") + 1])
    auto_approve = "--approve" in sys.argv

    for p, name in [(prompts, "视频提示词"), (script, "剧本")]:
        if not p.exists():
            print(f"❌ {name}不存在: {p}")
            sys.exit(1)

    issues = []
    checks = {}

    # ---- 1. 提示词合规 + 台词逐字（委托 check_prompts.py）----
    print("── check_prompts.py ──")
    code, out, err = run([sys.executable, str(ROOT / "scripts" / "check_prompts.py"),
                          str(prompts), str(script)])
    print(out or err)
    checks["prompts"] = {"passed": code == 0, "exit": code}
    if code != 0:
        issues.append("❌ 视频提示词未通过 check_prompts.py")

    # ---- 2. 剧本合法性（委托 check_script.py；它校验的是**剧本**格式，不是分镜）----
    print(f"\n── check_script.py ({script.name}) ──")
    code2, out2, err2 = run([sys.executable, str(ROOT / "scripts" / "check_script.py"), str(script)])
    print(out2 or err2)
    checks["script"] = {"passed": code2 == 0, "exit": code2}
    if code2 != 0:
        issues.append("❌ 剧本未通过 check_script.py")

    # 分镜存在性（不做格式校验——分镜由 check_prompts 的镜数对照间接覆盖）
    if storyboard:
        checks["storyboard"] = {"exists": storyboard.exists(), "path": str(storyboard)}
        if not storyboard.exists():
            issues.append(f"❌ 分镜不存在: {storyboard}")

    # ---- 3. 成本预估（可选，失败不阻断）----
    print("\n── cost_calculator.py ──")
    code3, out3, err3 = run([sys.executable, str(ROOT / "scripts" / "cost_calculator.py"),
                             "--prompts", str(prompts), "--model", "h3",
                             "--platform", "runpod", "--images", "--output", "json"])
    cost = {}
    if code3 == 0:
        try:
            cost = json.loads(out3.strip())
            cash = cost.get("cash_total_cny", 0)
            print(f"  现金成本预估: ¥{cash:.2f}（预算判定依据）")
        except Exception:
            print(f"  ⚠️ 成本解析跳过")
    else:
        print(f"  ⚠️ 成本计算跳过: {err3[:120]}")
    checks["cost"] = cost

    machine_ok = checks["prompts"]["passed"] and checks["script"]["passed"]

    # ---- 4. 用户显式确认 ----
    human_approved = auto_approve
    if not auto_approve:
        print(f"\n{'='*50}")
        print("G3 生产门：送发生成前需你确认（花钱）")
        print(f"{'='*50}")
        print(f"提示词: {prompts.name}")
        print(f"剧本:   {script.name}")
        print(f"机器检查: {'✅ 通过' if machine_ok else '❌ 未通过'}")
        print(f"现金成本预估: ¥{cost.get('cash_total_cny', '?')}")
        ans = input("确认送发生成？(y/N): ").strip().lower()
        human_approved = ans in ("y", "yes", "是")

    passed = machine_ok and human_approved
    if not human_approved:
        issues.append("❌ 用户未确认（花钱前必须显式确认）")

    # 通过则写标记
    if passed:
        (prompts.parent / ".gate_G3_passed").write_text("approved", encoding="utf-8")

    result = {
        "gate": "G3", "name": "生产门", "passed": passed,
        "human_approved": human_approved,
        "checks": checks,
        "estimated_cash_cny": cost.get("cash_total_cny"),
        "issues": issues,
        "checked_files": [str(prompts), str(script)],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if passed:
        print(f"\n✅ G3 生产门通过")
    else:
        print(f"\n❌ G3 生产门未通过")
        for i in issues:
            print(f"  - {i}")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()