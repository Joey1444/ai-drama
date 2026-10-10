#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 短剧制作流水线（线性 driver）

设计原则（2026-10-10 重写）：
- **只编排已验证的脚本**，不重新实现解析/生成逻辑（早期版本自造 YAML DSL 与批量入口，均跑不通，已删）。
- **花钱卡点前置**：进入任何产生费用的阶段**之前**先要用户确认（修复旧版"确认永远走不到"的门序倒置）。
- **--dry-run 零成本**：跑完所有免费检查 + 校验全部输入路径 + 打印后续命令，不花一分钱。
  这是借鉴 shortdrama-pipeline 的 fake 模式（先零成本跑通流程，再真花钱）。

流程：
    0 check_script   → 剧本合法性（免费，委托 scripts/check_script.py）
    1 check_prompts  → 提示词合规+台词（免费，委托 scripts/check_prompts.py）
    2 gates          → G1/G2 结构门（免费）
    ⛔ SPEND         → 用户确认（花钱前）★ 必须显式确认
    3 generate       → 送 Pod 生成（付费；打印已验证的命令序列）
    4 collect        → 拉回素材（scripts/collect_shots.py）
    5 edit           → 剪辑成片（scripts/pipeline_edit.py）
    6 gate_G4        → 成片门（scripts/check_gate_G4.py）
    7 finalize       → 留证+成本+漂移（scripts/finalize_episode.py）

用法：
    python scripts/run_pipeline.py --series 符 --episode E1 --dry-run     # 零成本校验
    python scripts/run_pipeline.py --series 符 --episode E1               # 全流程（会问确认）
    python scripts/run_pipeline.py --series 符 --episode E1 --from edit  # 从某阶段续跑
"""
import io
import os
import sys
import argparse
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


class Stage:
    def __init__(self, key, name, *, free=True, fn=None):
        self.key, self.name, self.free, self.fn = key, name, free, fn


def check_deps():
    """启动依赖自检：区分「必需」与「可选-降级」，给出明确安装指引。
    不阻断流程（可选缺失只降级），但让人一眼知道缺什么。"""
    import importlib.util
    required = [("yaml", "PyYAML"), ("numpy", "numpy")]
    optional = [("cv2", "opencv-python", "关键帧画质检测 / 跨镜漂移检测"),
                ("faster_whisper", "faster-whisper", "对白 ASR 校验"),
                ("zhconv", "zhconv", "中文繁简归一（ASR 比对用）")]
    import shutil as _sh
    missing_req, missing_opt, missing_bin = [], [], []
    for mod, pkg in required:
        if importlib.util.find_spec(mod) is None:
            missing_req.append(pkg)
    for mod, pkg, use in optional:
        if importlib.util.find_spec(mod) is None:
            missing_opt.append((pkg, use))
    for b in ("ffmpeg", "ffprobe"):
        if _sh.which(b) is None:
            missing_bin.append(b)

    if missing_req or missing_bin:
        print("❌ 缺少必需依赖：")
        for p in missing_req:
            print(f"   - Python 包 {p}")
        for b in missing_bin:
            print(f"   - 外部命令 {b}（Windows: winget install Gyan.FFmpeg）")
        print("   安装：pip install -r requirements.txt\n")
        sys.exit(2)
    if missing_opt:
        print("ℹ️ 可选依赖缺失（对应功能会降级并告警，不影响主流程）：")
        for pkg, use in missing_opt:
            print(f"   - {pkg}（{use}）")
        print("   装齐：pip install -r requirements.txt\n")


def run_py(script, args, timeout=600):
    cmd = [sys.executable, str(ROOT / script)] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, cwd=ROOT)
    return r.returncode, r.stdout, r.stderr


def discover(series: str, episode: str):
    """按命名约定发现本集文件（用通配，容忍文档编号变化）。"""
    d = ROOT / "docs" / "方案" / series
    def find(pat):
        hits = sorted(d.glob(pat))
        return hits[0] if hits else None
    return {
        "dir": d,
        "script": find(f"*{episode}剧本*.md"),
        "storyboard": find(f"*{episode}分镜*.md"),
        "prompts": find(f"*{episode}视频提示词*.md"),
        "visual": find("01-视觉设定.md") or find("*视觉设定*.md"),
        # 世界观简报的等价物：系列总纲（G1 门的输入）
        "worldview": find("*总纲*.md") or find("*世界观*.md"),
    }


def validate_inputs(files):
    problems = []
    for k in ("script", "storyboard", "prompts"):
        if files[k] is None:
            problems.append(f"缺 {k}（按 *{{EP}}*.md 未找到）")
    return problems


def stage_checks(files):
    """阶段 0-2：免费门禁（委托现成校验器）。"""
    ok = True
    for label, script, args in [
        ("check_script", "scripts/check_script.py", [files["script"]]),
        ("check_prompts", "scripts/check_prompts.py", [files["prompts"], files["script"]]),
    ]:
        code, out, err = run_py(script, args)
        print(f"  [{label}] 退出码 {code}")
        if code != 0:
            print((out or err)[-500:])
            ok = False
    # G1（结构）：**仅提示，不阻断**——世界观文档格式多样，误杀代价高于收益
    g1_target = files.get("worldview")
    if g1_target:
        code, out, err = run_py("scripts/check_gate_G1.py", [g1_target])
        print(f"  [gate_G1] 退出码 {code}" + ("" if code == 0 else "  ⚠️ 结构提示（不阻断）"))
    else:
        print("  [gate_G1] ⚠️ 未找到世界观简报/系列总纲，跳过")
    # G2（机器项，委托 check_script）：可靠，**阻断**
    code, out, err = run_py("scripts/check_gate_G2.py", [files["script"]])
    print(f"  [gate_G2] 退出码 {code}")
    if code != 0:
        ok = False
    return ok


def print_generate_commands(files, series, episode):
    """打印 Pod 侧已验证的生成命令序列（不做实现——避免重造坏轮子）。"""
    print("\n  📋 送发生成（在 Pod 内，已验证的序列）：")
    print("     1) scp scripts/ 与素材到 Pod")
    print("     2) python scripts/extract_shots.py <视频提示词.md>   # -> shots.json")
    print("     3) 逐镜：")
    print("        python scripts/make_payload.py --shots _validate/batch/shots.json \\")
    print("               --workflow-dir _validate/batch --shot M01 --out /tmp/wf_M01.json")
    print("        python3 comfy_ui2api.py /tmp/wf_M01.json -o /tmp/api_M01.json")
    print("        python3 comfy_patch.py /tmp/api_M01.json /tmp/payload_M01.json")
    print("        curl -b ck.txt -X POST -H 'Content-Type: application/json' \\")
    print("             --data-binary @/tmp/payload_M01.json http://127.0.0.1:8188/prompt")
    print("     4) 队列空后拉回：")
    print(f"        python scripts/collect_shots.py --host <ip> --port <port> "
          f"--out _validate/shots_real")
    print("\n  ⚠️ 详见 docs/调研/H3-RunPod-实操手册.md（8 个坑）")


def main():
    ap = argparse.ArgumentParser(description="AI 短剧制作流水线（线性）")
    ap.add_argument("--series", required=True)
    ap.add_argument("--episode", required=True, help="如 E1")
    ap.add_argument("--dry-run", action="store_true", help="零成本：只跑免费检查+校验输入")
    ap.add_argument("--from", dest="from_stage", default=None,
                    choices=["check", "generate", "collect", "edit", "gate_G4", "finalize"])
    ap.add_argument("--yes", action="store_true", help="预先确认为生成花钱（跳过交互）")
    args = ap.parse_args()

    check_deps()

    files = discover(args.series, args.episode)
    print("=" * 62)
    print(f"流水线：{args.series} {args.episode}   {'[DRY-RUN 零成本]' if args.dry_run else ''}")
    print("=" * 62)
    print("发现文件：")
    for k in ("script", "storyboard", "prompts", "visual", "worldview"):
        v = files.get(k)
        print(f"  {k:11s} {v.relative_to(ROOT) if v else '— 未找到'}")

    problems = validate_inputs(files)
    if problems:
        print("\n❌ 输入不完整：")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    # ---- 阶段 0-2：免费检查 ----
    print("\n▶ 阶段 0-2：免费门禁")
    checks_ok = stage_checks(files)
    if not checks_ok:
        print("\n❌ 免费门禁未通过，停止（先修剧本/提示词）")
        sys.exit(1)
    print("  ✅ 免费门禁通过")

    if args.dry_run:
        print_generate_commands(files, args.series, args.episode)
        print("\n✅ DRY-RUN 完成：输入齐备、免费门禁通过、命令序列就绪。未花任何钱。")
        return

    # ---- ⛔ 花钱卡点（前置于生成之前）----
    print("\n" + "=" * 62)
    print("⛔ SPEND 卡点：下一步会**花钱**（Pod GPU）")
    print("=" * 62)
    # 成本预估
    code, out, err = run_py("scripts/cost_calculator.py",
                            ["--prompts", files["prompts"], "--model", "h3",
                             "--platform", "runpod", "--images", "--output", "json"])
    if code == 0:
        import json
        try:
            c = json.loads(out)
            print(f"  现金成本预估：¥{c.get('cash_total_cny', '?')}（预算线 ¥15）")
        except Exception:
            pass
    if not args.yes:
        ans = input("  确认送发生成？(y/N): ").strip().lower()
        if ans not in ("y", "yes", "是"):
            print("  已取消，未花钱。")
            sys.exit(0)
    else:
        print("  已用 --yes 预确认")

    # ---- 阶段 3：生成（打印命令；实际在 Pod 内跑）----
    print("\n▶ 阶段 3：生成")
    print_generate_commands(files, args.series, args.episode)
    input("  在 Pod 内完成生成并拉回素材后，回车继续...")

    # ---- 阶段 4-7：委托已验证脚本 ----
    shots_real = ROOT / "_validate" / "shots_real"
    steps = [
        ("edit", "剪辑成片", "scripts/pipeline_edit.py", [
            "--storyboard", files["storyboard"], "--prompts", files["prompts"],
            "--script", files["script"], "--shots", shots_real,
            "--output", ROOT / "_validate" / "out" / "final.mp4"]),
        ("gate_G4", "成片门", "scripts/check_gate_G4.py", [
            ROOT / "_validate" / "out" / "final.mp4", files["script"], "--approve"]),
        ("finalize", "收尾留证", "scripts/finalize_episode.py", [
            "--episode", args.episode, "--series", args.series,
            "--output", ROOT / "_validate" / "out" / "final.mp4",
            "--shots", shots_real]),
    ]
    started = args.from_stage is None
    for key, name, script, sargs in steps:
        if not started:
            started = (args.from_stage == key)
            if not started:
                print(f"\n⏭️ 跳过 {name}（--from {args.from_stage}）")
                continue
        print(f"\n▶ {name}（{script}）")
        code, out, err = run_py(script, sargs, timeout=1800)
        print(out[-1500:] if out else "")
        if code != 0:
            print(f"❌ {name} 失败（退出码 {code}）\n{err[-500:]}")
            sys.exit(1)

    print("\n" + "=" * 62)
    print("✅ 流水线完成")
    print("=" * 62)


if __name__ == "__main__":
    main()
