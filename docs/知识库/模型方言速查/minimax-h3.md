---
model: minimax-h3
version: "2026-10 (开源权重 2026-08-03)"
modes: [T2VA, I2VA, FL2VA, Ref2VA]
native_duration_sec: {min: 4, max: 15, note: "本地部署实测 20s 也可出，非硬墙"}
resolution: "768p (768×1366竖屏)，需上采样到 1080×1920"
audio: "原生 32kHz 立体声，同步生成"
prompt_language: "en (正文必须英文，仅对白/歌词/画内文字保留原文)"
reference: "官方 skill h3-prompt-writing + cinematography + 事实基线.md + H3提示词.md"
---

# MiniMax H3 模型方言速查卡

## 正文结构（六段式 full-reference / 三段式 T2VA）

### T2VA / I2VA / FL2VA（三段结构）
```text
[Shot 1] Live-action, cinematic, <风景别/角度/构图/布光/色调/质感>
<integrated_multimodal_description: 自然英文句，含 motion type + amplitude + speed>
<overall_soundscape: English sentences describing ambient sound>
<non_diegetic_music: "N/A" (本项目 BGM 走后期)>
```

### Ref2VA / Full-reference（六段结构，出脸镜必用）
```text
[Shot 1] Live-action, cinematic, <风格声明>
<summary> [reference generation] <任务描述，350-500词>
<detailed_description> <生成任务详细描述>
<integrated_multimodal_description> <同上>
<overall_soundscape> <同上>
<non_diegetic_music> N/A
```

**关键差异**：Full-reference 必须有 `summary` 以 `[reference generation]` 开头，`detailed_description` 350-500词。

## 参考模式

| 模式 | 适用场景 | 素材角色 | H3 术语 |
|------|----------|----------|---------|
| T2VA | 纯文生/手/物/环境镜 | 无 | text |
| I2VA | 首帧参考（定妆/场景/道具） | 单图 | first_frame |
| FL2VA | 首尾帧参考（动作连贯） | 两图 | first_last_frame |
| Ref2VA | 多槽参考（身份+首帧+场景+道具） | 多图 | reference |

**本项目策略（升级路线.md §5）**：
- 出脸镜：Ref2VA（身份图 + 首帧关键帧 = 双参考）
- 手/物/环境镜：T2VA/I2VA（无脸可漂，不绑图）
- 定妆图：Qwen-Image 出图 → 抽帧 → 作 Ref2VA 的 identity 参考

## 运镜标准句式（仅这两句覆盖 90%）

```text
# 静态镜（绝大多数）
The camera holds a static shot throughout.

# 极缓推进（闪回/高潮用一次）
The camera pushes in with small amplitude at slow speed.
```

**禁用**：运镜标签堆句尾、变焦词、handheld、复杂运动模糊（H3 上会加剧抖动失真）。

## 画外音固定句式

```text
<Character> says in an off-screen voiceover. <Character> keeps lips sealed throughout the shot.
```

**必须紧跟**：说明画内人物嘴唇闭合（否则口型落到最显眼正脸上）。

## 对白格式

```text
<d>[Chinese] 台词逐字来自剧本，不翻译、不改写、不加语气词</d>
```

## 禁词/避雷清单

| 类别 | 禁用词 | 替代/说明 |
|------|--------|-----------|
| 画质溢美 | 超清/杰作/4K/8K/极致画质/高分辨率 | 无信息量，冲淡质感 |
| 运镜歧义 | Push In / Zoom / Dolly (单用) | 必须完整句式 + "physically moves forward without changing focal length" |
| 中文正文 | 任何中文描述性文字 | 正文全英文，仅对白/歌词/画内文字中文 |
| 画内文字 | 生成字幕/caption/对白叠加 | 默认不生成，正文声明 "no on-screen text/captions/subtitles at any moment" |
| 音乐 | non_diegetic_music 写具体风格 | 本项目写 N/A，BGM 后期加 |

## 实测参数（事实基线.md + H3-RunPod实操手册）

| 参数 | 实测值 | 备注 |
|------|--------|------|
| 单镜采样步数 | 20 步 | 进度条 x/20 = 步数非时长 |
| 4.46s 镜(107帧) | 86 秒采样 | 近似线性 |
| 20s 镜(481帧) | 9分30秒采样 | 越长越贵 |
| 时长取整 | 17帧网格 | 请求4秒→107帧→实际4.459s，**字幕必探测真实文件** |
| 首次启动下模型 | 15-25分钟 | ~70GB，盘占69GB |
| 全流程 20秒任务 | ~30分钟 | 采样9:30 + 加载解码 |
| RunPod 4090 价格 | **Secure $0.89/h** · Community 5090 $0.69/h | ⚠️ 早前误写 $0.74（方案-v2 过时值），已按事实基线纠正 |
| 网络卷价格 | $0.07/GB/月 | 200GB≈$14/月 |

## 一致性策略（针对 H3 无跨镜记忆）

| 策略 | 实施方式 | 成本 |
|------|----------|------|
| 自锚定（零新平台） | H3 出 4s 定妆镜 → pick_frame.py 抽正脸闭嘴帧 → 绑 Ref2VA identity | $0 额外 |
| 关键帧链路（升级） | Qwen-Image 出定妆/首帧 → I2VA → 同 Pod 零新平台 | GPU 分钟 <$0.5/集 |
| LoRA 训练 | RunPod 训角色 LoRA (4-8h/角色) | 多角色同框仍不保 |
| 后期归一 | 曝光/色调/颗粒后期统一 (ffmpeg/DAVINCI) | 人工时间 |

## 校验命令

```bash
# 提示词校验（逐镜：台词来自剧本/风格声明/运镜句式/画外音/六段结构/正文无中文/声明不生成字幕）
python scripts/check_prompts.py docs/方案/<系列>/<EP>视频提示词.md docs/方案/<系列>/<EP>剧本.md

# 分镜合法性（制作红线/时长/连续性）
python scripts/check_script.py docs/方案/<系列>/<EP>剧本.md
```

## 常见失模式与修复

| 现象 | 根因 | 修复 |
|------|------|------|
| 正文夹带中文 | 未读 h3-prompt-writing 官方规范 | 全文改英文，仅对白保留中文 |
| 运镜堆句尾 | 照搬 cinematography 标签而非自然句 | 改为两句标准句式 |
| 画外音口型错 | 缺"嘴唇闭合"跟随句 | 补固定句式 |
| 时长对不上 | 用请求值累加而非探测真实文件 | ffprobe 实测时长做字幕 |
| 跨镜曝光漂移 | T2VA 无跨镜记忆 | 关键帧链路/后期归一/LoRA |
| M09 内容跑偏 | 提示词未约束"只到腰部以下" | 静态视觉锚点+起止状态精确写 |
| 参考式跑不了 | Pod 缺 Ref2VA 权重 | 补下 19.53GB ref2va |

---

## 快速切换模板（给 short-drama-video-prompts 适配器用）

```yaml
# minimax-h3 profile
model_id: minimax-h3
prompt_language: en
native_duration: {min: 4, max: 15}
supported_modes: [text, first_frame, first_last_frame, reference]
audio_generation: same_pass
prompt_structure:
  t2va: 3-section
  ref2va: 6-section
style_declaration: "Live-action, cinematic"
camera_static: "The camera holds a static shot throughout."
camera_push_in: "The camera pushes in with small amplitude at slow speed."
voiceover_template: "{character} says in an off-screen voiceover. {character} keeps lips sealed throughout the shot."
dialogue_wrapper: "<d>[Chinese] {dialogue}</d>"
forbidden: ["chinese_in_body", "camera_tags_at_end", "push_in_without_physical", "quality_adjectives", "generate_subtitles"]
music_default: "N/A"
reference_roles: {identity: "identity", first_frame: "first_frame", last_frame: "last_frame", scene: "scene", prop: "prop"}
```

---

## 更新记录

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-10-09 | 正文改英文、六段式规范、自锚定策略 | h3-prompt-writing 官方 skill + 实测返工 |
| 2026-10-10 | 关键帧链路触发条件、Qwen-Image 集成 | 升级路线.md + 事实基线.md |