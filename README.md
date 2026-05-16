# Krow Agent SDK — 公开文档

> [`krow-agent-sdk`](https://pypi.org/project/krow-agent-sdk/) 是 [Krow Cloud](https://krow.cn) 提供的 Python SDK，
> 面向外部团队（科研 / 工业 / 业务）让你**用 Krow API key 写 plugin** 接入 Krow Agent IDE 的 ReACT 引擎、ACT 工具体系、Plugin Protocol、Visual QA 等能力。

---

## 现状摘要（2026-05-16）

| 能力 | 状态 |
|---|---|
| `pip install krow-agent-sdk` | ✅ [PyPI 0.8.12.4 已发布](https://pypi.org/project/krow-agent-sdk/) |
| 写 plugin + 用 `LLMReplayStore` record/replay 跑单元测试 | ✅ 完整可用 |
| 私有 runtime wheel + Krow Cloud reverse proxy | 🚧 v1.1 设计完成，cloud team 实施中（详 [`roadmap.md`](./docs/roadmap.md)） |
| `agent.run()` 端到端真实跑 agent | 🚧 等 runtime 上线 |
| EULA 法律生效 | 🚧 v1.1 DRAFT (good-faith disclosure)；等持证律师签字（详 [`EULA.md`](./docs/EULA.md) §0） |

---

## 文档导航

### 必读（新手入门）

| 文档 | 内容 |
|---|---|
| [`quickstart.md`](./docs/quickstart.md) | **5 分钟跑通**：装包 + Hello World + 5 类 plugin 范例 |
| [`external-developer-onboarding.md`](./docs/external-developer-onboarding.md) | **第 1 周指南**：周一上班 → 周五能 demo 节奏；含科研 / 工业 / 业务 3 种领域适配 |

### 进阶（写真实业务 plugin）

| 文档 | 内容 |
|---|---|
| [`advanced-development-guide.md`](./docs/advanced-development-guide.md) | **进阶最佳实践**：TURBO 哲学 + Plugin 设计原则 + 工具设计哲学 + ACT 编写最佳实践 + 基础设施速查 + 测试方法论 |
| [`runtime-install.md`](./docs/runtime-install.md) | runtime wheel 装机指南（**runtime 上线后启用**） |

### 法律 + 路线图

| 文档 | 内容 |
|---|---|
| [`EULA.md`](./docs/EULA.md) | 最终用户许可协议（v1.1 DRAFT，含 good-faith 披露） |
| [`roadmap.md`](./docs/roadmap.md) | SDK 进度 + Step 1-3 各 milestone |

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

> ⚠️ **`agent.run()` 当前依赖 runtime wheel**（cloud team 实施中）；现阶段建议用
> `LLMReplayStore` 走 record/replay 跑 plugin 单元测试，详 [`quickstart.md`](./docs/quickstart.md) §6。

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

> 文档版本：`krow-sdk-docs` 跟 `krow-agent-sdk==0.8.12.4` 同步发布。
