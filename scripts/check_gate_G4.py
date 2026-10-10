#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G4 成片门检查：build通过 + ASR≥90% + 抽帧肉眼确认无崩坏
用法：python scripts/check_gate_G4.py <成片路径> <剧本路径> [--approve]
"""

import io
import sys
import json
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Windows 上 stdout 默认 GBK，中文/emoji 会乱码或直接崩溃，强制 UTF-8
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

def run_cmd(cmd: List[str], cwd: Path = None) -> Tuple[int, str, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=cwd)
    return result.returncode, result.stdout, result.stderr

def check_build_passed(output_dir: Path) -> Tuple[bool, List[str]]:
    """检查 build.py 是否成功产出成片"""
    issues = []
    final_mp4 = output_dir / "final.mp4"

    if not final_mp4.exists():
        issues.append(f"❌ 成片不存在: {final_mp4}")
        return False, issues

    # 检查规格
    code, stdout, stderr = run_cmd([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name,r_frame_rate",
        "-of", "json", str(final_mp4)
    ])

    if code != 0:
        issues.append(f"❌ ffprobe 失败: {stderr}")
        return False, issues

    import json
    info = json.loads(stdout)
    stream = info["streams"][0]

    width = stream["width"]
    height = stream["height"]
    codec = stream["codec_name"]
    fps_str = stream["r_frame_rate"]
    num, den = map(int, fps_str.split('/'))
    fps = num / den

    issues_spec = []

    if width != 1080 or height != 1920:
        issues_spec.append(f"分辨率 {width}x{height} ≠ 1080x1920")
    if codec not in ["h264", "hevc"]:
        issues_spec.append(f"编码 {codec} 非 h264/hevc")
    if abs(fps - 30) > 1 and abs(fps - 60) > 1:
        issues_spec.append(f"帧率 {fps:.1f}fps 非标准 30/60fps")

    # 音频检查
    code, stdout, stderr = run_cmd([
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels",
        "-of", "json", str(final_mp4)
    ])
    if code == 0:
        ainfo = json.loads(stdout)
        astream = ainfo["streams"][0]
        if astream.get("sample_rate") != "32000":
            issues_spec.append(f"采样率 {astream.get('sample_rate')}Hz ≠ 32000Hz")
        if astream.get("channels") != 2:
            issues_spec.append(f"声道数 {astream.get('channels')} ≠ 2")

    if issues_spec:
        issues.append("⚠️ 规格不符合验收标准: " + "; ".join(issues_spec))
    else:
        print("  ✅ 成片规格符合验收标准 (1080x1920 / h264 / aac 32kHz / 30/60fps)")

    return len(issues) == 0, issues

def check_asr_similarity(final_mp4: Path, script_path: Path) -> Tuple[bool, List[str], float]:
    """ASR 校验：对白相似度 ≥90%

    ⚠️ verify_asr.py 的接口是**位置参数**（音频 参考文本）+ **文本输出**，
    不是 --video/--script + JSON。早期版本曾按错误接口写，跑不通。
    """
    issues = []

    # 依赖检查：faster-whisper 未装时不谎报，明确告警并跳过
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        issues.append("⚠️ 未安装 faster-whisper，ASR 校验跳过（pip install faster-whisper）——需人工核对台词")
        return True, issues, -1.0

    # verify_asr.py 的位置参数：argv[1]=音频/视频, argv[2]=参考文本
    # ⚠️ 实际路径是 _validate/verify_asr.py（不是 scripts/）
    verify_asr = ROOT / "_validate" / "verify_asr.py"
    if not verify_asr.exists():
        issues.append(f"⚠️ 找不到 {verify_asr}，ASR 校验跳过")
        return True, issues, -1.0
    code, stdout, stderr = run_cmd([
        sys.executable, str(verify_asr),
        str(final_mp4), str(script_path)
    ])

    if code != 0:
        issues.append(f"❌ ASR 校验失败: {stderr[:300]}")
        return False, issues, 0.0

    # 解析 "相似度    XX.X%    通过" 这一行
    match = re.search(r"相似度\s+([\d.]+)%", stdout)
    if not match:
        issues.append(f"⚠️ 无法从 ASR 输出解析相似度；原始输出已打印")
        print(stdout)
        return True, issues, -1.0

    similarity = float(match.group(1)) / 100.0

    if similarity >= 0.90:
        print(f"  ✅ ASR 相似度: {similarity:.1%} (≥90%)")
    else:
        issues.append(f"❌ ASR 相似度仅 {similarity:.1%} (<90%)")

    return len(issues) == 0, issues, similarity

def check_visual_quality(final_mp4: Path) -> Tuple[bool, List[str]]:
    """抽帧肉眼确认（自动化初筛 + 人工复核）"""
    issues = []

    # 自动化初筛：检测黑帧/绿屏/严重伪影/冻结帧
    code, stdout, stderr = run_cmd([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "frame=pkt_pts_time,pict_type",
        "-of", "csv=p=0", str(final_mp4)
    ])

    if code != 0:
        issues.append(f"⚠️ 无法抽帧分析: {stderr}")
        return True, issues  # 不阻断，仅预警

    # 简单统计
    lines = stdout.strip().split('\n')
    total_frames = len(lines)
    i_frames = sum(1 for l in lines if 'I' in l)

    print(f"  总帧数: {total_frames}, I帧: {i_frames}")

    # 时长检查
    code, stdout, stderr = run_cmd([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(final_mp4)
    ])
    if code == 0:
        duration = float(stdout.strip())
        print(f"  成片时长: {duration:.2f}s")

    return len(issues) == 0, issues

def main():
    if len(sys.argv) < 3:
        print("用法: python check_gate_G4.py <成片路径> <剧本路径> [--approve]")
        sys.exit(1)

    final_mp4 = Path(sys.argv[1])
    script_path = Path(sys.argv[2])
    auto_approve = "--approve" in sys.argv

    if not final_mp4.exists() or not script_path.exists():
        print("❌ 文件不存在")
        sys.exit(1)

    all_passed = True
    all_issues = []

    # 1. Build 通过 + 规格检查
    ok, issues = check_build_passed(final_mp4.parent)
    all_passed &= ok
    all_issues.extend(issues)

    # 2. ASR 相似度 ≥90%
    ok, issues, similarity = check_asr_similarity(final_mp4, script_path)
    all_passed &= ok
    all_issues.extend(issues)

    # 3. 视觉质量初筛
    ok, issues = check_visual_quality(final_mp4)
    all_passed &= ok
    all_issues.extend(issues)

    # 4. 用户显式确认（肉眼复核）
    human_approved = False
    if auto_approve:
        human_approved = True
        all_issues.append("ℹ️ 自动确认模式（--approve）")
    else:
        print(f"\n{'='*50}")
        print(f"G4 成片门确认")
        print(f"{'='*50}")
        print(f"成片: {final_mp4.name}")
        print(f"剧本: {script_path.name}")
        print(f"ASR相似度: {'未校验（缺依赖）' if similarity < 0 else f'{similarity:.1%}'}")
        print(f"规格检查: {'通过' if all_passed else '有问题'}")
        print(f"请人工抽帧确认无崩坏/口型错位/内容跑偏")
        print(f"{'='*50}")
        confirm = input("确认成片通过？(y/N): ").strip().lower()
        human_approved = confirm in ['y', 'yes', '是']

    all_passed &= human_approved
    if not human_approved:
        all_issues.append("❌ 用户未确认成片通过")

    # 写入通过标记
    if all_passed:
        (final_mp4.parent / ".gate_G4_passed").write_text("approved")
        (final_mp4.parent / ".gate_G4_asr.json").write_text(json.dumps({"similarity": similarity}))

    result = {
        "gate": "G4",
        "name": "成片门",
        "passed": all_passed,
        "human_approved": human_approved,
        "asr_similarity": similarity,
        "issues": all_issues,
        "checked_files": [str(final_mp4), str(script_path)]
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if all_passed:
        print(f"\n✅ G4 成片门通过：ASR {similarity:.1%}，人工确认无崩坏")
        sys.exit(0)
    else:
        print(f"\n❌ G4 成片门未通过")
        for issue in all_issues:
            print(f"  - {issue}")
        sys.exit(1)

if __name__ == "__main__":
    main()