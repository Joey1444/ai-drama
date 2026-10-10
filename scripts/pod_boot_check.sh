#!/usr/bin/env bash
# Pod 开机自检 —— **在 Pod 内跑**（scp 上去后 bash pod_boot_check.sh）
#
# 固化每次开机必做、此前靠手做的四件事：
#   1) ComfyUI 登录（/tmp 重启即清，密码文件可能没了）
#   2) 拉 object_info -> /tmp/oi.json（comfy_ui2api.py 依赖它；重启即丢）
#   3) 盘点资产（权重/LoRA/加速器），确认没缺
#   4) 确认 turbo 开关存在（r2v 节点 146）
#
# 需要环境变量：COMFYUI_PASSWORD
set -u
CK=/tmp/ck.txt
PW="${COMFYUI_PASSWORD:?需 export COMFYUI_PASSWORD=<ComfyUI 登录密码>}"
M=/workspace/ComfyUI/models
echo "══════ Pod 开机自检 $(date '+%H:%M:%S') ══════"

# 1) 登录
curl -s -c "$CK" http://127.0.0.1:8188/login -o /dev/null
CODE=$(curl -s -b "$CK" -c "$CK" -o /dev/null -w "%{http_code}" \
       -X POST -d "username=root&password=$PW" http://127.0.0.1:8188/login)
echo "1) 登录 HTTP=$CODE $([ "$CODE" = "302" ] || [ "$CODE" = "200" ] && echo ✅ || echo '❌ 密码可能变了')"

# 2) oi.json
[ -s /tmp/oi.json ] || curl -s -b "$CK" --max-time 40 http://127.0.0.1:8188/object_info -o /tmp/oi.json
echo "2) oi.json $(stat -c%s /tmp/oi.json 2>/dev/null || echo 0) 字节"

# 3) 资产
echo "3) 资产："
for d in diffusion_models loras vae text_encoders; do
  n=$(ls "$M/$d"/*.safetensors 2>/dev/null | wc -l)
  echo "   $d: $n 个"
done
ls "$M/diffusion_models"/*.safetensors 2>/dev/null | xargs -n1 basename | sed 's/^/     /'
echo "   LoRA："
ls "$M/loras"/*.safetensors 2>/dev/null | xargs -n1 basename | sed 's/^/     /'

# 4) turbo 开关
echo -n "4) turbo 开关（r2v 节点 146）："
python3 - <<'PY'
import json
try:
    d = json.load(open("/workspace/video_minimax_h3_r2v.json"))
    n = {x.get("id"): x for x in d.get("nodes", [])}
    print("存在 ✅ 当前值 =", n[146]["widgets_values"] if 146 in n else "?")
except Exception as e:
    print("检查失败:", e)
PY

echo ""
echo "下一步：bash pod_batch_generate.sh <shots.json>   （turbo 已自动开）"
