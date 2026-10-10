#!/usr/bin/env python3
"""对白校验：把成片音轨转写，与剧本台词比对

用途   H3 原生对白不保证逐字念对台词（方案 A2）。此脚本量化"念串了多少"，
       给出差异位置，人工只看不一致处。

关键   whisper 对中文默认输出【繁体 + 半角标点】，直接比对会虚低。
       故先归一化（繁转简 + 去标点空白），再比"可发声字"。

用法   python verify_asr.py [音频或视频文件] [参考文本]
       默认 tts.wav 对 tts_text.txt
"""
import difflib
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent


def normalize(s: str) -> str:
    """繁转简 + 去掉标点/空白，只留可发声字（4.1 字/秒 的口径）"""
    try:
        from zhconv import convert
        s = convert(s, "zh-cn")
    except ImportError:
        pass
    return re.sub(r"[\W_]+", "", s)


def main() -> None:
    audio = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tts.wav"
    ref_path = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "tts_text.txt"
    if not audio.exists():
        sys.exit(f"找不到音频: {audio}")

    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio), language="zh", vad_filter=True)
    hyp = "".join(s.text for s in segments).strip()
    ref = ref_path.read_text(encoding="utf-8").strip() if ref_path.exists() else ""

    print(f"音频     {audio.name}  时长 {info.duration:.2f}s")
    print(f"转写     {hyp}")
    print(f"剧本     {ref}")
    if not ref:
        return

    n_ref, n_hyp = normalize(ref), normalize(hyp)
    ratio = difflib.SequenceMatcher(None, n_ref, n_hyp).ratio()
    print(f"\n归一化后  剧本 {len(n_ref)} 字 / 转写 {len(n_hyp)} 字")
    print(f"相似度    {ratio:.1%}    {'通过' if ratio >= 0.9 else '需人工核对'}")

    if ratio < 0.99:
        print("\n差异位置（归一化后）:")
        sm = difflib.SequenceMatcher(None, n_ref, n_hyp)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                print(f"  {tag:8} 剧本[{n_ref[i1:i2]!r}]  转写[{n_hyp[j1:j2]!r}]")


if __name__ == "__main__":
    main()
