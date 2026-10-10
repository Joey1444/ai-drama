#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T2I 出图工具（OpenRouter 独立图片接口）

为什么要有它：Pod 上没有 T2I 模型，但 **OpenRouter 有独立图片接口**
（`POST /api/v1/images`，**不是对话接口**——cc-switch 的模型列表里没有图片模型，别去那找）。
免费模型会变，所以**模型可切换**，不写死。

用法:
    python scripts/t2i.py --list                          # 列出可用图片模型（含是否免费）
    python scripts/t2i.py --prompt "..." -o out.png       # 用默认模型出图
    python scripts/t2i.py --model <id> --prompt "..." -o out.png
    T2I_MODEL=<id> python scripts/t2i.py --prompt "..."   # 用环境变量临时切换

凭据: `~/.claude/token.txt` 的 `OpenRouter=` 行（不进代码/仓库）

⚠️ 免责：出图**按模型计费**（免费模型为 $0）。本工具不改变计费语义，只是转发请求。
"""
import argparse
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

API = "https://openrouter.ai/api/v1/images"
MODELS_API = "https://openrouter.ai/api/v1/models"

# 默认模型（免费、实测可用）。想换 → --model 或 T2I_MODEL 环境变量
DEFAULT_MODEL = "inclusionai/ming-image-0.1-design"
TOKEN_FILE = Path.home() / ".claude" / "token.txt"


def get_key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if k:
        return k
    if TOKEN_FILE.exists():
        for line in TOKEN_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("OpenRouter="):
                return line.split("=", 1)[1].strip()
    sys.exit("❌ 找不到 OpenRouter key（放 ~/.claude/token.txt 的 OpenRouter= 行，或设 OPENROUTER_API_KEY）")


def model_price(p: dict):
    """取该模型出图的**真实单价**（美元/次或/单位）。

    ⚠️ 2026-10-10 踩过：只看 `prompt`/`completion`/`image` 会得到 0，
    误判成"免费"——**真实计费在 `image_output` / `image_token`**。
    例：seedream-5-0-flash 的 prompt/completion/image 都是 0，
    但 image_token = 0.0000043（收费）；只有**全部字段为 0** 才是真免费。
    """
    if not p:
        return None, False
    vals = []
    for v in p.values():
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            pass
    if not vals:
        return None, False
    free = all(v == 0 for v in vals)
    # 出图相关字段优先，没有则取所有非零里的最小
    keyed = [float(p[k]) for k in ("image_output", "image_token", "image") if k in p and _isnum(p[k])]
    price = min([v for v in keyed if v > 0], default=None)
    if price is None:
        nz = [v for v in vals if v > 0]
        price = min(nz) if nz else 0.0
    return price, free


def _isnum(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def list_image_models(key: str) -> list:
    """列可用图片模型。

    ⚠️ 必须带 `?output_modalities=image`——不带过滤时只返回「输出含文本」的模型（12 个），
    会漏掉绝大多数纯出图模型（实测带过滤 61 个）。
    """
    url = MODELS_API + "?output_modalities=image"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    out = []
    for m in d.get("data", []):
        arch = m.get("architecture") or {}
        if "image" not in str(arch.get("output_modalities", [])):
            continue
        price, free = model_price(m.get("pricing") or {})
        out.append({"id": m.get("id"), "free": free, "price": price})
    return out


def generate(key: str, model: str, prompt: str, out: Path, timeout: int = 240) -> None:
    body = json.dumps({"model": model, "prompt": prompt}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=timeout))
    except urllib.error.HTTPError as e:
        sys.exit(f"❌ HTTP {e.code}: {e.read().decode(errors='ignore')[:400]}")
    except Exception as e:
        sys.exit(f"❌ {type(e).__name__}: {e}")

    data = r.get("data") or []
    if not data:
        sys.exit(f"❌ 响应无 data：{json.dumps(r, ensure_ascii=False)[:400]}")
    item = data[0]
    if item.get("b64_json"):
        raw = base64.b64decode(item["b64_json"])
    elif item.get("url"):
        raw = urllib.request.urlopen(item["url"], timeout=timeout).read()
    else:
        sys.exit(f"❌ 既无 b64_json 也无 url：{list(item.keys())}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    print(f"✅ {model}  →  {out}  ({len(raw)/1024:.0f} KB)")
    if r.get("usage"):
        print(f"   usage: {json.dumps(r['usage'], ensure_ascii=False)}")


def main():
    ap = argparse.ArgumentParser(description="T2I 出图（OpenRouter 图片接口，模型可切换）")
    ap.add_argument("--list", action="store_true", help="列出可用图片模型")
    ap.add_argument("--model", default=os.environ.get("T2I_MODEL", DEFAULT_MODEL))
    ap.add_argument("--prompt")
    ap.add_argument("--prompt-file", help="从文件读提示词（中文/长文本建议用这个）")
    ap.add_argument("-o", "--out", default="_validate/t2i/out.png")
    args = ap.parse_args()

    key = get_key()

    if args.list:
        ms = list_image_models(key)
        free = [m for m in ms if m["free"]]
        print(f"可用图片模型 {len(ms)} 个（其中免费 {len(free)} 个）：\n")
        for m in ms:
            tag = "🆓 免费" if m["free"] else f"  {m.get('price') or '?'}"
            print(f"  {tag:<12} {m['id']}")
        print(f"\n当前默认：{DEFAULT_MODEL}")
        print("切换：--model <id>  或  T2I_MODEL=<id>  或改本文件 DEFAULT_MODEL")
        return

    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
    if not prompt:
        sys.exit("❌ 需要 --prompt 或 --prompt-file（先用 --list 看模型）")

    generate(key, args.model, prompt, Path(args.out))


if __name__ == "__main__":
    main()
