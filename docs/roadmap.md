# Krow Agent SDK Roadmap

> **维护者**：每完成一个 Wave / Phase 后更新本文件（不要把 roadmap 内容回写到 AGENTS.md，本文件是 roadmap SSOT）。
> **决策原则**：Step 1 完成后才进 Step 2；Step 2 落地后才考虑 Step 3+。
>
> **元规则提示**：roadmap 内容**只放本文件**，AGENTS.md 只放 1 行指针（避免 god file 反弹）。

---

## Step 1 ✅ 完成（2026-05-13）

外部团队 monorepo 接入。`pip install -e ".[sdk]"` + 8 类 plugin protocol + read-only data facade + record/replay 一等公民。

| Wave / PR | 关键能力 | 状态 |
|---|---|---|
| Wave 1（mvp_critical S1.x） | `AgentBuilder`、`Agent`、3 stable + 3 mvp 共 6 类 Plugin Protocol、SDKContext、events 只读 facade | ✅ |
| Wave 2（stable S2.x） | `with_*_from_entry_points()` 自动发现（feature flag opt-in）、HintRegistry、deprecation 框架 | ✅ |
| Wave 3（experimental） | `MCPServerPlugin` / `SecurityPlugin` / `DomainPackPlugin` 协议骨架 | ✅ |
| Wave 4（krow_test_sdk） | `HeadlessAgentHarness` / `AgentRunResult` 测试基础设施公开 | ✅ |
| PR A1-A4（Phase A 完善） | API key 认证、read-only data facade、ACT extended.md 增量、ReACT budget bugfix | ✅ |
| PR B1-B5（Phase B 完善） | entry_points 自动发现、HTTP gateway facade、reverse telemetry opt-in、HintRegistry | ✅ |
| PR C1-C3（Phase C 完善） | telemetry opt-in、deprecation 装饰器、`build()` 自动注入 + cloud-model fallback | ✅ |
| **PR #212-#214（Phase C3 收尾）** | **quickstart + smoke 验证、`MCPServerPlugin` 形态 B 真接 ToolManager、`replay` SDK 一等公民** | ✅ |
| **PR #215（P2a/P2b）** | **headless 镜像默认装 SDK + 构建期 SDK smoke、Roadmap 入仓** | ✅ |

---

## Step 2 ✅ M1-M8 落地 / 🚧 M9 上线工作中 / ✅ 商业发布起步（2026-05-15）

**工程层面**：
- M1-M4（PyPI 子包 + OIDC publish）✅ 完成
- M5-M7（dual-build + nightly + SBOM + headless-bridge）✅ 完成
- M8（Cython spike + sdk-runtime build workflow）✅ 完成
- **M9（sdk-runtime 私有发布 + `krow-sdk-install` bridge）设计 ✅ / 上线 🚧**：
  - 设计文档齐备（`runtime-install-bridge-design.md` + `source-protection-design.md`）
  - **关键阻塞**：原设计走 GitHub Packages PyPI 端点，但 GH Packages **已停止支持 PyPI 类型**（2024 起 npm/Docker/Maven/NuGet/RubyGems 仍支持，PyPI 已 deprecated）→ v1 设计基础不可行
  - **决策（2026-05-15）**：**v2 reverse proxy 模式提前到 v1 启用**（Krow Cloud 直接代理 wheel 字节流，客户感知不到外部 registry，最优雅但 cloud team 工作量 ~2 周）
  - `packages/krow-sdk-install/` CLI 子包待建
- M10-M11（watermark + telemetry）✅ 完成
- Tier 1-5 死代码清理（excalidraw / ghost ACT / solution_*/he/local_refiner）✅ 完成

**商业发布层面**：
- ✅ `krow-agent-sdk==0.8.12.4` 已正式发布 PyPI 主站（2026-05-15）
- 🚧 EULA v1.1 仍为 DRAFT（good-faith disclosure）；等真律师签字 → v1.x EFFECTIVE → 移除 disclosure
- 🚧 M9 runtime 上线工作（v2 reverse proxy 实施）

**外部开发者实际可用度**：
- ✅ `pip install krow-agent-sdk` + 写 plugin + record/replay 单元测试
- ❌ `agent.run()` 真实跑（等 M9 上线）

外部团队 PyPI 接入：`pip install krow-agent-sdk` 独立子包，不依赖 krow monorepo。

| 待办 | 关键节点 | 优先级 |
|---|---|---|
| `packages/krow-agent-sdk/` 子包 + 独立 `pyproject.toml` | symlink 同步、收敛 ~60→~13 主依赖 + dual-build CI + nightly + SBOM + OIDC publish | ✅ P0 全部完成：设计文档 PR #232；**M1 ✅ PR #234** / **M2 ✅ PR #235** / **M3 ✅ PR #236** / **M4 ✅ PR #237**（`sdk-publish.yml` OIDC trusted publisher + `publish-testpypi → publish-pypi` 顺序 + `pypi` environment manual approval gate；`scripts/sdk_publish_dry_run.py` 6-step 本地预演；`docs/sdk/pypi-publish-setup.md` 完整 setup 文档）。<br/>**至此 Step 2 P0 全部完成**；首次发布只需 release engineer 按 setup 文档配 OIDC + GitHub environments，再 `git tag sdk-v0.8.12 && git push` 即可 |
| ~~独立 `release-sdk-pypi.yml`~~ | ~~独立 `sdk-v*` tag + OIDC trusted publisher~~ | ✅ M4 PR #237 已用 `.github/workflows/sdk-publish.yml` 落地（命名变更：`release-sdk-pypi` → `sdk-publish`，与 `sdk-build.yml` 命名对齐）；本行原计划与 M4 重复，统一记入 M4 |
| ~~BYO LLM provider（OpenAI / vLLM / Ollama）~~ | ~~让外部团队接非 Krow Cloud 的 LLM~~ | ❌ **已决策不做**（2026-05-12 用户辩论结论：Krow Cloud API key 是 SDK 唯一 LLM 入口，"只能用不能换"；走 Krow Cloud 自带 auth + 计费 + 多模型路由，外部团队无须自管 LLM 凭证）；外部团队若有特殊 LLM 接入需求 → 走 plugin 自实 `LLMProviderPlugin`（设计文档 §3.3 留有钩子，但**不**纳入 SDK 默认能力） |
| ~~`with_default_model("xxx")` API~~ | ~~让外部团队明确指定模型~~ | ✅ Step 2 P1 PR #224 落地；🔁 chore/sdk-model-selection-api（2026-05-15）取代为 6 个 `with_<category>_model`（chat / reasoning / vision / image_gen / image_edit / text_encoder），与 `ModelCategory` enum 6 类对齐；Service API `ExecuteTaskRequest.models` dict 镜像；✅ **chore/btq-model-overrides-2026-05-15 完成 headless 接通**（`BackgroundAgentTaskQueue._scoped_model_overrides` contextmanager + finally restore 防跨任务污染单例 ai_mgr / lpm；同时修复 SDK builder / api_gateway desktop path / BtQ helper 三处 P0 字段名 bug：`cfg.model_name` → `cfg.model`，参 `ProviderConfig` dataclass `modules/ai/providers.py:417-434`） |
| ~~`AgentBuilder.with_replay_store()` API~~ | ~~把 replay 接入主路径，不必手动 wrap~~ | ✅ Step 2 P2 PR #227 落地 |
| ~~MCPServerPlugin 形态 C（远程 MCP transport 自动连接）~~ | ~~Wave 3 骨架升级~~ | ✅ Step 2 P1 PR #230 落地（form-C = form-B 远程语义子集 + auto close/aclose） |
| domain pack 升级（ontology editor + custom entity 抽取） | 科研 / 工业领域适配 | P2 — 设计文档 `docs/sdk/pypi-subpackage-design.md` 之外的另一份 design doc 待沉淀；外部团队反馈优先度决定开工时机 |
| ~~visual_inspect plugin 完整公开~~ | ~~外部团队视觉 QA 用（CAD 图 / 工业图纸 / 报告页布局合规性等）~~ | ✅ **PR #239 落地（2026-05-13）**：`from krow_agent_sdk.visual import VisualAdapter` namespace（11 symbol re-export）+ `from krow_agent_sdk.experimental.protocols import VisualAdapterPlugin`（experimental P10）+ `AgentBuilder.with_visual_adapter(ext, cls)` / `with_visual_adapter_plugin(plugin)` / `with_visual_adapter_plugins_from_entry_points()` 三条链式 API + entry_points GROUP `krow.visual_adapter`（ALL_GROUPS 9→10）+ BuilderConfig 接收 visual fields；DomainPackPlugin.get_visual_adapters() 旧路径不破坏（OCP）；15 单测 + 364 SDK 全套 unit pass |
| ~~`Agent.run_stream()` 流式 API~~ | ~~让外部团队做交互式 UI / 实时进度条 / token 流式渲染~~ | ✅ **chore/sdk-run-stream-api-2026-05-15 完成**：`from krow_agent_sdk import StreamItem`（dataclass envelope，3 种 kind：`event` / `result` / `error`，frozen + fail-loud 字段配对校验）+ `Agent.run_stream(user_input, *, topics, idle_timeout=600.0, queue_max_size=1000, stop_event=None) -> Iterator[StreamItem]` 同步生成器；底层完全复用 `AgentV3.run` 主路径 + `EventBusReader.subscribe`，不引入新执行分支（OCP）；用户 break → finally 自动 unsubscribe + 自动 set owned stop_event 让 agent 协作 stop；**关键设计**：用 `terminated_event` 带外信号 + 短轮询主循环（不依赖 queue sentinel），避免 queue 满时 sentinel 被 drop 导致死锁；20 单测覆盖 happy path / 异常透传 / break 取消 / idle_timeout / queue 满 drop / 顺序复用 |

---

## Step 3+ 🌅 长期（计划 2027+）

| 方向 | 备注 |
|---|---|
| 多 plugin 之间 IPC / 协作协议 | 让一个 plugin 调用另一个 plugin 暴露的能力 |
| plugin marketplace / registry | 集中索引外部团队 plugin |
| Wasm / Pyodide 沙盒 | 高安全级别的 plugin 运行时隔离 |
| 多语言 SDK（TypeScript / Rust） | 让前端 / Rust 工程师也能写 plugin |

---

## 当前阻塞 / 待决策

- ✅ Step 1 已完整收尾
- ✅ Step 2 P0（PyPI 子包独立化）M1-M4 全部完成（2026-05-13）
- ✅ Step 2 P0 TestPyPI 首发（2026-05-15）：[`krow-agent-sdk==0.8.12`](https://test.pypi.org/project/krow-agent-sdk/0.8.12/) OIDC trusted publisher 验证通过 + 干净 venv smoke install 通过；artifact 路径 hotfix 见 PR #317
- ✅ Step 2 P1（`with_default_model`→6 个 `with_<cat>_model`（chore/sdk-model-selection-api 2026-05-15）/ `with_replay_store` / `MCPServerPlugin` form-C）全部完成
- ✅ Step 2 P1 `Agent.run_stream()` 流式 API（PR #316，2026-05-15）：`StreamItem` envelope + 同步生成器 + 20 unit tests + CI smoke 防回归
- ✅ Step 2 P2 visual_inspect plugin 完整公开（PR #239，2026-05-13）
- ✅ Step 2 P2 EULA 模拟法务 review（chore/eula-legal-review-2026-05-15）：v1.0 → v1.1，3 P0 + 4 P1 + 5 P2 修订 + 6 条新增标准条款（§13-18）+ Appendix C 三层 consent 机制；详 `eula-mock-legal-review-feedback.md` (internal)
- 🚧 Step 2 P2 EULA 后续阻塞：(a) 商务决策 3 项（governing law / liability floor / consent 机制 mandatory level）；(b) 持证律师签字（建议中国大陆 + 香港双 review，~14 天）；(c) Cloud 端 + CLI 端同意机制实施
- 🚧 Step 2 P2 剩余：`domain pack ontology editor + custom entity 抽取`；视外部团队反馈优先度决定开工时机
- ❌ Step 2 BYO LLM provider 已决策不做（见上表注释）

**正式 PyPI 首发阻塞**：必须等 EULA EFFECTIVE（v1.x → v1.x+1，含真律师签字），预计 **2026-06-19 (T+35)** 可达成；详 `eula-legal-review-checklist.md` (internal) §6 时间线。
