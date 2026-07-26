# Krow Agent SDK · API Reference Manual

> **版本**：`krow-agent-sdk == 0.8.12.5`（Step 2 完成）
> **最后更新**：2026-05-16
> **稳定性级别**：**Stable**（除"⚠️ experimental"标记的 API 外，其余 API 遵循 SemVer）
> **配套文档**：
> - [`quickstart.md`](./quickstart.md) — 5 分钟入门
> - [`advanced-development-guide.md`](./advanced-development-guide.md) — TURBO 哲学、设计原则、最佳实践
> - [`runtime-install.md`](./runtime-install.md) — sdk-runtime wheel 安装

---

## 目录

- [§0. 概述与稳定性承诺](#0-概述与稳定性承诺)
- [§1. 安装与最小入门](#1-安装与最小入门)
- [§2. `AgentBuilder` — 构造器链式 API](#2-agentbuilder--构造器链式-api)
  - [§2.1 必须项](#21-必须项)
  - [§2.2 工厂方法](#22-工厂方法)
  - [§2.3 LLM 模型选择 API（6 类）](#23-llm-模型选择-api6-类)
  - [§2.4 预算与 HTTP Gateway](#24-预算与-http-gateway)
  - [§2.5 Plugin 直接注入（6 stable + 3 experimental）](#25-plugin-直接注入6-stable--3-experimental)
  - [§2.6 Visual Adapter 注入（3 路径）](#26-visual-adapter-注入3-路径)
  - [§2.6.1 Document Parser 注入（2 路径）](#261-document-parser-注入2-路径)
  - [§2.7 entry_points 自动发现（8 个 + 1 个 all）](#27-entry_points-自动发现8-个--1-个-all)
  - [§2.8 测试注入](#28-测试注入)
  - [§2.9 LLM Record/Replay 接入](#29-llm-recordreplay-接入)
  - [§2.10 `build()` — 构造 Agent](#210-build--构造-agent)
- [§3. `Agent` — 运行时实例 API](#3-agent--运行时实例-api)
  - [§3.1 `Agent.run()` — 阻塞式同步执行](#31-agentrun--阻塞式同步执行)
  - [§3.2 `Agent.run_stream()` — 流式执行](#32-agentrun_stream--流式执行)
  - [§3.3 `Agent.shutdown()` — 资源清理](#33-agentshutdown--资源清理)
  - [§3.4 Agent 只读属性](#34-agent-只读属性)
  - [§3.5 HITL 挂起/续跑 — `with_hitl` / `Agent.resume`](#35-hitl-挂起续跑--with_hitl--agentresume)
- [§4. 配置 dataclass](#4-配置-dataclass)
  - [§4.1 `BudgetSpec`](#41-budgetspec)
  - [§4.2 `BuilderConfig`](#42-builderconfig)
  - [§4.3 `HttpGatewaySpec`](#43-httpgatewayspec)
- [§5. Plugin Protocols（核心扩展点）](#5-plugin-protocolsstable6--3-experimental)
  - [§5.1 `ACTPlugin` — 加新 ACT (P1)](#51-actplugin--加新-act-p1)
  - [§5.2 `ToolPlugin` — 加新工具 (P2)](#52-toolplugin--加新工具-p2)
  - [§5.3 `HintPlugin` — 加新软提示 (P3)](#53-hintplugin--加新软提示-p3)
  - [§5.4 `GatePlugin` — 加新 ConcludeGuard Gate (P4)](#54-gateplugin--加新-concludeguard-gate-p4)
  - [§5.5 `EventListenerPlugin` — 订阅 EventBus (P5)](#55-eventlistenerplugin--订阅-eventbus-p5)
  - [§5.6 `ObservabilityPlugin` — Metrics/Traces 转发 (P6)](#56-observabilityplugin--metricstraces-转发-p6)
  - [§5.7 `MCPServerPlugin` — MCP Server (P7, ⚠️ experimental)](#57-mcpserverplugin--mcp-server-p7--experimental)
  - [§5.8 `SecurityPlugin` — 安全策略 (P8, ⚠️ experimental)](#58-securityplugin--安全策略-p8--experimental)
  - [§5.9 `DomainPackPlugin` — 一站式 (P9, ⚠️ experimental)](#59-domainpackplugin--一站式-p9--experimental)
  - [§5.10 `VisualAdapterPlugin` — 视觉适配器 (P10, ⚠️ experimental)](#510-visualadapterplugin--视觉适配器-p10--experimental)
  - [§5.11 `DocumentParserPlugin` — 文档解析器 (P11)](#511-documentparserplugin--文档解析器-p11)
- [§6. EventBus 与流式事件](#6-eventbus-与流式事件)
  - [§6.1 `EventBusReader`](#61-eventbusreader)
  - [§6.2 `StreamItem` / `StreamItemKind`](#62-streamitem--streamitemkind)
  - [§6.3 稳定 topic 速查](#63-稳定-topic-速查)
- [§7. LLM Record/Replay 框架](#7-llm-recordreplay-框架)
  - [§7.1 `LLMReplayStore`](#71-llmreplaystore)
  - [§7.2 `LLMReplayMiss` / `LLMReplayError`](#72-llmreplaymiss--llmreplayerror)
  - [§7.3 `wrap_provider_manager_with_replay`](#73-wrap_provider_manager_with_replay)
  - [§7.4 `compute_request_hash` / `ReplayRecord`](#74-compute_request_hash--replayrecord)
- [§8. Auth / LLM / Data Facade](#8-auth--llm--data-facade)
  - [§8.1 `auth` — API key 校验](#81-auth--api-key-校验)
  - [§8.2 `llm` — Plugin source helper](#82-llm--plugin-source-helper)
  - [§8.3 `data` — 只读数据 facade](#83-data--只读数据-facade)
- [§9. Diagnostics / Hints / Visual / Lifecycle](#9-diagnostics--hints--visual--lifecycle)
  - [§9.1 `diagnostics` — 状态导出](#91-diagnostics--状态导出)
  - [§9.2 `hints` — Hint Registry](#92-hints--hint-registry)
  - [§9.3 `visual` — VisualAdapter 与 visual_inspect](#93-visual--visualadapter-与-visual_inspect)
  - [§9.4 `lifecycle` — 生命周期 hook](#94-lifecycle--生命周期-hook)
  - [§9.5 `extended_md_supplement_registry` — ACT 扩展 markdown](#95-extended_md_supplement_registry--act-扩展-markdown)
  - [§9.6 `metacognition` — 配置决策脑三注册表](#96-metacognition--配置决策脑三注册表)
- [§10. Telemetry 反向遥测](#10-telemetry-反向遥测)
- [§11. Test SDK — 开发者写 plugin 的测试工具](#11-test-sdk--开发者写-plugin-的测试工具)
- [§12. Errors — 错误层与黄金模板](#12-errors--错误层与黄金模板)
- [§13. 环境变量与 feature flag 速查](#13-环境变量与-feature-flag-速查)
- [§14. 版本兼容性 / 稳定性 / Deprecation](#14-版本兼容性--稳定性--deprecation)
- [§15. 附录：常用 import 速查](#15-附录常用-import-速查)

---

## §0. 概述与稳定性承诺

`krow-agent-sdk` 是 Krow 智能体平台的 **官方 Python SDK**，让外部开发者可以：

1. **快速接入 Krow Cloud LLM**（无需 prompt 工程，开箱即用 macro/micro ReACT 双层 ReAct + budget 控制 + concluce guard）
2. **写 plugin 扩展核心能力**（加 ACT / 工具 / 视觉适配器 / hint / gate / event listener / observability sink）
3. **录制回放 LLM 调用**（确定性单测 + 真实 LLM e2e 双轨）
4. **接 HTTP/WS Gateway 给前端 UI**（PR A3 / S1.15）

### 稳定性等级（SemVer 承诺）

| Level | API 范围 | 修改语义 |
|---|---|---|
| **Stable** | `AgentBuilder` 主链 / `Agent.run` / `BudgetSpec` / 6 个 stable Plugin Protocols / `EventBusReader` / `StreamItem` / 错误类 / `auth` / `llm` / `data` / `diagnostics` / `metacognition` 公开函数 | breaking 变更必须 MAJOR bump + 提前 1 release deprecation 警告 |
| **⚠️ Experimental** | `mcp_server` / `security` / `domain_pack` / `visual_adapter` Plugin 协议、`HttpGatewaySpec`、Wave 4 `test_sdk`、telemetry | 无 breaking 通知；可在 MINOR 版本删除 / 改名（详 §14） |
| **Internal** | 模块名以 `_` 开头（`_plugin_id_validator`、`_protocol_validator`、`_vendor`） | 不在公开 API；任何 release 都可改 |

### 版本与 Python 兼容

| 维度 | 要求 |
|---|---|
| Python | `>= 3.11`（3.11 / 3.12 / 3.13 全官方支持） |
| OS | Linux x86_64 / macOS arm64 / Windows x86_64 |
| 依赖 | `httpx>=0.27` / `pydantic>=2.5` / `rich>=13.7`（自动 pull） |
| Optional extras | `[visual]`（cairosvg + Pillow + lxml）/ `[http]`（FastAPI + uvicorn） |

---

## §1. 安装与最小入门

### §1.1 安装

```bash
# 标准安装（含 record/replay + 主路径功能）
pip install krow-agent-sdk

# 含 PPTX 视觉质检管线（HeadlessPPTXVisualAdapter）
pip install krow-agent-sdk[visual]

# 含 HTTP/WS gateway（外部 UI 接入）
pip install krow-agent-sdk[http]

# 全功能
pip install krow-agent-sdk[visual,http]
```

### §1.2 最小可运行例

```python
import os
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key(os.environ["KROW_API_KEY"])  # sk-user-xxxxx
    .with_project_root("/data/myproject")
    .build()
)
try:
    result = agent.run("帮我把今天会议纪要整理成 markdown")
    if result.success:
        print(result.final_output)
    else:
        print(f"任务失败: {result.execution_result}")
finally:
    agent.shutdown()
```

### §1.3 完整 import 路径

```python
# 主入口
from krow_agent_sdk import (
    AgentBuilder, Agent, BudgetSpec, BuilderConfig, HttpGatewaySpec,
    # Plugin Protocols (6 stable)
    ACTPlugin, ToolPlugin, GatePlugin,
    HintPlugin, EventListenerPlugin, ObservabilityPlugin,
    # 流式
    StreamItem, StreamItemKind, EventBusReader,
    # Lifecycle
    BasePluginLifecycle, SDKContext,
    # 顶层 facade
    diagnostics, data, hints,
    auth, llm, errors, lifecycle, events,
    # Step 2 P2 visual
    visual,
    # 进阶
    replay, telemetry, deprecation, entry_points,
    extended_md_supplement_registry,
    # 子模块 namespace
    experimental,
)

# Experimental Protocols（不稳定，可能在 MINOR 改）
from krow_agent_sdk.experimental.protocols import (
    MCPServerPlugin, SecurityPlugin, DomainPackPlugin, VisualAdapterPlugin,
)

# 错误类（fail-loud 边界）
from krow_agent_sdk.errors import (
    KrowSDKError,                    # 根基类
    MissingKrowAPIKeyError, InvalidKrowAPIKeyError, InvalidKrowBaseURLError,
    KrowAPIKeyInvalidError, KrowQuotaExceededError, LLMProviderError,
    MissingProjectRootError, ProjectRootNotWritableError,
    PluginSignatureMismatchError, InvalidPluginIDError,
    DuplicatePluginIDError, PluginLoadError,
)
```

### §1.4 双 import 路径（开发期 alias）

历史原因，主仓 monorepo 内 `from modules.agent.sdk import AgentBuilder` 也能 work（开发期等价 alias）。**对外开发者推荐**统一用 `from krow_agent_sdk import AgentBuilder`。

---

## §2. `AgentBuilder` — 构造器链式 API

`AgentBuilder` 是构造 `Agent` 实例的 **唯一 SDK 入口**。所有方法**返回 `self`**（fluent / 链式），方便链式拼接。

### §2.1 必须项

#### `with_krow_api_key(api_key: str) -> AgentBuilder`

| 字段 | 说明 |
|---|---|
| `api_key` | 形如 `sk-user-xxxxx`；从 [krow.cn](https://krow.cn) API 密钥页面创建 |
| **格式校验** | 立即校验：非 `sk-` 前缀 / 空字符串 → 抛 [`InvalidKrowAPIKeyError`](#12-errors--错误层与黄金模板) |
| **建议** | 优先用 [`AgentBuilder.from_env()`](#22-工厂方法) 从 env var 读取，避免 secret 进代码 |

```python
agent = AgentBuilder().with_krow_api_key("sk-user-abc123").with_project_root("/data/x").build()
```

#### `with_project_root(path: str | Path) -> AgentBuilder`

| 字段 | 说明 |
|---|---|
| `path` | 项目根目录绝对路径；自动 `expanduser().resolve()` |
| **作用** | native 工具（`document_reader` / `pptx_editor` / `native_fileops` 等）的 SSOT 根目录；多 agent 实例**不能共享**同一 root |
| **缺失** | `build()` 时抛 [`MissingProjectRootError`](#12-errors--错误层与黄金模板) |
| **不可写** | `build(validate_connection=True)`（默认 True）触发写权限测试，失败抛 [`ProjectRootNotWritableError`](#12-errors--错误层与黄金模板) |

---

### §2.2 工厂方法

#### `AgentBuilder.from_env() -> AgentBuilder` (classmethod)

从环境变量读 `KROW_API_KEY` + `KROW_PROJECT_ROOT`，等价手动调 2 个 with_* 方法。

| env var | 缺失行为 |
|---|---|
| `KROW_API_KEY` | 抛 [`MissingKrowAPIKeyError`](#12-errors--错误层与黄金模板) |
| `KROW_PROJECT_ROOT` | builder._project_root 留空；后续不调 `with_project_root` 则 `build()` 时抛 [`MissingProjectRootError`](#12-errors--错误层与黄金模板) |

```python
import os
os.environ["KROW_API_KEY"] = "sk-user-xxx"
os.environ["KROW_PROJECT_ROOT"] = "/data/x"
agent = AgentBuilder.from_env().build()
```

#### `AgentBuilder.from_config(config: BuilderConfig) -> AgentBuilder` (classmethod)

一次性从 [`BuilderConfig`](#42-builderconfig) dataclass 配置（生产推荐路径，避免 `with_*` 链长到难维护）。

```python
from krow_agent_sdk import AgentBuilder, BuilderConfig, BudgetSpec
from pathlib import Path

cfg = BuilderConfig(
    api_key="sk-user-xxx",
    project_root=Path("/data/x"),
    budget=BudgetSpec(max_total_llm_calls=80),
    tool_plugins=[my_tool_plugin],
)
agent = AgentBuilder.from_config(cfg).build()
```

---

### §2.3 LLM 模型选择 API（6 类）

> Builder time 显式指定每类模型 ID。云端清单走 `GET https://api.krow.cn/v1/models`（按 `is_<category>` 字段筛）。
> **设计协议**（专家辩论 chore/sdk-model-selection-api 方案 B）：
> - **System 1 边界** — 模型选择是确定性查表，**不允许 per-call override**（防 LLM 决定 LLM）
> - 未指定 → 走 cloud-model fallback（与现有行为完全一致；零 breaking 风险）
> - 同一 builder 实例对同 category 调多次 → 最后一次胜出

| 方法 | 类别 | 典型 model_id | 用途 |
|---|---|---|---|
| `with_chat_model(model_id)` | `chat` | `qwen3.6-plus` / `deepseek-chat` | 通用对话 / 代码生成 / planner 主路径 |
| `with_reasoning_model(model_id)` | `reasoning` | `deepseek-v4-pro` | 深度推理 / 思维链 / replan / verify |
| `with_vision_model(model_id)` | `vision` | `qwen2.5-vl-72b-instruct` | 视觉理解（visual_inspect / context_enhancer） |
| `with_image_gen_model(model_id)` | `image_gen` | `qwen-image` | 图像生成 |
| `with_image_edit_model(model_id)` | `image_edit` | `qwen-image-edit` | 图像编辑 |
| `with_text_encoder_model(model_id)` | `text_encoder` | `text-embedding-v2` | embedding / vector search |

```python
agent = (
    AgentBuilder()
    .with_krow_api_key(os.environ["KROW_API_KEY"])
    .with_project_root("/data/x")
    .with_chat_model("qwen3.6-plus")
    .with_reasoning_model("deepseek-v4-pro")
    .with_vision_model("qwen2.5-vl-72b-instruct")
    .build()
)
```

| 错误 | 触发 |
|---|---|
| `ValueError` | `model_id` 非空字符串 / 非 str |
| Cloud rejects | build() 后首次调用 LLM 时若 cloud /v1/models 不含该 model_id → log warning + fallback 默认（与未指定行为一致） |

---

### §2.4 预算与 HTTP Gateway

#### `with_budget(budget: BudgetSpec) -> AgentBuilder`

注入预算配置（详 [§4.1 BudgetSpec](#41-budgetspec)）。

```python
from krow_agent_sdk import BudgetSpec
agent = (
    AgentBuilder()
    .with_krow_api_key(...).with_project_root(...)
    .with_budget(BudgetSpec(max_total_llm_calls=60, max_walltime_s=900))
    .build()
)
```

#### `with_reasoning_artifacts(enable: bool = True) -> AgentBuilder` (PR-A · 2026-07-06)

启用**推理结构化产物出口**（默认关闭，零回归）。启用后 `build()` 挂载 `ReasoningResultRouter`（零 UI 依赖，与桌面 / E2E harness 共用 `init_reasoning_result_router` SSOT 入口）：推理任务（`reasoning_pipeline` ACT / reasoning 策略）收尾时自动把结构化 `ReasoningResult`（假设 / 证据 / ACH 矩阵 / 疑点 / 递归推理树 / 完整度记分卡）落盘到 `<project_root>/.krow/reasoning/{id}.json`，并发布 `reasoning.result_ready` 事件（含 `reasoning_id` + `result_path`）。

读取产物走 [§8.3 data facade](#83-data--只读数据-facade) 的 `get_reasoning_result` / `list_reasoning_results`。

> Router 是进程级单例（与桌面同语义）：同进程多 Agent 同时启用时，后 build 的实例接管（先前实例订阅被 close）。

```python
from krow_agent_sdk import AgentBuilder, data

agent = (
    AgentBuilder()
    .with_krow_api_key(os.environ["KROW_API_KEY"])
    .with_project_root("/data/case")
    .with_reasoning_artifacts()          # ← 开启结构化产物落盘
    .build()
)
agent.run(
    "谁是真凶？用竞争假设排除法逐条核验证据。",
    task_context={"source": "reasoning_panel", "act_name": "reasoning_pipeline",
                  "strategy": "hypothesis_test"},
)
result = data.get_reasoning_result()      # 最新一条（headless，与桌面同一份产物）
print(result["hypotheses"], result["metadata"].get("completeness_scorecard"))
```

#### `with_tool_execution_timeout(timeout: int | dict[str, int]) -> AgentBuilder` (FR-2 · 2026-06-15)

设置**单工具执行超时**。micro ReACT 单次工具调用默认硬超时仅 30s（内置
`long_running` 工具 300s），且**动态注册的 MCP 工具进不了静态 trait 表** → 长耗时
工具（CAE 网格剖分 10–15min、装配导入 ~280s、离线建库）会被误杀并触发整步重试。

本 API 是替代对 `ReACTEngine.TOOL_EXECUTION_TIMEOUT` / `ToolTraitRegistry` 等
internal 符号做 monkey-patch 的**公开**入口（patch internal 符号 SDK 升级即静默失效）。

| 入参形态 | 语义 |
|---|---|
| `int`（全局） | 所有工具步执行超时的**下限**（不缩短既有 `long_running` / `verify_fix` 保护） |
| `{tool_name: seconds}`（per-tool） | 对指定工具**精确生效**（"指定即采用"，可长可短，优先级最高） |

- **上限**：3600s（`AgentBuilder.TOOL_EXEC_TIMEOUT_HARD_CAP`）。超限 / ≤0 / 非正整数
  / 空 dict / 空工具名 → 立即抛 `ValueError`（fail-loud，防旁路注入超大值拖死无人值守 Pod）。
- **优先级**：显式 `with_tool_execution_timeout` > `BudgetSpec.tool_execution_timeout_s`
  （`from_config` 路径可经 `BudgetSpec` 字段配同一全局下限）。
- **per-run 覆盖**：等价于在 `Agent.run(task_context={"tool_execution_timeout": ...})`
  注入；builder 默认值用 `setdefault` 语义，per-run 显式值优先。

```python
# 全局下限：所有工具步至少 280s
agent = (
    AgentBuilder().with_krow_api_key(...).with_project_root(...)
    .with_tool_execution_timeout(280)
    .build()
)

# per-tool 精确：CAE 网格剖分单独给 900s，其余不变
agent = (
    AgentBuilder().with_krow_api_key(...).with_project_root(...)
    .with_tool_execution_timeout({"cae_mesh_solve": 900, "cae_assembly_import": 300})
    .build()
)
```

#### `with_base_url(url: str) -> AgentBuilder` (W4 新增 · staging / 私有部署)

覆盖默认 cloud API base URL（`https://api.krow.cn`），用于：

- **Pilot / Staging 联调**：`https://api-staging.krow.cn` 走 SDK team 内部环境（需 `pk-pilot-` key 配套）
- **私有化部署 (on-prem)**：客户自建 gateway，如 `https://krow-gateway.acme.internal`
- **自动化测试**：本地 mock gateway 端口（如 `https://127.0.0.1:18443` 走自签证书）

| 字段 | 说明 |
|---|---|
| `url` | 完整 HTTPS base URL，**必须** `https://` 前缀；**禁止**尾部斜杠；**禁止**含 path 段 |
| **格式校验** | 立即校验：违反任一规则 → 抛 [`InvalidKrowBaseURLError`](#12-errors--错误层与黄金模板) |
| **作用域** | 注入到 3 处 SSOT（`config.settings.module_interfaces.krow.api_base_url` / 已注册 `LLMProvider.api_url` / `KrowLLMProvider._api_base`）；所有 LLM / image / OCR / metadata 调用均路由到该 URL |
| **不调** | 默认走 `https://api.krow.cn`（生产）|
| **多次调** | 后调覆盖前调（last-call-wins） |

```python
# 1. Staging 联调（pk-pilot- key）
agent = (
    AgentBuilder()
    .with_krow_api_key("pk-pilot-xxx")
    .with_base_url("https://api-staging.krow.cn")  # 走 staging
    .with_project_root("/data/x")
    .build()
)

# 2. 私有化部署
agent = (
    AgentBuilder()
    .with_krow_api_key("sk-tenant-xxx")
    .with_base_url("https://krow-gateway.acme.internal")
    .build()
)
```

| 错误（[`InvalidKrowBaseURLError`](#12-errors--错误层与黄金模板)） | 触发 |
|---|---|
| `非 HTTPS` | `http://api.krow.cn` / `ws://...` 等非 https |
| `含尾部斜杠` | `https://api.krow.cn/` |
| `含 path 段` | `https://api.krow.cn/v1` / `.../api` 等 |
| `空字符串` | `with_base_url("")` |

> **何时不需要调**：用 `sk-` 生产 key + 默认 `https://api.krow.cn` → **不要**调；调了反而会被 cloud 拒（cross-tenant）。
> **常见踩坑**：把 `with_base_url("https://api.krow.cn/v1")` 写成带 `/v1` 后缀 — SDK 会内部加 `/v1/...`，导致最终 URL 变 `/v1/v1/chat/completions` 404。

#### `with_http_gateway(*, enable=True, host="127.0.0.1", port=8090, auth_token=None, dry_run=False) -> AgentBuilder` (⚠️ experimental)

启用 HTTP / WS / SSE 网关，让外部 UI 通过 HTTP 接 SDK Agent。详 [§4.3 HttpGatewaySpec](#43-httpgatewayspec)。

| 参数 | 默认 | 说明 |
|---|---|---|
| `enable` | `True` | 是否启用 |
| `host` | `127.0.0.1` | 仅本地；生产可 `0.0.0.0` |
| `port` | `8090` | 避开 KrowService 9527 |
| `auth_token` | `None` | 预留 bearer middleware（Wave B 实现） |
| `dry_run` | `False` | 测试用；不真启 uvicorn |

> 需要 `krow-agent-sdk[http]` extra 才能启动 uvicorn。
> Feature flag 双轨：env `KROW_SDK_HTTP_GATEWAY=1` 也能默认启用。

---

### §2.4.1 Persona 身份控制 + 多 Agent 轻量协同（A 层 + B 层 · v0.9.0.31+）

面向「多 agent 分工」场景的两层能力：A 层给每个 agent 注入**最高优先级身份与行为准则**（类比 `AGENTS.md` / `CLAUDE.md`），B 层让组长 agent 把子任务**委派**给组员 agent。

> 典型痛点：组长 agent 本应把活分给组员，却总是自己干。根因有二——(1) 默认 macro 基座身份是「任务规划与执行指挥官」，prompt 还含「必须包含至少一个执行步骤」等自执行指令；(2) 组长手上没有委派工具（能力缺失）。A 层解 (1)，B 层解 (2)，二者配合才彻底。

#### `with_agent_identity(identity: str) -> AgentBuilder` （A 层）

覆盖 macro 基座的默认身份描述（一句话角色定义）。注入到 system prompt 身份段。

| 入参 | 说明 |
|---|---|
| `identity` | 非空字符串；空 / 纯空白 → `ValueError`（fail-loud）；超 `AGENT_IDENTITY_MAX_CHARS` 上限 → `ValueError` |

#### `with_persona_directives(directives: str) -> AgentBuilder` （A 层）

注入**全局最高优先级行为准则**（可多段）。物理位置：紧跟安全红线之后的 `CRITICAL` 段（primacy 效应），并在 prompt 末尾追加一条「冲突时以行为准则为准」的提醒（recency 效应）——利用 LLM 注意力 U 型曲线双重强化。当身份要求（如「只分配不执行」）与默认规则（如「必须有执行步骤」）冲突时，以本准则为准。

| 入参 | 说明 |
|---|---|
| `directives` | 非空字符串；空 / 纯空白 → `ValueError`；超长 → `ValueError` |

#### `with_team_member(name: str, member: Agent | Callable[[str], dict], *, description: str = "") -> AgentBuilder` （B 层）

注册一个组员 agent。注册 ≥1 个后，`build()` **自动给组长注入 `delegate_to_member` 工具**（组长无需手写工具）。

| 入参 | 说明 |
|---|---|
| `name` | 组员名称，组长用它寻址；同一组长内唯一。空 / 重复 → `ValueError` |
| `member` | **SDK `Agent` 实例**（同进程委派，最常用）；或 **`Callable[[str], dict]` runner**（自定义传输，如子进程 / HTTP gateway，用于跨进程协同），入参子任务字符串、返回标准结果 dict（至少含 `summary` / `success`）。其他类型 → `ValueError` |
| `description` | 组员能力简介，写进委派工具描述帮组长选人 |

委派结果 dict 形状：`{"ok", "success", "summary", "output_files", "duration_seconds", "member"}`。

> **并发约束**：同一 `Agent` 实例不可重入 / 并发 `run`（见 `Agent._run_lock`）。同进程委派**串行**执行（组员 run 期间组长阻塞），不同组员实例各自独立。**禁止**把组长自身注册成自己的组员（重入必炸）。
> **边界**：本 API 覆盖**轻量**协同（少量组员、串行 / 自定义传输）。重量级分布式高并发多 agent 编排由 Krow Cloud 云端方案承载，不在 SDK 内实现。

完整示例（组长 + 2 组员）：

```python
from krow_agent_sdk import AgentBuilder

researcher = (
    AgentBuilder().from_env()
    .with_agent_identity("你是严谨的资料研究员，负责列要点、核查事实。")
    .build()
)
writer = (
    AgentBuilder().from_env()
    .with_agent_identity("你是文案撰写员，负责把要点润色成通顺文字。")
    .build()
)

leader = (
    AgentBuilder().from_env()
    .with_agent_identity("你是项目组长，负责拆解任务并分配给组员，不亲自执行。")
    .with_persona_directives(
        "收到任务后必须用 delegate_to_member 把子任务派给组员；"
        "检索类派给 researcher，撰写类派给 writer；你只分配与汇总，不自己执行。"
    )
    .with_team_member("researcher", researcher, description="资料搜集与事实核查")
    .with_team_member("writer", writer, description="把要点润色成通顺文字")
    .build()
)

result = leader.run("准备一段关于太阳能两个优点的简短介绍。")
print(result.final_output)
```

跨进程协同：把 `member` 传成自定义 runner（`Callable[[str], dict]`），在 runner 内通过 `subprocess` 或 HTTP gateway 调用另一进程的 member agent 即可。指南见 `advanced-development-guide.md` §11。

---

### §2.4.2 对话槽硬锁 ACT + 工具宇宙裁剪（v0.9.0.33+）

**解决的问题**：默认 SDK 把「用哪个 ACT」交给 macro LLM 决策——`task_context.act_name` 只是**软提示**（把该 ACT 的引导置顶 + 完整披露，但**不禁止**切换、**不裁**工具）。对话槽里的 `team_leader` agent 因此可能被语义选择器 / LLM 漂移到内置写作 ACT，导致它的派单工具（如 `tl.create_task`）不在 macro 工具视野里 → 组长既不能自办又找不到派单工具的**死路**。本特性提供**确定性硬锁**。

#### `with_locked_act(act_name: str, *, tool_universe: str = "global") -> AgentBuilder`

硬锁 agent 到指定 ACT：①**抑制其它 ACT** 的引导 / 菜单（macro LLM 看不到别的 ACT 作为可选项 → 杜绝漂移）；②**保证锁定 ACT 的工具在 macro 工具快照中可见**。

| 入参 | 说明 |
|---|---|
| `act_name` | 要锁定的 ACT 名（内置如 `"pptx_studio"`，或 `ACTPlugin.act_name` 如 `"team_leader"`）。空 / 纯空白 → `ValueError` |
| `tool_universe` | `"global"`（默认 · 仅锁 ACT + 保证工具可见，工具宇宙不裁）或 `"act_only"`（额外把 macro prompt 工具宇宙裁到「该 ACT 工具 + **内部工具**」）。非法值 → `ValueError` |

**只裁 prompt，不动注册表**：`act_only` 仅裁剪发给 LLM 的工具快照；`ToolManager` 注册表保持全量 → `lookup_tool_docs` 逃生口仍在，且内部工具（`llm_generate` / `run_step` / `native.*` / `editor.*` / `knowledge.*` / `kg_*` / `kb_*` / `krow_*` / `lookup_tool_docs` / `deep_reflect`）**永远保留**，绝不被裁。解析不到该 ACT 的工具集时**自动回退为不裁**（宁可多给工具，不误删派单工具）。

每次 `run` 默认注入 `act_name` / `lock_act=true` / `tool_universe`；**per-run `task_context` 同名键优先**（可临时解锁 / 改宇宙）。

#### 等价的 per-request `task_context` 键（Krow Cloud / 非 Python 集成）

不经 Python builder 时，直接在 `run(task_context=...)`（或服务端请求）里传：

| 键 | 类型 | 默认 | 语义 |
|---|---|---|---|
| `act_name` | str | — | 要锁定 / 提权的 ACT 名 |
| `lock_act` | bool | `false` | `true` = 硬锁 `act_name` + 抑制其它 ACT 引导/菜单 |
| `tool_universe` | `"act_only"` \| `"global"` | `"global"` | `act_only` = 裁 macro prompt 工具宇宙到「该 ACT 工具 + 内部工具」 |

**fail-loud 校验**（仅校验这三个新键，不波及其它 `task_context` 键）：`lock_act` 非 bool、`tool_universe` 取值非法、`lock_act=true` 缺 `act_name`、`tool_universe="act_only"` 未配 `lock_act=true` → 抛 `ACTLockValidationError`（`ValueError` 子类）。缺省零回退、任务槽（`act="self"`）零影响。

```python
from krow_agent_sdk import AgentBuilder

leader = (
    AgentBuilder().from_env()
    .with_act_plugin(team_leader_act_plugin)     # 声明 team_leader ACT + tl.create_task
    .with_tool_plugin(dispatch_tool_plugin)      # 注册 tl.create_task
    .with_locked_act("team_leader", tool_universe="act_only")
    .with_agent_identity("你是项目组组长，只拆解 + 派单，绝不亲自撰写正文。")
    .with_persona_directives("必须用 tl.create_task 派单；禁止用写作/文件工具自办。")
    .build()
)
result = leader.run("产出一份市场调研简报，拆解后派给团队成员。")
```

等价 per-run 写法（临时锁定单轮）：

```python
agent.run(task, task_context={"act_name": "team_leader", "lock_act": True, "tool_universe": "act_only"})
```

> 何时用 `with_locked_act` vs `act_name`？需要**确定性**禁止漂移（对话槽固定角色 agent）→ `with_locked_act`。只想**优先**某 ACT 但仍允许 LLM 跨域兜底 → 只传 `act_name`（软提示）。

---

### §2.5 Plugin 直接注入（6 stable + 3 experimental）

| 方法 | 协议 | 稳定性 | 详见 |
|---|---|---|---|
| `with_act_plugin(plugin)` | [`ACTPlugin`](#51-actplugin--加新-act-p1) | Stable | §5.1 |
| `with_tool_plugin(plugin)` | [`ToolPlugin`](#52-toolplugin--加新工具-p2) | Stable | §5.2 |
| `with_hint_plugin(plugin)` | [`HintPlugin`](#53-hintplugin--加新软提示-p3) | Stable | §5.3 |
| `with_gate_plugin(plugin)` | [`GatePlugin`](#54-gateplugin--加新-concludeguard-gate-p4) | Stable | §5.4 |
| `with_event_listener_plugin(plugin)` | [`EventListenerPlugin`](#55-eventlistenerplugin--订阅-eventbus-p5) | Stable | §5.5 |
| `with_observability_plugin(plugin)` | [`ObservabilityPlugin`](#56-observabilityplugin--metricstraces-转发-p6) | Stable | §5.6 |
| `with_mcp_server_plugin(plugin)` | [`MCPServerPlugin`](#57-mcpserverplugin--mcp-server-p7--experimental) | ⚠️ experimental | §5.7 |
| `with_security_plugin(plugin)` | [`SecurityPlugin`](#58-securityplugin--安全策略-p8--experimental) | ⚠️ experimental | §5.8 |
| `with_domain_pack_plugin(plugin)` | [`DomainPackPlugin`](#59-domainpackplugin--一站式-p9--experimental) | ⚠️ experimental | §5.9 |

每个方法的入参均为该 Protocol 的实现实例。多次调用自然累加（不会替换）。

> **声明式领域包（非 plugin 路径）**：知识编译（`strategy=knowledge_compile`）场景下，
> 激活/扩展领域本体**无需写 plugin**——直接 `.with_domain_pack("k12_math")` 激活内置包，
> 或 `.with_domain_pack_manifest("my_pack.yaml")` 程序化注册自定义包（支持 `parent_pack`
> 继承）。指定不存在的 pack_id → `UnknownDomainPackError`（fail-loud）。完整说明与
> System 1 评分工具见 `advanced-development-guide.md` §6.1.2。

```python
agent = (
    AgentBuilder().from_env()
    .with_act_plugin(my_research_act_plugin)
    .with_tool_plugin(my_research_tools_plugin)
    .with_hint_plugin(my_research_hint_plugin)
    .with_gate_plugin(my_research_gate_plugin)
    .build()
)
```

---

### §2.6 Visual Adapter 注入（3 路径）

> 自 Step 2 P2（2026-05-13）起，Visual Adapter 是公开扩展点。三种注入路径汇合到 `Agent.visual_adapters` 属性。

#### `with_visual_adapter(extension: str, adapter_class: Any) -> AgentBuilder`

最简单路径 — 不必组装 plugin，直接登记 `(扩展名, VisualAdapter 子类)`。

```python
from krow_agent_sdk.visual import VisualAdapter

class CADVisualAdapter(VisualAdapter):
    def open(self, source, **kwargs): ...
    def close(self): ...
    def render(self, page_index, width=960, height=540): ...
    def inventory(self, page_index): ...
    def page_count(self): ...

agent = (
    AgentBuilder().from_env()
    .with_visual_adapter(".dwg", CADVisualAdapter)
    .with_visual_adapter(".step", CADVisualAdapter)
    .build()
)
```

| 校验 | 行为 |
|---|---|
| `extension` 非 `.` 开头 | `ValueError` |
| `extension` 大小写 | 自动归一为小写 |

#### `with_default_pptx_adapter() -> AgentBuilder`

一行接入主仓 `HeadlessPPTXVisualAdapter`（PPTX 视觉质检管线，PR-7）。

| 依赖 | 要求 |
|---|---|
| extra | `pip install krow-agent-sdk[visual]` |
| 系统库 (Linux) | `libcairo2 + libpango + fonts-noto-cjk` |
| 失败兜底 | adapter 不可导入 → log warning + 跳过；不抛异常 |

#### `with_visual_adapter_plugin(plugin: VisualAdapterPlugin) -> AgentBuilder` (⚠️ experimental)

注册 [VisualAdapterPlugin](#510-visualadapterplugin--视觉适配器-p10--experimental) 实例，支持一次性返回多 (ext, cls) 对 + lifecycle hook。

---

### §2.6.1 Document Parser 注入（2 路径）

> 自 2026-06-13 起公开。
> 把自定义解析器注册为某扩展名的**默认**解析器：agent 内 `smart_read_document` 读该
> 扩展名文件时**物理路由**到你的解析器（System 1 闸门，LLM/planner 无感知，不依赖
> prompt 提示）。`shutdown()` 自动 unregister。

#### `with_document_parser(extension: str, parser: Any) -> AgentBuilder`

```python
class DatasheetParser:
    def parse(self, file_path: str) -> dict:
        if not looks_like_datasheet(file_path):
            return {"abstain": True, "reason": "非元器件 datasheet"}  # 回落内置链
        return {"success": True, "content": run_pipeline(file_path)}

agent = (
    AgentBuilder().from_env()
    .with_document_parser(".pdf", DatasheetParser())
    .build()
)
```

**解析器契约（三态返回）**：

| 返回 | 语义 | 后续 |
|---|---|---|
| `{"success": True, "content": ..., ...}` | 正常产物 | 直接作为 `smart_read_document` 输出（额外字段透传，附 `parser_source`） |
| `{"abstain": True, "reason": ...}` | 显式弃权 | 回落内置解析链（混合语料中非本域文件的**唯一**合法 fallback 通道） |
| `{"success": False, "error": ...}` 或抛异常 | 失败 | **fail-loud 透传**，不回落内置链（防 silent fallback 掩盖真因） |

| 校验 | 行为 |
|---|---|
| `extension` 非 `.` 开头 | `ValueError`（注册期） |
| `parser` 非 callable 且无 `parse` 方法 | `ValueError`（注册期） |
| 同 ext 重复注册 | 后注册者覆盖（log 留痕） |

> **与定向读取原语的关系**：`smart_read_document` 的 `pages` / `scan_keywords` /
> `layout_mode` 定向参数不经过自定义解析器；解析器内部可直接复用这些语法层原语
> （`from modules.tools.builtins.document_reader_tools import read_pdf_pages, scan_pdf_keywords`）。

#### `with_document_parser_plugin(plugin: DocumentParserPlugin) -> AgentBuilder`

注册 [DocumentParserPlugin](#511-documentparserplugin--文档解析器-p11) 实例，一次性返回多 (ext, parser) 对 + `on_load`/`on_unload` lifecycle hook + `plugin_id` 审计标识。

---

### §2.7 entry_points 自动发现（8 个 + 1 个 all）

> **Feature flag**：默认 OFF；需设 `KROW_ENABLE_PLUGIN_ENTRY_POINTS=1` 才生效（防止 plugin 被无意拉进），或 `force=True` 强制 override。

| 方法 | entry_points group | 协议 |
|---|---|---|
| `with_act_plugins_from_entry_points(*, force=False)` | `krow.act` | ACTPlugin |
| `with_tool_plugins_from_entry_points(*, force=False)` | `krow.tool` | ToolPlugin |
| `with_gate_plugins_from_entry_points(*, force=False)` | `krow.gate` | GatePlugin |
| `with_hint_plugins_from_entry_points(*, force=False)` | `krow.hint` | HintPlugin |
| `with_event_listener_plugins_from_entry_points(*, force=False)` | `krow.event_listener` | EventListenerPlugin |
| `with_observability_plugins_from_entry_points(*, force=False)` | `krow.observability` | ObservabilityPlugin |
| `with_domain_pack_plugins_from_entry_points(*, force=False)` | `krow.domain_pack` | DomainPackPlugin |
| `with_visual_adapter_plugins_from_entry_points(*, force=False)` | `krow.visual_adapter` | VisualAdapterPlugin |
| `with_all_plugins_from_entry_points(*, force=False)` | (上述 8 个全部) | 一次性扫全部 |

外部 plugin 包通过 `pyproject.toml` 暴露：

```toml
[project.entry-points."krow.act"]
my_research_act = "my_pkg.plugins:MyResearchACTPlugin"

[project.entry-points."krow.tool"]
my_research_tools = "my_pkg.plugins:MyResearchToolsPlugin"
```

> 单条 plugin 加载失败 log warning，不阻塞其他 plugin 的加载。
> MCPServer / Security 不在自动扫描范围（仍属 experimental，需手动注入）。

---

### §2.8 测试注入

#### `with_ai_manager(ai_manager: AIProviderManager) -> AgentBuilder`

**仅供测试** — 注入预先构造的 `AIProviderManager` 实例（替代 SDK 默认的 cloud provider 初始化）。生产环境**不要**调用此方法。

---

### §2.9 LLM Record/Replay 接入

#### `with_replay_store(store) -> AgentBuilder`

让 SDK 在 `build()` 时自动 install [`LLMReplayStore`](#71-llmreplaystore) swap，`Agent.shutdown()` 时自动 uninstall。免去手动 `wrap_provider_manager_with_replay(store)` + `finally swap.uninstall()`。

```python
from krow_agent_sdk.replay import LLMReplayStore

store = LLMReplayStore.from_env("fixtures/my_test.json")
agent = (
    AgentBuilder().from_env()
    .with_replay_store(store)
    .build()
)
try:
    result = agent.run("...")
finally:
    agent.shutdown()  # 自动 uninstall replay swap
```

| 校验 | 行为 |
|---|---|
| `store` 缺 `mode` 属性或 `get` callable | `ValueError`（duck typing，不强制 isinstance） |
| 重复调用 | 第二次覆盖第一次 |

---

### §2.10 `build()` — 构造 Agent

```python
def build(
    self,
    *,
    validate_connection: bool | None = None,
    on_progress: Callable[[str, dict], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
    on_report: Callable[[Any], None] | None = None,
    on_todo_created: Callable[[list], None] | None = None,
    on_todo_update: Callable[[str, Any], None] | None = None,
) -> Agent: ...
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `validate_connection` | `None` → 读 `KROW_SDK_BUILD_VALIDATE_CONNECTION` env（缺省 `1`） | 启动期连接校验：`GET /v1/models` + project_root 写权限测试 + plugin signature validator |
| `on_progress(stage, payload)` | `None` | 透传给 AgentV3 — 进度回调（每 macro / micro step） |
| `on_thinking(text)` | `None` | 透传给 AgentV3 — LLM 流式 reasoning chunk |
| `on_report(payload)` | `None` | 透传给 AgentV3 — 阶段性报告 |
| `on_todo_created(todos)` | `None` | 透传给 AgentV3 — macro plan 创建 todo 列表 |
| `on_todo_update(todo_id, status)` | `None` | 透传给 AgentV3 — todo 状态变化 |

| 抛错 | 触发 |
|---|---|
| `MissingKrowAPIKeyError` | api_key 缺失 |
| `MissingProjectRootError` | project_root 缺失 |
| `ProjectRootNotWritableError` | `validate_connection=True` 时 project root 不可写 |
| `KrowAPIKeyInvalidError` | `validate_connection=True` 时 cloud 返回 401 |
| `PluginSignatureMismatchError` | `validate_connection=True` 时 plugin signature 与 Protocol 不匹配 |
| `InvalidPluginIDError` | `plugin_id` 不符合 `<org>.<plugin_name>` 双段命名 |
| `DuplicatePluginIDError` | 同进程内 plugin_id 撞名 |
| `PluginLoadError` | plugin `on_load` 抛异常 |

> Plugin 错误模式由 env `KROW_SDK_PLUGIN_ERROR_MODE` 控制：
> - `swallow`（默认）— log error 不抛
> - `raise` — 抛 `PluginLoadError`
> - `quiet` — 不 log 不抛

---

## §3. `Agent` — 运行时实例 API

由 `AgentBuilder.build()` 返回。SDK 用户**不要**直接 `Agent(...)` 构造（构造器签名不在 SemVer 稳定承诺内）。

### §3.1 `Agent.run()` — 阻塞式同步执行

```python
def run(
    self,
    user_input: str,
    *,
    context: dict | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    stop_event: Any | None = None,           # threading.Event
    inbound_messages: list[dict[str, str]] | None = None,
    task_context: dict[str, Any] | None = None,
) -> AgentV3Result: ...
```

| 参数 | 说明 |
|---|---|
| `user_input` | 自然语言任务描述（必填） |
| `context` | 任务上下文 dict（可选；如 `{"output_dir": "/tmp/x"}`） |
| `session_id` | 会话 ID；缺省 SDK 自动生成 UUID。多次调用同 `session_id` 复用 ExperienceMemory |
| `project_id` | 项目 ID；与 KrowService 跨进程协作时使用 |
| `stop_event` | `threading.Event` 实例；外部 `set()` 后 agent 协作停止（不立即；详 `agent_v3.py` stop_event 协议） |
| `inbound_messages` | 上文消息序列 `[{"role": "user", "content": ...}]`（兼容 OpenAI chat 格式） |
| `task_context` | 任务级配置：`act_name`（软提示，提权某 ACT）、`lock_act` + `tool_universe`（硬锁 ACT + 裁工具宇宙，见 §2.4.2）、`agent_identity` / `persona_directives`（见 §2.4.1）、`micro_budget`、`max_coverage_rounds` 等 |

> **`task_context['max_coverage_rounds']`**（int，0-10，默认 2）：长文报告"覆盖度驱动续写"的最大轮数。
> 当结构化多章节报告（≥3000 字 + ≥3 标题）字符达标但 LLM 自检判定仍有用户子问题未覆盖时，系统会定向补全缺失章节，最多续写本轮数。
> IM 轻问答场景可设 `0` 关闭（避免任何额外续写延迟）；长报告场景可调高。全局开关：环境变量 `KROW_COVERAGE_CONTINUATION=0` 一键关闭。

#### 返回值：`AgentV3Result`（来自主仓 `modules.agent.agent_v3`）

| 字段 | 类型 | 含义 |
|---|---|---|
| `success` | `bool` | 任务是否成功 |
| `solution` | `str` | LLM 给出的最终解释（自然语言） |
| `execution_result` | `dict` | macro 步骤执行汇总（含每个 macro 的 success / output / error） |
| `final_output` | `str` | 最终交付内容（如生成的 markdown / 报告全文） |
| `metadata` | `dict` | 运行时 metadata（macro 步数、micro 调用数、LLM 调用次数、用时） |

```python
result = agent.run(
    "把 /data/x/meeting.txt 整理成 markdown 会议纪要",
    context={"output_dir": "/data/x/notes"},
    session_id="user_123_session_456",
)
if result.success:
    print(result.final_output)
else:
    print(f"FAIL: {result.execution_result}")
```

| 错误 | 说明 |
|---|---|
| `RuntimeError("Agent has been shutdown; cannot run.")` | `shutdown()` 后再调 |
| `KrowAPIKeyInvalidError` / `KrowQuotaExceededError` | LLM 401 / 402 |
| `LLMProviderError` | LLM 网络/5xx 重试链耗尽 |

> SDK 自动 emit metric `agent.run.calls` + audit `agent.run.start/complete/error`（如配置了 `ObservabilityPlugin` 会通过 sink 转发）。

#### 内置任务路由优化（v0.8.12.25 起，**零代码改动**）

`Agent.run()` 在 plan_task 阶段会让 LLM 对 `user_input` 做语义分类，并按任务类型走不同的执行路径：

| 任务类型 | 路径 | 用户感知 |
|---|---|---|
| 寒暄 / 小话题（"你好"、"谢谢"） | 0-step 直出（无 plan / 无工具调用） | < 2s 返回 |
| 纯信息检索（"OpenAI 最近发布了什么模型？"） | `ai_search` primary_step direct out | ~30-50s 返回，保留搜索引擎原始 `[1][2]` 引用脚标 + 自动拼接的 Markdown "## 参考来源" 列表 |
| 简单咨询 / 科普 / 答题 | macro single-step direct out（跳过 summary 改写） | 比常规快 ~10-30s |
| 标准任务（文件交付 / 多步综合 / 数据分析） | 完整 macro+micro ReACT + summary 改写 | 常规延迟 |

**外部开发者影响**：

- ✅ `result.final_output` 在快速路径下直接是工具产出的 Markdown 答案（不被 LLM 改写）
- ✅ 内置 `ai_search` 工具的 `answer` 字段会自动追加 Markdown 格式 `## 参考来源` 列表；结构化 `sources: list[dict]` 字段保留供下游消费方继续用
- ✅ 无需修改任何 SDK 调用代码——升级到 v0.8.12.25 即默认生效
- ⚠️ 自定义 `ToolPlugin` 若想享受同等待遇，需在 ACT yaml 内为该工具的 step 配 `primary_deliverable_step: <step_id>` + `report_detail: "detailed"`（详 `docs/sdk/advanced-development-guide.md`）

具体反模式 + 配套示例：见 [`quickstart.md` §4.6](./quickstart.md#46-内置-ai_search-联网搜索自动快速路径pr-2-起零代码改动)。

---

### §3.2 `Agent.run_stream()` — 流式执行

```python
def run_stream(
    self,
    user_input: str,
    *,
    topics: Sequence[str] = (...默认覆盖 macro/micro/llm/agent.task_*...),
    context: dict | None = None,
    session_id: str | None = None,
    project_id: str | None = None,
    stop_event: Any | None = None,
    inbound_messages: list[dict[str, str]] | None = None,
    task_context: dict[str, Any] | None = None,
    queue_max_size: int = 1000,
    idle_timeout: float | None = 600.0,
) -> Iterator[StreamItem]: ...
```

启动后台线程跑 `AgentV3.run`，主调用方逐个 yield [`StreamItem`](#62-streamitem--streamitemkind) envelope，直到任务完成 / 异常 / idle_timeout / 用户 break。

#### 默认 `topics`（约 17 个）

| 类别 | topic |
|---|---|
| Macro ReACT | `macro_react.plan_created` / `macro_react.todo_updated` |
| 进度 | `progressive.step_start` / `progressive.step_completed` / `progressive.replan_start` / `progressive.early_conclude` |
| Planner | `planner.phase2_start` / `planner.phase2_end` |
| Micro ReACT | `react.step` / `react.complete` / `react.thinking_stream` |
| LLM | `llm.request` / `llm.response` / `llm.error` |
| **终止信号**（必须包含至少 1 个） | `agent.task_start` / `agent.task_complete` / `agent.task_failed` / `agent.task_cancelled` |

> **铁律**：`topics` 必须包含至少 1 个终止 topic（`agent.task_complete` / `agent.task_failed` / `agent.task_cancelled`），否则 stream 永不结束 → 抛 `ValueError`（默认 `topics` 已包含全部 3 个）。

#### Yield 序列

```
event* → result|error
```

1. **多个** `StreamItem(kind="event")` — EventBus 推送的事件
2. **最后一个**为 `StreamItem(kind="result")`（成功 → `result.result` 是 `AgentV3Result`）或 `StreamItem(kind="error")`（异常 → `result.error` 是 `BaseException`）

#### 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `queue_max_size` | `1000` | 内部事件 queue 上限；满时丢弃**最旧**事件并 log warning（不阻塞 EventBus 主线程） |
| `idle_timeout` | `600.0` | `queue.get` 单次最长等待秒；超过 yield `StreamItem(kind="error", error=TimeoutError)` 后结束。`None` = 无限等待（不推荐生产） |

#### 完整例

```python
from krow_agent_sdk import StreamItem

agent = AgentBuilder.from_env().build()
try:
    for item in agent.run_stream("写一份周报"):
        if item.kind == "event":
            ev = item.event
            print(f"[{ev.type}] {ev.payload.get('summary', '')[:80]}")
        elif item.kind == "result":
            final = item.result
            print(f"DONE: {final.final_output[:200]}")
        elif item.kind == "error":
            raise item.error
finally:
    agent.shutdown()
```

#### 反模式（设计文档 §0.1 TURBO 哲学）

- ❌ 在 `event handler` / for-loop body 内调 LLM / 重 IO（会阻塞 EventBus 线程）
- ❌ 多次调 `run_stream()` 复用同一 Agent + 同一 session_id（AgentV3 是 stateful，并发会乱）
- ❌ 把 `topics` 自定义后漏掉所有 terminal topic → ValueError

#### 中途取消

```python
import threading

stop = threading.Event()
agent = AgentBuilder.from_env().build()
try:
    for item in agent.run_stream("写一份周报", stop_event=stop):
        if some_condition_to_cancel:
            stop.set()
            break  # generator close → 自动 unsubscribe
finally:
    agent.shutdown()
```

> 用户 `break` for-loop 时，SDK 自动：(1) `effective_stop.set()` (2) unsubscribe 全部 topics (3) 等后台 runner 线程退出（10s timeout）(4) 清队列。

---

### §3.3 `Agent.shutdown()` — 资源清理

```python
def shutdown(self) -> None: ...
```

| 行为 | 说明 |
|---|---|
| 停 HTTP gateway（如启用） | 防止外部还在访问时清理 plugin 状态 |
| 触发 plugin `on_unload` | 反向遍历所有 cleanup callback（含 EventBus unsubscribe / ToolManager unregister） |
| 释放 LLM replay swap | `with_replay_store(store)` 自动 install 的 swap 反向 uninstall |
| 标记 `_closed=True` | 之后 `run()` / `run_stream()` 抛 `RuntimeError` |

| 重复调用 | idempotent — 第二次直接 return |

> **强烈建议**用 `try / finally` 包裹（详最小入门例 §1.2）。Wave B 计划支持 `with` 语句（context manager 协议）。

---

### §3.4 Agent 只读属性

| 属性 | 类型 | 说明 |
|---|---|---|
| `agent.event_bus` | [`EventBusReader`](#61-eventbusreader) | 只读 EventBus facade（subscribe / unsubscribe / iter_recent） |
| `agent.loaded_plugin_ids` | `tuple[str, ...]` | 已加载 plugin ID 列表（debug / introspection） |
| `agent.http_gateway` | [`_HttpGatewayHandle`](#43-httpgatewayspec) `\| None` | HTTP Gateway handle；`None` = 未启用 |
| `agent.mcp_servers` | `tuple[dict, ...]` | ⚠️ experimental — 所有 MCPServerPlugin 注入的 server 配置 |
| `agent.security_policies` | `tuple[dict, ...]` | ⚠️ experimental — 所有 SecurityPlugin / DomainPackPlugin 注入的 policy |
| `agent.visual_adapters` | `tuple[tuple, ...]` | ⚠️ experimental — 所有路径注入的 (file_ext, adapter_class) 列表 |
| `agent.recommended_budget` | `dict \| None` | ⚠️ experimental — DomainPackPlugin 推荐的 budget |
| `agent.supplementary_md_providers` | `tuple` | ⚠️ experimental — DomainPack 注入的 extended_md supplement provider |

---

### §3.5 HITL 挂起/续跑 — `with_hitl` / `Agent.resume`

> 设计 SSOT：`docs/sdk/hitl-suspend-resume-design.md`。Agent 可在执行中途暂停向
> 用户提问（自然语言 + 图片 + 文件答复），凭 `resume_token` 从断点继续，
> **支持进程重启后续跑**（durable checkpoint）。

#### 启用（builder）

```python
agent = (
    AgentBuilder()
    .with_krow_api_key("sk-user-...")
    .with_project_root("./proj")
    .with_hitl(
        enabled=True,
        allow_llm_questions=True,            # 注入 request_human_input 工具，LLM 信息不足时自主发问
        confirm_before_tools=["smart_file_write"],  # 强制确认门：这些工具执行前框架必停（System 1）
        max_suspensions=5,                   # 单 run 最大挂起次数护栏
        ttl_seconds=7 * 24 * 3600,           # checkpoint 保留时限
    )
    .build()
)
```

#### 挂起与续跑

```python
result = agent.run("把文档翻译成那个语言")     # LLM 发现歧义 → 挂起
if result.suspended:
    print(result.suspension["question"])       # 要问用户的问题
    token = result.suspension["resume_token"]

    # 答复支持多模态（文本 / 图片 / 文件任意组合）
    result = agent.resume(token, {
        "text": "翻译成法语，参考附图标注",
        "images": ["annotated.png"],            # 本地路径 / data-uri / http url
        "files": ["规格书.pdf"],                # 注入 FileCache 供工具读取
    })
    # result 可能再次 suspended=True（多轮往返）
```

| API | 签名 | 说明 |
|---|---|---|
| `Agent.resume` | `(resume_token, human_input, *, stop_event=None) -> AgentV3Result` | `human_input` 接受 `str` / `dict` / `HumanInput`；CAS 幂等（并发/重复 resume 恰好一个赢，中途崩溃自动回滚可重试） |
| `Agent.list_checkpoints` | `(session_id) -> list[dict]` | 列出会话现存断点（元数据） |
| `Agent.cancel_checkpoint` | `(resume_token) -> None` | 显式取消；之后 resume → `CheckpointCancelledError` |

#### suspended 结果语义

| 字段 | 说明 |
|---|---|
| `result.suspended` | `True` = 等待人工输入（**不是失败**） |
| `result.suspension["resume_token"]` | 一次性 token；消费后再用 → `CheckpointConsumedError` |
| `result.suspension["question"]` | LLM / 确认门生成的问题 |
| `result.suspension["expected_input"]` | `free_text` / `approval` / `selection` / `file` |
| `result.suspension["options"]` | 可选项列表（selection 场景） |
| `result.suspension["origin"]` | `llm_tool`（LLM 自主发问）/ `policy_gate`（强制确认门） |
| `result.suspension["metadata"]` | `dict` — 透传的自定义 domain payload（默认 `{}`）。框架**不解释**其内容，原样回传。来源：`llm_tool` 经 `request_human_input(metadata={...})`；`policy_gate` 经 ACT `__act__.yaml` 的 `hitl_gate_metadata: {tool: {...}}` 声明。典型用途：选面 / 确认 UI 渲染所需的 domain 字段（如 `colored_step_key`、候选几何）。 |
| `result.suspension["expires_at"]` | checkpoint 过期时间（过期 resume → `CheckpointExpiredError`） |

#### 流式 / headless

- `run_stream()`：挂起以 `agent.task_suspended` 终止事件结束流；resume 重开流。
- headless HTTP（`api_gateway`）：`POST /api/v1/agent/resume`（body 含 `resume_token` / `text` / `images` / `files`）、`GET /api/v1/agent/checkpoints?session_id=...`、`POST /api/v1/agent/checkpoints/{token}/cancel`；BtQ 发布 `background_task.suspended` 生命周期事件（SSE 终止帧透传 HITL payload）。

#### 错误（`krow_agent_sdk.errors` 同层导出，`modules.agent.hitl.errors`）

| 错误 | 触发 |
|---|---|
| `CheckpointNotFoundError` | token 不存在 |
| `CheckpointConsumedError` | token 已消费（一次性） |
| `CheckpointExpiredError` | 超 TTL |
| `CheckpointCancelledError` | 已显式取消 |
| `CheckpointSchemaMismatchError` | 跨版本 schema 不兼容 |

#### per-run HITL 覆盖 — `run(task_context={'hitl': {...}})`（Stable）

`with_hitl` 设置的是 **builder 全局** HITL 策略（对该 Agent 的所有 run 生效）。若某次
调用需要**不同**的 HITL 策略（如只对高风险任务开确认门、对批量任务临时关 HITL），
在 `run` / `run_stream` / `arun` 传 `task_context={'hitl': {...}}` 即可**逐次覆盖**：

```python
agent = (
    AgentBuilder().with_krow_api_key("sk-user-...").with_project_root("./proj")
    .with_hitl(enabled=True, allow_llm_questions=True)   # builder 全局默认
    .build()
)

# 本次 run 改用更严格的确认门（覆盖 builder 全局）
result = agent.run(
    "批量改写这批合同",
    task_context={"hitl": {
        "enabled": True,
        "confirm_before_tools": ["smart_file_write", "terminal_execute"],
    }},
)

# 本次 run 临时关闭 HITL（无人值守批处理）
result = agent.run("生成日报", task_context={"hitl": {"enabled": False}})
```

| 契约 | 语义 |
|---|---|
| **优先级** | `task_context['hitl']`（per-run）> `with_hitl`（builder 全局）。`setdefault` 语义：调用方显式传入即采用，框架不覆盖（'指定即采用'）。 |
| **无 builder 默认时** | 即使**未调** `with_hitl`，per-run `task_context['hitl']` 仍生效（该次 run 独立启用 HITL）。 |
| **作用域** | 仅本次 `run`/`run_stream`/`arun` 调用；不改变 Agent 的 builder 全局策略，下次调用仍回落到 `with_hitl`（或无）。 |
| **dict 形态** | 与 `with_hitl` 参数同构（`enabled` / `allow_llm_questions` / `confirm_before_tools` / `max_suspensions` / `ttl_seconds`）。运行时由 `ProgressiveExecutor` 经 `task_context['hitl']` → `_HitlPolicy.from_dict` 消费。 |

> **稳定性**：本 per-run 覆盖契约为 **Stable**——`setdefault('hitl', ...)`（调用方优先）
> 语义受版本治理保护，breaking 变更须 MAJOR bump + 提前 1 release deprecation 警告
> （与 `with_hitl` 同级）。守门测试见 §3.5 对应 contract test。

#### ACT 声明式 HITL 粒度（per-ACT · `__act__.yaml`）

`allow_llm_questions` / `confirm_before_tools` 是 **run 级**开关；若需**按管线（ACT）**
细化 HITL 行为，ACT 作者可在 `__act__.yaml` 声明以下可选字段（ACT 激活时生效，调用方零改动 · OCP）：

| manifest 字段 | 类型 | 语义 |
|---|---|---|
| `hitl_allow_llm_questions` | `bool` | 覆盖全局 `allow_llm_questions`：该 ACT 拥有的工具所属 step 是否注入 `request_human_input`。典型：无人值守离线建库 ACT 声明 `false`，避免批处理场景过度发问→静默挂起。**按 `step.tool → 所属 ACT` 解析**（非 step-index）。 |
| `hitl_confirm_before_tools` | `list[str]` | 声明式强制确认门：执行这些工具前由 System-1 `_maybe_raise_hitl_gate` 必停（与 run 级 `confirm_before_tools` 取并集）。ACT 作者最清楚本管线高代价节点。 |
| `hitl_gate_metadata` | `dict[str, dict]` | `{tool_name: {...}}`——该工具触发确认门时，对应 payload 原样进 `suspension["metadata"]` 透传给前端（如选面 UI 渲染字段）。框架不解释内容。 |

> **粒度说明（接 kad 反馈 S2）**：HITL 发问门粒度为 **run 级 + per-ACT**，**无 per-step-index**。
> 若需「同一管线内 step A 允许发问、step B 禁止」，推荐做法是**把这两个 step 的工具拆到不同 ACT**，
> 或对禁止发问的 step 走 `hitl_allow_llm_questions=false`、对需要用户介入的 step 改用**声明式
> `hitl_confirm_before_tools` 强制确认门**（携带 `hitl_gate_metadata` 渲染自定义 UI）——而非依赖
> LLM「自觉在某 step 不发问」（文字引导对 LLM 不可靠）。

#### resume 状态存活契约（接 kad 反馈 S3）

HITL 挂起→resume 跨越的状态由 `ProgressiveExecutor.export_hitl_snapshot` / `restore_hitl_snapshot`
显式白名单捕获/恢复。**跨 resume 存活**的状态：

| 状态 | 跨 resume 存活 | 说明 |
|---|---|---|
| `step_results`（已完成步骤结果） | ✅ | 按 step_id 序列化进 checkpoint |
| `output_files`（已追踪产物清单） | ✅ | 含**远端/跨机产物**（标记 `remote: true`，见下）；不再因本地不存在而丢 |
| 预算（llm_calls / replans / elapsed） | ✅ | 挂起等待时长不计入墙钟 |
| `react_tools_called` / `pptx_ctx` | ✅ | |
| SearchSession 笔记 / planner 反馈累积 / 诊断缓存 | ❌（按需重建） | 纯优化层，不影响续跑正确性 |

**跨机产物追踪（2part 部署）**：当工具在远端机（如 Win 引擎机）产出文件、返回**远端绝对路径**
（`C:\...\x.fem`）时，`output_files` 条目带 `remote: true` 标记，且**不**做本地 `os.path.exists`
校验（POSIX host 上本地必不存在）。接入方据此知道该产物在远端、不应按本地文件读取/校验。

**mid-step 续跑工具幂等**：HITL 在 step 执行中途挂起、resume 后该 step 被重入时，挂起前**已成功
执行的重型工具**（同输入）由 System-1 持久幂等闸门跳过（不重跑），发 `hitl.idempotent_skip` 事件
（payload 含 `reused: true`）；同时该 step 的 `progressive.step_start` 带 `idempotent_replay: true`，
供接入方前端把「续跑重放」与「真执行」区分，避免渲染误导用户的「进行中」步骤条。

---

## §4. 配置 dataclass

### §4.1 `BudgetSpec`

```python
@dataclass
class BudgetSpec:
    target_walltime_s: int = 600
    max_walltime_s: int = 1800
    max_total_llm_calls: int = 120
    max_adapt_extensions: int = 3
    max_replans: int = 3
    micro_max_iterations: int = 8
    micro_max_time_ms: int = 180_000
    max_plan_steps: int = 20
    tool_execution_timeout_s: int = 0  # FR-2：单工具执行超时全局下限（0=不覆盖）
```

| 字段 | 单位 | 默认 | 含义 |
|---|---|---|---|
| `target_walltime_s` | 秒 | 600 | 目标墙钟（agent 倾向在此前完成；超过触发 adapt extension 协商） |
| `max_walltime_s` | 秒 | 1800 | **硬上限**墙钟；超过 fail-loud 中断 |
| `max_total_llm_calls` | 次 | 120 | 进程级 LLM 调用上限（macro + micro 总和） |
| `max_adapt_extensions` | 次 | 3 | **adapt budget extension** 触发次数上限（单个 plan step 内"再追加一步"的次数；**不是** macro plan 总步数，后者见 `max_plan_steps`） |
| `max_replans` | 次 | 3 | macro replan 触发次数上限 |
| `micro_max_iterations` | 次 | 8 | **通用工具步** micro ReACT 的默认最大迭代数（仅约束无特化 tuning 的通用步；ACT yaml `react_config` 与 `content_source`/`terminal_execute` 等特化值优先级更高）。经 `task_context['micro_budget']` 接入运行时 |
| `micro_max_time_ms` | 毫秒 | 180000 | **通用工具步** micro ReACT 默认最大墙钟（`terminal_execute` 保 300s 底线）。经 `task_context['micro_budget']` 接入运行时 |
| `max_plan_steps` | 个 | 20 | **macro plan 步数上限**（一次任务最多执行多少个宏观 plan step）。运行时夹紧到 `[12, 40]`：**下限 12**（设更小会被抬到 12；低于 12 仅内置 Strategy contract 可声明），**上限 40**。长流程自定义 ACT 需调高 |
| `tool_execution_timeout_s` | 秒 | 0 | **单工具执行超时全局下限**（FR-2）。`0` = 不覆盖（走运行时默认 30s / 300s）。`from_config` 路径的全局配法；per-tool 精确控制用 `AgentBuilder.with_tool_execution_timeout({tool: s})`（优先级更高）。上限 3600s |

> **建议起点**（外部开发者）：默认值适合"中等复杂度任务（写报告、PPT）"。如任务很轻（如简单文本归纳）可把 `max_total_llm_calls` 降到 30-60；如任务重（深度研究 + 跨工具协作）可升到 200。
> **长流程自定义 ACT 必读**：若你的 ACT 业务阶段较多（如 7+ 阶段），planner（LLM）可能动态拆成 15~20 个 macro 步；默认 `max_plan_steps=20` 通常够用，但若仍被 `safety_net:max_steps` 提前收尾，请显式调高（上限 40）：
> ```python
> budget = BudgetSpec(max_plan_steps=28, max_total_llm_calls=200)
> ```
> 注意：LLM 把业务阶段拆成更多技术步骤是正常的动态规划行为（系统不会硬绑定阶段数）；你要保证的是"步数预算 ≥ 实际需要的步数"，而非强制 LLM 只走 N 步。

```python
from krow_agent_sdk import BudgetSpec
budget = BudgetSpec(
    max_total_llm_calls=80,
    max_walltime_s=1200,
    micro_max_iterations=10,
)
agent = AgentBuilder.from_env().with_budget(budget).build()
```

---

### §4.2 `BuilderConfig`

```python
@dataclass
class BuilderConfig:
    api_key: str
    project_root: Path
    budget: BudgetSpec | None = None
    act_plugins: list[ACTPlugin] = field(default_factory=list)
    tool_plugins: list[ToolPlugin] = field(default_factory=list)
    gate_plugins: list[GatePlugin] = field(default_factory=list)
    hint_plugins: list[HintPlugin] = field(default_factory=list)
    event_listener_plugins: list[EventListenerPlugin] = field(default_factory=list)
    observability_plugins: list[ObservabilityPlugin] = field(default_factory=list)
    mcp_server_plugins: list[MCPServerPlugin] = field(default_factory=list)         # ⚠️ experimental
    security_plugins: list[SecurityPlugin] = field(default_factory=list)            # ⚠️ experimental
    domain_pack_plugins: list[DomainPackPlugin] = field(default_factory=list)       # ⚠️ experimental
    visual_adapter_plugins: list[VisualAdapterPlugin] = field(default_factory=list) # ⚠️ experimental
    inline_visual_adapters: list[tuple[str, Any]] = field(default_factory=list)
    validate_connection_on_build: bool = True
    ai_manager: AIProviderManager | None = None
    http_gateway: HttpGatewaySpec = field(default_factory=HttpGatewaySpec)
```

> 一次性配置大量 plugin 时推荐路径（vs 长 `with_*` 链）。

---

### §4.3 `HttpGatewaySpec` (⚠️ experimental)

```python
@dataclass
class HttpGatewaySpec:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8090
    auth_token: str | None = None
    dry_run: bool = False
```

`Agent.http_gateway` 暴露的运行时 handle 提供以下属性 / 方法：

| 字段 | 类型 | 说明 |
|---|---|---|
| `host` | `str` | 绑定 host |
| `port` | `int` | 绑定 port |
| `url` | `str` | `f"http://{host}:{port}"` |
| `is_running` | `bool` | gateway 当前是否运行 |
| `dry_run` | `bool` | 是否 dry_run 模式 |
| `stop()` | method | 显式停止 gateway（`Agent.shutdown()` 自动调） |

---

## §5. Plugin Protocols（核心扩展点）

10 个 Protocol 是 SDK 的核心扩展点，外部开发者通过实现这些 Protocol 给 Krow agent 加能力。

> **共通规则**：
> - 所有 Plugin 都必须有 `plugin_id` 属性，格式 `<org>.<plugin_name>`，全小写 `[a-z0-9_-]`，分别 3-20 / 3-30 字符（详 [§12 InvalidPluginIDError](#12-errors--错误层与黄金模板)）
> - SDK build() 期 `_protocol_validator` 会做 signature 校验（runtime_checkable 不查签名细节）
> - lifecycle hook（[§9.4](#94-lifecycle--生命周期-hook)）`on_load(ctx) / on_unload(ctx)` 可选实现
> - **System 1 vs System 2 边界**：每个 Protocol 文档明确标注（System 1 = 确定性 / System 2 = LLM 语义）

### §5.1 `ACTPlugin` — 加新 ACT (P1)

**System 1**（ACT 是声明式 yaml + markdown 容器）。让外部 plugin 加新 ACT（macro 层扩展）。

```python
@runtime_checkable
class ACTPlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...
    @property
    def act_name(self) -> str: ...           # 不含 ext_ 前缀；通常等于 <plugin_name> 段
    def get_act_root(self) -> Path: ...      # ACT 资源目录（含 __act__.yaml / extended.md）
    def get_act_file_path(self) -> Path: ... # 主 ACT markdown 文件路径
    def get_tool_names(self) -> list[str]: ...  # 该 ACT 启用的工具名（与 ToolPlugin 注册的对齐）
```

| 主仓 SSOT | 内部接入 |
|---|---|
| `modules/agent/act/act_loader.py:ACTLoader.register_extension_act` | SDK 自动调，外部不需要直接接触 |
| `modules/agent/act/act_manager.py:ACTManager.register_act` | 同上 |

| 命名规范 | 要求 |
|---|---|
| `plugin_id` | `<org>.<plugin_name>` 双段（如 `acme.research`） |
| `act_name` | 通常 = `<plugin_name>` 段（如 `research`），SDK 自动加 `ext_` 前缀 |
| `get_tool_names()` | 工具名必须以 `<plugin_name>.` 段为前缀（防撞 native，如 `research.web_search`） |

#### 最小实现

```python
from pathlib import Path
from krow_agent_sdk import ACTPlugin

class ResearchACTPlugin:
    plugin_id = "acme.research"
    act_name = "research"

    def get_act_root(self) -> Path:
        return Path(__file__).parent / "acts" / "research"

    def get_act_file_path(self) -> Path:
        return self.get_act_root() / "ext_research.md"

    def get_tool_names(self) -> list[str]:
        return ["research.web_search", "research.summarize"]
```

#### ACT 目录布局

```
acts/research/
├── __act__.yaml         # ACT metadata + 工具白名单 + 行为契约
├── extended.md          # 详细执行指令（给 LLM）
└── ext_research.md      # 主入口（SDK 加载用）
```

---

### §5.2 `ToolPlugin` — 加新工具 (P2)

**System 1**（工具注册是声明式 dict + Python handler）。让外部 plugin 加新工具到 ToolManager。

```python
@runtime_checkable
class ToolPlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...
    def get_tools(self) -> list[ToolSpec]: ...
```

#### `ToolSpec` TypedDict

```python
class ToolSpec(TypedDict, total=False):
    name: str                              # 必填；命名规范 <plugin_name>.<verb>_<noun>
    description: str                       # 必填；自然语言描述（给 LLM 看）
    input_schema: dict[str, Any]           # 必填；JSON Schema
    handler: Callable[..., Any]            # 必填；执行函数（接收 schema 参数）
    category: str                          # 可选；默认 "custom"
    direct_output: bool                    # 可选；默认 False
    user_visible: bool                     # 可选；默认 True
    output_schema: dict[str, Any] | None   # 可选
    complexity: str                        # 可选；"normal" / "lightweight" / ...
    dependencies: dict[str, Any] | None    # 可选；声明对其他工具/资源的依赖
```

| 字段 | 主仓真实 SSOT |
|---|---|
| 注册接口 | `modules/tools/manager.py:ToolManager.register_tool` |
| `server_name` | SDK 强制 `f"extension_{plugin_id}"`（详 V100.2 安全检查） |

#### 命名规范

工具名**必须**以 plugin 的 `<plugin_name>` 段为前缀，避免与 native 工具撞名：

| Plugin ID | OK 工具名 | NG（撞 native） |
|---|---|---|
| `acme.research` | `research.web_search`<br>`research.summarize_article` | ❌ `web_search`<br>❌ `summarize`（无前缀） |
| `cad.industrial_design` | `industrial_design.cad_extract_geometry` | ❌ `cad_extract` |

#### 最小实现

```python
from typing import Any
from krow_agent_sdk import ToolPlugin

def _do_web_search(*, query: str, max_results: int = 10) -> dict:
    # ... 真实实现 ...
    return {"results": [...], "count": ...}

class ResearchToolsPlugin:
    plugin_id = "acme.research"

    def get_tools(self) -> list[dict]:
        return [
            {
                "name": "research.web_search",
                "description": "Search the web for query keywords. Returns top-N hits.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
                "handler": _do_web_search,
                "category": "research",
            },
        ]
```

> **工具设计哲学**详见 [`advanced-development-guide.md` §3](./advanced-development-guide.md)（5 大原则：少而灵活 / 命名 / 输入鲁棒 / 输出格式 / 错误黄金模板）。

---

### §5.3 `HintPlugin` — 加新软提示 (P3)

**System 2**（hint 是给 LLM 的语义提示文本）。在 prompt 拼装阶段注入领域特定的软提示。

```python
@runtime_checkable
class HintPlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...
    @property
    def applicable_acts(self) -> list[str]: ...   # 空 list = 全局 hint
    def hint_for(self, context: dict) -> str | None: ...
```

#### `context` dict 字段（SDK 注入，plugin 不应修改）

| key | 类型 | 含义 |
|---|---|---|
| `act_name` | `str` | 当前 ACT 名 |
| `user_input` | `str` | 用户原始任务输入 |
| `tool_name` | `str` | 当前调用工具（micro ReACT 内） |
| `step_index` | `int` | macro / micro 步骤号 |

| 返回 | 行为 |
|---|---|
| `str`（markdown） | 拼接到 LLM prompt |
| `None` / `""` | 不适用，跳过 |
| 抛异常 | log warning，跳过（不阻塞主流程） |

#### 最小实现

```python
class ResearchHintPlugin:
    plugin_id = "acme.research"
    applicable_acts = ["research"]

    def hint_for(self, context: dict) -> str | None:
        if context.get("act_name") != "research":
            return None
        return (
            "**研究任务建议**：\n"
            "- 先用 `research.web_search` 搜 3-5 个权威源\n"
            "- 用 `research.summarize_article` 抽取要点\n"
            "- 最终汇总时引用源链接\n"
        )
```

> **铁律（设计文档 §0.1 TURBO）**：hint 是给 LLM 的语义建议，不能用来"教 LLM 别用某工具"或"教 LLM 别犯错"。物理性约束应通过 [GatePlugin](#54-gateplugin--加新-concludeguard-gate-p4) 或 ACT 工具白名单实现。

---

### §5.4 `GatePlugin` — 加新 ConcludeGuard Gate (P4)

**System 1**（Gate 是确定性判停规则）。让外部 plugin 加新 ConcludeGuard Gate，在 macro conclude / micro 步骤内 / **macro 计划落盘前**（`phase="plan"`，v0.9.0.32+）自动判停。

```python
GatePhase = Literal["macro", "micro", "plan"]

@runtime_checkable
class GatePlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...
    @property
    def phase(self) -> GatePhase: ...
    def get_gate(self) -> Gate: ...
```

| 主仓 SSOT | API |
|---|---|
| `modules/knowledge/conclude_guard_gates.py:Gate` Protocol | `evaluate(parsed: dict, context: dict) -> GateDecision` |
| `make_simple_gate(name, priority, evaluator)` 工厂 | 推荐外部用此构造，避免直接实现 Gate Protocol |

| `phase` 值 | 触发位面 |
|---|---|
| `"macro"` | macro ReACT 步骤 **conclude** 时（任务收尾前最后一道闸） |
| `"micro"` | micro ReACT 步骤内（单步工具执行内） |
| `"plan"` | macro ReACT **计划落盘前**（`plan_task` / 修订计划提交 state 之前的 veto；见下「Plan-time veto」） |

> **三相位严格隔离**：`plan` gate 只在计划提交前评估，绝不会在 conclude / micro 路径被误触发，反之亦然。

#### Plan-time veto（`phase="plan"` · v0.9.0.32+ · ALLOW/BLOCK）

> 场景：agent 在 macro ReACT 里**自规划**一些注定会被下游 `conclude` 阻断的步骤，先执行、再到收尾才被否决 → 白白浪费算力。`phase="plan"` gate 把审批前移到**计划落盘 state 之前**。

- 触发时机：`plan_task` 构造出计划、内部守门全过、但**尚未提交 state**（覆盖**初始创建 + 修订**两条路径的公共落盘点）。
- `GateVerdict.BLOCK` ⇒ 计划**不落盘、零步骤执行**，`plan_task` 直接把 `reason` 返回给 LLM；LLM 读到该 observation 后**自行重规划**（复用既有 replan 路径，无需额外接线）。
- `GateVerdict.ALLOW`（或未注册 plan gate）⇒ 计划照常落盘执行（零回退）。
- v1 仅 `ALLOW` / `BLOCK`；`REWRITE`（gate 直接改写计划）暂不支持。
- 该相位下 `evaluate(parsed, context)` 收到的载荷：
  - `parsed`：`{"action": "plan", "is_revision": bool, "goal": str, "steps": [{step_id, tool, purpose, constraints, depends_on}], "tools": [tool_name, ...]}`
  - `context`：`{"phase": "plan", "is_revision": bool, "goal": str, "plan_steps": [...], "existing_completed_steps": [...], "act_name": str, "task_context": dict}`

```python
from krow_agent_sdk import GatePlugin
from modules.knowledge.conclude_guard_gates import make_simple_gate, GateDecision, GateVerdict

class NoRawWebFetchPlanGate:
    """计划落盘前否决：禁止直接用 web_fetch，迫使 agent 改走受控检索。"""
    plugin_id = "acme.plan_policy"
    phase = "plan"

    def get_gate(self):
        def _evaluate(parsed, context):
            if "web_fetch" in (parsed.get("tools") or []):
                return GateDecision(
                    verdict=GateVerdict.BLOCK,
                    reason="❌ 计划被策略网关否决：本环境禁止 web_fetch，请改用 "
                           "ai_search 重新规划。",
                    gate_name="no_raw_web_fetch",
                )
            return GateDecision(verdict=GateVerdict.ALLOW, gate_name="no_raw_web_fetch")
        return make_simple_gate("no_raw_web_fetch", 50, _evaluate)
```

#### 最小实现

```python
from krow_agent_sdk import GatePlugin
# Gate / make_simple_gate / GateDecision 仍来自主仓（plugin 包通常会在 dev 装 monorepo
# 包；生产环境 sdk-runtime wheel 已含编译版本）
from modules.knowledge.conclude_guard_gates import make_simple_gate, GateDecision

def _research_quality_gate(parsed: dict, context: dict) -> GateDecision:
    sources = parsed.get("sources", [])
    if len(sources) < 3:
        return GateDecision(
            verdict="reject",
            reason=f"研究类任务至少 3 个源（当前 {len(sources)}）。",
        )
    return GateDecision(verdict="accept")

class ResearchGatePlugin:
    plugin_id = "acme.research"
    phase = "macro"

    def get_gate(self):
        return make_simple_gate(
            name="research_min_sources",
            priority=50,
            evaluator=_research_quality_gate,
        )
```

---

### §5.5 `EventListenerPlugin` — 订阅 EventBus (P5)

**System 1**（listener 是确定性事件转发）。订阅 EventBus 事件，做异步转发 / 审计 / metric 上报。

```python
@runtime_checkable
class EventListenerPlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...
    def get_subscriptions(self) -> list[tuple[str, Callable[[Any], None]]]: ...
```

| 稳定 topic 子集 | 详见 [§6.3](#63-稳定-topic-速查) |
|---|---|
| `agent.task_complete` / `agent.task_failed` / `agent.task_cancelled` | 任务终止 |
| `executor.*` | macro 执行器事件 |
| `progressive.*` | progressive 推进事件 |
| `budget.*` | 预算事件 |
| `react.*` | micro ReACT 事件 |
| 其他 topic | 仍可订阅，但**不在 SemVer 稳定保证内**（主仓 refactor 可能 break） |

#### **铁律**

- ❌ Handler 内调用 `BudgetController` write API
- ❌ Handler 内调用 `ToolManager.register_tool`
- ❌ Handler 内修改 agent 状态
- Handler 在 EventBus 线程跑，**必须超快超无副作用**

#### 最小实现

```python
import json
from typing import Any
from krow_agent_sdk import EventListenerPlugin

class AuditPlugin:
    plugin_id = "acme.audit"

    def _on_task_complete(self, event: Any) -> None:
        # 转发到外部 audit 系统（异步 / 队列；不要在此阻塞）
        with open("/var/log/krow-audit.jsonl", "a") as f:
            f.write(json.dumps({
                "type": event.type,
                "trace_id": event.trace_id,
                "timestamp": event.timestamp,
            }) + "\n")

    def get_subscriptions(self):
        return [
            ("agent.task_complete", self._on_task_complete),
            ("agent.task_failed", self._on_task_complete),
        ]
```

---

### §5.6 `ObservabilityPlugin` — Metrics/Traces 转发 (P6)

**System 1**。把 krow agent 内部 metrics / traces / audit log 推到外部系统（Datadog / Splunk / Grafana / 自建）。

```python
@runtime_checkable
class ObservabilityPlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...
    def register(self, observability_facade: Any) -> None: ...
```

| `observability_facade` 提供（SDK 注入） | 用途 | 内置 emit 现状 |
|---|---|---|
| `add_metric_sink(callback: Callable[[name, value, labels], None])` | metric 转发 | ✅ SDK 内置 emit（如 `agent.run.calls`） |
| `add_trace_sink(callback: Callable[[span], None])` | tracing 转发 | ⚠️ **当前 SDK 内置不 emit trace span**——sink 可注册但不会被内置埋点喂数据（保留给你自己的 span / 未来埋点）。详 honesty note |
| `add_audit_sink(callback: Callable[[event], None])` | audit log 转发 | ✅ SDK 内置 emit（如 `agent.run.start/complete/error`） |

> **诚实化说明（2026-06-01）**：内置埋点目前只触发 `emit_sdk_metric` / `emit_sdk_audit`（见 `modules/observability/sink_registry.py`），**未**调用 `emit_sdk_trace`。因此 `add_trace_sink` 注册的回调当前不会收到 SDK 自动产生的 span；若你需要 trace，请在自己的 plugin/工具代码里显式调用 `emit_sdk_trace(...)`。`metric` 与 `audit` sink 则会正常收到内置事件。

#### 最小实现

```python
class DatadogObservabilityPlugin:
    plugin_id = "acme.datadog"

    def register(self, facade) -> None:
        from datadog import statsd  # 假设已安装

        def _on_metric(name: str, value: float, labels: dict):
            tags = [f"{k}:{v}" for k, v in labels.items()]
            statsd.gauge(name, value, tags=tags)

        facade.add_metric_sink(_on_metric)
```

---

### §5.7 `MCPServerPlugin` — MCP Server (P7, ⚠️ experimental)

**System 1**。注册 MCP（Model Context Protocol）server endpoint 给 Agent 使用。

```python
@runtime_checkable
class MCPServerPlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...
    def get_servers(self) -> list[dict]: ...                              # 形态 A
    # def get_in_process_servers(self) -> list[tuple[str, Any]]: ...     # 形态 B/C（可选）
```

#### 三种形态（可同时实现）

| 形态 | 方法 | 行为 | 适用 |
|---|---|---|---|
| **A** 远程 endpoint metadata | `get_servers()` | 仅 collect 到 `Agent.mcp_servers`，**不**自动注册到 ToolManager、**也不自动建立连接**（需在 `on_load` 内自建 client，或改用形态 B/C） | plugin 仅声明用了哪些远程 MCP |
| **B** in-process server | `get_in_process_servers()` | feature flag `KROW_ENABLE_MCP_SERVER_PLUGIN=1` 开启时，**自动注册到 ToolManager** | plugin 内嵌一个 MCP server 实例 |
| **C** 远程 client | `get_in_process_servers()` 但实例是远程 client | 同 B，SDK 不区分 B/C | 接入第三方 SaaS MCP 服务 |

#### `server_instance` 鸭型协议（形态 B/C）

| 方法 | 必需 | 用途 |
|---|---|---|
| `list_tools() -> list[dict]` | ✅ | 返回工具元数据列表 |
| `call_tool(name: str, args: dict) -> Any` | ✅ | 远程调用工具 |
| `close() -> None` 或 `aclose()` | 可选 | SDK shutdown 时自动调用 |

#### 形态 C 例子（接入第三方 MCP）

```python
class RemoteMCPPlugin:
    plugin_id = "acme.remote_mcp"

    def __init__(self, mcp_url: str, api_key: str):
        from mcp.client import Client  # MCP 官方 python SDK
        self._mcp_url = mcp_url
        self._client = Client(mcp_url, auth=api_key)
        self._client.connect()

    def get_servers(self):
        return [{"name": "remote_x", "url": self._mcp_url, "auth": "***"}]

    def get_in_process_servers(self):
        return [("remote_x", self._client)]
```

---

### §5.8 `SecurityPlugin` — 安全策略 (P8, ⚠️ experimental)

**System 1**（Wave 1 仅声明骨架，强沙箱推 Step 3）。

```python
@runtime_checkable
class SecurityPlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...
    def get_policies(self) -> list[dict]: ...
```

| `policies` 字段 | 类型 | 说明 |
|---|---|---|
| `target_tool` | `str` | 工具名 |
| `rules` | `list[str]` | 形如 `"deny:write_outside_project_root"`、`"allow:read_only"` |

> Wave 1 仅 collect 到 `Agent.security_policies`，**不做强沙箱拦截**（强沙箱推 Step 3 subprocess / VM 隔离）。

---

### §5.9 `DomainPackPlugin` — 一站式 (P9, ⚠️ experimental)

**System 1 + System 2** 混合。一次性聚合 8 种 plugin 元素的"语法糖"协议。

```python
@runtime_checkable
class DomainPackPlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...
    @property
    def domain_name(self) -> str: ...

    # 全部 OPTIONAL（plugin 不实现某项时跳过该元素加载）
    def get_hints(self) -> list[Callable[[dict], str | None]]: ...
    def get_tools(self) -> list[ToolSpec]: ...
    def get_gates(self) -> list[tuple[str, Gate]]: ...      # (phase, gate)
    def get_extended_md_supplement(self, target_act: str) -> str | None: ...
    def get_visual_adapters(self) -> list[tuple[str, Any]]: ...   # (file_ext, adapter)
    def get_mcp_servers(self) -> list[dict]: ...
    def get_event_listeners(self) -> list[tuple[str, Callable[[Any], None]]]: ...
    def get_recommended_budget(self) -> dict | None: ...
```

#### `extended_md_supplement` 限制（v0.8 A9）

| 字段 | 上限 |
|---|---|
| 单 target ACT supplement | 4 KB |
| 整个进程内 supplement 累计 | 16 KB |

> 详见 [§9.5 extended_md_supplement_registry](#95-extended_md_supplement_registry--act-扩展-markdown)。

---

### §5.10 `VisualAdapterPlugin` — 视觉适配器 (P10, ⚠️ experimental)

**System 1**。让外部团队（CAD / 工业图纸 / 科研报告 等）注册自己的 `VisualAdapter` 直接接入 `visual_inspect` 工具链。

```python
@runtime_checkable
class VisualAdapterPlugin(Protocol):
    @property
    def plugin_id(self) -> str: ...
    def get_visual_adapters(self) -> list[tuple[str, Any]]: ...
```

| 字段 | 说明 |
|---|---|
| `file_ext` | 必须以 `.` 开头，小写（如 `.dwg`） |
| `adapter_class_or_instance` | `VisualAdapter` 子类（推荐 class 延迟实例化）或已实例化的 adapter（不推荐） |

> 多 plugin 注册同 ext → **后注册者覆盖**前者（给外部 plugin 替换内置 adapter 的能力）。

#### `VisualAdapter` ABC 定义（来自 [`visual` 模块](#93-visual--visualadapter-与-visual_inspect)）

```python
from krow_agent_sdk.visual import VisualAdapter

class CADVisualAdapter(VisualAdapter):
    def open(self, source, **kwargs): ...
    def close(self): ...
    def render(self, page_index, width=960, height=540): ...
    def inventory(self, page_index): ...
    def page_count(self): ...
```

#### 与 `with_visual_adapter(ext, cls)` 的关系

两条路径汇合到 `Agent.visual_adapters` 属性。区别：

| 路径 | 适用 | 支持 lifecycle | 支持 entry_points |
|---|---|---|---|
| `with_visual_adapter(".dwg", CADAdapter)` | 单文件简单注册 | ❌ | ❌ |
| `with_visual_adapter_plugin(plugin)` | 一次性多 (ext, cls) + plugin lifecycle | ✅ | ✅ |

---

### §5.11 `DocumentParserPlugin` — 文档解析器 (P11)

> 2026-06-13 新增。
> 把自定义文档解析器注册为某扩展名的**默认**解析器——agent 内 `smart_read_document`
> 读该扩展名文件时 System 1 物理路由到你的解析器，LLM/planner 无感知。
> 典型场景：垂直领域 PDF 结构化解析（元器件 datasheet、法律合同、医疗报告等）。

```python
from krow_agent_sdk.protocols import DocumentParserPlugin  # Protocol（structural typing）

class DatasheetParser:
    def parse(self, file_path: str) -> dict:
        if not self._looks_like_datasheet(file_path):
            return {"abstain": True, "reason": "非元器件 datasheet"}
        return {"success": True, "content": self._pipeline(file_path)}

class KadPdfPlugin:
    plugin_id = "kad.eda_datasheet_parser"

    def get_document_parsers(self):
        return [(".pdf", DatasheetParser())]

    # 可选 lifecycle hook
    def on_load(self, ctx): ...
    def on_unload(self): ...
```

| 字段 / 方法 | 约束 |
|---|---|
| `plugin_id` | 全局唯一（审计 / 注册来源标识） |
| `get_document_parsers()` | 返回 `list[(file_ext, parser)]`；`file_ext` 以 `.` 开头；`parser` 为 callable 或带 `parse(file_path) -> dict` 方法的对象 |

**解析器三态返回契约**（与 [§2.6.1](#261-document-parser-注入2-路径) 相同）：正常产物 dict / `{"abstain": True}` 回落内置链 / 失败（`success=False` 或抛异常）fail-loud 透传不回落。

> 多 plugin 注册同 ext → **后注册者覆盖**前者。
> 与 `with_document_parser(ext, parser)` 的关系：同 Visual Adapter 双路径模式——inline 适合单对快速注册（无 lifecycle），plugin 适合多对 + lifecycle + 审计标识。

#### 配套：`smart_read_document` PDF 定向读取原语

解析器内部（或任何 agent 任务）可用 `smart_read_document` 的可选参数做语法层转写，不必自研 PDF 底层：

| 参数 | 类型 | 作用 |
|---|---|---|
| `pages` | `str`（如 `"21-26,80"`，1-based） | 只转写指定页（大 PDF 必用，避免全文转储超上下文；单次上限 100 页） |
| `scan_keywords` | `list[str]`（≤ 50 个） | 确定性关键词→页码命中图（不返回正文，零 LLM 成本定位关键页；大小写不敏感；可与 `pages` 组合限定扫描范围） |
| `layout_mode` | `"plain"` / `"words"` / `"tables"` | `words` = words+bbox 行聚类转写（保留几何关系，结构化坐标在 `transcription.pages[].words`）；`tables` = 表格转写，输出携带 `transcription_method`（`find_tables` / `words_row_cluster`）+ `confidence`（`high` / `low`）标记，低置信产物**不应直接采信**，需下游确定性校验 |

---

## §6. EventBus 与流式事件

### §6.1 `EventBusReader`

由 `agent.event_bus` 暴露。**只读 facade**：仅 `subscribe` / `unsubscribe` / `iter_recent`，**不暴露** `publish` 等写方法（防止外部 plugin 反向污染主 EventBus）。

```python
class EventBusReader:
    def subscribe(
        self, topic: str, handler: Callable[[Any], None],
        *, track_recent: bool = False,
    ) -> str: ...
    def unsubscribe(self, token: str) -> None: ...
    def iter_recent(self, topic_pattern: str, n: int = 100) -> Iterator[Any]: ...
```

| 方法 | 说明 |
|---|---|
| `subscribe(topic, handler, *, track_recent=False) -> token` | 订阅；`track_recent=True` 时把命中的事件存入本 reader 的 ring buffer 供 `iter_recent` 读取（默认 False，不占内存） |
| `unsubscribe(token)` | 取消订阅 |
| `iter_recent(topic_pattern, n=100)` | 读最近 N 条事件（用于 UI debug / 慢启动 backfill）；只读快照，不影响 EventBus 状态；目前**不支持通配符**（精确 topic 名匹配） |

#### handler 签名

```python
def handler(event: Any) -> None: ...
```

`event` 是来自主仓 `modules.events.bus_core.Event` dataclass，含字段：

| 字段 | 含义 |
|---|---|
| `event.type` | topic 名（与 `subscribe` 的 topic 对齐） |
| `event.payload` | dict — 事件载荷（每 topic schema 不同；详 [§6.3](#63-稳定-topic-速查)） |
| `event.trace_id` | str — 跨事件的 trace ID（同 task / session 内一致） |
| `event.timestamp` | float — UTC 时间戳 |

#### 例

```python
agent = AgentBuilder.from_env().build()

def on_step_complete(event):
    p = event.payload
    print(f"step {p.get('step_index')} done: {p.get('summary', '')}")

token = agent.event_bus.subscribe(
    "progressive.step_completed",
    on_step_complete,
    track_recent=True,
)
try:
    result = agent.run("写一份周报")
    for ev in agent.event_bus.iter_recent("progressive.step_completed", n=10):
        print(f"recent: {ev.payload}")
finally:
    agent.event_bus.unsubscribe(token)
    agent.shutdown()
```

---

### §6.2 `StreamItem` / `StreamItemKind`

`Agent.run_stream()` yield 的统一 envelope（详 [§3.2](#32-agentrun_stream--流式执行)）。

```python
StreamItemKind = Literal["event", "result", "error"]

@dataclass(frozen=True)
class StreamItem:
    kind: StreamItemKind
    event: Any | None = None    # kind="event" 时 = Event dataclass 实例
    result: Any | None = None   # kind="result" 时 = AgentV3Result 实例
    error: BaseException | None = None  # kind="error" 时 = 后台线程异常
```

| 校验 | 行为 |
|---|---|
| `kind="event"` 但 `event=None` | `__post_init__` 抛 `ValueError` |
| `kind="result"` 但 `result=None` | 同上 |
| `kind="error"` 但 `error=None` | 同上 |

| 不可变 | `frozen=True` 不能改字段（防外部修改） |

#### 三种 kind 分辨

```python
for item in agent.run_stream("..."):
    match item.kind:
        case "event":
            print(f"[{item.event.type}]")
        case "result":
            final_output = item.result.final_output
        case "error":
            raise item.error
```

---

### §6.3 稳定 topic 速查

| 类别 | topic | payload 主字段 |
|---|---|---|
| 任务生命周期 | `agent.task_start` | `user_input` / `session_id` |
| 任务生命周期 | `agent.task_complete` | `success` / `final_output` / `metadata` |
| 任务生命周期 | `agent.task_failed` | `error_type` / `error_msg` |
| 任务生命周期 | `agent.task_cancelled` | `reason` |
| Macro ReACT | `macro_react.plan_created` | `todos` (list) |
| Macro ReACT | `macro_react.todo_updated` | `todo_id` / `status` |
| 进度 | `progressive.step_start` | `step_id` / `tool` / `purpose` / `idempotent_replay`(bool) |
| 进度 | `progressive.step_completed` | `step_id` / `summary` / `success` |
| 进度 | `progressive.replan_start` | `reason` / `attempt` |
| 进度 | `progressive.early_conclude` | `step_index` / `gate_name` / `reason` |
| HITL | `hitl.idempotent_skip` | `step_id` / `tool` / `reused`(bool) / `idempotent_reuse`(bool) |
| Planner | `planner.phase2_start` | `act_name` |
| Planner | `planner.phase2_end` | `act_name` / `tools_selected` |
| Micro ReACT | `react.step` | `iteration` / `tool_name` / `tool_args` |
| Micro ReACT | `react.complete` | `iterations` / `tool_calls_total` |
| Micro ReACT | `react.thinking_stream` | `chunk` (str) |
| LLM | `llm.request` | `source_module` / `messages_count` |
| LLM | `llm.response` | `source_module` / `latency_ms` / `tokens` |
| LLM | `llm.error` | `source_module` / `error_type` |
| Budget | `budget.llm_call_recorded` | `total_calls` / `remaining` |
| Budget | `budget.adapt_extension` | `extensions_used` |
| Budget | `budget.exhausted` | `category` / `limit` |

> **铁律**：表中 topic 在 SemVer 内稳定。**其他 topic** 仍可订阅（EventBus 是开放的），但**不在 SemVer 稳定保证内** — 主仓 refactor 可能 break。

---

## §7. LLM Record/Replay 框架

> 详细设计文档：[`advanced-development-guide.md` §6](./advanced-development-guide.md)（三层测试金字塔 — Unit / Replay / Real LLM E2E）。

### §7.1 `LLMReplayStore`

文件型 KV 存储，key=request_hash，value=ReplayRecord。线程安全。

```python
class LLMReplayStore:
    def __init__(self, path: Path, mode: Mode, on_miss: MissPolicy = "raise") -> None: ...

    @classmethod
    def from_env(
        cls, path: str,
        mode_env: str = "KROW_LLM_REPLAY_MODE",
        default: Mode = "replay",
    ) -> "LLMReplayStore": ...

    @property
    def mode(self) -> Mode: ...
    @property
    def path(self) -> Path: ...
    @property
    def on_miss(self) -> MissPolicy: ...

    def size(self) -> int: ...
    def put(self, record: ReplayRecord) -> None: ...
    def get(self, request_hash: str) -> Optional[ReplayRecord]: ...
    def has(self, request_hash: str) -> bool: ...
```

#### 类型别名

```python
Mode = Literal["record", "replay", "auto"]
MissPolicy = Literal["raise", "passthrough", "record_on_miss"]
```

| `Mode` 值 | 行为 |
|---|---|
| `record` | 透传到真实 LLM，把每次调用写进 fixture |
| `replay` | 不调真实 LLM，按请求哈希直接读 fixture |
| `auto` | fixture 文件存在 → replay；否则 → record |

| `MissPolicy` 值 | replay 模式下找不到对应 fixture 时的行为 |
|---|---|
| `raise`（默认） | 抛 `LLMReplayMiss`（CI 严格） |
| `passthrough` | 静默调真实 LLM，**不**回写 fixture |
| `record_on_miss` | 调真实 LLM **并回写** fixture（auto 模式默认） |

#### `from_env` env var 协议

| env var | 含义 | 缺省 |
|---|---|---|
| `KROW_LLM_REPLAY_MODE` | `"record"` / `"replay"` / `"auto"` | 由 `default` 参数决定 |

> **建议**：CI 跑 replay；本地写新测试用例时 `record` 录一次后切回 `replay`。

#### 使用例（手动管理 vs SDK 自动管理）

```python
# 推荐：让 SDK 自动管理生命周期（详 §2.9 with_replay_store）
from krow_agent_sdk import AgentBuilder
from krow_agent_sdk.replay import LLMReplayStore

store = LLMReplayStore.from_env("fixtures/my_test.json")
agent = AgentBuilder.from_env().with_replay_store(store).build()
try:
    result = agent.run("...")
finally:
    agent.shutdown()  # 自动 uninstall replay swap
```

```python
# 手动方式（高级用户 / 多 swap 链场景）
from krow_agent_sdk.replay import LLMReplayStore, wrap_provider_manager_with_replay

store = LLMReplayStore.from_env("fixtures/my_test.json")
swap = wrap_provider_manager_with_replay(store)
try:
    # 跑你的测试 ... agent.run(...)
finally:
    swap.uninstall()
```

---

### §7.2 `LLMReplayMiss` / `LLMReplayError`

```python
class LLMReplayError(RuntimeError): ...

class LLMReplayMiss(LLMReplayError):
    """replay 模式下找不到对应的录制记录"""
    request_hash: str

    def __init__(self, request_hash: str, prompt_preview: str) -> None: ...
```

抛出时机：`mode="replay"` + `on_miss="raise"` 且 fixture 内无对应 hash。

```
LLMReplayMiss: LLM replay cache miss hash=a1b2c3d4e5f6 prompt='帮我写一段...'.
请在 record 模式下重新录制 fixture。
```

---

### §7.3 `wrap_provider_manager_with_replay`

```python
def wrap_provider_manager_with_replay(store: LLMReplayStore) -> _ProviderMethodSwap: ...
```

把 SDK 默认的 `AIProviderManager` 全部 provider 的 `generate` / `stream` 方法替换为 `RecordReplayWrapper` 包装版；同时 hook `LLMProviderManager.get_chat_model` / `get_reasoning_model` 让动态获取的 adapter 也走 replay。

返回 `_ProviderMethodSwap`，含 `install()`（已自动调）+ `uninstall()` 方法。

| 错误 | 触发 |
|---|---|
| `LLMReplayError` | 主仓 `modules.ai.providers` 不可用（说明 SDK 安装不完整） |

---

### §7.4 `compute_request_hash` / `ReplayRecord`

```python
def compute_request_hash(messages: Any, extra: Optional[Dict[str, Any]] = None) -> str:
    """对 messages + extra 元数据计算稳定哈希（SHA-256 前 32 hex）。"""
    ...

@dataclass
class ReplayRecord:
    request_hash: str
    messages: List[Dict[str, str]]
    response: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]: ...
    @classmethod
    def from_json(cls, obj: Dict[str, Any]) -> "ReplayRecord": ...
```

| `compute_request_hash` 的 canonical 化 | 行为 |
|---|---|
| `messages` | 只看 `role` + `content`（去除时间戳类动态字段） |
| `content` | `\r\n` → `\n`，trim 首尾空白 |
| `extra` | 按 key 字典序 sort（保稳定） |

#### Fixture 文件 schema (JSON)

```json
{
  "version": 1,
  "records": [
    {
      "request_hash": "a1b2c3d4...",
      "messages": [
        {"role": "user", "content": "..."}
      ],
      "response": "...",
      "timestamp": 1731000000.0,
      "metadata": {
        "provider": "krow_cloud_chat",
        "kw.temperature": 0.7
      }
    }
  ]
}
```

---

## §8. Auth / LLM / Data Facade

### §8.1 `auth` — API key 校验

```python
from krow_agent_sdk import auth
```

| 函数 | 签名 | 用途 |
|---|---|---|
| `auth.validate_api_key_format(api_key)` | `(str) -> str` | 校验格式（`^sk-[A-Za-z0-9_\-]{17,}$`），通过返回 stripped key；不合法抛 `InvalidKrowAPIKeyError` |
| `auth.read_api_key_from_env()` | `() -> str` | 从 `KROW_API_KEY` env var 读 + 校验；缺失抛 `MissingKrowAPIKeyError` |
| `auth.read_project_root_from_env()` | `() -> str \| None` | 读 `KROW_PROJECT_ROOT` env；缺失返 `None` |

| 常量 | 值 |
|---|---|
| `auth.ENV_KROW_API_KEY` | `"KROW_API_KEY"` |
| `auth.ENV_KROW_PROJECT_ROOT` | `"KROW_PROJECT_ROOT"` |

> 大多数情况外部开发者不需要直接调这些函数 — `AgentBuilder.from_env()` 内部已经处理。手动调时主要用于自定义 `BuilderConfig` 构建流程。

---

### §8.2 `llm` — Plugin source helper

让 plugin 在 LLM 调用时正确标注 source_module（用于 audit / observability / tracing）。

```python
from krow_agent_sdk import llm
```

| 符号 | 类型 | 说明 |
|---|---|---|
| `llm.ChatMessage` | dataclass | `ChatMessage(role: str, content: str)`；与主仓 `modules.ai.providers.ChatMessage` 等价（runtime 装上后直接使用真实，否则 fallback 到 SDK vendored stub） |
| `llm.LLMSourceModule` | class with constants | 主仓内置常量：`PLANNER` / `EXECUTOR` / `REACT_THINKER` / `EVALUATOR` / `SUMMARY_REPORT` / `AI_MANAGER` / ... |
| `llm.llm_source_context(module: str)` | context manager | 通过 ContextVar 注入 source_module（**不是** `provider.generate()` 的参数） |
| `llm.make_plugin_source_module(plugin_id)` | `(str) -> str` | 生成 plugin 命名空间字符串 `"plugin:<plugin_id>"` |

#### Plugin 内调 LLM 的正确模板

```python
from krow_agent_sdk.llm import (
    ChatMessage, llm_source_context, make_plugin_source_module,
)

class ResearchToolHelper:
    plugin_id = "acme.research"
    SOURCE_MODULE = make_plugin_source_module(plugin_id)
    # → "plugin:acme.research"

    def synthesize(self, items: list[str], provider) -> str:
        with llm_source_context(self.SOURCE_MODULE):
            response: str = provider.generate([
                ChatMessage(role="user", content=f"Synthesize: {items}"),
            ])
        return response
```

> **铁律**：`source_module` 不是 `generate()` 的参数，是 ContextVar。详见 `advanced-development-guide.md` §2 LLM 调用反模式。

---

### §8.3 `data` — 只读数据 facade

```python
from krow_agent_sdk import data
```

只读访问 agent 内部数据层（StateManager / GlobalOntology / ExperienceMemory）。

| 函数 | 签名 | 返回 dict 主字段 |
|---|---|---|
| `data.get_state_snapshot(agent=None)` | `(Agent\|None) -> dict` | `current_session_id` / `todos_count` / `todos[≤50]` / `sub_states_count` / `is_initialized` |
| `data.get_global_ontology_snapshot(project_root=None)` | `(str\|Path\|None) -> dict` | `version` / `counts: {concept, entity, event, relation, document_chunk, action}` / `total` |
| `data.query_global_ontology(query, *, project_root=None, limit=10)` | `(str, ...) -> dict` | `query` / `matches[{object_type, id, label}]` / `match_count` |
| `data.get_memory_stats()` | `() -> dict` | `is_initialized` / `stats` (MemoryGraphService.get_stats() 转发) |
| `data.query_memories(query_text, *, limit=10, session_id=None, project_id=None)` | `(str, ...) -> dict` | `query` / `results[{id, node_type, title, content_preview, strength, tags}]` / `count` |
| `data.list_reasoning_results(project_root=None, limit=20)` | `(str\|Path\|None, int) -> dict` | `results[{reasoning_id, path, mtime}]`（按 mtime 倒序）/ `count` |
| `data.get_reasoning_result(reasoning_id=None, project_root=None)` | `(str\|None, str\|Path\|None) -> dict` | `ReasoningResult.model_dump` 结构（`hypotheses` / `evidences` / ACH 矩阵 / `doubts` / `reasoning_tree` / `metadata.completeness_scorecard`）；`reasoning_id=None` 取最新一条 |

> **推理产物出口**（PR-A · 议题 3）：`list_reasoning_results` / `get_reasoning_result` 读的是 `<project_root>/.krow/reasoning/*.json`，**前置** `AgentBuilder.with_reasoning_artifacts()` 已启用（见 [§2.4](#24-预算与-http-gateway)）；未启用时目录为空。这让 headless SDK 拿到与桌面推理工作台**同一份结构化产物**（竞争假设矩阵 / 证据链 / 疑点 / 递归推理树），只是没有 UI 画布。需要强类型时 `from krow_agent_sdk import ReasoningResult; ReasoningResult.model_validate(d)`（惰性 re-export）。

#### 设计原则

- **read-only** — 不暴露 store 实例
- **不抛异常** — 失败返 `{"error": "..."}`
- **零 LLM 调用** — 走 SQLite / 内存查询
- **零副作用** — 不发 EventBus 事件、不修改 state

```python
from krow_agent_sdk import data
import json

snap = data.get_global_ontology_snapshot()
print(json.dumps(snap, indent=2, ensure_ascii=False))
# {"is_initialized": true, "version": 23, "counts": {"concept": 12, "entity": 45, ...}, "total": 67}

hits = data.query_global_ontology("机器学习", limit=5)
for m in hits["matches"]:
    print(f"{m['object_type']}/{m['id']}: {m['label']}")
```

---

## §9. Diagnostics / Hints / Visual / Lifecycle

### §9.1 `diagnostics` — 状态导出

```python
from krow_agent_sdk import diagnostics
```

| 函数 | 签名 | 返回 |
|---|---|---|
| `diagnostics.dump_state(agent=None)` | `(Agent\|None) -> dict` | 全景 dict：sdk_version / plugin / tool / hint / event / observability / mcp_servers / security_policies / visual_adapters / recommended_budget |
| `diagnostics.get_plugin_snapshot(agent=None)` | `(Agent\|None) -> dict` | `loaded_plugin_ids[]` + `by_protocol: {hint, gate, observability}` |
| `diagnostics.get_tool_snapshot()` | `() -> dict` | `count` + `tools[{name, category, server_name, complexity, user_visible, is_internal, direct_output}]` |
| `diagnostics.get_hint_snapshot()` | `() -> dict` | `count` + `plugin_ids[]` |
| `diagnostics.get_observability_snapshot()` | `() -> dict` | `count` + `plugin_ids[]` |
| `diagnostics.get_event_subscription_snapshot()` | `() -> dict` | `topics: {topic: count}` + `total_subscribers` |
| `diagnostics.get_overlay_snapshot(store_path=None)` | `(str\|None) -> dict` | 慢环 learned overlay 只读快照：`store_path` / `exists` / `count` / `by_status{candidate,active,demoted}` / `by_tier{0,1}` / `lessons[{id,text,tier,status,lesson_type,recurrence,positive_outcomes,negative_outcomes,disclosure_triggers,...}]` |

> `get_overlay_snapshot` 用于审视双环元认知**慢环**的睡眠蒸馏结果（哪些教训是候选 / 已晋级 active / 复现与正负反馈计数）。字段语义 / 晋级阈值 / 维护方式见 [`advanced-development-guide.md`](./advanced-development-guide.md)「双环元认知与运行时自进化」。

#### 设计约束

- **read-only** — 不修改状态
- **不抛异常** — 失败返 `{"error": "..."}`
- **不暴露主仓内部对象** — 全是 plain Python（dict / list / 基础类型）
- **零 LLM 调用** — System 1 / 确定性查询

```python
import json
from krow_agent_sdk.diagnostics import dump_state

agent = AgentBuilder.from_env().with_tool_plugin(my_plugin).build()
state = dump_state(agent)
print(json.dumps(state, indent=2, ensure_ascii=False))
# 检查 my_plugin 的工具有没有真注册到 ToolManager
print([t["name"] for t in state["tool"]["tools"] if t["server_name"].startswith("extension_")])
```

---

### §9.2 `hints` — Hint Registry

```python
from krow_agent_sdk import hints
from krow_agent_sdk.hints import HintRegistry, get_hint_registry
```

进程级 singleton。**通常外部开发者不需要直接接触** —— SDK 在 `with_hint_plugin(plugin)` 时自动调 `register_hint`，`Agent.shutdown()` 时自动 `unregister_hint`。

```python
class HintRegistry:
    def register_hint(
        self, plugin_id: str, hint_callable: Callable[[dict], str | None],
        *, applicable_acts: list[str] | None = None,
    ) -> None: ...
    def unregister_hint(self, plugin_id: str) -> None: ...
    def list_plugin_ids(self) -> list[str]: ...
    def render_hints(self, context: dict, *, scope: str = "macro") -> str: ...
    def render_macro_hints(self, context: dict) -> str: ...
    def render_micro_hints(self, context: dict) -> str: ...
    def clear(self) -> None: ...
```

| 行为 | 说明 |
|---|---|
| 同 `plugin_id` 重复 register | 后注册覆盖前一次（支持 hot reload） |
| 渲染顺序 | FIFO |
| handler 抛异常 | swallow + log error，不影响其他 plugin |
| 拼接分隔符 | `"\n\n"` |
| `applicable_acts=None / []` | 全局 hint，所有 ACT 触发 |

```python
from krow_agent_sdk.hints import get_hint_registry

reg = get_hint_registry()
print(reg.list_plugin_ids())  # debug 用
```

---

### §9.3 `visual` — VisualAdapter 与 visual_inspect

```python
from krow_agent_sdk import visual
```

| 符号 | 类型 | 说明 |
|---|---|---|
| `visual.VisualAdapter` | ABC | 视觉适配器协议（5 抽象方法 + 1 property） |
| `visual.ElementEntry` | dataclass | inventory 返回元素 |
| `visual.SceneConfig` | dataclass | 场景配置（默认尺寸等） |
| `visual.SemanticRole` | enum | 语义角色 |
| `visual.SemanticMap` | dataclass | 语义图谱 |
| `visual.VisualGroundingResult` | dataclass | 视觉定位结果 |
| `visual.visual_inspect(file_path, page_index=0, **kwargs)` | function | 给 plugin 在测试 / hint 上下文中调用 |
| `visual.register_default_pptx_adapter()` | `() -> str` | 函数式注册 PPTX 默认适配器（**进程级**；多 Agent 场景请用 [`with_default_pptx_adapter`](#26-visual-adapter-注入3-路径) 改 Agent 局部生效） |

#### `VisualAdapter` ABC（5 抽象方法）

```python
class VisualAdapter(ABC):
    @abstractmethod
    def open(self, source: str | Path, **kwargs) -> None: ...
    @abstractmethod
    def close(self) -> None: ...
    @abstractmethod
    def render(self, page_index: int, width: int = 960, height: int = 540) -> bytes: ...
    @abstractmethod
    def inventory(self, page_index: int) -> list[ElementEntry]: ...
    @abstractmethod
    def page_count(self) -> int: ...
    @property
    def scene_config(self) -> SceneConfig: ...   # 默认值即可
```

| 方法 | 用途 |
|---|---|
| `open(source, **kwargs)` | 打开文件 / URL |
| `close()` | 释放资源 |
| `render(page, w, h)` | 渲染指定页为 PNG bytes |
| `inventory(page)` | 列出指定页的元素 metadata（位置 / 类型 / 文本） |
| `page_count()` | 总页数 |
| `scene_config` | 默认尺寸 / 字体等 |

> 完整 PPTX 自定义实现示例详 [`advanced-development-guide.md` §4](./advanced-development-guide.md)。

---

### §9.4 `lifecycle` — 生命周期 hook

```python
from krow_agent_sdk import lifecycle
from krow_agent_sdk.lifecycle import BasePluginLifecycle, SDKContext
```

#### `SDKContext` dataclass

```python
@dataclass
class SDKContext:
    api_key: str          # 已 mask
    project_root: Path
    sdk_version: str
    extra: dict[str, Any] = field(default_factory=dict)
```

SDK 在调 plugin lifecycle hook 时注入。

#### `BasePluginLifecycle` Protocol

```python
@runtime_checkable
class BasePluginLifecycle(Protocol):
    def on_load(self, ctx: SDKContext) -> None: ...      # 可选
    def on_unload(self, ctx: SDKContext) -> None: ...    # 可选
```

任何 plugin 都可**额外**实现这两个方法（Protocol runtime_checkable 不强制 Required，duck typing）。SDK 在以下时机自动调：

| 时机 | hook |
|---|---|
| `AgentBuilder.build()` 内 plugin 加载完成、`Agent` 构造之前 | `on_load(ctx)` |
| `Agent.shutdown()` 反向遍历 cleanup callback | `on_unload(ctx)` |

```python
class MyPlugin:
    plugin_id = "acme.research"

    def on_load(self, ctx):
        print(f"loading; project={ctx.project_root}")
        self._db = open_my_db()

    def on_unload(self, ctx):
        self._db.close()
```

| 异常处理 | 行为 |
|---|---|
| `on_load` 抛异常 | 走 plugin error mode（详 [`with_*_plugin` 错误处理](#210-build--构造-agent)） |
| `on_unload` 抛异常 | swallow + log error（不阻塞其他 cleanup） |

---

### §9.5 `extended_md_supplement_registry` — ACT 扩展 markdown

```python
from krow_agent_sdk import extended_md_supplement_registry
```

让 [`DomainPackPlugin`](#59-domainpackplugin--一站式-p9--experimental) 给 native ACT 追加 supplementary `extended.md` 文本。

| 函数 | 签名 | 用途 |
|---|---|---|
| `register_extended_md_supplement(plugin_id, target_act, text)` | `(str, str, str) -> None` | 注册 supplement |
| `unregister_extended_md_supplement(plugin_id)` | `(str) -> bool` | 反注册（plugin shutdown） |
| `get_supplements_for(act_name)` | `(str) -> list[(plugin_id, text)]` | 列出某 ACT 的全部 supplement |
| `merge_supplements_into_extended_md(act_name, base_extended_md)` | `(str, str) -> str` | 主仓 ACT 加载链路用，外部少用 |

#### v0.8 A9 限制

| 限制 | 上限 |
|---|---|
| 单 plugin 单 target ACT supplement | 4 KB |
| 整个进程内 supplement 累计 | 16 KB |

---

### §9.6 `metacognition` — 配置决策脑三注册表

```python
from krow_agent_sdk import (
    register_situation_contributor,
    register_wake_trigger,
    register_decision_classifier,
    get_registry_snapshot,
)
# 或：from krow_agent_sdk.metacognition import register_situation_contributor
```

Krow 的 macro 编排是元认知**决策脑**（GWT 全局工作站）：所有观测进工作站 → **稀疏**唤醒 → 注意力广播 → LLM 决策 → 信用回喂。它的领域扩展点是**三注册表**——把你自己垂直功能（如文献检索、报告生成）的**完整度信号**接进来，决策脑才能对你的任务"看得见、叫得醒、算得清"。

| 函数 | 签名 | 用途 |
|---|---|---|
| `register_situation_contributor(target)` | `(type\|callable\|str) -> str` | **观测层**：登记 SituationContributor（`applicable()`+`__call__()->{"error_vector","signals"}`） |
| `register_wake_trigger(target)` | `(callable\|str) -> str` | **唤醒层**：登记 WakeTrigger（`(prev,curr,delta,ledger)->str\|None`） |
| `register_decision_classifier(target)` | `(callable\|str) -> str` | **结算层**：登记 DecisionClassifier（`(action,snap,ledger)->str\|None`） |
| `get_registry_snapshot()` | `() -> dict` | 只读：三注册表已登记内容 + 计数（debug"我的 contributor 注册上了吗"） |

**入参**：可传**类/函数对象**（facade 自动推导 FQCN 并**校验可 re-import**）或 **FQCN 字符串** `pkg.mod:Symbol`。返回实际登记的 FQCN。

**三层契约**：

| 层 | 你实现 | 返回 |
|---|---|---|
| Contributor | `applicable(executor)->bool` + `__call__(executor)->dict` | `{"error_vector": {名: 0~1 距离}, "signals": {名: 值}}`（两键均可选） |
| WakeTrigger | `(prev, curr, delta, ledger)->str\|None` | 命中返唤醒事由字符串；否则 `None`。设 `fn.l0_event=True` 让它在软预算耗尽后仍能唤醒（完整度红线） |
| DecisionClassifier | `(action, snap, ledger)->str\|None` | 把 LLM 揭示的动作归类（信用回喂）；未命中 `None` 回落核心矩阵 |

**fail-loud 守门**（挡"注册≠激活"半边墙）：三者都必须是**模块顶层**类/函数——决策脑按 FQCN re-import 实例化，本地类 / lambda / 嵌套类在加载期只会被 silent 跳过。本 facade 在**注册期**就对不可 re-import 的 target `raise ValueError`。

**可观测**：决策脑运行时 emit `cognitive.situation` / `cognitive.decision_wake` / `cognitive.decision_feedback` 事件（SDK 默认订阅，见 [§6.3](#63-稳定-topic-速查)）。

完整实战（观测层 error_vector 设计、稀疏唤醒纪律、L0/L1/L2 权威阶梯、反模式）见 [`advanced-development-guide.md`](./advanced-development-guide.md) §10「配置决策脑三注册表」+ cookbook `examples/cookbook/litsci-metacog/`。

---

## §10. Telemetry 反向遥测

```python
from krow_agent_sdk import telemetry
```

⚠️ experimental — Wave 2 PR S2.17。**默认 OFF**，需用户 opt-in（`KROW_SDK_TELEMETRY_ENABLED=1`）。

| 函数 | 用途 |
|---|---|
| `telemetry.is_telemetry_enabled()` | 判断是否启用 |
| `telemetry.get_telemetry_client()` | 获取 singleton client（生产基本不需直接用） |

#### `TelemetryPayload` dataclass（dict 化）

| 字段 | 含义 |
|---|---|
| `sdk_version` | SDK 语义版本 |
| `python_version` | 例 "3.13" |
| `os` | 例 "linux" / "darwin" / "windows" |
| `plugin_id_hashes` | 已注册 plugin_id 的 SHA-256 前 16 hex（**不上报明文**） |
| `agent_run_count` | 周期内 `agent.run` 次数 |
| `error_types` | 周期内异常类名集合（不上报 stack trace） |

#### 隐私保护

- 所有 plugin_id 走 SHA-256 哈希 → 不上报明文
- 上报内容前过 `_contains_secret_pattern` 正则（`sk-...` / API key 形态）→ 命中则丢弃整个 payload
- 默认 OFF；用户必须显式 opt-in（`KROW_SDK_TELEMETRY_ENABLED=1`）

---

## §11. Test SDK — 开发者写 plugin 的测试工具

```python
# 仅在 SDK 装在 monorepo 开发模式（pip install -e .）时可用；
# wheel 安装后 tests/support 不在 wheel 内，import 静默失败（详 __init__.py P0b）
from krow_test_sdk import HeadlessAgentHarness, AgentRunResult, LLMReplayStore
```

| 符号 | 用途 |
|---|---|
| `HeadlessAgentHarness` | 无 UI 的 Agent harness，便于 plugin / 集成测试 |
| `AgentRunResult` | 简化版 `AgentV3Result` dataclass（含 `success` / `final_output` / `metadata`） |
| `LLMReplayStore` | 与 `krow_agent_sdk.replay.LLMReplayStore` 等价（重复 alias） |

#### 例（pytest fixture）

```python
import pytest
from pathlib import Path
from krow_test_sdk import HeadlessAgentHarness

@pytest.fixture
def my_plugin_harness(tmp_path: Path):
    harness = HeadlessAgentHarness(
        project_root=tmp_path,
        plugins=[MyResearchToolsPlugin()],
        replay_fixture=Path(__file__).parent / "fixtures/research_replay.json",
    )
    yield harness
    harness.shutdown()

def test_my_plugin(my_plugin_harness):
    result = my_plugin_harness.run("research the topic X")
    assert result.success
    assert "Topic X" in result.final_output
```

> Wheel 用户走 PyPI 安装时 `krow_test_sdk` 不可用；这是有意设计 — 外部 plugin 包通常以 monorepo 形态开发（`pip install -e ./packages/krow-agent-sdk`），不需要 production 走 wheel。
> 如果你只用 wheel 装 SDK 又想跑测试 → 用 [§7 Replay 框架](#7-llm-recordreplay-框架) 直接构造 Agent 测试。

---

## §12. Errors — 错误层与黄金模板

```python
from krow_agent_sdk.errors import KrowSDKError  # 根基类
```

所有 SDK fail-loud 错误继承 `KrowSDKError`。每个错误的 message 严格按 [`AGENTS.md §五 黄金模板`](https://github.com/aullik5/krow-sdk-docs/blob/main/docs/advanced-development-guide.md)：**一句话 + 原因 + 位置 + 1-3 个修法 + 相关链接**。

### §12.1 异常层次树

```
RuntimeError
└── KrowSDKError (根基类)
    ├── 认证 / API Key 类
    │   ├── MissingKrowAPIKeyError       # 既未 with_krow_api_key 也未 KROW_API_KEY env
    │   ├── InvalidKrowAPIKeyError       # 格式校验失败（非 sk- 前缀 / 含非法字符 / 长度不足）
    │   ├── InvalidKrowBaseURLError      # with_base_url(url) 格式不符 (非 https / 含 path / 尾斜杠)
    │   ├── KrowAPIKeyInvalidError       # 首次 LLM 调用 401（cloud 拒绝）
    │   ├── KrowQuotaExceededError       # LLM 调用 402（余额 / 配额超限）
    │   └── LLMProviderError             # LLM 网络 / 5xx / fallback 链耗尽
    │
    ├── Project root 类
    │   ├── MissingProjectRootError      # 既未 with_project_root 也未 KROW_PROJECT_ROOT env
    │   └── ProjectRootNotWritableError  # validate_connection 时项目根不可写
    │
    └── Plugin 类
        ├── PluginSignatureMismatchError  # plugin 实现签名与 Protocol 不一致
        ├── InvalidPluginIDError          # plugin_id 不符合 <org>.<plugin_name> 双段命名
        ├── DuplicatePluginIDError        # 进程内 plugin_id 撞名
        └── PluginLoadError               # plugin import / on_load 抛异常
```

### §12.2 错误详细表

| 错误 | 触发时机 | 关键 fields |
|---|---|---|
| `MissingKrowAPIKeyError` | `build()` 时既未 `with_krow_api_key` 也未 env | — |
| `InvalidKrowAPIKeyError` | `with_krow_api_key(key)` 调用时 | `masked_key` |
| `InvalidKrowBaseURLError` | `with_base_url(url)` 调用时 (非 https / 含 path / 尾斜杠 / 空) | `url` |
| `KrowAPIKeyInvalidError` | 首次 LLM 调用 cloud 返 401 | — |
| `KrowQuotaExceededError` | LLM 调用 cloud 返 402 | — |
| `LLMProviderError` | LLM 重试链耗尽 | `reason` |
| `MissingProjectRootError` | `build()` 时既未 `with_project_root` 也未 env | — |
| `ProjectRootNotWritableError` | `validate_connection=True` 时项目根写权限测试失败 | `project_root` |
| `PluginSignatureMismatchError` | plugin 加载期 `_protocol_validator` 校验失败 | `plugin_id` / `protocol_name` / `method` / `expected_sig` / `actual_sig` |
| `InvalidPluginIDError` | plugin_id 不合法 | `plugin_id` |
| `DuplicatePluginIDError` | 同进程 plugin_id 撞名 | `plugin_id` / `conflict_entry` / `existing_entry` |
| `PluginLoadError` | plugin entry_points 加载 / on_load 抛 | `plugin_id` / `reason` / `location` |

### §12.3 黄金模板示例（`MissingKrowAPIKeyError`）

```
❌ AgentBuilder.build() 缺少 krow cloud API key.
原因：strong-bound LLM 链路（详 design doc §3）必须有有效 API key 才能调 https://api.krow.cn/v1。
位置：AgentBuilder（任一 with_* 链尾的 .build() 调用点）。
你可以：
  1) 在 https://krow.cn API 密钥页面创建 key（前缀 sk-user-），
     然后调 .with_krow_api_key('sk-user-xxxxx').build()
  2) 设环境变量 KROW_API_KEY=sk-user-xxxxx，
     然后用 AgentBuilder.from_env().build()
  3) 见 docs/sdk/api-reference.md §1 + advanced-development-guide.md §6.1
```

> 详细黄金模板设计原则见 [`advanced-development-guide.md` §3.5 工具错误信息](./advanced-development-guide.md)。

### §12.4 错误处理推荐姿势

```python
from krow_agent_sdk.errors import (
    KrowSDKError,
    KrowQuotaExceededError, KrowAPIKeyInvalidError,
    PluginLoadError,
)

try:
    agent = AgentBuilder.from_env().build()
    result = agent.run(user_input)
except KrowQuotaExceededError:
    # 提示用户升级套餐 / 切到 replay
    notify_user("配额已耗尽，请升级套餐或开启 replay 模式")
except KrowAPIKeyInvalidError:
    # API key 已撤销 / 过期；让用户去 krow.cn 重新创建
    notify_user("API key 失效，请到 https://krow.cn 重新创建")
except PluginLoadError as exc:
    logger.error(f"plugin 加载失败 plugin={exc.fields.get('plugin_id')}", exc_info=True)
except KrowSDKError as exc:
    # 兜底：所有 SDK 错误都继承 KrowSDKError
    logger.error(f"SDK error: {exc}", exc_info=True)
finally:
    if 'agent' in locals():
        agent.shutdown()
```

---

## §13. 环境变量与 feature flag 速查

| env var | 默认 | 用途 |
|---|---|---|
| `KROW_API_KEY` | (空) | API key（`AgentBuilder.from_env()` 读） |
| `KROW_PROJECT_ROOT` | (空) | 项目根（`AgentBuilder.from_env()` 读） |
| `KROW_SDK_BUILD_VALIDATE_CONNECTION` | `1` | `build()` 默认是否做启动期连接校验 |
| `KROW_SDK_PLUGIN_ERROR_MODE` | `swallow` | plugin 错误模式：`swallow` / `raise` / `quiet` |
| `KROW_SDK_HTTP_GATEWAY` | `0` | feature flag：自动启用 HTTP Gateway（默认 host/port） |
| `KROW_ENABLE_PLUGIN_ENTRY_POINTS` | `0` | feature flag：`with_*_plugins_from_entry_points` 是否真扫描 |
| `KROW_ENABLE_MCP_SERVER_PLUGIN` | `0` | feature flag：MCPServerPlugin 形态 B（in-process）是否注册到 ToolManager |
| `KROW_PLUGIN_P10_VISUAL_ADAPTER` | `0` | feature flag：VisualAdapterPlugin entry_points 自动扫描 |
| `KROW_SDK_SIGNATURE_VALIDATION` | `1` | plugin 签名验证（设 `0` 跳过；不推荐生产） |
| `KROW_LLM_REPLAY_MODE` | `replay` | LLMReplayStore.from_env 默认模式：`record` / `replay` / `auto` |
| `KROW_SDK_TELEMETRY_ENABLED` | `0` | 是否反向上报 telemetry |
| `KROW_HEADLESS` | `0` | 主仓 headless 模式（影响内置 Visual Adapter 选择） |

#### 双环元认知 / 运行时自进化 kill switch（默认全 **ON**）

> 这些 flag 控制 [`advanced-development-guide.md`](./advanced-development-guide.md)「双环元认知与运行时自进化」描述的快环（认知负荷软提示）+ 慢环（睡眠蒸馏 / overlay 注入 / 晋级）。**默认全开**，设 `0`/`false`/`off`/`no` 关闭对应环节。

| env var | 默认 | 用途 |
|---|---|---|
| `KROW_METACOG_PROVIDER` | `1` | 快环：strained/overload 时注入认知负荷软提示到 prompt |
| `KROW_GOAL_GAP_FEEDER` | `1` | 快环：预算-目标背离（budget-goal divergence）感知与软提示 |
| `KROW_OVERLOAD_RESOLVE` | `1` | 快环：overload 时尝试无损过载重整 |
| `KROW_SLEEP_PHASE` | `1` | 慢环：睡眠期蒸馏（按簇聚类高频信号 → candidate 教训） |
| `KROW_OVERLAY_INJECT` | `1` | 慢环：把 active overlay 教训按 disclosure_triggers 注入 prompt |
| `KROW_OVERLAY_BEHAVIOR_CHANGE` | `1` | 慢环：允许 behavior-change 类教训晋级（软启动低权重） |
| `KROW_OVERLAY_FULL_WEIGHT` | `1` | 慢环：允许 behavior-change 教训长期在线正向后升全权重（否则封顶 0.7） |

#### 推理判别 / 长跑弹性 kill switch（0.9.0.48+ · 默认全 **ON**）

> 这些 flag 控制推理任务的判别性收口门与规模自适应预算。**默认全开**，设 `0`/`false`/`off`/`no` 关闭对应环节。

| env var | 默认 | 用途 |
|---|---|---|
| `KROW_REASONING_LONGRUN` | `1` | 8h 弹性长跑：墙钟到点时若推理对象仍有净增则里程碑续期（封顶 8h），并同步放开进度驱动的预算延长配额 + LLM 调用配额；每次续期发 `agent.max_wallclock_extended` 事件 + store checkpoint 落盘 |
| `KROW_VAGUE_WINNER_GATE` | `1` | 收口门：胜出假设未具名（"不知名第三者"式）且仍有未排除的具名候选时阻塞结案，逼具名或诚实降置信 |
| `KROW_ACH_FLIP_GROUNDING` | `1` | 反驳链接接地背书：`contradicts/refutes` 链接引用的证据必须真的提到被排除对象，否则降权为 weak 并 fail-loud 提示 |
| `KROW_WALLCLOCK_CORPUS_SCALE` | `1` | 墙钟档位 × 语料规模线性联动（≤1.5x 封顶） |
| `KROW_ITER_CORPUS_SCALE` | `1` | 迭代类预算（guard 补偿 / micro 迭代 cap）× 语料规模线性联动（≤4.0x 封顶，`KROW_ITER_CORPUS_MAX_FACTOR` 可调） |
| `KROW_SCORECARD_ENFORCE` | `1` | 完整度记分卡 enforce（推理任务专属）：结案时有完整度缺口 → BLOCK 并注入具体缺口（有界 2 次后降级放行）；设 `0` 回 warning-only 观测。结案快照始终附在报告"完整度记分卡（结案快照）"小节 |
| `KROW_DOUBT_GATE_MAX_BLOCKS` | `3` | 疑点消解门 block 预算（普通任务）：高置信疑点悬而未决时阻塞 conclude 的最大次数 |
| `KROW_DOUBT_GATE_LONGRUN_MAX_BLOCKS` | `8` | 疑点消解门 block 预算（真推理族长跑任务）：配合 8h 弹性续期，先用续期时间驱动定向搜证消解疑点再谈降级；降级放行发 `reasoning.doubt.degraded` 事件（剩余疑点快照） |

#### Feature flag 协议

| 真值 | 假值 |
|---|---|
| `1` / `true` / `yes` / `on`（任意大小写） | 其他（默认） |

---

## §14. 版本兼容性 / 稳定性 / Deprecation

### §14.1 SemVer 语义

| 版本号 | 修改语义 |
|---|---|
| `MAJOR` (`X.y.z`) | breaking 变更（删除 stable API / 改函数签名 / 改 dataclass 必需字段） |
| `MINOR` (`x.Y.z`) | 添加新 API / 改 experimental 协议 |
| `PATCH` (`x.y.Z`) | bug 修复 / 内部改进 / 文档更新 |
| `HOTFIX` (`x.y.z.W`, 4 段) | 紧急 patch（如 PyPI 元数据修复 PR #328 / #331） |

### §14.2 Stability promise

| API | Stability | 修改通知 |
|---|---|---|
| `AgentBuilder` 主链方法（必须项 + plugin 注入 + budget） | **Stable** | 任何 breaking 必须 MAJOR + 提前 1 release deprecation 警告 |
| `Agent.run` / `Agent.run_stream` / `Agent.shutdown` | **Stable** | 同上 |
| `BudgetSpec` / `BuilderConfig` | **Stable** | 加新字段必须有 default（OCP） |
| 6 个 stable Plugin Protocols | **Stable** | 加新方法必须 OPTIONAL |
| `EventBusReader` / `StreamItem` / 黑名单稳定 topic | **Stable** | topic schema 变更必须 MAJOR |
| `errors.*` 错误类 | **Stable** | 不删 class；message 文本可改 |
| `auth` / `llm` / `data` / `diagnostics` / `hints` 公开函数 | **Stable** | 同上 |
| `replay` 框架（除 `_ProviderMethodSwap`） | **Stable** | — |
| `experimental.protocols.*` | ⚠️ Experimental | 无 breaking 通知；可在 MINOR 删除/改名 |
| `HttpGatewaySpec` / `_HttpGatewayHandle` | ⚠️ Experimental | 同上 |
| `telemetry` | ⚠️ Experimental | 同上 |
| `test_sdk` | ⚠️ Experimental | 仅 monorepo 开发模式可用 |
| `_*` / `_vendor.*` | Internal | 任意 release 可改 |

### §14.3 Deprecation 流程

SDK 用 `@deprecated` decorator（`from krow_agent_sdk import deprecation`）标注：

```python
from krow_agent_sdk.deprecation import deprecated, is_deprecated, get_deprecation_metadata

@deprecated(
    since_version="0.9.0",
    removed_in="0.11.0",
    replacement="AgentBuilder.with_visual_adapter_plugin",
    reason="V2 visual adapter plugin 协议提供更完整 lifecycle hook",
)
def some_old_method(...): ...
```

| 函数 | 用途 |
|---|---|
| `deprecation.deprecated(since_version, removed_in=None, replacement=None, reason="")` | decorator 工厂 |
| `deprecation.is_deprecated(func)` | 判断是否标注了 `@deprecated` |
| `deprecation.get_deprecation_metadata(func)` | 获取 deprecation 元数据 dict |

#### 用户侧响应

- 调用 deprecated API → log warning 一次（每个 fn / 进程 / 默认）
- ⚠️ Experimental API 在 MINOR 删除时**不**走 deprecation 流程

---

## §15. 附录：常用 import 速查

### §15.1 完整 import 模板（拷贝即用）

```python
# 主入口（90% 用户只需要这些）
from krow_agent_sdk import AgentBuilder, Agent, BudgetSpec, BuilderConfig, StreamItem

# Plugin Protocols (6 stable)
from krow_agent_sdk import (
    ACTPlugin, ToolPlugin, GatePlugin,
    HintPlugin, EventListenerPlugin, ObservabilityPlugin,
)

# Plugin Protocols (4 experimental)
from krow_agent_sdk.experimental.protocols import (
    MCPServerPlugin, SecurityPlugin, DomainPackPlugin, VisualAdapterPlugin,
)

# Lifecycle
from krow_agent_sdk import BasePluginLifecycle, SDKContext

# 错误类
from krow_agent_sdk.errors import (
    KrowSDKError,
    MissingKrowAPIKeyError, InvalidKrowAPIKeyError,
    KrowAPIKeyInvalidError, KrowQuotaExceededError, LLMProviderError,
    MissingProjectRootError, ProjectRootNotWritableError,
    PluginSignatureMismatchError, InvalidPluginIDError,
    DuplicatePluginIDError, PluginLoadError,
)

# 流式
from krow_agent_sdk import EventBusReader, StreamItem, StreamItemKind

# Replay
from krow_agent_sdk.replay import (
    LLMReplayStore, ReplayRecord, RecordReplayWrapper,
    LLMReplayError, LLMReplayMiss,
    compute_request_hash, wrap_provider_manager_with_replay,
)

# LLM helper（plugin 内调 LLM 用）
from krow_agent_sdk.llm import (
    ChatMessage, LLMSourceModule, llm_source_context, make_plugin_source_module,
)

# Visual
from krow_agent_sdk.visual import (
    VisualAdapter, ElementEntry, SceneConfig,
    SemanticRole, SemanticMap, VisualGroundingResult,
    visual_inspect, register_default_pptx_adapter,
)

# Diagnostics
from krow_agent_sdk.diagnostics import (
    dump_state, get_plugin_snapshot, get_tool_snapshot,
    get_hint_snapshot, get_observability_snapshot,
    get_event_subscription_snapshot, get_overlay_snapshot,
)

# Data facade
from krow_agent_sdk.data import (
    get_state_snapshot, get_global_ontology_snapshot,
    query_global_ontology, get_memory_stats, query_memories,
)

# Auth
from krow_agent_sdk.auth import (
    validate_api_key_format, read_api_key_from_env, read_project_root_from_env,
    ENV_KROW_API_KEY, ENV_KROW_PROJECT_ROOT,
)

# Hints
from krow_agent_sdk.hints import HintRegistry, get_hint_registry

# Entry points 自动发现
from krow_agent_sdk.entry_points import (
    GROUP_ACT, GROUP_TOOL, GROUP_GATE, GROUP_HINT,
    GROUP_EVENT_LISTENER, GROUP_OBSERVABILITY, GROUP_DOMAIN_PACK, GROUP_VISUAL_ADAPTER,
    discover_plugins_for_protocol, is_plugin_entry_points_enabled,
)

# Extended.md supplement（DomainPackPlugin 高级用法）
from krow_agent_sdk.extended_md_supplement_registry import (
    register_extended_md_supplement, unregister_extended_md_supplement,
    get_supplements_for, merge_supplements_into_extended_md,
)

# Deprecation
from krow_agent_sdk.deprecation import (
    deprecated, is_deprecated, get_deprecation_metadata,
)

# Telemetry (⚠️ experimental)
from krow_agent_sdk.telemetry import (
    is_telemetry_enabled, get_telemetry_client,
)

# Test SDK（仅 monorepo dev 模式可用）
# from krow_test_sdk import HeadlessAgentHarness, AgentRunResult, LLMReplayStore
```

### §15.2 typical 用例 → 章节速查

| 想做什么 | 看哪节 |
|---|---|
| 5 分钟跑通 hello world | [§1.2](#12-最小可运行例) + [`quickstart.md`](./quickstart.md) |
| 链式构造 Agent | [§2](#2-agentbuilder--构造器链式-api) |
| 选择 LLM 模型 | [§2.3](#23-llm-模型选择-api6-类) |
| 加新工具给 LLM 用 | [§5.2 ToolPlugin](#52-toolplugin--加新工具-p2) + [`advanced-development-guide.md` §3](./advanced-development-guide.md) |
| 加领域 ACT（research / industrial / 等） | [§5.1 ACTPlugin](#51-actplugin--加新-act-p1) |
| 流式收事件 | [§3.2 run_stream](#32-agentrun_stream--流式执行) + [§6.3 topic 速查](#63-稳定-topic-速查) |
| 写测试不调真实 LLM | [§7 Replay 框架](#7-llm-recordreplay-框架) + [§2.9 with_replay_store](#29-llm-recordreplay-接入) |
| 添加领域视觉适配器（CAD / 工程图等） | [§2.6](#26-visual-adapter-注入3-路径) + [§5.10 VisualAdapterPlugin](#510-visualadapterplugin--视觉适配器-p10--experimental) |
| 推 metric 到外部 Datadog / Grafana | [§5.6 ObservabilityPlugin](#56-observabilityplugin--metricstraces-转发-p6) |
| Debug：plugin 没生效？ | [§9.1 dump_state](#91-diagnostics--状态导出) |
| 错误处理 / fail-loud 边界 | [§12 Errors](#12-errors--错误层与黄金模板) |

---

> **本手册结束。**
> 任何 API 文档错误 / 不清晰 / 缺失，请在 [GitHub Issues](https://github.com/aullik5/krow-sdk-docs/issues) 反馈。
> 进阶设计原则与最佳实践见 [`advanced-development-guide.md`](./advanced-development-guide.md)。
