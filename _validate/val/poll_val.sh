#!/usr/bin/env bash
PID="d9a4278c-4927-4456-a941-cbcf63a6765c"
SSH="ssh -i $HOME/.ssh/runpod_ed25519 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=20 -p 38970 root@80.15.7.37"
for i in $(seq 1 40); do
  OUT=$($SSH "curl -s -b /tmp/ck.txt --max-time 15 http://127.0.0.1:8188/history/$PID" 2>/dev/null)
  if echo "$OUT" | grep -q "$PID"; then
    echo "[$(date +%H:%M:%S)] 第 $i 次：完成"
    echo "$OUT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
h=list(d.values())[0]
for nid,o in h.get('outputs',{}).items():
    for k,v in o.items():
        if isinstance(v,list):
            for it in v:
                if isinstance(it,dict) and 'filename' in it:
                    print('OUTPUT:', it.get('subfolder','')+'/'+it['filename'])
" 2>/dev/null
    exit 0
  fi
  echo "[$(date +%H:%M:%S)] 第 $i 次：未完成"
  sleep 20
done
echo "[$(date +%H:%M:%S)] 超时"
exit 1
