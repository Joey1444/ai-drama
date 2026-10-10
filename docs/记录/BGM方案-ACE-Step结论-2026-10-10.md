# BGM 方案：ACE-Step 可行性结论（2026-10-10）

> **一句话**：**ACE-Step 不作为 BGM 交付路径**；BGM 走 **CC0 音乐库**。
> ACE-Step 降级为「一次受控小实验」，**不为它阻塞 E1**。

---

## 一、实测到的硬事实

| 项 | 实测 | 出处 |
|---|---|---|
| Python 要求 | **3.11–3.12**（本机 3.10.4 ❌） | 官方 README |
| 本机绕法 | ✅ **`uv` 可隔离装 3.12**（实测 28 秒装好，不动系统 3.10.4） | 实测 |
| 依赖坑 | pyproject **把 torch 钉成 CUDA 版**（`+cu128`），**无 Windows CPU 变体** → 官方路径要下 2.5GB 用不上的 CUDA 轮子。**绕法**：走 PyTorch 官方 CPU 源 | `pyproject.toml` |
| **下载量（我此前估错）** | ❌ 不是 4.7GB，**实际 8–10GB**：DiT turbo 4.7 + **独立的 5Hz LM 1.7B ~3.4GB** + Qwen3-Embedding-0.6B + VAE | `gpu_config.py` / `constants.py` 源码 |
| 安装 | ✅ **已验证可装**（CPU 版 torch 2.14.1+cpu，`import acestep` 通过，约 3 分钟） | 实测 |
| **本机内存** | ⚠️ 23.3G 总，**只剩 5.8G 空闲**（实测）→ 直接跑**大概率 OOM / thrashing** | 实测 |
| CPU 生成耗时 | 【推测】**30s 曲目 3–10 分钟；60s 5–15 分钟，上沿 30 分钟**。瓶颈是 **5Hz LM 的自回归**（60s = 300 token，每 token 一次 1.7B 前向） | 源码拆解（producer） |
| 官方 CPU 速度 | **未给**——这本身就是信号 | README |

## 二、为什么否掉（producer 判断 + 我采纳）

1. **ROI 低**：项目当前真实卡点是**画面连贯性**，不是 BGM。BGM 是"待换"，不是"卡点"。投 1–3 小时 + OOM 折腾，回报远低于投在连贯性上。
2. **观众不会因 BGM 是 AI 定制的而留下，只会因版权问题下架**。而 CC0 天然无版权风险。
3. **项目自己的规则**（`方案-v2.md` 附录 B）原话：
   > ACE-Step「能当'**值得试一次的实验**'，**不能当方案基石**；装不上就上云，别耗。」
4. **本机内存不够**：只剩 5.8G 空闲，峰值需求约 12–16GB。

## 三、决定

| 项 | 决定 |
|---|---|
| **BGM 交付** | **走 CC0 音乐库**（YouTube Audio Library / Pixabay Music）——零安装、15–30 分钟、专业成品、无版权风险 |
| **ACE-Step** | 降级为「一次受控小实验」，**且不在现在做**。真要试，按下面最小配置 |
| **不阻塞** | E1 不出片的原因不是 BGM；**BGM 不阻塞任何门** |

## 四、若将来真要试 ACE-Step（最小配置，别全量）

1. **不下 1.7B LM**——用 **DiT-only** 或 **0.6B LM**（省 3.4GB，且砍掉最慢的 300 步自回归）
2. **只生成 20–30s**，循环成 60s（现在的 BGM 本来就是 30s 循环，无损失）
3. **跑之前腾内存到 15GB+**（关 Chrome；当前仅 5.8G 空闲）
4. **时间盒**：记录 30s 样本的真实 CPU 秒数，**超过 15–20 分钟即止损**（转 CC0 或上 Pod）
5. 仓库留在 `D:\apps\ACE-Step-1.5`（**别放 C 盘**——用户明确要求）；venv 因带绝对路径需在 D 盘重建（uv 有缓存，约 3 分钟）

## 五、可复现的安装配方（已验证）

```bash
# 用 uv 隔离 Python 3.12，不动系统的 3.10.4
uv python install 3.12
uv venv --python 3.12 .venv-ace
# ★ 绕开 CUDA 钉，走 CPU 源（省 2.3GB）
uv pip install --python .venv-ace --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio
uv pip install --python .venv-ace -e . --no-deps
uv pip install --python .venv-ace transformers diffusers soundfile loguru einops accelerate numba vector-quantize-pytorch scipy matplotlib
```
