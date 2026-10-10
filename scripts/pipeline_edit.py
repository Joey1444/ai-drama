#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一剪辑入口：整合 make_edit.py + make_srt.py + build.py
用法：
  python scripts/pipeline_edit.py \
    --storyboard "docs/方案/符/08-E1分镜.md" \
    --prompts "docs/方案/符/09-E1视频提示词.md" \
    --script "docs/方案/符/06-E1剧本-定稿.md" \
    --shots _validate/shots_real \
    --output _validate/out/final.mp4

特性：
- 单命令完成：分镜→edit.json→字幕→成片
- 强制 UTF-8（Windows 兼容）
- 真实时长探测（ffprobe）
- 失败自动回退并告警
"""

import io
import json
import os
import re
import subprocess
import sys
import argparse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd, cwd=None, check=True, capture=True):
    """运行命令，返回 (code, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd, cwd=cwd or ROOT,
            capture_output=capture, text=True, encoding="utf-8",
            timeout=1800, check=check
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout, e.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "命令超时"


def main():
    parser = argparse.ArgumentParser(description="短剧统一剪辑管线")
    parser.add_argument("--storyboard", required=True, help="分镜文件路径")
    parser.add_argument("--prompts", required=True, help="视频提示词文件路径")
    parser.add_argument("--script", required=True, help="剧本文件路径")
    parser.add_argument("--shots", required=True, help="成片素材目录")
    parser.add_argument("--output", required=True, help="成片输出路径")
    parser.add_argument("--bgm", default="_validate/bgm.m4a", help="背景音乐路径")
    parser.add_argument("--skip-edit", action="store_true", help="跳过 edit.json 生成（已存在）")
    parser.add_argument("--skip-srt", action="store_true", help="跳过字幕生成（已存在）")
    parser.add_argument("--skip-build", action="store_true", help="只生成 edit.json 和字幕，不剪片")
    args = parser.parse_args()

    # 路径标准化
    storyboard = Path(args.storyboard).resolve()
    prompts = Path(args.prompts).resolve()
    script = Path(args.script).resolve()
    shots_dir = Path(args.shots).resolve()
    output = Path(args.output).resolve()
    bgm = Path(args.bgm).resolve()
    edit_json = ROOT / "_validate" / "edit.json"
    srt_path = ROOT / "_validate" / "subs" / "subtitle.srt"
    ass_path = ROOT / "_validate" / "subs" / "subtitle.ass"

    # 创建输出目录
    output.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "_validate" / "subs").mkdir(parents=True, exist_ok=True)
    (ROOT / "_validate" / "out").mkdir(parents=True, exist_ok=True)

    print(f"{'='*60}")
    print(f"短剧统一剪辑管线")
    print(f"{'='*60}")
    print(f"分镜: {storyboard.name}")
    print(f"提示词: {prompts.name}")
    print(f"剧本: {script.name}")
    print(f"素材: {shots_dir}")
    print(f"输出: {output}")
    print(f"{'='*60}")

    # ===== Stage 1: 生成 edit.json =====
    if not args.skip_edit:
        print(f"\n📝 Stage 1: 生成 edit.json")
        cmd = [
            sys.executable, str(ROOT / "scripts" / "make_edit.py"),
            str(storyboard), "-o", str(edit_json),
            "--clips", str(shots_dir)
        ]
        code, out, err = run_cmd(cmd)
        if code != 0:
            print(f"❌ make_edit.py 失败: {err}")
            sys.exit(code)
        print(f"  ✅ {edit_json}")

    # ===== Stage 2: 生成字幕 (SRT + ASS) =====
    if not args.skip_srt:
        print(f"\n📝 Stage 2: 生成字幕 (SRT + ASS)")
        cmd = [
            sys.executable, str(ROOT / "scripts" / "make_srt.py"),
            str(prompts),
            "--script", str(script),
            "--shots", str(ROOT / "_validate" / "batch" / "shots.json"),
            "--edit", str(edit_json),
            "--clips", str(shots_dir),
            "-o", str(srt_path)
        ]
        code, out, err = run_cmd(cmd)
        if code != 0:
            print(f"❌ make_srt.py 失败: {err}")
            sys.exit(code)
        print(f"  ✅ {srt_path}")
        print(f"  ✅ {ass_path}")

    # ===== Stage 3: 剪辑成片 =====
    if not args.skip_build:
        print(f"\n📝 Stage 3: 剪辑成片")
        # 复制 bgm 到 _validate/out/ 供 build.py 使用
        if bgm.exists():
            import shutil
            shutil.copy2(bgm, ROOT / "_validate" / "out" / "bgm.m4a")
            print(f"  📋 BGM 已复制: {bgm}")
        else:
            print(f"  ⚠️ BGM 不存在: {bgm}，将无背景音乐")

        cmd = [
            sys.executable, str(ROOT / "_validate" / "build.py"),
            str(edit_json)
        ]
        code, out, err = run_cmd(cmd, cwd=ROOT / "_validate")
        if code != 0:
            print(f"❌ build.py 失败: {err}")
            sys.exit(code)

        # 复制成片到指定输出路径
        final_mp4 = ROOT / "_validate" / "out" / "final.mp4"
        if final_mp4.exists():
            import shutil
            shutil.copy2(final_mp4, output)
            print(f"  ✅ 成片已输出: {output}")
        else:
            print(f"❌ 成片未生成: {final_mp4}")
            sys.exit(1)

    print(f"\n{'='*60}")
    print("✅ 全流程完成！")
    print(f"  edit.json: {edit_json}")
    print(f"  字幕: {srt_path} / {ass_path}")
    print(f"  成片: {output}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()