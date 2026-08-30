# Krow Agent SDK Roadmap

> **维护者**：每完成一个 Wave / Phase 后更新本文件（不要把 roadmap 内容回写到 AGENTS.md，本文件是 roadmap SSOT）。
> **决策原则**：Step 1 完成后才进 Step 2；Step 2 落地后才考虑 Step 3+。
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

## Step 2 ✅ M1-M8 + M10-M11 落地 / 🚀 M9 W1-W4 实施 / ✅ 商业发布稳定迭代（2026-05-16）

**工程层面**：
- M1-M4（PyPI 子包 + OIDC publish）✅ 完成
- M5-M7（dual-build + nightly + SBOM + headless-bridge）✅ 完成
- M8（Cython spike + `sdk-runtime-build.yml` 9-wheel matrix）✅ 完成（**注**：roadmap 历史版本误标 M9 为 ✅，实际未上线，详下）
- **M9（sdk-runtime 私有发布 + `krow-sdk-install` bridge）设计 ✅ / W1+W3 SDK 侧 ✅ / W2+W4 等 Cloud team 🚧**：
  - 设计文档齐备（`runtime-install-bridge-design.md` + `source-protection-design.md` + `cloud-runtime-proxy-spec.md` v1.1 + `cloud-team-response-ack.md`）
  - **2026-05-15**：原设计走 GH Packages PyPI 已 deprecated → 决策切换到 v2 reverse proxy
  - **2026-05-16 协议锁定**：Cloud team 答复（`cloud-team-response.md`）+ SDK team 确认（`cloud-team-response-ack.md`）→ **W1 启动**
    - Storage：火山引擎 TOS（cn-shanghai，bucket `krow-sdk-runtime`，S3 兼容接口）
    - Endpoint：`api.krow.cn/sdk/runtime/pypi/{simple,files}/...`（gateway 内 `sdk_runtime.rs` 模块；非独立 Service）
    - 鉴权：Bearer + Basic（`__token__:<KROW_API_KEY>`）双支持
    - 套餐 entitlement：Free 无 / Basic 10 次/天 / Pro 50 次/天 / Premium 无限
    - SLA：M9 99.5% → M10+ 99.9%
    - 计费：M9 暂不收费（套餐内含），预留 hook
  - **W1 SDK 侧 ✅ 完成（2026-05-17，0.8.12.7）**：
    - W1 Day 1：`cloud-runtime-manifest-sample.json` + `sdk-runtime-build.yml::publish-tos` job（v1.1 schema + atomic latest.json upload）✅
    - W1 Day 2：CI lint 守门（`scripts/lint_subpackage_invariants.py` 19 项 含 v2 reverse-proxy 关键词）✅
    - **W1 Day 3：测试 wheel fixture（`scripts/sdk_runtime_make_test_wheels.py` 9 wheel matrix + manifest/latest 生成 + 12 单测）+ workflow `fast_mode` dispatch（dry-run < 5 min vs cython 30 min；publish-tos fast-mode 跳真实 PUT）✅**
  - **W2（2026-05-23 周）等 Cloud team 🚧**：bucket+IAM+staging gateway → SDK 拿到 staging endpoint 后跑 `--base-url https://api-staging.krow.cn` 联调
  - **W3 SDK 侧 ✅ 完成（2026-05-17 提前到 W1 一并交付，0.8.12.7）**：
    - **W3 Day 1 (7) `packages/krow-sdk-install/` CLI 子包**：src layout（`__init__/cli/client/platform/errors/__main__`）+ console_scripts entry_point + 21 单测（PEP 503 parser + sha256 + 鉴权黄金模板 + tag 检测 + select wheel）+ `sdk-build.yml::install-cli-build/smoke`（3 OS × py3.11/3.13 = 6 matrix）✅
    - **W3 Day 1 (8) Pilot onboarding 文档**：私有 `docs/sdk/pilot-onboarding.md`（W2-W3 SDK team 自联调 SOP + P0 quick-look + 失败回退）+ 公开 `runtime-install.md` §8 Public Beta 时间表 ✅
    - **2026-05-17 决策更新**：跳过封闭 Pilot 阶段（原计划 5-10 名审核入选客户），W4 staging 联调通过即直接 Public Beta（任何 `KROW_API_KEY` 即可装），运营成本更低 + 不阻塞工程节奏 ✅
  - **W4（2026-05-30 周）真实 LLM E2E + 联调 🚧**：
    - **W4 预期结果卡 ✅**：`tests/sdk/_expected_results/w1_w4_runtime_install_journey.md`（Stage 1 unit mock 反向代理 + Stage 2 nightly real LLM 多维断言）
    - **W4 测试代码 ✅**：`tests/sdk/test_journey_runtime_install_real_llm.py`（9 测试：mock 反向代理全链路 happy + 401/429/sha256mismatch/network/platform_unsupported 错误路径 + nightly real_llm + CLI argparse）+ nightly workflow 自动收 ✅
    - **W4 真实联调 🚧**：等 Cloud team prod gateway 上线 → SDK team owner 三平台自联调通过 → 直接 Public Beta（公开任何 KROW_API_KEY 用户）
- M10（watermark）✅ 完成
- M11（telemetry）✅ 完成
- Tier 1-5 死代码清理 ✅ 完成

**商业发布层面**：
- ✅ `krow-agent-sdk==0.8.12.3` 已发 PyPI 主站（2026-05-15）
- ✅ `0.8.12.4` 已发（2026-05-15）：README + LICENSE 内私有仓链接修订
- ✅ `0.8.12.5` 已发（2026-05-16）：`pyproject.toml [project.urls]` 修指公开文档仓 + 公开文档完善（advanced-development-guide / api-reference 上线）
- ✅ `0.8.12.6` 已发（2026-05-16）：公开文档全审查 + 30 个 doc-drift 单测 + 3 个真实 LLM E2E (`with_<cat>_model` + `run_stream`) + lint_subpackage_invariants 19 项 v2 reverse-proxy 关键词守门
- 🚀 `0.8.12.7` 准备发（2026-05-17）：M9 W1-W4 SDK 侧实施完整交付（W1 测试 wheel + W3 install-cli 子包 + Pilot onboarding + W4 真实 LLM E2E 预期结果卡 + 9 测试 nightly 收）
- ✅ `0.8.12.10` 已发（2026-05-18）：**W3 W4 收尾大版本**（详 §"v0.8.12.10 交付清单" 一节）
  - **Cookbook v3 三 demo 落地**（PR #365 / #367 / #369 + recovery PR #377）：financial-analyst（财经研究 / 横向年报对比）+ literature-reviewer（学术研究 / 多 PDF 文献综述）+ contract-auditor（行政办公 / 合同审阅 + 强阻断 Gate + OpenTelemetry），覆盖 SDK 全部 6 类 production plugin
  - **Cookbook 真实 LLM E2E framework**（PR #378）：`_journey_e2e_helpers.py`（synthesize_*_pdf / run_journey / assert_journey）+ 5 cookbook journey runner + 多维断言 YAML 契约（exit_code / max_walltime_s / required_artifacts / required_sections_in / forbidden_keywords_in / min_artifact_bytes）
  - **`pk-pilot-` key 双前缀支持**（PR #378）：`API_KEY_PATTERN` 正则升级 + 新增 4 个单测 + `InvalidKrowAPIKeyError` 文案对齐
  - **W3 cloud-handoff 落地**（PR #372）：HK transit bucket（cn-hk-staging）+ CRR 同步 + multipart upload + 9 wheel 并行上传（`xargs -P 9`），TOS upload 路径稳定
  - **PPTX Cython hotfix**（PR #376）：`pptx_studio/tools.py` `local logging` 引用前赋值 → 替换为 top-level `logger`（main 上预存 Cython 编译错误，hotfix 解锁 sdk-runtime build）
  - **Tier 7 wheel slim**（PR #375）：`scripts/audit_sdk_runtime_wheel.py`（HARD/SOFT 双闭包 BFS 扫描）+ `WHEEL_EXCLUDE_LIST` 排除 9 dirs / 72 .py（extensions/, update/, ui/, chat/, monitoring/, graphql/, grpc/ 用户确认 + 3 dirs 由扫描判定 unreachable；formula/ 与 mcp/ 保留）+ Linux strip 后实测：438 MB → 76 MB（**5.7× 缩减**）；macOS 123 MB → 110 MB（1.1× 缩减）；Windows 53 MB（已默认无 debug symbols）
  - **docs 同步**（PR #379）：cookbook v3 / cookbook E2E results / Tier 7 wheel slim 进 SDK 文档主索引；`README.md` v1.2 + 新增 `cookbook-e2e-results.md`
- 🚧 EULA v1.1 仍为 DRAFT（good-faith disclosure）；等真律师签字 → v1.x EFFECTIVE → 移除 disclosure
- 🚀 M9 runtime 上线工作（v2 reverse proxy 4 周 W1-W4 实施中 · 2026-05-16 协议锁定）

**外部开发者实际可用度**：
- ✅ `pip install krow-agent-sdk` + 写 plugin + record/replay 单元测试
- 🚧 `agent.run()` 真实跑（等 M9 W4 上线，预计 2026-06）

**公开文档仓**：[aullik5/krow-sdk-docs](https://github.com/aullik5/krow-sdk-docs)（2026-05-15 上线，**8 份**对外文档 + cookbook 全目录同步自 monorepo `docs/sdk/`：quickstart / external-developer-onboarding / runtime-install / headless-deployment / advanced-development-guide / api-reference / roadmap / EULA）

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

| 决策脑（元认知）对外开放 | 让垂直场景团队把"离交付还差多少"接进元认知工作站，并在系统察觉卡点时**动手** | ✅ **2026-07~08 分批落地**：观测/唤醒/结算三注册表 + `register_domain_axis` + `publish_signal_envelope`（零注册感知）+ `get_registry_snapshot`（含 `axes` / `magnitude_clamped` 自查）+ 执行面 `register_control_reflex` / `register_step_actuator` / `register_reflex_decision`；结案读数 `metacog_decision_stats`、`cognitive.*` 事件族。可跑范例 `examples/cookbook/litsci-metacog/`（零 LLM）。**能力边界诚实登记**：可见 ≠ 能止损 ≠ 可修复，第三档（产物真的变好）内建通用面**做不到**，见 [advanced-development-guide §10.10](./advanced-development-guide.md)。文档 [api-reference §9.6 / §9.7](./api-reference.md#96-metacognition--配置决策脑三注册表) + 进阶指南 §10 |
| 外部 `SKILL.md` 装载 | 让**不写 Python** 的用户也能扩展 agent | ✅ **2026-08-23 落地**：`AgentBuilder.with_skill_directory(path)` / `get_skill_reports()` / `agent.skills`。**无 env 开关** —— 默认 OFF 的形式是"你没写那行调用"（与 `with_act_plugin` 同 idiom）。**不新增 Protocol** —— `SKILL.md` 的 frontmatter 被翻译成 `__act__.yaml` 后合成 `ACTPlugin`，走既有装载链；产物物化到 `.krow/skills/<name>/` 可审计。改名 / 未命中工具 / 注入过滤命中三件事全部进 `SkillLoadReport`。边界：不执行 skill 内脚本、不做隐式目录发现、不回写用户目录。用法见 [api-reference §2.7.1](./api-reference.md#271-外部-skillmd-装载v091) + [advanced-development-guide §4.11](./advanced-development-guide.md) |

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
- ✅ Step 2 P2 EULA 模拟法务 review（chore/eula-legal-review-2026-05-15）：v1.0 → v1.1，3 P0 + 4 P1 + 5 P2 修订 + 6 条新增标准条款（§13-18）+ Appendix C 三层 consent 机制；详 [`eula-mock-legal-review-feedback.md`](./eula-mock-legal-review-feedback.md)
- 🚧 Step 2 P2 EULA 后续阻塞：(a) 商务决策 3 项（governing law / liability floor / consent 机制 mandatory level）；(b) 持证律师签字（建议中国大陆 + 香港双 review，~14 天）；(c) Cloud 端 + CLI 端同意机制实施
- 🚧 Step 2 P2 剩余：`domain pack ontology editor + custom entity 抽取`；视外部团队反馈优先度决定开工时机
- ❌ Step 2 BYO LLM provider 已决策不做（见上表注释）

**当前阻塞 / 后续节点**：

- ✅ PyPI 主站已稳定迭代（`0.8.12.10` 已发）；EULA 仍处 v1.1 DRAFT（good-faith disclosure）
- 🚧 EULA v1.x EFFECTIVE：等真律师签字（建议中国大陆 + 香港双 review，~14 天），预计 **2026-06-19 (T+35)** 可达成；签字后下版 hotfix 发布移除 disclosure
- 🚀 M9 runtime W1-W4 上线节奏：W1 = 2026-05-17 周 / W4 = 2026-06；2026-05-17 决策：跳过封闭 Pilot，直接 Public Beta（任何 KROW_API_KEY 即可装）
- ✅ 公开文档完整：quickstart / external-developer-onboarding / runtime-install / advanced-development-guide / api-reference / roadmap / EULA 7 份对外文档同步自 monorepo
- 🚧 Cookbook 真实 LLM E2E real-run blocked：staging gateway LLM 端 **未部署**（pk-pilot- key 走 staging 时 `AuthExpiredError`），需 Cloud team 部署 staging gateway 的 LLM proxy 后才能跑真实 LLM；framework + skip 行为已落地（local 上跑需 prod sk- key + `KROW_REAL_LLM_E2E=1`）
- ✅ **2026-05-19 W4 self-side followups（PR #384）已合**：`AgentBuilder.with_base_url(url)` API + `tests/sdk/test_cloud_runtime_proxy_acceptance.py` §8 F1-F13 骨架（13+1 case，等 prod gateway 一键跑）+ `sdk-cookbook-smoke.yml` matrix 扩 v3 三 demo + `sdk-install-cli-publish.yml` 独立发布 workflow（待 release engineer 配 OIDC trusted publisher 后即可发 PyPI）

---

## v0.8.12.10 交付清单（2026-05-18）

> 详细变更摘要见 `config/version.py` `VERSION_HOTFIX = 10` 注释段。

| # | 子任务 | PR | 状态 |
|---|---|---|---|
| 1 | Cookbook v3 PR-A（financial-analyst）| #365 | ✅ |
| 2 | Cookbook v3 PR-B（literature-reviewer）| #367 | ✅ |
| 3 | Cookbook v3 PR-C（contract-auditor）| #369 | ✅ |
| 4 | Cookbook v3 #367 #369 squash race recovery（cherry-pick）| #377 | ✅ |
| 5 | W3 cloud-handoff（HK transit + CRR + multipart + parallel upload）| #372 | ✅ |
| 6 | PPTX Cython hotfix（main 上预存编译错误）| #376 | ✅ |
| 7 | Cookbook E2E framework + pk-pilot- key 支持 | #378 | ✅ |
| 8 | docs/sdk: cookbook v3 + E2E + Tier 7 同步 | #379 | ✅ |
| 9 | sdk-runtime Tier 7 wheel slim + version 0.8.12.10 | #375 | ✅ |
| 10 | docs/sdk v0.8.12.10 changelog + roadmap 更新 + GitHub release | #381 | ✅ |
| 11 | v0.8.12.10 readiness 诚实盘点 + W4 Cloud team 需求文档（C1-C8） | #382 | ✅ |
| 12 | W4 self-side followups — cookbook smoke v3 + with_base_url + acceptance skeleton + install-cli publish | #384 | ✅ |

**Tier 7 wheel slim 实测（run 26056951348, 9 platforms, strip 后）**：

| platform | strip 前 | strip 后 | reduction |
|---|---|---|---|
| ubuntu-3.11/3.12/3.13 | 438 / 421 / 419 MB | **76 / 71 / 71 MB** | **-82.5% ~ -83.0%** |
| macos-3.11/3.12/3.13 | 123 / 122 / 121 MB | **111 / 111 / 110 MB** | **-9% ~ -10%** |
| windows-3.11/3.12/3.13 | 53 / 52 / 52 MB | 53 / 52 / 52 MB | 0%（已默认无 debug symbols）|
