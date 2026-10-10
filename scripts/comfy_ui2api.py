#!/usr/bin/env python3
"""ComfyUI  UI 格式工作流 -> API 格式（可直接 POST /prompt）

用法: python3 conv.py <workflow.json> [-o out.json]

处理要点：
- 跳过前端虚拟节点（GetNode/SetNode/MarkdownNote/Note/Reroute）
- GetNode 的输出解析为其 SetNode 上游的真实来源（可递归）
- 控件值按 object_info 里控件输入的出现顺序对齐
"""
import json
import sys


def main():
    wf_path = sys.argv[1]
    out_path = None
    if "-o" in sys.argv:
        out_path = sys.argv[sys.argv.index("-o") + 1]

    oi = json.load(open("/tmp/oi.json"))
    d = json.load(open(wf_path))

    nodes = {n["id"]: n for n in d.get("nodes", [])}
    links = {l[0]: l for l in d.get("links", [])}
    # 兼容新版 links 为 dict 的情况
    if isinstance(d.get("links"), dict):
        links = d["links"]

    def link_origin(link_id):
        l = links.get(link_id)
        if not l:
            return None
        return str(l[1]), l[2]

    # SetNode: const 名 -> 其输入 link
    set_map = {}
    for n in d.get("nodes", []):
        if n.get("type") == "SetNode":
            wv = n.get("widgets_values") or []
            name = wv[0] if wv else None
            for inp in (n.get("inputs") or []):
                if inp.get("link") is not None:
                    set_map[name] = inp["link"]
                    break

    VIRTUAL = {"MarkdownNote", "Note", "GetNode", "SetNode", "Reroute",
               "PrimitiveNode", "NotePlus", "ReroutePrimitive"}

    def resolve(link_id, depth=0):
        """返回 [node_id, slot]，遇到 GetNode 继续往上找"""
        if link_id is None or depth > 20:
            return None
        o = link_origin(link_id)
        if not o:
            return None
        nid, slot = o
        n = nodes.get(int(nid))
        if n is None:
            return None
        if n.get("type") == "GetNode":
            wv = n.get("widgets_values") or []
            name = wv[0] if wv else None
            return resolve(set_map.get(name))
        if n.get("type") == "Reroute":
            for inp in (n.get("inputs") or []):
                if inp.get("link") is not None:
                    return resolve(inp["link"], depth + 1)
            return None
        return [nid, slot]

    WIDGET_TYPES = ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO")
    # 只走连线、不出控件的输入类型（其余一律当控件）
    LINK_ONLY = {
        "MODEL", "CLIP", "VAE", "IMAGE", "AUDIO", "LATENT", "MASK",
        "CONDITIONING", "SIGMAS", "SAMPLER", "GUIDER", "NOISE",
        "CONTROL_NET", "INTERPOLATION_STATES", "UPSCALE_MODEL",
        "CLIP_VISION", "STYLE_MODEL", "GLIGEN", "HOOKS", "WEBCAM",
        "POINT", "BBOX", "SEGS", "SAM2MODEL", "DETAILER_PIPE", "LATENT_UPSCALE",
    }

    def widget_specs(spec):
        """[(名字, 选项字典)] —— 按定义顺序，含已连线者。

        关键 1：widgets_values 里，被转成输入的控件**值仍在原位**，不能跳过。
        关键 2：带 `control_after_generate` 的 INT/FLOAT 会**多占一个值槽**（如 'fixed'）。
        """
        out = []
        for group in ("required", "optional"):
            for k, v in (spec.get("input", {}).get(group) or {}).items():
                ty = v[0]
                if isinstance(ty, list) or ty in WIDGET_TYPES or ty not in LINK_ONLY:
                    opts = v[1] if len(v) > 1 and isinstance(v[1], dict) else {}
                    out.append((k, opts))
        return out

    out = {}
    skipped = []
    for n in d.get("nodes", []):
        t = n.get("type")
        if t in VIRTUAL:
            continue
        spec = oi.get(t)
        if not spec:
            skipped.append((n.get("id"), t))
            continue

        specs = widget_specs(spec)
        wv = list(n.get("widgets_values") or [])
        # 少数自定义控件会在**头部**塞描述对象（如 LoraManager），此时从尾部对齐；
        # 其余情况多余的值一般在**尾部**，直接从头映射并丢弃即可。
        if len(wv) > len(specs) and "LoraManager" in t:
            wv = wv[len(wv) - len(specs):]

        inputs = {}
        i = 0
        for nm, opts in specs:
            if i < len(wv):
                inputs[nm] = wv[i]
                i += 1
            if "control_after_generate" in opts and i < len(wv):
                i += 1                  # 跳过伴生槽，不写入
        # 连线覆盖（连线优先）
        for inp in (n.get("inputs") or []):
            nm = inp.get("name")
            if inp.get("link") is not None:
                r = resolve(inp["link"])
                if r is not None:
                    inputs[nm] = r

        out[str(n["id"])] = {"class_type": t, "inputs": inputs,
                             "_meta": {"title": n.get("title", t)}}

    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if out_path:
        open(out_path, "w").write(txt)
        print(f"OK 节点数={len(out)} -> {out_path}")
        if skipped:
            print(" 跳过(无定义):", skipped[:8])
    else:
        print(txt)


if __name__ == "__main__":
    main()
