#!/usr/bin/env python3
"""把 API 格式工作流里的模型文件名，替换成本机实际存在的文件；并把画幅设为 9:16

用法: python3 comfy_patch.py <api_workflow.json> <out_payload.json>
"""
import glob
import json
import os
import sys

M = "/workspace/ComfyUI/models"


def pick(sub, *kw):
    fs = [os.path.basename(p) for p in glob.glob(f"{M}/{sub}/*.safetensors")]
    for k in kw:
        for f in fs:
            if k in f:
                return f
    return fs[0] if fs else None


def main():
    src, dst = sys.argv[1], sys.argv[2]
    api = json.load(open(src))

    diff = pick("diffusion_models", "fl2va")
    clip = pick("text_encoders")
    vae_v = pick("vae", "video_vae_fp16") or pick("vae", "video")
    vae_a = pick("vae", "audio_vae")
    tae = pick("vae_approx")

    print(f"  模型: {diff}\n  文本: {clip}\n  VAE : {vae_v} / {vae_a}\n  tae : {tae}")

    for k, v in api.items():
        ins = v["inputs"]
        for key in ("model_name", "clip_name", "vae_name", "tiny_vae", "ckpt_name"):
            if key in ins and isinstance(ins[key], str) and ins[key].endswith(".safetensors"):
                new = None
                if key == "model_name":
                    new = diff
                elif key == "clip_name":
                    new = clip
                elif key == "vae_name":
                    new = vae_a if "audio" in ins[key] else vae_v
                elif key == "tiny_vae":
                    new = tae
                if new and new != ins[key]:
                    print(f"   改 {k}.{key}: {ins[key][:38]} -> {new[:45]}")
                    ins[key] = new
        if v["class_type"] == "ResolutionSelector" and "aspect_ratio" in ins \
                and isinstance(ins["aspect_ratio"], str):
            if "9:16" not in ins["aspect_ratio"]:
                ins["aspect_ratio"] = "9:16 (Portrait Widescreen)"
                print(f"   改 {k}.aspect_ratio -> 9:16")

    # LoraManager 的 loras 为空时等于直通；但空数组会被 ComfyUI 当成"连线"而报错。
    # 直接摘掉该节点，下游改接它的上游。
    drop = [k for k, v in api.items() if "LoraManager" in v["class_type"]]
    for k in drop:
        ins = api[k]["inputs"]
        src = ins.get("model") or ins.get("MODEL")
        if not src:
            print(f"   ⚠️ {k} LoraManager 无上游，无法摘除，跳过")
            continue
        n = 0
        for kk, vv in api.items():
            for ik, iv in list(vv["inputs"].items()):
                if isinstance(iv, list) and len(iv) == 2 and str(iv[0]) == k:
                    if iv[1] == 0:
                        vv["inputs"][ik] = src
                        n += 1
                    else:
                        print(f"   ⚠️ {kk}.{ik} 用到 {k} 的 slot {iv[1]}，未 rewiring")
        del api[k]
        print(f"   摘除 {k} LoraManager（直通），改写下游 {n} 处引用")

    json.dump({"prompt": api, "client_id": "cli"}, open(dst, "w"))
    print(f"  已写 {dst}")


if __name__ == "__main__":
    main()
