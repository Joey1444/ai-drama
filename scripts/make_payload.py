#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 shots.json 取一镜，改好工作流（UI 格式），产出可直接喂 comfy_ui2api.py 的文件。

用法:
    python scripts/make_payload.py --shot M01 --out /tmp/wf_M01.json
    python scripts/make_payload.py --shots _validate/batch/shots.json --workflow-dir _validate/batch \
        --shot M01 --out /tmp/wf_M01.json [--ref-image chenmo.png]

按 mode 自动选工作流：
    t2va  -> t2v-pod.json                  （模板自带）
    ref2va-> video_minimax_h3_r2v.json     （官方 workflow_templates）

节点映射（**已按真实文件读出**，两套不一样，别混）：
    t2v:  提示词=132[0] · 时长=134[0] · 尺寸=172[0]
    r2v:  提示词=138[0] · 时长=132[0] · 尺寸=115[0] · 参考图=137[0]

输出仍是 **UI 格式**——下一步在 Pod 内跑：
    python3 comfy_ui2api.py /tmp/wf_M01.json -o /tmp/api_M01.json
    python3 comfy_patch.py   /tmp/api_M01.json  /tmp/payload_M01.json
    curl ... -X POST --data-binary @/tmp/payload_M01.json .../prompt

Windows 上 stdout 默认 GBK，中文会乱码，故显式强制 UTF-8。
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

ASPECT = "9:16 (Portrait Widescreen)"
MEGAPIXELS = 1.05

# mode -> (工作流文件名, 提示词节点, 时长节点, 尺寸节点, 参考图节点, 第二参考图节点)
# 注：r2v 的「时长」节点是 132（PrimitiveFloat），经 131 ComfyMathExpression 换算成帧后喂 136.length
#     —— 不是看起来更像的 131。改错节点会静默无效。
ROUTES = {
    "t2va":   ("t2v-pod.json",              132, 134, 172, None, None),
    "ref2va": ("video_minimax_h3_r2v.json", 138, 132, 115, 137, 139),
}


def arg(flag, default=None):
    if flag in sys.argv:
        return sys.argv[sys.argv.index(flag) + 1]
    return default


def main():
    shots_path = arg("--shots", "_validate/batch/shots.json")
    wf_dir = arg("--workflow-dir", "_validate/batch")
    shot_id = arg("--shot")
    out = arg("--out")
    ref_image = arg("--ref-image")
    ref_image2 = arg("--ref-image2")
    if not shot_id or not out:
        print(__doc__)
        return 2

    shots = {s["id"]: s for s in json.load(open(shots_path, encoding="utf-8"))}
    if shot_id not in shots:
        sys.exit("shots.json 里没有 %s" % shot_id)
    s = shots[shot_id]

    wf_name, n_prompt, n_dur, n_res, n_ref, n_ref2 = ROUTES[s["mode"]]
    wf_path = os.path.join(wf_dir, wf_name)
    if not os.path.isfile(wf_path):
        sys.exit("缺工作流 %s（t2v 的从 Pod 里取，r2v 的从 Comfy-Org/workflow_templates 下）" % wf_path)

    d = json.load(open(wf_path, encoding="utf-8"))
    nodes = {n.get("id"): n for n in d.get("nodes", [])}

    def wv(nid):
        if nid not in nodes:
            sys.exit("工作流 %s 里没有节点 %s" % (wf_name, nid))
        n = nodes[nid]
        if n.get("widgets_values") is None:
            n["widgets_values"] = []
        return n["widgets_values"]

    # 提示词
    v = wv(n_prompt)
    while len(v) < 1:
        v.append("")
    v[0] = s["prompt"]
    # 时长（秒）
    v = wv(n_dur)
    while len(v) < 1:
        v.append(0)
    v[0] = s["seconds"]
    # 尺寸
    v = wv(n_res)
    while len(v) < 3:
        v.append(0)
    v[0], v[1] = ASPECT, MEGAPIXELS

    # 参考式：挂参考图（两个槽位 = 身份 + 场景/第二身份）
    if n_ref is not None:
        img1 = ref_image or (s["reference"] or {}).get("path")
        if not img1:
            sys.exit("%s 是参考式，但 shots.json 里没有参考图路径，也没给 --ref-image" % shot_id)
        # 第二参考：显式给了就用（`--ref-image2` 或 shots.json 的 reference2）；
        # 没给则复用第一张——**保持旧行为**：139 仍指向模板自带的 mecha_dragon_lightning.png
        # 而 Pod 的 input/ 里没有它，必失败。
        img2 = ref_image2 or (s.get("reference2") or {}).get("path") or img1
        for nid, path in ((n_ref, img1), (n_ref2, img2)):
            if nid is None:
                continue
            v = wv(nid)
            while len(v) < 2:
                v.append("")
            v[0] = os.path.basename(path)

    json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("%s  模式=%s  工作流=%s" % (shot_id, s["mode"], wf_name))
    print("  时长 %ds  -> 节点 %s" % (s["seconds"], n_dur))
    print("  尺寸 %s @ %.2fMP -> 节点 %s" % (ASPECT, MEGAPIXELS, n_res))
    print("  提示词 %d 字 -> 节点 %s（前 70 字：%s…）" % (len(s["prompt"]), n_prompt, s["prompt"][:70]))
    if n_ref is not None:
        img1 = ref_image or s["reference"]["path"]
        img2 = ref_image2 or (s.get("reference2") or {}).get("path") or img1
        print("  参考图1 %s -> 节点 %s" % (os.path.basename(img1), n_ref))
        print("  参考图2 %s -> 节点 %s" % (os.path.basename(img2), n_ref2))
    print("  -> %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
