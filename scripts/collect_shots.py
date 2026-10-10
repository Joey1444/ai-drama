#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 Pod 把这一集的镜头全拉回来，按镜序改名成 shot_01.mp4 …，并写下 manifest。

用法:
    python scripts/collect_shots.py --port 38749 --host 80.15.7.37 \
        --shots _validate/batch/shots.json \
        --out _validate/shots_real \
        --manifest _validate/batch/manifest.json

为什么不用文件名序号猜：Pod 的 output 是 `auto_0000N.mp4` 顺序号，**里面混着模板自带的
demo 和定妆镜**，而且镜子的提交顺序和镜号顺序不一致（M02/M08 最后才提交）。
所以走 **ComfyUI /history 反查**：历史里存着每条任务的完整提示词，拿它去和 shots.json 的
prompt 前缀匹配，自描述、不靠猜，也不怕中间插了别的任务。

**默认不删 Pod 上的任何东西**——原始产物按《合规》要求全部留证。
Windows 上 stdout 默认 GBK，中文会乱码，故显式强制 UTF-8。
"""
import io
import json
import os
import re
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

KEY = os.path.expanduser("~/.ssh/runpod_ed25519")
SSH_OPTS = ["-i", KEY, "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=25",
            "-o", "BatchMode=yes"]
# scp 单独一份：不要把 SSH_OPTS 过滤着用——那个写法会**只删掉 -o、留下它的值**，scp 会收到游离参数
SCP_OPTS = ["-i", KEY, "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "BatchMode=yes"]
MATCH_LEN = 0           # 0 = 用完整提示词做键。
# ⚠️ 曾经用「前 60 字」做键，结果**11 个镜全撞到同一条历史**——因为 T2VA 镜的正文开头
#    60 字完全相同（`integrated_multimodal_description: [Shot 1] Live-action, cinematic, a …`）。
#    前缀匹配在这种"模板化正文"上必错，只能整段比。


def arg(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


def main():
    host = arg("--host")
    port = arg("--port")
    if not host or not port:
        print(__doc__)
        return 2
    shots_path = arg("--shots", "_validate/batch/shots.json")
    outdir = arg("--out", "_validate/shots_real")
    manifest_path = arg("--manifest", "_validate/batch/manifest.json")

    shots = json.load(open(shots_path, encoding="utf-8"))
    key = (lambda p: p) if MATCH_LEN == 0 else (lambda p: p[:MATCH_LEN])
    key2shot = {key(s["prompt"]): s for s in shots}

    # 1) 取 Pod 的 ComfyUI 登录态 + history
    # ⚠️ 密码**不硬编码**——从环境变量 COMFYUI_PASSWORD 读（密钥纪律：不进代码/git）
    import os
    comfy_pw = os.environ.get("COMFYUI_PASSWORD", "")
    if not comfy_pw:
        sys.exit("缺少 ComfyUI 密码：请先 `export COMFYUI_PASSWORD=...`（或设到平台 secret）")
    remote = (
        "cd /tmp && "
        "curl -s -c ck.txt http://127.0.0.1:8188/login -o /dev/null && "
        "curl -s -b ck.txt -c ck.txt -X POST -d 'username=root&password=%s' "
        "http://127.0.0.1:8188/login -o /dev/null && "
        "curl -s -b ck.txt http://127.0.0.1:8188/history" % comfy_pw
    )
    r = subprocess.run(["ssh"] + SSH_OPTS + ["-p", port, "root@%s" % host, remote],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not r.stdout.strip().startswith("{"):
        sys.exit("取 history 失败：\n" + (r.stderr or r.stdout)[:600])

    hist = json.loads(r.stdout)
    print("Pod 历史任务 %d 条" % len(hist))

    # 2) 每条历史 -> (提示词, 输出文件名)
    # ⚠️ 不能只盯 MiniMaxH3 节点的 `prompt` 字段：
    #    T2VA 的 prompt 是**字符串**（在 H3 节点上）；Ref2VA 的 prompt 是**连线**指向上游
    #    `PrimitiveStringMultiline.value`。只认前者会漏掉所有参考式镜。
    #    所以：把这条任务里所有长文本都当候选，谁匹配上算谁的。
    found = {}
    for pid, rec in hist.items():
        cands, filename = [], None
        for node in (rec.get("prompt", [None, None, {}])[2] or {}).values():
            for v in (node.get("inputs") or {}).values():
                if isinstance(v, str) and len(v) > 200:
                    cands.append(v)
        for o in (rec.get("outputs") or {}).values():
            for f in (o.get("images") or []):
                filename = filename or f.get("filename")
        for c in cands:
            if key(c) in key2shot:
                found[key(c)] = (pid, filename)

    # 3) 匹配 + 下载
    os.makedirs(outdir, exist_ok=True)
    manifest, missing = [], []
    for s in sorted(shots, key=lambda x: x["order"]):
        hit = found.get(key(s["prompt"]))
        if not hit:
            missing.append(s["id"])
            print("  %-4s ✗ 历史里没找到（可能还没跑完，或提示词改过）" % s["id"])
            continue
        pid, fname = hit
        local = os.path.join(outdir, "shot_%02d.mp4" % s["order"])
        scp = subprocess.run(
            ["scp"] + SCP_OPTS +
            ["-P", port, "root@%s:/workspace/ComfyUI/output/%s" % (host, fname), local],
            capture_output=True, text=True)
        if scp.returncode != 0 or not os.path.isfile(local):
            missing.append(s["id"])
            print("  %-4s ✗ 取片失败 %s" % (s["id"], (scp.stderr or "")[:120]))
            continue
        mb = os.path.getsize(local) / 1048576
        manifest.append({"id": s["id"], "order": s["order"], "seconds": s["seconds"],
                         "mode": s["mode"], "pod_file": fname, "prompt_id": pid,
                         "local": local})
        print("  %-4s ✓ %s -> shot_%02d.mp4  (%.1f MB)" % (s["id"], fname, s["order"], mb))

    json.dump(manifest, open(manifest_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\n拿到 %d/%d 镜 -> %s" % (len(manifest), len(shots), outdir))
    print("manifest -> %s" % manifest_path)
    if missing:
        print("⚠️ 缺：%s" % missing)
        return 1
    print("下一步：把这些 shot_NN.mp4 放进 _validate/shots/ 再跑 _validate/build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
