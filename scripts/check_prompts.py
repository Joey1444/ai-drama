#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验短剧视频提示词是否合 MiniMax H3 官方规范 + 与剧本一致。

用法:
    python scripts/check_prompts.py docs/方案/符/09-E1视频提示词.md docs/方案/符/06-E1剧本-定稿.md

检查项:
    1. <d>[Chinese] ...</d> 里的台词逐字来自剧本（不翻译不改写）
    2. 每个可复制正文块有 [Shot 1] + 风格声明（T2VA）
    3. 有运镜的自然英文句（motion type + amplitude + speed）
    4. 画外音用固定句式 says in an off-screen voiceover
    5. full-reference 有六段结构 + summary 方括号任务类型
    6. 可复制块内除台词外无中文（正文必须英文）
    7. 每块声明不生成字幕/画内文字

Windows 上 stdin/stdout 默认 GBK，中文路径与中文内容会乱码，故显式强制 UTF-8。
"""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

FIELDS = (
    "integrated_multimodal_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
)
REF_FIELDS = (
    "subject_definitions:",
    "summary:",
    "retention_analysis:",
    "detailed_description:",
)


def load(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def strip_bold(text):
    return text.replace("**", "")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    prompts, script = load(sys.argv[1]), strip_bold(load(sys.argv[2]))
    blocks = re.findall(r"```text\n(.*?)```", prompts, re.S)

    failures = []

    # 1. 台词逐字
    lines = re.findall(r"<d>\[Chinese\] (.*?)</d>", prompts)
    print("台词逐字核对（共 %d 句）" % len(lines))
    for line in lines:
        ok = line in script
        print("  %s %s" % ("OK  " if ok else "FAIL", line))
        if not ok:
            failures.append("台词不在剧本里: %s" % line)

    # 2-7. 逐块
    mot = re.findall(r"^### (MOTION-EP001-\d+)", prompts, re.M)
    print("\n可复制正文块 %d 个（MOTION 标题 %d 个）" % (len(blocks), len(mot)))

    for idx, body in enumerate(blocks, 1):
        tag = "块%d" % idx
        is_ref = "detailed_description:" in body
        if is_ref:
            for field in REF_FIELDS + ("overall_soundscape:", "non_diegetic_music:"):
                if field not in body:
                    failures.append("%s 六段缺 %s" % (tag, field))
            if not re.search(r"^summary:\n\[[a-z ]+\]", body, re.M):
                failures.append("%s summary 缺方括号任务类型" % tag)
            # full-reference 的风格句写在 [Shot 1] 之前
            if "[Shot 1]" not in body:
                failures.append("%s 缺 [Shot 1]" % tag)
        else:
            for field in FIELDS:
                if field not in body:
                    failures.append("%s 三段缺 %s" % (tag, field))
            if not re.search(r"\[Shot 1\] Live-action, cinematic", body):
                failures.append("%s 缺 [Shot 1] 风格声明" % tag)

        if not re.search(
            r"[Tt]he camera (holds a static shot|pushes in|pulls out|pans|trucks|tilts|tracks)",
            body,
        ):
            failures.append("%s 缺运镜自然句" % tag)

        if "off-screen voiceover" in body and "lips" not in body:
            failures.append("%s 有画外音但没写嘴唇闭合" % tag)

        if not re.search(r"[Nn]o captions, subtitles", body):
            failures.append("%s 缺「不生成字幕/画内文字」声明" % tag)

        leftover = re.sub(r"<d>\[Chinese\].*?</d>", "", body, flags=re.S)
        if re.search(r"[一-鿿]", leftover):
            failures.append("%s 正文残留中文（正文必须英文）" % tag)

        if not re.search(r"non_diegetic_music: (N/A|.+)", body):
            failures.append("%s 缺 non_diegetic_music" % tag)

    print("\n问题 %d 条" % len(failures))
    for item in failures:
        print("  FAIL " + item)
    if not failures:
        print("  全部通过")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
