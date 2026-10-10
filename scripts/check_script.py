#!/usr/bin/env python3
"""剧本校验：把 `验收标准.md` 里的「机器可校验项」跑一遍

用法   python scripts/check_script.py 剧集/EP001/剧本.md [--target-seconds 60]

规则说明
- 同框风险：按**场次**统计**在场**说话人。**画外音/旁白不计入**（本就不在场）。
- 含**闪回**的场次，同框数超标只告警不判失败（闪回天然跨时空）。
- 台词容量：整集可发声字 ≤ 目标秒数 × 4.1。

退出码 0 = 通过；1 = 有硬性失败；2 = 用法错误
"""
import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 对白形如：陈默（冷笑）：台词   —— 也容忍  陈默：台词
# group(1)=说话人  group(2)=括号内的表演/来源提示（如「画外」「闪回」）
SPEAKER = re.compile(r"^([^\s#\[\]（(：:]{1,12})\s*(?:[（(]([^）)]*)[）)])?\s*[：:]")
SCENE = re.compile(r"^##\s+(\S+)")
TAG = re.compile(r"^\[(SFX|VO|OS|画面文字|连续性|转场)\]")
PUNCT = re.compile(r"[\W_]+")
# 不在场的说话人：画外音 / 旁白 / OS / VO
OFFSCREEN = re.compile(r"画外|旁白|OS$|VO$")
# 闪回标记
FLASHBACK = re.compile(r"闪回")


def spoken_chars(s: str) -> str:
    """去掉标点与空白，只留可发声字（与 4.1 字/秒 口径一致）"""
    return PUNCT.sub("", s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("script", type=Path)
    ap.add_argument("--target-seconds", type=float, default=60.0)
    ap.add_argument("--max-speakers", type=int, default=2)
    ap.add_argument("--chars-per-second", type=float, default=4.1)
    args = ap.parse_args()

    if not args.script.exists():
        sys.exit(f"找不到剧本：{args.script}")

    lines = args.script.read_text(encoding="utf-8").splitlines()
    scenes: dict[str, set[str]] = {}
    flashback_scenes: set[str] = set()
    cur = "(无场次)"
    total_spoken = 0
    dialogue_lines = 0
    long_lines: list[int] = []
    has_continuity = False

    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        m = SCENE.match(line)
        if m:
            cur = m.group(1)
            scenes.setdefault(cur, set())
            continue
        if FLASHBACK.search(line):
            flashback_scenes.add(cur)
        if TAG.match(line):
            if line.startswith("[连续性]"):
                has_continuity = True
            continue
        sp = SPEAKER.match(line)
        if sp:
            name = sp.group(1)
            paren = sp.group(2) or ""
            # 画外音/旁白本就不在场，不计入同框
            if not (OFFSCREEN.search(name) or OFFSCREEN.search(paren)):
                scenes.setdefault(cur, set()).add(name)
            body = line[sp.end():]
            dialogue_lines += 1
            total_spoken += len(spoken_chars(body))
            if len(spoken_chars(body)) > 40:
                long_lines.append(i)

    fails, warns = [], []

    # 1) 同框风险（画外音已排除；闪回场次降级为告警）
    for sc, sps in scenes.items():
        if len(sps) > args.max_speakers:
            msg = (f"[同框风险] 场次 {sc} 有 {len(sps)} 个在场说话人"
                   f"（上限 {args.max_speakers}）：{'、'.join(sorted(sps))}")
            if sc in flashback_scenes:
                warns.append(msg + "  ← 该场含闪回，仅告警")
            else:
                fails.append(msg)

    # 2) 台词容量
    budget = args.target_seconds * args.chars_per_second
    if total_spoken > budget:
        warns.append(f"[台词容量] 可发声字 {total_spoken} 超过预算 {budget:.0f}"
                     f"（{args.target_seconds:g}s × {args.chars_per_second}/s）")

    # 3) 连续性标注
    if not has_continuity:
        fails.append("[连续性] 缺少 `[连续性]` 段——下游会丢失可追溯状态")

    # 4) 超长单句（提示，非硬失败）
    if long_lines:
        warns.append(f"[超长台词] {len(long_lines)} 句超过 40 可发声字（建议拆句）："
                     + "；".join(f"L{n}" for n in long_lines))

    print("=" * 56)
    print(f"剧本校验：{args.script}")
    print("=" * 56)
    print(f"  场次         {len(scenes)}")
    print(f"  对白行       {dialogue_lines}")
    print(f"  可发声字     {total_spoken}  (预算 {budget:.0f})")
    print(f"  在场说话人   " + "；".join(f"{k}={len(v)}" for k, v in scenes.items()))
    if flashback_scenes:
        print(f"  含闪回场次   {'、'.join(sorted(flashback_scenes))}")
    print()

    for w in warns:
        print(f"  ⚠️  {w}")
    for f in fails:
        print(f"  ❌  {f}")
    if not warns and not fails:
        print("  ✅  机器可校验项全部通过")

    print()
    print("  ℹ️  「结尾反转」与「钩子强度」无法机器判定 → 必须交 audience-proxy 评分")
    print("=" * 56)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
