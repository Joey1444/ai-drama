#!/usr/bin/env bash
# 在 **Pod 内** 逐镜生成（顺序执行）。
#
# 为什么必须在 Pod 内跑：`comfy_ui2api.py` 要读 /tmp/oi.json、`comfy_patch.py` 要读
# /workspace/ComfyUI/models —— 这两个路径只在本机（Pod）存在。在本机 Windows 上跑必失败。
#
# 用法（在 Pod 的 /workspace 下）：
#   bash pod_batch_generate.sh shots.json [起始镜号]
#
# shots.json 每项需含：id / mode(t2va|ref2va) / seconds / prompt
#   ref2va 时还需 reference.path（身份图）与可选 reference2.path（场景图）
set -u
SHOTS="${1:?用法: pod_batch_generate.sh shots.json [起始镜号]}"
START="${2:-}"
CK=/tmp/ck.txt

# 0) 保证已登录 + oi.json 存在（Pod 重启后 /tmp 会清空）
curl -s -c "$CK" http://127.0.0.1:8188/login -o /dev/null
curl -s -b "$CK" -c "$CK" -X POST -d "username=root&password=${COMFYUI_PASSWORD:?需 export COMFYUI_PASSWORD}" \
     http://127.0.0.1:8188/login -o /dev/null
[ -s /tmp/oi.json ] || curl -s -b "$CK" --max-time 30 http://127.0.0.1:8188/object_info -o /tmp/oi.json
echo "oi.json: $(stat -c%s /tmp/oi.json 2>/dev/null) 字节"

IDS=$(python3 -c "import json;[print(s['id']) for s in json.load(open('$SHOTS'))]")
echo "共 $(echo "$IDS" | wc -l) 镜"

for ID in $IDS; do
  # 支持从指定镜开始
  if [ -n "$START" ] && [ "$ID" != "$START" ] && [ "$STARTED" != "1" ]; then continue; fi
  STARTED=1

  echo "───── $ID ─────"
  python3 make_payload.py --shots "$SHOTS" --workflow-dir . --shot "$ID" --out "/tmp/wf_$ID.json" || { echo "$ID payload 失败，跳过"; continue; }
  python3 comfy_ui2api.py "/tmp/wf_$ID.json" -o "/tmp/api_$ID.json" >/dev/null || { echo "$ID 转换失败，跳过"; continue; }
  python3 comfy_patch.py "/tmp/api_$ID.json" "/tmp/payload_$ID.json" >/dev/null || { echo "$ID patch 失败，跳过"; continue; }

  PID=$(curl -s -b "$CK" -X POST -H "Content-Type: application/json" \
        --data-binary @"/tmp/payload_$ID.json" http://127.0.0.1:8188/prompt \
        | python3 -c "import sys,json;print(json.load(sys.stdin).get('prompt_id',''))")
  [ -z "$PID" ] && { echo "$ID 提交失败，跳过"; continue; }
  echo "$ID 已提交 prompt_id=$PID"

  # 等完成（最多 25 分钟）
  for _ in $(seq 1 100); do
    sleep 15
    curl -s -b "$CK" "http://127.0.0.1:8188/history/$PID" | grep -q "$PID" && { echo "$ID ✅ 完成"; break; }
  done
done
echo "批处理结束"
