# Krow Agent SDK + Plugin 架构设计（v0.8 已落地 · 2026-05-11 起源 / 2026-05-14 文档维护）

> **状态**：**Step 1 + Step 2 / M1-M4 工程已全部落地**（PR #174 起步 → #235 / #265 / #279 / #281 / #295 / #297）；
> 主仓 `modules/agent/sdk/` + `packages/krow-agent-sdk/` 为代码 SSOT，本文档为**设计辩论历史 + 设计意图 SSOT**.
> 进度跟踪以 [`roadmap.md`](./roadmap.md) 为唯一 SSOT；本文档是设计依据/铁证/辩论记录的归档.
> **作者**：krow team（2026-05-11 plugin-arch-design 会话产物，累积 8 轮辩论 + 1 轮"顶级开发者 / 顶级架构师"双视角 review）
> **v0.8 修订摘要（顶级 review 双视角，详 §13 Review Backlog）**：识别 11 个 P0 + 10 个 P1 问题并落地修订。**架构关键 P0**：（A1）runtime_checkable 加 plugin signature validator；（A2+A3）Protocol 优先级分层（mvp_critical / stable / experimental）+ 增减治理协议；（A6）build() 时连接验证；（A7）LLMSourceModule enum frozen 撞墙修复（改 `Union[BuiltinLLMSourceModule, str]`）；（A9）DomainPack supplement 总量上限（同 ACT 16KB / 全进程 64KB）；（A10）`agent.event_bus` 改 `EventBusReader` 只读 facade；（A13）S1.5/S1.6 blast radius 重估拆 sub-PR；（A16）反向 telemetry opt-in。**开发者关键 P0**：（D1）包名 import 路径双轨表 + Step 1 alias；（D3）error class 完整 message 文本；（D6）`KROW_SDK_PLUGIN_ERROR_MODE`；（D7）多租户部署模式子节。
> **第 8 轮辩论修订**：（1）turbo_diagnostics 维持现状不接入 v1（subagent 铁证 v1 已被 v2 替代）；（2）DomainPack 扩展为 8 元素 OPTIONAL；（3）API key 替换虚构的 KrowAuthSession（17 处修订 + Step 1 PR S1.17 必修 dead code）；（4）确认 PR #174 OPEN/REVIEW_REQUIRED
> **触发原因**：krow 团队的其他开发者要基于 krow 做工业设计 / 科研等垂直场景的深度定制；当前"扩展暴露的接口太少"导致他们必须 fork 主仓——本文要解决"不 fork、不 check-in 同一份代码"前提下让外部团队最大程度获得开发自由度的架构问题。
> **元规则对齐**：本文档是 design doc，不是元规则更新（不进 `AGENTS.md`）. 按 `AGENTS.md` (internal) §7.7 走独立 design-doc PR；落地后元规则更新走独立 PR.
> **决策方法**：按 `AGENTS.md` (internal) §4.2.2 架构缺陷流程：事实 → 铁证 → 辩论 → 修 → 复测；§6.2.2 5 顾问 review；§十二 元教训"渐进治理 + warning-only 起步".
>
> **历史锚点提示**（2026-05-14）：本文档大量引用 `AGENTS.md` 章节（§7.7 / §13.9 等）反映**辩论时期**的元规则版本（2026-05-11 时 AGENTS.md 含 §7.7 元规则文件独立 PR 协议、§13.9 SDK Roadmap）. 当前 `AGENTS.md` 已重构为**精简元规则**（§零 ~ §十二），**§13.9 SDK Roadmap 已迁到 [`docs/sdk/roadmap.md`](./roadmap.md)**（SSOT，`AGENTS.md` §十一 仅指针）；§7.7 元规则文件独立 PR 协议仍在 `AGENTS.md` §七 内. 本文档保留辩论时期的 §-引用作历史快照，**不**与当前 `AGENTS.md` 章节号一一对应.

---

## 目录

- [§0 背景与现状边界（铁证）](#§0-背景与现状边界铁证)
- [§1 设计目标与非目标](#§1-设计目标与非目标)
- [§2 容器形态决策](#§2-容器形态决策)
- [§3 LLM + Auth + Billing 强绑设计](#§3-llm--auth--billing-强绑设计)
- [§4 原生能力分层](#§4-原生能力分层)
- [§5 Plugin Protocol Spec（9 个）+ 3 个"不开 Protocol"策略声明](#§5-plugin-protocol-spec9-个-3-个不开-protocol策略声明)
- [§6 SDK 顶层 API（AgentBuilder）](#§6-sdk-顶层-apiagentbuilder)
- [§7 项目根目录策略](#§7-项目根目录策略)
- [§8 5 顾问专家辩论](#§8-5-顾问专家辩论)
- [§9 渐进路线图](#§9-渐进路线图)
- [§10 可逆性 / blast radius / feature flag](#§10-可逆性--blast-radius--feature-flag)
- [§11 测试 SDK（krow_test_sdk）](#§11-测试-sdkkrow_test_sdk)
- [§12 风险登记 + 已知未解决项](#§12-风险登记--已知未解决项)
- [§13 Review Backlog（v0.8 顶级 review 落地清单）](#§13-review-backlog)

---

## §0 背景与现状边界（铁证）

> 本节所有数据来自 2026-05-11 plugin-arch-design 会话两个调研 subagent 在 commit 时刻的现场核实，**禁止凭印象**。锚点用 `path + symbol` 形式，行号请现场用 `Grep -n` 查源码（`AGENTS.md` (internal) §0.2 文档锚点规范）。

### §0.1 现状统计

| 维度 | 数据 | 含义 |
|---|---|---|
| krow 是单包 monolith | `pyproject.toml` `[tool.setuptools.packages.find]` 把 `app* / modules* / ui* / storage* / config*` 全 include 进 `krow` 一个包 | "agent 引擎"没有独立包边界 |
| `modules/agent/` 体量 | 62 个 `.py` 文件 + `progressive/` 14 个 + `act/` 9 个 + `act/acts/` 19 个 ACT 包 + `react_templates/` 多个 | 引擎规模 ≈ 100+ 文件 |
| 单文件最大体量 | `modules/agent/agent_v3.py` 5350 行 | god class，既是入口又是大量业务逻辑 |
| 现有"懒加载导出"非"稳定 API" | `modules/agent/__init__.py` 用 `get_agent_v3()` / `get_planner_v3()` / `get_v3_bootstrap()` 等工厂函数暴露内部类 | 是 import 加速优化，不是 SDK facade |
| 部署形态 | `pyproject.toml` 有 `[desktop]` / `[headless]` / `[remote]` / `[knowledge]` 等 extras | 解决"装哪些依赖"，不解决"外部如何扩展" |

### §0.2 已存在的 OCP 扩展点（直接复用为 Plugin Protocol 实现底座）

`AGENTS.md` (internal) §0.2 "造轮子检查"4 步：每个 Plugin Protocol 必须先查现有 OCP 扩展点，能复用就不造新轮子。

| 现有 OCP 扩展点 | SSOT 路径 | 复用为 |
|---|---|---|
| `register_binary_rescuer(ext, rescuer)` | `modules/agent/agent_v3.py` | 二进制装配兜底（PPTX rescue），可作为 plugin OCP 模式的样板 |
| `ACTLoader.register_extension_act(ext_name, file_path, tools)` + 自定义 `acts_dir` | `modules/agent/act/act_loader.py` | **P1 ACTPlugin** 实现底座 |
| `ACTManager.register_act(act)` / `unregister_act` | `modules/agent/act/act_manager.py` | **P1 ACTPlugin** 实现底座（运行时注册） |
| `ToolManager.register_tool(...)` | `modules/tools/manager.py` | **P2 ToolPlugin** 实现底座 |
| `_get_headless_disabled_tool_names()` 聚合 | `modules/tools/manager.py` | **P2 ToolPlugin** headless 自声明扩展点 |
| `BudgetController._FORWARD_MAP` 字典扩展 | `modules/agent/progressive/budget_controller.py` | **P5 EventListenerPlugin** 监听 `budget.*` 的底座 |
| `GateChain.register(gate)` + `make_simple_gate(...)` | `modules/knowledge/conclude_guard_gates.py` | **P4 GatePlugin** 实现底座（已是 OCP 链式） |
| `EventBus.subscribe(event_type, callback) -> token` | `modules/events/bus.py` | **P5 EventListenerPlugin** 实现底座（直接暴露） |
| `MetricsRegistry` / `start_span` / `record_event` / `record_counter` | `modules/observability/__init__.py` | **P6 ObservabilityPlugin** 实现底座 |
| `ToolTraitRegistry.get_instance()` + `config/tool_traits.yaml` | `modules/agent/progressive/tool_traits.py` | **P2 ToolPlugin** 内 `latency_class` / `traits` 声明底座 |
| `init_background_task_queue(event_bus)` + `BackgroundAgentTaskQueue.submit(...)` | `modules/agent/background_task_queue.py` | 不开 Protocol，直接 SDK facade 暴露 `submit()` |
| `SandboxValidator` / `ProjectAccessPolicy` / `audit_reporter` | `modules/remote/security_policy.py` + `modules/observability/audit_reporter.py` | **P8 SecurityPlugin** 实现底座（部分复用，不完全适配） |
| `handle_visual_inspect(**kwargs)` 工具入口 + `VisualGroundingService` | `modules/agent/visual/visual_grounding_tools.py` + `modules/agent/visual/grounding_service.py` | **SDK 视觉质检函数式 API**（不开 Protocol）；外部 plugin 直接调用 |
| `register_visual_adapter(ext, adapter)` + `VisualAdapter` 协议 | `modules/agent/visual/visual_grounding_tools.py` + `modules/agent/visual/protocol.py` | **SDK Builder `with_visual_adapters_from_entry_points()`** 实现底座（不开 Protocol） |
| `ToolTraitRegistry.VERIFY_FIX` trait + `ProgressiveExecutor` verify-fix 分支（专用 prompt / 长超时 / companion 工具发现） | `modules/agent/progressive/tool_traits.py` + `modules/agent/progressive/executor.py` | **P2 ToolPlugin** 通过 `traits=["verify_fix"]` 字段获得闭环执行（无需新协议） |
| `ReACTEngine.register_conclude_guard(callback)` | `modules/agent/react_engine.py:ReACTEngine` | **P4 GatePlugin（phase="micro_react_conclude"）** 实现底座；与 ConcludeGuard 知识链是不同栈 |
| `KrowService` FastAPI routes（`/agent/execute` / `/agent/stream/{id}` SSE / `/ws/events` WS / `/files/*` / `/sessions/*` 等 ~30 endpoints） | `modules/remote/api_gateway.py` + `modules/remote/service.py:KrowService` | **SDK Builder `with_http_gateway()`** 实现底座（嵌入式默认不启动） |
| `KnowledgeAPI` / `SessionOntologyStore.to_view()` / `GlobalOntologyStore` / `ExperienceMemoryService.recall()` | `modules/knowledge/knowledge_api.py` + `modules/knowledge/reasoning_store.py` + `modules/knowledge/global_ontology_store.py` + `modules/agent/experience_memory/` | **SDK 数据 facade `krow_agent_sdk.data`**（只读，不开 Plugin Protocol） |
| `BudgetController._FORWARD_MAP`（事件转发）+ `TaskBudget`（真实 cap/计数）+ `ProgressiveExecutor._handle_adapt_budget_extension`（扩容内核）+ `ReACTConfig`（micro 预算） | 4 处分散 SSOT | **P5 EventListenerPlugin 监听 `budget.*` + AgentBuilder.with_budget(BudgetSpec) 配置参数化**（不允许 plugin 替换内核） |

**关键发现**：8 个 Plugin Protocol + 1 个 P9 DomainPackPlugin 中 **9 个底座已具备**（仅 `HintPlugin` / `MCPServerPlugin` / P9 supplementary extended.md 需新建薄封装）。这是渐进路线图能"2-3 月内交付 MVP"的物质基础。

**视觉质检策略说明**（第 6 轮辩论决策）：
- `visual_inspect` 是工具 + VLM 服务（调 `chat_vision`，与 §3 强绑 krow cloud 一致）
- `verify_fix` 不是独立基础设施，而是 `ToolTraitRegistry` trait + ProgressiveExecutor 内核行为
- AGENTS.md §二 当前漏列 `visual_inspect` / `verify_fix` —— 落地后独立元规则 PR 补

### §0.3 反插件化障碍（Step 1 / Step 2 必修项 — 铁证）

| 障碍 | 影响 | 修复 Step |
|---|---|---|
| `get_act_loader()` 不可注入自定义目录（默认绑 `__file__.parent/"acts"` 或 `get_app_root()/modules/agent/act/acts`） | 外部 plugin 无法用自定义 ACT 根目录 | Step 2 |
| 扩展 ACT 命名空间锁定 `ext_` 前缀（`ACTLoader.register_extension_act` 强制） | 外部 plugin 名字必须 `ext_<name>`，不利于第三方 namespace | Step 2 |
| `SemanticQueryService._get_ai_manager` 回退到 `app.container._build_ai_manager`（跨层依赖） | SDK 不能在 app 层之外用 | Step 1 |
| Headless 工具黑名单**硬编码**在 `ToolManager._get_headless_disabled_tool_names()` 内 import 具体模块（`pptx_editor_v2`） | 外部 plugin 无法声明自己的 headless 不可用工具 | Step 2 |
| `AgentV3` / `ProgressiveExecutor` 与 `EventBus` / ontology / backup 横向耦合，多处内部状态 | SDK facade 提取困难 | Step 1（薄封装，不动内部） |
| `v3_bootstrap.is_v3_available` 便捷函数返回 `V3Bootstrap.get_instance().is_v3_available` **方法对象**（未调用） | 自动化集成易误用 | Step 1 修 bug |
| 双 `ChatMessage`：`modules/ai/providers.py:ChatMessage` vs `modules/ai/krow/provider.py:ChatMessage` 是不同 dataclass | 违反 SSOT，plugin 调 LLM 用哪个？ | Step 1 |
| `LLMSourceModule.CHAT` 在 `modules/ai/providers.py` 重复赋值（后赋值覆盖前赋值） | bug | Step 1 |
| `KrowService.start()` 同步阻塞 + 无依赖注入（`__init__()` 无参） | SDK 不能注入 mock / 自定义配置 | Step 1（嵌入式容器形态 A 不需要 KrowService） |
| **`turbo_diagnostics.py` 与 executor 实际是 v1/v2 关系**（subagent 第 8 轮调研铁证修正第 7 轮误判）：v1 模块（含 7 个完整公开符号 + T4_LITE_CONFIG / T5_LITE_CONFIG）**已被 `executor_recovery.py` 替代**（铁证：`executor_recovery.py` 模块 docstring 明文"取代 T4-lite + T5-lite"+ `tests/test_turbo_diagnostics.py` 注释"`_handle_failure` 不再走 T4-lite ReACT"）；executor 内 `_diagnose_and_correct` 用动态名 `f"turbo_diagnose_step_{id}"` 是**完全独立的 v2 实现**（不同 prompt / 工具集 / 超时 / 结论 schema） | **不应接入 v1**：行为/超时/结论/budget 记账均不一致，强制接入会引入回归风险（详 §5.11 / §9.1 PR S1.12 已重写） | **Step 1 不接入**；架构文档与代码漂移是主仓治理债务，不在 SDK 范围 |
| **micro ReACT 内每次 LLM 调用是否计入 macro `TaskBudget.record_llm_call`** 未确认（subagent 第 7 轮调研标"需进一步调查"） | 若不一致 → macro budget 计数失真 → adapt/replan 触发条件错乱；BudgetSpec 配置项无效 | **Step 1 必修**（PR S1.13；含 unit test 守住一致性） |
| **`ReACTEngine._effective_max_iterations`** 在 execute() 开头被设但 `while iteration < self._config.max_iterations` 仍读 `_config`（subagent 留待） | `plan_task_handler._extend_macro_budget_if_needed` 只改 `_effective_max_iterations` 时**可能未生效** | **Step 1 必修**（PR S1.13） |
| **`AuthService._login_with_api_key` 调用 `KrowAuthAdapter.set_api_key` / `get_user_info`**（v0.8 第 8 轮辩论铁证当时是 dead code）| API key 登录路径全链 | **✅ 已完成**（PR S1.17 + 后续）：`modules/auth/krow_auth.py:1509 def set_api_key` / `:1540 def get_user_info` 已实现且接通；本表保留作历史辩论快照（**不再是 Step 1 必修项**） |
| **R26（v0.8 顶级 review A1）**：`@runtime_checkable Protocol` 只查方法名是否存在，**不查签名 / 类型 / 返回值**——plugin 写错签名（如 `get_act_root` 返回 `str` 而非 `Path`）`isinstance(plugin, ACTPlugin)` 仍 True，运行时才 break ACTLoader | 违反 §1.1 "**准确性 > 完整性**"：契约名义存在，运行时被破坏；plugin ecosystem 健康度受损 | **Step 1 必修**（PR S1.18）：新建 `modules/agent/sdk/_protocol_validator.py:validate_protocol_implementation(plugin, protocol)`，启动期用 `inspect.signature` + `typing.get_type_hints` 真实校验 plugin 方法签名 vs Protocol 定义；不匹配 fail-loud（含 mvp_critical 三个核心 P1/P2/P4，stable / experimental 渐进开） |
| **R27（v0.8 顶级 review A7）**：design doc §3.3 写"运行时按 plugin_id 注册新 enum entry"——但 Python `enum.Enum` 是 frozen，运行时**不能动态加 entry**；Step 1 PR S1.3 当前实现策略一定撞墙 | LLM source_module 串联失败；audit log 不能区分 plugin；§3.3 设计错误 | **Step 1 必修**（PR S1.3 修订）：把 `LLMSourceModule` 从纯 enum 改为 `Union[BuiltinLLMSourceModule, str]`；plugin 用 `f"plugin:{plugin_id}"` 字符串命名空间；`llm_source_context()` ContextVar / audit log 兼容 `str \| BuiltinLLMSourceModule`；详 §3.3 修订 |

### §0.4 现状结论

> krow 已经具备成为"插件化 agent 框架"的所有底座，但当前**没有对外稳定 API 边界**。本文档定义这条边界。



## §1 设计目标与非目标

### §1.1 设计目标（按 `AGENTS.md` (internal) §0.0 价值观优先级排序）

| 优先级 | 目标 | 落地 |
|---|---|---|
| 1 准确性 | 外部 plugin 调 agent 的语义结果与 krow native 完全一致 | LLM 后端、ACT 选择、Gate 链、预算计算全部走主仓 SSOT；plugin 不能"绕路" |
| 2 完整性 | 8 个 Plugin Protocol 一次性提供完整能力面（`AGENTS.md` (internal) §二 基础设施清单全覆盖） | Step 1 一次性发 8 Protocol 骨架（用户决策，第 3 轮辩论） |
| 3 速度 | 外部 plugin 接入到跑通 hello-world ≤ 30 分钟（含 LLM 调用） | SDK 提供 `AgentBuilder` 链式 API + 完整 demo + `krow-sdk validate-plugin` 自查工具 |
| 4 成本 | 不为外部团队拉额外 LLM token / CI 成本 | 外部 plugin LLM 调用强制走 krow cloud（计费记录串联）；测试走 `LLMReplayStore`（确定性、零成本） |

**核心目标**：**外部团队不 fork 主仓即可深度扩展 agent 行为**——通过 import + entry_points + Protocol 实现，永远不需要 check-in 到 krow main 分支。

### §1.2 非目标（明确不做）

`AGENTS.md` (internal) §0.0 反模式："**为了'看起来快'上 cache、上启发式跳过 LLM、上 regex 替代语义判断 → 牺牲准确性换速度，业务价值倒挂**"。本设计同样守住"什么不做"。

| 不做 | 理由 |
|---|---|
| **不做沙箱化的"强进程隔离"**（subprocess / RestrictedPython） | Python 嵌入式 plugin 没有真正进程内沙箱；强沙箱与"嵌入式容器"决策互斥；强沙箱推到 Step 3（可选） |
| **不做 LLM 后端可插拔** | 用户决策：强绑 krow cloud（auth/billing/quota 串联）。外部 plugin 不能自带 OpenAI / Anthropic key 绕过 krow cloud |
| **不做 desktop UI / Qt / PySide6 暴露** | SDK 形态是 headless agent；plugin 跑在嵌入式 Python 进程或外部团队自己的 host |
| **不做 ACT / 工具的"OVERRIDE"** | 外部 plugin **只能 ADD 不能 OVERRIDE** native ACT / 工具；防止 plugin 替换 native 实现导致语义漂移 |
| **不做 StateManager / ExperienceMemory / MetaLearning 替换** | 这些是 agent 元认知核心；外部"只能用不能换"（第 2 轮辩论决策） |
| **不做 LLM Provider Plugin** | 同上，强绑 krow cloud 后没有 LLM provider 替换的需求 |
| **不做"任意 Python 代码以 plugin 名义运行"** | plugin 必须实现 Protocol；非 Protocol 调用走标准 import（不是 plugin 协议责任） |
| **不做 RPC 化**（外部进程通过 RPC 调 krow） | 容器形态 A（嵌入式）足够；RPC 化推到 Step 3（按需，可选） |

### §1.3 边界对照

| 维度 | 在 SDK | 不在 SDK |
|---|---|---|
| Agent 引擎核心 | ✅ `AgentBuilder` facade 暴露 `AgentV3` 入口 | ❌ `AgentV3` 内部 5350 行实现细节 |
| 工具/ACT 注册 | ✅ Plugin Protocol P1/P2 | ❌ `ToolManager` 内部状态、`ACTLoader` 私有方法 |
| LLM 调用 | ✅ 强绑 `KrowLLMProvider` 走 krow cloud | ❌ 直接 `import httpx` / `import openai` |
| 预算 / Adapt / Replan | ✅ EventListener 监听 `budget.*` + Builder 配 `BudgetSpec` | ❌ `ProgressiveExecutor._handle_adapt_*` 内部方法 |
| ConcludeGuard | ✅ Plugin Protocol P4 | ❌ 9 个内置 gate 实现细节（外部不能改） |
| StateManager / ExperienceMemory | ✅ 只读访问（按需要） | ❌ 替换实现 |
| 远程 / 服务化 | ❌ 不暴露 KrowService（嵌入式不需要） | ❌ relay / api_gateway / billing 内部 |
| Desktop UI | ❌ 不在范围 | ❌ |



## §2 容器形态决策

### §2.1 三种形态对照

```
A. 嵌入式（Embedded）              B. 宿主式（Host）                   C. RPC 式（Remote）
┌─────────────────────────┐      ┌─────────────────────────┐         ┌─────────────────────────┐
│ 外部团队进程             │      │ krow agent 进程         │         │ 外部团队进程            │
│  └─ from krow_sdk import│      │  └─ load plugin via     │         │  └─ rpc.call(krow_agent)│
│     AgentBuilder        │      │     entry_points         │         └────────────┬────────────┘
│  └─ build + run         │      │  └─ run plugin's ACTs   │                      │ JSON-RPC / WebSocket
└─────────────────────────┘      └─────────────────────────┘                      │
  Plugin 与 agent 在同进程        Plugin 加载进 krow 宿主          ┌────────────▼────────────┐
                                                                   │ krow agent 服务进程     │
                                                                   │  └─ KrowService start   │
                                                                   │  └─ relay / api_gateway │
                                                                   └─────────────────────────┘
```

### §2.2 trade-off 表

| 维度 | A 嵌入式 | B 宿主式 | C RPC 式 |
|---|---|---|---|
| 外部团队上手成本 | ✅ 低（pip install + 跑） | ⚠️ 中（要懂 krow 启动流程） | ❌ 高（要部署 krow 服务） |
| 外部进程隔离 | ❌ 无（plugin crash 拖死 agent） | ❌ 无（plugin crash 拖死 krow） | ✅ 有 |
| 复用 krow 基础设施 | ⚠️ 部分（EventBus / BackgroundTask 等需要外部自己起） | ✅ 全部 | ✅ 全部 |
| 计费 / billing 串联 | ✅ 强绑 krow cloud（LLM 走主流程） | ✅ 强绑 | ✅ 强绑 |
| 调试难度 | ✅ 低（同进程 stack trace） | ⚠️ 中 | ❌ 高（跨进程） |
| 启动延迟 | ✅ 毫秒级 | ✅ 毫秒级 | ❌ 秒级（首次连接） |
| 调用延迟 | ✅ 微秒级（函数调用） | ✅ 微秒级 | ❌ 毫秒级（网络） |
| 安全边界 | ❌ 弱（Python 没真沙箱） | ❌ 弱 | ✅ 强（进程隔离） |
| 多租户 | ❌ 不支持（单进程单 plugin） | ⚠️ 受限 | ✅ 支持 |

### §2.3 选 A 嵌入式（用户决策第 1 轮）

**理由**：
1. 外部团队上手成本最低（pip install + import + 跑），符合"30 分钟接入"目标
2. 复用现有 `agent_v3.py` / `progressive/executor.py` 等核心实现，无需为多进程通信改造
3. krow 已有 `BackgroundAgentTaskQueue.submit()` 等 in-process API，嵌入式天然适配
4. LLM 强绑 krow cloud → 外部团队不需要 KrowService 后台进程也能用 LLM（直接调 `KrowLLMProvider`）
5. 可逆性：未来要做 B/C，A 的 SDK API 不变，只是底层实现切换

**承担的风险**：
- 外部 plugin crash 会拖死 agent 进程
- 弱沙箱（仅声明式 + 部分硬闸门，强沙箱推 Step 3）
- 同进程内 Plugin namespace 冲突需要协议约束（详 §5.1 namespace 强制）

### §2.4 可逆性 — 未来加 B/C 不破坏 SDK API

SDK 的 `AgentBuilder.build()` 返回的 `Agent` 对象，方法集（`run()` / `arun()`）保持稳定。未来支持 B/C 时：
- B 宿主式：`AgentBuilder` 不变，底层切换为"启动 KrowService + 加载 plugin"
- C RPC 式：`AgentBuilder` 不变，底层切换为"连接远程 KrowService 通过 `RemoteAgentProxy`"
- 外部 plugin 代码无需修改

### §2.5 进程边界 / 线程边界 / 单例边界

| 类别 | 边界 |
|---|---|
| Plugin 加载 | 主进程 import 期通过 `importlib.metadata.entry_points("krow.*")` 发现 + 加载 |
| Plugin 调用 | 主进程同步调用（除非 plugin 自己显式开线程 / asyncio） |
| EventBus | 单进程单 EventBus 单例（已有 `EventBus.get_instance()`）；plugin 订阅与 native 订阅同一 bus |
| BackgroundTaskQueue | 单进程单 queue 单例（已有 `init_background_task_queue()`）；plugin 提交的任务与 native 任务同优先级排队 |
| StateManager | 单进程单 `_global_instance`；plugin 只读访问（不替换） |
| AIProviderManager / LLMProviderManager | 单进程单 instance；强绑 krow cloud（详 §3） |



## §3 LLM + Auth + Billing 强绑设计（**第 8 轮辩论修订：API key 替换虚构的 KrowAuthSession**）

> **关键修订铁证**（第 8 轮辩论）：
> 1. design doc v0.1-v0.6 引用的 `KrowAuthSession.login_from_env()` / `with_krow_session(session)` —— 仓内**完全不存在**这两个符号（subagent 第 8 轮 grep 铁证），是 v0.1 起步阶段的虚构概念。
> 2. krow cloud 已有完整 OpenAI 兼容 API key 体系（截图证据 + 仓内 `https://api.krow.cn/v1` + `Authorization: Bearer sk-user-xxx` 一致；`AuthService._login_with_api_key` password.startswith("sk-") 分支已在）。
> 3. `KrowAuthAdapter.set_api_key` / `get_user_info` 是 dead code（subagent 铁证 + 与 `docs/plan_object_centric_v1_22.md` "dead code" 标注一致）→ Step 1 PR S1.17 必修。
> 4. SDK 嵌入式形态在 headless 床天然适配 API key（OpenAI / Anthropic / Cohere SDK 均用 API key），桌面 OAuth + device flow 路径不适合 plugin 编程场景。

### §3.1 强绑链路（铁证）

```
外部 plugin 调 LLM
      ↓
SDK Builder.with_krow_api_key("sk-user-xxx")  ← 强制传入，不传 fail-loud
   或 AgentBuilder.from_env() 读 KROW_API_KEY 环境变量
      ↓
内部 KrowAuthAdapter.set_api_key("sk-user-xxx")  ← Step 1 PR S1.17 修复 dead code
      ↓
KrowAuthAdapter.get_headers() → {"Authorization": "Bearer sk-user-xxx", ...}
      ↓
LLMProviderManager（注入 KrowLLMProvider with auth_adapter）
      ↓
provider = llm_manager.get_reasoning_model() / get_chat_model()
      ↓ (实际是 KrowLLMProvider，铁证：modules/ai/krow/provider.py:KrowLLMProvider)
KrowLLMProvider.chat()
      ↓
httpx.Client.post("https://api.krow.cn/v1/chat/completions",
                  headers={"Authorization": "Bearer sk-user-xxx"},
                  json={"model": ..., "messages": [...]})
      ↓ 服务端按 api_key_id 维度计费 + 累计请求数 + 最后使用时间（截图 krow.cn 控制台可见）
      ↓ 客户端响应含 usage（input_tokens / output_tokens / cost_cp）
      ↓
modules/ai/krow/usage.py:UsageTracker.record(service_type="llm", ...)  ← 本地 SQLite 缓存仅用于客户端展示
modules/remote/billing_interfaces.py:IBillingService.charge() ← 服务端真扣费
```

**关键澄清**（subagent 第 8 轮调研事实）：

| 维度 | 事实 |
|---|---|
| 计费权威源 | **服务端**：krow.cn 服务端按 api_key_id 在每次 Bearer Authorization 校验时记账（HTTP 层）；本地 `modules/ai/krow/usage.py` 仅做客户端展示缓存 |
| 本地 UsageTracker 维度 | `service_type/model/input_tokens/output_tokens/cost_cp` —— **不含** user_id 或 api_key_id（响应里有，但不持久化到本地维度键） |
| 远程 UsageTracker 维度 | `code_id`（连接码）—— 不是 user 也不是 api_key；用于"我的 krow 服务被哪些客户端连过" |
| Billing 维度 | `account_id`（user 或 org id） |
| api_key_id 维度 | **目前本地无该字段**；Step 1 PR S1.17 评估是否要加（取决于云端契约：若服务端按 api_key_id 计费且返回 api_key_id 在响应中，本地可持久化；若服务端只按 account_id 计费，本地不需要） |

### §3.2 SDK 强制契约（**API key 模式**）

外部 plugin 启动时必须提供 krow cloud API key（在 https://krow.cn 控制台 "API 密钥" 页面创建，前缀 `sk-user-`）：

```python
import os
from krow_agent_sdk import AgentBuilder

# 方式 A：显式传入
agent = (
    AgentBuilder()
    .with_krow_api_key("sk-user-xxxxxxxxxxxxxxxx")  # ← 强制；不传 fail-loud（MissingKrowAPIKeyError）
    .with_project_root("/data/cad_project")
    .build()
)

# 方式 B：从环境变量读取（推荐 for 生产部署 / CI / Docker）
agent = (
    AgentBuilder.from_env()  # 等价于 .with_krow_api_key(os.environ["KROW_API_KEY"])
    .with_project_root("/data/cad_project")
    .build()
)
```

不允许的反模式（design doc 必须明文写）：

| 反模式 | 替代方案 |
|---|---|
| `os.environ["OPENAI_API_KEY"] = "sk-..."` 然后期望 plugin 用 OpenAI 官方 API | ❌ 不允许；强绑 krow cloud；用 `KROW_API_KEY="sk-user-..."` |
| `import httpx; httpx.post("https://api.openai.com/...")` | ❌ 工具内禁止；走 `provider.generate()`（内部走 https://api.krow.cn/v1） |
| 自己造 `LLMProvider` 实现传给 Builder | ❌ Step 1 不开放；如果未来开放，必须验证走 KrowAuthAdapter + 计费 |
| 在 plugin 内 `from modules.ai.providers import AIProviderManager; m = AIProviderManager(...)` 自己造 manager | ❌ 走 SDK 注入的 LLMProviderManager 单例 |
| **API key 硬编码进 plugin 代码** / **写进公共 git 仓** | ❌ 截图 krow.cn 已警告"请勿在客户端代码或公共仓库中泄露 API 密钥"；走环境变量 / SecretsManager / `~/.krow/credentials` 加密存储 |
| 在 plugin 内 `from modules.auth import krow_auth; krow_auth.set_api_key("sk-...")` 绕过 SDK | ❌ Step 1 PR S1.17 后该方法是 SDK 内部使用的 SSOT；plugin 走 `AgentBuilder.with_krow_api_key()` |
| **以前的虚构概念** `KrowAuthSession.login_from_env()` / `with_krow_session(session)` | ❌ 仓内不存在该符号；第 8 轮辩论修订删除 |
| 试图用 `KROW_EMAIL` / `KROW_PASSWORD` 环境变量登录 | ❌ 这两个 env var 在 auth 模块**未实现**；plugin SDK 走 `KROW_API_KEY`；桌面 UI 路径走 `KROW_HEADLESS_AUTH_*` 族 access_token / refresh_token 注入（不在 plugin SDK 范围） |

### §3.3 Plugin 的 source_module 串联（**v0.8 顶级 review A7 修订：解 enum frozen 撞墙**）

`AGENTS.md` (internal) §infra-ssot-index.mdc §3 LLM 调用模板：必须用 `llm_source_context()` ContextVar 注入 source_module，让 audit log / usage tracker 能定位是哪个 plugin 调的 LLM。

#### §3.3.1 v0.7 设计错误 + v0.8 修订

**v0.7 设计错误**：v0.7 §3.3 写"运行时按 plugin_id 注册新 enum entry"——但 Python `enum.Enum` 是 frozen，**运行时不能动态加 entry**（`LLMSourceModule.PLUGIN_X = "..."` → AttributeError）。Step 1 PR S1.3 当前实现策略一定撞墙。

**v0.8 修订实现策略**（§0.3 R27 + Step 1 PR S1.3 修订）：把 `LLMSourceModule` 从纯 enum 改为 `Union[BuiltinLLMSourceModule, str]`：

```python
# modules/ai/providers.py（v0.8 修订）
from typing import Union
from enum import Enum

class BuiltinLLMSourceModule(str, Enum):
    """krow 内置 source_module（不含 plugin）。frozen 是合理的——内置不会动态加。"""
    PLANNER = "planner"
    EXECUTOR = "executor"
    REACT_THINKER = "react_thinker"
    EVALUATOR = "evaluator"
    SUMMARY_REPORT = "summary_report"
    AI_MANAGER = "ai_manager"
    CHAT = "chat"  # （Step 1 PR S1.3 同时修复 v0.7 §0.3 重复赋值 bug）

# Type alias：Plugin 用 str 字符串命名空间（不是 enum entry）
LLMSourceModule = Union[BuiltinLLMSourceModule, str]

# 约定：plugin 的 source_module 字符串格式：f"plugin:{plugin_id}"
def make_plugin_source_module(plugin_id: str) -> str:
    """生成 plugin 的 source_module 字符串。Step 1 PR S1.3 落地。"""
    return f"plugin:{plugin_id}"
```

#### §3.3.2 Plugin 调 LLM 模板（v0.8 修订）

```python
from krow_agent_sdk.llm import (
    ChatMessage,
    llm_source_context,
    make_plugin_source_module,
)

# SDK 在 plugin 加载期为每个 plugin 计算 source_module 字符串
# 实际值如：f"plugin:industrial_design" / f"plugin:research_agent"

source = make_plugin_source_module("industrial_design")
with llm_source_context(source):
    response = self.llm_provider.generate([
        ChatMessage(role="user", content=prompt),
    ])
```

audit log 自动记录 `plugin_id -> source_module -> token_usage -> compute_points`，billing_service 据此精确计费到 plugin。

#### §3.3.3 反模式

| 反模式 | 替代 |
|---|---|
| `LLMSourceModule.PLUGIN_INDUSTRIAL_DESIGN`（写 enum 常量） | 写 `make_plugin_source_module("industrial_design")` 返回 str |
| 试图 `LLMSourceModule.PLUGIN_X = "..."` 动态加 enum entry | enum frozen，**会 AttributeError**；走 §3.3.1 str alias 路径 |
| plugin 用 `BuiltinLLMSourceModule.PLANNER` 冒充 krow 内置 | SDK 启动期校验：plugin 必须用 `f"plugin:..."` 前缀；冒充内置 fail-loud |
| 多 plugin 共享同一 source_module 字符串 | 每个 plugin `plugin_id` 全局唯一（详 §5.1 双段命名 A8）→ source_module 自动唯一 |

### §3.4 计费 / 配额 / 用量

> **关键事实**（subagent 第 8 轮调研）：krow cloud 计费**主要在服务端做**（按 api_key 在 HTTP 层计账）；本地 `UsageTracker` 仅做客户端展示缓存。SDK 不需要主动 POST 上报，HTTP Authorization 里带 api_key 服务端就能记账。

| 维度 | 落地（铁证 SSOT） |
|---|---|
| **服务端计费**（**权威**）| krow.cn 服务端在每次 `Bearer sk-user-xxx` 校验时按 api_key_id 记账；客户端无需主动上报 |
| 本地用量缓存 | `modules/ai/krow/usage.py:UsageTracker.record(service_type/model/tokens/cost_cp)` —— 客户端展示用，**不含** user/api_key 维度 |
| 服务端用量同步 | `modules/ai/krow/usage.py:sync_with_server` —— `GET https://api.krow.cn/wallet/usage`（带 Bearer header）拉服务端汇总到本地 |
| 配额检查（连接码维度） | `modules/remote/usage_tracker.py:check_task_quota(code_id, estimated_compute)` —— **是连接码维度**，与 plugin SDK 嵌入式形态不冲突（plugin 直接调 LLM 不走连接码） |
| 余额扣减 | `modules/remote/billing_interfaces.py:IBillingService.charge(account_id, ...)` —— 服务端 RPC（plugin SDK 不直接调） |
| Plugin 维度统计 | 通过 `source_module = LLMSourceModule.PLUGIN_<id>` 在本地 audit log + 远端 trace 内分组（同一 api_key 多 plugin 共享 master key 时区分） |
| Per-plugin api key（U18）| 当前**不实现**；master api_key + source_module 已足够区分 plugin（第 8 轮决策）；未来若有强需求再开 |

### §3.5 错误处理（fail-loud 优先 · **v0.8 顶级 review D3 修订：完整 message 文本**）

每个 error class 的 message 严格按 `AGENTS.md` (internal) §五黄金模板（一句话 + 原因 + 位置 + 1-3 个修法 + 相关链接）。

#### §3.5.1 Error class 完整 message 文本

```python
# krow_agent_sdk/errors.py（Step 1 PR S1.17 落地）

class MissingKrowAPIKeyError(KrowSDKError):
    """build() 时未调 with_krow_api_key() 且 KROW_API_KEY env var 未设。"""
    DEFAULT_MESSAGE = """❌ AgentBuilder.build() 缺少 krow cloud API key。
原因：strong-bound LLM 链路（详 §3）必须有有效 API key 才能调 https://api.krow.cn/v1。
位置：AgentBuilder（任一 with_* 链尾的 .build() 调用点）。
你可以：
  1) 在 https://krow.cn API 密钥页面创建 key（前缀 sk-user-），然后 .with_krow_api_key('sk-user-xxxxx').build()
  2) 设环境变量 KROW_API_KEY=sk-user-xxxxx，然后用 AgentBuilder.from_env().build()
  3) 见 docs/sdk/plugin-architecture-design.md §3.2"""

class InvalidKrowAPIKeyError(KrowSDKError):
    """with_krow_api_key(key) 时格式校验失败（非 sk- 前缀 / 长度不足 / 含非法字符）。"""
    DEFAULT_MESSAGE = """❌ 传入的 API key 格式不合法：'{masked_key}'
原因：krow cloud API key 必须以 'sk-' 开头（OpenAI 兼容格式），通常是 'sk-user-' 前缀（个人 key）。
位置：AgentBuilder.with_krow_api_key(api_key=...)
你可以：
  1) 检查 key 是否完整复制（尾部空格 / 引号已剥）
  2) 到 https://krow.cn 重新创建一个 key
  3) 用 AgentBuilder.from_env() 从环境变量读避免手敲漏字符"""

class KrowAPIKeyInvalidError(KrowSDKError):
    """首次 provider.generate() 调用 api.krow.cn 返回 HTTP 401。"""
    DEFAULT_MESSAGE = """❌ krow cloud 拒绝当前 API key（HTTP 401 from https://api.krow.cn）。
原因：API key 已撤销 / 已过期 / 不属于当前账户。
位置：第一次 LLM 调用（KrowLLMProvider.chat 内 httpx.post 401 响应）。
你可以：
  1) 到 https://krow.cn API 密钥页面确认 key 状态
  2) 创建新 key 替换
  3) 若 build() 时已知风险可加 .build(validate_connection=True)（见 §7.1）让 SDK 在 build 阶段而非 first run 时报错"""

class KrowQuotaExceededError(KrowSDKError):
    """provider.generate() 调用返回 HTTP 402 / 服务端 quota_exceeded 响应。"""
    DEFAULT_MESSAGE = """❌ API key 余额不足或超出配额（HTTP 402 from https://api.krow.cn）。
原因：当前 sk-user-xxx 余额耗尽 / 触发服务端限速 / 月度配额耗尽。
位置：LLM 调用过程中（具体哪一步见 stack trace 中 source_module 字段）。
你可以：
  1) 到 https://krow.cn 充值或开通更高套餐
  2) 用 BudgetSpec 降低 max_total_llm_calls（见 §6.1）
  3) 主测试链改走 LLMReplayStore 零成本回放（见 §11.4）"""

class LLMProviderError(KrowSDKError):
    """LLM 调用失败（网络 / 5xx / 模型错误 / fallback 链耗尽）。"""
    DEFAULT_MESSAGE = """❌ LLM provider 调用失败（{reason}）。
原因：网络瞬断 / 服务端 5xx / 模型路由错误。
位置：KrowLLMProvider 内部 retry 链耗尽（默认 3 次）。
你可以：
  1) 检查 https://krow.cn 服务状态页
  2) 重试任务（agent.run 是幂等的）
  3) 若长期失败提交 bug report：krow_agent_sdk.diagnostics.dump_state(agent) 输出含 trace（见 §6.7）"""

class MissingProjectRootError(KrowSDKError):
    """build() 时未调 with_project_root() 且 KROW_PROJECT_ROOT env var 未设（详 §7.1）。"""
    DEFAULT_MESSAGE = """❌ AgentBuilder.build() 缺少项目根目录（force_explicit 策略）。
原因：项目根是 native 工具（document_reader / pptx_editor / native_fileops 等）的 SSOT，不能默认成 cwd（多租户 / 多 agent 实例时易污染）。
位置：AgentBuilder.build() 调用点。
你可以：
  1) 显式 .with_project_root('/data/myproject')
  2) 设环境变量 KROW_PROJECT_ROOT 然后用 AgentBuilder.from_env()
  3) 见 §7"""

class PluginSignatureMismatchError(KrowSDKError):
    """v0.8 新增 R26：Step 1 启动期 plugin signature validator 检测到 plugin 实现的方法签名与 Protocol 不匹配。"""
    DEFAULT_MESSAGE = """❌ Plugin {plugin_id} 实现的 {protocol_name}.{method} 签名不匹配契约。
原因：runtime_checkable Protocol 只查方法名存在性，不查签名/类型/返回值；signature validator 启动期对比发现 plugin 方法签名与 Protocol 定义不一致。
位置：plugin entry_points 加载期（_protocol_validator.validate_protocol_implementation）。
Protocol 定义签名：{expected_sig}
Plugin 实际签名：{actual_sig}
你可以：
  1) 修正 plugin 方法签名（推荐 mypy --strict 在 plugin CI 跑契约测试）
  2) 临时设 KROW_SDK_SIGNATURE_VALIDATION=0 跳过校验（不推荐，仅 dev/debug）
  3) 见 §0.3 R26 + §5 Protocol 契约测试模板"""
```

#### §3.5.2 触发场景速查表

| 场景 | Error class | 触发时机 |
|---|---|---|
| build() 缺 api_key | `MissingKrowAPIKeyError` | `AgentBuilder.build()` |
| api_key 格式错 | `InvalidKrowAPIKeyError` | `AgentBuilder.with_krow_api_key()` 调用时 |
| api_key 401 | `KrowAPIKeyInvalidError` | 首次 LLM 调用 / `build(validate_connection=True)` |
| api_key 402 | `KrowQuotaExceededError` | LLM 调用过程中任意时机 |
| 网络 / 5xx | `LLMProviderError` | retry 链耗尽 |
| 缺 project_root | `MissingProjectRootError` | `AgentBuilder.build()` |
| Plugin 签名错 | `PluginSignatureMismatchError`（v0.8 新增）| plugin entry_points 加载期 |

### §3.6 多租户部署模式（**v0.8 顶级 review D7 新增**）

> 真实场景：plugin 团队 A 给客户 X 部署 → X 的 API key（X 付费）；同 plugin 给客户 Y 部署 → Y 的 API key（Y 付费）。这是 SaaS / B2B 常态需求。

#### §3.6.1 三种多租户模式对比

| 模式 | 描述 | 推荐度 | 落地约束 |
|---|---|---|---|
| **A. per-tenant 进程隔离**（**推荐**）| 每客户独立 SDK 进程（K8s 一个 pod / Docker 一个 container 一客户）；每进程一个 `AgentBuilder` 实例 + 一个 api_key | ✅ **首选** | K8s/Docker 多 pod 部署；每 pod 独立 `KROW_API_KEY` env var；EventBus / project_root 进程内单例自然隔离 |
| **B. 同进程多 builder** | 一个 SDK 进程内为每客户创建独立 `AgentBuilder().with_krow_api_key(key_X).build()` | ⚠️ Step 2 起部分支持 | §2.5 单进程单 LLMProviderManager 单例约束需放松；`AgentBuilder.build()` 返回独立 `Agent` 实例 + 各持自己的 `KrowAuthAdapter`（U12）；project_root 必须 per-builder（detail 详 §7.3） |
| **C. 同进程单 builder 动态切 api_key** | 一个 builder 在 `agent.run(...)` 中按 tenant context 动态切 api_key | ❌ **不支持** | KrowAuthAdapter 启动期固化；动态切会撞 LLMProviderManager 单例；建议走 A |

#### §3.6.2 推荐架构（per-tenant 进程隔离 + Pod 级别 api_key 注入）

```
┌─────────────────────────────────────────┐
│ K8s Cluster                             │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│ │ Pod[X]   │ │ Pod[Y]   │ │ Pod[Z]   │ │
│ │ KROW_API │ │ KROW_API │ │ KROW_API │ │
│ │ _KEY=X   │ │ _KEY=Y   │ │ _KEY=Z   │ │
│ │ AgentB.  │ │ AgentB.  │ │ AgentB.  │ │
│ │ from_env │ │ from_env │ │ from_env │ │
│ │ .build() │ │ .build() │ │ .build() │ │
│ └──────────┘ └──────────┘ └──────────┘ │
└─────────────────────────────────────────┘
   每客户独立进程 → 计费 / project_root / EventBus 自然隔离
```

K8s deployment 示例：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: industrial-design-agent-tenant-x
spec:
  template:
    spec:
      containers:
      - name: agent
        image: industrial-design-agent:0.1.0
        env:
        - name: KROW_API_KEY
          valueFrom:
            secretKeyRef:
              name: tenant-x-credentials
              key: krow-api-key
        - name: KROW_PROJECT_ROOT
          value: /data/tenant-x
```

#### §3.6.3 Step 2 同进程多 builder 支持（U12）

若实战发现"per-tenant 进程隔离 部署成本过高"（如 100+ 小客户），Step 2 可考虑放松单例约束：

| 单例 | 当前 | Step 2 调整方案 |
|---|---|---|
| `LLMProviderManager` | 进程单例 | per-Agent 实例（每 build() 创建独立 manager）|
| `EventBus` | 进程单例 | 每 Agent 持有 sub-EventBus，全局 EventBus 做总线 |
| `StateManager._global_instance` | 进程单例 | per-Agent 实例（StateManager 已支持） |
| project_root | 进程单例（`set_project_root`）| per-Agent 实例（builder.with_project_root 已支持，需把 `get_project_root()` 改为 ContextVar） |

> Step 2 这套改造**不在当前 Step 1 承诺范围**；U12 / U18 跟踪。

#### §3.6.4 反模式

| 反模式 | 替代 |
|---|---|
| 客户端代码硬编码每客户 api_key | env var / SecretsManager / K8s secret |
| 一个 SDK 进程内频繁切 api_key 给不同客户 | 走 per-tenant 进程隔离（模式 A）|
| 多客户共享 master api_key 用 source_module 区分计费 | 起步可这样（§3.4 / U18），但**真实多租户 SaaS** 必须模式 A 隔离付费账户 |
| 模式 A 但所有客户共享同一 project_root | 必须 per-tenant project_root（避免数据交叉污染）|



## §4 原生能力分层

### §4.1 14 个 SDK 自带 native ACT

> 经第 5 轮辩论核实（铁证 + 用户决策）。19 个内置 ACT 中：14 个 SDK 自带，3 个砍，2 个不暴露。

| # | ACT name | 主要工具数 | category | 备注 |
|---|---|---|---|---|
| 1 | `native_fileops` | 29 | — | 通用文件 IO / 检索 / batch |
| 2 | `document_reader` | 2 | — | 多格式文档读 + 语义分析 |
| 3 | `ai_search` | 1 | — | AI 联网检索（学术 / 新闻 / 图片 / 视频） |
| 4 | `terminal_ops` | 1 | — | 终端命令执行（三级安全） |
| 5 | `word_editor` | 7 | — | Word 创建/编辑/修订标记 |
| 6 | `excel_editor` | 22 | — | Excel 表格编辑 / 公式 / 数据 |
| 7 | `pptx_editor` | 26 | — | PISMA-SVG 单管线（propose+render+assemble） |
| 8 | `pptx_studio` | 12 | editor | 继任 ACT（feature flag `g5_runtime_flag` 控制启用）；SDK 暴露但默认 disabled |
| 9 | `wiki_compiler` | 1 | knowledge | 百科全生命周期（编译/查询/审查/归档） |
| 10 | `graph_insight` | 2 | knowledge | 图谱洞察回写百科 |
| 11 | `reasoning_pipeline` | 3 | reasoning | 通用多轮推理管线 |
| 12 | `knowledge_analyzer` | 8 | — | 知识库分析（**未废弃**，铁证：subagent 第 6 轮调研确认 yaml 无 `deprecated`，act_manager 在 `has_knowledge_base()` 真时显式 `register_act`，`reasoning_pipeline` yaml `dependencies:` 仍依赖它）；Lite / 无 ES+Neo4j 运行时是"条件性不可用"，运行时 `has_knowledge_base()` fail-loud 守门 |
| 13 | `visual_grounding` | 1（`visual_inspect`） | — | 视觉检查 + 视觉理解（mode=`verify` / `analyze`）；调 `get_krow_llm_provider().chat_vision`（VLM）→ 与 §3 强绑 krow cloud 天然一致；可注入 `pptx_contrast_guard` 等 System 1 证据 |
| 14 | `krow_cloud` | 10 | — | 云服务（图像生成/OCR/视觉理解）；强绑 krow auth/billing |

### §4.2 砍掉的 ACT（3 个）

| ACT | 砍除原因 |
|---|---|
| `image_editor` | enabled 但缺 extended.md（实现不完整），与 `image_generator` / `krow_cloud` 能力重叠 |
| `image_generator` | enabled 但 yaml 注释自承认与 `krow_cloud` 重叠；统一走 `krow_cloud` 作 SSOT |
| `solution_generate` | `deprecated: true`（act_loader 视为不可用），已废弃 DSL |

> **归档策略**（`AGENTS.md` (internal) §十）：不直接 `git rm`，先 `git mv → modules/agent/act/acts/_archive/<name>_<YYYYMMDD>/`，6 个月兜底期后删除。具体归档 PR 不在本设计文档承诺范围（独立治理 PR）。

### §4.3 不暴露的 ACT（2 个）

| ACT | 不暴露原因 |
|---|---|
| `editor` | IDE 缓冲区耦合，headless / SDK 嵌入式形态不适用；外部 plugin 要 IDE 集成自己实现 |
| `krow_internal` | krow 内部 LLM / 语义查询专属（与外部 plugin 无关） |

### §4.4 native ACT 扩展规则（**只能 ADD，不能 OVERRIDE**）

外部 plugin 通过 `ACTPlugin` 加新 ACT，但**不能替换** native ACT 的实现。

| 操作 | 允许？ | 说明 |
|---|---|---|
| 加新 ACT（如 `cad_designer`） | ✅ | 走 `entry_points("krow.acts")` |
| ACT name 与 native 同名（如外部叫 `pptx_editor`） | ❌ | SDK 启动时 fail-loud（namespace 冲突） |
| 修改 native ACT 的 yaml / extended.md | ❌ | 物理上 plugin 没有写权限 |
| 给 native ACT 加新工具（如给 `pptx_editor` 加 `pptx_my_custom_layout`） | ⚠️ 受限 | 走 `ToolPlugin` 加全局工具，但**不能挂到** native ACT 的 `tools:` 列表（要挂只能挂自己的 ACT） |
| 在 native ACT 内插 hint | ⚠️ 受限 | 走 `HintPlugin` 加条件 hint，hint 在 reasoning preamble / tool priority hint 注入；**不能直接改** native ACT 的 hint |
| **DomainPack supplementary extended.md** 追加到 native ACT extended.md | ✅ ADD | 走 P9 `DomainPackPlugin.get_extended_md_supplement(target_act)`；ACTLoader 加载时**内存合并**（带 plugin_id 标记），不修改 yaml/extended.md 源文件；同 target 多 plugin append 按 priority 排序；**v0.8 review A9 加总量上限**：单 supplement ≤ 4000 字符（保留）；同 target_act 全部合并 ≤ 16000 字符（**新增**）；同 SDK 进程全部合并 ≤ 64000 字符（**新增**），超出 fail-loud 防 LLM prompt token 暴涨 |

### §4.5 native 工具扩展规则

| 操作 | 允许？ |
|---|---|
| 加新工具（namespace `<plugin_id>.<tool_name>`） | ✅ |
| 工具名与 native 工具同名 | ❌ namespace fail-loud |
| 替换 native 工具实现 | ❌ |
| 给 native 工具加 wrapper（plugin 自己写一个 wrapper 调 native） | ✅（这是 plugin 自己的工具，不是替换） |

### §4.6 Native ACT 运行时守门

- `pptx_studio` enabled: false：SDK 暴露但默认 disabled，外部 plugin 通过 feature flag `g5_runtime_flag` 启用，与 main repo 一致
- `knowledge_analyzer`：`ACTManager.register_act` 时检查 `has_knowledge_base()`（铁证：`config/edition.py:has_knowledge_base()` 检测 JRE + ES + Neo4j 运行时目录均存在且非空）—— Lite 上日志 `knowledge_analyzer ACT skipped (Lite edition)` 不注册（fail-loud 行为：能力不可用时 LLM 看不到这 8 个工具，不会误调）
- `visual_grounding` / `visual_inspect`：运行时由 `modules/agent/visual/visual_grounding_tools.py:_get_vg_enabled` 读取 `load_module_config().get("visual_grounding", {}).get("enabled", True)` 决定启用；VLM token 成本由 BudgetController 计入
- `terminal_ops`：受 `SecurityPlugin` 的 `shell_commands_allowed` 白名单约束（详 §5.8）



## §5 Plugin Protocol Spec（9 个）+ 3 个"不开 Protocol"策略声明

> 本节定义 SDK 暴露的 9 个核心 Plugin Protocol（P1-P8 通用底层协议 + P9 DomainPackPlugin 语法糖），加 3 个第 7 轮辩论决策"不开 Protocol、走函数式 facade + Builder 配置"的策略声明（§5.10 数据层 / §5.11 诊断工具 / §5.12 预算覆盖度）。
> 每个 Protocol Spec 用统一格式：用途 + System 1/2 标签 + Protocol 接口 + entry_points 注册 + 现有 SSOT 复用 + 反模式。
> Step 1 一次性骨架 P1-P8 + P9 + Step 2 同批实现真实加载（用户决策第 3 轮辩论 + 第 6 轮辩论加 P9 + 第 7 轮辩论确认不再加 P10）。

### §5.0 Protocol 优先级分层 + 增减治理协议（**v0.8 顶级 review A2+A3 新增**）

> Hyrum's Law：任何可观察行为都会被某 user 依赖。9 Protocol 一次性发布锁死后 5 年内难调整。本子节明文定义优先级分层 + 增减治理协议，给 SDK 演化留空间，避免 npm/pip ecosystem 碎片化教训。

#### §5.0.1 Protocol 优先级分层

| 层级 | Protocol | Step 1 必交付内容 | 维护承诺 | namespace |
|---|---|---|---|---|
| **mvp_critical** | P1 ACT / P2 Tool / P4 Gate | 真实加载 + 契约测试 + e2e + 1 个 dogfood plugin | **5 年 SemVer 强约束**（major bump 才能 break）| `krow_agent_sdk.protocols` |
| **stable** | P3 Hint / P5 EventListener / P6 Observability | 骨架 + 契约测试 + 1 个内部 dogfood | **3 年 SemVer 强约束** | `krow_agent_sdk.protocols` |
| **experimental** | P7 MCP / P8 Security / P9 DomainPack | 骨架 + feature flag default off + 1 sprint 观察期 | **2 年 SemVer 弱约束**（minor 内可 breaking + deprecation 1 个 minor 周期）| `krow_agent_sdk.experimental.protocols`（**v0.8 起单独 namespace**） |

**实施约束**：

- experimental 用 `from krow_agent_sdk.experimental import P9DomainPackPlugin`，**不**在主 `krow_agent_sdk.protocols` 暴露——明确告诉用户"未来可能 break"
- mvp_critical / stable 转 experimental（降级）= major bump
- experimental → stable（升级）= minor bump + 同期升级 namespace 路径
- AgentBuilder.from_env() 默认只加载 mvp_critical + stable，experimental 必须显式 `with_<x>_from_entry_points(group="krow.experimental.<x>")` 启用

#### §5.0.2 加新 Protocol 的治理协议（铁律 all-of）

未来新增 P10 / P11 / Pn 必须**同时**满足：

1. **真实需求证据**：≥ 2 个独立外部 plugin 真实需求（用 §5.6 telemetry opt-in 数据 OR 主动调研记录证）
2. **替代覆盖度评估**：用 Builder helper / function 不能覆盖 ≥ 80% 用例（写 trade-off 表）
3. **重叠度约束**：与现有 9 个 Protocol 重叠 < 60%（按方法语义对齐表评估）
4. **灰度 path**：先在 `experimental.protocols` namespace 灰度 ≥ 1 季度（feature flag default off）
5. **优先级分层登记**：同期更新 §5.0.1 优先级分层表 + 维护承诺等级
6. **辩论铁证**：按 `AGENTS.md` (internal) §4.2.2 走完整 5 顾问辩论（事实 → 铁证 → 辩论 → 修 → 复测）

#### §5.0.3 砍 Protocol 的治理协议（铁律 all-of）

砍 Protocol（如 P9 DomainPack 实战发现没人用）必须**同时**满足：

1. **6 个月 deprecation 期**：发布 deprecation 装饰器 + emit `DeprecationWarning` + audit log 记录调用方 plugin_id
2. **等价迁移路径**：design doc 写明老 plugin 等价迁移到哪个 Protocol / Builder helper
3. **major bump**：砍 Protocol = major bump（即便是 experimental 层的也要走 major）
4. **6 个月内不能再加同名 Protocol**（防"砍了又加"反复折腾外部团队）
5. **元规则同期更新**：`AGENTS.md` SSOT 表 + `.cursor/rules/plugin-authoring.mdc` 同期 PR

#### §5.0.4 既定 9 Protocol 的优先级分层（v0.8 决策）

| Protocol | 层级 | 理由 |
|---|---|---|
| P1 ACTPlugin | **mvp_critical** | 每个 plugin 都需要加新 ACT；不可替代 |
| P2 ToolPlugin | **mvp_critical** | 每个 plugin 都需要加新工具；不可替代 |
| P3 HintPlugin | stable | 50%+ plugin 需要，可用 P9 DomainPack helper 部分替代 |
| P4 GatePlugin | **mvp_critical** | 领域强约束 fail-loud 是核心场景；不可替代 |
| P5 EventListenerPlugin | stable | 50%+ plugin 需要，但可用 EventBus.subscribe 直接用替代部分 |
| P6 ObservabilityPlugin | stable | 50%+ plugin 需要 Datadog/Splunk；不可替代 |
| P7 MCPServerPlugin | experimental | < 30% plugin 用，且 MCP 协议本身在演进期 |
| P8 SecurityPlugin | experimental | MVP 降级版（强沙箱推 Step 3），仍在迭代 |
| P9 DomainPackPlugin | experimental | "语法糖"聚合，可被 P1+P2+P3+P4 等价覆盖；ecosystem 反馈后再决定升级 |

**Step 1 实施影响**（§9.1 同步修订 PR S1.1）：

- mvp_critical（P1/P2/P4）**必须**在 Step 1 真实加载 + e2e + 1 个 dogfood
- stable（P3/P5/P6）**必须**在 Step 1 骨架 + 契约测试，**真实加载**可推 Step 2
- experimental（P7/P8/P9）**仅**在 Step 1 骨架（feature flag default off 持续观察）；真实加载推 Step 2 + ramp 期

### §5.0.5 plugin_id 命名规范（**v0.8 顶级 review A8/D4 新增**）

> **痛点**：v0.7 P1/P2/P3/P4/P5 等 Protocol 反复用 `plugin_id`，但 design doc 散落 3 种格式（`industrial_design` / `industrial.cad_designer` / `<org>_<plugin>`）；不强制双段全局唯一会导致 plugin ecosystem 撞名（pip ecosystem 历史教训：`requests` vs `requests2` vs `python-requests`）。

#### plugin_id 双段命名规范（**强制**）

```
plugin_id = "<org>.<plugin_name>"
```

| 部分 | 规则 |
|---|---|
| `<org>` | 组织名 / 团队名 / GitHub username；**全小写**，仅 `[a-z0-9_-]`；3-20 字符 |
| `.` | 必须用点分隔 |
| `<plugin_name>` | plugin 业务名；**全小写 snake_case**，仅 `[a-z0-9_]`；3-30 字符 |

**例子**：

| ✅ 推荐 | ❌ 错误 |
|---|---|
| `acme.industrial_design` | `industrial_design`（缺 org 段，撞名风险） |
| `tencent_lab.lab_protocol` | `Tencent.LabProtocol`（大小写 / camelCase 错） |
| `solo-dev.research_helper` | `industrial.cad_designer`（org 段不存在的组织名风险） |
| `krow.knowledge_compile` | `krow_knowledge_compile`（缺点分段） |

#### plugin_id 强制约束（Step 1 PR S1.20 落地）

```python
# modules/agent/sdk/_plugin_id_validator.py（Step 1 PR S1.20 落地）
import re

PLUGIN_ID_PATTERN = re.compile(r"^[a-z0-9_-]{3,20}\.[a-z0-9_]{3,30}$")

def validate_plugin_id(plugin_id: str) -> None:
    """启动期 plugin_id 校验，违反 fail-loud。"""
    if not PLUGIN_ID_PATTERN.match(plugin_id):
        raise InvalidPluginIDError(
            f"❌ plugin_id 格式不合法：'{plugin_id}'\n"
            f"原因：必须是 '<org>.<plugin_name>' 双段命名\n"
            f"  <org>: 全小写 [a-z0-9_-] 3-20 字符\n"
            f"  <plugin_name>: 全小写 [a-z0-9_] 3-30 字符\n"
            f"位置：plugin entry_points 加载期\n"
            f"你可以：\n"
            f"  1) 在你的 pyproject.toml entry_points 改成 'org.plugin_name = your_module:plugin'\n"
            f"  2) 见 docs/sdk/plugin-architecture-design.md §5.0.5"
        )
```

#### plugin_id 全局唯一性

- 同 SDK 进程内 plugin_id 撞名（`acme.cad` 加载两次） → fail-loud `DuplicatePluginIDError`
- Step 2 PyPI 发布后：krow.cn 维护一个 plugin_id registry（与 PyPI 类似 / 保留 `krow.*` namespace）；外部团队建议先注册 `<org>` 段
- **不强制** plugin_id 与 PyPI 包名一致（pyproject.toml package 名是 distribution 名，与 plugin_id 解耦）；但**推荐**一致以减少认知负担

#### plugin_id 关联派生

| 派生路径 | 公式 | 例子 |
|---|---|---|
| LLM source_module（A7） | `f"plugin:{plugin_id}"` | `plugin:acme.industrial_design` |
| audit log subject | `plugin_id` | `acme.industrial_design` |
| EventBus error topic（D6） | `f"plugin.error.{plugin_id}"` | `plugin.error.acme.industrial_design` |
| ACT name（P1）| 必须以 `<plugin_name>` 段为前缀（不含 `<org>`）| ACT name `industrial_design.cad_designer` |
| Tool name（P2）| 必须以 `<plugin_name>` 段为前缀 | Tool name `industrial_design.cad_extract_geometry` |

### §5.1 P1 ACTPlugin — 外部加新 ACT

**用途**：外部 plugin 加新 ACT（macro 层扩展），如工业设计的 `cad_designer` ACT、科研的 `lab_protocol` ACT。

**System 1 / 2 标签**：System 1（ACT 是声明式 yaml + markdown 容器，加载是确定性查表）

**Protocol 接口**：

```python
# krow_agent_sdk/protocols.py
from typing import Protocol, runtime_checkable
from pathlib import Path

@runtime_checkable
class ACTPlugin(Protocol):
    """外部加新 ACT 的协议。
    
    Plugin 实现此协议后通过 entry_points 注册：
    
    [project.entry-points."krow.acts"]
    cad_designer = "industrial_design_pkg:get_act_definition"
    """
    
    plugin_id: str  # 全局唯一 id，作为 namespace 前缀（如 "industrial_design"）
    
    def get_act_root(self) -> Path:
        """返回外部 ACT 根目录（含 __act__.yaml + extended.md + 子目录）。
        
        SDK 内部调用 ACTLoader(acts_dir=plugin.get_act_root()) 加载。
        """
        ...
    
    def get_act_names(self) -> list[str]:
        """返回该 plugin 暴露的全部 ACT 名（不含 plugin_id 前缀）。
        
        SDK 注册时自动加 namespace：实际 ACT name = f"{plugin_id}.{act_name}"
        """
        ...
```

**entry_points 注册**：

```toml
[project.entry-points."krow.acts"]
cad_designer = "industrial_design_pkg:get_act_definition"

# Python 实现：
# def get_act_definition() -> ACTPlugin: ...
```

**现有 SSOT 复用**（`AGENTS.md` (internal) §0.2 造轮子检查）：
- `modules/agent/act/act_loader.py:ACTLoader` — 已支持 `acts_dir` 参数
- `modules/agent/act/act_manager.py:ACTManager.register_act` — 已支持运行时注册
- `ACTLoader.register_extension_act` — 已有 OCP 雏形（但 ext_ 前缀绑死，Step 2 要改）

**Step 1 改造**：
- 加载 SDK 内部 `_LoadedACTPlugin` 包装，复用 ACTLoader 多目录扫描
- ACTManager 注册时自动加 `plugin_id.` namespace 前缀
- namespace 冲突 → fail-loud（与 native ACT 同名直接 raise）

**Step 2 改造**（详 §9.2 PR S2.1）：
- ACTLoader 支持 `importlib.metadata.entry_points("krow.acts")` 自动发现
- 砍掉 `ext_` 前缀强制，改用 `<plugin_id>.<act_name>` 协议（兼容 fallback：旧 `ext_` 前缀继续工作 6 个月 + deprecation warning，详 §12.1 R14）
- feature flag `KROW_ENABLE_PLUGIN_ENTRY_POINTS=1`

**反模式（Plugin 作者必读）**：

| 反模式 | 替代 |
|---|---|
| ACT name 与 native 同名（如 `pptx_editor`） | 改名（如 `industrial_design.cad_pptx_editor`） |
| ACT 内引用 native 工具（`tools: [pptx_render_page_svg]`） | ACT 内只能列自己 plugin 注册的工具；要用 native 工具走 ReACT 自然调用，不挂 yaml |
| extended.md 写"请 LLM 不要用 X 工具" | 走 ToolManager 物理禁用（`AGENTS.md` (internal) §0.1 反模式） |
| 在 ACTPlugin 实现里 `import openai` | 工具内禁止调 LLM（CI 红线） |
| 想给 native ACT 注入领域知识（科研/工业） | 走 P9 DomainPackPlugin（§5.9 语法糖：聚合 hint+tool+gate+supplementary extended.md） |

---

### §5.2 P2 ToolPlugin — 外部加新工具（含 trait 声明）

**用途**：外部加 System 1 工具（如 CAD 计算、化学公式校验、特定数据库查询），并声明 latency_class / trait。

**System 1 / 2 标签**：工具实现可以是 System 1 或 System 2（调 LLM 的工具）。

**Protocol 接口**：

```python
@runtime_checkable
class ToolPlugin(Protocol):
    """外部加工具的协议。"""
    
    plugin_id: str
    
    def get_tools(self) -> list["ToolDefinition"]:
        """返回工具定义列表。
        
        每个工具 name 自动加 namespace 前缀：实际 name = f"{plugin_id}.{tool_name}"
        """
        ...

# SDK 暴露（包装 modules/tools/models.py:ToolDefinition）：
@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict  # JSON Schema
    handler: Callable[[dict, Any], str]
    
    # 来自 ToolTraitRegistry
    latency_class: Literal["hot", "warm", "cold"] = "warm"
    traits: list[str] = field(default_factory=list)  # CONTENT_CREATION / FILE_PATH / WEB_SOURCE / ...
    
    # 可选
    output_schema: dict | None = None
    headless_disabled: bool = False  # 等同主仓 _get_headless_disabled_tool_names 自声明
    user_visible: bool = True
```

**entry_points 注册**：

```toml
[project.entry-points."krow.tools"]
cad_tools = "industrial_design_pkg.tools:register_all"

# Python 实现：
# def register_all() -> ToolPlugin: ...
```

**现有 SSOT 复用**：
- `modules/tools/manager.py:ToolManager.register_tool` — 已有公开 API
- `modules/agent/progressive/tool_traits.py:ToolTraitRegistry` — 已有 trait 注册
- `modules/tools/manager.py:_get_headless_disabled_tool_names` — 已有 OCP 聚合（铁证：当前只有 `pptx_editor_v2.get_headless_disabled_tools()` 一个调用方）

**Step 1 改造**：
- SDK facade 内部把 `ToolDefinition.headless_disabled=True` 自动注册到 `_get_headless_disabled_tool_names` 聚合
- ToolTraitRegistry 接受 plugin 工具的 trait 声明

**Step 2 改造**：
- `entry_points("krow.tools")` 自动发现
- ToolManager 加 namespace 强制（`<plugin_id>.` 前缀，与 native 工具冲突 fail-loud）

**反模式**：

| 反模式 | 替代 |
|---|---|
| Tool 内 `import httpx; httpx.post("https://api.openai.com/...")` | 走 SDK 注入的 LLMProviderManager |
| 工具数 > 5 共享同一动词（`AGENTS.md` (internal) §五） | 合并 + 参数分流 |
| `latency_class` 不设（默认 warm） | 必须显式声明（hot/warm/cold） |
| 工具直接 `from modules.agent.* import *`（深 import） | 走 SDK facade |

---

### §5.3 P3 HintPlugin — 外部加条件 hint

**用途**：外部加"语义/创意类"软提示（如"工业设计 agent 倾向用度量制单位"、"科研 agent 应优先引用 peer-reviewed 论文"）。

**System 1 / 2 标签**：System 2（语义/创意软提示）

**红线**（`AGENTS.md` (internal) §0.1 反模式）：HintPlugin **不能**做"参数校验/错误防御/物理约束"——这些走 ToolPlugin 入口归一化（System 1）或 GatePlugin（System 1）。

**Protocol 接口**：

```python
@runtime_checkable
class HintPlugin(Protocol):
    """外部加条件 hint 的协议。"""
    
    plugin_id: str
    
    def should_inject(self, task_context: dict) -> bool:
        """判断当前任务上下文是否注入此 hint（如检查 act_name / user_intent_keywords）。"""
        ...
    
    def build_hint(self, task_context: dict) -> str:
        """返回要注入到 LLM prompt 的 hint 文本（自然语言）。
        
        hint 会被注入到 reasoning_preamble 或 tool_priority_hint 拼接段。
        """
        ...
    
    @property
    def hint_kind(self) -> Literal["reasoning_preamble", "tool_priority", "act_extended"]:
        """hint 注入位置。"""
        ...
```

**entry_points 注册**：

```toml
[project.entry-points."krow.hints"]
cad_unit_hint = "industrial_design_pkg.hints:UnitMetricHint"
```

**现有 SSOT 复用 / 新建**：
- `modules/agent/react_templates/reasoning_preamble.py:should_inject` + `build_reasoning_preamble` — 现有但是写死的（`AGENTS.md` (internal) §infra-ssot-index.mdc §1.2）
- 新建 `modules/agent/sdk/hint_registry.py`（薄注册中心，按 `hint_kind` 分组）

**Step 1 改造**：
- 抽出 `HintRegistry`（中等改造，§0.3 反插件化障碍提到）
- `reasoning_preamble.py` / `tool_priority_hint.py` 改造为遍历 `HintRegistry` 注入

**反模式**：

| 反模式 | 替代 |
|---|---|
| 用 hint 教 LLM "禁止使用 X 工具" | 走 ToolManager 物理禁用 |
| 用 hint 做参数校验"必须传 metric 单位" | 走 ToolPlugin 入口 `_normalize_input()` |
| hint 文本含"严禁/必须/禁止" 类硬约束 | 改 GatePlugin（System 1 闸门） |

---

### §5.4 P4 GatePlugin — 自定义 ConcludeGuard Gate（含 phase 字段覆盖 macro + micro 两栈）

**用途**：领域强约束 fail-loud（如机械设计的"齿轮模数必须满足强度公式"、化学合成的"反应物总量必须守恒"、科研论文"实体抽取数量不足"等）。

**System 1 / 2 标签**：System 1（fail-loud 物理闸门）

**关键事实**（第 7 轮辩论铁证）：krow agent **门控有 12 类，分散在 12 处**（详见下文"门控归属表"）；P4 GatePlugin 只覆盖其中 G1（ConcludeGuard 9 gates）+ G2（Micro ReACT conclude_guard）两类，由 `phase` 字段区分。其他 10 类门控**全部为内核行为**（不暴露 plugin），plugin 不能改。

**Protocol 接口**：

```python
from typing import Literal

@runtime_checkable
class GatePlugin(Protocol):
    """自定义 ConcludeGuard Gate 的协议（覆盖 macro + micro 两栈）。"""

    name: str  # gate 名（用于审计 log；自动加 plugin_id namespace）
    priority: int  # 链中执行顺序（小先执行；plugin gate 默认 priority 低于 native 9 个核心 gate）

    @property
    def phase(self) -> Literal["conclude", "micro_react_conclude"]:
        """门控生效阶段。

        - "conclude"           → 注入 modules/knowledge/conclude_guard_gates.py:GateChain
                                 任务收尾前对 conclude 结构化输出做 fail-loud 校验
                                 verdict 三态：ALLOW / BLOCK / DEFER

        - "micro_react_conclude" → 注入 modules/agent/react_engine.py:ReACTEngine.register_conclude_guard
                                   单步 micro ReACT 内 LLM action=conclude 的拦截回调
                                   返回字符串理由 → 拒绝；None → 通过
                                   （与 ConcludeGuard 知识链是不同栈，由 phase 字段区分注册去向）
        """
        ...

    def evaluate(
        self,
        parsed: dict[str, Any],
        context: dict[str, Any],
    ) -> "GateDecision":
        """检查当前 conclusion 是否合法。

        - phase="conclude"：返回 GateDecision(verdict=ALLOW/BLOCK/DEFER, reason=...)
        - phase="micro_react_conclude"：返回 GateDecision(verdict=ALLOW/BLOCK)
          （micro 引擎不接受 DEFER —— SDK 内部把 DEFER 映射为 ALLOW）
        """
        ...

# SDK 暴露 modules/knowledge/conclude_guard_gates.py 内 dataclass：
@dataclass(frozen=True)
class GateDecision:
    verdict: GateVerdict  # ALLOW / BLOCK / DEFER
    reason: str = ""
    gate_name: str = ""
```

**entry_points 注册**：

```toml
[project.entry-points."krow.gates"]
mech_constraints = "industrial_design_pkg.gates:MechanicalConstraintsGate"      # phase="conclude"
micro_no_placeholder = "industrial_design_pkg.gates:MicroNoPlaceholderGate"     # phase="micro_react_conclude"
```

**现有 SSOT 复用**：
- `modules/knowledge/conclude_guard_gates.py:GateChain.register(gate)` — 已是 OCP 链式（phase="conclude" 走这里）
- `modules/knowledge/conclude_guard_gates_impl.py:make_default_chains` — 默认链构造（含 9 个 native gate：data_layer / evidence_count / conclude_fields / self_verify / methodology / lead_drive / possibility / lint_debate_phase / inference_sufficiency + schema_shape / compile_mode / wiki_spec 等额外维度）
- `modules/agent/react_engine.py:ReACTEngine.register_conclude_guard(callback)` — 已有（phase="micro_react_conclude" 走这里）
- `make_simple_gate(...)` — 简化构造

**Step 1 改造**：
- SDK facade 暴露 `GateChain.add_plugin_gate(plugin_gate)`（phase="conclude"）和 `ReACTEngine.add_plugin_micro_guard(plugin_gate)`（phase="micro_react_conclude"）
- SDK 内部按 phase 字段路由到正确栈
- 注册顺序：plugin gate 默认 priority 低于 native（避免 plugin 撞坏 native 9 个核心 gate 的语义）

**门控归属表（12 类门控明文映射）**：

| # | 门控类型 | SSOT | 暴露 | 通过哪个 Plugin |
|---|---|---|---|---|
| **G1** | ConcludeGuard 9 gates（gate1-9 + schema_shape/compile_mode/wiki_spec） | `modules/knowledge/conclude_guard_gates_impl.py` | ✅ | **P4 GatePlugin（phase="conclude"）** |
| **G2** | Micro ReACT `register_conclude_guard` | `modules/agent/react_engine.py:ReACTEngine` | ✅ | **P4 GatePlugin（phase="micro_react_conclude"）** |
| G3 | Planner snapshot 工具过滤 | `modules/agent/planner_v3.py:_capture_tool_snapshot` + `_PPTX_PISMA_WHITELIST` | ❌ 内核 | — 外部要限制工具走 P2 ToolPlugin headless 自声明 |
| G4 | Plan 改写（退役工具守门） | `modules/agent/progressive/plan_task_handler.py:_RETIRED_PPTX_CREATION_TOOLS` + `_guard_pptx_retired_to_propose` | ❌ 内核 | — 主仓内部治理 |
| G5 | Executor pre_execute 早停 | `modules/agent/progressive/executor.py:_should_conclude` | ❌ 内核 | — 任务级 safety net 不暴露 |
| G6 | TaskBudget 步前预算闸（walltime + LLM 调用次数） | `executor.py:_execute_step_impl` 内 `check_time_budget` / `check_llm_budget` | ❌ 内核 | — 通过 `BudgetSpec` 配置上下限（详 §5.12 / §6.1） |
| G7 | ToolManager schema 校验 | `modules/tools/manager.py:execute_tool` 内 `validate_tool_args` + `_create_validation_error` | ✅ | **P2 ToolPlugin**（每 ToolDefinition 自带 input_schema） |
| G8 | ToolManager security_manager.enforce | `manager.py:execute_tool` 内 `security_manager.enforce` | ✅ | **P8 SecurityPlugin** |
| G9 | headless_disabled 工具过滤 | `manager.py:_get_headless_disabled_tool_names` + `register_tool` 双闸 | ✅ | **P2 ToolPlugin**（headless 自声明） |
| G10 | ACT 不变量 micro/macro 分离 | `modules/agent/act_hierarchy.py:_assert_no_micro_tool_in_macro_priorities` | ❌ 内核 | — 启动期校验，plugin 不能破 |
| G11 | Circuit breaker（ErrorAccumulator → 拒绝预算扩容） | `executor.py:_recompute_budget_after_replan` 内 `ErrorAccumulator.should_abort()` | ❌ 内核 | — macro 预算 SSOT 一部分 |
| G12 | Remote SandboxValidator（远程 API 网关路径校验，与 G8 不同代码路径） | `modules/remote/security_policy.py:SandboxValidator` + `api_gateway.py:check_file_access` | ✅ | **P8 SecurityPlugin**（与 G8 共享 policy） |
| G13 | prompt_safety sanitize | `modules/agent/progressive/prompt_safety.py` | ❌ U1 推迟 | — 第 4 轮辩论决策推到未来 |

**反模式**：

| 反模式 | 替代 |
|---|---|
| Gate 内调 LLM 做语义判断 | Gate 必须是 System 1 确定性逻辑；要 LLM 走 ToolPlugin 走 reasoning |
| Gate 返回 DEFER 当兜底 | DEFER 是"明确不知道交给后续 gate"，不是"不写就 DEFER" |
| Gate name 与 native gate 同名 | namespace 强制（`<plugin_id>.<gate_name>`） |
| BLOCK 但 reason 为空 | reason 必填，audit log + LLM replan 都要看 |
| micro_react_conclude phase 返回 DEFER | micro 引擎不接受 DEFER；SDK 自动映射为 ALLOW，但 plugin 应明确选 ALLOW/BLOCK |
| Plugin 试图通过 P4 改 G3-G6 / G10-G11 内核门控 | 不允许；这些是 agent 内核不变量；外部 plugin 想限制工具 → 走 P2 ToolPlugin headless 声明；想配置预算 → 走 BudgetSpec |

---

### §5.5 P5 EventListenerPlugin — 监听 EventBus

**用途**：订阅 EventBus 事件（`budget.*` / `agent.*` / `background_task.*` / `progressive.*` / `react.*` / `experience.*` / `wiki.*` / `turbo.*` 等），实现自定义监控 / 副作用。

**System 1 / 2 标签**：System 1（确定性数据流）

**Protocol 接口**：

```python
@runtime_checkable
class EventListenerPlugin(Protocol):
    """订阅 EventBus 的协议。"""
    
    plugin_id: str
    
    def get_subscriptions(self) -> list[tuple[str, Callable[["Event"], None]]]:
        """返回 (topic, handler) 列表。
        
        topic 支持精确匹配（如 "budget.extended"）。
        通配匹配（如 "budget.*"）需要 EventBus 升级支持（不在 Step 1 范围）。
        """
        ...

# SDK 暴露 modules/events/bus.py:Event 数据模型
```

**entry_points 注册**：

```toml
[project.entry-points."krow.event_listeners"]
budget_alerter = "industrial_design_pkg.listeners:BudgetAlerter"
```

**现有 SSOT 复用**：
- `modules/events/bus.py:EventBus.subscribe(event_type, callback) -> token` — 已有完整 API
- `EventBus.unsubscribe(token)` — 已有
- topic 命名规范：`budget.*` / `background_task.*` / `progressive.*` / `react.*` / `agent.*` / `experience.*` / `wiki.*` / `turbo.*` 等（`AGENTS.md` (internal) §infra-ssot-index.mdc §5.3 命名约定）

**Step 1 改造**：
- SDK facade 在 plugin 加载期遍历 `get_subscriptions()` 自动 subscribe
- plugin unload 时自动 unsubscribe（防泄漏）

**Step 2 改造**：
- topic 通配匹配（如 `budget.*` 一次订阅所有 budget 事件）
- handler 隔离：plugin handler 抛异常**不能**拖死 EventBus（用 try/except 包裹 + 发布 `plugin.error.<plugin_id>` 事件）

**SDK 承诺稳定的 EventBus topic 子集**（第 7 轮辩论铁证：仓内 topic 海量含动态字符串，SDK **不承诺**全集；以下子集是稳定契约）：

| 类别 | 稳定 topic（SDK 承诺）|
|---|---|
| **Budget**（5 个 facade 转发事件，由 `BudgetController._FORWARD_MAP` 暴露） | `budget.extended` / `budget.target_reached` / `budget.max_reached` / `budget.grace_started` / `budget.exhausted` |
| **Agent 生命周期** | `agent.progress` / `agent.thinking_stream` / `agent.task_complete` / `agent.binary_rescue.succeeded` |
| **Executor** | `executor.deferred_confirmation_required` / `executor.stop_request` |
| **Background Task** | `background_task.queued` / `background_task.started` / `background_task.completed` / `background_task.failed` |
| **ReACT** | `react.metrics_snapshot` / `react.micro_timeout` / `react.budget_exhausted` / `react.thinking_timeout` |
| **Plugin lifecycle** | `plugin.loaded` / `plugin.unloaded` / `plugin.error.<plugin_id>` |
| **不承诺**（动态 topic 不在稳定契约内）| `reasoning.<strategy_name>` / `pipeline.rollout` / 所有 `f"..."` 拼装出来的动态 topic |

**典型应用场景**：

| 场景 | 订阅 topic |
|---|---|
| 预算监控 + 超阈值告警 | `budget.extended` / `budget.grace_started` / `budget.exhausted` |
| 后台任务进度同步 | `background_task.queued` / `.started` / `.completed` / `.failed` |
| 自定义 audit log | `agent.task_complete` / `react.metrics_snapshot` |
| 经验记忆触发 | `experience.record_complete` / `experience.recall_complete` |

**反模式**：

| 反模式 | 替代 |
|---|---|
| handler 内同步调 LLM（阻塞 EventBus） | handler 应轻量；要调 LLM 走 BackgroundTaskQueue.submit() 异步（铁证：EventBusCore.publish 在无 bridge 时同步分发，订阅者执行串行） |
| handler 内自己起 thread / asyncio loop | 走 BackgroundTaskQueue（统一调度） |
| **监听 `budget.*` 然后试图修改预算数值** | **listener 仅读**；BudgetController 是事件转发 facade（不执行预算逻辑）；要配置 budget 上下限走 `AgentBuilder.with_budget(BudgetSpec)`（详 §5.12 + §6.1）；plugin 不能改 `_handle_adapt_budget_extension` 内核扩容公式 |
| 假定 SDK 承诺所有 topic 都稳定 | 只用 SDK 承诺稳定子集（上表）；动态 topic 监听属"best-effort"，主仓内部 refactor 时可能消失 |
| 跨进程 EventBus | EventBus 是**进程内单例**（`EventBusCore` get_instance）；跨进程 UI 走 `with_http_gateway` 启 KrowService `/ws/events` 或 `/agent/stream/{id}` SSE（详 §6.5） |

---

### §5.6 P6 ObservabilityPlugin — 自定义 trace/metrics/audit sink

**用途**：把 agent 的 tracing / metrics / audit 数据发到外部团队的 Datadog / Sentry / Splunk / 自家 ELK。

**System 1 / 2 标签**：System 1（确定性数据出口）

**Protocol 接口**：

```python
@runtime_checkable
class ObservabilityPlugin(Protocol):
    """自定义 observability sink 的协议。
    
    实现以下三个 ABC 之一或多个：
    - TraceSink：接收 TraceSpan
    - MetricsSink：接收 metric 事件
    - AuditSink：接收 audit log 事件
    """
    
    plugin_id: str
    
    @property
    def trace_sink(self) -> Optional["TraceSink"]:
        ...
    
    @property
    def metrics_sink(self) -> Optional["MetricsSink"]:
        ...
    
    @property
    def audit_sink(self) -> Optional["AuditSink"]:
        ...

class TraceSink(Protocol):
    def emit(self, span: "TraceSpan") -> None: ...

class MetricsSink(Protocol):
    def emit_counter(self, name: str, value: float, tags: dict) -> None: ...
    def emit_event(self, name: str, attrs: dict) -> None: ...

class AuditSink(Protocol):
    def emit(self, audit_record: dict) -> None: ...
```

**entry_points 注册**：

```toml
[project.entry-points."krow.observability"]
datadog_sink = "industrial_design_pkg.observability:DatadogSink"
```

**现有 SSOT 复用 / 新建**：
- `modules/observability/__init__.py` 已暴露：`MetricsRegistry` / `record_counter` / `record_event` / `start_span` / `TraceSpan` / `current_trace_id` / `drain_spans` 等
- `modules/observability/audit_reporter.py:WikiAuditReporter` / `install_wiki_audit_reporter` — 已有
- 新建 `TraceSink` / `MetricsSink` / `AuditSink` ABC（薄封装现有 API）

**Step 1 改造**：
- 新建三个 ABC（小工作量）
- `MetricsRegistry` 改造为支持 sink 列表（事件分发到所有注册 sink）
- tracing `drain_spans` 改造为分发到所有 TraceSink

**反模式**：

| 反模式 | 替代 |
|---|---|
| sink 内同步 HTTP POST（阻塞主流程） | sink 应缓冲 + 异步 flush |
| sink 内调 LLM 做"智能告警" | observability 是 System 1，禁止跨界 |
| sink 抛异常拖死主流程 | SDK 内部 try/except 包裹 |

---

### §5.7 P7 MCPServerPlugin — 注册外部 MCP server

**用途**：外部 plugin 把领域设备 / 服务（CAD 软件、实验室仪器、领域 API）暴露为 MCP server，让 agent 通过 MCP 协议调用。

**System 1 / 2 标签**：System 1（MCP 协议是确定性 RPC）

**Protocol 接口**：

```python
@runtime_checkable
class MCPServerPlugin(Protocol):
    """外部注册 MCP server 的协议。"""
    
    plugin_id: str
    server_name: str  # MCP server 名（用于工具命名）
    
    def get_server_config(self) -> "MCPServerConfig":
        """返回 MCP server 配置（连接方式、工具列表、参数模式）。"""
        ...

@dataclass
class MCPServerConfig:
    name: str
    transport: Literal["stdio", "http", "websocket"]
    command: list[str] | None  # stdio 时启动命令
    url: str | None  # http/websocket 时 endpoint
    tools: list[ToolDefinition]
```

**entry_points 注册**：

```toml
[project.entry-points."krow.mcp_servers"]
solidworks_mcp = "industrial_design_pkg.mcp:SolidWorksMCPServer"
```

**现有 SSOT 复用**：
- `modules/mcp/` 已有 MCP 协议客户端（`mcp>=1.0.0` 主依赖）
- `modules/agent/mcp_registry.py` — MCP server 注册中心

**Step 2 改造**（中等改造）：
- 现有 `modules/mcp/` 是客户端连接外部 MCP server；要做"反向注册"——让 plugin 声明 server 配置 → SDK 启动时连接 → 工具自动注入 ToolManager
- `entry_points("krow.mcp_servers")` 自动发现

**反模式**：

| 反模式 | 替代 |
|---|---|
| MCP server 暴露太多工具（> 20 个） | 拆多个 server 或合并工具（`AGENTS.md` (internal) §五） |
| MCP server 启动失败 SDK 静默吞错 | fail-loud，启动期错误立即抛 |
| 连接 MCP server 走第三方 LLM key | LLM 强绑 krow cloud（§3） |

---

### §5.8 P8 SecurityPlugin — 声明式安全策略（MVP 降级版）

**用途**：外部 plugin 自我声明安全策略——文件 IO / shell 白名单 / 网络访问 / 子进程边界。

**System 1 / 2 标签**：System 1（部分硬闸门 + 部分审计）

**MVP 降级声明**（铁证，第 4 轮辩论决策）：

| 维度 | MVP 实现 | 真沙箱（Step 3 强化） |
|---|---|---|
| 文件 IO 白名单 | ✅ `SandboxValidator` 硬闸门（违反 fail-loud） | 同 MVP |
| Shell 命令白名单 | ✅ `SandboxValidator` 硬闸门 | 同 MVP |
| 网络访问白名单 | ⚠️ 仅审计 + EventBus 事件，**不**真阻断 | subprocess 隔离阻断 |
| 子进程边界 | ⚠️ 仅声明 + 审计 | subprocess 隔离 |
| LLM 后端强绑 krow cloud | ✅ Builder 注入 + provider 检查 | 同 MVP |
| 数据隔离（plugin 间） | ⚠️ 仅 namespace 命名约定 | 真隔离 |

**design doc 必须明文写**：MVP 不是强沙箱；强沙箱在 Step 3（subprocess 隔离）。

**Protocol 接口**：

```python
@runtime_checkable
class SecurityPlugin(Protocol):
    """声明式安全策略协议。"""
    
    plugin_id: str
    
    @property
    def policy(self) -> "PluginSecurityPolicy":
        ...

@dataclass
class PluginSecurityPolicy:
    # 文件 IO 白名单（{project_root} 占位符自动解析）
    file_paths_allowed: list[str] = field(default_factory=list)
    file_paths_readonly: list[str] = field(default_factory=list)
    
    # Shell 命令白名单
    shell_commands_allowed: list[str] = field(default_factory=list)
    
    # 网络访问（弱执行：违反时审计 + EventBus 事件，不阻断）
    network_hosts_allowed: list[str] = field(default_factory=list)
    
    # 子进程边界（声明式 + 审计）
    subprocess_allowed: bool = False
    
    # LLM 后端：必须走 krow cloud（不可配置，文档常量）
    llm_must_use_krow_cloud: Literal[True] = True
```

**entry_points 注册**：

```toml
[project.entry-points."krow.security_policies"]
cad_security = "industrial_design_pkg.security:CADSecurityPolicy"
```

**现有 SSOT 复用**：
- `modules/remote/security_policy.py:SandboxValidator` / `ProjectAccessPolicy` — 已有底座（语义需扩展）
- `modules/remote/security_policy.py:SecurityPolicyManager` — 单例
- `modules/observability/audit_reporter.py` — 审计 sink
- `modules/events/bus.py` — EventBus（用 `plugin.security.violation` topic 发布违规事件）

**Step 1 改造**：
- 新建 `modules/agent/sdk/security.py`（薄封装），复用底层 `SandboxValidator`
- `PluginSecurityPolicy` 数据模型 + `with_security_policy` Builder API

**Step 2 改造**：
- 文件 IO + shell 命令的硬闸门集成到 ToolManager 工具调用前置 hook
- 网络访问监控（弱执行）走 `socket.socket.connect` import hook（弱守门）
- audit log + EventBus 事件
- 跨平台 smoke（`SandboxValidator` 在 win/mac/linux 路径分隔符行为不同）

**反模式**：

| 反模式 | 替代 |
|---|---|
| `file_paths_allowed = ["/**"]`（开全部） | 必须显式列白名单 |
| `subprocess_allowed=True` 但不声明 shell_commands_allowed | shell_commands_allowed 必须显式列 |
| 假装"做了沙箱"（`AGENTS.md` (internal) §0.0 准确性 > 完整性） | design doc 必须明文 MVP 不是强沙箱 |
| Plugin 试图绕过 SandboxValidator（直接 `os.write` 跳过 SDK file API） | Step 3 才能根治；MVP 通过 audit + 行为审查兜底 |

---

### §5.9 P9 DomainPackPlugin — 领域知识包（语法糖：聚合 Hint+Tool+Gate+supplementary extended.md）

**用途**（第 6 轮辩论 / 用户场景驱动）：科研 / 工业设计 / 法律 / 医疗等团队常需要"批量定制 native ACT 的领域专用知识"。例如科研场景：要让 native `wiki_compiler` 抽取的实体类型符合"研究方法 / 算法名 / 数据集名 / 评估指标"等专属定义；工业设计场景：要让 native `pptx_editor` 渲染时遵循"双视图正交制图 / 国标公差标注"等领域规范。

**痛点（不开 P9 时的反模式）**：

外部 plugin 团队要做这件事，**不开 P9** 时只能：
- 写一个 HintPlugin 加 N 条 hint（散在 reasoning preamble / tool priority hint）
- 写一个 ToolPlugin 加自己的领域工具（如 `research.extract_paper_entities`）
- 写一个 GatePlugin 加领域闸门（如 `mech_constraints` / `paper_quality_gate`）
- **跨 3 个 plugin 文件**，**逻辑严重碎片化**——一个领域包的所有元素散在 3 个包内，不利于版本管理 / 复用 / 移交

**P9 = 语法糖**：把 HintPlugin + ToolPlugin + GatePlugin + supplementary extended.md（追加到 native ACT extended.md）**4 类元素聚合到一个 plugin 类**里，外部团队**只写 1 个 DomainPack 类**，SDK 启动时**内部展开**为 3 个底层 plugin + supplementary md。

**System 1 / 2 标签**：System 1（pack 数据是声明式 yaml + markdown；展开是确定性查表）

**Protocol 接口**：

```python
# krow_agent_sdk/protocols.py
from typing import Protocol, runtime_checkable, Optional
from pathlib import Path

@runtime_checkable
class DomainPackPlugin(Protocol):
    """领域知识包协议——聚合 Hint+Tool+Gate+supplementary extended.md。

    SDK 启动时**内部展开**为：
    - HintPlugin（条件 hint 注入到 native ACT 的 reasoning preamble / tool priority hint）
    - ToolPlugin（领域工具，namespace=plugin_id）
    - GatePlugin（领域闸门）
    - supplementary extended.md（追加到 target_act 的 extended.md，内存合并、不改源文件）

    Plugin 实现此协议后通过 entry_points 注册：

    [project.entry-points."krow.domain_packs"]
    research_pack = "research_agent_pkg:get_domain_pack"
    """

    plugin_id: str  # 全局唯一 id
    pack_name: str  # 领域包名（如 "research_paper_extraction" / "industrial_design_metric"）
    target_acts: list[str]  # 作用于哪些 native ACT（如 ["wiki_compiler", "knowledge_analyzer"]）

    @property
    def priority(self) -> int:
        """优先级 1-10。多 pack 同 target_act 时按 priority 降序合并；同 priority 时按 plugin_id 字典序。"""
        ...

    # ── 原 4 元素（必填或返回空集合）──

    def get_extended_md_supplement(self, target_act: str) -> Optional[str]:
        """返回追加到 target_act extended.md 的 markdown 文本（不超过 4000 字符；超长 fail-loud）。

        允许 None 表示不追加。
        ACTLoader 加载 target_act 时，将 native extended.md + 所有 pack 的 supplement 内存合并：

            <native extended.md>
            ---
            ## 领域知识包：<pack_name>（plugin: <plugin_id>）
            <supplement_text>

        合并后的内容用于生成给 LLM 看的 ACT prompt（不写回磁盘，不修改 native 源文件）。
        """
        ...

    def get_hints(self) -> list["HintDefinition"]:
        """领域 hint。SDK 内部展开为 HintPlugin 注册到 HintRegistry。"""
        ...

    def get_tools(self) -> list["ToolDefinition"]:
        """领域工具。SDK 内部展开为 ToolPlugin 注册到 ToolManager；自动加 namespace `<plugin_id>.<tool_name>`；ToolDefinition 内可携 traits 字段（如 `["VERIFY_FIX","FILE_PATH"]`）以注入 trait registry。"""
        ...

    def get_gates(self) -> list["Gate"]:
        """领域闸门。SDK 内部展开为 GatePlugin 注册到 GateChain（phase=conclude）。"""
        ...

    # ── 第 8 轮辩论新增 4 元素（全 OPTIONAL，默认空）──

    def get_visual_adapters(self) -> dict[str, "VisualAdapter"]:
        """领域格式视觉适配器（如 `.step` 工业 CAD / `.mol` 分子 / `.fasta` 生物序列）。

        SDK 内部展开为 `register_visual_adapter(ext, adapter)` 调用（详 §6.4）。
        默认返回 `{}`（不注册任何 adapter）。

        一个 ext 多 pack 注册时由 SDK 启动期检测冲突并 fail-loud，由 plugin 端协调。
        """
        return {}

    def get_mcp_servers(self) -> list["MCPServerConfig"]:
        """领域 MCP server 配置（如 SolidWorks MCP / 实验室仪器 MCP / 论文数据库 MCP）。

        SDK 内部展开为 P7 MCPServerPlugin 注册（自动反向 server 启动 + 工具注入 ToolManager）。
        默认返回 `[]`（不注册任何 server）。
        """
        return []

    def get_event_listeners(self) -> list[tuple[str, Callable[["Event"], None]]]:
        """领域 EventBus 事件监听（用于领域 audit log / 自定义指标）。

        每项是 `(topic_pattern, listener)`，topic_pattern 必须是 §5.5 P5 EventListenerPlugin
        承诺的稳定 topic 子集（`budget.*` / `agent.*` / `executor.*` / `react.*` /
        `background_task.*` / `plugin.*`）；订阅动态 topic（如 `pptx.page_*`）会被 SDK
        启动期 fail-loud 拒绝。

        listener 必须只读 / 副作用幂等；禁止修改 budget / state / event payload（详 §5.5 反模式）。
        默认返回 `[]`（不注册任何监听器）。
        """
        return []

    def get_recommended_budget(self) -> Optional["BudgetSpec"]:
        """领域**推荐**预算配置（不强制；plugin 端 BudgetSpec 优先级更高）。

        SDK 内部行为：当 plugin 调 `AgentBuilder.with_domain_pack(pack)` 时，
        若 plugin 在 `with_domain_pack` 之**前**未显式调 `with_budget(...)`，
        则用 pack 的 recommended_budget 填充默认值；
        若 plugin 已显式调 `with_budget(...)`，则忽略 pack 的推荐值（plugin 优先）。

        默认返回 `None`（不提供推荐值）。
        """
        return None
```

**约束铁律**（`AGENTS.md` (internal) §0.1 TURBO + §0.2 OCP 严守 / 防"meta-plugin 越来越胖"反模式）：

| 铁律 | 落地 |
|---|---|
| **DomainPack 只聚合现有 plugin 协议元素 + 已暴露 SSOT** | 8 元素全部走 P1/P2/P3/P4/visual_adapter/P5/P7 + BudgetSpec 已有路径，禁止引入新 System 2 行为 |
| **每个 get_\* 都 OPTIONAL** | 默认 `[]` / `{}` / `None`；老 P9 plugin 不写新方法直接兼容（向后兼容） |
| **SDK 内部 expander 完全展开为底层 plugin 注册** | 无 DomainPack 独有的运行时行为；可逆性高（plugin 团队改用直接 P1+P2+...+P7 写法等价） |
| **扩展新字段必须先回到第 8 轮辩论原则审视** | 防 P9 元素无限膨胀；候选项必须满足"复用现有 SSOT + OCP 不破红线"（如 `get_react_templates` 已被第 2 轮否决，不能塞进来；`get_experience_categories` 是 system enum，plugin 不能加） |

**entry_points 注册**：

```toml
[project.entry-points."krow.domain_packs"]
research_pack = "research_agent_pkg:get_research_pack"

# Python 实现：
# def get_research_pack() -> DomainPackPlugin: ...
```

**完整使用示例（科研场景）**：

```python
# research_agent_pkg/__init__.py
from krow_agent_sdk.protocols import DomainPackPlugin, HintDefinition, ToolDefinition
from krow_agent_sdk.gates import make_simple_gate

class ResearchPaperPack:
    plugin_id = "acme.research_pack"  # 双段 "<org>.<plugin_name>"（详 _plugin_id_validator）
    pack_name = "research_paper_extraction"
    target_acts = ["wiki_compiler", "knowledge_analyzer"]
    priority = 5

    def get_extended_md_supplement(self, target_act: str) -> Optional[str]:
        if target_act == "wiki_compiler":
            return """
### 科研论文实体抽取规范

抽取的实体类型限定为：
- **方法名**（method）：论文提出的算法 / 模型架构（如 `Transformer` / `BERT`）
- **数据集**（dataset）：用于实验的公开数据集（如 `ImageNet` / `GLUE`）
- **评估指标**（metric）：精度 / 召回率 / F1 / BLEU 等
- **作者机构**（org）：论文署名机构

**禁止**抽取通用实体（如 `论文`、`模型`、`数据`）—— 这些是模糊概念。
"""
        return None

    def get_hints(self) -> list[HintDefinition]:
        return [
            HintDefinition(
                name="research_extraction_focus",
                hint_text="科研场景：抽实体只看方法/数据集/指标三类；遇到通用名词（论文/模型）跳过。",
                trigger_acts=["wiki_compiler"],
                position="reasoning_preamble",
            ),
        ]

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="research.extract_paper_metadata",  # 自动加 plugin_id namespace 后是 "research_agent.research.extract_paper_metadata"
                description="抽取论文元数据（DOI / 作者 / 发表年份 / venue）",
                handler=extract_paper_metadata_handler,
                latency_class="warm",
                traits=["CONTENT_SOURCE"],
            ),
        ]

    def get_gates(self) -> list:
        return [
            make_simple_gate(
                name="paper_extraction_quality_gate",
                check=lambda ctx: ctx.entities_count >= 3,  # 至少抽 3 个实体才允许 conclude
                block_reason="科研论文百科：实体抽取数量不足 3，建议 replan 再读一次论文",
            ),
        ]

def get_research_pack() -> DomainPackPlugin:
    return ResearchPaperPack()
```

**SDK 内部展开机制**（Step 2 实现）：

```python
# krow_agent_sdk/_domain_pack_expander.py（伪代码，第 8 轮辩论扩展为 8 元素）
def expand_domain_pack(pack: DomainPackPlugin, registries: SDKRegistries) -> None:
    # ── 原 4 元素 ──

    # 1. 注册 hint
    for hint in pack.get_hints():
        registries.hint_registry.register(
            plugin_id=pack.plugin_id,
            hint=hint,
            priority=pack.priority,
        )

    # 2. 注册 tool（自动加 namespace + 注入 traits）
    for tool in pack.get_tools():
        registries.tool_manager.register_tool(
            name=f"{pack.plugin_id}.{tool.name}",
            ...,
            tool_def=tool,
        )
        for trait in (tool.traits or []):
            registries.trait_registry.add(name=tool.name, trait=trait)

    # 3. 注册 gate（phase=conclude）
    for gate in pack.get_gates():
        registries.gate_chain.register(gate)

    # 4. supplementary extended.md：注册到 ACTLoader 的 supplement_registry
    for target_act in pack.target_acts:
        supplement = pack.get_extended_md_supplement(target_act)
        if supplement:
            assert len(supplement) <= 4000, f"supplement too long for {pack.plugin_id}/{target_act}"
            registries.act_loader.register_extended_md_supplement(
                target_act=target_act,
                plugin_id=pack.plugin_id,
                priority=pack.priority,
                supplement=supplement,
            )

    # ── 第 8 轮辩论新增 4 元素（OPTIONAL）──

    # 5. 注册 visual_adapters（薄封装 register_visual_adapter；详 §6.4）
    for ext, adapter in (pack.get_visual_adapters() or {}).items():
        registries.visual_registry.register(ext=ext, adapter=adapter, plugin_id=pack.plugin_id)

    # 6. 注册 MCP servers（走 P7 MCPServerPlugin loader）
    for server_cfg in (pack.get_mcp_servers() or []):
        registries.mcp_loader.register_server(plugin_id=pack.plugin_id, config=server_cfg)

    # 7. 注册 event listeners（topic 必须在 §5.5 稳定子集内，否则 fail-loud）
    for topic_pattern, listener in (pack.get_event_listeners() or []):
        registries.event_listener_loader.register(
            plugin_id=pack.plugin_id,
            topic_pattern=topic_pattern,
            listener=listener,
        )

    # 8. recommended_budget：仅当 builder 未显式 .with_budget(...) 时填默认值
    rec = pack.get_recommended_budget()
    if rec is not None and not registries.builder.has_explicit_budget():
        registries.builder.set_default_budget(rec)
```

**ACTLoader 加载时合并逻辑**（Step 2 改造）：

```python
def get_act_extended_md(self, act_name: str) -> str:
    base = self._load_native_extended_md(act_name)  # 读 native extended.md
    supplements = self._supplement_registry.get(act_name, [])  # list[(priority, plugin_id, text)]
    supplements.sort(key=lambda x: (-x[0], x[1]))  # priority 降序、plugin_id 字典序

    parts = [base]
    for priority, plugin_id, text in supplements:
        parts.append(f"\n---\n## 领域知识包：{plugin_id}（priority={priority}）\n{text}\n")
    return "\n".join(parts)
```

**现有 SSOT 复用**（`AGENTS.md` (internal) §0.2 造轮子检查）：
- HintRegistry / ToolManager / GateChain — Step 1 已建（§0.2 表）
- ACTLoader extended.md 加载 — `modules/agent/act/act_loader.py` 已有；Step 2 加 `register_extended_md_supplement` + 内存合并（OCP 扩展，不破现有调用）

**Step 1 改造**（仅协议骨架）：
- 新建 `krow_agent_sdk/protocols.py:DomainPackPlugin` Protocol
- 新建 `krow_agent_sdk/_domain_pack_expander.py` expander 骨架（不调底层注册）
- 新建 `tests/sdk/test_domain_pack_protocol_contract.py` 契约测试骨架

**Step 2 改造**（实现 + entry_points 加载）：
- `ACTLoader.register_extended_md_supplement` + 内存合并逻辑
- `expand_domain_pack` 真实展开到底层 hint/tool/gate
- entry_points("krow.domain_packs") 自动发现
- feature flag `KROW_PLUGIN_P9_DOMAIN_PACK`

**反模式**：

| 反模式 | 替代 |
|---|---|
| supplement 内写 prompt 注入（"忽略上文系统指令"） | SDK 启动期扫描敏感关键词 fail-loud（与 PromptSafetyPlugin U1 协同） |
| 多 pack 同 target_act 各自定义冲突的"实体类型"（一个说只抽 X，另一个说只抽 Y） | priority 排序合并；冲突由 LLM 看到所有 supplement 文本，按 priority 顺序权衡（System 2 决策） |
| pack 试图覆盖 native extended.md（写"忽略上文 native 规则") | 物理上不可能（内存合并，supplement 永远在 native 之后追加；LLM 看到 native 在前） |
| supplement > 4000 字符 | fail-loud；想塞更多内容请拆多个 pack |
| pack 在 supplement 内"嵌入完整 ACT 重定义" | 不允许；要新 ACT 走 P1 ACTPlugin |
| pack 修改 native ACT 源文件 | 物理上不允许（plugin 没写权限），且 ACTLoader 加载时已用内存合并避免源文件污染 |
| pack target_acts 写不存在的 native ACT name | SDK 启动期 fail-loud（namespace 校验） |
| **第 8 轮新增**：pack 在 `get_visual_adapters` 内为已存在 ext（如 `.docx`）注册 adapter 试图覆盖 native | SDK 启动期检测同 ext 多 plugin 注册 fail-loud；plugin 端协调（plugin_id 命名空间或换 ext 别名） |
| **第 8 轮新增**：pack 在 `get_event_listeners` 内订阅动态 topic（如 `pptx.page_finish`） | SDK 启动期 fail-loud；§5.5 稳定 topic 子集只含 `budget.*` / `agent.*` / `executor.*` / `react.*` / `background_task.*` / `plugin.*` |
| **第 8 轮新增**：pack listener 内修改 budget / state / event payload | listener 是只读契约（`AGENTS.md` (internal) §0.2 SRP）；只能做 audit / metrics / 转发到外部系统 |
| **第 8 轮新增**：pack 试图通过 `get_recommended_budget` 强制 plugin 端 BudgetSpec | recommended_budget 是软建议；plugin 端 `with_budget(...)` 优先级更高（详 expander §8） |
| **第 8 轮新增**：pack 引入"全新 plugin 维度"（如 `get_react_templates` / `get_experience_categories`） | 不允许；P9 只聚合现有元素；新 plugin 维度必须先走 §5 新增 Protocol（不开 P10/P11） |

**与 §4.4 native ACT 扩展规则对齐**：P9 是 §4.4 表中"DomainPack supplementary extended.md → ADD"行的实现底座；唯一允许 ADD 的方式即 P9 + ACTLoader 内存合并；其他任何"修改 native ACT"路径都被禁止。

---

### §5.10 数据层暴露策略（不开 Plugin Protocol，函数式只读 façade）

**用途**（第 7 轮辩论 / 用户场景驱动）：外部 plugin 团队常需要"读 agent 数据层"做深度集成（如 plugin 自己做领域向量检索 / 读 ontology 给 LLM 看 / 读 experience memory 做 cross-task 学习 / 读 agent state 做诊断 / 上报内部知识图谱节点到 plugin 自己的可视化）。

**关键事实**（第 7 轮辩论铁证）：
- 仓内**多 sqlite db 分散落点**（subagent 找到 7+ 个）：`agent_memory.db` / `experience_memory/memory.db` / `.krow/ontology/global.db` / `transaction_log.db` / `knowledge.db`（多路径）/ `.file_index.db` / `~/.copilot/file_audit.db`
- Python API 层已有完整只读门面：`KnowledgeAPI` / `SessionOntologyStore.to_view()` / `GlobalOntologyStore` / `ExperienceMemoryService.recall()` / `AgentMemoryStore`（StateManager）

**策略**（不开 Plugin Protocol，只暴露 SDK 函数式只读 façade）：

| 数据层 | SDK 暴露方式 | 写权限 |
|---|---|---|
| 会话 ontology | `krow_agent_sdk.data.get_ontology_view() → SessionOntologyView`（包装 `SessionOntologyStore.to_view()`） | ❌ 写禁止；写只能走 ACT 工具触发 ontology emit 事件 |
| 全局 ontology | `krow_agent_sdk.data.get_global_ontology(scope="current_project") → GlobalOntologyReader`（包装 `GlobalOntologyStore`，强制 scope 隔离） | ❌ 写禁止 |
| Knowledge Graph（含 Neo4j L2 可选） | `krow_agent_sdk.data.query_knowledge(query, scope, layers=["L0","L1"]) → KnowledgeResult`（默认不查 L2 防 Neo4j 高负载） | ❌ 写禁止；写走 `wiki_compiler` ACT |
| Experience Memory | `krow_agent_sdk.data.recall_experiences(query, k=5, category=None) → list[ExperienceRecord]` | ❌ 写禁止；写走 ACT 工具的 `record_experience` 自动触发 |
| Agent State | `krow_agent_sdk.data.get_state_snapshot() → AgentStateSnapshot`（StateManager 当前状态只读快照） | ❌ 写禁止 |
| Vector Embedding | 不直接暴露 EmbeddingEngine；plugin 想做向量检索 → 走 `recall_experiences` 内置语义检索 | ❌ |

**为什么不开 Plugin Protocol**：
- 数据层是 SSOT，OCP 扩展点是"加新读写工具"（走 P2 ToolPlugin），不是"加新数据存储 backend"（这是元认知不让换的范畴，与第 2/3 轮辩论一致）
- 不开 Protocol = 0 blast radius；plugin 只读不影响内核数据一致性

**反模式**：

| 反模式 | 替代 |
|---|---|
| Plugin 直接 `sqlite3.connect("agent_memory.db")` 读写 | 启动期扫描 plugin 模块 import → warning + audit；fail-loud 反对；走 `krow_agent_sdk.data` API |
| Plugin 调 `AgentMemoryStore.update_state()` 写状态 | 不暴露写 API；写只能通过 StateManager 内部 + agent 自己 |
| Plugin 调 `Neo4jKGWriter.write()` 写图 | 不暴露写 API；写走 `wiki_compiler` ACT |
| Plugin 试图改 ontology 数据 | `SessionOntologyView` / `GlobalOntologyReader` 无写方法 |
| Plugin 在 query_knowledge 里查 L2 Neo4j 高频 | 默认 `layers=["L0","L1"]` 不查 L2；要查 L2 必须显式传 + 走 BudgetController 计入 |

---

### §5.11 诊断工具策略（不开 Plugin Protocol，read-only facade，**不接入 turbo_diagnostics v1**）

**用途**（第 7 轮辩论）：外部 plugin 团队需要 agent 诊断能力（dump_state / get_diagnostics_snapshot / metrics 导出）做 bug report、运维监控、性能分析。

**关键事实**（第 8 轮辩论铁证修正第 7 轮误判）：

| 项 | 第 7 轮误判 | 第 8 轮铁证 |
|---|---|---|
| `turbo_diagnostics.py` 是死代码 | "应该接入 executor 主干（PR S1.12）" | **错误**：v1 完整设计已被 v2（`executor_recovery.py` + `_diagnose_and_correct`）替代；`executor_recovery.py` 模块 docstring 明文："**取代 T4-lite + T5-lite**"；`tests/test_turbo_diagnostics.py` 注释："**`_handle_failure` 不再走 T4-lite ReACT**" |
| `turbo_diagnose_step_*` 与 v1 关系 | "内联实现的 t4 诊断" | **错误**：`f"turbo_diagnose_step_{id}"` 仅是 ReACTEngine 动态名；prompt（`_DIAGNOSTIC_SYSTEM_PROMPT`）/ 工具集（`search_files`+`grep_content`+`read_file`+`save_note`+`inspect_step_result`）/ 超时（45s vs v1 的 30s）/ 结论 schema（`DiagnosticCorrection` vs v1 的 `TurboDiagnosisResult`）**全部不同**——不是别名，是独立 v2 实现 |
| 接入 v1 风险 | "中（影响诊断分支）" | **实际：高**——`run_t4_diagnostic` 内部**不调** `record_llm_call`（v2 显式调），接入会让 budget 计数失算；prompt/工具/schema 不一致会让 `parse_diagnostic_conclusion` 解析失败 |

**第 8 轮决策**：**不接入 v1**；架构文档（`docs/current/core/TURBO_ARCHITECTURE.md` / `V3_ARCHITECTURE_GUIDE.md`）与代码漂移是主仓治理债务，**不在 SDK 范围**。

**原 PR S1.12 重写**：从"接入 turbo_diagnostics + 暴露 diagnostics facade"砍半 → **仅暴露 SDK diagnostics facade**（薄封装现有 `ProgressiveExecutor` 状态读取），1.5 天工作量，0 executor 改动。

**SDK diagnostics facade 仍提供**（read-only）：
- `agent_session_debug` / `dump_state` 当前**不存在通用 SDK API**（仅 `scripts/s14_visual_walkthrough.py:_dump_state` 局部脚本函数）
- `modules/observability/{tracing,metrics,audit_reporter}.py` 已有完整能力

**策略**（不开 Plugin Protocol，函数式 read-only facade）：

| 诊断能力 | SDK 暴露方式 |
|---|---|
| Agent 状态快照 | `krow_agent_sdk.diagnostics.get_snapshot(agent) → DiagnosticsSnapshot`（含 BudgetController state / TaskBudget / 当前 plan / 执行历史 / event log 最近 N 条） |
| 完整 state dump | `krow_agent_sdk.diagnostics.dump_state(agent, output_path) → Path`（落盘为 JSON，用于 bug report） |
| Tracing | 走 P6 ObservabilityPlugin（已有）；plugin 自己注册 TraceSink |
| Metrics | 走 P6 ObservabilityPlugin（已有）；plugin 自己注册 MetricsSink |
| Plugin 自定义诊断 | 走 P5 EventListenerPlugin 订阅 `turbo.*` / `executor.*` / `react.*` / `agent.*` 事件 |

**为什么不开 P10 DiagnosticsPlugin**：
- 诊断是 agent 内核行为（如 turbo_diagnostics 的 t4/t5 探测策略），元认知不让外部替换（与第 2/3 轮辩论"只能用不能换"决策一致）
- plugin 想自定义诊断 → 走 P5 + P6 已足够

**Step 1 必修（PR S1.12 + S1.13）**：
- **PR S1.12**（第 8 轮修订，工作量从 3d 缩到 1.5d）：**仅暴露** `krow_agent_sdk.diagnostics.dump_state` / `get_snapshot` SDK API（薄封装现有 ProgressiveExecutor 状态读取）；**不接入** turbo_diagnostics v1（第 8 轮铁证：v1 已被 v2 `executor_recovery.py` + `_diagnose_and_correct` 替代，强制接入会引入回归风险）
- **PR S1.13**：核实 micro 内每次 LLM 调用是否计入 macro `TaskBudget.record_llm_call` + 加 unit test 守住一致性 + 修 `ReACTEngine._effective_max_iterations` 与 `while iteration < self._config.max_iterations` 不一致问题（§0.3 R21 / R22）

**反模式**：

| 反模式 | 替代 |
|---|---|
| 把 turbo_diagnostics v1 接入 executor 主干（**第 8 轮辩论否决**） | v1 已被 v2（executor_recovery + _diagnose_and_correct）替代；维持现状不动；架构文档与代码漂移是主仓治理债务，不在 SDK 范围 |
| Plugin 想替换 v2 诊断策略（_diagnose_and_correct） | 不开 Protocol；plugin 走 P5 EventListener 自查 `executor.*` / `turbo.*` 事件 |
| Plugin 把 dump_state 输出 JSON 直接塞 LLM 做"智能诊断" | 走 ToolPlugin 加诊断工具（System 2）；不要在 dump 函数内调 LLM |
| Plugin 通过 dump_state 拿到 sqlite 内部数据 | dump_state 输出过滤掉 secrets / token / 私密路径；plugin 不能借此绕过 §5.10 数据层只读边界 |

---

### §5.12 预算插件覆盖度声明（**关键事实澄清**）

**用途**（第 7 轮辩论 / 用户问题驱动）：用户问"BudgetPlugin 能完整覆盖预算控制吗"——答案是**不能**。本子节明文澄清 plugin 能做什么、不能做什么，避免设计错位。

**关键事实**（第 7 轮辩论铁证）：

```
┌─────────── 真实预算架构（4 处 SSOT，分散）───────────┐
│                                                       │
│  Macro 任务级（TaskBudget）                            │
│   SSOT: modules/agent/progressive/models.py:TaskBudget│
│   ├─ max_total_time_ms / time_used                    │
│   ├─ max_total_llm_calls / llm_calls_used             │
│   ├─ adapt_extensions_used / max_adapt_extensions     │
│   └─ replans_used                                     │
│                                                       │
│  ProgressiveExecutor 主循环（扩容内核）                 │
│   SSOT: modules/agent/progressive/executor.py         │
│   ├─ _handle_adapt_budget_extension（+5min/次）       │
│   ├─ _compute_dynamic_cap（动态上限）                 │
│   ├─ _try_replan + _recompute_budget_after_replan     │
│   └─ ErrorAccumulator 断路器（拒绝预算扩容）          │
│                                                       │
│  AgentV3 watchdog（墙钟监控）                          │
│   SSOT: modules/agent/agent_v3.py                     │
│   ├─ target_wallclock_reached                         │
│   ├─ max_wallclock_reached                            │
│   └─ grace_conclude_started                           │
│                                                       │
│  Micro ReACTConfig（独立空间）                         │
│   SSOT: modules/agent/react_engine.py:ReACTConfig     │
│   ├─ max_iterations                                   │
│   ├─ max_time_ms                                      │
│   └─ react.budget_exhausted / react.micro_timeout     │
│                                                       │
│  BudgetController = 仅事件转发 facade（不执行预算）     │
│   SSOT: modules/agent/progressive/budget_controller.py│
│   _FORWARD_MAP:                                       │
│     progressive.adapt_budget_extended → budget.extended│
│     agent.target_wallclock_reached    → budget.target_reached │
│     agent.max_wallclock_reached       → budget.max_reached    │
│     agent.grace_conclude_started      → budget.grace_started  │
│     progressive.budget_exhausted      → budget.exhausted      │
└───────────────────────────────────────────────────────┘
```

**预算两轴**（**没有 token-level budget**！铁证：`record_llm_call()` 仅 `+= 1`，不带 token；token 计费在 `KrowLLMProvider._notify_usage` 走 `UsageTracker.record(..., input_tokens=..., output_tokens=...)`）：

| 轴 | macro SSOT | micro SSOT |
|---|---|---|
| Walltime | `TaskBudget.max_total_time_ms` + `check_time_budget()` | `ReACTConfig.max_time_ms` |
| LLM 调用次数 | `TaskBudget.max_total_llm_calls` + `record_llm_call()` | `ReACTConfig.max_iterations`（迭代上限） |
| Token | ❌ **不存在 macro/micro 级 token budget**；token 仅在 `UsageTracker` 计费维度（krow cloud 余额管理） | ❌ |

**adapt 扩容机制**（macro 层）：
- 触发：`_reflect_and_adapt` 在 macro 步间 + TaskBudget 80% 时间压力检测
- 单次扩容：固定 +5 分钟（`_ADAPT_EXTENSION_MAX_MS = 300_000` ms）
- 动态上限：`_compute_dynamic_cap = max(MEGA_HARD_CAP, min(estimated, ABSOLUTE_MAX_CAP))`，其中 `estimated = read_time + write_time + 600s overhead`
- 次数上限：`max_adapt_extensions`（默认 3 次），撞顶后 fail-loud
- 受 `ErrorAccumulator` 断路器约束（错误累积 → 拒绝扩容）

**plugin 能做什么**：

| ✅ 允许 | 通过 |
|---|---|
| 监听 `budget.*` 5 个 facade 事件做告警/审计 | P5 EventListenerPlugin |
| 把 budget metrics 推到外部 Datadog/Prometheus/Grafana | P6 ObservabilityPlugin |
| 配置 macro/micro/adapt/replan/watchdog **全部预算上下限** | `AgentBuilder.with_budget(BudgetSpec)`（详 §6.1） |
| 在自己 plugin 工具内主动 `record_llm_call()` 计入 macro | 通过 SDK 注入的 `LLMProviderManager.get_*_model()` 自动计入（不需自己调） |
| 监听 `budget.exhausted` 后做"领域 fallback"（如保存当前进度） | P5 EventListener handler 内调 ToolPlugin |

**plugin 不能做什么**：

| ❌ 禁止 | 原因 |
|---|---|
| 替换 `_handle_adapt_budget_extension` 扩容公式（+5min/次 → 自定义算法） | 内核行为；元认知不让换；与第 2/3 轮决策一致 |
| 自定义 `_compute_dynamic_cap` 上限算法 | 内核行为；动态上限策略是 agent 治理一部分 |
| 干预 `ErrorAccumulator` 断路器决策 | 内核 safety net；错误熔断不让外部绕过 |
| 通过 P5 listener handler 试图修改 `TaskBudget.max_total_time_ms` 数值 | listener 只读；SDK 内部 `BudgetSpec` 在启动期固定，运行时不可改（防 plugin 中途扩容耗 krow cloud 余额） |
| 在 plugin 工具内手动调 `_handle_adapt_budget_extension` 提前扩容 | 不暴露这个内核 API |

**Plugin 想做的常见场景 → 推荐路径**：

| 场景 | 走法 |
|---|---|
| "预算到达 80% 触发自定义告警" | P5 EventListener 订阅 `budget.target_reached` |
| "LLM 调用次数过多预测告警" | P6 ObservabilityPlugin MetricsSink + plugin 自己计算阈值 |
| "task 超时 graceful 落盘" | P5 EventListener 订阅 `budget.grace_started` |
| "限制某 plugin 工具的 token 上限" | 通过 SDK 注入的 LLM provider，plugin 自己在调用前 estimate prompt token；不要试图改 macro budget |
| "工业领域任务用更长 walltime" | `AgentBuilder.with_budget(BudgetSpec(target_walltime_s=1800, max_walltime_s=3600, max_adapt_extensions=5))` |
| "plugin 想"动态扩容"" | ❌ 不允许；走"启动期通过 BudgetSpec 设大 + adapt 内核自动扩容"路径 |

**结论**：第 2 轮辩论已砍 BudgetListenerPlugin / BudgetExtensionPlugin；第 7 轮辩论再次确认**不开新 Protocol**。预算覆盖度通过 P5 EventListener（监听）+ P6 ObservabilityPlugin（导出）+ AgentBuilder.with_budget(BudgetSpec)（配置参数化）三条路径达到"完整可用 + 不破内核"的平衡。

### §5.13 反向 Telemetry opt-in（**v0.8 顶级 review A16 新增**）

**痛点**（顶级架构师视角）：§5.6 ObservabilityPlugin 是 plugin → 外部（plugin 把数据推到 Datadog 等）。**反向**没设计：

- 主仓维护者想知道"全网 plugin 用了哪些 Protocol？"→ 没机制
- "P7 / P8 / P9 实际使用率？"→ 没数据 → 不知道该砍 / 该投资
- "外部 plugin 触发了哪些 fail-loud 错误？最高频反模式？"→ 仅本地 audit，无集中

→ SDK 演化决策（§5.0.1 优先级分层 / §5.0.2 增减治理 / §9.3 Step 3 触发）**全是拍脑袋**。这是 LangChain / pip 历史教训（早期没 telemetry，5 年后 ecosystem 碎片化无解）。

**v0.8 决策：opt-in telemetry 模式，默认 off**：

```bash
# 用户 opt-in 后 SDK 上报最小匿名统计到 krow.cn
export KROW_SDK_TELEMETRY=1   # 默认 off，必须显式 opt-in
```

**上报内容**（minimal anonymous，与 GDPR 对齐）：

| 字段 | 说明 |
|---|---|
| `sdk_version` | 当前 SDK 版本号（如 `2.1.0`） |
| `plugin_id_hash` | 各 plugin_id 的 SHA-256 hash（不含明文 plugin_id，避免泄露） |
| `protocols_used` | 各 plugin 实际实现的 Protocol 列表（`["P1", "P2", "P4"]`） |
| `protocol_call_counts` | 各 Protocol 调用次数聚合（无入参 / 无返回值，仅次数） |
| `error_counts` | 各 error class 的触发次数（聚合，不含 stack trace） |
| `feature_flags_state` | 各 `KROW_PLUGIN_<x>` feature flag 的开关状态（不含 KROW_API_KEY 等 secrets） |

**绝不上报**：

- ❌ API key / secrets / OAuth token（黑名单 SECRETS_PATTERNS 过滤）
- ❌ 具体 user_input / agent.run 输入输出（只统计次数）
- ❌ 文件路径 / project_root（只统计次数）
- ❌ 任何可能含 PII 的字段

**上报频率 / 通道**：

- 频率：每小时聚合上报一次（不 per-call）
- 通道：HTTPS POST 到 `https://api.krow.cn/sdk/telemetry/v1/anonymous`（独立端点，与计费 / LLM 通道分离）
- 失败：silent drop（不能 telemetry 影响 SDK 主流程）

**Step 2 PR S2.17（v0.8 新增）**：实现 telemetry 上报 + opt-in 提示 + 数据流闭环（krow.cn 后端聚合 dashboard）

**反模式**：

| 反模式 | 替代 |
|---|---|
| telemetry 默认开启（违反 GDPR） | 默认 off + 明文 opt-in |
| 上报具体输入输出 / API key 内容 | 只上报聚合次数 + plugin_id_hash |
| telemetry 失败拖死 SDK 主流程 | silent drop |
| 把 telemetry 数据塞 LLM 做"智能分析" | telemetry 是 System 1 数据；System 2 分析在 krow.cn 后端做 |



## §6 SDK 顶层 API（AgentBuilder）

### §6.0 包名 import 路径双轨表（**v0.8 顶级 review D1 新增**）

> **痛点**：design doc 内 11 处 import 用 `from krow_agent_sdk import ...`，但 §9.1 落地路径是 `modules/agent/sdk/`（主仓内部子包）；Step 1 不发布 PyPI；开发者跟着写 `from krow_agent_sdk import AgentBuilder` → ImportError。

#### §6.0.1 阶段化 import 路径

| 阶段 | 真实 import 路径 | 备注 |
|---|---|---|
| **Step 1 落地期** | `from modules.agent.sdk import AgentBuilder` | main repo 内部 dogfood，需 main repo 路径 |
| **Step 1 PR S1.18 起（推荐）**| `from krow_agent_sdk import AgentBuilder` | **alias 双轨**：S1.18 在 `modules/agent/sdk/__init__.py` 加 `sys.modules.setdefault("krow_agent_sdk", sys.modules[__name__])`，使两个路径同时可用；外部团队 dogfood 时已能用稳定 import |
| **Step 2 PyPI 发布后** | `from krow_agent_sdk import AgentBuilder` | 走 PyPI；老 alias 保留 6 个月（与 §10.3 deprecation 一致） |

#### §6.0.2 完整 import map（design doc 内所有 SDK 路径）

| design doc 引用 | Step 1 真实路径（无 alias 时）| Step 1 alias 后 / Step 2 后路径 |
|---|---|---|
| `from krow_agent_sdk import AgentBuilder, BudgetSpec` | `from modules.agent.sdk import AgentBuilder, BudgetSpec` | `from krow_agent_sdk import AgentBuilder, BudgetSpec` |
| `from krow_agent_sdk.protocols import ACTPlugin, ToolPlugin, ...` | `from modules.agent.sdk.protocols import ...` | `from krow_agent_sdk.protocols import ...` |
| `from krow_agent_sdk.experimental.protocols import P9DomainPackPlugin` (A2) | `from modules.agent.sdk.experimental.protocols import ...` | `from krow_agent_sdk.experimental.protocols import ...` |
| `from krow_agent_sdk.gates import make_simple_gate` | `from modules.agent.sdk.gates import make_simple_gate` | `from krow_agent_sdk.gates import make_simple_gate` |
| `from krow_agent_sdk.events import subscribe` | `from modules.agent.sdk.events import subscribe` | `from krow_agent_sdk.events import subscribe` |
| `from krow_agent_sdk.visual import visual_inspect, VisualAdapter, open_adapter, ElementEntry, SceneConfig, SemanticRole, SemanticMap, VisualGroundingResult, FILLABLE_ROLES, PRESERVE_ROLES, ALL_ROLES, CONFIDENCE_THRESHOLD` | `from modules.agent.sdk.visual import ...` | `from krow_agent_sdk.visual import ...` |
| `from krow_agent_sdk.data import ...` | `from modules.agent.sdk.data import ...` | `from krow_agent_sdk.data import ...` |
| `from krow_agent_sdk.diagnostics import ...` | `from modules.agent.sdk.diagnostics import ...` | `from krow_agent_sdk.diagnostics import ...` |
| `from krow_agent_sdk.llm import ChatMessage, llm_source_context, make_plugin_source_module` | `from modules.agent.sdk.llm import ...` | `from krow_agent_sdk.llm import ...` |
| `from krow_test_sdk.harness import WorkbenchHarness` | `from tests.e2e_framework.harness import WorkbenchHarness`（A11 Step 2 物理迁移）| `from krow_test_sdk.harness import WorkbenchHarness` |

#### §6.0.3 Step 1 PR S1.18（v0.8 新增）

```python
# modules/agent/sdk/__init__.py
import sys

# v0.8 顶级 review D1：让外部团队从 Day 1 用稳定 import 路径
sys.modules.setdefault("krow_agent_sdk", sys.modules[__name__])

# 暴露稳定 API：
from .builder import AgentBuilder, BuilderConfig
from .protocols import (
    ACTPlugin, ToolPlugin, HintPlugin, GatePlugin,
    EventListenerPlugin, ObservabilityPlugin,
)
# experimental 单独 namespace（A2）
from . import experimental
# ...
```

效果：开发者 Day 1 写 `from krow_agent_sdk import AgentBuilder`，无论 Step 1 还是 Step 2 都能跑。

### §6.0.4 Plugin 错误模式 + lifecycle hook（**v0.8 顶级 review D5 + D6 新增**）

#### Plugin error mode（D6）

`KROW_SDK_PLUGIN_ERROR_MODE` 环境变量控制 plugin handler 抛异常时的行为：

| 模式 | 行为 | 适用场景 |
|---|---|---|
| `swallow`（**默认**）| `try/except` 包裹 + 发布 `plugin.error.<plugin_id>` 事件 + audit log + **`logging.error` 到 stderr** | 生产部署（plugin 错误不拖死 agent） |
| `raise` | fail-loud，plugin 错误立即向上抛 | CI / dev 调试（开发者第 7 天 debug 时必用） |
| `quiet` | 仅 audit log，不打 stderr，不发 EventBus | 大流量场景下减少日志噪声 |

**Step 1 必修**：当前 design doc 仅说"plugin 调用包 try/except + 发 EventBus 事件"——这意味着 swallow，但开发者**默认不订阅 `plugin.error.*`**，永远看不到错误。**v0.8 修订**：默认 swallow 模式必须**自动 logging.error 到 stderr**（开发者总能看到 + 不打断主流程）+ 加 `KROW_SDK_PLUGIN_ERROR_MODE` 环境变量切换。

#### Plugin lifecycle hook（D5）

所有 9 个 Protocol（P1-P9）共享一个可选 mixin（**不是新 Protocol**），plugin 实现 `on_load` / `on_unload` 控制资源 lifecycle：

```python
# krow_agent_sdk/protocols.py（v0.8 新增）

class BasePluginLifecycle(Protocol):
    """所有 Protocol（P1-P9）共享的可选 lifecycle mixin。"""

    def on_load(self, sdk_context: "SDKContext") -> None:
        """SDK build() 时调用一次；plugin 在此初始化资源。

        典型用例：
        - 启动 MCP server 连接（不能塞 __init__；entry_points discovery 时不应连）
        - 校验外部依赖（CAD SDK 是否安装）
        - 加载领域配置 / 模型权重

        sdk_context 提供：
        - sdk_context.event_bus: EventBusReader（可订阅）
        - sdk_context.project_root: Path
        - sdk_context.logger: logging.Logger（plugin_id 自动绑定）
        """
        ...

    def on_unload(self) -> None:
        """SDK shutdown() 时调用一次；plugin 在此释放资源（关连接 / 释放句柄）。"""
        ...
```

**SDK 内部加载顺序**（Step 1 PR S1.1 落地）：

```
build() 时：
  for plugin in discovered_plugins:
    1. validate_protocol_implementation(plugin, protocol)  # A1 / R26
    2. if hasattr(plugin, "on_load"): plugin.on_load(sdk_context)
    3. register to ToolManager / ACTLoader / GateChain / EventBus / ...

shutdown() 时（反向）：
  for plugin in reversed(loaded_plugins):
    1. unregister from ToolManager / ...
    2. if hasattr(plugin, "on_unload"): plugin.on_unload()
```

`on_load` / `on_unload` 都是 **OPTIONAL**——老 plugin 不实现也不破契约。

### §6.1 AgentBuilder 链式 API

**SDK 唯一入口**：`from krow_agent_sdk import AgentBuilder`（详 §6.0 import 路径双轨表）

```python
class AgentBuilder:
    """链式构造 Agent 的入口。
    
    内部包装现有 modules/agent/v3_bootstrap.py:bootstrap_v3()，
    对外提供稳定 API；内部实现可自由 refactor。
    """
    
    # ────── 必须项（第 8 轮辩论修订：API key 替换虚构的 KrowAuthSession）──────

    def with_krow_api_key(self, api_key: str) -> "AgentBuilder":
        """强绑 krow cloud API key 认证（必须项）。

        api_key 格式：`sk-user-xxx`（在 https://krow.cn API 密钥页面创建）

        内部走 `https://api.krow.cn/v1` + `Authorization: Bearer <api_key>`，
        与 OpenAI API 完全兼容（详 §3）。

        参数校验：
        - 格式不对（非 `sk-` 前缀）→ 立即抛 `InvalidKrowAPIKeyError`（fail-loud）
        - 不传且环境变量 `KROW_API_KEY` 未设 → `build()` 抛 `MissingKrowAPIKeyError`
        """
        ...

    @classmethod
    def from_env(cls) -> "AgentBuilder":
        """快捷启动：从 `KROW_API_KEY` 环境变量读 api_key + `KROW_PROJECT_ROOT`（可选）读项目根。

        等价于：

            builder = AgentBuilder().with_krow_api_key(os.environ["KROW_API_KEY"])
            if "KROW_PROJECT_ROOT" in os.environ:
                builder = builder.with_project_root(os.environ["KROW_PROJECT_ROOT"])

        推荐用于生产部署 / CI / Docker 容器（避免 api_key 硬编码）。
        """
        ...

    def with_project_root(self, path: str | Path) -> "AgentBuilder":
        """强制声明 project root。

        不传 build() 时 raise MissingProjectRootError（fail-loud，详 §7）。
        """
        ...
    
    # ────── 可选项 ──────

    def with_budget(self, budget: "BudgetSpec") -> "AgentBuilder":
        """配置预算（macro/micro/adapt/replan/watchdog 全配置；详 §5.12 + 下方 BudgetSpec 完整 dataclass）。"""
        ...

    def with_http_gateway(
        self,
        port: int = 8765,
        auth_token: Optional[str] = None,
        bind_host: str = "127.0.0.1",
        enable: bool = False,
    ) -> "AgentBuilder":
        """启动 KrowService FastAPI gateway（默认不启动）。

        启用后外部 UI（Web / Electron / Slack bot 等跨进程客户端）可走 HTTP/WebSocket/SSE 调 SDK Agent：
        - POST /api/v1/agent/execute
        - GET  /api/v1/agent/stream/{task_id}（SSE 进度流）
        - WS   /ws/events（EventBus 全部 stable topic 流）
        - GET/POST /api/v1/files/{tree,read,upload,...}
        - GET  /api/v1/sessions/*

        feature flag KROW_SDK_HTTP_GATEWAY 控制；嵌入式同进程 UI 不需要启动。
        """
        ...

    def with_acts_from_entry_points(self, group: str = "krow.acts") -> "AgentBuilder":
        """自动发现外部 ACT plugin（默认开）。"""
        ...
    
    def with_tools_from_entry_points(self, group: str = "krow.tools") -> "AgentBuilder":
        """自动发现外部 Tool plugin（默认开）。"""
        ...
    
    def with_hints_from_entry_points(self, group: str = "krow.hints") -> "AgentBuilder":
        """自动发现外部 Hint plugin（默认开）。"""
        ...
    
    def with_gates_from_entry_points(self, group: str = "krow.gates") -> "AgentBuilder":
        """自动发现外部 Gate plugin（默认开）。"""
        ...
    
    def with_event_listeners_from_entry_points(self, group: str = "krow.event_listeners") -> "AgentBuilder":
        """自动发现外部 EventListener plugin（默认开）。"""
        ...
    
    def with_observability_from_entry_points(self, group: str = "krow.observability") -> "AgentBuilder":
        """自动发现外部 Observability plugin（默认开）。"""
        ...
    
    def with_mcp_servers_from_entry_points(self, group: str = "krow.mcp_servers") -> "AgentBuilder":
        """自动发现外部 MCP server plugin（默认开）。"""
        ...
    
    def with_security_policies_from_entry_points(self, group: str = "krow.security_policies") -> "AgentBuilder":
        """自动发现外部 SecurityPolicy plugin（默认开）。"""
        ...

    def with_domain_packs_from_entry_points(self, group: str = "krow.domain_packs") -> "AgentBuilder":
        """自动发现外部 DomainPackPlugin（P9 语法糖）。

        P9 内部展开为 HintPlugin + ToolPlugin + GatePlugin + supplementary extended.md 注册。
        feature flag KROW_PLUGIN_P9_DOMAIN_PACK 控制启用。
        """
        ...

    def with_visual_adapter_plugins_from_entry_points(self, group: str = "krow.visual_adapter") -> "AgentBuilder":
        """自动发现外部 VisualAdapter（不开 Plugin Protocol，函数式 OCP 扩展）。

        内部调用 modules/agent/visual/visual_grounding_tools.py:register_visual_adapter(ext, adapter)
        让外部 plugin 加自己的格式适配器（如 .step / .iges CAD 格式 / .mol / .fasta 等）。
        feature flag KROW_PLUGIN_VISUAL_ADAPTERS 控制启用。
        """
        ...

    # ────── Native ACT 选择（v0.8 顶级 review D8 修订：明确叠加语义）──────

    def with_native_acts(self, names: list[str]) -> "AgentBuilder":
        """显式选择启用哪些 native ACT（默认全部 14 个）。

        v0.8 顶级 review D8：with_native_acts 与 with_acts_from_entry_points **是叠加语义**：
        - with_native_acts(names) 控制 14 个 native ACT 的启用子集（不传时默认全部启用）
        - with_acts_from_entry_points(group) 控制外部 plugin ACT 的发现加载
        - 最终启用的 ACT 集 = native_acts(选定子集) ∪ entry_points 发现的 plugin ACT
        - 二者**独立**，调用顺序无关；命名空间冲突 fail-loud（plugin ACT 必须 <plugin_id>. 前缀）

        参考 §4.1 表选 ACT name。
        """
        ...

    def with_krow_cloud_features(self, features: list["KrowCloudFeature"]) -> "AgentBuilder":
        """选择启用 krow_cloud ACT 的哪些子能力（v0.8 顶级 review A4 修订：用 enum 替代 list[str] 防 Hyrum's Law）。

        @dataclass(frozen=True)
        class KrowCloudFeature(str, Enum):
            IMAGE_GEN = "image_gen"
            OCR = "ocr"
            VISION = "vision"
            # ...
        """
        ...

    # ────── 直接注入（高级，慎用）──────

    def with_act_plugin(self, plugin: ACTPlugin) -> "AgentBuilder":
        """直接注册 ACTPlugin 实例（不走 entry_points）。"""
        ...

    def with_tool_plugin(self, plugin: ToolPlugin) -> "AgentBuilder":
        """直接注册 ToolPlugin 实例。"""
        ...

    # ... 其他 with_<X>_plugin() 类似

    # ────── BuilderConfig 替代路径（v0.8 顶级 review A5 新增：防 god class 蔓延） ──────

    @classmethod
    def from_config(cls, config: "BuilderConfig") -> "AgentBuilder":
        """从一份 BuilderConfig dataclass 一次性构造 builder（推荐 production 用）。

        优势：
        - 链式 with_* 方法越加越胖（god class antipattern）→ BuilderConfig 是 dataclass，加新 feature 只加字段
        - 测试时 mock 一个配置只写 1 个 dataclass，不需要 30 个 stub
        - 配置可序列化（YAML/JSON）→ 部署时直接读配置文件

        与链式 API 等价：
            builder = AgentBuilder.from_config(BuilderConfig(api_key="sk-user-x", ...))
            # 等价于
            builder = AgentBuilder().with_krow_api_key("sk-user-x").with_project_root(...)...
        """
        ...

    # ────── 构造（v0.8 顶级 review A6 修订：build() 时连接验证） ──────

    def build(self, *, validate_connection: bool = True) -> "Agent":
        """构造 Agent；缺失必须项 → fail-loud。

        v0.8 顶级 review A6：validate_connection（默认 True）启用时 build() 内部跑：
          1. GET https://api.krow.cn/v1/models 验证 api_key 可用（极轻量）
          2. project_root 写权限测试（写一个 .krow_lock 文件然后删除）
          3. 加载的 plugin 走 _protocol_validator.validate_protocol_implementation 校验签名（A1 / R26）

        任一失败 → 立即 raise（不延迟到 first run）：
          - api_key 401 → KrowAPIKeyInvalidError
          - api_key 402 → KrowQuotaExceededError
          - project_root 不可写 → MissingProjectRootError 子类 ProjectRootNotWritableError
          - plugin 签名错 → PluginSignatureMismatchError

        dev/test 走 validate_connection=False 跳过（如 LLMReplayStore 测试 / offline dev）：
          builder.build(validate_connection=False)

        feature flag KROW_SDK_BUILD_VALIDATE_CONNECTION（默认 1）控制全局缺省。
        """
        ...


# BudgetSpec 完整 dataclass（第 7 轮辩论扩展，覆盖 4 处分散预算 SSOT 的全部 plugin 可配置项）
@dataclass
class BudgetSpec:
    """完整预算配置 dataclass。详细预算覆盖度声明见 §5.12。"""

    # ─── Macro 任务级（TaskBudget）───
    target_walltime_s: int = 600                  # 目标墙钟（达标后触发 budget.target_reached）
    max_walltime_s: int = 1800                    # 硬墙钟上限（HARD_CAP_MS）
    max_total_llm_calls: int = 120                # 全任务 LLM 调用次数上限（无 token-level budget；详 §5.12）

    # ─── Adapt 扩容（_handle_adapt_budget_extension）───
    max_adapt_extensions: int = 3                 # adapt 最多扩容次数
    adapt_extension_step_ms: int = 300_000        # 每次 +5 min（_ADAPT_EXTENSION_MAX_MS 默认）
    adapt_dynamic_cap_strategy: Literal["read_write", "absolute", "off"] = "read_write"
                                                  # "read_write": read_time + write_time + 600s overhead 估算
                                                  # "absolute": 直接用 absolute_max_cap_ms
                                                  # "off": 不动态扩，撞 max_walltime_s 即停
    absolute_max_cap_ms: int = 7_200_000          # ABSOLUTE_MAX_CAP_MS 硬顶 2 小时

    # ─── Replan 配置 ───
    max_replans: int = 3

    # ─── Micro ReACT（ReACTConfig，独立于 macro，详 §5.12）───
    micro_max_iterations: int = 8                 # 单 micro ReACT 步迭代上限
    micro_max_time_ms: int = 180_000              # 单 micro ReACT 步墙钟上限（3 min）
    micro_max_thinking_s: int = 30                # 流式 thinking 单段上限（react.thinking_timeout）

    # ─── Watchdog（AgentV3 墙钟监控）───
    enable_grace_conclude: bool = True            # 撞 max_walltime_s 后是否启用 grace conclude
    grace_walltime_extra_s: int = 60              # grace 额外时间窗口


# build() 返回的 Agent 对象
class Agent:
    def run(
        self,
        user_input: str,
        *,
        context: dict | None = None,
        session_id: str | None = None,
        stop_event: Event | None = None,
        # 第 7 轮辩论：UI 通信 callback 直接透传 AgentV3 现有 5 个 callback
        on_progress: Callable[[str, dict], None] | None = None,
        on_todo_created: Callable[[list], None] | None = None,
        on_todo_update: Callable[[dict], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        on_report: Callable[[dict], None] | None = None,
    ) -> "AgentResult":
        """同步执行 agent。callback 与 EventBus 并行（callback 是 AgentV3 现有快路径，EventBus 是统一 pub-sub）。"""
        ...

    async def arun(self, *args, **kwargs) -> "AgentResult":
        """异步执行 agent。"""
        ...

    def cancel(self) -> None:
        """主动取消（与 stop_event 并行；cancel() 设置 _cancelled 标志）。"""
        ...

    @property
    def event_bus(self) -> "EventBusReader":
        """暴露**只读** EventBus reader 供同进程 UI 订阅 stable topic 子集（详 §5.5 / §6.5）。

        v0.8 顶级 review A10 修订：从暴露完整 EventBus → 暴露 EventBusReader 只读 facade。
        防 Hyrum's Law（"任何可观察行为都会被某 user 依赖"）：
        - 老接口 `agent.event_bus.publish(...)` 会让 plugin 主动发事件污染主流程
        - 老接口 `agent.event_bus._subscribers` 会让 plugin 依赖内部状态，主仓 refactor 即破

        EventBusReader 仅暴露：
        - subscribe(topic, handler) -> Token
        - unsubscribe(token)
        - iter_recent(topic_pattern, n=100) -> Iterator[Event]（最近 N 条只读）
        不暴露：publish / 内部状态 / 任何可写方法。
        """
        ...

    def shutdown(self) -> None:
        """关闭 agent + 清理 plugin（unsubscribe / unregister / call plugin.on_unload() 等）。"""
        ...


# v0.8 顶级 review A10 新增：EventBus 只读 facade
class EventBusReader:
    """SDK 暴露给 plugin / UI 的 EventBus 只读视图。

    设计目的：
    - 隔离 modules/events/bus.py:EventBus 内部实现（防 Hyrum's Law）
    - 主仓未来 refactor EventBus 内部不影响外部
    - plugin 只能"读 + 订阅"，不能"写 + 发事件"（保 EventBus 是内核单向 pub-sub）

    plugin 想发布事件 → 应该走 EventBus，但通过 P5 EventListenerPlugin 的 listener 内部副作用，
    或走 P6 ObservabilityPlugin 自己的 sink，**不**通过 SDK 反向 publish。
    """

    def subscribe(self, topic: str, handler: Callable[["Event"], None]) -> "Token":
        """订阅一个稳定 topic（详 §5.5 表）。返回 token 用于 unsubscribe。"""
        ...

    def unsubscribe(self, token: "Token") -> None:
        """注销订阅。"""
        ...

    def iter_recent(self, topic_pattern: str, n: int = 100) -> Iterator["Event"]:
        """读最近 N 条事件（用于 UI debug / 慢启动 backfill）。只读快照，不影响 EventBus 状态。"""
        ...


# v0.8 顶级 review A5 新增：BuilderConfig dataclass（替代部分链式 with_*）
@dataclass
class BuilderConfig:
    """SDK 一次性配置 dataclass。AgentBuilder.from_config(config) 是推荐 production 路径。

    优势：
    - 配置可序列化（YAML/JSON），部署时直接读配置文件
    - 测试 mock 简单（只 mock 一个 dataclass）
    - 防 AgentBuilder god class 蔓延（链式 with_* 已 16 个，未来加 feature 只加字段不加方法）
    """
    api_key: str                                # 必需（替换 with_krow_api_key）
    project_root: Path                          # 必需（替换 with_project_root）
    budget: Optional[BudgetSpec] = None         # 可选（替换 with_budget）
    http_gateway: Optional["HTTPGatewayConfig"] = None  # 可选（替换 with_http_gateway）
    plugin_loaders: "PluginLoaders" = field(default_factory=lambda: PluginLoaders())
    native_acts: Optional[list[str]] = None     # None = 全部 14 个；list = 显式子集
    krow_cloud_features: Optional[list["KrowCloudFeature"]] = None  # 注意 enum 不是 str（A4）
    validate_connection_on_build: bool = True   # 替换 build(validate_connection=...)


@dataclass
class HTTPGatewayConfig:
    port: int = 8765
    auth_token: Optional[str] = None
    bind_host: str = "127.0.0.1"
    enable: bool = False


@dataclass
class PluginLoaders:
    """每个 Protocol 的加载策略（True=从 entry_points 自动发现；False=禁用；List=显式列表覆盖）。"""
    acts: bool | list[ACTPlugin] = True                # P1
    tools: bool | list[ToolPlugin] = True              # P2
    hints: bool | list[HintPlugin] = True              # P3
    gates: bool | list[GatePlugin] = True              # P4
    event_listeners: bool | list[EventListenerPlugin] = True   # P5
    observability: bool | list[ObservabilityPlugin] = True     # P6
    mcp_servers: bool | list[MCPServerPlugin] = False  # P7 experimental，default off（A2）
    security_policies: bool | list[SecurityPlugin] = False     # P8 experimental，default off
    domain_packs: bool | list[DomainPackPlugin] = False        # P9 experimental，default off
    visual_adapters: bool = True                       # 函数式 OCP 不是 Protocol
```

### §6.2 默认行为

不调任何 `with_*_from_entry_points()` 时，SDK 默认**全部启用**：

```python
# 等价于：
agent = (
    AgentBuilder()
    .with_krow_api_key("sk-user-xxx")  # 或 AgentBuilder.from_env() 读 KROW_API_KEY
    .with_project_root("/data/cad")
    # 以下默认开（需要时显式 .with_*(False) 关闭）
    .with_acts_from_entry_points()
    .with_tools_from_entry_points()
    .with_hints_from_entry_points()
    .with_gates_from_entry_points()
    .with_event_listeners_from_entry_points()
    .with_observability_from_entry_points()
    .with_mcp_servers_from_entry_points()
    .with_security_policies_from_entry_points()
    .with_domain_packs_from_entry_points()       # P9 默认开（feature flag KROW_PLUGIN_P9_DOMAIN_PACK 控制）
    .with_visual_adapters_from_entry_points()    # 视觉格式适配器默认开
    .with_native_acts(ALL_14_NATIVE_ACTS)  # 默认全开
    .build()
)
```

### §6.3 完整 hello-world 外部 plugin 示例

外部团队的 pip 包结构（独立仓库）：

```
industrial-design-agent/
├── pyproject.toml
├── industrial_design_pkg/
│   ├── __init__.py        # entry_points 实现入口
│   ├── acts/              # 自定义 ACT 目录
│   │   └── cad_designer/
│   │       ├── __act__.yaml
│   │       └── extended.md
│   ├── tools.py           # 自定义工具
│   ├── gates.py           # 自定义 ConcludeGuard Gate
│   ├── hints.py           # 自定义 hint
│   └── security.py        # 自定义安全策略
└── tests/
    └── test_cad_e2e.py
```

`pyproject.toml`：

```toml
[project]
name = "industrial-design-agent"
version = "0.1.0"
dependencies = ["krow-agent-sdk>=2.0,<3.0"]

[project.entry-points."krow.acts"]
cad_designer = "industrial_design_pkg:get_act_plugin"

[project.entry-points."krow.tools"]
cad_tools = "industrial_design_pkg.tools:get_tool_plugin"

[project.entry-points."krow.gates"]
mech_constraints = "industrial_design_pkg.gates:get_gate_plugin"

[project.entry-points."krow.hints"]
unit_metric_hint = "industrial_design_pkg.hints:get_hint_plugin"

[project.entry-points."krow.security_policies"]
cad_security = "industrial_design_pkg.security:get_security_plugin"
```

`industrial_design_pkg/__init__.py`：

```python
from pathlib import Path
from krow_agent_sdk.protocols import ACTPlugin

class IndustrialDesignACTs:
    plugin_id = "acme.industrial_design"  # 双段 "<org>.<plugin_name>"
    
    def get_act_root(self) -> Path:
        return Path(__file__).parent / "acts"
    
    def get_act_names(self) -> list[str]:
        return ["cad_designer"]

def get_act_plugin() -> ACTPlugin:
    return IndustrialDesignACTs()
```

外部团队的启动脚本（**第 8 轮辩论修订：API key 模式**）：

```python
import os
from krow_agent_sdk import AgentBuilder, BudgetSpec

# 方式 A：从环境变量启动（推荐生产/CI）
agent = (
    AgentBuilder.from_env()  # 读 KROW_API_KEY 环境变量
    .with_project_root("/data/cad_project")
    .with_budget(BudgetSpec(target_walltime_s=600, max_walltime_s=1800))
    .build()
)

# 方式 B：显式传 api_key（适合脚本调试）
agent = (
    AgentBuilder()
    .with_krow_api_key("sk-user-xxxxxxxxxxxxxxxx")
    .with_project_root("/data/cad_project")
    .with_budget(BudgetSpec(target_walltime_s=600, max_walltime_s=1800))
    .build()  # 自动从 entry_points 加载所有 industrial_design_pkg 的 plugin
)

result = agent.run("帮我设计一个减速箱齿轮组，模数 m=2，齿数 z=20")
print(result.final_output)
```

环境变量约定（`KROW_API_KEY` SSOT）：

```bash
# .env 或 docker-compose.yml 或 K8s Secret
export KROW_API_KEY="sk-user-xxxxxxxxxxxxxxxx"      # 必需；在 https://krow.cn 控制台创建
export KROW_PROJECT_ROOT="/data/myproject"          # 可选；不传需 .with_project_root() 显式
```

整套接入到跑通**目标 ≤ 30 分钟**（含 LLM 调用）。

### §6.4 视觉质检 SDK 用法（第 6 轮辩论：部分暴露 + 不开 Protocol）

外部 plugin 团队做视觉质检（CAD 渲染输出校验、生物论文图片校验、化学结构图校验等）的两条暴露路径：

#### §6.4.1 直接调用 visual_inspect 函数式 API

```python
from krow_agent_sdk.visual import visual_inspect

# 在 plugin 自己的工具 handler 里调用
def cad_render_and_verify_handler(args):
    output_path = render_cad_to_pptx(args["cad_file"])

    # 调 SDK 视觉质检（内部走 VisualGroundingService → chat_vision VLM）
    inspect_result = visual_inspect(
        file_path=str(output_path),
        mode="verify",  # "verify" / "analyze"
        page_index=-1,
        expectation="CAD 双视图导出：主视图 + 俯视图齐全；尺寸标注无 placeholder；线型符合国标",
    )

    return {
        "success": inspect_result.success,
        "issues": inspect_result.issues,
        "delta": inspect_result.delta_context,
    }
```

`visual_inspect` 内部自动：
- 走 `KrowLLMProvider.chat_vision` VLM（强绑 krow cloud auth/billing，§3 一致）
- 通过 BudgetController 计入 token 成本
- 自动识别格式（pdf / pptx / docx / png / jpg / step / iges / mol / fasta 等，含外部 plugin 通过 §6.4.2 注册的格式）

#### §6.4.2 给外部 plugin 加新格式适配器（OCP 扩展）

外部 plugin 让 `visual_inspect` 支持自己的领域格式（如 `.step` / `.iges` / `.mol` / `.fasta` 等），通过 entry_points 注册（v0.9.x 实际 group 名是 **单数** `krow.visual_adapter`，与 `modules/agent/sdk/entry_points.py:GROUP_VISUAL_ADAPTER` SSOT 一致）：

```toml
# 外部 plugin 的 pyproject.toml
[project.entry-points."krow.visual_adapter"]
step_adapter_plugin = "industrial_design_pkg.visual:STEPVisualAdapterPlugin"
mol_adapter_plugin = "research_agent_pkg.visual:MOLVisualAdapterPlugin"
```

```python
# industrial_design_pkg/visual.py
from krow_agent_sdk.visual import VisualAdapter
from krow_agent_sdk.experimental.protocols import VisualAdapterPlugin

class STEPAdapter(VisualAdapter):
    """CAD .step 文件渲染适配器（实现 5 个抽象方法 + 可选 RENDER_SOURCE）。

    详 ``modules/agent/visual/protocol.py:VisualAdapter`` 契约。
    """
    RENDER_SOURCE = "step-cad-renderer"        # 可选：透传给 VLM preamble
    RENDER_FIDELITY_CLASS = "geometry_match"   # 可选：默认 geometry_match

    def supports(self, ext: str) -> bool:
        return ext.lower() in {".step", ".stp", ".iges"}

    def open(self, source, **kwargs) -> None:
        # 用 CAD SDK 加载 STEP 文件
        ...

    def close(self) -> None:
        # 释放 CAD SDK 资源
        ...

    def render(self, page_index: int, width: int = 960, height: int = 540) -> bytes:
        # 渲染指定页（STEP 单页 = 单视角）为 PNG bytes 给 VLM
        ...

    def inventory(self, page_index: int) -> list:
        # 返回 ElementEntry 列表（element id / role / bbox 等）
        ...

    def page_count(self) -> int:
        return 1


class STEPVisualAdapterPlugin:
    """通过 ``VisualAdapterPlugin`` Protocol 暴露给 entry_points。"""
    plugin_id = "industrial-design-step"

    def get_visual_adapters(self) -> list[tuple[str, type]]:
        return [(".step", STEPAdapter), (".stp", STEPAdapter), (".iges", STEPAdapter)]
```

SDK 内部调 `modules/agent/visual/visual_grounding_tools.py:register_visual_adapter(ext, adapter)`（已是 OCP 函数）—— **不需要新 Plugin Protocol**，第 6 轮辩论决策。

#### §6.4.3 通过 verify_fix trait 获得"长超时 + companion 工具发现 + verify-fix 专用 prompt"闭环

外部 plugin 给自己的工具打 `traits=["verify_fix"]`，由 `ProgressiveExecutor` 自动启用 verify-fix 内核行为：

```python
# 外部 plugin 的 ToolPlugin
ToolDefinition(
    name="research.protein_structure_verify",
    description="校验蛋白质结构图与论文描述一致",
    handler=protein_structure_verify_handler,
    latency_class="cold",
    traits=["verify_fix", "VERIFY_FIX"],  # ← 自动获得 verify-fix 闭环
)
```

打了 `verify_fix` trait 的工具，`ProgressiveExecutor` 会自动：
- 提供更长执行超时（cold + verify-fix 标签合作）
- 自动发现可作为 fix 的 companion 工具（如同 plugin 注册的 `protein_structure_fix`）
- 注入 verify-fix 专用 system prompt（提醒 LLM 这是"先校验后修复"的闭环工具）

**不需要新 Plugin Protocol**——通过 P2 ToolPlugin 已有的 `traits` 字段即可（第 6 轮辩论决策）。

#### §6.4.4 反模式

| 反模式 | 替代 |
|---|---|
| 外部 plugin 自己写视觉质检工具（不用 visual_inspect）→ 重复造 VLM + 适配器轮子 | 调 `visual_inspect()` 函数式 API（§6.4.1） |
| 外部 plugin 自己 import openai 做 VLM | 走 SDK 注入的 `KrowLLMProvider.chat_vision`（§3 强绑 krow cloud） |
| 外部 plugin 想"修改" verify-fix 的 prompt / 超时策略 | 不允许：verify_fix 是 ProgressiveExecutor 内核行为；plugin 只能"打 trait 获得闭环"，不能改内核 |
| 外部 plugin 把超大图片直接发给 visual_inspect 不下采样 | VisualGroundingService 内部已有下采样 + token 预算检查；plugin 不需操心 |

### §6.5 UI 通信策略（嵌入式同进程 + 跨进程 HTTP/WS 双轨）

第 7 轮辩论决策：**双轨 + Builder 显式开 HTTP**。

#### §6.5.1 嵌入式同进程 UI（默认路径）

适用：Streamlit / Gradio / Tkinter / Qt embed / 命令行 / Jupyter 等单进程 Python UI。

```python
from krow_agent_sdk import AgentBuilder, BudgetSpec
from krow_agent_sdk.events import subscribe  # 进程内 EventBus 单例 facade

agent = (
    AgentBuilder.from_env()  # 第 8 轮辩论：API key 替换虚构的 KrowAuthSession
    .with_project_root("/data/myproject")
    .with_budget(BudgetSpec(target_walltime_s=600, max_walltime_s=1800))
    .build()
)

# 路径 1：直接订阅 EventBus stable topic 子集
def on_budget_extended(event):
    ui.show_toast(f"预算扩容: +{event.payload['extension_ms']/1000}s")

token1 = subscribe("budget.extended", on_budget_extended)
token2 = subscribe("agent.task_complete", lambda e: ui.show_done())

# 路径 2：直接传 callback 到 run()
result = agent.run(
    "帮我设计一个减速箱齿轮组",
    on_progress=lambda phase, data: ui.update_progress_bar(phase, data),
    on_thinking=lambda text: ui.append_chat_bubble(text),
    on_report=lambda report: ui.show_report(report),
    stop_event=ui.stop_signal,  # threading.Event；UI 点取消时 .set()
)

# 完成后清理
agent.shutdown()  # 自动 unsubscribe / unregister 所有 plugin
```

#### §6.5.2 跨进程 UI（Builder 显式开 HTTP/WS Gateway）

适用：Web 前端（React/Vue）/ Electron / Slack bot / 远程客户端等跨进程 UI。

```python
agent = (
    AgentBuilder.from_env()  # 第 8 轮辩论：API key 替换虚构的 KrowAuthSession
    .with_project_root("/data/myproject")
    .with_http_gateway(
        port=8765,
        auth_token="bearer-xyz",  # UI 走 Authorization header 鉴权（与 SDK 自身 KROW_API_KEY 不冲突）
        bind_host="127.0.0.1",
        enable=True,  # 显式开（feature flag KROW_SDK_HTTP_GATEWAY 全局兜底）
    )
    .build()
)

# 启动后 SDK 内部启 KrowService FastAPI server，外部 UI 走：
# - POST http://127.0.0.1:8765/api/v1/agent/execute  → 提交任务
# - GET  http://127.0.0.1:8765/api/v1/agent/stream/{task_id}  → SSE 进度流
# - WS   ws://127.0.0.1:8765/ws/events  → EventBus stable topic 全订阅
# - GET/POST http://127.0.0.1:8765/api/v1/files/*  → 文件管理
# - DELETE http://127.0.0.1:8765/api/v1/sessions/{id}  → 取消任务
```

#### §6.5.3 EventBus topic 稳定契约

**SDK 承诺稳定的 topic 子集**（详 §5.5 表）—— 外部 UI 只能订阅稳定子集；动态 topic 不在契约内。

#### §6.5.4 反模式

| 反模式 | 替代 |
|---|---|
| Web UI 直接 `import` `agent.event_bus` 跨进程 | EventBus 是**进程内单例**；走 `with_http_gateway()` 启 `/ws/events` WS |
| 同进程 UI 走 HTTP | 性能浪费；同进程走 callback / EventBus subscribe |
| 自己实现 IPC（ZeroMQ / Redis） | KrowService 现成 HTTP/WS 已够用，不要造重复轮子 |
| 外部 UI 假定全部 EventBus topic 都稳定 | 只用 SDK 承诺稳定子集；动态 topic 监听属"best-effort" |
| 复用 `tests/e2e_framework/{ui,web,tab}_probe.py` 给 Web UI | 那些是 PySide6 桌面绑定（`QWebEngineView` / `MainWindow.EditorTabs`），不能用于其他 UI 框架 |

### §6.6 SDK 数据访问 facade（`krow_agent_sdk.data` 只读模块）

第 7 轮辩论决策：**不开 Plugin Protocol，函数式只读 façade**（详 §5.10）。

```python
from krow_agent_sdk.data import (
    get_ontology_view,
    get_global_ontology,
    query_knowledge,
    recall_experiences,
    get_state_snapshot,
)

# 1. 读会话 ontology（包装 SessionOntologyStore.to_view()）
ontology_view = get_ontology_view()
hypotheses = ontology_view.get_hypotheses(min_confidence=0.7)

# 2. 读全局 ontology（强制 scope 隔离）
global_view = get_global_ontology(scope="current_project")
concepts = global_view.search_concepts("齿轮模数")

# 3. 查 knowledge（默认 layers=["L0","L1"]，不查 L2 防 Neo4j 高负载）
result = query_knowledge(
    query="齿轮强度公式",
    scope="current_project",
    layers=["L0", "L1"],
)

# 4. 经验记忆 recall
experiences = recall_experiences(
    query="减速箱设计",
    k=5,
    category="industrial_design",
)

# 5. agent 状态只读快照
snapshot = get_state_snapshot()
print(f"当前 state: {snapshot.current_state_id}")
print(f"父链: {snapshot.parent_chain}")
```

**反模式**：直接 `sqlite3.connect("agent_memory.db")` / 调内部 store write API（详 §5.10）。

### §6.7 SDK 诊断 facade（`krow_agent_sdk.diagnostics` 只读模块）

第 7 轮辩论决策：**不开 Plugin Protocol，read-only facade + Step 1 修补 turbo_diagnostics 接入**（详 §5.11）。

```python
from krow_agent_sdk.diagnostics import (
    get_snapshot,
    dump_state,
)

# 1. 取诊断快照（含 BudgetController state / TaskBudget / 当前 plan / 执行历史 / event log 最近 N 条）
snapshot = get_snapshot(agent)
print(f"Walltime used: {snapshot.task_budget.time_used_ms / 1000:.1f}s")
print(f"LLM calls: {snapshot.task_budget.llm_calls_used}/{snapshot.task_budget.max_total_llm_calls}")
print(f"Adapt extensions: {snapshot.task_budget.adapt_extensions_used}")

# 2. 完整 state dump（用于 bug report；自动过滤 secrets / token / 私密路径）
output_path = dump_state(agent, output_path="/tmp/krow_dump.json")
```

**反模式**：plugin 试图通过 dump_state 拿到 sqlite 内部数据（已过滤）；plugin 在 dump 函数内调 LLM"智能诊断"（System 1/2 边界）。



## §7 项目根目录策略

**用户决策**（第 3 轮辩论）：`force_explicit` —— 强制外部调 `with_project_root()`，不传 fail-loud。

### §7.1 fail-loud 入口

```python
# 1. 不传 with_project_root：
agent = AgentBuilder().with_krow_api_key("sk-user-xxx").build()
# → raises MissingProjectRootError(
#     "AgentBuilder.build() requires .with_project_root(path). "
#     "项目根目录是 native 工具（document_reader / pptx_editor 等）的 SSOT，必须显式声明。"
# )

# 2. 不传 with_krow_api_key 且无 KROW_API_KEY env：
agent = AgentBuilder().with_project_root("/data/foo").build()
# → raises MissingKrowAPIKeyError(
#     "AgentBuilder.build() requires .with_krow_api_key('sk-user-xxx') or env KROW_API_KEY. "
#     "API key 是 krow cloud 强绑认证的唯一路径，可在 https://krow.cn API 密钥页面创建。"
# )
```

### §7.2 兼容现有 `get_project_root()` 调用

`AgentBuilder.with_project_root(path)` 内部调用 `modules/utils/project_context.py:set_project_root(path)`，使 native ACT 工具透明使用：

| 调用方 | 兼容方式 |
|---|---|
| `modules/utils/project_context.py:get_project_root()` 返回 `Optional[Path]` | SDK 启动后总是返回 plugin 设的 path |
| native 工具（如 `read_file` / `pptx_render_page_svg`）依赖 `get_project_root()` | 透明工作 |
| Plugin 自己读项目根 | 走 `from krow_agent_sdk.context import get_project_root`（SDK facade，包装 `modules/utils/project_context.py`） |

### §7.3 多 plugin 共享 project root 的策略

| 场景 | 行为 |
|---|---|
| 同一 SDK 进程内有多个 plugin（如 cad + research 都加载） | **共享同一 project_root**（单 SDK = 单 agent = 单 project_root） |
| 外部团队需要"plugin 各自独立 root" | 不在 SDK 范围；外部启动多个 `AgentBuilder` 实例（各自 with_project_root），分别 run |
| Plugin 试图改 project_root | 通过 `SecurityPlugin` 的 `file_paths_allowed` 限制；SDK 不暴露 `set_project_root` 给 plugin |

### §7.4 路径规范

- 必须是绝对路径（`Path(...).is_absolute()` 检查 → fail-loud 否则）
- 必须存在或可创建（不存在时 SDK 自动 `mkdir(parents=True)`）
- 跨平台：win 用 `\` mac/linux 用 `/`，SDK 内部 `Path` 对象处理



## §8 5 顾问专家辩论

> 按 `AGENTS.md` (internal) §6.2.2 + §4.2.2 强制流程：5 个角色（TURBO / 架构 / 基础设施 / 可逆性 / 测试）每人 5-8 个具体论点 + 反对方应答 + 最终决策。

### §8.1 TURBO 顾问（System 1 fast/syntax + System 2 slow/semantic）

**核心立场**：plugin 协议必须严格区分"语法/确定性"和"语义/创意"，hint 不能替代 System 1 闸门。

**论点**：

1. **GatePlugin = System 1 闸门**：gate 返回 BLOCK 必须**物理闸住**（agent 真不让继续 conclude），不允许只发 warning hint。落地：`Gate.evaluate()` 返回 `GateDecision(verdict=BLOCK)` → `GateChain` 短路返回 BLOCK，executor 物理走 replan / fail。
2. **HintPlugin = System 2 软提示**：定位为"语义/创意类提示"。**红线**写明禁止用 hint 做"参数校验/错误防御/物理约束"——这种问题归 ToolPlugin 入口归一化（System 1）或 GatePlugin（System 1）。(`AGENTS.md` (internal) §0.1 PNG 旁路反模式 引证)
3. **ToolPlugin trait 声明 = System 1 数据**：`latency_class` 是确定性查表数据（给 `tool_priority_hint.py` 排序用），不是给 LLM 看的。
4. **ObservabilityPlugin 不许做语义判断**：trace/metrics/audit sink 是 System 1 数据出口；禁止 sink 内 `import openai` 调 LLM 做"智能告警"。
5. **EventListenerPlugin 必须区分同步/异步**：同步 listener 阻塞主流程必须严格 timeout（System 1 闸门），异步 listener 走 `BackgroundAgentTaskQueue.submit()`。
6. **System 2 工具不能吃 System 1 的活**：Plugin 加新工具时，"几何计算/颜色查表/精确数值"必须落 System 1；禁止 plugin 在工具内 `import openai`（CI 红线 contracts.yml deterministic-no-LLM 守门）。
7. **MCPServerPlugin 是确定性 RPC**：MCP 协议本身是 JSON-RPC（System 1）；server 内部决定 System 1 / System 2 是 server 自己的事，不在 SDK 协议层。
8. **SecurityPlugin MVP 降级是 System 1 数据流**：声明式权限清单 + 部分硬闸门 + 部分审计；强沙箱（subprocess 隔离）推到 Step 3。

**反对方应答**（"如果外部团队就是想做语义工具呢？"）：
- 答：System 2 工具走"调 LLM 的工具"形态，但仍然不让 plugin 自己 import 第三方 LLM SDK ——必须走 SDK 注入的 `LLMProviderManager.get_*_model()`，让 budget 计数 + krow cloud auth/billing 串联（与 §3 一致）。

**最终决策**：
- ✅ Protocol 设计与 TURBO 哲学一致
- ✅ §5 每个 Protocol Spec 内**明文写出"System 1 还是 System 2"标签**
- ✅ HintPlugin 红线在 §5.3 写明

---

### §8.2 架构原则顾问（SSOT / OCP / SRP / DRY）

**核心立场**：每个 Protocol 必须对应一个清晰 SSOT，且全仓唯一。

**论点**：

1. **SSOT 表新增行**：design doc 落地后，`AGENTS.md` (internal) §一 SSOT 表加：`SDK plugin protocols → modules/agent/sdk/protocols.py`。同步 §7.7 元规则文件独立 PR。
2. **OCP 检查**：8 个 Protocol 都是"加新实现 = 加新 plugin 包，不改 main repo"。✅ 满足。
3. **SRP 检查**：每个 Protocol 单一职责（详 §5）；无重叠。
4. **DRY 检查 1 — namespace 强制**：外部 ACT / 工具 / Gate / hint 的命名都加 `<plugin_id>.` 前缀，避免与 native 重名 → fail-loud。
5. **DRY 检查 2 — hint 内容**：HintPlugin 加新 hint 与 native hint 内容若重叠（DRY 闸门），走 `lint_act_hint.py` warning（已有）。
6. **SSOT 飘移防御**：`AgentBuilder` API（SDK 暴露）和 `v3_bootstrap.bootstrap_v3()`（内部）会不会变成 2 套 SSOT？决策：Builder 是 SDK 稳定 facade，**内部实现**复用 v3_bootstrap，不双写；contracts.yml 加契约测试守住 facade 与内部行为一致。
7. **LLM 调用 SSOT**：plugin 内调 LLM 必须走 `AGENTS.md` (internal) §infra-ssot-index.mdc §3 模板（`provider.generate(messages: List[ChatMessage])` + `llm_source_context()`），**不允许**自己 import httpx。
8. **现状反 SSOT 必修**（铁证 §0.3）：双 `ChatMessage`（`modules/ai/providers.py` vs `modules/ai/krow/provider.py`）必须 Step 1 修；`LLMSourceModule.CHAT` 重复赋值必须 Step 1 修。

**反对方应答**（"外部 plugin 不在 main repo CI，闸门怎么管？"）：
- 答：CI 守不住外部仓库，但 SDK 文档写明"重大反模式"+ 提供 contract test 模板让外部自查；plugin 注册时 SDK 内部检测 plugin 模块的 import 是否含 `httpx` / `openai` 给出 warning（弱守门）。

**最终决策**：
- ✅ 设计满足 SSOT/OCP/SRP/DRY
- ✅ design doc §5 写明 namespace 强制规则
- ✅ `AGENTS.md` (internal) §一 SSOT 表加 plugin protocols 行（落 §7.7 独立 PR，**本文档落地后下一个 PR**）
- ✅ Step 1 必修 ChatMessage 双轨 + LLMSourceModule 重复赋值 bug

---

### §8.3 基础设施顾问（不造重复轮子）

**核心立场**：每个 Protocol 必须复用现有基础设施，禁止新建"平行系统"。

**论点**：

1. **EventListenerPlugin → 走 `modules/events/` EventBus**，不新建 pub-sub。
2. **ObservabilityPlugin → 走 `modules/observability/` 现有 `MetricsRegistry` / `start_span` / `record_event`**；新建 `TraceSink` / `MetricsSink` / `AuditSink` ABC 是必需的薄封装（小工作量）。
3. **ToolPlugin → 走 `modules/tools/manager.py:ToolManager.register_tool`**，扩展 `_get_headless_disabled_tool_names` 已有的 OCP 注册模式（铁证 §0.2）。
4. **ACTPlugin → 走 `modules/agent/act/act_loader.py:ACTLoader`**（已支持 `acts_dir` 参数）+ `ACTManager.register_act`（已支持运行时注册）。Step 2 扩展 entry_points 自动发现。
5. **GatePlugin → 走 `modules/knowledge/conclude_guard_gates.py:GateChain.register`**（已是 OCP 链式）。
6. **MCPServerPlugin → 走 `modules/mcp/`**（已有 MCP 协议客户端）+ `modules/agent/mcp_registry.py`（已有注册中心）；本次扩展为支持"反向 server 注册"。
7. **LLM 调用 → 走 `modules/ai/providers.py:LLMProviderManager`**，强绑 krow cloud（与 §3 一致）。
8. **BackgroundTaskQueue → 直接复用 `modules/agent/background_task_queue.py:BackgroundAgentTaskQueue.submit()`** 公开 API，**不开 Plugin Protocol**（决策第 2 轮辩论：直接 SDK facade 暴露 submit）。

**反对方应答**（"现有基础设施可能不够开放，要不要先重构？"）：
- 答：Step 1 不重构基础设施，只在 sdk/ 子包**内部**写 facade 包装；Step 2 才动 ACTLoader / ToolManager / GateChain 加 entry_points 加载点（最小侵入式 OCP 扩展）。

**最终决策**：
- ✅ 不造重复轮子（铁证 §0.2 表）
- ⚠️ ObservabilityPlugin 新建 3 个 sink ABC（薄封装现有 API）
- ⚠️ HintPlugin 新建 `HintRegistry`（中等改造，§0.3 反插件化障碍）
- ⚠️ MCPServerPlugin 中等改造（反向 server 注册）

---

### §8.4 可逆性顾问（blast radius / revert / feature flag）

**核心立场**：任何对外承诺都不可逆，**先验证再承诺**。

**论点**：

1. **Step 1 完全可逆**：`modules/agent/sdk/` 子包内部 facade，不发布、不对外承诺、可随时删除。blast radius = main repo 内部代码。
2. **Step 2 部分可逆**：entry_points 加载机制一旦发布，外部包开始用就**不可下线**。必须有：
   - feature flag `KROW_ENABLE_PLUGIN_ENTRY_POINTS=1`（默认 off，1-2 sprint 观察期后转 default on）
   - SDK 版本协议（major 变更才 break）
   - deprecation 装饰器（`@deprecated_since("X.Y", removal="X+1.0")`）
3. **Protocol 一次性发 8 vs 分批发**：
   - 用户决策第 3 轮辩论：**一次性发 8 个**（Step 1 骨架 + Step 2 同批实现）
   - 风险：某个 Protocol 设计错了拖累全局 → 缓解：每个 Protocol 内部带 feature flag，可独立关闭
4. **每个 Step 独立 revert 路径**：
   - Step 1 revert：删 `modules/agent/sdk/` + 恢复 `app/` 层深 import
   - Step 2 revert：feature flag 关掉 → 行为退回 Step 1
   - Step 3 不在当前承诺范围
5. **breaking change 的逃生口**：每次 SDK 升级 major（如 1.x → 2.x），保留 1.x facade 6 个月，给外部 plugin 升级窗口期。
6. **风险登记**（详 §12）：
   - 风险 1：内部 refactor 把 facade 漂偏 → 缓解：契约测试 + Step 2 plugin 兼容性矩阵到 contracts.yml
   - 风险 2：外部 plugin crash 拖死 agent 进程 → 缓解：plugin 调用都包 `try/except` + EventBus 发布 `plugin.error.<plugin_id>` 事件 + audit log
   - 风险 3：entry_points 加载顺序敏感 → 缓解：plugin 注册时声明 priority（1-10），冲突时按 priority 排序 + 报告冲突
   - 风险 4：外部 plugin 滥用 LLM 烧 krow cloud 余额 → 缓解：BudgetController 已有限额，plugin 调 LLM 走 `record_llm_call()` 计入

**反对方应答**（"分批发会让外部团队等很久 → 用户为何选了一次性发 8 个？"）：
- 用户回答："**重资产一次性交付**"——MVP 阶段就要覆盖完整能力面，避免分批迁移带来的"plugin 接入半途等待"成本。但每个 Protocol 内部带 feature flag 兜底。

**最终决策**：
- ✅ Step 1/2 可逆，Step 3 不在当前承诺
- ✅ §9 路线图一次性发 8 个 Protocol（但每个有独立 feature flag）
- ✅ §10 详写 feature flag + deprecation + revert 路径

---

### §8.5 测试顾问（plugin 协议如何测）

**核心立场**：不让外部 plugin 重造测试基础设施轮子；plugin 自身必须有契约测试。

**论点**：

1. **每个 Protocol 配契约测试**：`tests/sdk/test_<plugin>_protocol_contract.py`：
   - fake plugin 注册（实现 Protocol）
   - 验证 hook 在正确时机被调用
   - 验证返回值被正确处理
   - 验证错误隔离（plugin 抛异常不拖死 agent）
2. **暴露测试 SDK** `krow_test_sdk` namespace（package = `tests/e2e_framework/` + `tests/support/` 的子集）：
   - `WorkbenchHarness` / `AgentProbe` / `EventTracer` / `waiters` / `LLMReplayStore`
   - 给外部 plugin 写 e2e 用，禁止他们重造（`AGENTS.md` (internal) §3.4 测试基础设施铁律）
3. **plugin 协议测试加到 contracts.yml**：每个 PR 跑契约测试，确保不破坏 plugin 契约（warning-only 起步，1 sprint 观察后转硬阻塞，`AGENTS.md` (internal) §十一 元教训）。
4. **真实 LLM E2E 模板**：`examples/cad-design-plugin/` + `examples/research-agent-plugin/` 给完整 e2e（用 `LLMReplayStore` + 真实 LLM nightly），让外部团队有 reference。
5. **plugin 自查工具**：SDK 内置 `krow-sdk validate-plugin <pkg>` CLI，外部 PR 前自查（namespace / trait / entry_points 命名 / 反模式如 import httpx 等）。
6. **跨平台 smoke**：plugin 协议契约测试加 `@pytest.mark.cross_platform_smoke`，win/mac/linux 矩阵都跑（外部 plugin 经常踩跨平台坑）。
7. **预期结果卡（`AGENTS.md` (internal) §4.1）**：写真实 LLM E2E 必须先写预期结果卡（多维断言 + 容差 + fail signals + perf 上限）。
8. **像素走查**：plugin 暴露 UI 元素时（如 PPTX 渲染输出）必须 baseline 比对 + 5% 容忍。

**反对方应答**（"测试 SDK 也对外暴露 → 又增加一份对外承诺"）：
- 答：测试 SDK 与生产 SDK 同版本号 + 同 deprecation 协议，不是新增承诺。且 `tests/e2e_framework/` 已有清晰内部边界，对外暴露是"既有能力打包"，不是"新建"。

**最终决策**：
- ✅ 测试 SDK 与生产 SDK 同步暴露（详 §11）
- ✅ §11 写测试 SDK 暴露策略
- ✅ §9 Step 2 包含 contracts.yml 加 plugin 契约测试



## §9 渐进路线图

> `AGENTS.md` (internal) §十一 元教训："**一次性'全量大改 + 硬闸门' = 假绿 + 反复 hotfix。任何新治理任务先建一份'渐进治理路线图'，warning-only 起步**"。
> 用户决策第 3 轮辩论：**紧凑排**（1 sprint Step 1 + 1-2 sprint Step 2），2-3 月内交付 MVP 8 Protocol。

### §9.1 Step 1：在 main repo 内画清边界（**1 sprint，零对外承诺**）

| PR | 标题 | 改动范围 | 估时 | blast radius |
|---|---|---|---|---|
| S1.1 | feat(sdk): 新建 modules/agent/sdk/ 子包 + 8 个 Protocol 定义骨架 | 新文件，零侵入 | 3d | 无（新文件） |
| S1.2 | feat(sdk): AgentBuilder 链式 API + with_project_root fail-loud + with_krow_api_key 强绑（第 8 轮辩论修订）| 新文件 + 内部复用 v3_bootstrap | 4d | 内部 |
| S1.3 | fix: 双 ChatMessage 合并到 modules/ai/providers.py SSOT + LLMSourceModule.CHAT 重复赋值 + LLMSourceModule.PLUGIN_<id> 命名空间 | 跨多文件 refactor | 3d | 中（LLM 调用全链路） |
| S1.4 | fix: v3_bootstrap.is_v3_available 返回方法对象 bug | 1 行 | 0.5d | 低 |
| S1.5a（**v0.8 顶级 review A13 拆 sub-PR**）| refactor(app): app/ 层只读 facade（`get_agent_v3()` 等懒导出迁移到 sdk facade，**不动调用方**） | sdk/__init__.py 暴露 facade 函数 | 1d | 低（仅薄封装） |
| S1.5b | refactor(app): app/ 层调用方按目录分批迁（每批 ≤ 5 文件，跨 `app/ui/` `app/services/` 等子目录） | app/ 层多文件 refactor | 5d × 6 批 = 30d | 中（每批独立 PR + 桌面 e2e 回归）|
| S1.5c | refactor(app): desktop UI e2e 全套回归 + cross_platform_smoke（win/mac/linux） | 测试 + 验证 | 5d | 中 |
| S1.6 | refactor: SemanticQueryService 改注入式（消除 app.container 跨层依赖） | semantic_query.py | 1d | 低 |
| S1.7 | feat(sdk): HintRegistry 抽象 + reasoning_preamble.py / tool_priority_hint.py 改造 | hint 注册中心新建 | 3d | 中 |
| S1.8 | feat(sdk): 新建 TraceSink / MetricsSink / AuditSink ABC + observability sink 列表分发 | observability 改造 | 2d | 低 |
| S1.9 | test(sdk): 8 个 Protocol 契约测试骨架（fake plugin + hook 时机验证） | tests/sdk/ 新目录 | 3d | 无 |
| S1.10 | docs: docs/sdk/plugin-architecture-design.md final + examples/hello-world-plugin/ demo（用内部 entry_points 模拟） | 新文件 | 3d | 无 |
| S1.11 | feat(sdk): P9 DomainPackPlugin Protocol 骨架 + `_domain_pack_expander` 骨架 + tests/sdk/test_domain_pack_protocol_contract.py | 新文件，零侵入 | 2d | 无（新文件） |
| S1.12 | feat(sdk): 仅暴露 krow_agent_sdk.diagnostics.{dump_state,get_snapshot} facade（**不接入 turbo_diagnostics v1**——第 8 轮辩论铁证：v1 已被 executor_recovery v2 替代，不应再动；详 §5.11 + §0.3 R20 修订） | 新建 sdk/diagnostics.py（薄封装 ProgressiveExecutor 状态读取） | 1.5d | 低（只读 facade，不改 executor） |
| S1.13 | fix: 核实并修复 micro/macro LLM 计数一致性（micro 内每次 LLM 调用是否计入 macro `record_llm_call`）+ 修 `ReACTEngine._effective_max_iterations` 与 while 条件不一致 + 补 unit test 守住 | react_engine.py + executor.py | 2d | 中（影响 budget 计数） |
| S1.14 | feat(sdk): krow_agent_sdk.data 只读 facade（get_ontology_view / get_global_ontology / query_knowledge / recall_experiences / get_state_snapshot）+ 启动期 plugin 模块 import 扫描 sqlite3 warning | 新文件 sdk/data.py | 3d | 低（薄封装） |
| S1.15 | feat(sdk): AgentBuilder.with_http_gateway 实现（薄封装 KrowService FastAPI 启停 + auth_token 注入 + bind_host 控制） | 新文件 sdk/http_gateway.py | 3d | 低（feature flag 默认 off） |
| S1.16 | feat(sdk): P4 GatePlugin phase 字段实现 + ReACTEngine.add_plugin_micro_guard 路由 + 12 类门控归属表契约测试 | sdk/gates.py + react_engine.py + tests/sdk/ | 2d | 低 |
| S1.17 | fix(auth): 实现 KrowAuthAdapter.set_api_key + get_user_info（修第 8 轮调研发现的 dead code）+ 接通 AuthService.\_login_with_api_key + KROW_API_KEY 环境变量识别 + AgentBuilder.with_krow_api_key + AgentBuilder.from_env classmethod + UsageTracker.record_usage 加 api_key_id 维度（如云端契约需要）+ remove design doc 虚构概念 KrowAuthSession + **build(validate_connection=True) 实现 GET /v1/models 验证（v0.8 review A6）** | krow_auth.py + service.py + sdk/auth.py + builder.py + usage_tracker.py | 4d | 中（认证主链路改造，需 nightly 真实 API key e2e 验证） |
| **S1.18（v0.8 review D1）**| feat(sdk): `modules/agent/sdk/__init__.py` 加 `sys.modules.setdefault("krow_agent_sdk", sys.modules[__name__])` alias，让外部团队 Day 1 用稳定 import 路径；同期把 design doc 内所有 `from krow_agent_sdk` import 在 examples/ 下能跑 | sdk/__init__.py | 0.5d | 低 |
| **S1.19（v0.8 review A1/R26）**| feat(sdk): 新建 `modules/agent/sdk/_protocol_validator.py:validate_protocol_implementation(plugin, protocol)`，用 `inspect.signature` + `typing.get_type_hints` 真实校验 plugin 方法签名 vs Protocol 定义；不匹配抛 `PluginSignatureMismatchError`；KROW_SDK_SIGNATURE_VALIDATION env var 控制；mvp_critical（P1/P2/P4）必启用，stable / experimental 渐进开 | sdk/_protocol_validator.py + builder.py 加载链 | 2d | 低（独立模块）|
| **S1.20（v0.8 review A2/A3）**| feat(sdk): 实施 §5.0 Protocol 优先级分层：`modules/agent/sdk/protocols/` (mvp_critical+stable) + `modules/agent/sdk/experimental/protocols/` (experimental P7/P8/P9) 两套 namespace；P9 import 从主 namespace 移到 experimental | sdk/protocols/ + sdk/experimental/ | 1d | 低（path 重组）|
| **S1.21（v0.8 review A10）**| feat(sdk): 新建 `EventBusReader` 只读 facade（subscribe/unsubscribe/iter_recent，无 publish/内部状态）；`Agent.event_bus` property 返回 EventBusReader 而非 EventBus；同进程 UI 示例改造 | sdk/events.py + sdk/builder.py | 1d | 低 |
| **S1.22（v0.8 review D5/D6）**| feat(sdk): BasePluginLifecycle mixin（on_load/on_unload OPTIONAL）+ `KROW_SDK_PLUGIN_ERROR_MODE` 环境变量（swallow/raise/quiet）+ swallow 模式自动 stderr log；与现有 plugin 加载链集成；契约测试 | sdk/lifecycle.py + sdk/error_handling.py + plugin loader 链 | 1.5d | 低 |
| **S1.23（v0.8 review A7/R27）**| fix(llm): 把 `LLMSourceModule` 从纯 enum 改为 `Union[BuiltinLLMSourceModule, str]`；引入 `make_plugin_source_module(plugin_id) -> str`；`llm_source_context()` ContextVar 兼容 str；audit log / UsageTracker 兼容；同期修 v0.7 R7 `LLMSourceModule.CHAT` 重复赋值 bug（与 S1.3 合并）| modules/ai/providers.py + sdk/llm.py + audit log | 1d | 低（与 S1.3 配套） |

**Step 1 退出标准**（**v0.8 顶级 review 修订**）：
- ✅ `modules/agent/sdk/` 暴露 mvp_critical（P1/P2/P4）+ stable（P3/P5/P6）共 6 个 Protocol 真实加载（A2 优先级分层）
- ✅ `modules/agent/sdk/experimental/protocols/` 暴露 experimental（P7/P8/P9）共 3 个 Protocol 骨架 + feature flag default off（A2）
- ✅ `app/` 层全部走 sdk facade（内部双跑 v3_bootstrap，外部不可见）— **S1.5a-c 拆 sub-PR 渐进迁移**（A13）
- ✅ `tests/sdk/` 契约测试全绿 + plugin signature validator（A1/R26）启动期检测
- ✅ `examples/hello-world-plugin/` 端到端跑通（含最小 ACT yaml + tools.py + extended.md 30 行骨架；D2）
- ✅ Step 1 中 §0.3 反插件化障碍**全部修复**（含 R20-R22 第 7 轮 + R23 第 8 轮 AuthService dead code + R26/R27 v0.8）
- ✅ `krow_agent_sdk.{data,diagnostics,events,visual,auth}` 5 个 facade 模块就位
- ✅ `AgentBuilder.with_http_gateway()` 可选启动 KrowService
- ✅ `AgentBuilder.with_krow_api_key()` + `AgentBuilder.from_env()` 可用，支持真实 sk-user-xxx 调用 api.krow.cn + `build(validate_connection=True)` 启动期连接验证（v0.8 A6）
- ✅ `Agent.event_bus` 暴露 `EventBusReader` 只读 facade（v0.8 A10）
- ✅ `KROW_SDK_PLUGIN_ERROR_MODE` / `KROW_SDK_BUILD_VALIDATE_CONNECTION` / `KROW_SDK_SIGNATURE_VALIDATION` env vars 落地（v0.8 D6/A6/A1）
- ✅ `LLMSourceModule` 从 enum 改为 `Union[BuiltinLLMSourceModule, str]`，plugin 用 `make_plugin_source_module(plugin_id)` 字符串命名空间（v0.8 A7/R27）
- ✅ `from krow_agent_sdk import AgentBuilder` alias 让 Day 1 用稳定路径（v0.8 D1）
- ✅ P4 GatePlugin phase 字段 + 12 类门控归属表契约测试全绿
- ✅ 不发布 PyPI、不对外承诺

**Step 1 总估时（v0.8 修订）**：~52-78 天 ≈ 10-15 周（2.5-4 sprint，**比 v0.7 长**），主要变化：
- v0.7 估时 44d → v0.8 修订 52-78d
- S1.5 拆为 S1.5a/b/c 三个 sub-PR：4d → 1d + 30d + 5d = 36d（A13 实事求是估算 desktop UI 影响）
- **新增 6 个 v0.8 review PR**：S1.18(0.5d) + S1.19(2d) + S1.20(1d) + S1.21(1d) + S1.22(1.5d) + S1.23(1d) = 7d
- 总计：原 44d - S1.5 4d + S1.5 拆出来 36d + 新增 7d = 83d 上限；若 S1.5b 各批并行可压到 50-60d 下限

**v0.8 元教训**：v0.7 估的 44d 是对 S1.5 blast radius 的低估（"refactor app/ 层全部走 sdk facade" 实际涉及 30+ 文件 + desktop UI e2e）；架构师 review 的"实事求是估算 + 拆 sub-PR"是必要的。

### §9.2 Step 2：entry_points 真实加载机制（**1-2 sprint，灰度对外**）

| PR | 标题 | 改动范围 | 估时 | blast radius |
|---|---|---|---|---|
| S2.1 | feat(sdk): ACTLoader 支持 importlib.metadata.entry_points("krow.acts") 发现外部 ACT 包 + namespace 改造（砍 ext_ 前缀） | act_loader.py + 兼容 | 4d | 中 |
| S2.2 | feat(sdk): ToolManager 支持 entry_points("krow.tools") 注册外部工具 + headless_disabled 自声明 | tools/manager.py | 4d | 中 |
| S2.3 | feat(sdk): GateChain.add_plugin_gate + entry_points("krow.gates") | conclude_guard | 2d | 低 |
| S2.4 | feat(sdk): EventListenerPlugin 加载 + try/except 隔离 + plugin.error.* 事件 | events/bus.py + sdk | 2d | 低 |
| S2.5 | feat(sdk): ObservabilityPlugin 加载 + sink 列表分发到 plugin sink | observability | 2d | 低 |
| S2.6 | feat(sdk): HintPlugin 加载 + HintRegistry entry_points 接入 | sdk/hint_registry | 2d | 低 |
| S2.7 | feat(sdk): MCPServerPlugin 加载 + 反向 server 注册 + 工具自动注入 ToolManager | modules/mcp/ + sdk/ | 5d | 中 |
| S2.8 | feat(sdk): SecurityPlugin 加载 + SandboxValidator 集成到 ToolManager 工具调用前置 hook | sdk/security + tools/manager | 4d | 中 |
| S2.9 | feat(sdk): feature flag KROW_ENABLE_PLUGIN_ENTRY_POINTS=1 + deprecation 装饰器 | sdk/ | 2d | 低 |
| S2.10 | feat(sdk): krow_test_sdk namespace 暴露 e2e_framework + LLMReplayStore | tests/ → krow_test_sdk/ | 3d | 低 |
| S2.11 | feat(sdk): krow-sdk CLI（validate-plugin / list-plugins / etc.） | sdk/cli.py | 3d | 低 |
| S2.12 | docs: examples/cad-design-plugin/ + examples/research-agent-plugin/（独立外部仓 demo） | 新仓 / examples/ 目录 | 6d | 无 |
| S2.13 | ci: contracts.yml 加 plugin 契约测试 + cross_platform_smoke + plugin 兼容性矩阵 | .github/workflows/ | 2d | 无 |
| S2.14 | feat(sdk): ACTLoader.register_extended_md_supplement + 内存合并加载（priority 排序）+ 4000 字符上限 + prompt 注入扫描 | act_loader.py | 4d | 中（影响所有 native ACT prompt 生成） |
| S2.15 | feat(sdk): P9 DomainPackPlugin entry_points 加载 + `_domain_pack_expander` 真实展开（hint/tool/gate/supplement）+ feature flag KROW_PLUGIN_P9_DOMAIN_PACK | sdk/_domain_pack_expander.py | 4d | 中 |
| S2.16 | feat(sdk): visual_adapter entry_points("krow.visual_adapter") 加载（薄封装 register_visual_adapter）+ feature flag KROW_ENABLE_PLUGIN_ENTRY_POINTS | sdk/visual_loader.py | 1d | 低 |

**Step 2 退出标准**：
- ✅ 1-2 个真实外部 plugin 包（cad-design / research-agent demo）端到端跑通（含 P9 DomainPack）
- ✅ feature flag default off → 1 个 sprint 观察期 → 转 default on
- ✅ contracts.yml plugin 契约测试全绿（含 P9 + visual_adapter）
- ✅ 跨平台 smoke 全绿（win/mac/linux）
- ✅ `AGENTS.md` (internal) 加 plugin 开发指南章节（独立 PR §7.7）
- ✅ `AGENTS.md` (internal) §二 补 visual_inspect / verify_fix SSOT（独立元规则 PR §7.7）

**Step 2 总估时**：~50 天 ≈ 10 周（2.5-3 sprint）。

### §9.3 Step 3：拆 PyPI 包（**按需，不在当前承诺范围**）

不写具体 PR 列表。触发条件：
- 外部团队反馈"装 krow 全部依赖太重，要剥离 desktop UI / knowledge backend"
- 外部团队反馈"要独立版本节奏，跟 krow main 不同步"
- 外部团队反馈"嵌入式无沙箱不安全，要 RPC 隔离"
- monorepo workspace 工具（hatch / uv workspace）成熟 + 内部 dev 流程能跟上

#### §9.3.1 Step 3 触发监测机制（**v0.8 顶级 review A15 新增**）

> **痛点**：v0.7 列了 4 个触发条件但没说怎么监测——"外部团队反馈"是被动等待，不是主动收集。

**v0.8 监测渠道**：

| 渠道 | 频率 | 触发阈值 | 落地 |
|---|---|---|---|
| **Telemetry**（§5.13 opt-in 反向 telemetry）| 月度自动 | `protocols_used` 数据显示 ≥ 3 个独立 plugin 团队反馈"装 krow 太重"OR 单 SDK 进程内存超 2GB OR experimental Protocol 使用率 < 5% 持续 3 个月 | krow.cn 后端 dashboard 自动告警 |
| **GitHub Issue label**（`step3-trigger`）| 持续 | ≥ 3 个独立 plugin 团队 +1 同一个 Issue | 触发 Step 3 启动决策 |
| **季度 plugin 团队主动调研**（3-5 个 plugin 团队问卷）| 季度 | "依赖太重 / 版本节奏不同步 / 沙箱不够" 任一项 ≥ 60% | 触发 Step 3 启动决策 |
| **CI 数据**（lite vs full edition build size 监控）| 持续 | full edition build > 1.5GB（当前 ~800MB；超阈值说明 monorepo 已扛不住）| 触发 Step 3 启动决策 |

**Step 3 启动 checklist**（任一渠道触发后）：

1. 5 顾问辩论（`AGENTS.md` (internal) §6.2.2）评估"分包 vs 继续 monorepo"trade-off
2. 评估 hatch / uv workspace 成熟度（v0.8 时机：2026 后期 / 2027 初）
3. 评估 dev 流程影响（CI / 跨包 import / 测试基础设施）
4. 出 Step 3 design doc PR + 渐进路线图（与 Step 1/2 一致风格）

### §9.4 时间线

```
Week 0-3   ─ Step 1 (S1.1-S1.10)：内部 facade + 反插件化障碍修复 + 契约测试
Week 4-12  ─ Step 2 (S2.1-S2.13)：entry_points 加载 + 真实 plugin demo + CI 加固
Week 13+   ─ feature flag 观察期；若顺利 → Step 2 转 default on；按需启动 Step 3
```



## §10 可逆性 / blast radius / feature flag

### §10.1 每个 Step 的可逆性

| Step | revert 路径 | 残留风险 |
|---|---|---|
| Step 1 | 删 `modules/agent/sdk/` 子包 + 恢复 `app/` 层深 import | 无（内部 refactor，无对外承诺） |
| Step 2 | feature flag `KROW_ENABLE_PLUGIN_ENTRY_POINTS=0` → 行为退回 Step 1 | 已发布的 SDK API 不可下线，但可降级 |
| Step 3 | 不在当前承诺，按需启动；revert 通过 monorepo merge 回主仓 | N/A |

### §10.2 feature flag 设计

**全局开关**：

| 环境变量 | 默认 | 用途 |
|---|---|---|
| `KROW_ENABLE_PLUGIN_ENTRY_POINTS` | `0`（off） | Step 2 总开关；off 时 SDK 行为退回 Step 1 |
| `KROW_PLUGIN_ALLOWLIST` | `""`（全开） | 逗号分隔 plugin_id 白名单；非空时只加载列出的 plugin |
| `KROW_PLUGIN_BLOCKLIST` | `""` | 逗号分隔 plugin_id 黑名单；列出的 plugin 跳过加载 |

**单 Protocol 开关**（每个 Protocol 独立 feature flag，便于灰度）：

| 环境变量 | 默认 | Protocol |
|---|---|---|
| `KROW_PLUGIN_P1_ACT` | `1` | ACTPlugin |
| `KROW_PLUGIN_P2_TOOL` | `1` | ToolPlugin |
| `KROW_PLUGIN_P3_HINT` | `1` | HintPlugin |
| `KROW_PLUGIN_P4_GATE` | `1` | GatePlugin |
| `KROW_PLUGIN_P5_EVENT` | `1` | EventListenerPlugin |
| `KROW_PLUGIN_P6_OBSERVABILITY` | `1` | ObservabilityPlugin |
| `KROW_PLUGIN_P7_MCP` | `0`（高风险，灰度） | MCPServerPlugin |
| `KROW_PLUGIN_P8_SECURITY` | `1` | SecurityPlugin |
| `KROW_PLUGIN_P9_DOMAIN_PACK` | `0`（新协议，灰度起步；1 sprint 观察期后转 1） | DomainPackPlugin |
| `KROW_PLUGIN_VISUAL_ADAPTERS` | `1` | visual_adapter entry_points 加载（不是 Protocol，但走同 feature flag 模式） |
| `KROW_SDK_HTTP_GATEWAY` | `0`（默认 off，显式 `with_http_gateway(enable=True)` 才启动） | KrowService FastAPI gateway（跨进程 UI；详 §6.5） |
| `KROW_SDK_DATA_FACADE` | `1` | `krow_agent_sdk.data` 只读 façade（详 §5.10 / §6.6） |
| `KROW_SDK_DIAGNOSTICS_FACADE` | `1` | `krow_agent_sdk.diagnostics` 只读 façade（详 §5.11 / §6.7） |
| `KROW_API_KEY` | （无默认） | **认证必需**：krow cloud API key（`sk-user-xxx`）；用 `AgentBuilder.from_env()` 时读这个变量；详 §3 |
| `KROW_PROJECT_ROOT` | （无默认） | 可选：`AgentBuilder.from_env()` 时读项目根；不传需 `.with_project_root()` 显式 |
| `KROW_SDK_PLUGIN_ERROR_MODE`（**v0.8 新增 D6**）| `swallow` | plugin handler 抛异常的处理模式：`swallow`（默认 + stderr log）/ `raise`（fail-loud）/ `quiet`（仅 audit log，不打 stderr）；详 §6.0.4 |
| `KROW_SDK_BUILD_VALIDATE_CONNECTION`（**v0.8 新增 A6**）| `1` | `build()` 时是否做连接验证（GET /v1/models + project_root 写权限测试 + plugin signature 校验）；CI / offline dev 设 `0` |
| `KROW_SDK_SIGNATURE_VALIDATION`（**v0.8 新增 A1/R26**）| `1` | 启动期 plugin signature validator 是否启用；`0` 时跳过签名校验（仅 dev/debug，不推荐生产）|
| `KROW_SDK_TELEMETRY`（**v0.8 新增 A16**）| `0`（**off**） | opt-in 反向 telemetry 上报（plugin_id_hash + protocols_used + 错误聚合）到 https://api.krow.cn/sdk/telemetry/v1/anonymous；详 §5.13 |

任何 Protocol / facade 出问题可单独关闭，不影响其他模块。

#### §10.2.1 feature flag vs Builder 配置优先级链（**v0.8 顶级 review A12 修订**）

> **痛点澄清**：v0.7 §6.2 默认全部启用 vs §10.2 `KROW_PLUGIN_P9_DOMAIN_PACK=0` 默认 off — 两层语义冲突，开发者不知道实际行为。

**v0.8 决策：AND 关系（任一 false 即不加载）**：

```
最终行为 = (Builder 是否调 with_*_from_entry_points) AND (feature flag 是否 on) AND (BuilderConfig.plugin_loaders.<x> 是否为 True/list)
```

| Builder 配置 | feature flag | 实际行为 |
|---|---|---|
| 调 `with_domain_packs_from_entry_points()` 或 BuilderConfig 默认 True | `KROW_PLUGIN_P9_DOMAIN_PACK=1` | ✅ 加载 |
| 调 `with_domain_packs_from_entry_points()` | `KROW_PLUGIN_P9_DOMAIN_PACK=0` | ❌ 不加载（feature flag 优先 cut off）|
| 不调（或显式 `with_<x>(enable=False)`） | `KROW_PLUGIN_P9_DOMAIN_PACK=1` | ❌ 不加载（Builder 优先 cut off） |
| 不调 | `KROW_PLUGIN_P9_DOMAIN_PACK=0` | ❌ 不加载 |

**实施约束**：
- AgentBuilder 默认行为（§6.2）必须**遵守 §10.2 feature flag 默认值**——experimental Protocol（P7/P8/P9）的 flag default off → Builder default 也 off
- BuilderConfig.plugin_loaders 默认值与 §6.2 默认行为对齐

### §10.3 deprecation 协议

**版本号**：SDK 走 SemVer：`major.minor.patch`

| 变更类型 | 版本号 | 影响 |
|---|---|---|
| Protocol 接口签名变化 | major +1 | break；保留旧 facade 6 个月 |
| 加新 Protocol 方法（带 default 实现） | minor +1 | 兼容 |
| Protocol 实现 bug fix | patch +1 | 兼容 |

**deprecation 装饰器**（SDK 内置）：

```python
from krow_agent_sdk.deprecation import deprecated_since

class AgentBuilder:
    @deprecated_since(
        "2.0",
        removal="3.0",
        replacement="with_krow_api_key(api_key)",
    )
    def with_legacy_oauth_session(self, session: "LegacyOAuthSession") -> "AgentBuilder":
        """[DEPRECATED] 桌面 OAuth 会话登录。请改用 with_krow_api_key(api_key)。"""
        ...
```

调用废弃 API → emit `DeprecationWarning` + audit log 记录调用方 plugin_id（让 SDK 维护者能追踪谁还在用旧 API）。

### §10.4 blast radius 分析

| 改动 | blast radius | 缓解 |
|---|---|---|
| Step 1 `modules/agent/sdk/` 新建 | 0（新文件） | 无需 |
| Step 1 `app/` 改走 sdk facade | app 层全部文件（约 30+ 文件） | 通过 facade 函数签名兼容 + 契约测试守住 |
| Step 1 ChatMessage 双轨合并 | 全仓所有 LLM 调用方（约 50+ 文件） | grep 全文替换 + 契约测试 |
| Step 2 ACTLoader 改造 | act_loader.py + ACTManager + 19 个 native ACT 加载 | feature flag 兜底 + 全量 ACT 注册测试 |
| Step 2 ToolManager 改造 | tools/manager.py + 全部内置工具注册 | feature flag + 工具注册回归测试 |
| Step 2 GateChain 改造 | conclude_guard 全链 | 现有 9 个 native gate 测试全绿 |
| Step 2 SecurityPlugin SandboxValidator 集成 | 工具调用前置 hook（影响所有工具） | feature flag + 跨平台 smoke 全绿 |

### §10.5 元规则文件改动协议（**v0.8 顶级 review A14 修订：时机对齐代码落地**）

按 `AGENTS.md` (internal) §7.7：

| 文件 | 必须独立 PR | 时机（**v0.8 修订**） |
|---|---|---|
| `AGENTS.md` §一 SSOT 表加 plugin protocols 行 | ✅ 独立 PR | **S1.1 PR 同期独立元规则 PR**（与代码同步落地，**不是** design doc PR 后；防新 LLM agent 找不到 SSOT 路径）|
| `AGENTS.md` 加 plugin 开发指南章节 | ✅ Step 2 之后独立 PR | Step 2 完成后 |
| `AGENTS.md` §二 补 visual_inspect / verify_fix SSOT 行 | ✅ Step 2 同期独立元规则 PR | Step 2 |
| `.cursor/rules/plugin-authoring.mdc`（新建） | ✅ Step 2 之后独立 PR | Step 2 完成后 |
| `tests/MAP.md` 加 `tests/sdk/` 子目录登记 | ✅ **与 S1.9 同 PR** | S1.9 同 PR |

**v0.8 元教训**：v0.7 §10.5 写"design doc 落地后下一个 PR"——但实际 design doc 落地后**真实代码还没建**，新 LLM agent 看 AGENTS.md SSOT 表跳到 `modules/agent/sdk/protocols.py` 会 file-not-found。**v0.8 修订**：元规则 PR 必须**与对应代码 PR 同期独立**（不在它前 / 不在它后），与 `AGENTS.md` (internal) §0.0 准确性 > 完整性原则一致。



## §11 测试 SDK（krow_test_sdk）

> **现状漂移说明**（2026-05-14 sdk-review batch 2 追加）：本节是 v0.8 设计意图。
> **当前实际 SSOT**：对外测试 harness 已统一到 `from krow_agent_sdk.test_sdk import HeadlessAgentHarness`
> （主仓 `modules/agent/sdk/test_sdk.py`，pure Python 不依赖 PySide6，可在 Linux Docker
> 内跑）。`tests/e2e_framework/harness.py:WorkbenchHarness` **依赖 PySide6**，仅 monorepo
> 内 UI e2e 使用，**不**通过 SDK 公开导出。下表 "krow_test_sdk.harness:WorkbenchHarness"
> 是 v0.8 设想的独立 namespace；目前 SDK 用户应直接走 `HeadlessAgentHarness` +
> `LLMReplayStore`（`from krow_agent_sdk.replay import LLMReplayStore`）。

### §11.1 暴露策略

`krow_test_sdk` 是与生产 SDK 同包发布的 namespace（v0.8 设想；当前 SDK 已合并到
`krow_agent_sdk.test_sdk` + `krow_agent_sdk.replay` 子模块），包含 `tests/e2e_framework/`
+ `tests/support/` 的子集。

**对外暴露的能力**（`AGENTS.md` (internal) §3.3 测试基础设施清单 子集）：

| 能力 | 当前真实 SSOT（推荐用） | v0.8 设想路径（保留作历史参考） |
|---|---|---|
| HeadlessAgentHarness | `from krow_agent_sdk.test_sdk import HeadlessAgentHarness` | — |
| WorkbenchHarness（含 UI） | `tests/e2e_framework/harness.py:WorkbenchHarness`（仅 monorepo 内） | `krow_test_sdk.harness` |
| AgentProbe | `tests/e2e_framework/agent_probe.py:AgentProbe` | `krow_test_sdk.agent_probe` |
| EventTracer | `tests/e2e_framework/event_tracer.py` | `krow_test_sdk.event_tracer` |
| waiters（wait_until / wait_event / wait_signal / WaitTimeout） | `tests/e2e_framework/waiters.py` | `krow_test_sdk.waiters` |
| ArtifactSink | `tests/e2e_framework/artifact.py` | `krow_test_sdk.artifact` |
| LLMReplayStore | `from krow_agent_sdk.replay import LLMReplayStore` | `krow_test_sdk.llm_replay` |
| journey runner | `tests/e2e_real/_journey_runner.py` | `krow_test_sdk.journey_runner` |

**不对外暴露**（main repo 内部专用）：
- `tests/e2e_framework/auth.py`（含 desktop UI 登录细节）
- `tests/e2e_framework/ui_probe.py` / `tab_probe.py` / `web_probe.py`（与 PySide6 耦合）
- `tests/e2e_framework/screenshot.py` / `modal_guard.py`（同上）

### §11.2 外部 plugin 写 e2e 模板

```python
# 外部 plugin 的测试代码
from krow_test_sdk.harness import WorkbenchHarness
from krow_test_sdk.agent_probe import AgentProbe
from krow_test_sdk.llm_replay import LLMReplayStore
from krow_test_sdk.event_tracer import EventTracer
from krow_test_sdk.waiters import wait_event, wait_until

import pytest

@pytest.mark.cross_platform_smoke
def test_cad_designer_e2e_replay(tmp_path):
    """端到端用 LLMReplayStore 跑（确定性、零 LLM 成本）。"""
    
    replay_store = LLMReplayStore.load(
        Path(__file__).parent / "fixtures/cad_design_replay.json"
    )
    
    with WorkbenchHarness.embedded(
        krow_api_key="sk-user-fake-replay",  # 第 8 轮辩论：API key 替换 fake_krow_session
        project_root=tmp_path,
        llm_replay=replay_store,
    ) as harness:
        probe = AgentProbe(harness)
        tracer = EventTracer(harness.event_bus)
        
        result = probe.run("帮我设计一个减速箱齿轮组")
        
        # 多维断言（参考 AGENTS.md §4.1 预期结果卡）
        assert result.success
        assert "齿轮模数" in result.final_output
        assert (tmp_path / "exports/gearbox.pptx").exists()
        
        # 验证 plugin gate 被调用
        gate_events = list(tracer.iter_events("conclude_guard.gate_check"))
        assert any(e.payload["gate_name"] == "industrial_design.mech_constraints" for e in gate_events)
```

### §11.3 plugin 协议契约测试模板

外部 plugin 的契约测试（验证自己实现了 Protocol）：

```python
# 外部 plugin 的 tests/test_plugin_contract.py
from krow_test_sdk.contract import (
    assert_implements_act_plugin,
    assert_implements_tool_plugin,
    assert_implements_gate_plugin,
)

from industrial_design_pkg import get_act_plugin, get_tool_plugin, get_gate_plugin

def test_act_plugin_contract():
    plugin = get_act_plugin()
    assert_implements_act_plugin(plugin)
    # 自动验证：plugin_id / get_act_root() / get_act_names() 都正确
    # 自动验证：act_root 含 __act__.yaml
    # 自动验证：act_names 内的 ACT 都能被 ACTLoader 加载

def test_tool_plugin_contract():
    plugin = get_tool_plugin()
    assert_implements_tool_plugin(plugin)
    # 自动验证：每个 ToolDefinition 有合法的 input_schema
    # 自动验证：handler 是 callable
    # 自动验证：latency_class 是 hot/warm/cold
```

### §11.4 真实 LLM E2E（按 `AGENTS.md` (internal) §4.1）

外部 plugin 的真实 LLM e2e 模板：

- 提前写"预期结果卡"（多维断言：actions / artifacts / quality / fail_signals / perf）
- nightly 跑真实 LLM（用真实 `KROW_API_KEY=sk-user-xxx` 环境变量；CI 走 GitHub Actions secrets，本地走 `.env` + `direnv`）
- 主测试链跑 `LLMReplayStore`（确定性、零成本）
- nightly 真实 e2e 必跑：API key 验证（401 / 402 / 模型路由 / 计费上报到 https://krow.cn 控制台）
- UI 类必须像素走查（baseline + 5% 容忍）—— plugin 暴露 UI 时必填

### §11.5 plugin 自查工具

SDK 内置 CLI：

```bash
# 验证当前已安装 plugin
krow-sdk validate-plugin industrial-design-agent

# 输出示例：
# ✅ ACTPlugin: industrial_design.cad_designer
#    - act_root: /path/to/acts
#    - act_names: ["cad_designer"]
#    - extended.md: 1342 lines
# ✅ ToolPlugin: 5 tools registered
#    - cad_calculate_gear_strength: latency_class=warm, traits=[CONTENT_SOURCE]
#    - ...
# ⚠️ Warning: tool 'cad_render' has no latency_class (defaulting to 'warm')
# ❌ Error: GatePlugin 'mech_constraints' returns DEFER without reason (anti-pattern)
# ⚠️ Warning: Plugin imports `httpx` directly (anti-pattern; use SDK-injected LLM provider)
```



## §12 风险登记 + 已知未解决项

### §12.1 风险登记（设计阶段已识别）

| # | 风险 | 概率 | 严重度 | 缓解 |
|---|---|---|---|---|
| R1 | 内部 refactor 把 SDK facade 漂偏（双写不同步） | 高 | 中 | `tests/sdk/test_*_protocol_contract.py` 契约测试 + Step 2 加 plugin 兼容性矩阵到 contracts.yml |
| R2 | 外部 plugin crash 拖死 agent 进程 | 中 | 高 | plugin 调用都包 `try/except` + EventBus 发布 `plugin.error.<plugin_id>` 事件 + audit log；Step 3 强沙箱根治 |
| R3 | entry_points 加载顺序敏感 | 中 | 中 | plugin 注册时声明 priority（1-10），冲突按 priority 排序 + 报告冲突 |
| R4 | 外部 plugin 滥用 LLM 烧 krow cloud 余额 | 中 | 高 | BudgetController 已有限额；plugin 调 LLM 走 `record_llm_call()` 计入；`source_module=PLUGIN_<id>` 精确计费 |
| R5 | namespace 冲突（plugin 间 / plugin 与 native） | 中 | 中 | 强制 `<plugin_id>.` 前缀；冲突 fail-loud |
| R6 | Plugin 假装"做了沙箱"（`AGENTS.md` (internal) §0.0 准确性 > 完整性） | 低 | 高 | design doc + SDK 文档明文写 MVP 不是强沙箱；强沙箱推 Step 3 |
| R7 | LLM source_module 重复赋值 bug 影响 audit log | 高 | 中 | Step 1 修复（铁证 §0.3） |
| R8 | 双 ChatMessage 反 SSOT | 高 | 中 | Step 1 修复（铁证 §0.3） |
| R9 | plugin 接入文档不全 → 外部团队走错路（如自己造 LLM provider） | 中 | 中 | examples/ 提供完整 hello-world + cad-design + research-agent demo |
| R10 | feature flag 太多导致组合爆炸 | 中 | 低 | 默认配置开箱即用；feature flag 只在出问题时调 |
| R11 | knowledge_analyzer 在没 ES 时启动报错 | 低 | 低 | 已有 `has_knowledge_base()` fail-loud 守门 |
| R12 | pptx_studio feature flag 在 SDK 与 main repo 不同步 | 低 | 低 | feature flag 走环境变量统一 SSOT |
| R13 | 跨平台路径差异（win `\` vs unix `/`）破坏 SandboxValidator 白名单匹配 | 中 | 中 | 跨平台 smoke 全绿 + `Path` 标准化 |
| R14 | Step 2 改 ACTLoader 砍 ext_ 前缀破坏现有内部使用方 | 中 | 中 | 兼容性 fallback：旧 `ext_` 前缀继续工作 6 个月 + deprecation warning |
| R15 | 多 DomainPack 同 target_act 时 supplement 内容互相冲突（一个 pack 说"只抽 X"，另一个说"只抽 Y"），LLM 看到两条矛盾指令导致行为漂移 | 中 | 中 | priority 排序合并 + supplement 头部明文标注 plugin_id；冲突由 LLM 看到所有 supplement 文本按 priority 顺序权衡（System 2 决策）；实战 + nightly e2e 跑多 pack 共存 case |
| R16 | DomainPack supplement 让 native ACT prompt 失控（4000 字符上限被绕过 / prompt 注入"忽略上文"等敏感关键词） | 中 | 高 | 4000 字符上限 fail-loud；启动期扫描 supplement 关键词黑名单（"忽略上文系统指令" / "ignore previous instructions" / "you are now" 等）→ 命中即拒绝加载 + EventBus 事件；与 PromptSafetyPlugin U1 协同 |
| R17 | visual_inspect 调 chat_vision VLM 烧 token 预算（VLM 比 chat 模型贵 5-10x），plugin 滥用导致 krow cloud 余额超支 | 中 | 高 | BudgetController 已有限额；VLM 调用走 `record_llm_call(category="vision")` 单独计费维度；外部 plugin 文档明文写"高频视觉质检请走 LLMReplayStore + nightly 真实模式"（`AGENTS.md` (internal) §4.1） |
| R18 | 外部 UI 假定全部 EventBus topic 都稳定，主仓 refactor 时 plugin/UI 失效（动态 topic 破契约） | 中 | 中 | SDK 文档明文标注稳定 topic 子集 vs 动态 topic（详 §5.5）；动态 topic 监听属"best-effort"；契约测试 + nightly 跑稳定子集变化检测 |
| R19 | Plugin 通过 `krow_agent_sdk.data.query_knowledge(layers=["L2"])` 查 L2 Neo4j 高频导致后端崩溃 | 中 | 中 | 默认 `layers=["L0","L1"]` 不含 L2；显式传 L2 时走 BudgetController 计入 + rate limit；nightly e2e 验证 L2 高负载场景 |
| R20 | ~~turbo_diagnostics 接入 executor 后改变 adapt 触发时序~~（**第 8 轮辩论作废**：subagent 铁证 v1 已被 v2 替代，PR S1.12 改为"仅暴露 SDK facade 不接入 v1"——这条风险消失）| ~~~~ | ~~~~ | **R20 已消除**：第 8 轮辩论维持现状，不接入 v1；v1/v2 文档漂移属主仓治理债务（不在 SDK 范围） |
| R21 | micro/macro LLM 计数一致性修复（PR S1.13）改变 budget 计算，破现有 e2e 测试 | 中 | 中 | Step 1 PR S1.13 加 unit test + 跑现有 e2e_real 套件；不一致是潜在 bug 必须修，但需要小心地灰度（feature flag 暂未列） |
| R22 | Plugin 滥用 `BudgetSpec` 设极大值（`max_walltime_s=86400` / `max_total_llm_calls=10000`）耗尽 krow cloud 余额 | 高 | 高 | BudgetSpec 加全局上限校验（启动期 fail-loud 拒绝超过 `KROW_SDK_BUDGET_HARD_CAP_*` 环境变量的值）；audit log 记录 Plugin id + BudgetSpec 配置 |
| R23 | **第 8 轮辩论新增**：`AuthService._login_with_api_key` → `KrowAuthAdapter.set_api_key` / `get_user_info` 是 dead code（subagent 铁证 + `docs/plan_object_centric_v1_22.md` 标注），直接转 API key 模式会触发 NoMethodError | 高 | 高 | Step 1 PR S1.17 必修：实现两个方法 + 接通 AuthService 分支 + 加 `KROW_API_KEY` 环境变量识别 + nightly 真实 sk-user-xxx e2e 验证（覆盖 401/402/计费上报） |
| R24 | **第 8 轮辩论新增**：design doc v0.1-v0.6 引用的 `KrowAuthSession` / `login_from_env` 是虚构概念（仓内不存在），第 7 轮辩论沿用未发现 | 中 | 中 | 第 8 轮辩论修订全部 17 处 KrowAuthSession 出现（已修订完毕；附录 A 第 8 轮决策日志记录）；元教训："先铁证后决策"，比照第 6 轮 knowledge_analyzer 误判 |
| R25 | **第 8 轮辩论新增**：DomainPack 扩展为 8 元素后 plugin 可能利用 `get_event_listeners` 在 `budget.exhausted` handler 内试图修改 budget（违反只读契约） | 中 | 中 | listener 严格只读契约（§5.5）+ DomainPack expander 在注册时 wrap listener 为只读视图（plugin 拿不到 BudgetController write API）+ 启动期扫描 plugin 模块 import budget_controller 写 API → warning |
| **R26（v0.8 顶级 review A1）**：`@runtime_checkable` Protocol 只查方法名存在性，plugin 写错签名运行时才 break | 高 | 高 | Step 1 PR S1.19 加 `_protocol_validator.validate_protocol_implementation` 启动期签名校验 + `KROW_SDK_SIGNATURE_VALIDATION` env var 控制 + `PluginSignatureMismatchError` |
| **R27（v0.8 顶级 review A7）**：design doc §3.3 "运行时按 plugin_id 注册新 enum entry" 撞 Python `enum.Enum` frozen | 高 | 高 | Step 1 PR S1.23 改 `LLMSourceModule = Union[BuiltinLLMSourceModule, str]`；plugin 用 `make_plugin_source_module(plugin_id) -> str` 字符串命名空间 |
| **R28（v0.8 顶级 review A13）**：v0.7 PR S1.5 "refactor app/ 层全部走 sdk facade" 估时 4d 严重低估 blast radius（实际 30+ 文件 + desktop UI e2e 套件全跑）| 高 | 中 | Step 1 PR S1.5 拆为 S1.5a/b/c 三个 sub-PR：薄 facade(1d) + 调用方分批迁(每批 5 文件 × 6 批 = 30d) + e2e 全套回归(5d) |
| **R29（v0.8 顶级 review A10）**：`agent.event_bus` 暴露完整 `EventBus` 接口 → Hyrum's Law 灾难（plugin 用 publish() / 内部状态 → 主仓 refactor 全破）| 中 | 高 | Step 1 PR S1.21 改 `EventBusReader` 只读 facade（仅 subscribe/unsubscribe/iter_recent，无 publish/内部状态） |
| **R30（v0.8 顶级 review A6）**：`with_krow_api_key()` 后第 1 次 LLM 调用前才能验 api_key（401 才知道 invalid），开发者可能 1h 后才发现 key 错 | 高 | 中 | Step 1 PR S1.17 加 `build(validate_connection=True)` 启动期 GET /v1/models 验证 + project_root 写权限测试；`KROW_SDK_BUILD_VALIDATE_CONNECTION=0` 跳过（dev/offline）|
| **R31（v0.8 顶级 review D6）**：plugin handler 抛异常 swallow 后开发者**默认看不到错误**（不订阅 `plugin.error.*`），违反准确性原则 | 高 | 高 | Step 1 PR S1.22 默认 swallow 模式自动 `logging.error` 到 stderr（开发者总能看到）+ `KROW_SDK_PLUGIN_ERROR_MODE` env var（swallow/raise/quiet）|
| **R32（v0.8 顶级 review A2/A3）**：9 Protocol 一次性发布锁死后 5 年内难调整（Hyrum's Law + npm/pip 历史教训）| 高 | 高 | §5.0 Protocol 优先级分层（mvp_critical / stable / experimental）+ §5.0.2/3 增减治理协议；experimental 用 `krow_agent_sdk.experimental.protocols` 单独 namespace + feature flag default off |

### §12.2 已知未解决项（推迟到后续设计）

| # | 项目 | 状态 |
|---|---|---|
| U1 | PromptSafetyPlugin（prompt 安全检查） | 实现不完善暂不加；未来若领域有强需求再设计（第 4 轮辩论决策） |
| U2 | 强沙箱（subprocess 隔离 / RestrictedPython） | 推 Step 3；MVP 用声明式 + 部分硬闸门兜底 |
| U3 | RPC 容器形态（C） | 推 Step 3；现有 `agent_proxy.py` + `relay_transport.py` 可作底座 |
| U4 | ReactTemplatePlugin（自定义 micro ReACT 场景模板） | 第 2 轮辩论决策：降级到走 ToolPlugin 加 micro 工具，不单独 Protocol；未来若多 plugin 真有自定义模板需求再加 |
| U5 | StateStorePlugin / ExperienceMemoryPlugin / ReplanStrategyPlugin / MetaLearningPlugin | 第 2/3 轮辩论决策：元认知 / 状态机不让外部替换；只能用不能换 |
| U6 | BackgroundTaskPlugin | 第 2 轮辩论决策：直接暴露 `BackgroundAgentTaskQueue.submit()` 不开 Protocol |
| U7 | TraitPlugin | 第 2 轮辩论决策：合并到 ToolPlugin（trait 是 Tool 元数据） |
| U8 | LLM Provider Plugin | 强绑 krow cloud；不开放 LLM provider 替换 |
| U9 | ConfigPlugin（外部 plugin 注册自己的配置项） | 第 2 轮辩论决策：用 entry_points + plugin 自己读环境变量 / yaml 即可 |
| U10 | tests/sdk/ 跨平台 baseline 测试基础设施（截图 baseline 比对） | `tests/e2e_framework/screenshot.py` 当前没有 ready 的对比 API；要做要先扩展（OCP） |
| U11 | LLMSourceModule.PLUGIN_<id> 自动注入机制 | Step 1 设计；运行时按 plugin_id 动态生成 LLMSourceModule entry |
| U12 | 多 SDK 进程实例并存（外部团队启动多个 AgentBuilder） | Step 1 默认支持（每个 build() 返回独立 Agent）；但单 SDK 进程内 EventBus / project_root 单例不变 |
| U13 | Plugin hot reload（开发时不重启 reload plugin） | 不在 Step 1/2 范围；外部团队自己 importlib.reload 处理 |
| U14 | Plugin metrics 聚合到 krow 主仓 audit | Step 2 走 ObservabilityPlugin 自己暴露给 plugin；krow 主仓不聚合 plugin 自己的 metrics |
| U15 | 多 DomainPack 同 target_act 时 priority 冲突的细粒度合并策略（同 priority 时是字典序还是注册顺序） | Step 2 决策：同 priority 时按 plugin_id 字典序（确定性） + 加 EventBus 事件 `domain_pack.priority_collision` 提醒；未来若有需求可加 user-overridable 排序 hook |
| U16 | DomainPack supplement extended.md 长度上限是否要按 target_act 分级（如 wiki_compiler 给 8000 / pptx_editor 给 4000） | Step 2 起步统一 4000 字符；实战发现某 ACT 强需求再分级（按 `AGENTS.md` (internal) §0.0：先简单后复杂） |
| U17 | visual_adapter entry_points 多个 plugin 注册同一 ext（如 plugin A 和 plugin B 都注册 `.step`）的优先级策略 | Step 2 决策：fail-loud（namespace 冲突）；外部 plugin 必须自己协调或用 plugin_id 命名空间区分（如 `industrial_design.step` vs `cad_kit.step`） |
| U18 | per-plugin API key（每个 plugin 持独立 `sk-user-xxx` 实现细粒度计费） | **第 8 轮辩论决策**：起步用 master api_key + `source_module=PLUGIN_<id>` audit 区分；未来若实战有强需求（多租户 SaaS / per-plugin 余额隔离）再加 `AgentBuilder.with_plugin_api_key(plugin_id, api_key)`（详 Q18） |
| U19 | krow cloud 服务端契约：响应 `usage` 中是否带 `api_key_id` 字段 | Step 1 PR S1.17 调研云端契约后决策（含 nightly 真实 e2e 验证） |

### §12.3 Open Questions（review 时讨论）

1. **Q1**：`AgentBuilder.build()` 是否同步阻塞还是可异步？建议同步（与现有 `bootstrap_v3()` 一致）；但 `Agent.run()` 同时支持 sync 和 async（与 `AgentV3.run()` 现状一致，需要补 `arun()`）。
2. **Q2**：plugin 的 `plugin_id` 是 entry_points 名还是 plugin 自己声明？建议**自己声明**（避免 entry_points 名与代码内 namespace 不一致），SDK 启动期校验两者一致。
3. **Q3**：krow_cloud_features 列表的 SSOT 在哪？建议在 `modules/agent/act/acts/krow_cloud/__act__.yaml` 加 `features:` 字段（细分 image_gen / ocr / vision 等子能力），SDK 透传。
4. **Q4**：是否需要 plugin lifecycle hook（`on_load` / `on_unload` / `on_agent_start` / `on_agent_end`）？倾向**最小化**——只暴露 `on_load` 和 `on_unload`（详细 lifecycle 走 EventListenerPlugin 订阅 `agent.*` 事件）。
5. **Q5**：测试 SDK `krow_test_sdk` 是与生产 SDK 同包发布，还是独立包？建议**独立包**（外部团队不在生产环境装测试依赖）。
6. **Q6**：MCPServerPlugin 的 server 是否需要 lifecycle 管理（启动 / 健康检查 / 重连）？建议复用 `modules/mcp/` 现有客户端的连接管理；plugin 只声明配置，不管理 lifecycle。
7. **Q7**（review fix A2）：DomainPack `priority` 字段当前定义为 1-10 整数，是否要支持小数 / 负数 / 字符串标签（如 `"high"/"normal"/"low"`）？建议**仍维持 1-10 整数**（System 1 确定性），未来若需细粒度可扩展。
8. **Q8**（review fix A3）：DomainPack 是否允许"target_acts 含 plugin 自己注册的 ACT"（即领域 pack 给自己 plugin 的 ACT 加 supplement）？建议**允许**（OCP，pack 内自我组合也合理），但 supplement 处理逻辑相同（不修改源文件）。
9. **Q9**（review fix A4）：DomainPack 失败（如 supplement 超长 / namespace 冲突）时，整个 pack 加载是 fail-loud 拒绝，还是 partial（其他元素继续加载）？建议 **fail-loud 整 pack 拒绝**（`AGENTS.md` (internal) §0.0 准确性 > 完整性）。
10. **Q10**（review fix A5）：visual_inspect 函数式 API 是否要支持 batch（多文件一次调用）？建议**起步只支持单文件**，外部 plugin 自己 for 循环调用；实战发现批量需求再加 `visual_inspect_batch()`。
11. **Q11**（review fix A6）：visual_adapter 注册的 ext 是否要 case-insensitive？建议**是**（统一 `.lower()` 处理），与 `modules/agent/visual/visual_grounding_tools.py:register_visual_adapter` 现有行为一致。
12. **Q12**（review fix A1 → 已通过 P9 解决；保留为历史记录）：领域知识包定制需求 → P9 DomainPackPlugin 提供"语法糖聚合 hint+tool+gate+supplement"路径；不需要新增其他 Protocol。
13. **Q13**（第 7 轮辩论）：未来若领域有强 prompt 安全需求（如医疗/法律对 prompt injection 高度敏感），是否开 P10 PromptSafetyPlugin？建议**仍维持 U1 推迟**；先观察 §5.10 数据层 façade + P5 EventListener 监听 `security.prompt_injection` 事件能否覆盖；若不够再启动新 Protocol 设计。
14. **Q14**（第 7 轮辩论）：`AgentBuilder.with_http_gateway` 是否在 SDK 启动时立即占用端口（影响进程启动时间）？建议**只在 `enable=True` 时启动**；默认 lazy（不占端口）。
15. **Q15**（第 7 轮辩论）：`krow_agent_sdk.data.query_knowledge` 默认 `layers=["L0","L1"]` 不查 L2 是否会让 Plugin 失去重要知识？建议**显式传 L2 即可解锁**；默认保护是"防误用 + 防 Neo4j 高负载"。
16. **Q16**（第 7 轮辩论）：`dump_state` 输出过滤 secrets / token / 私密路径的清单是否 SSOT？建议**新建** `modules/agent/sdk/diagnostics_filter.py:SECRETS_PATTERNS` 作为 SSOT，启动期单元测试守住命中率。
17. **Q17**（第 7 轮辩论）：`BudgetSpec` 全局上限校验（防滥用，R22）是否要做成 plugin-id 区分（plugin A 上限 1h，plugin B 上限 24h）？建议**暂不分**（全局统一上限）；分级走主仓配置（不在 SDK 范围）。
18. **Q18**（第 8 轮辩论 → 已知未解决项 U18 同步登记）：per-plugin API key（每个 plugin 持有独立 sk-user-xxx 实现细粒度计费）。**第 8 轮决策**：起步用 master api_key + `source_module=PLUGIN_<id>` 在 audit 区分；未来若实战发现强需求（如多租户 SaaS / per-plugin 余额隔离）再开"per-plugin api_key 配置"（`AgentBuilder.with_plugin_api_key(plugin_id, api_key)`）。
19. **Q19**（第 8 轮辩论）：UsageTracker 是否要加 `api_key_id` 维度（与 service_type/model 同级）？建议**取决于云端契约**：若服务端在 LLM 响应里返回 `api_key_id` 字段（subagent 第 8 轮调研未证实云端契约），则 PR S1.17 加；否则不加（避免造重复轮子）。
20. **Q20**（第 8 轮辩论）：API key 在 SDK 进程内是否要走 `CredentialStore` 加密存储？建议**不需要**：SDK 嵌入式形态下 api_key 走环境变量 / SecretsManager（外部团队基础设施），SDK 进程内只在内存持有 + KrowAuthAdapter.get_headers() 直接拼 Bearer header；CredentialStore 是桌面 UI 路径的便利存储，与 plugin SDK 不在同一职责。

### §12.4 文档维护协议

- 本设计文档 = SDK API 与架构决策的 SSOT
- Step 1 落地后必须更新 §0 现状 + §9 路线图实际进度
- Step 2 落地后必须把 `AGENTS.md` 加 plugin 开发指南章节（§7.7 独立 PR）
- 任何 Protocol 接口变化必须先更新本文档 § 5（design doc PR）+ 后跟 implementation PR
- Protocol 设计反模式新增 → 加到 §5 对应 Protocol 的"反模式"表

---

## §13 Review Backlog（v0.8 顶级 review 落地清单）

> 本节是 v0.8 修订的"反模式 / 已落地 / 待落地"清单——每个 issue 标注严重度（P0/P1/P2）+ 修订 § 锚点 + 落地 PR。
> review 视角：顶级开发者（DX / Day 1-Day 90）+ 顶级架构师（5 年生命周期 / Hyrum's Law / npm/pip 历史教训）。

### §13.1 P0 issue 落地表（必修，11 个）

| # | issue | 视角 | 修订 § | 落地 PR |
|---|---|---|---|---|
| **A1** | `runtime_checkable` 虚假强类型（plugin 签名错运行时才 break）| 架构师 | §0.3 R26 / §3.5 `PluginSignatureMismatchError` / Step 1 退出标准 | S1.19 |
| **A2** | 9 Protocol 一次性发布缺优先级分层（Hyrum's Law 风险） | 架构师 | §5.0.1 优先级分层 + §5.0.4 既定 9 Protocol 分配 | S1.20 |
| **A3** | Protocol 增减治理协议缺失 | 架构师 | §5.0.2 加治理 / §5.0.3 砍治理 | （治理协议入设计文档即生效） |
| **A6** | fail-loud 延后到 first run | 架构师 | §6.1 build(validate_connection) / §10.2 KROW_SDK_BUILD_VALIDATE_CONNECTION | S1.17（修订）|
| **A7** | LLMSourceModule enum frozen 撞墙 | 架构师 | §0.3 R27 / §3.3 改 Union[..., str] | S1.23 |
| **A9** | DomainPack supplement 总量上限缺失 | 架构师 | §4.4 修订（同 ACT 16KB / 全进程 64KB） | S2.14（沿用，约束加上限）|
| **A10** | `agent.event_bus` Hyrum's Law 灾难 | 架构师 | §6.1 改 EventBusReader / §10.2 R29 | S1.21 |
| **A13** | S1.5/S1.6 blast radius 低估（实事求是估算）| 架构师 | §9.1 拆 S1.5a/b/c sub-PR / §10.2 R28 | S1.5a + S1.5b × 6 + S1.5c |
| **A16** | 反向 telemetry 缺失 | 架构师 | §5.13 opt-in / §10.2 KROW_SDK_TELEMETRY | S2.17 |
| **D1** | 包名 import 路径双轨混乱 | 开发者 | §6.0 import map + alias 双轨 | S1.18 |
| **D3** | error class 列名字没列实际 message | 开发者 | §3.5 完整黄金模板 message 文本 | S1.17（含）|
| **D6** | plugin error swallow vs propagate 不明确 | 开发者 | §6.0.4 KROW_SDK_PLUGIN_ERROR_MODE / §10.2 R31 | S1.22 |
| **D7** | 多租户部署模式不闭环 | 开发者 | §3.6 多租户 3 模式 + K8s 推荐架构 | （文档落地） |

### §13.2 P1 issue 落地表（应修，10 个）

| # | issue | 视角 | 修订 § | 落地 PR |
|---|---|---|---|---|
| A4 | SemVer 边界不全 | 架构师 | §10.3 deprecation 协议（含 4 类边界）| 文档落地（Step 2 之前完善） |
| A5 | AgentBuilder god class 蔓延 | 架构师 | §6.1 加 BuilderConfig + from_config classmethod | S1.2（含 BuilderConfig）|
| A8 | plugin_id 跨发布唯一性（强制双段命名）| 架构师 | §5.1 加 `<org>.<plugin>` 强制双段命名 | S2.1（namespace 改造时） |
| A11 | test SDK vs main repo 漂移 | 架构师 | §11 物理迁移 `tests/e2e_framework/` → `modules/agent/sdk/test_harness/` | S2.10（test SDK 暴露时） |
| A12 | feature flag vs Builder 配置冲突 | 架构师 | §10.2.1 优先级链（AND 关系）| 文档落地 |
| A14 | 元规则 PR 时机错位 | 架构师 | §10.5 改"S1.1 PR 同期独立元规则 PR" | S1.1 同期元规则 PR |
| D2 | 30 分钟接入 hello-world 缺最小 ACT 骨架 | 开发者 | §6.3 加 `__act__.yaml` + `tools.py` + `extended.md` 30 行骨架 | S1.10（examples 时）|
| D4 | plugin_id 命名约束三处不一致 | 开发者 | §5.1 顶部加"plugin_id 命名规范"块 | S1.20（namespace 改造时）|
| D5 | plugin lifecycle hook 缺失 | 开发者 | §6.0.4 BasePluginLifecycle mixin | S1.22 |
| D8 | with_native_acts vs with_acts_from_entry_points 语义不清 | 开发者 | §6.1 修订（叠加语义 + 决策矩阵）| 文档落地 |
| D9 | test SDK PySide6 耦合 | 开发者 | §11 加 `HeadlessAgentHarness`（无 PySide6 依赖）| S2.10 |
| D10 | CI 集成模板缺失 | 开发者 | §11 待补 GitHub Actions workflow 模板 | S2.12（examples 时） |

### §13.3 P2 issue 落地表（可改进）

| # | issue | 视角 | 修订 § | 落地 PR |
|---|---|---|---|---|
| A15 | Step 3 触发条件被动等待 | 架构师 | §9.3.1 监测机制（telemetry / GitHub Issue / 季度调研 / CI 数据）| Step 3 启动前 |

### §13.4 v0.8 元教训

1. **runtime_checkable Protocol 不是真强类型**：必须配套 `_protocol_validator.validate_protocol_implementation` 启动期校验签名（A1）
2. **enum frozen 撞墙**：design doc 写"运行时按 plugin_id 注册新 enum entry" 是错误前提；实现策略必须 fact-check Python 类型系统（A7）
3. **Hyrum's Law 防御**：暴露给外部的接口必须最小化（EventBusReader 不暴露 publish；A10）
4. **fail-loud 必须真在边界**：build() 时验 api_key + project_root + plugin signature，**不延迟**到 first run（A6）
5. **blast radius 实事求是估算**：refactor app/ 层 30+ 文件 4d 是低估；必须拆 sub-PR + 桌面 e2e 全套回归（A13）
6. **plugin ecosystem 健康度需要反向 telemetry**：没数据驱动决策 → 5 年后 ecosystem 碎片化无解（A16）
7. **swallow 模式默认 stderr log**：plugin 错误 swallow 但开发者必须能看到（D6）
8. **Protocol 优先级分层 + 增减治理**：9 Protocol 一次性发布锁死后 5 年难调整 → mvp_critical/stable/experimental 三层 + 增减治理协议（A2/A3）
9. **hello-world 缺最小骨架等于没有**：开发者从 design doc 跑不通 → 30 分钟接入目标失败（D2）
10. **多租户是 SaaS 第 30 天问题**：必须 design doc 提前明确 per-tenant 进程隔离推荐（D7）

---

## 附录 A：决策日志（8 轮辩论 + 1 轮顶级 review 双视角 → v0.8）

| 轮次 | 决策 | 理由（铁证） |
|---|---|---|
| 1 容器形态 | 嵌入式（A） | 用户上手成本最低 + 可逆性 + 不影响计费串联 |
| 1 LLM 后端 | 强绑 krow cloud | 复用现有 auth/billing 基础设施 |
| 1 项目根 | force_explicit fail-loud | `AGENTS.md` (internal) §0.0 准确性 > 完整性 |
| 1 文档落点 | docs/sdk/plugin-architecture-design.md 独立 PR | `AGENTS.md` (internal) §7.7 元规则文件独立 PR；本文档不是元规则更新 |
| 2 Protocol 数 | 全部发但继续辩论 | 一次性交付完整能力面 |
| 2 砍 StateStorePlugin / ExperienceMemoryPlugin | 元认知不让换 | "只能用不能换" |
| 2 砍 ReactTemplatePlugin / BudgetListenerPlugin / ReplanStrategyPlugin / TraitPlugin / BackgroundTaskPlugin | 走现有 OCP 不单独 Protocol | DRY / 不造重复轮子 |
| 2 加 MCPServerPlugin / 不加 MetaLearningPlugin / 不加 ConfigPlugin / krow_cloud 走 Builder 配置 | 见辩论框架 | — |
| 3 发布节奏 | Step 1 一次性 8 骨架 + Step 2 同批实现 | 重资产一次性交付 |
| 3 节奏 | 紧凑排（2-3 月） | 用户决策 |
| 4 SecurityPlugin | 加 P8（MVP 降级） | 复用 SandboxValidator；强沙箱推 Step 3 |
| 5 image_editor / image_generator | 都砍统一走 krow_cloud | image_editor 缺 extended.md；image_generator 与 krow_cloud 重叠 |
| 5 editor ACT | 不暴露 | IDE 缓冲区耦合 |
| 5 krow_cloud | SDK 自带（强绑 krow auth/billing） | 用户要求暴露 |
| 5 pptx_studio | SDK 暴露但默认 disabled（feature flag） | enabled: false 是 main repo 现状 |
| 5 knowledge_analyzer | SDK 暴露但运行时 fail-loud 守门 | 已有 has_knowledge_base() |
| 5 双 ChatMessage / LLMSourceModule.CHAT 重复赋值 | Step 1 必修 | 反 SSOT bug |
| 6 P9 DomainPackPlugin | 加（语法糖） | 用户场景驱动：科研/工业领域 native ACT 知识定制；4 元素聚合到一个 pack 类，不破红线（不修改 native 源） |
| 6 knowledge_analyzer 状态澄清 | 维持 §4.1 描述（**未废弃**，Lite 条件性不可用） | subagent 第 6 轮调研铁证：yaml 无 deprecated；act_manager 在 has_knowledge_base() 真时显式 register_act；reasoning_pipeline 仍依赖；用户最初"已废弃"认知与仓库事实不符 |
| 6 视觉质检暴露策略 | 部分暴露 + 不开 P10：visual_inspect 函数式 API + register_visual_adapter Builder 配置 + verify_fix 走 ToolPlugin trait | 复用现有 VisualGroundingService + krow cloud 计费串联；OCP 扩展点已具备（`register_visual_adapter`）；不破红线（plugin 不能改 ProgressiveExecutor 内核） |
| 6 AGENTS.md §二 漏列 visual_inspect / verify_fix | Step 2 同期独立元规则 PR 补 | subagent 第 6 轮 grep 全文确认 §二 漏列；走 §7.7 元规则文件独立 PR 协议 |
| 7 UI 通信策略 | 双轨：嵌入式 EventBus+callback（默认）+ Builder 显式 `with_http_gateway` 启 KrowService（跨进程）| subagent 第 7 轮调研铁证：KrowService FastAPI 已有 ~30 endpoints + WS + SSE 完整能力，但嵌入式默认不启动；不造重复轮子 + 同进程性能优先 |
| 7 数据层暴露策略 | 只读 façade（不开 Plugin Protocol）`krow_agent_sdk.data` | subagent 找到 7+ 个 sqlite db；Python API 层（KnowledgeAPI / SessionOntologyStore.to_view() / GlobalOntologyStore / ExperienceMemory.recall）已是只读门面；写禁止保 SSOT |
| 7 诊断工具策略（**第 8 轮修订**）| read-only facade（不开 P10）；**第 8 轮辩论：不接入 v1**（PR S1.12 重写为"仅暴露 SDK facade"）| 第 7 轮误判 turbo_diagnostics 为"死代码应接入"；第 8 轮 subagent 铁证 v1 已被 v2 替代（`executor_recovery.py` 模块 docstring 明文"取代 T4-lite + T5-lite"+ `tests/test_turbo_diagnostics.py` 注释"_handle_failure 不再走 T4-lite ReACT"）；接入会让 budget 计数失算 + parse_diagnostic_conclusion 解析失败 |
| 7 门控插件归属（12 类门控分散）| P4 GatePlugin 加 phase 字段（"conclude"/"micro_react_conclude"）覆盖 G1+G2；G3-G6/G10-G11 内核不暴露；G7-G9/G12 已在 P2/P8 范围；G13 推迟（U1） | subagent 找到 12 类门控分散在 12 处；维持 9 个 Protocol 不变（不开 P10）；明文写门控归属表防认知错位 |
| 7 预算插件覆盖度（关键澄清）| P5 监听 + P6 导出 + AgentBuilder.with_budget(BudgetSpec) 配置参数化；不开新 Protocol；plugin 不能替换内核扩容公式 | subagent 铁证：BudgetController 只**转发事件不执行**；真实 SSOT 在 TaskBudget+ProgressiveExecutor+AgentV3 watchdog+ReACTConfig 4 处分散；macro/micro 独立空间；无 token-level budget |
| 7 §0.3 反插件化障碍新增 R20/R21/R22（**第 8 轮 R20 作废**）| ~~turbo_diagnostics 接入~~（第 8 轮作废）+ micro/macro LLM 计数一致性 + ReACTEngine.\_effective\_max\_iterations 修复 | R20 第 8 轮作废，文档漂移属主仓治理债务；R21/R22 维持 |
| **8 turbo_diagnostics 处理（修订第 7 轮）**| **维持现状不动**（A 方案）：design doc S1.12 重写为"仅暴露 SDK diagnostics facade，不接入 v1"；架构文档与代码漂移属主仓治理债务（不在 SDK 范围）| subagent 第 8 轮调研 5 条铁证：v1 完整设计被 v2（executor_recovery + _diagnose_and_correct）主动替代；prompt/工具集/超时/结论 schema/budget 记账全部不一致；强制接入会引入回归 |
| **8 DomainPack 工作范围**| 扩展为 8 元素：原 4 元素（hint+tool+gate+supplement）+ 第 8 轮新增 4 元素（visual_adapters / mcp_servers / event_listeners / recommended_budget）；全 OPTIONAL；约束铁律"只聚合现有元素 + 不引入新 System 2 行为" | 用户挑战 P9 单独成插件合理性；扩大工作范围使 P9 真正成为"领域统一入口"价值；不破 SSOT/OCP/SRP/DRY |
| **8 SDK 认证模式**| 全面转 API key：with_krow_api_key 替换虚构的 with_krow_session；`AgentBuilder.from_env()` 读 `KROW_API_KEY` 环境变量；Step 1 PR S1.17 必修 dead code | 用户截图证据 + subagent 铁证：（1）krow.cn 已有完整 sk-user-xxx 控制台与 OpenAI 兼容路径；（2）design doc v0.1-v0.6 引用的 `KrowAuthSession` / `login_from_env` 在仓内**完全不存在**（虚构概念）；（3）`AuthService._login_with_api_key → KrowAuthAdapter.set_api_key/get_user_info` 是 dead code（`docs/plan_object_centric_v1_22.md` 标注一致）；API key 是 SDK 嵌入式 / headless 编程场景天然适配 |
| **8 per-plugin api_key 粒度**| 起步用 master api_key + `source_module=PLUGIN_<id>` audit 区分（U18 推迟）| 起步简单；未来若多租户 SaaS / per-plugin 余额隔离强需求再开 |
| **8 PR 状态确认**| PR #174 OPEN/未合并/REVIEW_REQUIRED；元规则 PR 均未建（按 §10.5 触发条件正确）| `gh pr view 174` 状态确认；design doc 第 6/7/8 轮辩论修订均累积在 PR #174 单一 PR（按 §7.7：design doc 不是元规则文件 AGENTS.md，可累积）|
| **9 顶级 review 双视角（v0.8）**| 落地 11 P0 + 10 P1 issue：（A1）plugin signature validator；（A2+A3）Protocol 优先级分层 mvp_critical/stable/experimental + 增减治理协议；（A6）build() 时连接验证；（A7）LLMSourceModule 改 `Union[BuiltinLLMSourceModule, str]`；（A9）supplement 总量上限 16KB/64KB；（A10）EventBusReader 只读 facade；（A13）S1.5 拆 sub-PR + Step 1 估时 44d → 52-78d；（A16）opt-in 反向 telemetry；（D1）import 路径双轨表；（D3）error class 完整 message；（D6）KROW_SDK_PLUGIN_ERROR_MODE；（D7）多租户部署模式子节 | 顶级开发者视角（DX / Day 1-Day 90）+ 顶级架构师视角（5 年生命周期 / Hyrum's Law / npm/pip 历史教训）双视角 review 文档 v0.7；识别 v0.7 设计中的虚假强类型（A1）/ enum frozen 撞墙（A7）/ Hyrum's Law 暴露（A10）/ blast radius 低估（A13）/ swallow 反模式（D6）等多处真问题；元教训："runtime_checkable 不是真强类型；fail-loud 必须真在边界（不延迟到 first run）；plugin ecosystem 健康度需要反向 telemetry" |

## 附录 B：常用 SSOT 路径速查

| 主题 | 路径 |
|---|---|
| AgentV3 入口 | `modules/agent/agent_v3.py:AgentV3` |
| V3 启动 | `modules/agent/v3_bootstrap.py:bootstrap_v3` |
| KrowLLMProvider | `modules/ai/krow/provider.py:KrowLLMProvider` |
| LLMProviderManager | `modules/ai/providers.py:LLMProviderManager` |
| ChatMessage SSOT | `modules/ai/providers.py:ChatMessage`（不是 `modules/ai/krow/provider.py:ChatMessage`） |
| ACTLoader / ACTManager | `modules/agent/act/act_loader.py` / `act_manager.py` |
| ToolManager | `modules/tools/manager.py:ToolManager` |
| GateChain | `modules/knowledge/conclude_guard_gates.py:GateChain` |
| EventBus | `modules/events/bus.py:EventBus` |
| BackgroundTaskQueue | `modules/agent/background_task_queue.py:BackgroundAgentTaskQueue` |
| project_root | `modules/utils/project_context.py:get_project_root / set_project_root` |
| app_root | `modules/utils/portable_path.py:get_app_root` |
| BudgetController | `modules/agent/progressive/budget_controller.py:BudgetController` |
| ToolTraitRegistry | `modules/agent/progressive/tool_traits.py:ToolTraitRegistry` |
| StateManager | `modules/agent/state_manager.py:StateManager` |
| AgentMemoryStore | `modules/agent/memory/store.py:AgentMemoryStore` |
| ExperienceV3Integration | `modules/agent/experience_v3_integration.py:get_experience_integration` |
| SandboxValidator | `modules/remote/security_policy.py:SandboxValidator` |
| Auth | `modules/auth/__init__.py`（CredentialStore / AuthService / KrowAuthAdapter） |
| Billing | `modules/remote/billing_interfaces.py` + `modules/remote/usage_tracker.py` |
| visual_inspect 工具入口 | `modules/agent/visual/visual_grounding_tools.py:handle_visual_inspect` |
| VisualGroundingService | `modules/agent/visual/grounding_service.py:VisualGroundingService` |
| register_visual_adapter | `modules/agent/visual/visual_grounding_tools.py:register_visual_adapter` |
| VisualAdapter 协议 | `modules/agent/visual/protocol.py:VisualAdapter` |
| VERIFY_FIX trait | `modules/agent/progressive/tool_traits.py:ToolTraitRegistry.VERIFY_FIX` |
| verify-fix 执行分支 | `modules/agent/progressive/executor.py`（`_handle_verify_fix_*` 系列方法） |
| EventBus（兼容层）| `modules/events/bus.py:EventBus.get_instance()` |
| EventBusCore（核心 SSOT）| `modules/events/bus_core.py:EventBusCore.get_instance()` |
| AgentV3 callback | `modules/agent/agent_v3.py:AgentV3.__init__`（5 个：on_progress / on_todo_created / on_todo_update / on_thinking / on_report）|
| KrowService FastAPI gateway | `modules/remote/service.py:KrowService` + `modules/remote/api_gateway.py` |
| TaskBudget（macro 真实 SSOT）| `modules/agent/progressive/models.py:TaskBudget` |
| ReACTConfig（micro 预算 SSOT）| `modules/agent/react_engine.py:ReACTConfig` |
| BudgetController.\_FORWARD\_MAP（事件转发，**不执行预算**）| `modules/agent/progressive/budget_controller.py:_FORWARD_MAP` |
| `_handle_adapt_budget_extension`（macro 扩容内核）| `modules/agent/progressive/executor.py`（+5min/次，受动态上限约束）|
| `_compute_dynamic_cap`（动态上限算法）| `modules/agent/progressive/executor.py`（read_time + write_time + 600s overhead）|
| ErrorAccumulator（断路器）| `modules/agent/progressive/executor.py:ErrorAccumulator.should_abort()` |
| ConcludeGuard 9 native gates | `modules/knowledge/conclude_guard_gates_impl.py:Gate1DataLayer / Gate2EvidenceCount / ... / Gate9InferenceSufficiency` + `make_default_chains` |
| ReACTEngine.register_conclude_guard（micro conclude 闸门）| `modules/agent/react_engine.py:ReACTEngine.register_conclude_guard` |
| ToolManager 安全策略 | `modules/tools/manager.py:ToolManager.execute_tool` 内 `security_manager.enforce` |
| Planner snapshot 过滤 | `modules/agent/planner_v3.py:PlannerV3._capture_tool_snapshot` + `_PPTX_PISMA_WHITELIST` |
| Plan 改写（退役工具）| `modules/agent/progressive/plan_task_handler.py:_RETIRED_PPTX_CREATION_TOOLS` + `_guard_pptx_retired_to_propose` |
| ACT 不变量（micro/macro 分离）| `modules/agent/act_hierarchy.py:_assert_no_micro_tool_in_macro_priorities` |
| KnowledgeAPI（数据层 L0/L1/L2 门面）| `modules/knowledge/knowledge_api.py:KnowledgeAPI` |
| SessionOntologyStore.to_view() | `modules/knowledge/reasoning_store.py:SessionOntologyStore` |
| GlobalOntologyStore | `modules/knowledge/global_ontology_store.py:GlobalOntologyStore` |
| ExperienceMemoryService | `modules/agent/experience_memory/sqlite_engine.py:SQLiteGraphEngine` + `experience_memory/models.py` |
| AgentMemoryStore（StateManager 持久化）| `modules/agent/memory/store.py:AgentMemoryStore` + `get_memory_store` |
| turbo_diagnostics（**v1，已被 v2 替代不接入**）| `modules/agent/progressive/turbo_diagnostics.py:should_diagnose_turbo / run_t4_diagnostic / run_t5_exploration` —— 第 8 轮辩论维持现状，仅 unit test 引用 |
| executor_recovery（**v2 真实路径**）| `modules/agent/progressive/executor_recovery.py:quick_diagnosis / assemble_diagnostic_context / parse_diagnostic_conclusion`（模块 docstring 明文"取代 T4-lite + T5-lite"）|
| `_diagnose_and_correct`（**v2 内联 ReACT 诊断**）| `modules/agent/progressive/executor.py:ProgressiveExecutor._diagnose_and_correct` —— 用动态 ReACTConfig name `f"turbo_diagnose_step_{step_id}"`；prompt = `_DIAGNOSTIC_SYSTEM_PROMPT`，结论 = `DiagnosticCorrection` |
| UsageTracker.record（krow cloud 计费维度）| `modules/ai/krow/provider.py:_notify_usage` 内 `UsageTracker.record(input_tokens=..., output_tokens=..., cost_cp=...)`（本地 SQLite 缓存仅展示用，不含 user/api_key 维度；服务端按 api_key 真扣费）|
| KrowAuthAdapter（**第 8 轮辩论修订主链路**）| `modules/auth/krow_auth.py:KrowAuthAdapter`（OAuth + API key 双轨认证；Step 1 PR S1.17 实现 `set_api_key` / `get_user_info` dead code）|
| AuthService.\_login\_with\_api\_key（**第 8 轮辩论 dead code 必修**）| `modules/auth/service.py:AuthService._login_with_api_key`（`password.startswith("sk-")` 分支；调用 `krow_auth.set_api_key` / `get_user_info`，目前两方法未实现）|
| `KROW_API_KEY` 环境变量（SDK 必需）| Step 1 PR S1.17 引入；与 `KROW_HEADLESS_AUTH_*` 族（桌面 OAuth 路径）不冲突；详 §3 |
| `https://api.krow.cn/v1/chat/completions`（OpenAI 兼容 API）| `modules/ai/krow/provider.py:KrowLLMProvider.API_BASE_URL + CHAT_ENDPOINT`（response 含 usage 字段，服务端按 Bearer api_key 计费）|
| **v0.8 plugin signature validator**（A1/R26）| `modules/agent/sdk/_protocol_validator.py:validate_protocol_implementation` —— 启动期 `inspect.signature` + `typing.get_type_hints` 校验 plugin vs Protocol 签名一致性 |
| **v0.8 BuiltinLLMSourceModule**（A7/R27）| `modules/ai/providers.py:BuiltinLLMSourceModule` —— `LLMSourceModule = Union[BuiltinLLMSourceModule, str]` type alias；plugin 用 `make_plugin_source_module(plugin_id) -> str` |
| **v0.8 EventBusReader**（A10）| `modules/agent/sdk/events.py:EventBusReader` —— 只读 facade（subscribe/unsubscribe/iter_recent，无 publish/内部状态）|
| **v0.8 BuilderConfig**（A5）| `modules/agent/sdk/builder.py:BuilderConfig` + `PluginLoaders` + `HTTPGatewayConfig` —— dataclass 替代部分链式 with_* |
| **v0.8 Telemetry endpoint**（A16）| `https://api.krow.cn/sdk/telemetry/v1/anonymous` —— opt-in 反向 telemetry（KROW_SDK_TELEMETRY=1 启用）|
| **v0.8 BasePluginLifecycle**（D5）| `modules/agent/sdk/protocols/lifecycle.py:BasePluginLifecycle` —— on_load(sdk_context) / on_unload() OPTIONAL mixin |
| **v0.8 import alias**（D1）| `modules/agent/sdk/__init__.py` 内 `sys.modules.setdefault("krow_agent_sdk", sys.modules[__name__])` |
| **v0.8 experimental Protocol namespace**（A2）| `modules/agent/sdk/experimental/protocols/` —— P7/P8/P9 单独 namespace + feature flag default off |

## 附录 C：CI workflow 影响清单

按 `AGENTS.md` (internal) §八 CI workflow 表，本设计对 CI 的影响：

| workflow | Step 1 影响 | Step 2 影响 |
|---|---|---|
| `lint.yml` | 加 `tests/sdk/` 路径到 test-naming lint | 同 |
| `unit.yml` | 加 `tests/sdk/` 契约测试（含 P9 DomainPackPlugin 骨架） | 同 |
| `contracts.yml` | 加 plugin 协议契约测试（warning-only 起步，1 sprint 后转硬阻塞）；含 P9 supplement 4000 字符上限 + prompt 注入扫描契约 | feature flag KROW_ENABLE_PLUGIN_ENTRY_POINTS=1 跑全套契约测试 + plugin 兼容性矩阵 + P9 多 pack 共存矩阵 |
| `headless.yml` | 加 `krow_test_sdk` collection 测试 | 同 |
| `nightly.yml` | 不变 | 加真实 LLM plugin demo e2e + 真实 VLM `visual_inspect` 验证（按 `AGENTS.md` (internal) §4.1 预期结果卡） |
| `build-lite.yml` / `build-full.yml` | 不变 | 不变 |

---

**文档结束**。审阅请填 §12.3 Open Questions 答案，落地决策走 design-doc PR review；实现按 §9 路线图分步发 PR。

