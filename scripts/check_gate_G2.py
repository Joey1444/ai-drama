#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G2 剧本门检查

设计原则（2026-10-10 修正）：**不重造轮子，不机判本该人判的东西。**
- 机器可校验项（同框/台词容量/连续性标注）→ 委托 scripts/check_script.py
- 判断类评分（钩子强度/反转力度/实害具体度/可拍性）→ 读评分文件
  （由 audience-proxy + producer 产出，**不做关键词匹配**——那会误杀合格剧本）

评分文件约定：`docs/方案/<系列>/.scores/<EP>.json`
    {"钩子强度":5,"反转力度":4,"实害具体度":4,"可拍性":5,"scored_by":"audience-proxy+producer"}
缺失时门禁**不阻断**，标记 needs_human_review（与 check_script.py 的口径一致）。

用法：python scripts/check_gate_G2.py <剧本路径> [--scores <评分文件路径>]
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
CHECK_SCRIPT = ROOT / "scripts" / "check_script.py"


def run_check_script(script_path: Path) -> tuple:
    """委托现成的 check_script.py 做机器可校验项"""
    try:
        r = subprocess.run(
            [sys.executable, str(CHECK_SCRIPT), str(script_path)],
            capture_output=True, text=True, encoding="utf-8", timeout=120
        )
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return -1, "", f"找不到 {CHECK_SCRIPT}"
    except Exception as e:
        return -1, "", str(e)


def load_scores(scores_path: Path) -> dict:
    if scores_path and scores_path.exists():
        try:
            return json.loads(scores_path.read_text(encoding="utf-8"))
        except Exception as e:
            return {"_error": str(e)}
    return {}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)

    script_path = Path(sys.argv[1])
    scores_path = None
    if "--scores" in sys.argv:
        scores_path = Path(sys.argv[sys.argv.index("--scores") + 1])
    else:
        # 默认找 <系列>/.scores/<EP>.json
        ep = script_path.stem.split("-")[0]  # 如 "06"
        scores_path = script_path.parent / ".scores" / f"{ep}.json"

    if not script_path.exists():
        print(f"❌ 剧本不存在: {script_path}")
        sys.exit(1)

    issues = []
    needs_human = False

    # ---- 1. 机器可校验项：委托 check_script.py ----
    code, out, err = run_check_script(script_path)
    machine_ok = (code == 0)
    print(out)
    if not machine_ok:
        issues.append(f"❌ check_script.py 未通过（退出码 {code}）")
        if err:
            issues.append(err[:300])
    machine_note = "✅ 机器可校验项通过" if machine_ok else "❌ 机器可校验项未通过"

    # ---- 2. 判断类评分：读评分文件 ----
    scores = load_scores(scores_path)
    DIMS = ["钩子强度", "反转力度", "实害具体度", "可拍性"]
    scoring_ok = False
    total = None

    if scores and all(d in scores for d in DIMS):
        vals = {d: scores[d] for d in DIMS}
        total = sum(vals.values())
        has_low = any(v <= 2 for v in vals.values())
        scoring_ok = (total >= 14) and not has_low
        if not scoring_ok:
            if total < 14:
                issues.append(f"❌ 四维总分 {total}/20 < 14")
            for d, v in vals.items():
                if v <= 2:
                    issues.append(f"❌ 单项「{d}」= {v} ≤ 2（直接打回）")
    else:
        needs_human = True
        print("ℹ️ 未找到评分文件，判断类评分（钩子/反转/实害/可拍性）未校验")
        print(f"   期望路径: {scores_path}")
        print("   → 需 audience-proxy + producer 产出评分后写入：")
        print('     {"钩子强度":N,"反转力度":N,"实害具体度":N,"可拍性":N,"scored_by":"..."}')

    # ---- 3. 结论 ----
    # 机器项不过 → 直接失败；机器项过但无评分 → 标记待人工，不阻断
    passed = machine_ok and scoring_ok
    if machine_ok and needs_human:
        passed = True  # 与 check_script.py 口径一致：判断项交人工，不机器阻断

    result = {
        "gate": "G2",
        "name": "剧本门",
        "passed": passed,
        "machine_check": {"passed": machine_ok, "note": machine_note},
        "scoring": {"total": total, "scores": scores or None,
                    "checked": not needs_human},
        "needs_human_review": needs_human,
        "issues": issues,
        "checked_file": str(script_path),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if machine_ok and not needs_human:
        if passed:
            print(f"\n✅ G2 剧本门通过：机器项过 + 四维 {total}/20")
        else:
            print(f"\n❌ G2 剧本门未通过：四维 {total}/20")
    elif machine_ok:
        print(f"\n🟡 G2 机器项通过，判断类评分待补（needs_human_review）")
    else:
        print(f"\n❌ G2 未通过：机器可校验项失败")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()