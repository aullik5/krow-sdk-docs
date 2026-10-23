# Krow Agent SDK — 公开文档

> [`krow-agent-sdk`](https://pypi.org/project/krow-agent-sdk/) 是 [Krow Cloud](https://krow.cn) 提供的 Python SDK，
> 面向外部团队（科研 / 工业 / 业务）让你**用 Krow API key 写 plugin** 接入 Krow Agent 的执行引擎、ACT 工具体系、SDK Plugin Protocol、Visual QA 等能力。

---

## 现状摘要（2026-10-23）

| 能力 | 状态 |
|---|---|
| `pip install krow-agent-sdk` | ✅ [PyPI 0.9.5.27 已发布](https://pypi.org/project/krow-agent-sdk/) |
| 写 plugin + 用 `LLMReplayStore` record/replay 跑单元测试 | ✅ 完整可用 |
| `agent.run()` 端到端真实跑 agent | ✅ `pip install krow-sdk-install && krow-sdk-install --api-key $KROW_API_KEY` 装 runtime 后即可（详 [`runtime-install.md`](./docs/runtime-install.md)） |
| **运行模式** | ✅ 0.9.5 起默认 **klik**（一条对话、一个决策者；模型用 shell + `krow <子命令>` 组合能力）。turbo 仅作回退模式、平台计划退役（治理决定，非代码现状），本仓文档不再提供 turbo 用法（详 [`quickstart.md`](./docs/quickstart.md) §0.1） |
| Krowwork 市场插件包（`plugin.json`）开发规范 | ✅ 已公开（详 [`plugin-marketplace-guide.md`](./docs/plugin-marketplace-guide.md)）；**生产提交 / 审核 / 分发安装三段：规划 / 实验·以平台公告为准** |
| EULA 法律生效 | 🚧 v1.1 DRAFT (good-faith disclosure)；等持证律师签字（详 [`EULA.md`](./docs/EULA.md) §0） |

---

## 先分清两个名字

| 名字 | 是什么 | 在哪读 |
|---|---|---|
| **SDK Plugin Protocol** | 10 类 Python 协议类（ACT / Tool / Hint / Gate / EventListener / Observability / MCPServer / Security / DomainPack / VisualAdapter），通过 `AgentBuilder.with_*_plugin(...)` 装进**你自己宿主的 agent** | `quickstart.md` / `api-reference.md` §5 / `advanced-development-guide.md` / `examples/cookbook/` |
| **Krowwork 市场插件包（`plugin.json`）** | 打成 `tar.gz` 上架到 Krowwork 插件市场、由主人装给**平台组员**的能力包（技能 `SKILL.md` + 纯 Python 工具包 + `mcp.json` 连接） | `plugin-marketplace-guide.md` |

两者不是同一套协议，不能互相替代。

---

## 文档导航

### 必读（新手入门）

| 文档 | 内容 |
|---|---|
| [`quickstart.md`](./docs/quickstart.md) | **5 分钟跑通**：装包 + Hello World + 5 类 plugin 范例；§0.1 = 两个名字的区别 + 默认 klik 运行模式 |
| [`external-developer-onboarding.md`](./docs/external-developer-onboarding.md) | **第 1 周指南**：周一上班 → 周五能 demo 节奏；含科研 / 工业 / 业务 3 种领域适配 |

### 进阶（写真实业务 plugin · SDK Plugin Protocol）

| 文档 | 内容 |
|---|---|
| [`api-reference.md`](./docs/api-reference.md) | **完整 API 手册**：`AgentBuilder` 全部链式方法（§2.4.4 = 运行模式 `with_run_mode` / `KROW_RUN_MODE`）/ `Agent.run` + `run_stream` / 10 个 Plugin Protocols / `LLMReplayStore` / `EventBusReader` / 错误类全表 / 环境变量速查 |
| [`advanced-development-guide.md`](./docs/advanced-development-guide.md) | **进阶最佳实践**：klik 继承原则（§1.10 = klik 新增总则 + plugin 四种形态）+ Plugin 设计原则 + 工具设计哲学 + ACT 编写最佳实践 + 基础设施速查 + 测试方法论 |
| [`runtime-install.md`](./docs/runtime-install.md) | runtime wheel 装机指南（`krow-sdk-install`） |
| [`headless-deployment.md`](./docs/headless-deployment.md) | 容器 / 服务端无桌面部署（Dockerfile 模板、`KROW_DATA_DIR` / `KROW_RUN_MODE`、K8s 实践、故障排查） |
| [`examples/cookbook/`](./examples/cookbook/) | 12 个端到端可 fork 的 demo（索引见 [`examples/cookbook/README.md`](./examples/cookbook/README.md)） |

### Krowwork 市场插件开发与上架（`plugin.json`）

| 文档 | 内容 |
|---|---|
| [`plugin-marketplace-guide.md`](./docs/plugin-marketplace-guide.md) | 插件包格式 `krow-plugin/1`、`plugin.json` 字段、技能 / 工具 / 连接三类组件规范、自动检查规则、本地自测（`krow tool list/help/run`）。**第 5–6 节的提交 / 审核 / 分发安装为规划 / 实验，以平台公告为准** |

### 法律 + 路线图

| 文档 | 内容 |
|---|---|
| [`EULA.md`](./docs/EULA.md) | 最终用户许可协议（v1.1 DRAFT，含 good-faith 披露） |
| [`roadmap.md`](./docs/roadmap.md) | SDK 进度：当前状态（0.9.5.27 / klik 波次 / turbo 回退口径）+ 历史 milestone |

---

## 5 分钟跑通

```bash
pip install krow-agent-sdk krow-sdk-install
krow-sdk-install --api-key sk-user-xxxx        # 装私有 runtime wheel（到 https://krow.cn 拿 API key）
```

```python
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key("sk-user-xxxx")
    .with_project_root("./my_workspace")
    .build()                                   # 0.9.5 起默认 klik 运行模式，无需额外设置
)

result = agent.run("写一个 hello world Python 文件到 ./my_workspace/")
print(result.success, result.final_output)
agent.shutdown()
```

> 没装 runtime 时 `agent.run()` 不可用；可以先用 `LLMReplayStore` 走 record/replay 跑 plugin 单元测试，详 [`quickstart.md`](./docs/quickstart.md) §6。

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

> 文档版本：`krow-sdk-docs` 跟随 `krow-agent-sdk` PyPI 主版本同步发布；当前对齐 `0.9.5.27`
> （参 [PyPI 项目页](https://pypi.org/project/krow-agent-sdk/)）。`docs/` 下各文档由主仓自动镜像；本 README 与 `examples/cookbook/README.md` 由人工维护。
