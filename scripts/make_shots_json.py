#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从《视频提示词.md》解析出 shots.json（送发用的镜头清单）。

为什么要有这个脚本：shots.json 是送发的中间件，手工维护必然与提示词漂移。
本脚本**以提示词为唯一真相**，每次从 md 重新生成。

解析的真实格式（实测）：
    ### MOTION-EP001-01 · 血手撑墙
    - 分镜：`08-E1分镜.md` M01 ｜ 时长：**4s**（`duration: 4`）｜ 模式：**Ref2VA**
    - 输入参考图：REF-...（顺序：1）· 输入/参考图/xxx.png《...》（用途：...）；REF-...（顺序：2）· ...
    #### 可复制提示词
    ```text
    <正文>
    ```

用法：
    python scripts/make_shots_json.py <视频提示词.md> -o _validate/batch/shots.json
"""
import io
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def parse(md_path: Path):
    t = md_path.read_text(encoding="utf-8")
    # 按 ### MOTION-EP001-NN · 切块
    parts = re.split(r'^### MOTION-EP001-(\d+)\s*·\s*', t, flags=re.M)[1:]
    shots = []
    for num, body in zip(parts[0::2], parts[1::2]):
        sid = f"M{int(num):02d}"

        dur = re.search(r'时长[：:]\s*\*\*(\d+)\s*s\*\*', body)
        seconds = int(dur.group(1)) if dur else 5

        mode = re.search(r'模式[：:]\s*\*\*([A-Za-z0-9]+)', body)
        mode = (mode.group(1) if mode else "T2VA").lower()      # ref2va / t2va

        # 输入参考图：抓所有 `输入/参考图/<file>.png`
        refs = re.findall(r'输入/参考图/([A-Za-z0-9_.\-]+\.png)', body)
        # 去重保序
        seen, uniq = set(), []
        for r in refs:
            if r not in seen:
                seen.add(r); uniq.append(r)

        pm = re.search(r'####\s*可复制提示词\s*\n+```text\n(.*?)\n```', body, re.S)
        if not pm:
            print(f"  ⚠️ {sid} 找不到「可复制提示词」块，跳过", file=sys.stderr)
            continue

        shots.append({
            "id": sid,
            "order": int(num),
            "seconds": seconds,
            "mode": mode,
            "reference":  {"path": uniq[0]} if len(uniq) >= 1 else None,
            "reference2": {"path": uniq[1]} if len(uniq) >= 2 else None,
            "prompt": pm.group(1).strip(),
        })
    return shots


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    md = Path(sys.argv[1])
    out = Path(sys.argv[sys.argv.index("-o") + 1]) if "-o" in sys.argv else Path("_validate/batch/shots.json")
    if not md.exists():
        sys.exit(f"❌ 找不到 {md}")

    shots = parse(md)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(shots, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"解析 {len(shots)} 镜 -> {out}")
    total = 0
    for s in shots:
        r1 = (s["reference"] or {}).get("path", "—")
        r2 = (s["reference2"] or {}).get("path", "—")
        total += s["seconds"]
        print(f"  {s['id']}  {s['seconds']}s  {s['mode']:<7} ref={r1:<22} ref2={r2:<22} {len(s['prompt'])}字")
    print(f"\n总时长 {total}s")


if __name__ == "__main__":
    main()
