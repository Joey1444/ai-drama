#!/usr/bin/env bash
# ACE-Step 本机可行性实测（时间盒）。用 uv 隔离 Python 3.12，不动系统 3.10.4
set -u
cd /tmp/ACE-Step-1.5 2>/dev/null || { echo "FAIL: 没克隆到 repo"; exit 1; }
echo "[1] 装 Python 3.12（uv 隔离）..."
uv python install 3.12 2>&1 | tail -2
echo "[2] 建 venv 3.12 ..."
uv venv --python 3.12 .venv-ace 2>&1 | tail -2
echo "[3] 装 CPU 版 torch（绕开 cu128 钉，省 2.3GB）..."
uv pip install --python .venv-ace --index-url https://download.pytorch.org/whl/cpu "torch" "torchvision" "torchaudio" 2>&1 | tail -3
echo "[4] 装 ACE-Step 其余依赖..."
uv pip install --python .venv-ace -e . --no-deps 2>&1 | tail -2
uv pip install --python .venv-ace transformers diffusers soundfile loguru einops accelerate numba vector-quantize-pytorch scipy matplotlib 2>&1 | tail -3
echo "[5] 验证 import ..."
.venv-ace/Scripts/python -c "import torch, acestep; print('torch', torch.__version__, 'CUDA:', torch.cuda.is_available())" 2>&1 | tail -3
echo "DONE"
