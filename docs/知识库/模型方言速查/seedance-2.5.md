---
model: seedance-2.5
version: "2026-10 (火山方舟/字节跳动)"
modes: [T2V, I2V, F2V (首尾帧)]
native_duration_sec: {min: 5, max: 30, note: "单段最长 30s，远超 H3"}
resolution: "720p/1080p 原生支持，竖屏 9:16"
audio: "原生音画同步，支持对白/音效/BGM 一次性生成"
prompt_language: "zh (中文分镜+素材+声音语法)"
reference: "Seedance 2.5 方言 + short-drama-video-prompts references/seedance-2.5.md + seedance-drama-maker 实战"
---

# Seedance 2.5 模型方言速查卡

## 核心优势（vs H3）
- **单段 30s**：长镜头叙事，少拼接
- **50 参考输入**：多槽参考能力强
- **14 语言原生音频**：对白/音效/BGM 同步生成
- **中文正文**：无需强制英文，提示词工程门槛低

## 正文结构（Seedance 2.5 方言）

```json
{
  "task_type": "t2v" | "i2v" | "f2v",
  "prompt": "中文分镜描述：景别/运镜/动作/表演/环境/光影/色调",
  "duration": 10,
  "aspect_ratio": "9:16",
  "reference_images": [
    {"role": "character", "image_url": "..."},
    {"role": "first_frame", "image_url": "..."},
    {"role": "last_frame", "image_url": "..."}
  ],
  "audio": {
    "dialogue": [{"speaker": "A", "text": "台词", "emotion": "平静"}],
    "sfx": ["环境音", "动作音效"],
    "bgm": "背景音乐风格描述或留空"
  },
  "camera": "fixed | push_in | pull_out | pan | orbit | handheld",
  "style": "cinematic | anime | realistic | stylized"
}
```

## 参考模式

| 模式 | role 值 | 说明 |
|------|---------|------|
| 角色一致性 | "character" | 多角度/表情参考，建议 3-5 张 |
| 首帧锚定 | "first_frame" | 构图/布光/色调完全锁定 |
| 尾帧锚定 | "last_frame" | 动作落点/转场衔接 |
| 场景/风格 | "scene" / "style" | 环境一致性/画风迁移 |

**最多 50 张参考**，同角色多角度建议 3-5 张。

## 运镜控制（camera 字段）

| 值 | 对应 | 适用场景 |
|----|------|----------|
| fixed | 静止镜头 | 对白/情绪/特写 |
| push_in | 推镜头 | 情绪递进/揭示 |
| pull_out | 拉镜头 | 环境展示/孤独感 |
| pan | 移镜头 | 空间巡视/跟随 |
| orbit | 环绕 | 角色展示/立体感 |
| handheld | 手持 | 紧迫/纪实/不稳 |

## 音频同轨（原生支持）

```json
"audio": {
  "dialogue": [
    {"speaker": "陈默", "text": "错一笔，烧一条命。", "emotion": "冷峻"},
    {"speaker": "老墨", "text": "符纸选得不错。", "emotion": "玩味"}
  ],
  "sfx": ["风声", "笔尖摩擦纸张声", "远处钟楼敲击"],
  "bgm": "low key ambient, cold cyan-grey tone, subtle tension"
}
```

**优势**：对白逐字可控、情绪可指定、音效/BGM 同步生成，无需后期对轨。

## 实测参数（seedance-drama-maker + 方案 v2 调研）

| 参数 | 数值 | 备注 |
|------|------|------|
| 单段生成时长 | 5-30s | 远超 H3 15s 上限 |
| 并发生成 | 支持 | seedance-drama-maker 并发 2 |
| 轮询间隔 | 15秒 | 最大等待 1800 秒 |
| 720p 价格(二手) | ~¥0.6/s | 火山方舟/BytePlus；方法论口径 |
| 1080p 价格(二手) | **~¥1.5/s** | 方法论 L350；⚠️ 早前误写 ¥1.2，已纠 |
| 单集成本(10镜×10s) | ~¥60-150 | 【推算】含重抽，未经实测 |

## 一致性策略

| 策略 | 实施 | 成本 |
|------|------|------|
| 角色参考图 | 3-5张多角度 character role | 零额外成本 |
| 首尾帧链路 | F2V 模式首尾帧衔接 | 零额外成本 |
| 场景风格锁 | scene/style role 参考图 | 零额外成本 |
| 长叙事 | 单段 30s 覆盖整场 | 减少拼接一致性风险 |

## 校验清单

- [ ] task_type 与参考图 role 匹配
- [ ] duration 在 5-30s 区间
- [ ] aspect_ratio 竖屏 "9:16"
- [ ] dialogue speaker 与剧本角色名一致
- [ ] reference_images 去重、角色多角度≥3张
- [ ] camera 值在枚举内
- [ ] bgm/sfx 描述具体风格而非空泛

## 适配器接口（给 short-drama-video-prompts）

```yaml
model_id: seedance-2.5
prompt_language: zh
native_duration: {min: 5, max: 30}
supported_modes: [text, first_frame, first_last_frame, reference]
audio_generation: same_pass
prompt_format: json
reference_roles: [character, first_frame, last_frame, scene, style]
camera_enum: [fixed, push_in, pull_out, pan, orbit, handheld]
style_enum: [cinematic, anime, realistic, stylized]
audio_fields: {dialogue: true, sfx: true, bgm: true}
```

## 常见失模式

| 现象 | 根因 | 修复 |
|------|------|------|
| 参考图 role 错误 | character/first_frame 混用 | 角色一致性用 character，构图锁定用 first_frame |
| 时长超限 | 请求 >30s | 拆分镜头或用 F2V 首尾帧衔接 |
| 对白不同步 | speaker 名称与剧本不一致 | 严格对应剧本角色名 |
| 多角色口型乱 | 未指定 speaker 情绪 | 每句 dialogue 指定 emotion |
| 画风不稳 | 缺少 style/scene 参考 | 加 1-2 张风格参考图 role=style |

---

## 更新记录

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-10-10 | 初版：结构化 JSON、音频同轨、50参考 | Seedance 2.5 方言 + seedance-drama-maker |