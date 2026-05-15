# Krow Agent SDK — 公开文档

> [`krow-agent-sdk`](https://pypi.org/project/krow-agent-sdk/) 是 [Krow Cloud](https://krow.cn) 提供的 Python SDK，
> 面向外部团队（科研 / 工业 / 业务）让你**用 Krow API key 写 plugin** 接入 Krow Agent IDE 的 ReACT 引擎、ACT 工具体系、Plugin Protocol、Visual QA 等能力。
>
> 本仓只放**对外公开文档**。SDK / runtime / agent 主体源码在 Krow team 私有 monorepo 内。

---

## 现状摘要（2026-05-15）

| 能力 | 状态 |
|---|---|
| `pip install krow-agent-sdk` 公开 SDK 主包 | ✅ [PyPI 0.8.12.3 已发布](https://pypi.org/project/krow-agent-sdk/) |
| 写 plugin + 用 `LLMReplayStore` record/replay 跑单元测试 | ✅ 完整可用 |
| 私有 runtime wheel `krow-agent-sdk-runtime` + `krow-sdk-install` CLI | 🚧 M9 上线工作中（详 [`roadmap.md`](./docs/roadmap.md)） |
| `agent.run()` 端到端真实跑 agent | 🚧 等 M9 完成 |
| EULA 法律生效 | 🚧 v1.1 DRAFT (good-faith disclosure)；等持证律师签字（详 [`EULA.md`](./docs/EULA.md) §0） |

---

## 文档导航

### 必读（新手 30 分钟入门）

| 文档 | 内容 |
|---|---|
| [`quickstart.md`](./docs/quickstart.md) | **5 分钟跑通**：装包 + Hello World + 5 类 plugin 范例 |
| [`external-developer-onboarding.md`](./docs/external-developer-onboarding.md) | **第 1 周指南**：周一上班 → 周五能 demo 节奏；含科研 / 工业 / 业务 3 种领域适配 |

### 核心参考

| 文档 | 内容 |
|---|---|
| [`plugin-architecture-design.md`](./docs/plugin-architecture-design.md) | **Plugin Protocol SSOT**（237 KB）：8 类 plugin（Tool / Hint / Gate / EventListener / Observability / MCPServer / DomainPack / VisualAdapter）完整签名、生命周期、entry_points 自动发现协议 |
| [`runtime-install.md`](./docs/runtime-install.md) | runtime wheel 装机指南（**M9 上线后启用**） |

### 法律 + 路线图

| 文档 | 内容 |
|---|---|
| [`EULA.md`](./docs/EULA.md) | 最终用户许可协议（v1.1 DRAFT，含 good-faith 披露） |
| [`roadmap.md`](./docs/roadmap.md) | SDK 进度 SSOT（Step 1-3 / Wave / M1-M11 milestone） |

---

## 5 分钟跑通

```bash
pip install krow-agent-sdk
```

```python
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key("sk-user-xxxx")        # 到 https://krow.cn/dashboard 拿
    .with_project_root("./my_workspace")
    .build()
)

result = agent.run("写一个 hello world Python 文件到 ./my_workspace/")
print(result.success, result.final_output)
agent.shutdown()
```

> ⚠️ **`agent.run()` 当前依赖 M9 runtime wheel**（上线工作中）；现阶段建议用
> `LLMReplayStore` 走 record/replay 跑 plugin 单元测试，详 [`quickstart.md`](./docs/quickstart.md) §6。

---

## 常见问题快查

### 这个仓和 Krow monorepo 是什么关系？

| 仓 | 用途 | 可见性 |
|---|---|---|
| **本仓 `aullik5/krow-sdk-docs`** | 公开文档站 + Issues / 反馈渠道 | ✅ Public |
| `aullik5/krow`（monorepo） | SDK / runtime / agent 主体源码 + ACT 工具 + 内部讨论 | 🔒 Private |

文档同步：本仓内的 `docs/*.md` 是从 monorepo `docs/sdk/` 同步过来的子集（仅对外文档）。

### 我能 fork 这个 repo 改文档提 PR 吗？

可以。改 `docs/` 内文档 → 提 PR；Krow team 会 review 并同步回 monorepo 主源 SSOT。

但 **PyPI 包源码**变更**不在本仓**——SDK 源码在私有 monorepo，只有 Krow team 内部可改。
外部贡献模式：通过本仓 [Issues](https://github.com/aullik5/krow-sdk-docs/issues) 提 feature request / bug report。

### 哪些设计决策没在本仓？

下列文档是**内部 design doc**，**保留在私有仓**：

- `pypi-publish-setup.md`（OIDC publish 配置）
- `pypi-subpackage-design.md`（子包结构决策）
- `source-protection-design.md`（威胁模型 + Cython 保护策略）
- `runtime-install-bridge-design.md`（bridge 内部协议）
- `eula-legal-review-checklist.md` + `eula-mock-legal-review-feedback.md`（法务 review 流程）
- `release-engineer-handbook.md`（release 操作手册）
- `cython-spike-report.md` / `watermark-telemetry-design.md`（实现细节）

如果你是 Krow team collaborator，到 monorepo `docs/sdk/` 查看完整 SSOT。

---

## 反馈 / 支持

| 渠道 | 用途 | 响应 SLA |
|---|---|---|
| [GitHub Issues](https://github.com/aullik5/krow-sdk-docs/issues) | bug report / feature request / 文档错误 | 1-3 天 |
| [GitHub Discussions](https://github.com/aullik5/krow-sdk-docs/discussions) | 用法咨询 / plugin 设计讨论 | 1-3 天 |
| `support@krow.cn` | 紧急生产问题 | 24 小时 |
| `sales@krow.cn` | 套餐升级 / 商务咨询 | 1 天 |

---

## License

[`LICENSE`](./LICENSE)（Krow Agent SDK End User License Agreement v1.1 DRAFT，含 good-faith disclosure）。

商用 / 二次分发前必读 §3 Restrictions + §6 IP + §0 disclosure。

---

> 文档版本：`krow-sdk-docs` 跟 `krow-agent-sdk==0.8.12.3` 同步发布（2026-05-15）。
> SSOT 在 [aullik5/krow](https://github.com/aullik5/krow)（私有，Krow team 内部）的 `docs/sdk/` 目录。
