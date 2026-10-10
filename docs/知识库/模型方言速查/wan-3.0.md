---
model: wan-3.0
version: "2026-10 (阿里云/通义万相)"
modes: [T2V, I2V, F2V, 多镜时间段]
native_duration_sec: {min: 5, max: 20, note: "单段最长 20s"}
resolution: "720p/1080p 原生支持，竖屏 9:16"
audio: "支持音频同步生成，中文优化"
prompt_language: "zh (中文正文+素材编号+多镜时间段语法)"
reference: "Wan 3.0 方言 + short-drama-video-prompts references/wan-3.0.md + director-desk 实战"
---

# Wan 3.0 模型方言速查卡

## 核心优势（vs H3/Seedance）
- **中文原生**：提示词全中文，无需翻译
- **多镜时间段**：单次生成多个镜头，自带时间轴
- **阿里云生态**：Model Studio/API 直连，国内直连无障碍
- **成本可控**：按秒计费，有免费额度

## 正文结构（Wan 3.0 方言）

```json
{
  "task_type": "t2v" | "i2v" | "f2v" | "multi_shot",
  "prompt": "中文正文：主体/动作/环境/光影/色调/运镜/氛围",
  "negative_prompt": "可选：模糊/变形/低质量/水印/文字/多肢体",
  "duration": 10,
  "resolution": "720p" | "1080p",
  "aspect_ratio": "9:16",
  "reference_images": [
    {"index": 1, "url": "...", "control_type": "character" | "first_frame" | "style"},
    {"index": 2, "url": "...", "control_type": "last_frame"}
  ],
  "shots": [
    {"start": 0, "end": 5, "prompt": "镜头1描述", "camera": "push_in"},
    {"start": 5, "end": 10, "prompt": "镜头2描述", "camera": "fixed"}
  ],
  "audio": {
    "tts": {"text": "台词", "speaker": "中文女/男", "emotion": "平静"},
    "bgm": "风格描述",
    "sfx": ["音效列表"]
  }
}
```

**特有**：`shots` 数组支持单次生成多镜头，每镜有独立时间段和提示词。

## 参考模式

| control_type | 适用场景 | 说明 |
|--------------|----------|------|
| character | 角色一致性 | 多角度/表情，建议 3-5 张 |
| first_frame | 首帧构图锁定 | 完全控制起始画面 |
| last_frame | 尾帧动作锁定 | 控制结束状态/转场 |
| style | 画风迁移 | 色调/质感/风格一致 |

## 运镜控制（camera 字段）

| 值 | 说明 |
|----|------|
| fixed | 静止 |
| push_in | 推进 |
| pull_out | 拉远 |
| pan_left/right | 左/右移 |
| tilt_up/down | 仰/俯 |
| orbit | 环绕 |
| handheld | 手持摇晃 |

## 音频支持

- **TTS**：中文语音合成，多音色可选，情绪可控
- **BGM/SFX**：风格描述生成
- **口型同步**：I2V/F2V 模式下自动同步

## 实测参数（director-desk + 方案 v2 调研）

| 参数 | 数值 | 备注 |
|------|------|------|
| 单段时长 | 5-20s | 单次生成 |
| 多镜总时长 | ≤60s | shots 数组累计 |
| 并发限制 | Model Studio 限额 | 需申请配额 |
| 价格(二手) | 720p ~¥0.4/s, 1080p ~¥0.8/s | 阿里云 Model Studio |
| 单集成本 | ~¥40-80 | 含重抽 |
| 免费额度 | 新用户送额度 | 适合测试 |

## 一致性策略

| 策略 | 实施 | 成本 |
|------|------|------|
| character 参考 | 3-5张多角度 | 零额外 |
| multi_shot 单次生成 | 单次生成全集分镜 | 减少跨镜漂移 |
| style 参考 | 1-2张风格图 | 零额外 |
| 首尾帧衔接 | F2V 模式 | 零额外 |

## 校验清单

- [ ] task_type 与参考图/shots 匹配
- [ ] multi_shot 时 shots 时间段不重叠、累计≤60s
- [ ] reference_images control_type 明确
- [ ] negative_prompt 包含基础负面词
- [ ] TTS speaker 与角色性别/年龄匹配

## 适配器接口

```yaml
model_id: wan-3.0
prompt_language: zh
native_duration: {min: 5, max: 20}
supported_modes: [text, first_frame, first_last_frame, reference, multi_shot]
audio_generation: same_pass
prompt_format: json
reference_control_types: [character, first_frame, last_frame, style]
camera_enum: [fixed, push_in, pull_out, pan_left, pan_right, tilt_up, tilt_down, orbit, handheld]
multi_shot: true
max_shots_per_gen: 6
max_total_duration: 60
tts_speakers: ["中文女", "中文男", "方言女", "方言男", "儿童", "老年"]
```

## 常见失模式

| 现象 | 根因 | 修复 |
|------|------|------|
| 多镜时间段重叠 | shots start/end 设置错误 | 严格按顺序不重叠分段 |
| 角色一致性差 | character 参考图<3张/角度单一 | 补齐 3-5 张不同角度/表情 |
| 画风漂移 | 缺少 style 参考 | 加 1-2 张风格参考图 |
| TTS 音色不符 | speaker 选错 | 按角色年龄/性别/方言选 speaker |
| API 限流/报错 | 配额不足/并发超限 | 申请配额/加队列延迟 |

---

## 更新记录

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-10-10 | 初版：多镜时间段、中文正文、阿里云生态 | Wan 3.0 方言 + director-desk |