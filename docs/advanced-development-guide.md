# Krow Agent SDK — 进阶开发最佳实践

> 给"已读完 [`quickstart.md`](./quickstart.md)、写过第一个 plugin"的外部开发者。
> 本文档解释**写 plugin 的实战最佳实践**，让你的 plugin 能与 SDK 主路径协同得当（不撞规则、不翻车、不踩坑）。
> 阅读节奏：约 60 分钟通读 + 写 plugin 时按需回查。
> 本文档与 SDK 主仓内部使用的 [`AGENTS.md`](https://pypi.org/project/krow-agent-sdk/) 元规则同源（提炼对外公开级内容）。

> **本文档与 [`concepts/`](./concepts/) 目录的边界**（按 [Diátaxis](https://diataxis.fr/) 框架）：
> - 本文档 = **How-to**（"应该怎么写好 plugin"）— 实战最佳实践 + 反模式
> - [`concepts/`](./concepts/) = **Explanation**（"krow 内部如何工作 / 为什么这样设计"）— Agent lifecycle / Progressive Execution / Budget / ConcludeGuard / ExperienceMemory
> 两者互补，不重复。如果你想理解机制而不仅仅是"按规矩写"，先去看 `concepts/`。

---

## 目录

| 章节 | 主题 | 何时读 |
|---|---|---|
| §0 | 价值观（准确性 > 完整性 > 速度 > 成本） | 写代码前 |
| §1 | TURBO 哲学（两条总则：①语义/语法分工 System 1/System 2 + ②finished artifact 优先 + 近因效应锚定） | 设计任何决策前 |
| §2 | Plugin 设计 5 大原则（SSOT / OCP / SRP / DRY / 复用） | 写 plugin 前 |
| §3 | ToolPlugin 设计哲学（功能强大 + Agent 友好接口） | 写 ToolPlugin |
| §4 | ACTPlugin / extended.md 编写最佳实践 | 写 ACTPlugin |
| §5 | HintPlugin / GatePlugin / EventListener 边界 | 写其它 plugin |
| §6 | 关键基础设施速查（公开 SDK 暴露的接口；§6.8 = 策略自动路由的默认行为与开关） | 写代码时按需 |
| §7 | 测试方法论（Plugin 单测 + record/replay + 真实 LLM 验证） | 验收前 |
| §8 | 反模式黑名单（铁证支撑） | 写完前 review |
| §9 | 双环元认知与运行时自进化（快环软提示 + 慢环睡眠蒸馏 / overlay） | 想观测/维护 agent 自进化 |
| §10 | 配置决策脑三注册表 + 控制反射带（观测层 / 唤醒层 / 结算层 / 致动 + 领域轴 + 零注册信号包络） | 想让决策脑对你的任务"看得见、叫得醒、算得清、动得了手" |
| §11 | 多 Agent 轻量协同（A 侧 persona + B 侧 delegate） | 需要多角色分工 |
| §12 | 对话槽硬绑 ACT + 工具宇宙裁剪 | 需要按会话收窄工具面 |

---

## §0 价值观（**最上位约束**）

### 0.1 排序

> **准确性 > 完整性 > 速度 > 成本**

| 价值 | 含义 | 你写 plugin 时的体现 |
|---|---|---|
| **准确性** | 输出结果正确 / 不胡编 / 不撒谎 | 错就 fail-loud；宁可少做、不可做错 |
| **完整性** | 该交付的产物完整、不缺页、不缺字段 | 一次任务的所有产物全交付 + 自我验收 |
| **速度** | 用户可感知的延迟与吞吐 | 在准确 + 完整的前提下优化；不为速度牺牲前两项 |
| **成本** | LLM token / 计算 / 存储 | 在前三项已达标后才优化；不为省 token 砍准确性 |

### 0.2 判定冲突

| 冲突 | 选哪个 |
|---|---|
| 速度 vs 准确性 | **永远选准确**（错的快没意义） |
| 成本 vs 完整性 | **永远选完整**（少交付一半价值丢失 50%+） |
| 完整性 vs 准确性 | **选准确**（部分正确比全部错的好） |

### 0.3 反模式（铁证）

| 反模式 | 为什么错 |
|---|---|
| 为了"看起来快" 上 cache 跳过 LLM | 牺牲准确性换速度 → 业务价值倒挂 |
| 用启发式 / regex 替代语义判断 | 同上；语义问题应交给 LLM（详 §1） |
| 不确定时 try/except 吞错继续 | 用户拿到错误结果也不知道；应 fail-loud |
| 跑到一半超 token / 网络抖动就吐部分结果说"差不多了" | 完整性破坏；应重试或明确告知不完整 |

> **核心铁律**：你的 plugin 失败了不丢人，**默默给错的结果**才是大事故。任何不确定的状况优先 fail-loud。

---

## §1 TURBO 哲学（**Krow Agent 的灵魂**）

### 1.1 一句话总结（**TURBO = 两条总则**）

TURBO 哲学由**两条总则**构成，未来你只需记住"TURBO 哲学"这一个概念即涵盖两条：

> **总则①（分工）："语义交给 LLM、语法交给系统。"**
> 非确定性的语义 / 决策 / 创意 → LLM（System 2）；确定性需求 → System 1 工具 / 闸门。详 §1.2–§1.5。
> **总则②（喂料）："给 LLM 成品，不给零件"（finished artifact 优先 + 近因效应锚定）。**
> 给 LLM 的应是**可直接 COPY VERBATIM 的最终产物**（vendor 模板 / spec_lock SSOT / 完整片段），
> 而不是一堆语法说明书让它自己拼；长链路关键步骤前用**近因效应**让 LLM 回顾 finished artifact 锚定方向，保证不偏移。详 §1.6。

两条总则同源：都在**把 LLM 该做的留给 LLM、把 LLM 不必做的挪走**——总则①挪走确定性计算，总则②挪走"从零件拼装成品"的认知负担。反面统称 "Syntax 代偿 Semantic"（详 §1.9 反模式 D）。

### 1.2 双系统架构（总则①）

| 维度 | System 1（系统 / fast / syntax） | System 2（LLM / slow / semantic） |
|---|---|---|
| **职责** | 机械校验、错误信号结构化、协议守门、确定性查表、精确数值 / 几何计算 | 理解、生成、决策、风格、叙事、创意 |
| **特征** | 可被 unit test 100% 覆盖、零成本、毫秒级、行为可重放 | 需要 prompt 工程、有不确定性、按 token 计费、秒级～分钟级 |
| **范例** | 几何计算 / 颜色对查表 / 工具优先级排序 / Gate 8 闸门 | 写 SVG / ReACT 推理循环 / brief 解析 |
| **绝不混做** | System 1 工具内**禁止调 LLM**（性能 + 可重放性死线） | System 2 hint 不要让 LLM 做 cos/sin / 颜色对比度查表（出工具） |

### 1.3 写 plugin 时的判定 3 步

写**任何** plugin 代码 / hint / prompt 之前，先答这 3 个问题：

1. **能不能让系统侧 fail-loud 闸住？**
   - 能 → 写闸门（GatePlugin / 工具入参校验），**不准**用 hint 提醒 LLM
2. **能不能封装成 System 1 确定性工具让 LLM 调？**
   - 能 → 写 ToolPlugin，hint 里只列工具名 + 调用时机
3. **是不是真的"语义/决策/创意"问题？**
   - 是 → 才允许写 hint / prompt，且必须带"铁证"

### 1.4 反模式（铁证级）

#### 反模式 A："PNG 旁路反模式"（System 1 没闸住，靠 hint 教 LLM）

**场景**：发现 LLM 把某个工具的 `use_compat_mode=True` 当逃生口，结果不准。

| ❌ 错误 | ✅ 正确 |
|---|---|
| 把"严禁翻参数"写在 hint 里反复警告 | 物理移除该参数（System 1 闸住）/ 工具入口归一化掉 |

**铁律**：能让代码闸住的，就**不要**写在 hint 里教 LLM。LLM 会忘 / 误读 / 优先 short-cut。

#### 反模式 B：让 LLM 凭感觉算几何 / 配色

| ❌ 错误 | ✅ 正确 |
|---|---|
| hint 里写"请仔细配色避免撞色" | 写一个 `pick_color_pair(palette, conflict_set) -> (fg, bg)` 工具 |
| hint 里写"请让两个图形对齐" | 写一个 `align_horizontal(elements) -> coords` 工具 |
| LLM 算 `cos(45°) * 100` | 工具内做 `math.cos(math.radians(45)) * 100`，输出给 LLM 用 |

#### 反模式 C：System 1 工具内调 LLM

ToolPlugin 内部**绝不能** `import openai` / `import httpx` 调 LLM。这违反 TURBO 边界，破坏 unit test 100% 覆盖能力。

如果工具确实需要 LLM 输出，**让 ToolManager 之外的 ACT 调度逻辑**处理（即由主 agent 调用一个 LLM-driven 路径替代该工具）。

### 1.5 实战决策树

写一行新代码前，问自己：

```
这件事是确定性的（输入 → 唯一输出）吗？
├─ 是 → System 1（写工具 / 闸门 / 入口归一化）
│        测试用 unit test 覆盖；零成本
└─ 否（涉及理解 / 生成 / 决策） → System 2
        让 LLM 来做；测试用 record/replay
```

**举例 1**：判断"用户输入是否含敏感词" → 关键词列表查表 → System 1
**举例 2**：判断"用户输入语义上是否在抱怨产品" → 需要理解 → System 2
**举例 3**：把 markdown 转 HTML → 确定性映射 → System 1（用 markdown 库）
**举例 4**：写一个段落总结 → 创意生成 → System 2

### 1.6 finished artifact 优先 = 总则② · LLM-first 三件套（**Krow Agent 核心架构选择**）

> 这是 §1.1 **总则②"给 LLM 成品，不给零件"的落地**。源自一次真实迁移的元复盘：某"用 700 行 finished artifact 输入"的实现，在最终视觉/语义质量上反而 **1.9–2.0×** 碾压了另一套"用 5 万行 python 补丁后处理"的实现——喂给 LLM 的是成品而非零件，模型的复用能力被真正释放。写完整套 plugin 后回看这一节做对照检查。

**核心信念**：**LLM 能力在快速进步, 你的 plugin 代码量应在收缩, 而不是膨胀**.

**为什么这是总则**：LLM 最擅长的是"看懂一个成品 → 照着改两笔产出新成品"（复用），最不擅长的是"从零件说明书 + 一堆散提示 → 自己拼装成品"（易漏、易偏、易返工）。总则② = 永远把前者喂给 LLM。

#### 第 1 件: finished artifact 输入

给 LLM 的应当是**可直接复用的产物**, 不是构建产物所需的零件.

| ❌ building blocks (LLM 自己拼) | ✅ finished artifact (LLM 复用) |
|---|---|
| 返回结构化 JSON `{geometry: {center_x: 480, ...}}` 让 LLM 拼 SVG | 返回完整 SVG 段 `<line x1="480" y1="120" .../>` 让 LLM COPY |
| Hint: "请配色避免撞色" + 调用 `pick_color_pair(...)` 工具 | Hint: "已选色: `fg=#1a3c6e, bg=#ffffff (contrast=8.4)`, 请直接用" |
| 文档说明 + 多个工具组合 | 一个 markdown 段 LLM 直接 30s 完成 |

**判定**: LLM 看完是否 **30 秒内能产出最终结果**? 是 → finished artifact. 否 → building blocks.

#### 第 2 件: post-hoc gate (验证 + fail-loud)

System 1 闸门只 **验证 + 报错**, **不**替 LLM 修复.

```python
# ❌ syntax 代偿 (替 LLM 改完, silent continue)
def normalize_svg(svg: str) -> str:
    return svg.replace("&", "&amp;")  # 自动补 LLM 漏的 escape

# ✅ post-hoc gate (验证 + 报错让 LLM 重做)
def validate_svg(svg: str) -> Optional[ToolError]:
    try:
        lxml.fromstring(svg.encode(), parser=lxml.etree.XMLParser(recover=False))
        return None
    except lxml.etree.XMLSyntaxError as e:
        return ToolError(
            code="LLM_SVG_NOT_WELL_FORMED",
            message=f"❌ SVG 不合法 (line {e.lineno} col {e.offset}). 请检查 & 是否转义为 &amp;, 标签是否闭合.",
        )
```

**判定**: 出错时, 系统是 **告诉 LLM 错了让它重做** 还是 **替 LLM 改完静默 continue**? 前者 = 真 gate; 后者 = syntax 代偿.

#### 第 3 件: vendor 风格库

用 markdown 参考库 + SSOT 锚定 LLM 风格, 不靠 python 算法.

```
your_plugin/
├── refs/
│   ├── style_modern.md      # vendor 风格 1: 现代极简
│   ├── style_business.md    # vendor 风格 2: 商务深沉
│   └── style_creative.md    # vendor 风格 3: 创意活泼
├── spec_lock.md.template    # SSOT 模板: 主色 / 字号 / 品牌锚
└── tool_load_vendor.py      # 工具: LLM 调它选 vendor + 注入 prompt
```

LLM 流程: `tool_load_vendor(style="modern")` → 工具返回 `refs/style_modern.md` 完整 markdown → LLM 看完 COPY + 改文本/颜色锚定 `spec_lock.md`.

**对照**: 不要写一个 `python_style_engine.py` 算法自动选风格 + 生成 — 这是 building blocks + syntax 代偿双反.

#### 第 4 件: 近因效应锚定 (长链路关键步骤前回顾 finished artifact)

LLM 注意力呈 U 型曲线——开头 (primacy) 和**结尾 (recency)** 最受重视，中段最易被稀释。长链路（多页生成 / 多步 ReACT / conclude 前）里，如果 finished artifact（vendor 模板 / spec_lock SSOT / 风格锚）只在**最开头**注入一次，跑到后面就会被中间大量上下文冲淡 → 方向漂移（配色跑偏 / 字号不一致 / 忘了品牌锚）。

**做法**：在每个关键步骤**动作前**，把该步真正要遵守的 finished artifact 段**重新放到 prompt 近端**（结尾）让 LLM 现场回顾，而不是依赖它记住开头看过的东西。

| ❌ 只在开头注入一次 | ✅ 关键步骤前 recency 回顾 |
|---|---|
| system prompt 开头贴 spec_lock，之后 20 页全靠 LLM"记住" | 每页渲染前把该页的 spec_lock 段重贴到 prompt 尾部 |
| conclude 前不重申验收标准（DoD） | conclude 前把 DoD / 成品范例重贴到近端再让它自检 |

**落地手段**：用 `HintPlugin` 的 `should_inject(task_context)` 做条件注入（按当前 step 分流，把对应 finished artifact 段放到高优先级/结尾段）；或用 `PromptPriority`（`CRITICAL` primacy + 结尾 recency，详 §11.2）控制物理顺序。**判定**：你的关键步骤是不是"LLM 现在就能看到它该 COPY 的那份成品"？还是"指望它记得 50 条消息之前看过"？

### 1.7 度量指标: syntax/semantic 比 (plugin 健康度)

```
syntax_semantic_ratio = (你 plugin 月度新增 python LOC) / (LLM 月度 token 消耗 / 1000)
```

| 比值 | 健康度 | 你该做什么 |
|---|---|---|
| < 0.5 | ✅ LLM-first 健康 | 继续维持 |
| 0.5 - 2.0 | ⚠️ 警告 | retrospect "这些补丁是否替代了 LLM 决策" |
| > 2.0 | ❌ syntax 代偿失控 | 强制 retrospect + 撤补丁路线图 |

**举例** (反模式触发器): 你的 plugin 上月加了 800 行 python 但只多花了 100k token (ratio = 8.0) → 强警告. 说明你在用 python 替 LLM 做事.

### 1.8 升级 LLM 模型时的强制复检

每次 LLM 模型 major version bump (qwen3.6 → qwen3.7 / claude-4.6 → claude-5.0 等):

1. **全量回归补丁层** — 跑 syntax/semantic 比历史趋势
2. **选 N 个补丁做 A/B** — 开 vs 关, 关掉后 LLM 输出是否还达标
3. **撤掉所有"能撤"的补丁** — 开 PR 独立 review
4. **沉淀复检报告** 到

**铁律**: 模型升级周期是**撤补丁的窗口**, 不是堆补丁的窗口.

### 1.9 反模式 D-G (来自 ppt-master 元复盘)

#### 反模式 D: "Syntax 代偿 Semantic" (主反模式)

用确定性 python 算法 / 后处理替 LLM 做语义/审美/创意决策, 累计 N 个补丁 = LLM 边界被持续侵蚀.

铁证: PISMA-SVG 5万行 vs ppt-master 700 行, 视觉效果反胜 1.9-2.0×.

#### 反模式 E: "补丁累积惯性"

升级 LLM 模型时不撤旧补丁, 让 LLM 进步红利被代码层困住.

#### 反模式 F: "building blocks 反 finished artifact"

给 LLM 喂工具输出零件 JSON 让它自己拼装, 而非可 COPY VERBATIM 的完整产物.

#### 反模式 G: "覆盖率绿但视觉差"

单元测试 100% 绿但视觉/语义级 metric 持续逊于 baseline (没人测整体输出质量).

**判定铁律**: 任何 LLM-facing 模块必须有**视觉/语义级 metric** (字数 / 元素密度 / 像素 diff / NPS / ...) 作为 PR 验收门, 不只看代码 coverage.

---

## §2 Plugin 设计 5 大原则

### 2.1 SSOT (Single Source of Truth)

**定义**：任何元数据 / 配置 / 协议**只能有一份权威定义**。

| 维度 | 应放在哪 |
|---|---|
| Plugin 暴露的工具列表 | `ToolPlugin` 类内的 `get_tools()` 方法 |
| Plugin 配置 schema | `PluginConfig` dataclass 里 |
| 错误码与 message | 集中常量类（不要散在多处 raise） |
| Plugin 元数据（name / version / author） | `entry_points` group `krow.plugin` 内 |

**禁止**：

- ❌ 在 `__init__.py` 写一遍 tool 列表，然后在另一个 yaml 又写一遍 → 早晚漂移
- ❌ Plugin A 内写一份 ACT 配置，Plugin B 又复刻一份 → 两边走错路

### 2.2 OCP (Open-Closed Principle)

**定义**：对扩展开放、对修改关闭——加新能力**不应**改老代码。

| 准则 | 推荐 | 反例 |
|---|---|---|
| 新增功能加参数（带 default） | `read_file(path, start_line=None, encoding="utf-8")` | 加新工具 `read_file_v2` |
| 行为分流用 enum 字符串 | `mode="strict" / "lenient"` | `_strict_internal=True` 私参 |
| 复杂参数用 dict | `options={"compact": True}` | 10 个独立参数 |
| 不破坏旧调用 | 加新参数必须有 default；改 default 走灰度协议 | 直接改 default 让所有旧调用失效 |

**Plugin 视角的 OCP**：

- 你的 ToolPlugin 升级 v1 → v2 → v3 时，**老用户调用方式不变**（参数加 default）
- 加新工具 → 加新 `Tool` 子类，不改老 `Tool`
- 改 ACT 行为 → 加新 ACT 配置 enum，不改老 ACT yaml

### 2.3 SRP (Single Responsibility Principle)

**定义**：每个模块 / 函数 / 类只做一件事。

| Plugin 类 | 职责 |
|---|---|
| `ToolPlugin` | 提供工具集，每个工具单一动作 |
| `HintPlugin` | 提供软提示，**不**做参数校验 / 防御逻辑（那是 GatePlugin / 工具入口的事） |
| `GatePlugin` | 提供 fail-loud 守门，**不**做内容生成（那是 LLM 的事） |
| `EventListenerPlugin` | 监听事件 + 落审计，**不**改 agent 状态 |
| `ObservabilityPlugin` | metric / trace 输出，**不**做错误处理（那是 plugin 自己的事） |

### 2.4 DRY (Don't Repeat Yourself)

**定义**：同一段逻辑 / 文案 / schema 不准在多处出现。

**反模式**：

| 反例 | 修法 |
|---|---|
| 3 个工具内各自实现"路径转绝对路径"逻辑 | 抽 `_to_absolute(path) -> Path` 共享 |
| Hint 文本里同一句话写 3 遍（不同位置） | 抽常量；动态拼接 |
| 多个 plugin 各自校验"API key 格式" | 用 SDK 提供的 `validate_api_key()` 公共函数 |

### 2.5 复用 > 重造（**最关键**）

**写代码前的"造轮子检查"4 步**：

1. **Grep SDK 内现有 API** — 用主题关键词搜，命中 → 优先复用
2. **看 §6 基础设施清单** — 是不是已有现成 API（EventBus / ToolManager / etc.）
3. **看 SDK 文档** — quickstart.md / 本文 §6 是不是已有相关引导
4. **真没有再造轮子** — 但要在 GitHub Discussions 提一下"是不是 SDK 缺这个能力"

**反模式**（高频踩坑）：

- ❌ 在你的 plugin 内写一个新 EventBus → SDK 已有 `from krow_agent_sdk import EventBus`
- ❌ 在你的 plugin 内写一个 LLM client → SDK 已有 `from krow_agent_sdk.replay import LLMReplayStore`
- ❌ 在你的 plugin 内写文件 watch / 路径解析 → SDK 已有 helpers

---

## §3 ToolPlugin 设计哲学（**LLM 视角，不是程序员视角**）

### 3.1 基本原则

> 工具是给 **LLM** 用的，不是给程序员用的。所有设计按"LLM 视角"做 trade-off。

| 维度 | 原则 | 反例 → 推荐 |
|---|---|---|
| **数量** | 少而灵活：> 5 个工具共享同一动词 = 应合并 + 参数分流 | `pptx_create_freeform/grid/chart/table/...` 8 个 → `pptx_render_page_svg(page_kind=...)` 1 个 |
| **命名** | 动词在前 + 明确宾语 + 下划线小写 + 不带版本号 + 域前缀 | `file_reader_v2` → `read_file` |
| **输入鲁棒** | 接受多种格式（路径/enum 大小写/单值或 list/JSON 字符串或 dict）+ 自然语言 + 空值容错 | strict 类型 → 入口 `_normalize_input()` 归一 |
| **输出格式** | 自然语言/markdown > 平铺 JSON > 嵌套 JSON > 二进制；关键字段在首尾 | `{matches:[{file:{path,meta},loc:{line}}]}` 嵌套 → `{ok, summary, file, line, snippet}` 平铺 |
| **错误信息** | 黄金模板：一句话 + 原因 + 位置 + 1-3 个修法 + 相关链接 | `Error: invalid input` → `❌ 参数 page_kind 必须是 freeform/grid/chart/table 之一，你传了 'free'。修法：1) 改成 'freeform'；2) 调 pptx_list_page_kinds 看完整列表` |

### 3.2 命名规范（强约束）

**好命名**：

```
read_file
search_files
write_file
pptx_render_page_svg     ← 域前缀 pptx_ + 动词 render + 宾语 page_svg
excel_compute_formula
web_search
save_note
```

**坏命名**：

```
FileReader               ← PascalCase（Python 不爱）
read_file_v2             ← 带版本（OCP 反例）
pptx_create_v3_full      ← 同上
get_data                 ← 太泛；不知道做啥
helper_util              ← 不是动词宾语结构
```

### 3.3 入参鲁棒（LLM 经常输错）

LLM 给你的入参**100% 不可信**。要在工具入口做归一化：

```python
def my_tool(
    paths: Union[str, List[str], None],     # LLM 可能传单 str / list / None
    mode: str = "strict",                    # LLM 可能写 "Strict" / "STRICT" / "strict"
    options: Union[dict, str, None] = None,  # LLM 可能传 JSON 字符串
):
    # 入口归一
    if paths is None or paths == "" or paths == []:
        return _empty_result("paths 不能为空")
    if isinstance(paths, str):
        paths = [paths]
    paths = [_to_absolute(p) for p in paths]

    mode = mode.lower().strip()
    if mode not in {"strict", "lenient"}:
        return _error(f"mode 必须是 strict/lenient，你传了 '{mode}'")

    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            return _error("options 不是合法 JSON")
    options = options or {}

    # ... 真实逻辑
```

### 3.4 输出格式（LLM 视角）

**优先级**：自然语言 / markdown > 平铺 JSON > 嵌套 JSON > 二进制。

**好输出**：

```python
return {
    "ok": True,
    "summary": "找到 3 个匹配文件",
    "files": [
        {"path": "/a.py", "line": 10, "snippet": "def foo():"},
        {"path": "/b.py", "line": 25, "snippet": "foo()"},
    ],
}
```

**坏输出**：

```python
return {
    "result": {
        "data": {
            "items": [
                {"file": {"meta": {"path": ..., "size": ...}}, "loc": {"start": ..., "end": ...}}
            ]
        },
        "metadata": {"timestamp": ..., "version": ...}
    }
}  # 嵌套 4 层；LLM 取数据要 result.data.items[0].file.meta.path
```

### 3.5 错误信息黄金模板（**强制**）

```
❌ <一句话发生了什么>。
   原因：<根因>
   位置：<出错的具体参数 / 路径 / 行>
   修法：
     1. <最常见的修法>
     2. <备选修法>
     3. （可选）<更多上下文>
   相关：<相关工具 / 文档链接>
```

**好错误**：

```
❌ 参数 path 不存在该文件。
   位置：path = "./missing.py"
   修法：
     1. 检查路径拼写
     2. 调 search_files(name="missing.py") 看是否换了名
     3. 是新文件 → 先调 write_file 创建
   相关：read_file / write_file / search_files
```

**坏错误**：

```
Error: invalid argument
```

### 3.6 OCP 扩展性

| 准则 | 推荐 | 反例 |
|---|---|---|
| 新功能加参数（带 default） | `read_file(path, start_line=None, encoding="utf-8")` | 加新工具 `read_file_v2` |
| 行为分流用 enum 字符串 | `mode="strict" / "lenient"` | `_strict_internal=True` 私参 |
| 复杂参数用 dict | `options={"compact": True}` | 10 个独立参数 |
| 加新输出字段 | 始终 ok 返回 + 新字段直接加（不破老调用方） | 改返回结构搞 v2 |

### 3.7 红线

- ❌ ToolPlugin 内调 LLM（System 1 工具禁止 — TURBO 边界）
- ❌ 加 hint 教 LLM "别用某工具" → 物理移除工具 / `with_disabled_tools()` 闸住
- ❌ 工具数 > 5 共享同一动词 → 合并 + 参数分流
- ❌ 输出嵌套 3 层以上 JSON → 平铺
- ❌ 错误信息只说 "failed" → 黄金模板（含可执行修法）
- ❌ **零件契约反模式**：把一个产物拆成 N 个 `required` 字段让 LLM 分别填（详 §3.7.1）

### 3.7.1 成品契约 vs 零件契约（**input_schema 设计核心原则**）

> 由 zzp 团队 2026-05-25 cookbook 真跑反馈驱动；"教训 3"。
> 完整可执行 checklist + 双侧对照代码示例： glob 自动注入到 LLM 编辑 plugin 时）。

LLM 调你工具时填的 `arguments` 是**契约**。契约有两种形态：

| 契约类型 | 示例 | 模型友好度 |
|---|---|---|
| **成品契约**（finished artifact） | `write_doc(markdown_text: str)` | ✅ 高 — LLM 直接写完整 markdown 即可 |
| **零件契约**（building blocks） | `write_doc(title: str, content: str)` + 注释「content 不含 #」 | ❌ 低 — LLM 想"自己写完整 markdown"是本能, 注释约束不可强制 |

**铁律**：
- `required` 越多越脆——只列**没有合理 default、不能从其他字段推导**的字段
- 能从其他字段 fallback 推导的（如 `title` 可提 `content` 首 H1 / `output_path.stem`） → 改 optional + handler 内自动推导
- 涉及**纯系统侧 normalize** 的事（如独占行 `**xxx**` → `## xxx` / 去重 H1） → handler 内做后处理，**不靠 LLM 自律**

### 3.8 实战 checklist（写完 ToolPlugin 后过一遍）

- [ ] 工具数 ≤ 5？或合理分类？
- [ ] 命名都是动词在前？
- [ ] 入参支持 LLM 常见输入变形（str/list/None/JSON 字符串）？
- [ ] 输出 ≤ 2 层嵌套？关键字段在顶层？
- [ ] 错误都用黄金模板？
- [ ] 加新功能的接口能向后兼容吗？
- [ ] unit test 100% 覆盖（System 1 应该可以做到）？
- [ ] **input_schema `required` 列表是不是"没有合理 default 也不能从其他字段推导"**？
- [ ] **description 里有没有写"模型必须 / 模型不要"这类语义约束**？若有 → 抽出来在 handler 里做 System 1 闸门（normalize / fallback）
- [ ] **cookbook unit test 是否 mock 了"LLM 漏 required 字段"场景** → 断言 handler fallback 仍能产出可接受产物？

---

## §4 ACTPlugin 编写最佳实践

### 4.1 ACT 是什么

ACT (Activity / Capability Tier) = **一组工具 + 一份 hint 模板 + 一个语义意图**的捆绑。

LLM 不直接看完整工具列表（太长 → 注意力分散），而是按"当前任务意图"匹配出 1-3 个最相关的 ACT，每个 ACT 内的工具与 hint 才被注入到 prompt。

**简单类比**：ACT = 一个"工种"，里面有该工种的工具箱（tools）+ 工种说明书（hint）+ 招呼语（intent description）。

### 4.2 ACT 文件结构

```
my_plugin/
  acts/
    __act__.yaml              # ACT 元数据（必）
    extended.md               # 详细 hint（可选；按需加载）
    summary.md                # 简短摘要（必；hot path 注入 prompt）
```

**🔥 重要：extended.md 工具文档的两种写法（2026-05-27 PR-1/PR-2 新增）**

micro ReACT Phase-2 prompt 需要从 extended.md 提取**每个工具的完整契约**
（参数 / 输出 / 门禁）。SDK 解析器同时支持两种写法：

| 写法 | 适用场景 | 解析方式 |
|---|---|---|
| **写法 A（推荐）**：`### tool_name` heading + 参数表 + JSON 示例 | 工具数 ≤ 10，每工具有独立详细说明 | `_parse_extended` 主路径（精确） |
| **写法 B（兼容）**：markdown 表格列工具，cell 用反引号包围工具名 | 工具数 > 10，需要并排展示 step / phase / 门禁 | `_parse_extended_table_fallback`（自动识别） |

**两种写法对照范例**：

写法 A（参见主仓 `modules/agent/act/acts/native_fileops/extended.md`）：

```markdown
### data_analyst_read_csv

读取 CSV 元数据 + 前 10 行预览。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| path | string | 是 | 文件路径 |
| max_rows | integer | 否 | 预览行数（默认 10） |

```json
{"tool_name": "data_analyst_read_csv", "tool_args": {"path": "data.csv"}}
```
```

写法 B（适合复杂工程化 ACT，参见 cookbook `ext_data_analyst.md`）：

```markdown
## Phase 1 工具调用契约（按 step 排）

| Step | 工具 | 输入参数（精确名） | 输出字段 / 门禁 |
|---|---|---|---|
| 1 | `data_analyst_read_csv` | `path: str`, `max_rows: int=10` | `columns`, `dtypes`, `row_count` |
| 2 | `data_analyst_compute_stats` | `path`, `columns: list[str]` | `stats[col].{mean, std, min, max}` |
```

**判定准则**：

- 工具 ≤ 5 + 每工具有 10 行以上 know-how → **写法 A**
- 工具 > 10 + 工程化跨步骤契约（step / phase / 门禁矩阵）→ **写法 B**
- 两种**可同时用**（写法 A 章节会覆盖写法 B 表格行；SDK 优先 heading）

**⚡ 自动文档兜底（2026-05-27 PR-1）**：如果你只在 `ToolPlugin.get_tools()` 里
声明了 `input_schema`，SDK 会**自动**用 `ACTDocGenerator` 生成 `### tool_name +
参数表 + JSON 示例` 注入到 extended.md 末尾 —— **不用在 ACT markdown 里再写一遍参数表**。
你只需在 ACT extended.md 里写"跨工具约束 / 工作流 / 门禁"等 System 2 内容。
详 §4.9。

### 4.3 `__act__.yaml` 写法

```yaml
name: my_research_agent
display_name: 科研论文助手
intent_description: |
  帮用户读论文、写综述、做 BibTeX 引用。
  适用：用户提到 "论文" / "paper" / "arxiv" / "综述" / "literature review" 等关键词。
tools:
  - search_arxiv
  - read_pdf
  - extract_bibtex
  - summarize_paper
hint_files:
  summary: summary.md
  extended: extended.md     # 可选；只在 LLM 主动 call when_extended_needed 时才加载
require_acts: []              # 可选；本 ACT 依赖的其他 ACT
exclude_acts: []              # 可选；与本 ACT 互斥的 ACT
```

### 4.4 写 `intent_description` 的黄金法则

**目标**：让 LLM 在意图匹配时一眼能判断"该不该选我"。

| 准则 | 示例 |
|---|---|
| 用**用户关键词**触发，不用"专业术语" | `"用户提到 论文/paper/arxiv"` 而不是 `"学术文献检索"` |
| 列**典型场景**（不是抽象功能） | `"读 PDF + 抽 BibTeX"` 而不是 `"信息抽取"` |
| **明确不适用场景** | `"不适用：纯算法问题、代码题、数学题"` |
| 控制在 100-200 字 | 太长 LLM 不读完 |

**好范例**：

```yaml
intent_description: |
  帮用户读论文、写综述、做 BibTeX 引用。
  适用：用户提到 "论文" / "paper" / "arxiv" / "综述" / "literature review"
        / "参考文献" / "BibTeX" 等关键词。
  典型场景：读 PDF 抽 BibTeX、对比多篇论文、生成综述大纲、转引用格式。
  不适用：写代码题、数学推理、纯网页搜索（用 web_search ACT）。
```

**坏范例**：

```yaml
intent_description: 学术文献处理工具集。   # 太抽象，LLM 不知道用户问啥时该选我
```

### 4.5 写 `summary.md`（hot path）

**目标**：50-200 字让 LLM 知道"现在我手上有什么工具、什么时候该用"。

```markdown
# 📚 科研论文助手

| 工具 | 用途 |
|---|---|
| `search_arxiv(query)` | arxiv 检索（关键词或 arxiv ID） |
| `read_pdf(path_or_url)` | 读 PDF 文本（自动 OCR 兜底） |
| `extract_bibtex(text)` | 从论文文本抽 BibTeX |
| `summarize_paper(text, length=500)` | 论文摘要 |

**典型流**：
1. `search_arxiv` 找论文
2. `read_pdf` 拉全文
3. `extract_bibtex` + `summarize_paper` 二选一
```

**铁律**：

- 不要在 summary.md 里写长篇逻辑 → 写到 `extended.md`
- 不要把每个工具的全部参数列出来 → ToolManager 会自动注入工具签名
  （默认 500 字符上限覆盖 95% 工具；超长 schema 工具建议在 `extended.md`
  写法 A 里手写完整参数表 —— 详 §4.6 + §4.9）
- 用 markdown 表格让 LLM 一眼扫到

### 4.6 写 `extended.md`（按需加载）

**目标**：当 LLM 在某个具体任务上需要详细 know-how 时按需读。

#### 4.6.1 写法 A：`### tool_name` heading 风格（推荐）

```markdown
# 📚 科研论文助手 — 详细规则

### read_pdf

读取 PDF 文本（自动 OCR 兜底）。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| path_or_url | string | 是 | 本地路径或 arxiv URL |
| mode | string | 否 | "text" / "ocr_with_math"（默认 text） |

```json
{"tool_name": "read_pdf", "tool_args": {"path_or_url": "paper.pdf"}}
```

**何时调**：
- 用户给了 arxiv URL → `read_pdf(url)` 直接读
- PDF 含大量公式 → 加 `mode="ocr_with_math"`

### extract_bibtex

从论文文本抽 BibTeX。

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| text | string | 是 | 论文全文或 abstract |

**最佳实践**：
1. preprint 没 DOI → 手填 `arxiv_id` 字段
```

✅ **SDK 解析器精确识别每个工具**：
- `### read_pdf` heading → `all_tools["read_pdf"] = {description, parameters, examples}`
- micro ReACT Phase-2 prompt 看到完整契约

#### 4.6.2 写法 B：markdown 表格风格（工程化场景）

```markdown
# 📚 科研论文助手 — Phase 编排

## Phase 1：检索 + 读取

| Step | 工具 | 输入参数（精确名） | 输出字段 / 门禁 |
|---|---|---|---|
| 1 | `search_arxiv` | `query: str`, `max_results: int=10` | `papers: list[{title, abstract, pdf_url}]` |
| 2 | `read_pdf` | `path_or_url: str`, `mode: str="text"` | `text`, `pages_count`（`pages_count>0` 否则停） |

## Phase 2：抽取 + 摘要

| Step | 工具 | 输入参数 | 输出字段 / 门禁 |
|---|---|---|---|
| 3 | `extract_bibtex` | `text: str` | `bibtex_str`；缺 DOI → 手填 `arxiv_id` |
| 4 | `summarize_paper` | `text`, `length: int=500` | `summary_str`；length > 800 → 警告 token 上限 |
```

✅ **SDK 自动识别**：
- `_parse_extended_table_fallback` 扫表格，从 cell 反引号识别 `search_arxiv` / `read_pdf` / `extract_bibtex` / `summarize_paper`
- 写入 `all_tools[name] = {parameters: <表头+所在行>}`
- `_extract_tool_section_from_table` 按工具名返回完整表格段落 + 章节标题

#### 4.6.3 何时该写 extended.md

| 情形 | 该写吗 |
|---|---|
| summary.md 已塞不下、LLM 需详细 know-how | ✅ 写 |
| 信息太杂 | ❌ 拆多个 ACT |
| 信息只 1-2 条 | ❌ 直接加到 summary.md |
| 工具只在 `ToolPlugin.get_tools()` 注册了 schema | ⚠️ **不一定要写**——SDK 会自动生成（详 §4.9） |

### 4.7 ACT hint 反模式

#### 反模式 A：在 hint 里写"严禁 / 不要"

| ❌ 错误 | ✅ 正确 |
|---|---|
| hint："严禁直接调 `os.system`" | 不暴露 `os.system` 工具（System 1 闸住） |
| hint："不要在用户没确认前删文件" | 在 `delete_file` 工具入口加确认 prompt（System 1 闸住） |

**铁律**：能让 System 1 物理闸住的，就**不要**写在 hint 里教 LLM。

#### 反模式 B：hint 与工具签名重复

ToolManager 自动注入每个工具的签名（参数 + docstring）。如果你在 hint 里又把签名写一遍 → DRY 违反 + 早晚漂移。

**正确**：hint 里只写"何时调用、串用顺序、典型组合"，**不**写参数细节。

#### 反模式 C：让 hint 长篇大论

LLM context 是稀缺资源。一个 ACT 的 hint 加起来 > 2K token → 反模式。

**修法**：

- 把详细规则拆到 extended.md（按需加载）
- 把多余规则下沉到工具入口归一化（System 1）
- 把铁律下沉到 GatePlugin（System 1）

### 4.9 SDK 自动工具文档生成（2026-05-27 PR-1）

**问题**：开发者写 ACT extended.md 时，常常被迫**手写**每个工具的参数表
（因为担心 LLM 不知道参数名 / 类型）。结果：

- 工具改 schema 后忘了同步文档 → LLM 看到过时签名 → 调用失败
- 多个 ACT 引用同一工具 → 参数表在多处复制 → DRY 违反
- 写 30+ 个工具的参数表 → 上手成本爆炸

**SDK 自动兜底**：当你在 `ToolPlugin.get_tools()` 里声明工具 spec 时：

```python
class MyAnalyticsToolPlugin:
    plugin_id = "myorg.analytics"

    def get_tools(self):
        return [{
            "name": "data_analyst_compute_stats",
            "description": "对 CSV 数值列做 mean/std/min/max 统计",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "CSV 路径"},
                    "columns": {"type": "array", "items": {"type": "string"}, "description": "要统计的列名"},
                },
                "required": ["path", "columns"],
            },
            "handler": _compute_stats_handler,
        }]
```

**SDK 自动做的事**（`modules/agent/sdk/auto_tool_doc.py`）：

1. 注册时调 `ACTDocGenerator.generate_tool_doc(spec)` 生成完整 markdown：
   ```markdown
   ### data_analyst_compute_stats

   对 CSV 数值列做 mean/std/min/max 统计

   | 参数 | 类型 | 必填 | 说明 |
   |---|---|---|---|
   | path | string | 是 | CSV 路径 |
   | columns | string[] | 是 | 要统计的列名 |

   ```json
   {"tool_name": "data_analyst_compute_stats", "tool_args": {}}
   ```
   ```

2. 缓存到进程级 SSOT `_TOOL_DOC_REGISTRY[tool_name]`
3. ACTPlugin 加载时注册 `extended_md_supplement_provider`，按需把工具文档拼接注入到对应 ACT 的 `extended.md` 末尾
4. `_parse_extended` 重新 parse 合并后的内容，`all_tools` 全部可用
5. micro ReACT Phase-2 prompt 看到所有工具完整契约

**防重复注入**：若你在 ACT extended.md 已手写 `### <tool_name>` heading（说明
你主动覆盖了 SDK 默认文档），SDK 会跳过该工具的自动注入 —— 避免 prompt 翻倍 +
DRY 违反。

**Rollback**：env `KROW_SDK_AUTO_TOOL_DOC=false` 关闭自动生成。

**判定准则**：

| 你需要做的事 | 怎么做 |
|---|---|
| 让 LLM 知道工具有什么参数 | 仅在 `ToolPlugin.get_tools()` 写 `input_schema` —— SDK 自动生成 |
| 给 LLM 加跨工具约束（"先 A 再 B"） | 在 ACT extended.md 写 `## Phase 工作流` 章节 |
| 给某个工具加业务级硬规则 | 在 ACT extended.md 写 `### tool_name`（覆盖 SDK 默认） |
| 防 LLM 调用错误参数值 | 用 `GatePlugin` System 1 闸住，不要写在 hint 里 |

### 4.10 自检：ACT 是否被正确解析

**典型病症**：写完 ACT 后跑 plan_task，发现 LLM 凭工具名瞎填参数 / 跳步骤 / 顺序错。
高概率是 ACT 解析失败 → micro ReACT prompt 空空。

**5 分钟自检脚本**：

```python
# tests/test_my_act_loading.py
def test_my_act_doc_coverage():
    """反退化 test：保证 ACT extended.md 被 SDK 正确解析。"""
    from modules.agent.act.act_hierarchy import get_hierarchy_loader

    loader = get_hierarchy_loader()
    extended = loader.load_extended("ext_my_act_name")

    assert extended is not None, "ACT 加载失败"
    # 覆盖率断言：声明的工具数 vs 解析出的工具数
    declared_tools = ["my_tool_a", "my_tool_b", "my_tool_c"]
    parsed = set(extended.all_tools.keys())
    missing = [t for t in declared_tools if t not in parsed]
    assert not missing, f"工具未解析：{missing}（检查 extended.md 写法）"

    # Phase-2 prompt 完整性断言
    prompt = loader.load_extended_as_prompt(
        act_name="ext_my_act_name",
        tool_filter=declared_tools[:3],
    )
    assert len(prompt) > 500, f"prompt 过短 ({len(prompt)}b)，工具文档可能缺失"
    for t in declared_tools[:3]:
        assert t in prompt, f"工具 {t} 文档未注入 Phase-2 prompt"
```

跑 `pytest tests/test_my_act_loading.py -v`，覆盖率 < 80% 立刻发现问题。

---

## §5 其它 Plugin 类型边界（HintPlugin / GatePlugin / EventListener / Observability）

### 5.1 HintPlugin（**软**提示）

| 适用 | 不适用 |
|---|---|
| ✅ "如果用户问 X，建议先用 Y 工具" | ❌ "禁止用户做 X"（软提示不强制 → 用 GatePlugin） |
| ✅ "回答前先确认 Z" | ❌ "Z 必须 ≥ 10 字"（用 GatePlugin） |
| ✅ 给 LLM 注入领域知识（"金融数据习惯用 Q-Q 图"） | ❌ 业务校验逻辑 |

**关键约束**：HintPlugin 输出是**给 LLM 看的**，**不能**直接控制 agent 行为。如果你要"强制不让某事发生" → GatePlugin。

```python
from typing import Optional


class FinanceDomainHintPlugin:
    """领域知识 hint：用户做金融数据分析时给 LLM 注入业界最佳实践。

    实现 ``krow_agent_sdk.protocols.HintPlugin`` Protocol：
    - ``plugin_id`` (property/class attr)
    - ``applicable_acts`` (property/class attr) → list[str]
    - ``hint_for(context: dict) -> Optional[str]``
    """

    plugin_id = "acme.finance_hints"

    # 空 list = 全局 hint；写具体 ACT 名 = 仅在那些 ACT 内触发
    applicable_acts = ["data_analyst", "finance_research"]

    def hint_for(self, context: dict) -> Optional[str]:
        """根据运行时 context 决定是否产出 hint 文本。

        ``context`` 由 SDK 注入，常见字段：
            - act_name: 当前 ACT
            - user_input: 用户原始输入
            - tool_name: 即将调用的工具（若在工具调用前的 hint 注入点）
            - step_index: 当前 macro step 编号

        返回 None / 空串 / 抛异常 → 视为"本 hint 不适用"，跳过即可。
        """
        user_input = (context.get("user_input") or "").lower()

        # 软提示 1：金融时序数据
        if any(kw in user_input for kw in ("股票", "k线", "金融", "财务", "收益率")):
            return (
                "## 金融数据分析建议\n"
                "- 收益率分布通常右偏 → 用 log-return 而不是 simple return\n"
                "- 检查异常值前先做 Q-Q 图判断分布形态\n"
                "- 时序数据要先看 ADF 平稳性再做回归\n"
            )

        # 软提示 2：用户给了一个 csv 但没说怎么分析
        if context.get("tool_name") == "data_analyst_compute_stats":
            cols = context.get("dataframe_columns", [])
            if any(c.lower() in ("date", "timestamp", "time") for c in cols):
                return (
                    "提示：检测到时间列，建议在 markdown 报告里加一段"
                    "时序图说明（同环比、趋势、季节性）。"
                )

        return None  # 不适用 → 不注入 hint
```

**注册到 Agent**：

```python
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key(api_key)
    .with_hint_plugin(FinanceDomainHintPlugin())   # ← 注册
    .build()
)
```

**反模式（与上表一致）**：

| ❌ 错误 hint | ✅ 正确做法 |
|---|---|
| `return "禁止使用 simple return"` | 这是硬约束 → 写 GatePlugin 在 compute_stats 入口拦截 |
| `return "log-return = log(P_t/P_{t-1})"`（公式细节） | 应放工具的 docstring（ToolManager 注入工具签名时一起带），不要塞 hint context |
| `return "你必须先问用户股票代码"` | 这是流程强制 → 在 ACT extended.md 的 workflow 里写 step 0；hint 是软建议不强制 |
| `hint_for` 内 `requests.get(...)` 远程拉知识库 | 慎用 — hint 在 prompt 拼接热路径，IO 慢 → 推迟到工具内做 |

### 5.2 GatePlugin（**硬**守门）

`Gate` = 在 agent conclude 之前插入的"检查闸"，不通过就**fail-loud**。

**典型用例**：

| 用例 | 实现 |
|---|---|
| 不允许 agent 在生产路径写文件 | Gate 检查 `recent_tool_results` 里 write_* 工具的 path 参数 |
| CSV 含 PII 字段（手机/身份证）禁止流到 LLM | Gate 扫描 read_csv 返回的 columns（cookbook `PIIDetectorGate`）|
| Agent 调某 API 单次超过 1000 元成本上限 | Gate 检查累计 token 消耗 |
| Agent 准备 conclude 但还没完成必要步骤 | ConcludeGuard Gate 链（主仓内置 8 gates） |

**铁律**：

- Gate 失败 = **conclude 被 BLOCK**，黄金错误模板回送 LLM 让其改方案。
- Gate 不应做"软警告"那是 HintPlugin 的事。
- Gate 应给清晰错误信息（黄金模板）让用户/LLM 知道为什么挂掉。

#### GatePlugin 完整公开 API

外部 plugin 写 Gate 必备的全部公开 API（自 SDK v0.8.13.0 起 re-export 到 `krow_agent_sdk.protocols`）：

| 名字 | 用途 |
|---|---|
| `GatePlugin` | Protocol —— plugin 入口签名（`plugin_id` / `phase` / `get_gate()`） |
| `GatePhase` | Literal `"macro"` / `"micro"` / `"plan"` —— gate 工作位面（`"plan"` 自 v0.9.0.32 起，见 §5.2.1） |
| `Gate` | Protocol —— gate 实例签名（`name` / `priority` / `evaluate(parsed, context)`） |
| `GateDecision` | dataclass —— gate 返回值（`verdict` / `reason` / `gate_name`） |
| `GateVerdict` | Enum —— `ALLOW` / `BLOCK` / `DEFER` 三态 |
| `make_simple_gate(name, priority, evaluator)` | factory —— 把函数包装成 `Gate` 实例 |

> 历史注解（v0.8.12.x 之前）：SDK 只暴露 `GatePlugin` Protocol 但不暴露 `GateDecision` /
> `GateVerdict` / `make_simple_gate`，外部 plugin 实际**写不出** Gate 实例。本 gap
> 已在 v0.8.13.0 修复——全部 6 个名字一起 re-export。

#### GatePlugin Protocol 真实签名

```python
@runtime_checkable
class GatePlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...   # 全局唯一 ID，<org>.<plugin_name>

    @property
    def phase(self) -> GatePhase: ... # "macro" | "micro" | "plan"

    def get_gate(self) -> Gate: ...   # 返回 Gate 实例（满足 Gate Protocol）
```

#### 完整代码示例：PIIDetectorGate（cookbook 真实实现）

```python
from krow_agent_sdk.protocols import (
    GateDecision, GateVerdict, GatePlugin, make_simple_gate,
)

_PII_KEYWORDS = {"phone", "mobile", "email", "id_card", "ssn",
                 "手机", "身份证", "邮箱", "银行卡"}


class PIIDetectorGate:
    """合规守门：检测 column 名含 PII 关键词时 BLOCK conclude."""

    plugin_id = "acme.pii_gate"
    phase = "macro"  # macro ReACT conclude 之前评估

    def __init__(self, *, allow_pii: bool = False) -> None:
        self._allow_pii = allow_pii

    def get_gate(self) -> Gate:
        allow_pii = self._allow_pii

        def evaluate(parsed: dict, context: dict) -> GateDecision:
            if allow_pii:
                return GateDecision(
                    verdict=GateVerdict.ALLOW,
                    reason="allow_pii=True 已显式放行",
                    gate_name="pii_detector",
                )
            for tr in context.get("recent_tool_results", []):
                if tr.get("tool_name") != "data_analyst_read_csv":
                    continue
                cols = tr.get("result", {}).get("columns", []) or []
                hits = [c for c in cols
                        if any(kw in str(c).lower() for kw in _PII_KEYWORDS)]
                if hits:
                    return GateDecision(
                        verdict=GateVerdict.BLOCK,
                        reason=(
                            f"❌ PII 守门：检测到含敏感字段的列 {hits}\n"
                            "   位置：data_analyst_read_csv 返回 columns\n"
                            "   修法：\n"
                            "     1. 让用户先脱敏后再上传（hash / mask 末 4 位）\n"
                            "     2. 或调用层加 allow_pii=True 显式承担合规风险\n"
                            "     3. 合规依据：GDPR Art.5 数据最小化原则"
                        ),
                        gate_name="pii_detector",
                    )
            return GateDecision(verdict=GateVerdict.DEFER, gate_name="pii_detector")

        return make_simple_gate(name="pii_detector", priority=50, evaluator=evaluate)
```

**注册到 AgentBuilder**：

```python
agent = (
    AgentBuilder()
    .with_krow_api_key(api_key)
    .with_project_root(root)
    .with_gate_plugin(PIIDetectorGate(allow_pii=False))   # 硬守门
    .with_tool_plugin(DataAnalystToolPlugin())
    .build()
)
```

**`evaluate(parsed, context)` 三态返回**：

| 返回 | 行为 |
|---|---|
| `GateDecision(verdict=GateVerdict.BLOCK, reason=...)` | 立即短路 chain；conclude 失败；reason 文本回送 LLM |
| `GateDecision(verdict=GateVerdict.ALLOW)` | 显式放行本 gate（chain 内其它 gate 仍评估；多 gate AND 关系） |
| `GateDecision(verdict=GateVerdict.DEFER)` | 暂时无判决（不命中本 gate 责任域；让 chain 后续 gate 决定） |

**完整端到端 demo**：见 cookbook `examples/cookbook/data-analyst/data_analyst_plugin.py:PIIDetectorGate`
+ `OutputPathGate` —— 同一 agent 注册 2 个 GatePlugin 演示合规审计场景。

#### 5.2.1 Plan-time veto（`phase="plan"` · v0.9.0.32+ · 计划落盘前否决）

> **要解决的问题**：上面的 `phase="macro"` gate 在 agent **conclude（收尾）时**才评估。
> 但在某些托管环境（如 Krow Cloud 的 conversation slot）里，agent 跑 macro ReACT 时会
> **自规划**一些注定会被下游 conclude gate 阻断的步骤——这些步骤会被**先执行**、直到
> 收尾才被否决 → 白白浪费一整轮算力。`phase="plan"` 把审批**前移**到计划真正落盘执行
> 之前，让你在 agent 动手前就否决一份坏计划。

**触发时机**：`plan_task`（含修订）构造出计划、内部守门全过、但**尚未提交 state** 时。
覆盖**初始创建 + 修订**两条路径的公共落盘点。

**判决语义（v1 仅 ALLOW / BLOCK，REWRITE 暂缓）**：

| 返回 | 行为 |
|---|---|
| `GateVerdict.BLOCK` | 计划**不落盘、零步骤执行**；`plan_task` 直接把 `reason` 返回给 LLM；LLM 读 observation 后**自行重规划**（复用既有 replan 路径，无新机制） |
| `GateVerdict.ALLOW`（或未注册 plan gate） | 计划照常落盘执行（零回退） |

**`evaluate(parsed, context)` 在 plan 相位收到的载荷**（与 macro/micro 不同）：

```python
parsed = {
    "action": "plan",
    "is_revision": bool,          # 是否为修订（replan）
    "goal": str,
    "steps": [{"step_id", "tool", "purpose", "constraints", "depends_on"}, ...],
    "tools": [tool_name, ...],    # 计划用到的工具集合（便于做白/黑名单）
}
context = {
    "phase": "plan",
    "is_revision": bool,
    "goal": str,
    "plan_steps": [...],          # 同 parsed["steps"]
    "existing_completed_steps": [...],  # 已完成步骤（修订时判断进度）
    "act_name": str,
    "task_context": dict,
}
```

**完整示例：禁止计划里出现某工具，迫使 agent 重规划**

```python
from krow_agent_sdk.protocols import (
    GateDecision, GateVerdict, make_simple_gate,
)

class BudgetAwarePlanGate:
    """计划落盘前否决：步骤数 > 6 或用到 heavy_render → BLOCK，省掉无谓执行。"""
    plugin_id = "acme.plan_budget"
    phase = "plan"   # ← 关键：计划落盘前评估

    def get_gate(self):
        def evaluate(parsed: dict, context: dict) -> GateDecision:
            steps = parsed.get("steps") or []
            tools = parsed.get("tools") or []
            if len(steps) > 6:
                return GateDecision(
                    verdict=GateVerdict.BLOCK,
                    reason=(
                        f"❌ 计划被预算网关否决：步骤数 {len(steps)} > 6。\n"
                        "   修法：合并为不超过 6 步的精简计划后重新 plan_task。"
                    ),
                    gate_name="plan_budget",
                )
            if "heavy_render" in tools:
                return GateDecision(
                    verdict=GateVerdict.BLOCK,
                    reason="❌ 本会话禁用 heavy_render，请改用 light_render 重新规划。",
                    gate_name="plan_budget",
                )
            return GateDecision(verdict=GateVerdict.ALLOW, gate_name="plan_budget")
        return make_simple_gate("plan_budget", 50, evaluate)
```

**注册方式与 macro/micro gate 完全一致**（`.with_gate_plugin(BudgetAwarePlanGate())`）；
SDK build() 时按 `plugin.phase` 自动路由到 plan 相位注册表，与 macro/micro **严格隔离**
（plan gate 绝不会在 conclude 触发，反之亦然）。

> **边界**：plan gate 是 **fail-safe** 的——gate 评估抛异常会被静默吞掉（计划照常落盘），
> 外部 plugin 的 bug 绝不炸穿 plan 主路径。若要"不可绕过"的硬约束，应同时在 macro
> conclude gate 兜底（双层防护）。

### 5.3 EventListenerPlugin（审计 / metric）

适合**只读 / 旁路**的场景：

| 用例 | 实现 |
|---|---|
| 把 agent 每步行为落到 ELK | 监听 `executor.step.finished` → 写 Kafka |
| 统计每个 LLM 调用的 token | 监听 `llm.call.finished` → 累加到 Prometheus |
| 发现长任务 > 30min 自动通知用户 | 监听 `task.elapsed` → 触发钉钉 |

**关键约束**：

- 监听器**不应抛异常**（除非 fatal）
- 监听器**不应改 agent 状态**（只读）
- 监听器**不应做长 IO**（用异步队列）

### 5.4 ObservabilityPlugin（trace / metric）

与 EventListener 的区别：

| 维度 | EventListener | Observability |
|---|---|---|
| 触发 | 按事件订阅 | 全链路注入（span context） |
| 用途 | 落审计 / 通知 | 性能 trace / metrics 输出 |
| 输出 | 自由（Kafka / DB / log） | 标准化（OpenTelemetry / Prometheus） |

**典型用例**：

```python
class PrometheusObservability(ObservabilityPlugin):
    name = "prometheus_metrics"

    def on_span_start(self, span: Span):
        SPAN_START_COUNTER.labels(span.name).inc()

    def on_span_end(self, span: Span):
        SPAN_DURATION_HIST.labels(span.name).observe(span.duration_ms)
```

---

## §6 关键基础设施速查（公开 SDK 暴露的接口）

> 本节只列**公开 SDK 暴露给外部 plugin 用的 API**。私有 runtime 实现细节不在本文档范围。
> 完整 API 手册（带签名 + 例子）见 [`api-reference.md`](./api-reference.md)。

### 6.1 Agent 入口

```python
from krow_agent_sdk import (
    AgentBuilder,           # 链式 builder 构造 Agent
    Agent,                  # 主入口（不直接 new；通过 .build() 拿到）
    BudgetSpec,             # 预算配置 dataclass
    BuilderConfig,          # builder 内部状态 dataclass
    HttpGatewaySpec,        # HTTP gateway 配置（opt-in）
    StreamItem,             # run_stream() 返回的 envelope
    StreamItemKind,         # Literal["event", "result", "error"]
    EventBusReader,         # 给 plugin 看的只读 EventBus 视图
)
# AgentV3Result 不在 SDK 顶层 export；通过 result = agent.run(...) 拿到
```

| API | 用途 |
|---|---|
| `AgentBuilder()` | 启动构造链 |
| `.with_krow_api_key(key)` | 配 Krow API key |
| `.with_project_root(path)` | 指定 agent 工作根目录 |
| `.with_chat_model(name)` | 选 chat 模型（如 `"qwen3.6-plus"`） |
| `.with_reasoning_model(name)` | 选 reasoning 模型（如 `"deepseek-v4-pro"`） |
| `.with_vision_model(name)` | 选视觉理解模型 |
| `.with_image_gen_model(name)` | 选图像生成模型 |
| `.with_image_edit_model(name)` | 选图像编辑模型 |
| `.with_text_encoder_model(name)` | 选 embedding 模型 |
| `.with_tool_plugin(plugin)` | 注册 ToolPlugin |
| `.with_act_plugin(plugin)` | 注册 ACTPlugin |
| `.with_hint_plugin(plugin)` | 注册 HintPlugin |
| `.with_gate_plugin(plugin)` | 注册 GatePlugin |
| `.with_event_listener_plugin(plugin)` | 注册 EventListenerPlugin |
| `.with_observability_plugin(plugin)` | 注册 ObservabilityPlugin |
| `.with_mcp_server_plugin(plugin)` | 注册 MCPServerPlugin（experimental，需 `KROW_ENABLE_MCP_SERVER_PLUGIN=1`）|
| `.with_security_plugin(plugin)` | 注册 SecurityPlugin（experimental）|
| `.with_domain_pack(pack_id)` | 激活内置/已注册领域包（声明式，**无需写 plugin**；如 `"k12_math"`/`"medical"`；不存在 → `UnknownDomainPackError` fail-loud；详 §6.1.2）|
| `.with_domain_pack_manifest(manifest, activate=True)` | 程序化注册自定义领域包（`dict` / `.yaml` 路径 / `DomainPackManifest`，可 `parent_pack` 继承内置包）|
| `.with_domain_pack_plugin(plugin)` | 注册 DomainPackPlugin（experimental，聚合 hint/tool/gate）|
| `.with_visual_adapter(ext, cls)` | 注册 VisualAdapter（按文件扩展名）|
| `.with_visual_adapter_plugin(plugin)` | 注册 VisualAdapterPlugin（批量）|
| `.with_default_pptx_adapter()` | 一行打开 PPTX 视觉质检 |
| `.with_document_parser(ext, parser)` | 注册自定义文档解析器为该扩展名**默认**解析器（System 1 物理路由；abstain 可回落内置链；详 `api-reference.md` §2.6.1）|
| `.with_document_parser_plugin(plugin)` | 注册 DocumentParserPlugin（批量 + lifecycle；详 `api-reference.md` §5.11）|
| `.with_replay_store(store)` | 走 record/replay 测试模式 |
| `.with_budget(BudgetSpec(...))` | 自定义预算 |
| `.with_http_gateway(HttpGatewaySpec(...))` | opt-in HTTP gateway |
| `.with_*_plugins_from_entry_points()` | opt-in 扫 entry_points 自动注册（需 `KROW_ENABLE_PLUGIN_ENTRY_POINTS=1`） |
| `.with_hitl(...)` | 启用 HITL 挂起/续跑（Agent 中途暂停问用户 + 凭 token 断点续跑；详 `api-reference.md` §3.5） |
| `.build(validate_connection=True)` | 构造 Agent（自动凭证注入 + cloud 模型 fallback） |

#### 6.1.1 HITL 挂起/续跑（人机协同）

垂直场景（如 CAD / 工业软件驱动）经常需要中途停下来与用户确认。启用
`with_hitl` 后两条挂起路径（设计 SSOT：`docs/sdk/hitl-suspend-resume-design.md`）：

1. **LLM 自主发问**（`allow_llm_questions=True`）：注入 `request_human_input`
   工具，LLM 信息不足时调用 → run 返回 `suspended=True`；
2. **强制确认门**（`confirm_before_tools=[...]`）：计划步骤将调用清单内工具前，
   框架在步骤边界**必停**（System 1 守门，不依赖 LLM 自觉）。

```python
result = agent.run(goal)
while result.suspended:
    answer = my_ui.ask_user(result.suspension["question"])   # 你的 UI / CLI / HTTP
    result = agent.resume(result.suspension["resume_token"], answer)
```

要点：
- **跨进程恢复**：checkpoint 持久化（SQLite），进程重启后新建 Agent 直接
  `resume(token, answer)` 即可；
- **多模态答复**：`{"text": ..., "images": [...], "files": [...]}`——图片注入
  vision part，文件注册 FileCache 供工具读取；
- **幂等**：token 一次性（CAS）；重复/并发 resume 恰好一个赢，失败自动回滚可重试；
- **headless**：HTTP `POST /api/v1/agent/resume` + SSE `background_task.suspended`
  终止事件（详 api-reference §3.5）；
- 验收脚本：`scripts/repro_hitl_suspend_resume.py`（一键验证挂起→续跑→token 拒重放）。

#### 6.1.2 声明式领域包（Domain Pack · 知识编译二次开发）

垂直领域（K12 教育 / 医学 / 法律…）做知识编译时，"该抽哪些实体/关系、wiki 该有哪些章节、
图分析该校验什么不变量" 各不相同。**领域包（domain pack）** 把这些差异声明在一份
`manifest.yaml` 里（实体/关系 kind、few-shot、planner hint、字段 spec、System 1 评分配置），
让同一套引擎按领域本体编译——**不用改引擎、不用写 plugin**。

**用法 A · 激活内置领域包**（一行）：

```python
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key(api_key)
    .with_project_root("./k12_kb")
    .with_domain_pack("k12_math")          # 激活内置 K12 数学包
    .build()
)
# K12 资料 → 知识点/定义/定理/公式/原子知识/原子技能 + part_of / requires_* /
# prerequisite_of 学习路径骨架；conclude 时自动校验学习路径无环（DAG）。
result = agent.run("把这些教材编译成知识库与百科词条",
                   task_context={"strategy": "knowledge_compile"})
```

> 指定不存在的 pack_id → `UnknownDomainPackError`（fail-loud，遵循"指定≠采用"铁律，
> 绝不静默回退到默认包）。`with_domain_pack` 会合并项目已激活的包（`active_packs.yaml`）。

**用法 B · 自定义/校本领域包**（继承内置包再扩展）：

```yaml
# k12_school_pack.yaml —— 在内置 k12_math 上加题库实体与 TESTS 关系
id: k12_school
display_name: K12 校本题库包
parent_pack: k12_math               # 继承 k12_math 的全部实体/关系/few-shot
entity_kinds_extend:
  - kind: question
    description: 一道题（题干 + 难度 + 知识点标签）
relation_kinds_extend:
  - kind: tests                     # Question --tests--> KnowledgePoint
    description: 题考查某知识点
edge_field_specs:
  tests:
    weight: {type: float, min: 0.0, max: 1.0, default: 1.0}
```

```python
agent = (
    AgentBuilder()
    .with_krow_api_key(api_key)
    .with_project_root("./k12_kb")
    .with_domain_pack_manifest("k12_school_pack.yaml")   # dict / yaml 路径 / DomainPackManifest
    .build()
)
```

**System 1 评分/校验工具**（零 LLM，可在 pipeline 后处理直接调）：

```python
from modules.knowledge.k12_scoring import (
    detect_prerequisite_cycles,   # 学习路径前置 DAG 环检测（networkx + Kahn 兜底）
    aggregate_dimensions,         # 多维难度/掌握度加权聚合
    normalize_weights,            # 权重归一到和为 1
)
from modules.knowledge.global_ontology_metrics import iter_relation_pairs

edges = list(iter_relation_pairs("prerequisite_of"))
report = detect_prerequisite_cycles(edges)
assert report.is_dag, f"学习路径有环：{report.cycles}"
```

**数学公式 LaTeX 增强**（图片公式 → LaTeX；复用 metafile 栅格化 + 视觉 LLM）：
K12 讲义里公式常以 WMF/EMF 图片（MathType/WPS Equation）存储，纯文本抽取拿不到，
`Formula` 节点 `latex` 恒空。`modules.knowledge.formula_latex` 是可复用 building
block（System 1 抽图/栅格化/归一 + System 2 视觉识别），fail-soft：

```python
from modules.knowledge.formula_latex import (
    extract_docx_formula_images,   # System 1：docx OLE 公式预览图 → PNG + 上下文
    recognize_formula_latex,       # System 2：公式 PNG → LaTeX（视觉 LLM）
    enrich_formula_latex_attrs,    # System 1：识别 + coerce 成可写 {"latex": ...}
)
for fi in extract_docx_formula_images("讲义.docx"):
    res = recognize_formula_latex(fi.png_bytes, context_text=fi.context_text)
    if res.ok:
        print(res.latex)   # 识别失败不编造，latex 留空待补（manifest fail-soft 约定）
```

**完整端到端 demo**：`examples/cookbook/k12-math/`（声明式激活 + 校本特化 +
题库层 mock + 学习路径/TESTS 权重校验，含自带导数/概率/立体几何 3 份资料 +
`mock_question_bank/`）。

```python
# 阻塞式（返回 AgentV3Result，不是 RunResult）
result = agent.run(user_input)
# result.success / result.solution / result.execution_result / result.final_output

# 流式（用户可中断；详 quickstart §2 流式输出）
for item in agent.run_stream(user_input):
    if item.kind == "event":
        # event 是 modules.events.bus_core.Event dataclass
        print(item.event.type, item.event.payload)
    elif item.kind == "result":
        print("Done:", item.result.final_output)
    elif item.kind == "error":
        raise item.error  # 后台异常
```

#### 6.1.3 激活完整 reasoning 管线（纯推理任务 · 与桌面同源）

`task_context={"strategy": ...}` 只是**选**一条推理策略；要让纯推理任务拿到**与桌面"推理工作台"
逐字一致的完整编排**（多步假设/证据/矩阵/反驳的 per-strategy 编排 preamble + per-strategy Gate），
再加一个 `"source": "reasoning_panel"`：

```python
# 纯推理任务（如竞争假设 ACH / 因果发现）→ 原生激活完整 reasoning 运行时
result = agent.run(
    "对『X 是否是 Y 的主因』做竞争假设(ACH)分析：提≥2 个假设、从证据抽取并标来源、"
    "建证据×假设矩阵、按反驳最少诊断",
    task_context={"source": "reasoning_panel", "strategy": "hypothesis_test"},
)
```

- **`strategy` 取值**：内置 reasoning 策略 id（如 `hypothesis_test` / `causal_discovery` /
  `evidence_chain` / `comparative_analysis` / `temporal_trace` / `bayes_inference` /
  `graph_analytics` / `deductive_proof`）。编排步骤是**代码级 SSOT**（runtime 内置），桌面升级
  时随 runtime wheel 自动跟随——你**无需在 worker 里手抄管线步骤**（手抄 = 多 SSOT 漂移反模式）。
- **触发粒度建议（worker 作者）**：只对**纯推理** capability 挂 `source: reasoning_panel`；写作/
  检索/读取等**混合任务**不要挂（会把常规执行流换成推理流，反而绕路）。判定"是不是纯推理任务"放在
  你的 capability 路由里，混合时降级为普通 `agent.run(...)`。
- **定量策略依赖**：`causal_discovery` 等定量因果/概率策略的统计估计/反驳需 opt-in
  `pip install krow-agent-sdk[reasoning]`（scipy/dowhy/causal-learn/pgmpy）；缺库时引擎 fail-loud
  降级定性路径，不静默出错。
- **act_only 锁 worker**：单 forced-ACT 的 worker（如领域 specialist pod）**不能切换** ACT，但
  `source: reasoning_panel` 与 `act_name` 锁不冲突——它只改任务上下文的推理分支，ACT 仍锁定。
  实战参考 cookbook：[`examples/cookbook/reasoning-analyst/`](../../packages/krow-agent-sdk/examples/cookbook/reasoning-analyst/)。

#### 6.1.4 取回结构化推理产物（headless · 与桌面同一份）

纯 SDK 默认**不落盘** `.krow/reasoning/{id}.json`（那条路由只在桌面 / 后台任务队列集成时挂载）。要在 headless 拿到与桌面推理工作台**同一份结构化产物**（竞争假设矩阵 / 证据链 / 疑点 / 递归推理树 / 完整度记分卡），build 时 opt-in `with_reasoning_artifacts()`：

```python
from krow_agent_sdk import AgentBuilder, data

agent = (
    AgentBuilder().with_krow_api_key(key).with_project_root("/data/case")
    .with_reasoning_artifacts()          # 挂 ReasoningResultRouter（进程级单例）
    .build()
)
agent.run("谁是真凶？", task_context={"source": "reasoning_panel",
          "act_name": "reasoning_pipeline", "strategy": "hypothesis_test"})

r = data.get_reasoning_result()          # None = 最新一条
print(r["hypotheses"], r["metadata"].get("completeness_scorecard"))
for item in data.list_reasoning_results()["results"]:
    print(item["reasoning_id"], item["mtime"])
```

API 详见 [api-reference.md §2.4 `with_reasoning_artifacts` + §8.3 data facade](./api-reference.md#83-data--只读数据-facade)。

#### 6.1.5 三个真实世界 journey 预设（cookbook `--preset`）

`reasoning-analyst` cookbook 内置三个贴近真实场景的完整 journey，**除 UI 外等价桌面**：

| 预设 | 场景 | 策略 | 真数据环境变量 |
|---|---|---|---|
| `target_discovery` | 肺癌论文找靶点（区分因果致因 vs 相关） | `causal_discovery` | `KROW_JOURNEY_LUNG_CANCER_PAPERS` |
| `whodunit_x` / `whodunit_z` | X / Z 悲剧推理真凶（ACH 竞争假设排除） | `hypothesis_test` | `KROW_JOURNEY_TRAGEDY_X` / `_Z` |

```bash
# smoke（随仓零版权合成微样例，无真数据也跑通全链路）
python main.py --preset whodunit_x
# 复现完整效果（指向你自备的期刊 PDF / 小说全文；版权数据不进仓）
$env:KROW_JOURNEY_TRAGEDY_X = 'D:\...\X.txt'; python main.py --preset whodunit_x
```

> **版权合规**：期刊 PDF / 小说译本都不进公开仓，仓里只随发自撰的零版权合成微样例。设对应 env 或 `--sources` 指向真数据即复现。预设定义见 cookbook `real_world_journeys.py`。

### 6.2 LLM helper（在 LLM-driven Tool 中按需用，注意 §1.4 反模式 C）

```python
from krow_agent_sdk.llm import build_chat_message, build_chat_messages
# build_chat_message(role, content) -> dict
# build_chat_messages(system, user) -> list[dict]
```

> ⚠️ **TURBO 边界**：System 1 工具内**禁止**调 LLM。LLM-driven 工具的合理形态是把工具上层"ACT-内 ReACT 循环"作为驱动方，工具本身仍是 deterministic helper。详 §1.4 反模式 C。

### 6.3 EventBus（只读视图）

`EventBusReader` 是 SDK 给 plugin 提供的只读视图（不能 publish），通过 `agent.event_bus` 访问：

```python
from krow_agent_sdk import EventBusReader

reader: EventBusReader = agent.event_bus  # 只读 EventBusReader（不是 EventBus）

def on_step(event):
    # event 是 modules.events.bus_core.Event dataclass：type / payload / trace_id / timestamp
    print(event.type, event.payload)

token = reader.subscribe("progressive.step_completed", on_step, track_recent=True)
# ...
reader.unsubscribe(token)

# 也支持 ring buffer 回看（仅 track_recent=True 的 topic）：
for ev in reader.iter_recent("progressive.step_completed", n=10):
    print(ev.type, ev.payload)
```

> Plugin 想"发"事件 → 走 P5 EventListenerPlugin 的 listener 副作用 / P6 ObservabilityPlugin 自己的 sink，**不**通过 SDK 反向 publish（保单向 pub-sub）。

### 6.4 Replay Store（测试一等公民）

```python
from krow_agent_sdk.replay import LLMReplayStore

# 推荐：从环境变量决定 mode（CI replay / 本地 record / auto）
store = LLMReplayStore.from_env(
    "tests/fixtures/my_test.json",      # fixture 路径
    mode_env="KROW_LLM_REPLAY_MODE",    # 默认值
    default="replay",
)

# 或显式指定
from pathlib import Path
store = LLMReplayStore(Path("fixtures/x.json"), mode="replay")

agent = (
    AgentBuilder()
    .with_replay_store(store)            # SDK 自动 wrap 所有 LLM provider
    .build()
)
```

**特点**：

- 0 token 成本（replay 模式）
- 完全确定性可重放（key = request hash）
- CI 可跑（`KROW_LLM_REPLAY_MODE=replay`，cache miss 抛 `LLMReplayMiss`）
- mode：`record` / `replay`（默认）/ `auto`

### 6.5 Plugin 接口（**实例属性 / 协议方法**，不是 ctx 注入）

> SDK 走 **Protocol**（duck typing） + 实例属性的扁平形态，**没有** PluginContext / ToolContext 注入。`plugin_id` 是 property / class attr，工具 handler 直接是 `Callable`。

```python
from krow_agent_sdk.protocols import ToolPlugin, ACTPlugin

# ToolPlugin: plugin_id (property) + get_tools() -> list[ToolSpec]
class MyToolPlugin:
    plugin_id = "acme.search"   # 双段 "<org>.<plugin_name>"

    def get_tools(self) -> list[dict]:
        return [{
            "name": "acme_search",
            "description": "搜某个数据库",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "handler": _do_search,    # Callable[..., Any]
        }]

def _do_search(query: str) -> dict:
    if not query.strip():
        return {"ok": False, "error": "❌ query 不能为空。"}
    return {"ok": True, "results": [...]}


# ACTPlugin: plugin_id + act_name (property) + get_act_root() + get_act_file_path() + get_tool_names()
# 详 quickstart.md §3 + api-reference.md §5.1
```

### 6.6 Lifecycle hooks（可选）

```python
from krow_agent_sdk import BasePluginLifecycle, SDKContext

class MyPlugin(BasePluginLifecycle):
    plugin_id = "acme.example"

    def on_load(self, ctx: SDKContext) -> None:
        # ctx.api_key  : str
        # ctx.workspace: Path
        # ctx.event_bus: EventBusReader  (只读，不能 publish)
        ...

    def on_unload(self) -> None:
        ...
```

`BasePluginLifecycle` 是**可选** mixin —— Protocol 本身不要求 lifecycle 方法。`on_load` 异常 → fail-loud；`on_unload` 异常 → log warning 不阻塞。

### 6.7 Plugin entry_points（**opt-in**，默认关）

在你的 `pyproject.toml` 内（一个 plugin 一个 group）：

```toml
[project.entry-points."krow.act_plugin"]
my_research = "my_pkg.plugin:get_act_plugin"

[project.entry-points."krow.tool_plugin"]
my_cad = "my_pkg.cad:CADQueryPlugin"
```

主进程**默认不**自动扫描；用户必须 opt-in：

```python
import os
os.environ["KROW_ENABLE_PLUGIN_ENTRY_POINTS"] = "1"

agent = (
    AgentBuilder()
    .with_krow_api_key(key)
    .with_all_plugins_from_entry_points()  # 扫 9 个 group
    .build()
)
```

或按类型粒度扫：

```python
.with_act_plugins_from_entry_points()
.with_tool_plugins_from_entry_points()
.with_hint_plugins_from_entry_points()
.with_gate_plugins_from_entry_points()
.with_event_listener_plugins_from_entry_points()
.with_observability_plugins_from_entry_points()
.with_domain_pack_plugins_from_entry_points()
.with_visual_adapter_plugins_from_entry_points()
```

> **安全**：默认关闭防 supply-chain（恶意 wheel install 自动注入 plugin）。打开 entry_points 自动扫描 = 信任 PyPI 上所有装的 wheel；生产建议保持显式 `.with_<type>_plugin(...)`。

### 6.8 策略自动路由：引擎默认会做什么，怎么关（0.9.1.4 起）

这是**唯一一处引擎会替你的 plugin 做语义决策**的地方，值得单独读一遍。

**引擎在做什么**：`task_context` 里没有 `strategy` 时，引擎会用一次轻量 LLM 分类判断"这是不是一道推理题、该走哪套方法论"。命中具体推理策略（如 `hypothesis_test` 竞争假设分析）时会给这个 run 挂上对应的**契约**：plan 阶段的相位硬门、conclude 阶段的合规门、推理级墙钟预算。

**为什么你需要知道**：契约里的硬门会**要求 LLM 调用该方法论的记账工具**（ACH 族的 `propose_hypothesis` / `add_evidence` / `recompute_ach_matrix` 等）。这些工具由主仓注册，即使不在你 ACT 声明的工具集里，LLM 也调得到 —— 于是你会在日志里看到大量与业务无关的工具调用。真实案例：一个海关 HS 归类 plugin，问题"该报哪个 HS"被判成"多候选里锁定唯一答案"= 竞争假设分析，31 次工具调用里 20 次是 ACH 记账。

**0.9.1.4 起的默认行为（多数 plugin 什么都不用做）**：

| 你的 `task_context` | 引擎行为 |
| --- | --- |
| 带 `act_name` / `capability` / `lock_act` 任一 | **不路由**（认为你已经决定了这轮干什么） |
| 显式传了 `strategy` | 不路由（指定即采用） |
| 什么都没带（裸调用） | 路由；但猜出来的策略只享**基础墙钟**，不给 8h 长跑弹性 |
| 声明了 `tool_universe="act_only"` | 额外校验：策略硬门要的工具不在你的 ACT 工具集里 → 不采用该策略 |

**0.9.1.6 追加的两条（都不需要你改代码，默认生效）**：

*查询类问题不再进推理管线*。路由器的意图分类新增了一类 `lookup`，判据是**答案从哪来**而不是**问题难不难**：答案已经写在手册/标准/税则/知识库里、任务是查出来并按规则套用 → `lookup`；答案不在任何单份资料里、必须跨来源提假设再排除才能得出 → `reasoning`。

对你（SDK / REST / chat 入口）而言，判为 `lookup` 意味着**根本不会采用任何推理策略** —— 采用判据要求意图必须是 `reasoning`，所以推理契约、ACH 纪律、推理级预算一个都不会挂上，LLM 收到的是一段"走最短检索路径、优先用你的专用查询工具、结论给出依据出处"的软引导。桌面推理面板是唯一的例外：它一律采用策略（用户是主动点进推理面板的），此时 `lookup` 的作用是不再注入"至少 N 条假设 + 逐条挑战"那套 ACH 纪律。

真机实测（`scripts/repro_hs_lookup_real_llm.py`，真实 LLM）：上面那个 HS 归类原句、锂电池税则号、DRG 编码、税前扣除四条全部判为 `lookup` 且在 SDK 入口不被采用；同一批里"p99 变差找原因""三家供应商谁泄密"仍分别走 `causal_discovery` / `hypothesis_test`，没有被误伤。

注意这条**只影响引导与契约，不替你做业务判断**：`lookup` 仍然会去查资料、仍然走完整的 plan/run 流程，只是不再按情报分析的方法论展开。

*墙钟按入口分档*。8 小时那档是给桌面推理面板设计的（用户守在那儿等一次深度分析）。SDK plugin / REST / chat 这些入口的绝对天花板现在是 **2 小时**，因为你们的调用方通常自带超时、用户也没有"我在等一个 8 小时任务"的预期。需要满额的显式传 `depth_mode=True`：

```python
task_context = {"depth_mode": True}   # 恢复 8h 上限（显式意图优先）
```

`wallclock_budget_s` / `wallclock_hard_deadline_s` 若声明了更紧的边界，仍然按更小者生效 —— 这条分档只是给"什么都没声明"的 run 加了个兜底顶。

**分级承诺：猜出来的策略拿不到硬门**（下一个 hotfix 起默认生效，同样不需要你改代码）

引擎决定"这活儿归 `hypothesis_test` 管"之后给多少东西，以前是二值的：要么全给（方法论引导 + plan 阶段硬门 + conclude 门 + 推理级预算 + 最长 8h），要么什么都不给。现在分成四档：

| 档位 | 给什么 | 谁产生 |
| --- | --- | --- |
| L0 观察 | 方法论引导、工具分层提示 | 你显式声明 `commitment_level=0` |
| L1 方法论 | + conclude 软门 | **引擎自动路由采纳的上限** |
| L2 完整契约 | + plan 阶段硬门、conclude 硬阻塞 | 面板入口 / 你显式传了 `strategy` |
| L3 长跑 | + 8h 墙钟续期 | `depth_mode=True` |

对 plugin 最要紧的是 **L1 那条线**：引擎猜出来的策略不再享有 plan 阶段硬门。硬门是所有约束里唯一会造成死循环的一个 —— 缺一个必装工具不是"少做一步"，而是 `plan_task` 被反复打回重规划，直到预算烧光；上面那个 HS 归类案例里 20 次越界的 ACH 记账调用，正是被它逼出来的。降到 L1 之后，方法论该走哪几个阶段仍然写在引导里告诉 LLM，但不再 reject。

同一档位还会改写引导的**措辞**：L2 说"违反会被 Gate 5 拒绝"，L1 改成"以上是建议梯度，若你判断这套方法论工具不适用，按任务本身该用的工具规划即可"。在硬门不生效的档位上对 LLM 说一句系统并不会执行的威胁，会驱使它为了躲避不存在的惩罚去硬凑方法论工具 —— 那正是我们想避免的行为。

想更省，可以自己降到 L0（"借个思路，但别管我怎么干"）：

```python
task_context = {"commitment_level": 0}
```

你什么都不声明时是 L2 —— 也就是 0.9.1.6 之前的行为，**降档只发生在自动路由这一条路径上**，因为那是唯一没有人为策略背书的路径。

**三个显式开关**（按精确度从高到低）：

```python
# ① 单次调用：告诉引擎"策略归属我判过了"（传 False 则相反：要求引擎自由路由）
task_context = {"strategy_routing_decided": True}

# ② 单次调用：直接指定，最精确
task_context = {"strategy": "evidence_chain"}   # 或 "" + 上面的 decided=True 表示"不挂策略"

# ③ 进程级 kill switch（调试用，不建议长期开）
os.environ["KROW_CHAT_REASONING_AUTOROUTE"] = "0"   # 关闭自动路由
os.environ["KROW_REASONING_LONGRUN"] = "0"          # 关闭长跑续期
```

**怎么确认真实生效**：路由结果会发 `reasoning.strategy.routed` 事件（含 `strategy` / `routed` / `intent` / `reason` / `entry` / `commitment_level`），订阅 EventBus（§6.3）即可看到引擎到底选了什么、为什么、给了哪一档。日志里对应 `AgentV3: 自动策略路由 → …（… 承诺档位=L1 方法论 …）`；被上述任一道门拦下时会打印跳过原因。

> 设计背景与三轮专家辩论：（内部）。

---

## §7 测试方法论

### 7.1 三层测试金字塔

```
        ▲
        │  E2E 真实 LLM 测试（少而精）
        │  - 跑 1-2 个完整 user journey
        │  - 用真实 LLM 验证 prompt 与模型对齐
        │  - nightly 跑（成本高）
        │
        │  Replay 测试（覆盖核心路径）
        │  - 用 LLMReplayStore 跑录制好的 LLM 对话
        │  - 0 token 成本 + 完全确定性
        │  - 每次 PR / push 都跑（CI 主力）
        │
        │  Unit 测试（覆盖 System 1）
        │  - 测工具入参归一、错误模板、Gate 守门
        │  - 100% 覆盖（System 1 应该可以做到）
```

### 7.2 写 Unit 测试（System 1）

System 1 工具应该**100% 可被 unit test 覆盖**：

```python
def test_my_tool_empty_query():
    tool = MyTool()
    result = tool.execute(ctx=mock_ctx(), query="")
    assert result["ok"] is False
    assert "不能为空" in result["error"]


def test_my_tool_normalizes_path_list():
    tool = MyTool()
    # 单 str → 自动包装为 list
    result = tool.execute(ctx=mock_ctx(), paths="/a")
    assert result["normalized_paths"] == ["/a"]
    # list → 保持
    result = tool.execute(ctx=mock_ctx(), paths=["/a", "/b"])
    assert result["normalized_paths"] == ["/a", "/b"]
```

### 7.3 写 Replay 测试

> **真实 API**：`LLMReplayStore` 的 mode 由 `KROW_LLM_REPLAY_MODE` env 或构造参数决定；`record` 模式下每次 LLM 调用自动 `put` 到 fixture，无需手动 `save()`。

**录制阶段**（本地一次性，跑前 `set KROW_LLM_REPLAY_MODE=record`）：

```python
import os
from pathlib import Path
from krow_agent_sdk import AgentBuilder
from krow_agent_sdk.replay import LLMReplayStore

os.environ["KROW_LLM_REPLAY_MODE"] = "record"  # 本地 record；CI 默认 replay
store = LLMReplayStore.from_env("./fixtures/my_test.json")
agent = (
    AgentBuilder()
    .with_krow_api_key(os.environ["KROW_API_KEY"])
    .with_project_root("./workspace")
    .with_replay_store(store)            # SDK 自动 wrap LLM provider
    .build()
)
try:
    result = agent.run("我的测试 user input")
    assert result.success
finally:
    agent.shutdown()  # 自动 uninstall replay swap，并 persist fixture
```

**回放阶段**（CI 每次跑）：

```python
import pytest
from krow_agent_sdk import AgentBuilder
from krow_agent_sdk.replay import LLMReplayStore


def test_my_journey_replay():
    # CI 默认 replay；fixture 必须已被 record 阶段提交到仓
    store = LLMReplayStore.from_env(
        "./fixtures/my_test.json",
        default="replay",
    )
    agent = (
        AgentBuilder()
        .with_krow_api_key("sk-user-fake-for-replay-mode-only")
        .with_project_root("./workspace")
        .with_replay_store(store)
        .build()
    )
    try:
        result = agent.run("我的测试 user input")
        assert result.success
        assert "expected_output_substring" in result.final_output
    finally:
        agent.shutdown()
```

**cache miss 行为**：默认 `on_miss="raise"` → 撞 cache miss 抛 `LLMReplayMiss`，提示需要重 record，避免悄悄烧钱。

### 7.4 写 E2E 真实 LLM 测试

**关键问题**：LLM 不确定性 → 用什么作为 PASS/FAIL 判据？

**答**：**预期结果卡 + 多维断言 + 容差**。

预期结果卡示例（`fixtures/expected_my_journey.yaml`）：

```yaml
expected_actions:
  macro_steps_min: 3
  macro_steps_max: 8
  required_tools_called:
    - search_arxiv
    - read_pdf
expected_artifacts:
  output_file: "./output/summary.md"
  output_size_kb_min: 1
  output_size_kb_max: 50
expected_quality:
  must_contain:
    - "BibTeX"
  must_not_contain:
    - "TODO"
    - "lorem ipsum"
expected_fail_signals:
  no_replan_more_than: 2
  no_budget_exhausted: true
  llm_calls_max: 80
expected_perf:
  wall_clock_max_seconds: 600
```

测试代码：

```python
def test_my_journey_real_llm(real_llm_available):
    if not real_llm_available:
        pytest.skip("nightly only")
    expected = yaml.safe_load(open("./fixtures/expected_my_journey.yaml"))

    agent = AgentBuilder().with_krow_api_key(KEY).build()
    result = agent.run("写一篇 transformer 综述")

    # 多维断言
    assert result.success
    assert expected["expected_actions"]["macro_steps_min"] <= result.macro_steps_count
    assert all(t in result.tools_called for t in expected["expected_actions"]["required_tools_called"])
    assert Path(expected["expected_artifacts"]["output_file"]).exists()
    # ... 其它维度
```

### 7.5 测试反模式

| ❌ 错误 | ✅ 正确 |
|---|---|
| `mock.patch('httpx...')` 模拟 LLM | 用 `LLMReplayStore` |
| 测试内 `time.sleep(N)` 死等 | 用 `wait_until(predicate)` |
| 测试用一个完美 LLM 输出做绝对断言 | 用预期结果卡 + 多维容差 |
| 不写 unit test，只写 e2e | unit test 是 System 1 的护栏，必须有 |
| record 完后 LLM 改了 → 测试还过 | 定期跑真实 LLM 验证 prompt 与模型对齐 |

---

## §8 反模式黑名单（带铁证）

> 凡违反这一节的设计，**99% 概率会出 bug**。请逐条核对。

### 8.1 TURBO 边界违反

| 反模式 | 铁证 | 修法 |
|---|---|---|
| ToolPlugin 内 `import openai` 调 LLM | 失去 unit test 100% 覆盖；性能可重放性破坏 | 把 LLM 驱动逻辑抽到上层 ACT；ToolPlugin 只做 System 1 |
| HintPlugin 内做参数校验 | LLM 经常忽略软提示 → 校验形同虚设 | 用 GatePlugin（System 1 fail-loud） |
| 让 LLM 算 `cos / sin / 颜色对比度` | LLM 算数不可靠（已知数学题翻车率 5-10%） | 写 System 1 工具查表 / 计算 |
| 用 regex 抽语义信息（"是不是抱怨"） | 自然语言无穷变化；regex 一定漏 | 用 LLM (System 2) |

### 8.2 SSOT / DRY 违反

| 反模式 | 铁证 | 修法 |
|---|---|---|
| 在 plugin yaml 写一遍工具列表，又在 `__init__.py` 注册一遍 | 早晚漂移 → bug | yaml 是 SSOT，code 自动读 yaml |
| 错误信息散在 5 个 `raise ValueError(...)` | 改文案要找 5 处 | 集中常量类 |
| `summary.md` 重复 ToolManager 自动注入的工具签名 | LLM 看 2 遍浪费 token | summary.md 只写"何时调"，不写参数 |

### 8.3 OCP 违反

| 反模式 | 铁证 | 修法 |
|---|---|---|
| `read_file_v2` / `read_file_v3` | LLM 不知道选哪个；老代码全失效 | 加新参数 `read_file(path, mode="...")` |
| 改 `read_file()` default 让所有旧调用变行为 | 静默改变行为 → 历史 hint 全错 | 加新参数；旧 default 不变 |

### 8.4 错误处理反模式

| 反模式 | 铁证 | 修法 |
|---|---|---|
| `try: ... except: pass` 吞错继续 | 用户拿到错误结果不知情 | 至少 log + raise；最好 fail-loud 给清晰信息 |
| 错误信息只说 "failed" | LLM 不知道怎么修 | 用 §3.5 黄金模板 |
| LLM 失败 1 次直接返回 "我做不到" | 应有 1-3 次 retry + 不同策略 | SDK 的 ProgressiveExecutor 自带；plugin 不要自己 short-circuit |

### 8.5 测试反模式

| 反模式 | 铁证 | 修法 |
|---|---|---|
| `mock.patch('httpx.post')` 模拟 LLM | 重造 `LLMReplayStore` 轮子；LLM 协议变就漂 | 用 `LLMReplayStore` |
| 测试内 `time.sleep(5)` 死等 agent | 慢 + 容易 flaky | 用 `wait_until` / event 监听 |
| 只写 e2e 不写 unit | System 1 没护栏 | 先写 unit 100% 覆盖工具入口归一 |
| 依赖一次 LLM 输出做绝对断言 | LLM 不确定性 → 偶发 fail | 用预期结果卡 + 多维容差 |

### 8.6 信息披露反模式（**Plugin 作者关心**）

| 反模式 | 铁证 | 修法 |
|---|---|---|
| 把 KROW_API_KEY 透传给第三方 API | 凭证泄漏风险 | 只在 SDK <-> Krow Cloud 链路上用 |
| 把用户业务数据 log 到 stdout | 可能被 ELK 截到 | 脱敏 / log 前过滤 |
| 把 Plugin 内部 stack trace 全文返回给 agent | LLM 可能在用户输出里复述 | 错误黄金模板内只露用户能修的 hint |

---

## §9 双环元认知与运行时自进化

> **这一章是给想观测 / 维护 agent "自进化"行为的开发者**。绝大多数场景你**什么都不用做**——双环元认知随 runtime 内置、默认全开、自我调节。本章解释它在做什么、产物落在哪、怎么只读查看、需要时怎么 kill。

### 9.1 双环模型（一图理解）

Krow agent 在跑任务时同时运行两个认知回路：

| 回路 | 时机 | 职责 | 形态 | 成本 |
|---|---|---|---|---|
| **快环（M1/M2）** | 任务执行**中**（每步） | 实时感知认知负荷（目标进度 / 预算燃烧 / 工具抖动），strained/overload 时往 prompt 注入**软提示**纠偏 | System 1 遥测（零 LLM）+ 软提示 | ~0 |
| **慢环（M3/M4）** | 任务**结束后**（事件驱动 + 节流，进程内） | 把高频认知负荷 / 失败信号**睡眠期蒸馏**成 learned overlay 教训，按在线证据**晋级**，注入后续任务 prompt | System 1 聚类/晋级 + System 2 每簇最多 1 次 LLM 蒸馏 | 极低（预算封顶） |

设计纪律：**语义交给 LLM、语法交给系统**。快环的负荷分级、慢环的聚类 / 晋级 / 防膨胀全是确定性 System 1；只有"把一簇信号蒸馏成一句教训"才用 1 次 LLM。

### 9.2 快环：认知负荷软提示

快环是纯 System 1 遥测：每步算 `budget_burn_ratio` / `progress_ratio` 等轴，分级
`nominal / strained / overload`。只有 strained/overload 才往 prompt 注入一段简短软
提示（如"预算已过半但目标进度偏低，考虑收敛范围 / 先交付核心"），**不**硬改 LLM 输出。
这条软提示链解决「预算快烧光但目标还差得远」这类典型元认知场景。

快环全程零额外 LLM 成本、对你的 plugin 完全透明。kill switch 见 §9.6。

### 9.3 慢环：睡眠蒸馏 + overlay 两层存储

慢环把"反复出现的认知负荷 / 失败模式"沉淀成可复用教训：

1. **采集**：任务结束后按 `cluster_key` 聚类遥测信号。
2. **蒸馏（睡眠期）**：高频簇（复现 ≥ 2）每簇**最多 1 次** LLM 蒸馏成一条教训文本，
   写入 overlay 存储为 `candidate`（**collect-only，绝不直接注入**）。单轮蒸馏受预算
   封顶（默认 ≤ 3 次 LLM 调用 / ≤ 30s），用户新任务到达立即让位。
3. **晋级（在线证据门，纯统计零 LLM）**：`candidate` 复现 ≥ 3 → 升 `active`（开始注入
   prompt）；`active` 教训若净负反馈（`negative - positive`）≥ 3 → 自动降级 `demoted`。
4. **注入**：`active` 教训按 `disclosure_triggers` 命中才加载进后续任务 prompt（按需，
   不是永久全量）。

overlay 是**两层 JSON**（复刻 AGENTS.md「压缩核心 + 按需加载」）：

| 层 | tier | 含义 | 硬上限 |
|---|---|---|---|
| Tier-0 `core` | `0` | 压缩核心原则，永久注入 | 12 条（超限 fail-loud） |
| Tier-1 `overlay` | `1` | 场景化，命中 triggers 才加载 | 总量 200 条；30 天未命中的 candidate 自动衰减 |

`lesson_type` 两类：`info_only`（只读提示，零行为风险，默认放开晋级）与
`behavior_change`（改变执行行为，软启动低权重 0.3、正反馈累积加权封顶 0.7，长期在线
正向 + 观测量 ≥ 10 + active ≥ 7 天 + 支持率 ≥ 0.8 才升全权重 1.0）。

### 9.4 只读查看蒸馏结果（`get_overlay_snapshot`）

SDK 暴露只读 diagnostics API 审视慢环产物：

```python
import json
from krow_agent_sdk.diagnostics import get_overlay_snapshot

snap = get_overlay_snapshot()   # 也可传 store_path="/path/to/overlay.json"
print(f"共 {snap['count']} 条 · {snap['by_status']} · 落盘={snap['store_path']}")
for lesson in snap["lessons"]:
    print(f"[{lesson['status']}/{'core' if lesson['tier']==0 else 'overlay'}]"
          f" recur={lesson['recurrence']} +{lesson['positive_outcomes']}"
          f"/-{lesson['negative_outcomes']} :: {lesson['text']}")
```

返回字段（plain dict，read-only，不抛异常 → 失败返 `{"error": ...}`）：

| 字段 | 含义 |
|---|---|
| `store_path` / `exists` | overlay.json 落盘位置 / 是否存在 |
| `count` / `by_status` / `by_tier` | 总数 / 按 candidate·active·demoted / 按 tier 0·1 计数 |
| `lessons[]` | 每条教训：`id` / `text` / `tier` / `status` / `lesson_type` / `recurrence` / `positive_outcomes` / `negative_outcomes` / `weight` / `disclosure_triggers` / `cluster_key` / `scope` / `created_ts` / `updated_ts` |

落盘位置默认 `{KROW_DATA_DIR}/self_evolution/overlay.json`（容器部署务必把 `KROW_DATA_DIR`
挂到持久卷，否则蒸馏结果随容器销毁；详 [`headless-deployment.md`](./headless-deployment.md)）。

### 9.5 维护（纠错 / 固化）

- **只读审视**：用上面的 `get_overlay_snapshot()`。
- **人工纠错**：overlay 是 candidate 起步 + 在线证据自动晋级/降级，**坏教训会因净负反馈
  自动 demote**，通常无需手动干预。桌面 Krow IDE 的「记忆面板」提供 pin / 删除 UI；纯 SDK
  场景可直接编辑 overlay.json（进程未跑时）或删文件重置。
- **固化为 base**（高级 / 谨慎）：长期稳定的 active 教训可经人工门提案固化进 base，属于
  内部维护流程，不在 SDK 用户日常范围。

### 9.6 何时 kill / 调参

默认全开即可。需要确定性复现（如录制 replay 测试）或排查时，可用环境变量逐环关闭
（详 [`api-reference.md`](./api-reference.md) §13「双环元认知 / 运行时自进化 kill switch」）：

| 目的 | 设置 |
|---|---|
| 关快环软提示 | `KROW_METACOG_PROVIDER=0`（+ `KROW_GOAL_GAP_FEEDER=0`） |
| 关慢环蒸馏 | `KROW_SLEEP_PHASE=0` |
| 关 overlay 注入（蒸馏仍跑但不进 prompt） | `KROW_OVERLAY_INJECT=0` |
| 完全确定性（测试场景） | 上述全设 `0` |

> 实战 cookbook：[`examples/cookbook/reasoning-analyst/`](../../packages/krow-agent-sdk/examples/cookbook/reasoning-analyst/) 演示如何订阅 `cognitive.load` 事件观测快环，并用 `get_overlay_snapshot` 查看慢环蒸馏。

---

## §10 配置决策脑三注册表 + 控制反射带（让决策脑对你的任务"看得见、叫得醒、算得清、动得了手"）

> 这一篇解决一个具体问题：**你基于 SDK 开发了一个垂直功能（文献检索、报告生成、代码审查…），但决策脑对你的任务族"全盲"——它不知道你离交付还差多少、也不知道你什么时候卡住了。** 本章教你用三注册表把领域完整度信号接进决策脑。litsci（文献检索）就是靠这套把"检索到 91 篇却零下载空转 17 分钟"这类事故变得可被决策脑察觉的。

### 10.1 先搞清：决策脑是什么，三注册表在其中的位置

Krow 的 macro 编排不是"规划→执行→再规划"的死循环，而是一个元认知**决策脑**，架构对齐认知科学的 **GWT（全局工作站理论）**：

```
① 观测（每拍）        ② 稀疏唤醒            ③ 广播 + 决策         ④ 信用回喂
Contributor 写快照 → WakeTrigger 判定 →  注入决策请求块 → LLM →  Classifier 归类 → 结算 Δ
（离验收多远？）      （现在该惊动吗？）     （揭示决策，非命令）      （这次决策有用吗？）
```

关键在**稀疏**：决策脑不是每拍都惊动 LLM（那样又慢又贵），而是平时静默观测，只在"该管"的时候点亮工作站、把注意力广播给 LLM。三注册表就是这套机制的**领域扩展点**（OCP：核心引擎领域无关，你按 FQCN 自注册，不改核心）：

| 注册表 | GWT 角色 | 你注册什么 | 契约 |
|---|---|---|---|
| **SituationContributor** | 观测层 | 把领域状态写进工作站 | `applicable(exe)->bool` + `__call__(exe)->{"error_vector":{...},"signals":{...}}` |
| **WakeTrigger** | 唤醒层 | 决定何时点亮工作站 | `(prev,curr,delta,ledger)->str\|None`（命中返事由） |
| **DecisionClassifier** | 结算层 | 把 LLM 动作归类做信用回喂 | `(action,snap,ledger)->str\|None` |

三层合起来解决的是"决策脑知道了"。**知道之后系统能做的曾经只有一件事——给 LLM 写一段建议文案。** 这在实测里会露馅：同一个卡点连着劝了 8 次、每次建议都合理，却始终没有任何东西落盘。那时缺的不是更好的建议，是一个执行器。

补这一格的是**控制反射**（`register_control_reflex`）。它**不是第四个注册表**——底下走的还是既有的决策契约（`DecisionSpec(kind=reflex)`），现有的 `landing` / `salvage` / `materialize` 全都在这条路上，SDK 只是把入口暴露出来。它跑在每个 macro 拍首的反射带里，**先于唤醒评估**，也就是在 LLM 被问之前就确定性地动手。契约、参数、以及"何时该用它、何时该用 step 执行器"的选型见 [`api-reference.md` §9.6](./api-reference.md#96-metacognition--配置决策脑三注册表)。

**核心已内建 10 个 domain-neutral 触发器**（gate 阻断 / 停滞 / 目标停滞 / 恶化 / 工具连败 / loop 迭代未达标 / progressive modify 空转…），**跨所有任务族免费生效**。你通常**只需补观测层 contributor**（把领域信号变成 error_vector），停滞/恶化就自动被核心触发器捕获——很多时候连自定义 trigger 都不用写。

### 10.2 观测层：error_vector vs signals（最重要的一层）

一个 contributor 返回两类数据，语义完全不同，别混：

| 键 | 语义 | 谁用 | 值域 |
|---|---|---|---|
| `error_vector` | **离验收的距离**（0=完美，1=最差） | 核心 `_trigger_stall`/`_trigger_worsening` 判"持续不降/在变差" | 每个分量 0~1 |
| `signals` | **观测明细**（任意事实） | 你自己的 WakeTrigger 做语义判定 + 事件可观测 | 任意 |

```python
class DownloadCompletenessContributor:
    """把'下载完整度'接进决策脑（域自判门禁 + error_vector + signals）。"""

    def applicable(self, executor) -> bool:
        # ⚠️ 收窄：只在有活跃下载信号时才 True——否则简单任务会误报"传感器失活"
        return self._download_requested(executor) > 0

    def __call__(self, executor) -> dict:
        requested = self._download_requested(executor)
        failed = self._download_failed(executor)
        if requested <= 0:
            return {}                                   # fail-soft：无信号返空
        return {
            "error_vector": {"download_gap": round(failed / requested, 4)},
            "signals": {"dl_requested": requested, "dl_failed": failed},
        }
```

**四条铁律**（违反任何一条 = 埋雷）：

1. **error_vector 必须有 ground-truth 背书**——只注册"有真值可校准"的分量（来自 gate / 校验器 / 真机 journey）。**禁止**把 LLM 自评分、启发式估算当 error_vector（噪声会让停滞判定假阳/假阴）。没真值就只放进 `signals`，别放 error_vector。⚠️ 这条铁律**只约束 error_vector 与 L0 触发器**（自主级 C）——`signals` 与 warning-only/L2 触发器**不要求** ground-truth，可**提前预判注册**（三级准入详见 §10.8）。
2. **`applicable()` 要收窄**——只在探测到活跃领域信号时返 True。恒真却零产出 = "传感器失活"假象，会拖累核心 dead-sensor 自检。
3. **System-1 确定性 + fail-soft**——contributor 是纯读、零 LLM、零副作用；任何异常返 `{}`（绝不抛，态势装配不能被单个 contributor 拖垮）。
4. **复用工具返回值 SSOT，不新造账本**——从 executor 已有的 `_step_results` / 工具 output 读计数，别自己在 executor 上挂新状态。

### 10.3 唤醒层：稀疏，不是越多越好

WakeTrigger 是 System-1 纯谓词。写它的唯一目的是**在核心 10 个触发器覆盖不到的领域专属场景**补一刀。纪律：

- **每形态每任务只唤醒一次**（`self._fired` 标志）——同一条件每拍重复唤醒 = 唤醒风暴，会淹没真正的信号。
- **门禁靠 signals 天然隔离**：非本领域任务的 snapshot 里没有你的 signal 键，trigger 自然返 None，不需要额外 if。
- **完整度红线用 `l0_event`**：默认软预算耗尽后触发器一律让位（让任务收尾）。若你的场景是"缺一页/漏一批就算失败"的完整度红线，给触发器设 `fn.l0_event = True`，它在软预算耗尽后仍能唤醒（`§0.0 完整性 > 速度`）。

```python
def wake_zero_download_with_hits(prev, curr, delta, ledger) -> str | None:
    """检索有果却零下载 → 唤醒（L2 advisory · 每任务一次靠调用方去重）。"""
    sig = curr.signals
    hits, dl = sig.get("papers_found"), sig.get("dl_downloaded")
    if isinstance(hits, int) and hits >= 3 and dl == 0:
        return f"zero_download:检索到{hits}篇却零下载——放宽约束或诚实转交付元数据"
    return None
```

**必标两个轴属性**（缺任一都会让你的触发器"喊了但没人接"）：

| 属性 | 回答什么 | 取值 |
|---|---|---|
| `value_axis` | 这个信号**有多重要**（同拍多触发器命中时的裁决序） | `accuracy` / `completeness` / `speed` / `cost`（按 AGENTS.md §0.0 价值观字典序） |
| `error_axis` | **谁来处置它**（轴 × 执行器满秩矩阵的对齐键） | 见下 |

```python
from krow_agent_sdk.metacognition import AXIS_PRIMARY_ERROR, AXIS_ADVISORY, CORE_AXES

wake_zero_download_with_hits.value_axis = "completeness"
wake_zero_download_with_hits.error_axis = AXIS_ADVISORY   # 处置由核心决策承接
```

`error_axis` 的三种诚实姿态（**不声明**不是第四种——那是欠账，满秩矩阵会点名说"无从校验"）：

1. **复用核心轴**：问题能被核心决策处置就用核心轴常量（全集见 `CORE_AXES`）。误差向量类信号一律用符号轴 `AXIS_PRIMARY_ERROR`——它在运行时解析成当拍最痛的分量，`continue` / `replan` / `extend_budget` 都在推动它。
2. **advisory**：你只是"值得看一眼"的提醒，处置由别的决策承接 → 标 `AXIS_ADVISORY`（`"-"`）。这是**显式**声明"我不要求专属执行器"，与"忘了写"区分开。
3. **领域轴**：确实需要专属处置 → 自定轴名，并用 `modules.agent.progressive.decision_contract.register_decision_contract` 登记能处置它的决策。只加轴不加决策 = "只有传感器没有执行器"，铁证。

### 10.4 权威阶梯 L0/L1/L2（为什么你的 trigger 有时"被让位"）

决策脑与 System-1 反射共存，靠三级权威避免打架（幂等）：

| 级 | 谁 | 例子 | 能否被软预算/让位 |
|---|---|---|---|
| **L0** | 安全/记账/完整度红线 | 预算硬顶、gate BLOCK、loop 迭代未达标 | 不可协商（软预算耗尽仍生效） |
| **L1** | 决策脑语义决策 | replan / conclude / converge | 权威最高的"决定" |
| **L2** | advisory 反射 | 大多数领域停滞提醒 | 软预算耗尽即让位；L1 在效期内也让位 |

你写的普通领域 trigger 默认是 **L2**：当 LLM 刚拍了 replan/conclude/converge，你的反射会**自动让位**（不会去注一个和刚拍板动作打架的"补做步"）。这是 SDK 内建的幂等保护，你无需关心实现，只需知道：**想让信号在收尾阶段也一定被听见，就升 L0（`l0_event`）；否则默认 L2 足够。**

### 10.5 怎么注册（SDK 公开 API）

```python
from krow_agent_sdk.metacognition import (
    register_situation_contributor,
    register_wake_trigger,
    register_decision_classifier,
    get_registry_snapshot,
)

# 传类/函数对象即可（facade 自动推导并校验 FQCN 可 re-import）
register_situation_contributor(DownloadCompletenessContributor)
register_wake_trigger(wake_zero_download_with_hits)

# debug：确认注册上了
snap = get_registry_snapshot()
assert any("DownloadCompletenessContributor" in c for c in snap["contributors"])
```

**在哪调用**：进程启动早期一次即可（如你的 plugin 装配函数、或 app 启动脚本）。注册是**幂等**的。

**注册≠激活**：注册只是让你的 contributor 进候选池；它是否对某个具体任务生效，取决于每拍的 `applicable(executor)` 判定。所以务必写单测走 `register → load → applicable → __call__` 全链路（见 §10.7）。

### 10.6 真实范例：litsci 文献检索

litsci 是"基于 SDK 开发、独立配置三注册表"的活例子（源码 `packages/krow-worker-litsci-plugin/krow_worker_litsci/litsci_situation_contributors.py`）：

- **观测层** `LitsciPipelineContributor`：从 `litsci_download_pdf` 的 `counts` + `litsci_paper_search` 的 `papers` 读计数 → `error_vector.litsci_download_gap` + 检索/确认/下载 signals；
- **唤醒层** `LitsciDownloadGapTrigger`（检索有果却零下载 / 下载失败率越阈）+ 复用核心停滞触发器覆盖 17 分钟空转；
- **接线**：litsci worker boot 时调 `register_litsci_metacog()` 自注册（独立分发无 runtime 时静默跳过，不拖垮 boot）;
- **可观测**：决策脑运行时 emit `cognitive.situation` / `cognitive.decision_wake` / `cognitive.decision_feedback`，SDK 默认订阅。

> 完整可跑 demo：cookbook [`examples/cookbook/litsci-metacog/`](../../packages/krow-agent-sdk/examples/cookbook/litsci-metacog/)（自包含合成域，演示 contributor + trigger 注册 + 单测断言"注册≠激活"）。

### 10.7 反模式黑名单（都有铁证）

| 反模式 | 症状 | 解 |
|---|---|---|
| **"注册≠激活"半边墙** | 注册了但 `applicable` 恒 False / FQCN 不可 re-import → 加载期 silent 跳过 | facade 注册期已 fail-loud 挡不可 re-import；再写 `register→load→applicable` 单测闭环 |
| **无 ground-truth 的 error_vector** | 把 LLM 自评/启发式当"离验收距离" → 停滞判定假阳假阴 | 只有真值背书的分量进 error_vector，其余进 signals |
| **唤醒风暴** | 同一条件每拍唤醒 → 淹没真信号 | 每形态每任务 `self._fired` 一次 + 靠 signals 键天然门禁 |
| **传感器失活假阳** | `applicable` 恒真却零产出 → 拖累 dead-sensor 自检 | `applicable` 收窄到"有活跃领域信号"才 True |
| **在 executor 上挂新账本** | 自造 pipeline 状态 → 与工具 output SSOT 漂移 | 复用工具返回值 / `_step_results`，不新造 |
| **只有传感器没有执行器** | 触发器不声明 `error_axis` → 一直唤醒而系统不知道该拿它怎么办（满秩矩阵报"无从校验"） | 按 §10.3 三种姿态之一声明：核心轴 / `AXIS_ADVISORY` / 领域轴 + `register_decision_contract` |
| **手打轴名字符串** | 轴名是"传感器 ↔ 执行器"对齐键，打错一个字母不报错，只让满秩矩阵静默缺一格 | 引用常量：`from krow_agent_sdk.metacognition import AXIS_PRIMARY_ERROR, CORE_AXES` |

### 10.8 三级准入 A/B/C：ground-truth 铁律不是"一刀切"（2026-07-23）

> 设计 SSOT：。

早期为防"Goodhart 假信号"，我们对**所有**注册内容一律要求"先有 lessons/铁证"。实践证明这**过谨慎**——它把"观测"与"自主行动"混为一谈，导致新任务族要等出事才能享受决策脑。现改为**按准入等级分档**：门槛与"决策脑据此做多大的自主动作"挂钩，越自主越严。

| 准入级 | 覆盖内容 | ground-truth 要求 | 何时可注册 |
|---|---|---|---|
| **A 观测级** | `signals`（任意事实明细）+ `warning-only` 触发器（只 emit 事件/日志，不改动作） | **无**——鼓励**提前预判**注册 | 随时；只要"想看见"就注册 |
| **B 咨询级（L2）** | L2 advisory 触发器（会注入决策请求块、影响 LLM，但软预算/L1 在效期内让位） | **观测到模式**（如 nightly journey 复现 N 次、或有明确因果假设） | 有可复现的观测证据后 |
| **C 自主级（L0 / error_vector）** | `error_vector` 分量 + `l0_event` 触发器（进停滞/信用结算、软预算耗尽仍生效） | **强 ground-truth**（gate / 校验器 / 真机 journey 真值背书） | 有真值可校准后（原铁律不变） |

**判定口诀**：**越自主，门槛越高**。只想"看见"→ A 级（随便注册，进 `signals`）；想"提醒 LLM"→ B 级（要有观测证据）；想让系统"据此自动停滞判定/记信用"→ C 级（必须真值背书）。这样**所有任务族都能立刻用 A 级把领域信号接进来**（提前预判），而 C 级仍严防 Goodhart。

**正/中性反馈（signed salience）**：决策脑不再只对"故障"（负向）反应——核心已内建**正半轴**（`pace_ahead` 进度显著领先预算 / `early_convergence` 已达标而预算有余）与**中性半轴**（`context_shift` 出现计划未预期的新缺口维度）触发器，对应新动作 **conclude 提前落袋** 与 **deepen 机会性深化**。这些是 domain-neutral 核心能力，**你无需注册即自动享受**；你只需按上表把领域 `signals` 喂进快照，正向触发器会读通用派生信号（progress/burn/quality_deficit）自动工作。三重阻尼防 scope creep：正向唤醒走**独立子配额**（永不挤占负向/L0）、**一次性**、`deepen` 仅在交付规格留有质量余量（`quality_headroom` 信号）时才渲染且**严禁扩展用户未要求的范围**。

### 10.9 让决策脑替你动手：执行面注册（2026-07-30）

> API 速查见 [`api-reference.md`](./api-reference.md) §9.7；本节讲**判据怎么选**——那才是写执行器唯一值钱的部分。

§10.1–10.8 讲的全是**观测面**：让决策脑看见你的领域。但看见之后由谁动手？在此之前答案是"只能是核心那几条通用决策"。于是外部开发者能做的极限是把信号发出去，然后期待 `replan` / `converge` 恰好对症——这正是本仓吃过多次的那种半边墙的**扩展面版本**：有传感器没执行器。

现在两个执行入口都对外开放（`krow_agent_sdk.actuation`）：

| 入口 | 什么时候被问 | 你回答什么 |
|---|---|---|
| **StepActuator** | 每个 step 执行完之后 | "这里缺一步，我补上"（纯加法） |
| **ReframeProvider** | 同上，但**先于**所有补救执行器 | "当前这条路子饱和了，撤掉余步换一条"（减法 + 加法） |

**为什么减法要单独有个入口**（这是整套机制的由来）：补救执行器只会往计划里**加**步。当一条路子本身走不通时，加步只是在同一堵墙上多撞几次——真机上表现为"越努力越贵、产出不变"。所以撤步与起新路必须在**同一次动作**里原子生效，且撤步由通用层裁决（三条不变量：已执行步不撤 / 交付步不撤 / 被依赖步不撤），provider 只描述意图。

#### 判据纪律：三条

**① 零 LLM**。执行器是 System-1：确定性、可 unit test、毫秒级。要语义的部分留给它注入的那一步——`purpose` 里把"做什么、为什么、不要再做什么"写成**成品指令**（TURBO 总则②），参数由 micro LLM 按语义填。写成"继续处理"这种零件文案等于什么都没说。

**② 自判适用性**。不认自己这一族就返 `None`，别靠注册顺序抢。判据要读**你的领域产物**，不要读"过了多少拍"——后者会在 agent 正常跑别的步骤时假开火。

**③ 饱和签名选"产出"，不选"时间"**。`saturation_counter()` 的用法是每次观测喂一个**产出签名**，签名没变即 +1、变了归零：

```python
from krow_agent_sdk.actuation import make_reframe_plan, make_plan_step, saturation_counter

class MyReframeProvider:
    def __init__(self) -> None:
        self._counter = saturation_counter(3, label="smart_layer")

    def __call__(self, exe, plan):
        if not _is_my_family(exe):
            return None
        # 签名 = 这条路子的产出。内建三族分别取：store 四桶计数（推理）/
        # 相位 progress（wiki 编译）/ 成功出图数（PPT）——都是"做出来了多少"。
        if not self._counter.observe_signature(_my_output_signature(exe)).saturated:
            return None
        step = make_plan_step(exe, tool="my_open", purpose="…换一条路子的成品指令…")
        return make_reframe_plan(
            drop_step_ids=_pending_ids_of_saturated_path(plan),
            new_step=step,
            reason="smart_layer 连续 3 拍无新产出",
            telemetry={"signature": _my_output_signature(exe)},
        )
```

注意通用的 `ActDeclaredReframeProvider` 用的签名是"**尝试**次数涨了、**成功**次数没涨"——它刻意不看"没动静"，因为不动 ≠ 饱和（agent 可能正在别处干正事）。你自定义签名时保留这个性质：**饱和 = 在试、且试不出新东西**。

#### 记账：不登记契约 = 报表上你从没动过手

`ledger.actuations` 按**决策名**计数，计数前查契约表，没登记的动作直接不计。铁证在治理文档 §9.0 第 3 项：四个内建执行器天天注入步骤，报表 `actuations_total` 恒 0，据此得出的结论是"决策脑从不动手"——差一点据此把功能退休。所以：

```python
register_reflex_decision(
    "my_gap_fix", authority="A3",
    actuator="my_pkg.actuators:MyActuator",   # 与 register_step_actuator 同一字符串
    axis="my.gap",                            # 先 register_domain_axis 登记
    max_fires=2,
)
```

换框架**不要**自己起决策名，用现成的 `DECISION_REFRAME`（全族共用一个名字是刻意的：按族拆名会把一个控制律的指标拆成 N 份，横向比不了）。想知道"我这一族到底通电了没有"，读结案 `metacog_decision_stats["actuation_sources"]`——它按**来源类**分档，正是为这个问题加的。

#### 反模式（执行面专属）

| 反模式 | 症状 | 解 |
|---|---|---|
| **不登记契约就开火** | 动作真生效，报表 `actuations_total` 恒 0 → 复盘结论反向 | `register_reflex_decision` + 动作带 `decision=` |
| **把请求当结果** | 遥测里写"撤了 5 步"，实际被不变量挡下 3 步 | 只信 `cognitive.actuated` 事件里的 `dropped_steps` |
| **无界执行器** | 每拍都注一步 → 计划膨胀、预算烧光 | `max_fires` / 自己的 `MAX_FIRES`，触顶让位 `converge` |
| **饱和签名读时间** | agent 干别的正事时假开火，把好路子撤了 | 签名只读本路子的**产出** |
| **能声明却写了 provider** | 15 个内建 ACT 都靠 yaml 覆盖，你多维护一份 python | 先试 `reframe_frameworks`，判据要读领域产物时才写 provider |
| **耗尽时假装成功** | 所有路子试完仍返回"新步" → 空烧到预算耗尽 | `make_reframe_plan(new_step=None)` 只撤不加，把缺口交给 `converge` 如实收敛 |

**在哪注册**：与 §10.5 同款——进程启动早期一次，幂等。headless / K8s 下注册表是**进程内**状态，每个 Pod 都要跑到；`get_actuation_snapshot()` 启动后打一行日志自检。

---

## §11 多 Agent 轻量协同（A 层 persona + B 层 delegate · v0.9.0.31+）

> 一篇指导：如何用 SDK 让多个 agent **分工协作**——给每个 agent 独立身份与行为准则，并让「组长」把子任务**派给**「组员」，而不是自己埋头干。

### 11.1 要解决的问题

实践中常见这样一幕：你想让一个组长 agent 把活分配给几个组员 agent，但组长**总是自己把活干了**。根因有两条，缺一不可同时治：

| 根因 | 层 | 表现 | 解法 |
|---|---|---|---|
| **身份/纪律缺失** | 默认 macro 基座身份是「任务规划与执行指挥官」，prompt 还含「必须包含至少一个执行步骤」「不要无工具执行就下结论」等**自执行**指令 | 即使你口头说「你是组长」，模型仍按默认 prompt 自己执行 | **A 层**：`with_agent_identity` + `with_persona_directives` 注入最高优先级身份与准则，覆盖默认 |
| **能力缺失** | 组长手上**没有委派工具** | 即使想委派，也无工具可调，只能用现有工具自己做 | **B 层**：`with_team_member` 自动注入 `delegate_to_member` 工具 |

A 层让组长「想委派」，B 层让组长「能委派」。二者配合才彻底。

### 11.2 A 层：身份与行为准则（最高优先级 prompt 注入）

prompt 注入对 agent 的影响是**分等级**的——Krow 用 `PromptPriority`（`CRITICAL` / `HIGH` / `NORMAL` / `LOW` / `URGENT`）控制各段在最终 prompt 中的物理顺序，利用 LLM 注意力 U 型曲线（开头 primacy + 结尾 recency 最受重视）。

- `with_agent_identity("一句话角色")`：覆盖默认身份段。
- `with_persona_directives("多段行为准则")`：注入到**安全红线之后的 `CRITICAL` 段**（primacy），并在 prompt **末尾**追加「冲突时以行为准则为准」提醒（recency）。当你的身份要求（如「只分配不执行」）与默认规则（如「必须有执行步骤」）冲突时，以你的准则为准。

二者均 **fail-loud**：传空 / 纯空白 / 超长 → `ValueError`（显式声明却给非法值不静默吞掉）。不调用时行为与旧版**逐字节一致**（零回退）。

```python
researcher = (
    AgentBuilder().from_env()
    .with_agent_identity("你是严谨的资料研究员，负责列要点、核查事实，不做润色。")
    .build()
)
```

### 11.3 B 层：委派工具与组员寻址

`with_team_member(name, member, *, description="")` 注册组员；注册 ≥1 个后 `build()` 自动给组长注入 `delegate_to_member(member_name, task)` 工具。工具描述里会列出所有组员名 + 简介，帮组长选人。

`member` 两种形态：

1. **SDK `Agent` 实例**（同进程委派，最常用、最稳健）。委派 handler 调 `member.run(task)`。
2. **`Callable[[str], dict]` runner**（自定义传输，用于**跨进程**协同）。runner 入参子任务字符串，返回标准结果 dict（至少含 `summary` / `success`）。

委派结果统一规范化为：`{"ok", "success", "summary", "output_files", "duration_seconds", "member"}`。

```python
leader = (
    AgentBuilder().from_env()
    .with_agent_identity("你是项目组长，负责拆解任务并分配给组员，不亲自执行。")
    .with_persona_directives(
        "收到任务后必须用 delegate_to_member 把子任务派给组员；"
        "检索类派给 researcher，撰写类派给 writer；你只分配与汇总。"
    )
    .with_team_member("researcher", researcher, description="资料搜集与事实核查")
    .with_team_member("writer", writer, description="把要点润色成通顺文字")
    .build()
)
result = leader.run("准备一段关于太阳能两个优点的简短介绍。")
```

### 11.4 跨进程协同（启动多个 agent 进程）

把 `member` 传成自定义 runner，在 runner 内以子进程 / HTTP 调用另一进程的 member agent。子进程模式（稳健、无端口 / 鉴权负担）示意：

```python
import json, subprocess, sys

def subprocess_member_runner(role: str, identity: str):
    def _run(task: str) -> dict:
        payload = json.dumps({"role": role, "identity": identity, "task": task})
        proc = subprocess.run(
            [sys.executable, "member_worker.py"],
            input=payload, capture_output=True, text=True, timeout=300,
        )
        # member_worker.py 内 build 一个 member Agent 跑 task，把结果 JSON 打到 stdout
        return json.loads(_extract_result_line(proc.stdout))
    return _run

leader = (
    AgentBuilder().from_env()
    .with_agent_identity("你是组长，只分配不执行。")
    .with_persona_directives("必须用 delegate_to_member 把子任务派给组员。")
    .with_team_member("researcher", subprocess_member_runner("researcher", "你是研究员"))
    .with_team_member("writer", subprocess_member_runner("writer", "你是撰写员"))
    .build()
)
```

参考实现：仓库 `tests/sdk/_team_member_worker.py`（组员子进程入口）+ `tests/sdk/test_multi_agent_coordination_real_llm_e2e.py`（1 组长 + 2 组员子进程的真实 LLM 协同 E2E）。

### 11.5 约束与边界（务必读）

- **不可重入 / 不可并发**：同一 `Agent` 实例不能并发或重入 `run`（`Agent._run_lock`）。同进程委派**串行**执行（组员 run 期间组长阻塞）。不同组员实例彼此独立、可分别 run。
- **禁止自委派**：不要把组长自己注册成自己的组员（重入必炸）。
- **预算 / 超时**：组长一次 run 会触发组员的完整 run，叠加 `with_budget` / `with_tool_execution_timeout` 要给足额度。
- **轻量边界**：本方案面向少量组员、串行 / 自定义传输的轻量场景。**重量级分布式高并发**多 agent 编排由 Krow Cloud 云端方案承载，不在 SDK 内实现。

---

## §12 对话槽硬锁 ACT + 工具宇宙裁剪（v0.9.0.33+）

### 12.1 为什么需要硬锁

默认 SDK 把「用哪个 ACT」当作**语义决策**交给 macro LLM：`task_context.act_name` 只是**软提示**——把该 ACT 的 `planner_hint` 置顶 + 完整披露，但**不禁止**切换、**不裁**工具宇宙（macro 工具快照默认是全局注册表，避免废掉文件 / 文档 / 搜索等跨域基础能力）。

这在「对话槽固定角色 agent」场景会出事：一个 `team_leader` agent 只该做「拆解 + 派单」，它的派单工具是自定义 ACT 工具 `tl.create_task`。但语义选择器 / LLM 可能漂移到内置写作 ACT 的工作流，于是组长**既被纪律禁止自办、又在当前工作流里找不到派单工具** → 死路。根因不是工具被物理删除（它仍在全局注册表），而是 LLM 被错误的 ACT 引导带偏。

### 12.2 两个确定性开关

`with_locked_act(act_name, *, tool_universe="global")`（或等价 per-run `task_context` 键 `lock_act` / `tool_universe`）：

1. **`lock_act=true`（锁 ACT 选择）**：强制 pin 到 `act_name`，并**抑制其它 ACT** 的引导与菜单（macro LLM 看不到别的 ACT 作为可选项）——从根上消除漂移。这一步通常已足够修复「找不到派单工具」：抑制写作 ACT 引导后，LLM 只会按 team_leader 工作流走，而 `tl.create_task` 本就在全局快照里可见。
2. **`tool_universe="act_only"`（裁工具宇宙 · 额外硬化）**：把发给 LLM 的 macro 工具快照裁到「该 ACT 工具 + 内部工具」。**只裁 prompt 快照，不动 `ToolManager` 注册表**——`lookup_tool_docs` 逃生口仍在；`plan_task` 白名单校验仍读全量注册表，不会因裁剪误杀。

### 12.3 三条不可破的红线（实现保证）

- **内部工具永不裁**：`llm_generate` / `run_step` / `native.*` / `editor.*` / `knowledge.*` / `kg_*` / `kb_*` / `krow_*` / `lookup_tool_docs` / `deep_reflect` 在 `act_only` 下始终保留（否则 agent 连基本规划 / 生成都做不了）。
- **解析不到就不裁**：若解析不到锁定 ACT 的工具集（未知 ACT），自动回退为不裁（宁可多给工具，绝不误删 `tl.create_task` 这类派单工具）。
- **缺省零回退 + 任务槽零影响**：不传这三个键 → 行为逐字不变；普通任务槽（`act="self"`）完全不受影响。

### 12.4 fail-loud 校验（指定≠采用）

只校验这三个新键，不波及其它 `task_context` 键。以下情况抛 `ACTLockValidationError`（`ValueError` 子类）：`lock_act` 非 bool；`tool_universe` 取值非法；`lock_act=true` 缺 `act_name`；`tool_universe="act_only"` 未配 `lock_act=true`（裁工具却不锁 ACT 会与裁后的工具宇宙不一致）。这是 AGENTS.md「指定≠采用」反模式的落地——显式声明的契约不可满足时必须在系统可见处 fail-loud，禁止 silent no-op。

### 12.5 完整示例

```python
from krow_agent_sdk import AgentBuilder

leader = (
    AgentBuilder().from_env()
    .with_act_plugin(team_leader_act_plugin)   # 声明 team_leader ACT，get_tool_names()=["tl.create_task"]
    .with_tool_plugin(dispatch_tool_plugin)    # 注册 tl.create_task
    .with_locked_act("team_leader", tool_universe="act_only")
    .with_agent_identity("你是项目组组长，只拆解 + 派单，绝不亲自撰写正文。")
    .with_persona_directives(
        "## 组长纪律（最高优先级）\n"
        "- 必须用 `tl.create_task` 把每个子任务派给团队成员。\n"
        "- 禁止用写作 / 文件工具自己完成正文。"
    )
    .build()
)
result = leader.run("产出一份市场调研简报，拆解后逐个派给团队成员。")
```

参考实现：`tests/sdk/test_conversation_act_lock_real_llm_e2e.py`（锁 team_leader 后直接 `tl.create_task` 派单、不漂移到写作 ACT 的真实 LLM E2E）+ `tests/sdk/test_sdk_conversation_act_lock.py`（校验 / 抑制 / 裁剪 / 零回退单测）。

### 12.6 与 `act_name`（软提示）/ persona 的分工

- 需要**确定性**禁止漂移（对话槽固定角色）→ `with_locked_act`。
- 只想**优先**某 ACT 但仍允许 LLM 跨域兜底 → 只传 `task_context.act_name`（软提示）。
- 锁 ACT 解决「用哪个工作流 + 哪些工具」；persona（§2.4.1 `with_agent_identity` / `with_persona_directives`）解决「你是谁 + 行为纪律」。对话槽组长通常**三者合用**：锁 team_leader + 组长身份 + 「只派单不自办」纪律。

---

## 进一步阅读

- [`quickstart.md`](./quickstart.md)：5 分钟入门 + 5 类 plugin 范例
- [`external-developer-onboarding.md`](./external-developer-onboarding.md)：第 1 周节奏 + 3 种领域适配
- [`runtime-install.md`](./runtime-install.md)：runtime wheel 装机指南
- [`roadmap.md`](./roadmap.md)：SDK 进度 + milestone

---

> 文档版本：跟随 `krow-agent-sdk` PyPI 主版本同步发布；当前与最新 patch 对齐
> （当前 PyPI: <https://pypi.org/project/krow-agent-sdk/>）。本文档持续吸纳社区反馈 —
> 欢迎到 [GitHub Discussions](https://github.com/aullik5/krow-sdk-docs/discussions) 提建议。
