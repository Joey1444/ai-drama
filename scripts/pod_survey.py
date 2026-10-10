#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pod 上 H3 资产与工作流的系统侦察。在 Pod 内跑：python3 survey.py"""
import json, glob, os

INTEREST = ("Lora", "Sampler", "Guider", "Sigma", "Scheduler", "Primitive",
            "Load", "Resolution", "MiniMaxH3", "VAE", "Text", "Save", "Image")

def dump(path):
    print("=" * 72)
    print(os.path.basename(path))
    try:
        d = json.load(open(path))
    except Exception as e:
        print("  无法解析:", e); return
    nodes = {n.get("id"): n for n in d.get("nodes", [])}
    links = {l[0]: l for l in d.get("links", [])}
    for nid in sorted([k for k in nodes if isinstance(k, int)]):
        n = nodes[nid]
        t = n.get("type", "")
        if not any(k in t for k in INTEREST):
            continue
        wv = str(n.get("widgets_values"))
        print("  %4s %-34s %s" % (nid, t, wv[:60]))
        for i in (n.get("inputs") or []):
            l = links.get(i.get("link"))
            if l:
                src = nodes.get(l[1], {})
                print("       %s <- %s(%s)" % (i.get("name"), l[1], src.get("type")))

print("### /workspace/*.json 工作流 ###")
for f in sorted(glob.glob("/workspace/*.json")):
    if any(k in os.path.basename(f) for k in ("pod", "r2v", "h3", "video", "workflow")):
        dump(f)

print("\n### 模型清单 ###")
for sub in ("diffusion_models", "loras", "hyperflow", "vae", "text_encoders",
            "checkpoints", "unet", "pdd_acc"):
    p = "/workspace/ComfyUI/models/" + sub
    if os.path.isdir(p):
        files = [f for f in os.listdir(p) if f.endswith((".safetensors", ".gguf", ".ckpt"))]
        if files:
            print("  %s:" % sub)
            for f in sorted(files):
                sz = os.path.getsize(os.path.join(p, f)) / 1e9
                print("     %-58s %.1fG" % (f, sz))
