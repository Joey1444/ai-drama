#!/usr/bin/env bash
# 轮询后台任务产物下载就绪 —— 在 **本机** 跑（不需要在 Pod 内）
# 用法: bash scripts/pod_poll.sh <host> <ssh_port> <prompt_id> [最多次数]
HOST="${1:?host}"; PORT="${2:?ssh port}"; PID="${3:?prompt_id}"; MAX="${4:-40}"
KEY="${COMFYUI_PASSWORD:?需 export COMFYUI_PASSWORD}"
SSH="ssh -i $HOME/.ssh/runpod_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -p $PORT root@$HOST"
$SSH "curl -s -c /tmp/ck.txt http://127.0.0.1:8188/login -o /dev/null; \
      curl -s -b /tmp/ck.txt -c /tmp/ck.txt -X POST -d 'username=root&password=$KEY' \
           http://127.0.0.1:8188/login -o /dev/null"
for i in $(seq 1 "$MAX"); do
  OUT=$($SSH "curl -s -b /tmp/ck.txt --max-time 15 http://127.0.0.1:8188/history/$PID" 2>/dev/null)
  if echo "$OUT" | grep -q "$PID"; then
    echo "[$(date +%H:%M:%S)] 第 $i 次：完成"
    echo "$OUT" | python3 -c "
import sys,json
d=json.load(sys.stdin); h=list(d.values())[0]
for o in h.get('outputs',{}).values():
    for v in o.values():
        if isinstance(v,list):
            for it in v:
                if isinstance(it,dict) and 'filename' in it:
                    print('OUTPUT:', it.get('subfolder','')+'/'+it['filename'])
" 2>/dev/null
    exit 0
  fi
  sleep 20
done
echo "超时"; exit 1
