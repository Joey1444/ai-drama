#!/usr/bin/env bash
# 等 Pod provision 完 + SSH 真能连上，然后把端口/IP 打出来。
# 供后台运行：不占对话，准备好了才通知。
# 用法: bash scripts/pod_wait_ready.sh [间隔秒] [最长分钟]

set -u
POD="sgjki4u5idjwx3"
KEYFILE=~/.ssh/runpod_ed25519
INTERVAL="${1:-20}"
MAXMIN="${2:-45}"
TRIES=$(( MAXMIN * 60 / INTERVAL ))

KEY=$(grep -m1 RUNPOD_API_KEY ~/.claude/token.txt | cut -d= -f2- | tr -d ' \r')
[ -z "$KEY" ] && { echo "FAIL: 读不到 RUNPOD_API_KEY"; exit 2; }

echo "等待 provision：每 ${INTERVAL}s 探一次，最多 ${MAXMIN} 分钟"

for i in $(seq 1 "$TRIES"); do
  J=$(curl -s --max-time 30 "https://api.runpod.io/graphql?api_key=$KEY" \
      -H 'Content-Type: application/json' \
      -d "{\"query\":\"query { pod(input:{podId:\\\"$POD\\\"}) { desiredStatus runtime { ports { ip isIpPublic privatePort publicPort type } } } }\"}")

  # 从 ports 里挑 type=tcp 且 privatePort=22 的那个 publicPort，配公网 IP
  read -r IP PORT <<<"$(printf '%s' "$J" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print(""); raise SystemExit
p=d.get("data",{}).get("pod") or {}
rt=p.get("runtime") or {}
pub=[q for q in (rt.get("ports") or []) if q.get("type")=="tcp" and q.get("privatePort")==22 and q.get("isIpPublic")]
if pub: print(pub[0]["ip"], pub[0]["publicPort"])
else: print("")
' 2>/dev/null)"

  if [ -n "${PORT:-}" ]; then
    if ssh -i "$KEYFILE" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
           -o ConnectTimeout=12 -o BatchMode=yes -p "$PORT" "root@$IP" 'echo SSH_READY' 2>/dev/null | grep -q SSH_READY; then
      echo "READY ip=$IP port=$PORT（第 $i 次探测，约 $(( i * INTERVAL / 60 )) 分钟）"
      exit 0
    fi
    [ $(( i % 6 )) -eq 1 ] && echo "  第 $i 次：端口已开($PORT)，SSH 还没通"
  else
    [ $(( i % 6 )) -eq 1 ] && echo "  第 $i 次：容器还没起来"
  fi
  sleep "$INTERVAL"
done

echo "TIMEOUT: ${MAXMIN} 分钟内 SSH 未就绪"
exit 1
