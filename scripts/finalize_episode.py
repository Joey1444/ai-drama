#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
收尾脚本：留证 + 成本上报 + 漂移检测 + 自动停机
用法：
  python scripts/finalize_episode.py \
    --episode E1 \
    --series 符 \
    --output _validate/out/final.mp4 \
    --shots _validate/shots_real \
    --budget-cny 15
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd, cwd=None, capture=True):
    try:
        result = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=capture, text=True, encoding="utf-8", timeout=300)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "超时"
    except Exception as e:
        return -1, "", str(e)


def main():
    parser = argparse.ArgumentParser(description="单集收尾：留证+成本+漂移检测+自动停机")
    parser.add_argument("--episode", required=True, help="集号，如 E1")
    parser.add_argument("--series", required=True, help="系列名，如 符")
    parser.add_argument("--output", required=True, help="成片路径")
    parser.add_argument("--shots", required=True, help="成片素材目录")
    parser.add_argument("--budget-cny", type=float, default=15.0, help="预算上限(元)")
    parser.add_argument("--auto-stop-pod", action="store_true", help="自动停止 RunPod (需配置 pod_id)")
    args = parser.parse_args()

    series = args.series
    episode = args.episode                 # 如 "E1"
    output = Path(args.output).resolve()
    shots_dir = Path(args.shots).resolve()
    budget = args.budget_cny
    ep_num = int(episode[1:])              # 1
    ep3 = f"{ep_num:03d}"                  # "001"

    # 项目文档编号约定（固定类型索引，非集号）：
    #   00 人物小传 · 01 视觉设定 · 02 分集大纲 · 06 剧本 · 08 分镜 · 09 视频提示词
    doc = {
        "剧本": f"06-{episode}剧本-定稿.md",
        "分镜": f"08-{episode}分镜.md",
        "视频提示词": f"09-{episode}视频提示词.md",
        "图片提示词": f"{episode}图片提示词.md",
    }

    # 留证目录
    evidence_dir = ROOT / "docs" / "生成留证" / series / f"EP{ep3}"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    print(f"{'='*60}")
    print(f"收尾任务：{series} {episode}")
    print(f"{'='*60}")

    all_ok = True
    report = {
        "series": series,
        "episode": episode,
        "timestamp": datetime.now().isoformat(),
        "output": str(output),
        "shots_dir": str(shots_dir),
        "budget_cny": budget,
        "steps": {}
    }

    # 1. 留证：复制关键文件
    print(f"\n📁 Step 1: 证据留证 -> {evidence_dir}")
    evidence_files = [
        ("剧本", ROOT / "docs" / "方案" / series / doc["剧本"]),
        ("分镜", ROOT / "docs" / "方案" / series / doc["分镜"]),
        ("视频提示词", ROOT / "docs" / "方案" / series / doc["视频提示词"]),
        ("图片提示词", ROOT / "docs" / "方案" / series / doc["图片提示词"]),
        ("edit.json", ROOT / "_validate" / "edit.json"),
        ("字幕 SRT", ROOT / "_validate" / "subs" / "subtitle.srt"),
        ("字幕 ASS", ROOT / "_validate" / "subs" / "subtitle.ass"),
        ("剪辑图", ROOT / "_validate" / "out" / "graph.txt"),
    ]
    copied = 0
    for name, src in evidence_files:
        if src.exists():
            dst = evidence_dir / src.name
            shutil.copy2(src, dst)
            copied += 1
            print(f"  ✅ {name}")
        else:
            print(f"  ⚠️ 缺失: {name} ({src})")
    report["steps"]["evidence"] = {"copied": copied, "dir": str(evidence_dir)}

    # 2. 成本核算
    print(f"\n💰 Step 2: 成本核算")
    code, out, err = run_cmd([
        sys.executable, str(ROOT / "scripts" / "cost_calculator.py"),
        "--shots-dir", str(shots_dir),
        "--model", "h3",
        "--platform", "runpod",
        "--output", "json"
    ])
    cost_info = {}
    if code == 0:
        try:
            # cost_calculator 的日志已走 stderr，stdout 是纯 JSON
            cost_info = json.loads(out)
            actual = cost_info.get("cash_total_cny", cost_info.get("total_cny", 0))
            print(f"  现金成本: ¥{actual:.2f} / 预算 ¥{budget:.2f} ({actual/budget*100:.0f}%)")
            if actual > budget:
                print(f"  ⚠️ 现金成本超预算！")
        except Exception as e:
            print(f"  ⚠️ 成本解析失败: {e}")
    else:
        print(f"  ⚠️ 成本计算失败: {err}")
    report["steps"]["cost"] = cost_info

    # 3. 漂移检测
    print(f"\n🔍 Step 3: 跨镜一致性检测")
    shots = sorted(shots_dir.glob("*.mp4"))
    # 委托 scripts/check_drift.py（不在 finalize 内联 -c，避免 Windows 反斜杠路径转义炸）
    code, out, err = run_cmd([
        sys.executable, str(ROOT / "scripts" / "check_drift.py"),
        str(shots_dir), "--json", "--threshold", "8"
    ])
    if code == 2:
        print(f"  ⚠️ 未安装 cv2，漂移检测跳过（pip install opencv-python）")
        report["steps"]["drift"] = {"skipped": "cv2 not installed"}
    elif code in (0, 1):
        try:
            drift = json.loads(out)
            avg = drift.get("avg_delta_e", 0)
            print(f"  平均色差 ΔE={avg}（阈值 8）")
            print("  ✅ 通过" if drift.get("passed") else "  ⚠️ 超阈值，建议归一化/LoRA")
            report["steps"]["drift"] = drift
        except Exception as e:
            print(f"  ⚠️ 漂移结果解析失败: {e}")
    else:
        print(f"  ⚠️ 漂移检测失败: {err[:200]}")

    # 4. ASR 校验（复用 verify_asr.py）
    print(f"\n🎤 Step 4: ASR 对白校验")
    script_path = ROOT / "docs" / "方案" / series / doc["剧本"]
    if script_path.exists() and output.exists():
        # verify_asr.py 是位置参数接口（音频 参考文本）+ 文本输出
        try:
            import faster_whisper  # noqa: F401
            code, out, err = run_cmd([
                sys.executable, str(ROOT / "_validate" / "verify_asr.py"),
                str(output), str(script_path)
            ])
            if code == 0:
                m = re.search(r"相似度\s+([\d.]+)%", out)
                if m:
                    sim = float(m.group(1)) / 100.0
                    print(f"  相似度: {sim:.1%}")
                    print(f"  {'✅ 通过 (≥90%)' if sim >= 0.9 else '❌ 不达标 (<90%)'}")
                    report["steps"]["asr"] = {"similarity": sim}
                else:
                    print(f"  输出: {out[:200]}")
            else:
                print(f"  ⚠️ ASR 失败: {err[:200]}")
        except ImportError:
            print(f"  ⚠️ 未安装 faster-whisper，跳过 ASR 校验")
            report["steps"]["asr"] = {"skipped": "faster-whisper not installed"}
    else:
        print(f"  ⚠️ 剧本或成片缺失，跳过")

    # 5. 规格校验
    print(f"\n📐 Step 5: 成片规格校验")
    if output.exists():
        code, out, err = run_cmd([
            "ffprobe", "-v", "error",
            "-show_entries", "stream=width,height,codec_name,r_frame_rate,sample_rate,channels",
            "-of", "json", str(output)
        ])
        if code == 0:
            info = json.loads(out)
            v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
            a = next((s for s in info["streams"] if s["codec_type"] == "audio"), {})
            checks = {
                "分辨率": f"{v.get('width')}x{v.get('height')}" == "1080x1920",
                "视频编码": v.get("codec_name") in ["h264", "hevc"],
                "音频编码": a.get("codec_name") == "aac",
                "采样率": a.get("sample_rate") == "32000",
                "声道": a.get("channels") == 2,
            }
            all_pass = all(checks.values())
            for k, v in checks.items():
                status = "✅" if v else "❌"
                print(f"  {status} {k}: {v}")
            report["steps"]["specs"] = checks
            if not all_pass:
                print(f"  ⚠️ 规格不符合验收标准")
        else:
            print(f"  ⚠️ ffprobe 失败")

    # 6. 自动停机（可选）
    if args.auto_stop_pod:
        print(f"\n🛑 Step 6: 自动停止 RunPod")
        pod_id_file = ROOT / "_validate" / ".pod_id"
        if pod_id_file.exists():
            pod_id = pod_id_file.read_text().strip()
            # 这里需要配置 RunPod API Key
            print(f"  Pod ID: {pod_id} (需配置 API Key 才能自动停止)")
        else:
            print(f"  ⚠️ 未找到 .pod_id")

    # 7. 清理临时文件（可选）
    print(f"\n🧹 Step 7: 清理临时文件（保留留证与成片）")
    # 可选：清理 _validate/shots / _validate/batch / _validate/shots_test 等

    # 保存汇总报告
    report_path = evidence_dir / "finalize_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📋 汇总报告: {report_path}")

    print(f"\n{'='*60}")
    print("收尾完成")
    print(f"留证目录: {evidence_dir}")
    print(f"成本: {cost_info.get('total_cny', 'N/A')} / ¥{budget}")
    print(f"成片: {output}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()