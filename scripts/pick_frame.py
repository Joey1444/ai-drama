#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 H3 定妆镜产物里挑一帧当参考图（本机 ffmpeg，$0）。

为什么要挑：定妆帧要喂给 M02/M08 当「身份」参考图，必须是**正脸 + 闭嘴 + 光照均匀**的那一帧。
H3 出的是 4 秒视频，里面人会呼吸、会眨眼，所以得肉眼挑一帧，不能盲抽
（方法论 §7.2 / §3-A5：别抽说话帧，会把这个错误咬进后续所有镜头）。

用法:
    # 第一步：出候选接触表（4x4 网格，每格左上角是时间戳）
    python scripts/pick_frame.py 陈默定妆镜.mp4
    #   → 落到 _validate/frames/sheet.png，看图选一帧，记下它的时间戳

    # 第二步：把选中的那帧导成参考图
    python scripts/pick_frame.py 陈默定妆镜.mp4 --pick 2.75 --out 输入/参考图/陈默定妆.png

Windows 上 stdout 默认 GBK，中文路径会乱码，故显式强制 UTF-8。
"""
import io
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# ffmpeg 滤镜图里盘的冒号必须转义成 \:，否则 'C:/...' 会被当成选项分隔符
FONT = r"C\:/Windows/Fonts/arial.ttf"
GRID = 4          # 4x4 = 16 格
SAMPLE_FPS = 4    # 采样密度；4 秒的片子 → 16 帧，正好铺满网格


def run(args):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", path]).stdout.strip()
    try:
        return float(out)
    except ValueError:
        sys.exit("读不到时长，确认文件是视频、且 ffprobe 在 PATH 里：%s" % path)


def make_sheet(src):
    os.makedirs("_validate/frames", exist_ok=True)
    out = "_validate/frames/sheet.png"
    # 实测：Windows 上必须同时加单引号和转义，少一个都会报 "No option name near"
    label = ("drawtext=fontfile='%s':text='%%{pts\\:hms}':x=6:y=6:fontsize=20:"
             "fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=4" % FONT)
    vf = ("fps=%d,scale=240:426,%s,tile=%dx%d" % (SAMPLE_FPS, label, GRID, GRID))
    res = run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vf", vf, "-frames:v", "1", out])
    if res.returncode != 0:
        sys.exit("出接触表失败：\n" + res.stderr.strip())
    dur = probe_duration(src)
    print("接触表 -> %s" % out)
    print("  每格 = 0.25 秒（采样 %d fps），左上角是时间戳，按行从左到右、从上到下排列。" % SAMPLE_FPS)
    print("  片长 %.2fs，共约 %d 帧。" % (dur, int(dur * SAMPLE_FPS) + 1))
    print("\n挑标准（缺一不可）：① 正脸、五官清晰  ② 嘴唇闭合  ③ 光照均匀、无强烈侧光")
    print("                    ④ 画面里没有第二个人  ⑤ 不糊、不畸变")
    print("\n选好后：python scripts/pick_frame.py %s --pick <时间戳> --out 输入/参考图/陈默定妆.png" % src)


def pick(src, ts, out):
    d = os.path.dirname(os.path.abspath(out))
    os.makedirs(d, exist_ok=True)
    res = run(["ffmpeg", "-y", "-v", "error", "-i", src, "-ss", ts, "-frames:v", "1", out])
    if res.returncode != 0:
        sys.exit("导帧失败：\n" + res.stderr.strip())
    size = os.path.getsize(out)
    print("已导出 -> %s  (%.0f KB, 时间戳 %ss)" % (out, size / 1024.0, ts))
    print("\n下一步：把 09-E1视频提示词.md 的挂图计划里 PLAN-CHENMO-SHEET 改成 REF-CHENMO-SHEET，")
    print("        写上这个路径，M02 / M08 就能提交了。")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    if not os.path.isfile(src):
        sys.exit("找不到文件：%s" % src)
    if "--pick" in sys.argv:
        ts = sys.argv[sys.argv.index("--pick") + 1]
        out = "输入/参考图/陈默定妆.png"
        if "--out" in sys.argv:
            out = sys.argv[sys.argv.index("--out") + 1]
        pick(src, ts, out)
    else:
        make_sheet(src)
    return 0


if __name__ == "__main__":
    sys.exit(main())
