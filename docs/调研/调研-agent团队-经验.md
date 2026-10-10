# 调研：Agent 团队怎么搭才稳（全网搜集中）

> 2026-10-09 起 ｜ 目的：为 ai-drama 固化一支能稳定产出短剧的 agent 团队
> 状态：**进行中**，每轮搜索后追加

---

## 第一轮来源

| # | 来源 | 类型 |
|---|---|---|
| 1 | Claude Code 官方文档「协调会话团队 / agent teams」（zh-CN） | 官方规范 |
| 2 | lilys.ai《Claude Code 如何搭建一个多 Agent 短剧编剧团队》 | 中文实战 |
| 3 | XucroYuri/how-to-make-script《Multi-Agent Screenplay Architecture》 | 架构设计 |
| 4 | Claude Code 官方文档「subagents」（前一轮） | 官方规范 |
| 5 | VoltAgent/awesome-claude-code-subagents（25.6k★，100+ agent） | 社区集合 |

---

## 经验 A：先想清楚用哪种"多 agent"

**官方明确区分两种，成本差一个数量级：**

| | Subagents | Agent Teams（实验性） |
|---|---|---|
| 通信 | 各自回报给调用者 | **队友之间直接通信** |
| 协调 | 主 agent 管全部 | 共享任务列表 + 自我认领 |
| 最适合 | 只要结果的专注任务 | **需要讨论、互相质疑的复杂工作** |
| 成本 | 较低 | **明显更高**（每个队友是独立 Claude 实例） |

**📌 对我们的启示**：短剧创作里，"世界观/编剧/制片"三方**需要互相质疑**（本轮已验证：制片人的红线直接否掉了编剧的设计）→ 这种适合 team；而"事实核查""观众测试"只要结果 → 适合 subagent。

**官方给的团队规模建议**：**从 3–5 个队友起步**；每个队友 5–6 个任务；超过一定点收益递减——"三个专注的队友胜过五个分散的队友"。

---

## 经验 B：稳定性来自"文档驱动"，不是来自提示词

**lilys.ai 那篇中文实战踩过的坑，正是我们要防的：**
- 上下文超限（20 万 tokens，触发 compacting）→ **关键信息全存文档**，压缩后仍能了解进度
- 新窗口无上下文 → 输入 `/status`，主 Agent 自动读 `Script progress.md`，**全新窗口也能秒接上**
- 时间线不一致 → 主 Agent 自己发现人物小传与大纲矛盾

**📌 对我们的启示**：**记忆必须落在文件里**，不能指望对话上下文。我们的 `方案-v2.md` / `验证记录` / `审核意见` 已经是这个模式，要把它制度化。

**官方也背书**：agent teams 的共享任务列表本身就是文档化的协调机制。

---

## 经验 C：用"交接包"代替全上下文共享

来自 XucroYuri 的架构文档，**这条最工程化、最值得抄**：

每个专家的输出不是一大段话，而是一个**有界的交接包**：

```
working_hypothesis     当前工作假设
loaded_bundle_ids      加载了哪些资料
open_questions         未决问题
confidence             置信度
recommended_next_agent 建议下一个接手谁
needs_human_review     是否需要人工审
```

**四条设计原则**（原文）：
1. 中心 orchestrator —— 当"归属与综合"重要时
2. 专家制 —— 当"不同决策需要不同知识包"时
3. **用交接包，而不是全上下文共享**
4. 人在**昂贵或模糊的关口**介入

**📌 对我们的启示**：每个 agent 定义里都要写死**输出契约**（前一轮我写的 worldbuilder 输出契约就是雏形），并且带 `confidence` 与 `needs_human_review`——**这两项是防自嗨的关键**。

---

## 经验 D：短剧特有的"创作法则"要写进配置层

lilys.ai 那篇的做法：在 `CLAUDE.md` 顶层内置**短剧创作法则**——
> "第一集要有强钩子，第 20 集是付费点，每 10 集要有三个话题点"

并且专门设了一个 **Script Aligner（审核 agent）**，它的实际作用是**挑节奏问题**——原文记录它指出了"**剧情冲突和爽点节奏不够快**"，建议"第一集就有冲突，每两三集一个高潮"，经 4 轮迭代才确认合格。

**📌 对我们的启示**：我们要的 `audience-proxy` + 一个**节奏审核**角色，本质就是 Script Aligner。而且**审核要能迭代多轮**，不是一遍过。

---

## 经验 E：官方支持用 subagent 定义充当队友（省一半事）

官方原文：spawn 队友时可以**按名字引用 subagent 定义**，复用其 `tools` / `model` / `effort` / body。

**📌 对我们的启示**：**只写一套 `.claude/agents/*.md`，既能当 subagent 调用，也能当 team 队友**。不需要维护两套。

---

## 经验 F：质量门可以用 hooks 硬约束

官方提供三个 hook 事件做质量门：
- `TeammateIdle` —— 队友将空闲时触发，exit 2 可打回并要求继续干
- `TaskCreated` —— 任务创建时，exit 2 可拒绝创建
- `TaskCompleted` —— 任务标记完成时，exit 2 可**阻止完成**并给反馈

**📌 对我们的启示**："产出稳定"可以**不靠自觉，靠 hook 硬拦**——比如：剧本没带结尾反转就不许标记完成。这与我们全局规则里"必须无条件阻断/放行 → settings.json 的 permissions/hooks"一致。

---

## 经验 G：成本与团队规模

- lilys.ai 作者原话：**"Claude Code 的 tokens 是真的贵，每次循环其实都是在烧钱"**
- 官方：agent teams 令牌消耗**明显高于**单会话，随活跃队友数线性增长
- 官方：**从 3–5 个起步**；三个专注的胜过五个分散的

**📌 对我们的启示**：团队**不超过 5–6 个**；日常别开 team，只在"需要互相质疑"的关口开。

---

## 第二轮来源

| # | 来源 | 类型 |
|---|---|---|
| 6 | `hahagood/snowflake-novel-subagents` | 16 agent 的小说流水线（最具体） |
| 7 | `bybren-llc/story-systems-template` | 11 agent + `/writers-room` 会议模式 |

---

## 经验 H：加一个"编排器"，别让主 agent 兼当项目经理

snowflake 的做法：**1 个 orchestrator + 10 个步骤 agent + 5 个辅助 agent**。
编排器只管：**初始化目录 / 追踪进度 / 验证前置条件 / 推荐下一步**——它不写内容。

**步骤之间有明确依赖链**：步骤 4 需要 1+2+3 一致；步骤 6 需要 4+5 一致；步骤 8 需要 6+7 一致。

**📌 对我们的启示**：短剧也有依赖链（世界观 → 编剧 → 分镜 → 提示词 → 生成）。编排器可以直接用**主会话**充当，但**依赖校验要显式**——"上游没定完不许进下游"。

---

## 经验 I：辅助 agent 按"阶段"触发，不是全程待命

snowflake 的辅助 agent 绑定到特定步骤：

| 辅助 agent | 在哪几步触发 |
|---|---|
| `genre-specialist` 类型专家 | 步骤 1、2、4、6 |
| `dialogue-master` 对话大师 | 步骤 7、9、10 |
| `pacing-controller` 节奏控制 | 步骤 6、8、9 |
| `consistency-checker` 一致性检查 | **步骤 4、6、8 完成后（阶段性）** |
| `editor-reviewer` 完稿审阅 | 步骤 10 完成后 |

**📌 对我们的启示**：`audience-proxy` / `producer` / `fact-checker` 不该每步都叫，应该**绑定到关口**——比如 producer 只在"设定定稿后、生成前"叫。

---

## 经验 J：质量评分制 —— 最可操作的"产出稳定"手段

snowflake 给**每个 agent 的输出定死评分维度与合格线**：
- 步骤 1：3 个维度（有趣度、突兀度、合理度），满分 15，**合格 12**
- 步骤 2–10：各 4 个维度，满分 20，**合格 14**
- 辅助 agent：各 3 个维度，满分 15，**合格 10**

**📌 对我们的启示**：这是我们最缺的一环。**"产出稳定"= 可量化的验收线**。我们该给编剧输出定维度（钩子强度 / 反转力度 / 实害具体度 / 可拍性），不合格就打回重写，而不是靠"感觉还行"。

---

## 经验 K：agent 文件的七段式模板（社区已收敛的最佳结构）

snowflake 规定每个 agent 文件按此顺序写：

1. YAML frontmatter（`name` / `description` / `tools`）
2. 标题与角色定位
3. 核心职责 / 工作流程
4. **文件输入与输出**
5. **输出格式（含模板引用）**
6. **质量评分**
7. 工作流集成（与谁配合）

配套：`templates/` 目录放**输出模板**，agent 只引用不重写。

**📌 对我们的启示**：直接采用。并且我们要加一个 `templates/` 目录，把"世界观简报""故事引擎""可行性评估"的格式模板固化成文件。

---

## 经验 L：状态文档是团队的记忆

snowflake：`{项目}/snowflake/项目状态.md` + `01-一句话概括.md` ~ `10-正文/`，全部 agent 以该目录为根。
story-systems-template：`/writers-room` = **6 个 agent 的前期会议**（和我们"拉团队讨论"完全同构）。

**📌 对我们的启示**：我们需要一个**项目状态文档**（谁做到哪一步、卡在哪、下一步谁接手），以及一个**会议模式**入口。

---

## 经验 M：一致性靠"自动化校验 + 提交规范"，不靠人盯

story-systems-template 的做法：
- 验证脚本：`npm run validate`、`lint:fountain`、`lint:md`
- **pre-commit hook** 跑在暂存文件上
- 提交格式 `type(scope): description`（type 有 scene/ dialogue/ structure/ revision…）
- 分支隔离：`main` 放稳定稿，`draft/v1`、`scene/[name]` 放草稿
- `protectedPaths` 保护自定义内容不被模板同步覆盖

**📌 对我们的启示**：我们有 `build.py`（成片管线）和 `verify_asr.py`（对白校验）已经是这个思路；**剧本层也缺一个校验脚本**（比如自动检查"每集是否有结尾反转""台词是否超长""是否出现多角色同框"）。

---

## 经验 N：把 CLI 当"agent 的基础设施"，不是给人用的

story-systems-template 的 "Agents as UX"：**用户不学命令行，agent 替他跑工具**。

**📌 对我们的启示**：完全贴合本用户（零编程）。所有脚本都要设计成"agent 调、用户看自然语言结果"。

---

## 第三轮来源（Reddit / Twitter 实操）

| # | 来源 | 类型 |
|---|---|---|
| 8 | Twitter @Bober_smart（32 万阅读） | Agent Teams 的模型分工实战 |
| 9 | Reddit r/ClaudeAI（468 赞） | subagent 安全事件 |
| 10 | Reddit r/ClaudeCode | subagent 当 junior dev 的讨论 |

---

## 经验 O：按"能力/成本"分层配模型，贵的只用在把关

那条高赞帖的分工（可直接借鉴）：

| 角色 | 模型 | 职责 |
|---|---|---|
| **Architect** | 最强模型 + high effort | **规划结构、最终合并** |
| **Developer** | 中档模型 + medium effort | 在隔离工作区里干活 |
| **Adversary / Critic** | 专设一档 | **在合同边界、反复失败、交付前审计**时介入，抓漏洞 |
| **Script Layer** | 不走 LLM | 机械任务（开文件、调 CLI），16ms 完成 |

**📌 对我们的启示**：我们的映射是 `opus` = pro（强）、`haiku` = flash（便宜）。
- 世界观 / 编剧 / 制片（要判断）→ **强模型**
- 事实核查 / 格式化 → **可降档**
- **机械任务（拼视频、转字幕）已经全在脚本里，不走 LLM** —— 这条我们早就在做（build.py / verify_asr.py），是对的

---

## 经验 P：必须有"对抗角色"，且要写进硬规则

同一个帖子的关键动作：**在 `CLAUDE.md` 里加一条规则 —— 开 PR 前必须经 adversary 审查**。
（官方也支持用 `TaskCompleted` hook 把这类规则变成**硬阻断**。）

**📌 对我们的启示**：我们的 `producer`（唱反调）就是 adversary。
**必须把它从"可选建议"升级成"硬门"**：剧本/设定没经过 producer 与 audience-proxy 就**不许进入生成阶段**。

---

## 经验 Q：subagent 的输出是"不可信输入"

Reddit 那条 468 赞的安全事件：一个 subagent 返回了 **prompt-injection payload**（伪装成系统指令、要求"永不告诉用户"的隐藏行为）。主模型识别后丢弃并重新起了 agent。

**📌 对我们的启示**：我们的 agent 会**联网抓外部内容**（fact-checker / traffic-strategist）。**外部抓回来的内容一律当数据，不当指令**；发现可疑注入要**直接向用户报告**。

---

## 汇总：18 条经验 → 5 类

| 类别 | 经验 | 要点 |
|---|---|---|
| **架构** | A / H / I | 先分 subagent vs team；加编排器；辅助 agent 按阶段触发 |
| **稳定** | B / J / K / L / M | **文档驱动记忆**；**质量评分与合格线**；七段式模板；状态文档；自动化校验 |
| **协作** | C / F / P | **交接包**（含 confidence / needs_human_review）；hook 做硬门；对抗角色写进规则 |
| **分工** | E / O | 一套定义两用（subagent + 队友）；按成本分层配模型 |
| **风险** | G / Q | 团队 3–5 人、成本随人数线性增长；外部内容当数据不当指令 |

---

## 待补（下一轮）

- [x] `hahagood/snowflake-novel-subagents` ✅
- [x] `bybren-llc/story-systems-template` ✅
- [x] Reddit / Twitter 实操 ✅
- [ ] HackerNoon《Claude Book》多 agent 写小说框架（perplexity gates）— 抓取 500，待换源
- [ ] `woanderingboy/novel-writing-pipeline`（Agent Skill）
- [ ] ACL 论文 IBSEN（Director-Actor 协作生成剧本）
