#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""短剧剪辑管线 v3 —— 按电影剪辑逻辑，不是拼接

输入   shots/*.mp4          镜头（任意尺寸/帧率；有无音轨皆可）
       edit.json            剪辑参数（掐头去尾 / 转场表 / 调色 / 声音）
       subs/subtitle.srt    字幕（时间轴按**剪辑后**算 —— 用 scripts/make_srt.py 生成）
       bgm.m4a              背景音乐（可选）
输出   out/final.mp4        1080x1920 竖屏 / -14 LUFS / 烧中文字幕

用法   python build.py [edit.json]

v2 -> v3 改了什么（依据：Walter Murch 剪辑六规则 / StudioBinder 转场指南 / Bordwell ASL）：
  1. **默认硬切**。v2 每两镜之间都 xfade 0.4s —— 专业里这是"业余幻灯片"：
     dissolve 是**标点**，全片只用几次，只有语义变了（时间跳跃/幕结束/情绪重音）才加。
     要加就写进 edit.json 的 transitions 表，**不要全局开**。
  2. **每镜掐头去尾**（in on motion / out on motion）。素材是固定长度，切点被镜头边界粗定，
     但**镜内入出点才是剪辑本体** —— 入点选"动作已起"，出点选"动作到顶"。
  3. **声音独立成轨**：每段音频用 atrim 截、adelay 摆到自己的绝对偏移，再 amix。
     这就是 **J-cut（声先入）/ L-cut（声延续）** 的落地点，也是最"像电影"的一步。
  4. **声音设计**：低频垫紧张段（被感到而非被听到）；结尾前**抽掉全部声音**——最狠的一刀。
  5. **分离调色**：阴影偏青蓝 + 高光偏暖（青橙），而不是笼统"冷青灰"。
  6. 时间轴不再有 xfade 漂移 —— 字幕和成片用的是同一套算术。

Windows 上 stdout 默认 GBK，中文会乱码，故显式强制 UTF-8。
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

W, H = 1080, 1920
AUDIO_SR = 32000
FALLBACK_FPS = 30.0
LUFS, TP, LRA = -14.0, -1.5, 11.0
BGM_GAIN = 0.12
ROOT = Path(__file__).resolve().parent


def probe(p: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,r_frame_rate", "-of", "json", str(p)],
        capture_output=True, text=True, check=True).stdout
    st = json.loads(out).get("streams", [])
    v = next((s for s in st if s["codec_type"] == "video"), None)
    a = next((s for s in st if s["codec_type"] == "audio"), None)
    fps = FALLBACK_FPS
    if v and v.get("r_frame_rate"):
        n, _, d = v["r_frame_rate"].partition("/")
        try:
            fps = float(n) / float(d or 1)
        except (ValueError, ZeroDivisionError):
            pass
    return {"w": (v or {}).get("width"), "h": (v or {}).get("height"),
            "fps": fps, "has_audio": a is not None}


def mean_luma(p: Path, at: float = 0.5) -> float:
    """镜头中段的平均亮度（YAVG，0–255）。用来做跨镜曝光归一。

    为什么需要：T2VA 逐镜独立生成，**每镜的曝光是模型自己掷的**——
    实测同一场景内能差 2 倍（35 → 72）。这是"连贯性差"最主要的形态，
    而且是**后期能修的**（不需要重出、不需要加平台）。
    """
    try:
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", "%.2f" % at, "-i", str(p), "-frames:v", "1",
             "-vf", "signalstats,metadata=print:file=-", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60).stdout
        m = re.search(r"YAVG=([0-9.]+)", out)
        return float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0


def duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(p)], capture_output=True, text=True,
                         check=True).stdout.strip()
    return float(out)


def main() -> None:
    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "edit.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    th, tt = float(cfg.get("trim_head", 0.0)), float(cfg.get("trim_tail", 0.0))
    min_shot = float(cfg.get("min_shot", 1.0))
    trans = {int(k): v for k, v in (cfg.get("transitions") or {}).items()
             if not k.startswith("_")}
    shift = {int(k): float(v) for k, v in (cfg.get("audio_shift") or {}).items()
             if not k.startswith("_")}
    grade = cfg.get("grade") or {}
    lowfreq = cfg.get("lowfreq") or {}
    silence = cfg.get("silence_before") or None

    # 素材目录：默认 shots/，可用环境变量 SHOTS_DIR 覆盖
    # （2026-10-10 修：此前写死 shots/，而 pipeline_edit 把素材放在别处 → 两边对不上、跑不通）
    shots_dir = Path(os.environ.get("SHOTS_DIR") or (ROOT / "shots"))
    if not shots_dir.is_absolute():
        shots_dir = ROOT / shots_dir
    shots = sorted(shots_dir.glob("*.mp4"))
    if not shots:
        sys.exit(f"没有找到素材：{shots_dir}/*.mp4")
    print(f"素材目录：{shots_dir}（{len(shots)} 个）")
    infos = [probe(s) for s in shots]
    raw = [duration(s) for s in shots]
    n = len(shots)
    fps = infos[0]["fps"] or FALLBACK_FPS

    # ---- 0. 逐镜曝光归一（T2VA 每镜曝光是模型自己掷的，同场景能差 2 倍）----
    exposure = cfg.get("exposure") or {}
    gains = [1.0] * n
    if exposure.get("target"):
        tgt = float(exposure["target"])
        keep = set(exposure.get("keep") or [])
        measured = [mean_luma(s) for s in shots]
        for i in range(n):
            if ("M%02d" % (i + 1)) in keep or measured[i] <= 0:
                continue
            gains[i] = min(1.0, tgt / measured[i])      # **只压不提**（本剧压暗风格）
        print("曝光归一  target=%.0f（只压不提）" % tgt)
        for i in range(n):
            flag = ""
            if ("M%02d" % (i + 1)) in keep:
                flag = "  ← 保留（故意暗）"
            print("  shot_%02d  YAVG %5.1f → %5.1f  gain %.3f%s"
                  % (i + 1, measured[i], measured[i] * gains[i], gains[i], flag))

    # ---- 1. 掐头去尾：镜内入出点 ----
    cuts = []
    for i, d in enumerate(raw):
        a = min(th, max(0.0, d - min_shot))
        b = d - min(tt, max(0.0, d - min_shot))
        if b - a < min_shot:
            a, b = 0.0, d
        cuts.append((a, b, b - a))

    # ---- 2. 时间轴 ----
    # ⚠️ 转场**不再占用重叠时长**：dip / fade 就是"前一镜淡出、后一镜淡入"，原地淡。
    #    旧版用 xfade 做，既吃掉时间、又和 concat 混用导致滤镜图绑定失败
    #    （实测：13 镜图直接 "Error binding filtergraph inputs/outputs"）。
    starts, acc = [], 0.0
    for i, (_, _, d) in enumerate(cuts):
        starts.append(acc)
        acc += d
    total = acc

    print("剪辑表  掐头 %.2fs / 掐尾 %.2fs  成片 %.2fs" % (th, tt, total))
    for i, (_, _, d) in enumerate(cuts):
        t = trans.get(i + 1)
        mark = "  [%s %.2fs]" % (t[0], float(t[1])) if t else ""
        print("  shot_%02d  成片 %6.2f–%6.2f  有效 %.2fs (原 %.2fs)%s"
              % (i + 1, starts[i], starts[i] + d, d, raw[i], mark))

    # ---- 3. 视频图：逐段 trim -> 归一 -> 硬切/转场 ----
    fc = []
    for i, (a, b, d) in enumerate(cuts):
        # 转场 = 原地淡：前一镜尾部淡出、后一镜头部淡入（dip-to-black 的本义）
        fade = ""
        if i in trans:                                    # 本镜头部淡入
            fade += ",fade=in:st=0:d=%.3f" % float(trans[i][1])
        if (i + 1) in trans and i < n - 1:                # 本镜尾部淡出
            fd = float(trans[i + 1][1])
            fade += ",fade=out:st=%.3f:d=%.3f" % (max(0.0, d - fd), fd)
        fc.append(f"[{i}:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,"
                  f"fps={fps:g},scale={W}:{H}:force_original_aspect_ratio=increase,"
                  f"crop={W}:{H},setsar=1,"
                  # BT709 归一：AI/异源素材的色彩元数据常常缺省或错配，显式钉死才不偏色。
                  # 做法抄自 MoneyPrinterTurbo（MIT）与 OpenMontage，命令自己写。
                  f"scale=out_color_matrix=bt709:out_range=tv,"
                  f"setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
                  # 曝光归一：乘法缩放亮度，保留色度不动（比加 brightness 好，不会洗黑）
                  f"lutyuv=y=val*{gains[i]:.4f}"
                  f"{fade},"
                  f"format=yuv420p[v{i}]")
    # 一律 concat 硬切 —— 不再和 xfade 混用
    prev = "[v0]"
    for i in range(1, n):
        out_lbl = "[vcat]" if i == n - 1 else f"[vx{i}]"
        fc.append(f"{prev}[v{i}]concat=n=2:v=1:a=0{out_lbl}")
        prev = out_lbl

    # ---- 4. 调色（分离调色：阴影青蓝 + 高光暖）----
    chain = []
    if grade.get("lut3d"):
        chain.append("lut3d=%s" % grade["lut3d"])
    if grade.get("contrast") or grade.get("saturation"):
        chain.append("eq=contrast=%.3f:saturation=%.3f"
                     % (float(grade.get("contrast", 1.0)), float(grade.get("saturation", 1.0))))
    if grade.get("shadows_blue") or grade.get("highlights_red"):
        chain.append("colorbalance=bs=%.3f:rh=%.3f"
                     % (float(grade.get("shadows_blue", 0)), float(grade.get("highlights_red", 0))))
    if grade.get("vibrance"):
        chain.append("vibrance=intensity=%.3f" % float(grade["vibrance"]))
    if grade.get("unsharp"):
        chain.append("unsharp=%s" % grade["unsharp"])
    fc.append("[vcat]%s[vgrade]" % (",".join(chain) if chain else "null"))

    # ---- 5. 字幕 ----
    # ⚠️ **优先用 .ass**：ASS 文件里把 PlayResX/Y 写死（1080x1920），字号才是**真实像素**。
    #    走 `subtitles=…srt:force_style=…` 时 `original_size` 实测**不生效**——
    #    libass 仍按默认 PlayRes(384x288) 换算，FontSize=68 被放大到约 24% 画面高度，字大到出画。
    #    （.ass 由 scripts/make_srt.py 生成，与 .srt 同源同时产出。）
    subs_dir = ROOT / "subs"
    sub_ass = subs_dir / "subtitle.ass"
    sub_srt = subs_dir / "subtitle.srt"
    if sub_ass.exists():
        fc.append("[vgrade]ass=%s[vout]" % sub_ass.name)
    elif sub_srt.exists():
        fc.append("[vgrade]subtitles=%s[vout]" % sub_srt.name)
    else:
        fc.append("[vgrade]null[vout]")

    # ---- 6. 声音：独立成轨 -> J/L 交叠 ----
    # 每段截到有效长度，adelay 摆到「自己的起点 + audio_shift」。这就是 J-cut / L-cut。
    a_labels = []
    for i, (a, b, d) in enumerate(cuts):
        if infos[i]["has_audio"]:
            fc.append(f"[{i}:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
                      f"aformat=sample_fmts=fltp:sample_rates={AUDIO_SR}:"
                      f"channel_layouts=stereo[ai{i}]")
        else:
            fc.append(f"anullsrc=r={AUDIO_SR}:cl=stereo,atrim=0:{d:.3f},"
                      f"asetpts=PTS-STARTPTS[ai{i}]")
        at = max(0.0, starts[i] + shift.get(i + 1, 0.0))
        fc.append(f"[ai{i}]adelay={int(round(at * 1000))}|{int(round(at * 1000))}[ap{i}]")
        a_labels.append(f"[ap{i}]")
    fc.append("%samix=inputs=%d:duration=longest:normalize=0[aflat]"
              % ("".join(a_labels), n))

    # 低频：垫在紧张段（被感到而非被听到）
    if lowfreq.get("ranges"):
        fc.append("sine=frequency=%d:sample_rate=%d:duration=%.3f,"
                  "aformat=channel_layouts=stereo[lf]"
                  % (int(lowfreq.get("freq", 48)), AUDIO_SR, total))
        expr = "+".join("between(t,%.3f,%.3f)" % (float(r[0]), float(r[1]))
                        for r in lowfreq["ranges"])
        fc.append("[lf]volume=enable='%s':volume=%.3f[lfv]" % (expr, float(lowfreq.get("gain", 0.05))))
        fc.append("[aflat][lfv]amix=inputs=2:duration=first:normalize=0[amix1]")
        acur = "[amix1]"
    else:
        acur = "[aflat]"

    # 结尾前抽掉全部声音（最狠的一刀）
    if silence and silence.get("at") is not None:
        at, dur = float(silence["at"]), float(silence.get("duration", 0.3))
        fc.append("%svolume=enable='between(t,%.3f,%.3f)':volume=0[asil]"
                  % (acur, at, at + dur))
        acur = "[asil]"

    if (ROOT / "bgm.m4a").exists():
        # **闪避（ducking）**：用对白当 key 把 BGM 压下去，而不是固定音量——
        # 静场时 BGM 自然浮起，一说话自动让路。比固定 gain 好得多。
        # 做法抄自 OpenMontage 的 audio_mixer._duck（sidechaincompress），代码自己重写。
        # 顺序要紧：sidechaincompress 压缩的是**第一个**输入，所以 BGM 在前、对白当 sidechain；
        # 之后再 amix 对白 + 被压过的 BGM（对白要 asplit 成两份：一份当 key、一份留着混）。
        fc.append("%sasplit=2[aspeech][akey]" % acur)
        fc.append(f"[{n}:a]volume=0.6[abgm]")
        fc.append("[abgm][akey]sidechaincompress=threshold=0.02:ratio=9:"
                  "attack=200:release=500[aduck]")
        fc.append("[aspeech][aduck]amix=inputs=2:duration=first:normalize=0[amixb]")
        acur = "[amixb]"

    fc.append("%sloudnorm=I=%s:TP=%s:LRA=%s,aresample=%d[aout]"
              % (acur, LUFS, TP, LRA, AUDIO_SR))

    (ROOT / "out").mkdir(exist_ok=True)
    # 把滤镜图 dump 出来——出问题时可以单独喂给 ffmpeg 定位是哪一环
    graph = ";\n".join(fc)
    (ROOT / "out" / "graph.txt").write_text(graph, encoding="utf-8")

    cmd = ["ffmpeg", "-y", "-v", "warning", "-stats"]
    for s in shots:
        cmd += ["-i", str(s)]
    if (ROOT / "bgm.m4a").exists():
        # ⚠️ **必须循环**：我们的 BGM 素材只有 30s，成片 54s——
        #    不循环的话后 24 秒完全没有音乐（踩过）。-stream_loop -1 让它铺满，再由 -t 截断。
        cmd += ["-stream_loop", "-1", "-i", str(ROOT / "bgm.m4a")]
    (ROOT / "out").mkdir(exist_ok=True)
    cmd += ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
            "-t", "%.3f" % total,
            "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k", str(ROOT / "out" / "final.mp4")]

    print("\n执行 ffmpeg ...")
    run_cwd = subs_dir if (sub_ass.exists() or sub_srt.exists()) else ROOT
    sys.exit(subprocess.run(cmd, cwd=run_cwd).returncode)


if __name__ == "__main__":
    main()
