# 归档 · TURBO 时代的公开文档原文（0.9.5.27 之前）

> **状态：历史归档（legacy）。不是推荐做法，不提供兼容指导。**
> - **是什么**：`krow-agent-sdk` 0.9.5 之前，公开文档用「TURBO 哲学」命名设计原则，TURBO 同时也是当时的默认运行模式（macro / micro ReACT 栈）。本文件逐字保留这些章节在 0.9.5.27 文档更新**之前**的原文，供查证历史措辞用。
> - **现在的口径**：0.9.5 起默认运行模式是 **klik**。TURBO 的两条总则（①语义交给 LLM、语法交给系统；②给 LLM 成品不给零件）连同「准确 > 完整 > 速度 > 成本」价值观，作为 klik 的「继承不变」三条原封保留，只是不再叫 TURBO——见 [`advanced-development-guide.md`](../advanced-development-guide.md) §1 / §1.10。
> - **turbo 运行模式的地位**：**回退模式**，代码路径保留（`KROW_RUN_MODE=turbo` 可切），平台计划退役——这是治理决定，不是代码现状。公开文档不再提供 turbo 用法，本归档也**不**教你怎么在 turbo 下写 plugin。
> - **替代路径**：新项目一律按 klik 写——[`quickstart.md`](../quickstart.md) §0.1、[`api-reference.md`](../api-reference.md) §2.4.4、[`advanced-development-guide.md`](../advanced-development-guide.md) §1.10；要上架 Krowwork 插件市场的看 [`plugin-marketplace-guide.md`](../plugin-marketplace-guide.md)。
> - 本文件不在默认导航里，只从 roadmap、进阶指南与 API 参考 §2.4.4 的脚注链接到达；原文中的行号、版本号均为归档时的状态，不再维护。原文里指向同目录文档的相对链接按本文件所在的 `archive/` 位置改为 `../`，其余文字逐字未动。
> - **收录范围**：只收录 0.9.5.27 更新前**确实已在本公开仓发布过**的文字；内部文档里从未公开的段落不在归档之列。原文中指向内部文档的链接已按公开政策剥离，个别句尾因此不完整（如 §1.8 第 4 条），属剥离痕迹，不是原文如此。

---

## 一、`advanced-development-guide.md` §1「TURBO 哲学」原文（更新前全文）

> 以下为 0.9.5.27 文档更新前该章原文，逐字保留；其中对其它章节的 §引用按原文件当时的编号。

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

## 二、其它公开文档中被改口的 TURBO 措辞（更新前原句）

| 文件（公开仓 `docs/` 下） | 更新前行号 | 原句 |
|---|---|---|
| `quickstart.md` | 7 | > - [`advanced-development-guide.md`](../advanced-development-guide.md) — TURBO 哲学 / 工具设计 / 测试方法论 |
| `quickstart.md` | 712 | 2. **架构上**：读 [`api-reference.md`](../api-reference.md) §5 的 10 类 plugin protocol（6 stable + 4 experimental）；[`advanced-development-guide.md`](../advanced-development-guide.md) §1 TURBO 哲学 / §4 ACT 最佳实践 / §6 测试方法论 |
| `external-developer-onboarding.md` | 589 | \| [`advanced-development-guide.md`](../advanced-development-guide.md) \| TURBO 哲学 / 工具设计 / 测试方法论 \| |
| `api-reference.md` | 8 | > - [`advanced-development-guide.md`](../advanced-development-guide.md) — TURBO 哲学、设计原则、最佳实践 |
| `api-reference.md` | 1188 | #### 反模式（设计文档 §0.1 TURBO 哲学） |
| `api-reference.md` | 1919 | > **铁律（设计文档 §0.1 TURBO）**：hint 是给 LLM 的语义建议，不能用来"教 LLM 别用某工具"或"教 LLM 别犯错"。物理性约束应通过 [GatePlugin](#54-gateplugin--加新-concludeguard-gate-p4) 或 ACT 工具白名单实现。 |
| `advanced-development-guide.md` | 493 | - ❌ ToolPlugin 内调 LLM（System 1 工具禁止 — TURBO 边界） |
| `advanced-development-guide.md` | 1757 | > ⚠️ **TURBO 边界**：System 1 工具内**禁止**调 LLM。LLM-driven 工具的合理形态是把工具上层"ACT-内 ReACT 循环"作为驱动方，工具本身仍是 deterministic helper。详 §1.4 反模式 C。 |
| `advanced-development-guide.md` | 2155 | ### 8.1 TURBO 边界违反 |
| `advanced-development-guide.md` | 2502 | **① 零 LLM**。执行器是 System-1：确定性、可 unit test、毫秒级。要语义的部分留给它注入的那一步——`purpose` 里把"做什么、为什么、不要再做什么"写成**成品指令**（TURBO 总则②），参数由 micro LLM 按语义填。写成"继续处理"这种零件文案等于什么都没说。 |

---

> 归档日期：2026-10-23（配套 `krow-agent-sdk` 0.9.5.27）。如需查更早的版本，用公开仓的 git 历史。
