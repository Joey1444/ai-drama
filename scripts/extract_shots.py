#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把《09-E1视频提示词.md》抽成机器可读的 shots.json（批量出片的输入）。

用法:
    python scripts/extract_shots.py docs/方案/符/09-E1视频提示词.md -o _validate/batch/shots.json

产出每镜: { id, title, seconds, mode(t2va|ref2va), reference|null, prompt }
- prompt   = 该镜 ```text 代码块里的**整段**（三段或六段），提交时原样灌进 H3 节点
- seconds  = 时长（整数秒），直接喂 t2v-pod.json 的 PrimitiveFloat
- mode     = 由「输入参考图」是否为空决定；ref2va 目前**跑不了**（Pod 无 Ref2VA 权重）

Windows 上 stdout 默认 GBK，中文会乱码，故显式强制 UTF-8。
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

BLOCK = re.compile(r"^### (MOTION-EP001-(\d+)) · (.+?)$", re.M)


def parse(text):
    parts = BLOCK.split(text)
    shots = []
    for i in range(1, len(parts), 4):
        tag, num, title, body = parts[i], parts[i + 1], parts[i + 2], parts[i + 3]

        # 时长不在行首：它在 `- 分镜：… ｜ 时长：**4s**（duration: 4）｜ 模式：…` 这一行里
        m = re.search(r"时长：\*\*(\d+)s\*\*", body)
        if not m:
            raise SystemExit("  %s 缺时长" % tag)
        seconds = int(m.group(1))

        # 「输入参考图」这一行的正文（到行尾）；「无（…）」表示文生
        ref_line = ""
        mr = re.search(r"- 输入参考图：(.*)", body)
        if mr:
            ref_line = mr.group(1).strip()
        is_ref = ref_line and not ref_line.startswith("无")

        ref = None
        if is_ref:
            slot = re.match(r"`?([A-Z0-9\-]+)", ref_line)
            path = re.search(r"·\s*([^\s《]+\.(?:png|jpg|jpeg|webp))", ref_line)
            ref = {"slot": slot.group(1) if slot else None,
                   "path": path.group(1) if path else None,
                   "raw": ref_line}

        code = re.search(r"#### 可复制提示词\s+```text\n(.*?)```", body, re.S)
        if not code:
            raise SystemExit("  %s 缺可复制提示词块" % tag)
        prompt = code.group(1).strip()

        shots.append({"id": tag.replace("MOTION-EP001-", "M"),
                      "order": int(num), "title": title.strip(),
                      "seconds": seconds,
                      "mode": "ref2va" if is_ref else "t2va",
                      "reference": ref, "prompt": prompt})
    return sorted(shots, key=lambda s: s["order"])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    shots = parse(open(sys.argv[1], encoding="utf-8").read())
    out = "_validate/batch/shots.json"
    if "-o" in sys.argv:
        out = sys.argv[sys.argv.index("-o") + 1]

    print("%-5s %-4s %-8s %-6s %s" % ("镜", "秒", "模式", "参考图", "标题"))
    for s in shots:
        print("%-5s %-4s %-8s %-6s %s" % (
            s["id"], s["seconds"], s["mode"],
            "有" if s["reference"] else "—", s["title"]))
    bad = [s["id"] for s in shots if not 4 <= s["seconds"] <= 15]
    print("\n共 %d 镜，合计 %ds%s" % (
        len(shots), sum(s["seconds"] for s in shots),
        "；❌ 越界: %s" % bad if bad else "；H3 区间(4–15s) 全部合法 ✅"))
    print("参考式（需 Ref2VA）: %s" % ([s["id"] for s in shots if s["mode"] == "ref2va"] or "无"))

    with open(out, "w", encoding="utf-8") as fh:
        json.dump(shots, fh, ensure_ascii=False, indent=1)
    print("-> %s" % out)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
