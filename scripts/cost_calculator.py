#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI短剧单集成本计算器
用法：
  python scripts/cost_calculator.py --shots-dir _validate/shots_real --model h3 --platform runpod
  python scripts/cost_calculator.py --prompts docs/方案/符/09-E1视频提示词.md --model h3 --platform runpod --output json
"""

import io
import json
import os
import sys
import argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 汇率
USDCNY = 7.2

# 模型单价 (元/秒)。
# ⚠️ 来源分级（fact-checker 2026-10-10 核查）：
#   h3 cloud_768p/2k = 方案-v2 附录C（二手 ofox.ai，可信度中）
#   seedance 720p = 方法论（可信度中）；1080p = 方法论 ¥1.5/s（**早前误写 ¥1.2，已纠**）
#   wan / kling = **【无项目内来源·二手转述】**，仅备用，用前必须回源
MODEL_PRICES = {
    "h3": {"cloud_768p": 0.58, "cloud_2k": 0.94},
    "seedance": {"cloud_720p": 0.60, "cloud_1080p": 1.50},
    "wan": {"cloud_720p": 0.40, "cloud_1080p": 0.80},      # 【二手·待重查】
    "kling": {"cloud_std": 0.50, "cloud_omni": 0.54},      # 【二手·待重查】omni≈$0.075/s
}

# RunPod GPU 小时价（元/h）—— 事实基线：Secure 4090 $0.89/h；Community 5090 $0.69/h
# ⚠️ 早前误用方案-v2 的过时值 $0.74，已按事实基线纠正
RUNPOD_GPU_HOUR_CNY = {
    "runpod": 0.89 * USDCNY,        # Secure 4090
    "runpod_5090": 0.69 * USDCNY,   # Community 5090
}

# H3 生成吞吐：约 4.5 秒视频 / 分钟采样（事实基线：4.46s 镜采样 86s）
H3_SECONDS_PER_MINUTE = 4.5

# 重抽系数
RESHOOT_FACTOR = {"low": 1.0, "medium": 1.5, "high": 3.0}

# ⚠️ 以下为【推算/假设】值，非实测；已显式标注，改动前请回源
MANUAL_RATE_CNY = 150        # 【假设】人工时薪，无项目内来源
IMAGE_COST_PER_SHOT = 0.5    # 【假设】关键帧单张成本（同 Pod GPU 分摊）
TTS_COST_PER_SHOT = 2.0      # 【假设】TTS 单镜成本
LIPSYNC_COST_PER_SHOT = 5.0  # 【假设】口型单镜成本
BGM_COST_PER_EPISODE = 30.0  # 【假设】BGM 单集成本（本机 ACE-Step 可为 0）


def parse_prompts_for_shots(prompts_path: Path) -> list:
    """从视频提示词解析镜头 ID 列表

    真实格式：`### MOTION-EP001-01 · 血手撑墙`（三级标题，ID 形如 MOTION-EP001-01）。
    早期版本用 `##` + `\\w+` 只抓到 "EP001"，13 个标题全撞成同一个 ID。
    """
    content = prompts_path.read_text(encoding='utf-8')
    import re
    # 三级标题；ID 允许中划线（EP001-01）
    ids = re.findall(r'^#{2,3}\s+MOTION-([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\s*·', content, re.M)
    return ids


def parse_prompts_durations(prompts_path: Path) -> list:
    """从每个 MOTION 块的「时长：**Ns**」解析各镜时长（秒）"""
    content = prompts_path.read_text(encoding='utf-8')
    import re
    # 块头：### MOTION-... ，块内首个「时长：**Ns**」
    blocks = re.split(r'^#{2,3}\s+MOTION-', content, flags=re.M)[1:]
    durs = []
    for b in blocks:
        m = re.search(r'时长[：:]\s*\*\*(\d+(?:\.\d+)?)\s*s?\*\*', b)
        if not m:
            m = re.search(r'duration[：:]\s*(\d+(?:\.\d+)?)', b)
        if m:
            durs.append(float(m.group(1)))
    return durs


def calculate_cost(
    shots: int = 0,
    total_seconds: float = 0,
    avg_duration: float = 0,
    model: str = "h3",
    platform: str = "runpod",
    quality: str = "medium",
    resolution: str = "768p",
    need_images: bool = False,
    need_tts: bool = False,
    need_lip_sync: bool = False,
    need_bgm: bool = False,
    manual_hours: float = 2.0,
    shots_list: list = None,
    shots_dir: Path = None,
) -> dict:
    """计算单集成本"""
    result = {
        "video_generation": 0.0,
        "image_generation": 0.0,
        "tts_voice": 0.0,
        "lip_sync": 0.0,
        "bgm_sfx": 0.0,
        "compute_runtime": 0.0,
        "storage": 2.0,
        "manual_hours": manual_hours,
        "manual_cost": manual_hours * MANUAL_RATE_CNY,
        "contingency": 0.0,
        "total_cny": 0.0,
        "total_usd": 0.0,
        "breakdown": {},
        "shots_count": shots,
        "total_seconds": total_seconds,
    }

    # 如果提供了 shots_dir，探测真实时长
    if shots_dir and shots_dir.exists():
        total_seconds = 0
        shot_count = 0
        for mp4 in sorted(shots_dir.glob("*.mp4")):
            try:
                import subprocess
                out = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", str(mp4)],
                    capture_output=True, text=True, check=True
                ).stdout.strip()
                total_seconds += float(out)
                shot_count += 1
            except:
                pass
        if shot_count > 0:
            shots = shot_count
            avg_duration = total_seconds / shot_count
            result["shots_count"] = shots
            result["total_seconds"] = total_seconds
            result["avg_duration"] = round(avg_duration, 2)

    # 如果没有总秒数，用镜头数 * 平均时长 * 重抽系数
    if total_seconds == 0 and shots > 0 and avg_duration > 0:
        total_seconds = shots * avg_duration * RESHOOT_FACTOR.get(quality, 1.5)
        result["total_seconds"] = round(total_seconds, 1)

    # 视频生成成本
    if model == "h3":
        if platform == "cloud":
            key = "cloud_2k" if resolution == "2k" else "cloud_768p"
            result["video_generation"] = total_seconds * MODEL_PRICES["h3"][key]
        else:
            # RunPod：**只按 GPU 小时计费**（不再叠加"元/秒"，那会把成本虚高近一倍）
            gpu_rate = RUNPOD_GPU_HOUR_CNY.get(platform, RUNPOD_GPU_HOUR_CNY["runpod"])
            gpu_hours = (total_seconds / H3_SECONDS_PER_MINUTE) / 60.0
            result["compute_runtime"] = round(gpu_hours * gpu_rate, 2)
            result["video_generation"] = 0.0
            result["_runpod_note"] = (
                f"RunPod 按 GPU 小时计费：{gpu_hours:.2f}h × ¥{gpu_rate:.2f}/h "
                f"（吞吐 {H3_SECONDS_PER_MINUTE}s 视频/分钟采样）"
            )
    elif model == "seedance":
        key = "cloud_1080p" if resolution in ["1080p", "2k"] else "cloud_720p"
        result["video_generation"] = total_seconds * MODEL_PRICES["seedance"][key]
    elif model == "wan":
        key = "cloud_1080p" if resolution in ["1080p", "2k"] else "cloud_720p"
        result["video_generation"] = total_seconds * MODEL_PRICES["wan"][key]
    elif model == "kling":
        key = "cloud_omni" if quality == "high" else "cloud_std"
        result["video_generation"] = total_seconds * MODEL_PRICES["kling"][key]

    # 图片生成 (关键帧链路)
    if need_images:
        result["image_generation"] = shots * IMAGE_COST_PER_SHOT

    # TTS/配音
    if need_tts:
        result["tts_voice"] = shots * TTS_COST_PER_SHOT

    # 口型同步
    if need_lip_sync:
        result["lip_sync"] = shots * LIPSYNC_COST_PER_SHOT

    # BGM/音效
    if need_bgm:
        result["bgm_sfx"] = BGM_COST_PER_EPISODE

    # 小计
    subtotal = (result["video_generation"] + result["image_generation"] + result["tts_voice"] +
                result["lip_sync"] + result["bgm_sfx"] + result["compute_runtime"] +
                result["storage"] + result["manual_cost"])

    # 风险缓冲 20%
    result["contingency"] = round(subtotal * 0.2, 2)

    result["total_cny"] = round(subtotal + result["contingency"], 2)
    result["total_usd"] = round(result["total_cny"] / USDCNY, 2)

    # ⚠️ 现金成本 vs 人工成本必须分开：
    #    验收标准 L1#4 的「云API<¥60 / RunPod<¥15」指的是**现金支出**（算力+API+素材），
    #    人工工时是**隐性成本**，不该把预算判定顶爆（否则永远"超预算"）。
    result["cash_cost_cny"] = round(
        result["video_generation"] + result["image_generation"] + result["tts_voice"] +
        result["lip_sync"] + result["bgm_sfx"] + result["compute_runtime"] +
        result["storage"], 2)
    result["cash_contingency"] = round(result["cash_cost_cny"] * 0.2, 2)
    result["cash_total_cny"] = round(result["cash_cost_cny"] + result["cash_contingency"], 2)

    # 明细
    result["breakdown"] = {
        "视频生成": round(result["video_generation"], 2),
        "关键帧图片": round(result["image_generation"], 2),
        "TTS配音": round(result["tts_voice"], 2),
        "口型同步": round(result["lip_sync"], 2),
        "BGM/音效": round(result["bgm_sfx"], 2),
        "算力运行": round(result["compute_runtime"], 2),
        "存储/网络": round(result["storage"], 2),
        "现金小计": result["cash_cost_cny"],
        "现金风险缓冲(20%)": result["cash_contingency"],
        "现金总计(CNY)": result["cash_total_cny"],
        f"人工({manual_hours}h)": round(result["manual_cost"], 2),
        "现金+人工(CNY)": result["total_cny"],
        "现金+人工(USD)": result["total_usd"],
    }

    # 预算判定——**只看现金成本**
    budget_cap = 60 if platform == "cloud" else 15
    budget_ok = result["cash_total_cny"] < budget_cap
    result["budget_check"] = {
        "budget_cny": budget_cap,
        "cash_actual_cny": result["cash_total_cny"],
        "passed": budget_ok,
        "margin_pct": round((1 - result["cash_total_cny"] / budget_cap) * 100, 1),
        "labor_cost_cny": round(result["manual_cost"], 2),
        "_note": "预算判定只看现金成本；人工成本单列，不计入预算线"
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="AI短剧单集成本计算器")
    parser.add_argument("--prompts", help="视频提示词文件路径（用于解析镜头数）")
    parser.add_argument("--shots-dir", help="成片素材目录（用于探测真实时长）")
    parser.add_argument("--shots", type=int, default=0, help="镜头数（不提供时从 prompts 解析）")
    parser.add_argument("--duration", type=int, default=0, help="目标总时长(秒)")
    parser.add_argument("--avg-duration", type=float, default=0, help="平均镜长(秒)")
    parser.add_argument("--model", choices=["h3", "seedance", "wan", "kling"], default="h3")
    parser.add_argument("--platform", choices=["cloud", "runpod", "runpod_5090"], default="runpod")
    parser.add_argument("--quality", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--resolution", choices=["768p", "720p", "1080p", "2k"], default="768p")
    parser.add_argument("--images", action="store_true", help="需要关键帧图片生成")
    parser.add_argument("--tts", action="store_true", help="需要TTS配音")
    parser.add_argument("--lip-sync", action="store_true", help="需要口型同步")
    parser.add_argument("--bgm", action="store_true", help="需要BGM/音效")
    parser.add_argument("--manual-hours", type=float, default=2.0, help="预估人工小时")
    parser.add_argument("--output", choices=["json", "table"], default="table")

    args = parser.parse_args()

    # 解析镜头数
    shots = args.shots
    duration = args.duration
    # 诊断日志一律走 stderr —— 否则污染 --output json 的 stdout，
    # 让所有 json.loads(stdout) 的消费方（check_gate_G3 / finalize_episode）解析失败
    log = (lambda *a: print(*a, file=sys.stderr)) if args.output == "json" else print

    if args.prompts and shots == 0:
        prompts_path = Path(args.prompts)
        if prompts_path.exists():
            shot_ids = parse_prompts_for_shots(prompts_path)
            shots = len(shot_ids)
            log(f"从提示词解析到 {shots} 个镜头")
            # 若无显式时长，从块内「时长：**Ns**」汇总
            if duration == 0:
                durs = parse_prompts_durations(prompts_path)
                if durs:
                    duration = sum(durs)
                    log(f"从提示词汇总标称时长: {duration:.0f}s（各镜 {durs}）")

    # 计算平均镜长
    avg_duration = args.avg_duration
    if avg_duration == 0 and duration > 0 and shots > 0:
        avg_duration = duration / shots

    shots_dir = Path(args.shots_dir) if args.shots_dir else None

    result = calculate_cost(
        shots=shots,
        total_seconds=0,   # 传 0，让 calculate_cost 用 shots×avg×重抽系数（或实测文件时长）
        avg_duration=avg_duration,
        model=args.model,
        platform=args.platform,
        quality=args.quality,
        resolution=args.resolution,
        need_images=args.images,
        need_tts=args.tts,
        need_lip_sync=args.lip_sync,
        need_bgm=args.bgm,
        manual_hours=args.manual_hours,
        shots_dir=shots_dir,
    )

    result["avg_duration"] = round(avg_duration, 1) if avg_duration else round(
        (result.get("total_seconds", 0) / shots), 1) if shots else 0

    if args.output == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*50}")
        print(f"AI短剧单集成本预估 | {args.model.upper()} | {args.platform} | {args.quality}")
        print(f"{'='*50}")
        print(f"镜头数: {result['shots_count']} | 总时长: {result['total_seconds']:.1f}s | 平均镜长: {result.get('avg_duration', 0):.1f}s")
        print(f"重抽系数: {RESHOOT_FACTOR.get(args.quality, 1.5)}x | 分辨率: {args.resolution}")
        print(f"{'-'*50}")
        for k, v in result["breakdown"].items():
            if isinstance(v, (int, float)):
                print(f"{k:16s} ¥{v:>9.2f}")
            else:
                print(f"{k:16s} {v}")
        print(f"{'-'*50}")
        print(f"现金成本:   ¥{result['cash_total_cny']:>9.2f}  ← 预算判定依据")
        print(f"人工成本:   ¥{result['manual_cost']:>9.2f}  （{args.manual_hours}h，隐性成本，不计入预算线）")
        print(f"合计:       ¥{result['total_cny']:>9.2f} (≈ ${result['total_usd']:.2f})")
        print(f"{'='*50}\n")

        # 预算判定
        budget_ok = result["budget_check"]["passed"]
        status = "✅ 符合验收标准（现金成本）" if budget_ok else "⚠️ 现金成本超预算，需优化"
        print(f"验收标准: 云API<¥60 / RunPod<¥15 | {status}")
        print(f"现金余量: {result['budget_check']['margin_pct']:.1f}%")


if __name__ == "__main__":
    main()