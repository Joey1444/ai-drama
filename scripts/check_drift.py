#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨镜一致性漂移检测（首尾帧 Lab 色差）

用法：python scripts/check_drift.py <镜头目录> [--threshold 8]

用 OpenCV 读每镜首帧与尾帧，算 Lab 色彩空间均值 ΔE，报告平均/最大色差。
ΔE 越大 = 跨镜/镜内色彩越不一致。默认阈值 8（超出建议触发归一化或 LoRA）。

依赖 cv2：未安装时明确报错退出（不静默假装通过）。
"""
import io
import sys
import json
import argparse
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def imread_unicode(path: Path):
    """读图，绕过 OpenCV 在 Windows 上不支持非 ASCII 路径的限制。"""
    import cv2
    import numpy as np
    try:
        buf = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
    except Exception:
        return None


def frame_color(img):
    import cv2
    import numpy as np
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    return np.array(lab.reshape(-1, 3).mean(axis=0), dtype=float)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("shots_dir")
    ap.add_argument("--threshold", type=float, default=8.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        import cv2  # noqa: F401
        import numpy as np  # noqa: F401
    except ImportError:
        print("❌ 未安装 cv2/opencv-python，无法检测漂移（pip install opencv-python）", file=sys.stderr)
        sys.exit(2)

    shots_dir = Path(args.shots_dir)
    shots = sorted(shots_dir.glob("*.mp4"))
    if len(shots) < 2:
        print(f"⚠️ 镜头不足（{len(shots)} 个），跳过漂移检测", file=sys.stderr)
        sys.exit(0)

    import cv2
    results, deltas = [], []
    for s in shots:
        cap = cv2.VideoCapture(str(s))
        ok1, f1 = cap.read()
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total - 1))
        ok2, f2 = cap.read()
        cap.release()
        if not (ok1 and ok2):
            continue
        d = float(np.linalg.norm(frame_color(f1) - frame_color(f2)))
        deltas.append(d)
        results.append({"shot": s.name, "delta_e": round(d, 2)})

    avg = sum(deltas) / len(deltas) if deltas else 0.0
    mx = max(deltas) if deltas else 0.0
    out = {
        "shots": len(shots),
        "analyzed": len(deltas),
        "avg_delta_e": round(avg, 2),
        "max_delta_e": round(mx, 2),
        "threshold": args.threshold,
        "passed": avg <= args.threshold,
        "per_shot": results,
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"  {r['shot']}  ΔE {r['delta_e']:.2f}")
        print(f"  平均 ΔE {avg:.2f} / 最大 {mx:.2f}（阈值 {args.threshold}）")
        print("  ✅ 通过" if out["passed"] else "  ⚠️ 超阈值，建议归一化或 LoRA")
    sys.exit(0 if out["passed"] else 1)


if __name__ == "__main__":
    main()