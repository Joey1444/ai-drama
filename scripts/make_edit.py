#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从《分镜表》自动推导剪辑参数 edit.json —— 剪辑感不靠手写，靠分镜。

用法:
    python scripts/make_edit.py "docs/方案/符/08-E1分镜.md" -o _validate/edit.json

**为什么要有这个脚本**：`6-剪辑合成字幕.md` 里写着「剪辑感无法自动化」——**那条的前提是
"从原始素材里剪"**（素材没有既定用途，留哪段靠审美）。但我们是**先有分镜、后有镜头**：
分镜里已经把剪辑决策写死了。所以剪辑感 = 分镜的既定参数，可以自动推导。

映射规则（分镜字段 -> 剪辑参数）：

| 分镜里的 | 推导出 |
|---|---|
| `## 场景N` 的分节 | **场景边界处给一次 dip-to-black**（其余全硬切——专业默认） |
| 每镜「时长」 | 时间轴与 ASL |
| 「声音」列含 **低频/轰鸣** | `lowfreq.ranges`（低频垫底区间，"被感到而非被听到"） |
| 画面/声音里的 **「画外」** 标注 | `audio_shift` 负值 = **J-cut（声先入）** |
| 「声音」列有台词 + 是**最后一镜** | `silence_before`（威胁出口前抽掉全部声音——最狠的一刀） |
| 「风险」列非「低」 | `trim_tail` 收紧（有风险的动作镜早点切走） |

Windows 上 stdout 默认 GBK，中文会乱码，故显式强制 UTF-8。
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

J_CUT = 0.5           # J-cut：声先入提前多少秒
SILENCE = 0.35        # 结尾威胁前抽掉多长的声音
DIP = 0.12            # 场景转换的黑场时长
LOWFREQ_WORDS = ("低频", "轰鸣", "轰")
# ⚠️ 「画外」在分镜里有两个完全不同的意思，裸匹配会误判：
#    ① 画外**音**（声音来自画面外）→ 该给 J-cut   ← 要的是这个
#    ② 「视线停在画**外**」（看向镜头外）→ 与声音无关
#    所以必须要求它后面跟的是"声音类"的字（：音贴传来…），不能只认这两个字。
OFFSCREEN_RE = re.compile(r"画外(?=[：:音贴传来说喊叫])")
CLIPS_DIR = "_validate/shots"     # 用于探测真实时长（标称秒数不可靠）


def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def probe_duration(path: str):
    """真实文件时长。H3 按 17 帧网格取整：请求 4s 实出 4.459s，累加会差出好几秒。"""
    try:
        import subprocess
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", path], capture_output=True, text=True,
                             check=True).stdout.strip()
        return float(out)
    except Exception:
        return None


def parse_storyboard(path: str):
    """解析分镜表 -> [(镜, 场景号, 时长, 景别, 画面, 声音, 风险)]，按镜序"""
    rows, scene = [], 0
    for line in open(path, encoding="utf-8"):
        if re.match(r"^##\s+.*场景", line):          # 「## 二、场景一 · …」
            scene += 1
            continue
        c = [x.strip() for x in line.split("|")]
        if len(c) >= 8 and re.fullmatch(r"\*\*M\d+\*\*", c[1]):
            mid = c[1].strip("*")
            m = re.match(r"(\d+)s", c[2])
            if not m:
                continue
            rows.append({"id": mid, "order": int(mid[1:]), "scene": scene,
                         "seconds": int(m.group(1)), "size": c[3],
                         "picture": c[4], "sound": c[5], "risk": c[7]})
    return rows


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    out = arg("-o", "_validate/edit.json")
    rows = parse_storyboard(src)
    if not rows:
        sys.exit("没解析到镜头行——检查分镜表的表格格式")

    # ---- 真实时长（优先探测文件；缺文件才退回标称并告警）----
    th, tt = 0.4, 0.4
    clips_dir = arg("--clips", CLIPS_DIR)
    import os
    fallback = False
    for r in rows:
        f = os.path.join(clips_dir, "shot_%02d.mp4" % r["order"])
        d = probe_duration(f) if os.path.isfile(f) else None
        if d is None:
            d, fallback = float(r["seconds"]), True
        r["raw"] = d
        r["trim"] = max(1.0, d - th - tt)
    if fallback:
        print("⚠️ 有镜头文件缺失，部分时长退回**标称秒数**——时间轴会偏，出片前请重跑")

    # ---- 场景边界 -> dip ----
    transitions = {}
    for i, r in enumerate(rows):
        if i > 0 and r["scene"] != rows[i - 1]["scene"]:
            transitions[str(i + 1)] = ["dip", DIP]

    # ---- 画外音 -> J-cut（该镜声音提前）----
    audio_shift = {}
    for i, r in enumerate(rows):
        if not OFFSCREEN_RE.search(r["picture"] + r["sound"]):
            continue
        # ⚠️ **前一镜有台词时不能 J-cut**：声先入会把这一镜的人声压到上一镜尾巴上，
        #    两句人声就叠在一起了（实测踩过：M04 的「笔呢？」压到 M03 老墨的遗言上）。
        #    J-cut 只该压在**没台词的镜尾**（环境音/静场）上。
        if i > 0 and "台词" in rows[i - 1]["sound"]:
            continue
        audio_shift[str(i + 1)] = -J_CUT

    # ---- 风险镜 ----
    risky = [r["id"] for r in rows if r["risk"] and "低" not in r["risk"]]

    # ---- 结尾威胁前抽声音 ----
    # 注意：dip/fade 是**原地淡**（前一镜淡出、后一镜淡入），**不占重叠时长** —— 不减法。
    acc = 0.0
    for r in rows[:-1]:
        acc += r["trim"]
    silence = {"at": round(max(0.0, acc - SILENCE), 2), "duration": SILENCE}

    cfg = {
        "_generated_by": "scripts/make_edit.py  <- %s（**别手改，改分镜**）" % src,
        "xfade": 0,
        "_xfade_note": "0 = 全片硬切（专业默认，diegetic 标点是例外）。只在场景边界给一次 dip。",
        "trim_head": th,
        "trim_tail": tt,
        "_trim_note": "每镜掐头去尾。风险镜已列出，若成片动作被切掉，可对单镜调小。",
        "min_shot": 1.0,
        "risky_shots": risky,
        "transitions": transitions,
        "_transitions_note": "由分镜的「## 场景N」分节自动推导：只在场景边界给 dip。",
        "audio_shift": audio_shift,
        "_audio_shift_note": "由分镜里的「画外音」标注推导（注意：只有『画外：/画外音/画外贴…』才算，『视线停在画外』不算）：该镜声音提前 0.5s = J-cut。",
        "silence_before": silence,
        "subtitle": {
            "font": "Microsoft YaHei", "size": 68, "margin_v": 240, "outline": 3,
            "_note": "size / margin_v 是**真实像素**（build.py 会传 original_size=1080x1920，"
                     "不传的话 ASS 按默认 384x288 算，字会巨大且位置飘到画面中部）。"
                     "⚠️ **margin_v 不要超过 260**——实测 300 时 libass 会整条字幕都不画（静默失败）。"
                     "⚠️ 也不要加 Alignment，实测会一起坏掉。",
        },
        "grade": {"lut3d": "", "contrast": 1.08, "saturation": 0.92,
                  "shadows_blue": 0.06, "highlights_red": 0.04,
                  "vibrance": 0.08, "unsharp": "5:5:0.6"},
        "exposure": {
            "target": 46,
            "_note": "逐镜把平均亮度拉向 target，**只压不提**（本剧是压暗风格）。"
                     "keep = 故意暗、不动的镜（首尾威胁镜）。"
                     "为什么需要：T2VA 每镜曝光是模型自己掷的，实测同场景能差 2 倍（35→72）。",
            "keep": [rows[-1]["id"]],
        },
        "lowfreq": {"ranges": [], "freq": 48, "gain": 0.055},
    }

    # ---- 低频区间：由「声音」列里的低频/轰鸣推导 ----
    acc, ranges = 0.0, []
    for r in rows:
        d = r["trim"]
        if any(w in r["sound"] for w in LOWFREQ_WORDS):
            ranges.append([round(acc, 2), round(acc + d, 2)])
        acc += d
    cfg["lowfreq"]["ranges"] = ranges
    cfg["_lowfreq_note"] = "由分镜「声音」列里的「低频/轰鸣」自动推导。"

    json.dump(cfg, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("从分镜推导出剪辑参数（%d 镜，共 %d 个场景）" % (len(rows), rows[-1]["scene"]))
    print("  场景边界 -> dip : %s" % (transitions or "无"))
    print("  画外 -> J-cut   : %s" % (audio_shift or "无"))
    print("  低频垫底区间    : %s" % ranges)
    print("  结尾抽声音      : at %.2fs 持续 %.2fs" % (silence["at"], silence["duration"]))
    print("  风险镜（出点收紧）: %s" % (risky or "无"))
    print("  -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
