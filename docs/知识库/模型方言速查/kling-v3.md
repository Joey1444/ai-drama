---
model: kling-v3
version: "2026-10 (快手可灵)"
modes: [T2V, I2V, F2V, 口型同步]
native_duration_sec: {min: 5, max: 10, note: "单段 5-10s，可扩展到 30s (Omni)"}
resolution: "720p/1080p，竖屏 9:16 原生"
audio: "支持口型同步，TTS 集成"
prompt_language: "zh (中文提示词+参考图 role)"
reference: "Kling v3 官方文档 + ai-short-drama-tools + 方案 v2 调研"
---

# Kling v3 模型方言速查卡

## 核心优势（vs H3/Seedance/Wan）
- **口型同步原生强**：Lip Sync 效果业界领先，真人特写可用
- **Omni 模式**：单段可达 30s，支持复杂动作
- **快手生态**：快手分发原生适配，算法加成
- **中文提示词**：无需翻译

## 正文结构

```json
{
  "model": "kling-v3" | "kling-v3-omni",
  "prompt": "中文描述：主体/动作/环境/运镜/光影/色调/氛围",
  "negative_prompt": "模糊/变形/低质量/水印/文字/多肢体/崩坏",
  "duration": 5 | 10 | 30,
  "aspect_ratio": "9:16",
  "reference_images": [
    {"role": "subject" | "first_frame" | "last_frame", "url": "..."}
  ],
  "camera_control": {
    "type": "fixed" | "push_in" | "pull_out" | "pan" | "tilt" | "orbit" | "handheld",
    "config": {"speed": 0.5, "range": 10}
  },
  "lip_sync": {
    "enable": true,
    "audio_url": "...",
    "mode": "accurate" | "expressive"
  },
  "cfg_scale": 0.5,
  "seed": -1
}
```

## 参考模式

| role | 适用场景 |
|------|----------|
| subject | 主体一致性（角色/物体），多角度 3-5 张 |
| first_frame | 首帧构图完全锁定 |
| last_frame | 尾帧动作/转场锁定 |

## 运镜控制（camera_control）

| type | config 参数 | 适用场景 |
|------|-------------|----------|
| fixed | 无 | 静态情绪镜头 |
| push_in | speed/range | 情绪递进/揭示 |
| pull_out | speed/range | 环境展示/孤立感 |
| pan | speed/direction | 空间巡视/跟随 |
| tilt | speed/direction | 仰视/俯视压迫感 |
| orbit | speed/radius | 角色立体展示 |
| handheld | intensity | 紧迫/纪实/不稳 |

## 口型同步——核心杀手锏

```json
"lip_sync": {
  "enable": true,
  "audio_url": "TTS生成或真人录制的音频URL",
  "mode": "accurate"  # accurate=精准/ expressive=表现力优先
}
```

**适用场景**：真人特写念白、对白密集镜头
**优势**：比 H3 原生口型准得多，比 Sync Labs/Hedra 便宜

## 实测参数（方案 v2 §3-B3 + ai-short-drama-tools）

| 参数 | 数值 | 备注 |
|------|------|------|
| 标准模式时长 | 5-10s | 单段 |
| Omni 模式时长 | 10-30s | 复杂动作/长叙事 |
| 并发 | 平台限额 | 需申请 |
| 标准档价格(二手) | **~¥0.54/s** | ⚠️ Omni ≈ $0.075/s（3-关键帧调研口径）；早前误写 ¥1.0，已纠 |
| 单集成本 | ~¥50-100 | 【推算】含重抽+口型 |

## 一致性策略

| 策略 | 实施 | 成本 |
|------|------|------|
| subject 参考 | 3-5张多角度 | 零额外 |
| 首尾帧衔接 | F2V 模式 | 零额外 |
| 口型同步复用 | 同音频多镜头复用 | 零额外 |
| LoRA/微调 | 平台支持定制模型 | 需沟通 |

## 校验清单

- [ ] model 选择正确
- [ ] duration 匹配模式
- [ ] reference_images role 明确
- [ ] lip_sync 需要时 enable=true + audio_url 有效
- [ ] camera_control type 在枚举内
- [ ] negative_prompt 含基础负面词

## 适配器接口

```yaml
model_id: kling-v3
prompt_language: zh
native_duration: {min: 5, max: 10}
omni_duration: {min: 10, max: 30}
supported_modes: [text, first_frame, first_last_frame, reference]
audio_generation: lip_sync_separate
reference_roles: [subject, first_frame, last_frame]
camera_control_types: [fixed, push_in, pull_out, pan, tilt, orbit, handheld]
lip_sync: true
lip_sync_modes: [accurate, expressive]
omni_mode: true
```

## 常见失模式

| 现象 | 根因 | 修复 |
|------|------|------|
| 口型不同步 | audio_url 失效/模式选错 | 检查 URL 有效/选 accurate 模式 |
| Omni 模式崩坏 | 时长过长/动作过复杂 | 拆分为标准模式多镜头 |
| 主体漂移 | subject 参考图不足 | 补齐 3-5 张不同角度 |
| 运镜失控 | camera_control 配置不当 | 简化为 fixed/push_in |
| API 报错/限流 | 配额/并发/格式错误 | 查错误码/加重试/降并发 |

---

## 更新记录

| 日期 | 变更 | 来源 |
|------|------|------|
| 2026-10-10 | 初版：口型同步、Omni模式、快手生态 | Kling v3 官方 + ai-short-drama-tools |