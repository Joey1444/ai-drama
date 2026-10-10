#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 短剧单集成本计算器
用法：python 成本计算器.py --shots 13 --duration 60 --model h3 --platform runpod
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import Literal

@dataclass
class CostBreakdown:
    video_generation: float = 0.0
    image_generation: float = 0.0
    tts_voice: float = 0.0
    lip_sync: float = 0.0
    bgm_sfx: float = 0.0
    compute_runtime: float = 0.0
    storage: float = 0.0
    manual_hours: float = 0.0
    manual_cost: float = 0.0
    contingency: float = 0.0  # 20% 风险缓冲
    total_cny: float = 0.0
    total_usd: float = 0.0

# 汇率
USDCNY = 7.2

# 模型单价 (元/秒，含重抽系数)
MODEL_PRICES = {
    "h3": {"cloud_768p": 0.58, "cloud_2k": 0.94, "runpod_4090": 0.07, "runpod_5090": 0.05},
    "seedance": {"cloud_720p": 0.60, "cloud_1080p": 1.20},
    "wan": {"cloud_720p": 0.40, "cloud_1080p": 0.80},
    "kling": {"cloud_std": 0.50, "cloud_omni": 1.00},
}

# 重抽系数
RESHOOT_FACTOR = {"low": 1.0, "medium": 1.5, "high": 3.0}

# 人工时薪
MANUAL_RATE_CNY = 150  # 元/小时

def calculate_cost(
    shots: int,
    avg_duration: float,
    model: str,
    platform: Literal["cloud", "runpod"],
    quality: Literal["low", "medium", "high"] = "medium",
    resolution: Literal["768p", "720p", "1080p", "2k"] = "768p",
    need_images: bool = False,
    need_tts: bool = False,
    need_lip_sync: bool = False,
    need_bgm: bool = False,
    manual_hours: float = 2.0,
) -> CostBreakdown:
    cb = CostBreakdown()

    # 视频生成总秒数
    total_seconds = shots * avg_duration * RESHOOT_FACTOR[quality]

    # 视频生成成本
    if model == "h3":
        if platform == "cloud":
            key = "cloud_2k" if resolution == "2k" else "cloud_768p"
            cb.video_generation = total_seconds * MODEL_PRICES["h3"][key]
        else:  # runpod
            key = "runpod_5090" if "5090" in platform else "runpod_4090"
            cb.video_generation = total_seconds * MODEL_PRICES["h3"][key]
            cb.compute_runtime = (total_seconds / 4.5) * 60 * (0.74 / 3600) * USDCNY  # 4.5秒/分钟采样速度估算
    elif model == "seedance":
        key = "cloud_1080p" if resolution in ["1080p", "2k"] else "cloud_720p"
        cb.video_generation = total_seconds * MODEL_PRICES["seedance"][key]
    elif model == "wan":
        key = "cloud_1080p" if resolution in ["1080p", "2k"] else "cloud_720p"
        cb.video_generation = total_seconds * MODEL_PRICES["wan"][key]
    elif model == "kling":
        key = "cloud_omni" if quality == "high" else "cloud_std"
        cb.video_generation = total_seconds * MODEL_PRICES["kling"][key]

    # 图片生成 (关键帧链路)
    if need_images:
        # Qwen-Image 在同 Pod，GPU 分钟成本极低
        cb.image_generation = shots * 0.5  # 约 ¥0.5/张

    # TTS/配音
    if need_tts:
        cb.tts_voice = shots * 2.0  # 约 ¥2/镜头

    # 口型同步
    if need_lip_sync:
        cb.lip_sync = shots * 5.0  # 约 ¥5/镜头

    # BGM/音效
    if need_bgm:
        cb.bgm_sfx = 30.0  # 单集固定成本

    # 存储/网络卷 (月摊销到单集)
    cb.storage = 2.0

    # 人工成本
    cb.manual_hours = manual_hours
    cb.manual_cost = manual_hours * MANUAL_RATE_CNY

    # 小计
    subtotal = (cb.video_generation + cb.image_generation + cb.tts_voice +
                cb.lip_sync + cb.bgm_sfx + cb.compute_runtime + cb.storage + cb.manual_cost)

    # 风险缓冲 20%
    cb.contingency = subtotal * 0.2

    cb.total_cny = subtotal + cb.contingency
    cb.total_usd = cb.total_cny / USDCNY

    return cb

def main():
    parser = argparse.ArgumentParser(description="AI短剧单集成本计算器")
    parser.add_argument("--shots", type=int, default=13, help="镜头数")
    parser.add_argument("--duration", type=int, default=60, help="目标时长(秒)")
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
    avg_duration = args.duration / args.shots

    cb = calculate_cost(
        shots=args.shots,
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
    )

    if args.output == "json":
        print(json.dumps(asdict(cb), ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*50}")
        print(f"AI短剧单集成本预估 | {args.model.upper()} | {args.platform} | {args.quality}")
        print(f"{'='*50}")
        print(f"镜头数: {args.shots} | 目标时长: {args.duration}s | 平均镜长: {avg_duration:.1f}s")
        print(f"重抽系数: {RESHOOT_FACTOR[args.quality]}x | 分辨率: {args.resolution}")
        print(f"{'-'*50}")
        print(f"视频生成:     ¥{cb.video_generation:>8.2f}")
        if cb.image_generation: print(f"关键帧图片:   ¥{cb.image_generation:>8.2f}")
        if cb.tts_voice:    print(f"TTS配音:      ¥{cb.tts_voice:>8.2f}")
        if cb.lip_sync:     print(f"口型同步:      ¥{cb.lip_sync:>8.2f}")
        if cb.bgm_sfx:      print(f"BGM/音效:      ¥{cb.bgm_sfx:>8.2f}")
        if cb.compute_runtime: print(f"算力运行时:    ¥{cb.compute_runtime:>8.2f}")
        print(f"存储/网络:     ¥{cb.storage:>8.2f}")
        print(f"人工({cb.manual_hours}h):      ¥{cb.manual_cost:>8.2f}")
        print(f"{'-'*50}")
        print(f"小计:         ¥{cb.total_cny - cb.contingency:>8.2f}")
        print(f"风险缓冲(20%):¥{cb.contingency:>8.2f}")
        print(f"{'='*50}")
        print(f"总计:         ¥{cb.total_cny:>8.2f} (≈ ${cb.total_usd:.2f})")
        print(f"{'='*50}\n")

        # 预算判定
        budget_ok = cb.total_cny < 60 if args.platform == "cloud" else cb.total_cny < 15
        status = "✅ 符合验收标准" if budget_ok else "⚠️ 超预算，需优化"
        print(f"验收标准: 云API<¥60 / RunPod<¥15 | {status}")

if __name__ == "__main__":
    main()