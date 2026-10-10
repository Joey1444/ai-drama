#!/usr/bin/env bash
# 每 30 秒重试启动 Pod，成功即退出；最多 60 次（30 分钟）
POD="sgjki4u5idjwx3"
KEY=$(grep -m1 RUNPOD_API_KEY ~/.claude/token.txt | cut -d= -f2- | tr -d ' \r')
for i in $(seq 1 60); do
  R=$(curl -s --max-time 30 "https://api.runpod.io/graphql?api_key=$KEY" \
      -H "Content-Type: application/json" \
      -d "{\"query\":\"mutation { podResume(input: {podId: \\\"$POD\\\"}) { id desiredStatus } }\"}")
  if echo "$R" | grep -q '"desiredStatus":"RUNNING"'; then
    echo "[$(date +%H:%M:%S)] 第 $i 次：启动成功 RUNNING"
    exit 0
  fi
  echo "[$(date +%H:%M:%S)] 第 $i 次：未起（$(echo "$R" | grep -o 'not enough free GPUs' || echo 其他)）"
  sleep 30
done
echo "[$(date +%H:%M:%S)] 60 次仍未起，放弃（宿主机持续无空闲 GPU）"
exit 1
