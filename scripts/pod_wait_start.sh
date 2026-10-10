#!/usr/bin/env bash
# 轮询 RunPod，直到 Pod sgjki4u5idjwx3 起机成功。
# 故意不打印 API key。成功/超时/放弃时退出，由调用方收到通知后接手。
# 用法: bash scripts/pod_wait_start.sh [间隔秒] [最长分钟]

set -u
POD="sgjki4u5idjwx3"
INTERVAL="${1:-30}"
MAXMIN="${2:-180}"
TRIES=$(( MAXMIN * 60 / INTERVAL ))

KEY=$(grep -m1 RUNPOD_API_KEY ~/.claude/token.txt | cut -d= -f2- | tr -d ' \r')
if [ -z "$KEY" ]; then echo "FAIL: 读不到 RUNPOD_API_KEY"; exit 2; fi

echo "轮询启动：每 ${INTERVAL}s 一次，最多 ${MAXMIN} 分钟（$TRIES 次）"
for i in $(seq 1 "$TRIES"); do
  R=$(curl -s --max-time 30 "https://api.runpod.io/graphql?api_key=$KEY" \
      -H 'Content-Type: application/json' \
      -d "{\"query\":\"mutation { podResume(input:{podId:\\\"$POD\\\", gpuCount:1}) { id desiredStatus } }\"}")

  if printf '%s' "$R" | grep -q '"id"'; then
    echo "STARTED 第 $i 次尝试（约 $(( i * INTERVAL / 60 )) 分钟）"
    echo "$R"
    exit 0
  fi

  # 只在错误类型变化时说话，避免刷屏
  case "$R" in
    *"not enough free GPUs"*)
      [ $(( i % 10 )) -eq 1 ] && echo "  第 $i 次：仍无空闲 GPU" ;;
    *)
      echo "  第 $i 次：非容量类错误 —— $R" ;;
  esac
  sleep "$INTERVAL"
done
echo "TIMEOUT: ${MAXMIN} 分钟内一直没抢到卡"
exit 1
