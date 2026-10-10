#!/usr/bin/env bash
# 等 Pod 上的 ComfyUI 渲染队列跑空（running + pending 都为 0），然后退出。
# 供后台运行：不占对话，跑完了才通知。
# 用法: bash scripts/pod_wait_queue.sh <port> <host> [间隔秒] [最长分钟]

set -u
PORT="${1:?需要 SSH 端口}"
HOST="${2:?需要 IP}"
INTERVAL="${3:-20}"
MAXMIN="${4:-90}"
TRIES=$(( MAXMIN * 60 / INTERVAL ))

SSH="ssh -i $HOME/.ssh/runpod_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -o BatchMode=yes -p $PORT root@$HOST"

echo "盯着队列：每 ${INTERVAL}s 一次，最多 ${MAXMIN} 分钟"
for i in $(seq 1 "$TRIES"); do
  N=$($SSH 'curl -s -b /tmp/ck.txt http://127.0.0.1:8188/queue 2>/dev/null | python3 -c "import json,sys
try:
    q=json.load(sys.stdin)
    print(len(q.get(\"queue_running\") or [])+len(q.get(\"queue_pending\") or []))
except Exception:
    print(-1)"' 2>/dev/null | tr -d '\r')

  case "$N" in
    0) echo "DONE 队列已空（等了约 $(( i * INTERVAL / 60 )) 分钟），可以收片了"; exit 0 ;;
    -1|"") [ $(( i % 6 )) -eq 1 ] && echo "  第 $i 次：SSH 或 ComfyUI 没响应，重试" ;;
    *) [ $(( i % 6 )) -eq 1 ] && echo "  第 $i 次：队列剩 $N 个" ;;
  esac
  sleep "$INTERVAL"
done

echo "TIMEOUT: ${MAXMIN} 分钟内队列没跑空"
exit 1
