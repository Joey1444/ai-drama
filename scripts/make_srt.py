#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从《视频提示词》+《剧本》生成这一集的字幕 SRT —— 时间轴与 build.py **严格同源**。

用法:
    python scripts/make_srt.py "docs/方案/符/09-E1视频提示词.md" \
        --script "docs/方案/符/06-E1剧本-定稿.md" \
        --shots _validate/batch/shots.json \
        --edit  _validate/edit.json \
        --clips _validate/shots \
        -o _validate/subs/subtitle.srt

⚠️ **字幕错位的两个成因，本脚本都堵住了**：
  1. **转场会改时间轴**（v3 已默认全硬切，但 edit.json 里若有 transitions 仍要算进去）
  2. **标称秒数 ≠ 实际时长**。H3 的时长按 17 帧网格取整：请求 4 秒，实际出 **4.459s**。
     所以**必须探测真实文件**，不能拿 shots.json 里的 `seconds` 直接累加 —— 否则 13 镜下来
     能差出好几秒。（`--clips` 指向的目录里没有文件时，才退回标称秒数并告警。）

Windows 上 stdout 默认 GBK，中文会乱码，故显式强制 UTF-8。
"""
import io
import json
import os
import re
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

HEAD_PAD = 0.3       # 镜头内字幕出现前留的余量
TAIL_PAD = 0.2       # 镜头结束前提前消失的余量


def ts(sec: float) -> str:
    """秒 -> SRT 时间戳 HH:MM:SS,mmm"""
    if sec < 0:
        sec = 0.0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return "%02d:%02d:%02d,%03d" % (h, m, int(s), round((s - int(s)) * 1000))


def a_ts(sec: float) -> str:
    """秒 -> ASS 时间戳 H:MM:SS.cc（百分秒）"""
    if sec < 0:
        sec = 0.0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return "%d:%02d:%02d.%02d" % (h, m, int(s), round((s - int(s)) * 100))


def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def probe_duration(path: str):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", path], capture_output=True, text=True,
                             check=True).stdout.strip()
        return float(out)
    except Exception:
        return None


def dialogue_of(prompt: str):
    return [m.strip() for m in re.findall(r"<d>\[Chinese\] (.*?)</d>", prompt, re.S)]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    shots = {s["id"]: s for s in json.load(open(arg("--shots", "_validate/batch/shots.json"),
                                                  encoding="utf-8"))}
    out = arg("-o", "_validate/subs/subtitle.srt")
    clips_dir = arg("--clips", "_validate/shots")
    cfg = {}
    edit_path = arg("--edit", "_validate/edit.json")
    if edit_path and os.path.isfile(edit_path):
        cfg = json.loads(open(edit_path, encoding="utf-8").read())

    th = float(cfg.get("trim_head", 0.0))
    tt = float(cfg.get("trim_tail", 0.0))
    min_shot = float(cfg.get("min_shot", 1.0))
    trans = {int(k): v for k, v in (cfg.get("transitions") or {}).items()
             if not k.startswith("_")}

    # 画面叠字（M01 的钩子标题）——取自剧本的 [画面文字]
    overlay = None
    script = arg("--script")
    if script and os.path.isfile(script):
        txt = open(script, encoding="utf-8").read().replace("**", "")
        m = re.search(r"\[画面文字\]\s*(.+?)\s*$", txt, re.M)
        if m:
            overlay = m.group(1).strip()

    order = sorted(shots.values(), key=lambda s: s["order"])

    # ---- 与 build.py 同源的时长：优先探测真实文件 ----
    rows, fallback = [], False
    for s in order:
        f = os.path.join(clips_dir, "shot_%02d.mp4" % s["order"])
        d_raw = probe_duration(f) if os.path.isfile(f) else None
        if d_raw is None:
            d_raw, fallback = float(s["seconds"]), True
        a = min(th, max(0.0, d_raw - min_shot))
        b = d_raw - min(tt, max(0.0, d_raw - min_shot))
        if b - a < min_shot:
            a, b = 0.0, d_raw
        rows.append([s, a, b, b - a])

    starts, acc = [], 0.0
    for i, (_, _, _, d) in enumerate(rows):
        starts.append(acc)
        acc += d          # 转场是原地淡，不占重叠时长——不减
    total = acc

    cues = []
    for i, (s, a, b, d) in enumerate(rows):
        lines = dialogue_of(s["prompt"])
        if overlay and s["order"] == 1:
            lines = [overlay] + lines
        for ln in lines:
            cues.append((starts[i] + HEAD_PAD,
                         max(starts[i] + HEAD_PAD + 0.6, starts[i] + d - TAIL_PAD), ln))

    if fallback:
        print("⚠️ 有镜头文件缺失，部分时长退回**标称秒数**——字幕可能错位，出片前请重跑")

    with open(out, "w", encoding="utf-8") as fh:
        for i, (a, b, txt) in enumerate(cues, 1):
            fh.write("%d\n%s --> %s\n%s\n\n" % (i, ts(a), ts(b), txt))

    # ---- 同时产一份 ASS：把 PlayResX/Y 写死，字号才是**真实像素** ----
    # 为什么不用 subtitles=...:force_style=：实测 original_size **不生效**，
    # libass 仍按默认 PlayRes(384x288) 换算，FontSize=68 会被放大到 24% 画面高度
    # ——字大到出画。写成 ASS 并显式声明 PlayRes 就没有这个歧义。
    ass = os.path.splitext(out)[0] + ".ass"
    sc = cfg.get("subtitle") or {}
    with open(ass, "w", encoding="utf-8") as fh:
        fh.write(
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
            "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
            "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Default,%s,%d,&H00FFFFFF,&H90000000,&H00000000,0,0,0,0,100,100,0,0,1,%d,1,2,"
            "80,80,%d,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
            "Effect, Text\n"
            % (sc.get("font", "Microsoft YaHei"), int(sc.get("size", 68)),
               int(sc.get("outline", 3)), int(sc.get("margin_v", 240))))
        for a, b, txt in cues:
            fh.write("Dialogue: 0,%s,%s,Default,,0,0,0,,%s\n"
                     % (a_ts(a), a_ts(b), txt.replace("\n", "\\N")))

    print("时间轴（掐头 %.2f / 掐尾 %.2f，成片 %.2fs）" % (th, tt, total))
    for i, (s, a, b, d) in enumerate(rows):
        t = trans.get(i + 1)
        mark = "  [%s %.2fs]" % (t[0], float(t[1])) if t else ""
        print("  %-4s 成片 %6.2f–%6.2f  有效 %.2fs%s"
              % (s["id"], starts[i], starts[i] + d, d, mark))
    print("\n共 %d 条字幕 -> %s" % (len(cues), out))
    if not cues:
        print("⚠️ 一条台词都没抽到——检查提示词里的 <d>[Chinese] …</d>")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
