# Krow Agent SDK · 5 分钟 Quickstart

> 本教程让你在 5 分钟内用 Krow Agent SDK 跑一个真实 LLM hello-world，不需要桌面 app、不需要修改 krow 主仓代码。
>
> **进阶资料**：
> - [`api-reference.md`](./api-reference.md) — 完整 API 手册（15 章 / 57 子节）
> - [`advanced-development-guide.md`](./advanced-development-guide.md) — TURBO 哲学 / 工具设计 / 测试方法论
>
> **适用版本**：`krow-agent-sdk >= 0.8.12.5`（`build()` 自动凭证注入 + cloud 模型 fallback + 6 个 `with_<cat>_model` API）。

---

## 0. 你需要什么

| 项 | 说明 |
|---|---|
| **Python** | ≥ 3.11（SDK SSOT：`packages/krow-agent-sdk/pyproject.toml::requires-python`；3.11 / 3.12 / 3.13 都跑得通；monorepo 内 dev `.venv` 锁 3.13，详 `AGENTS.md` §一 SSOT 表） |
| **Krow API Key** | 从 krow 客户端 - 设置 - API Key 创建一个 `sk-...` 前缀的 key（推荐 `sk-user-` 前缀，长度 ≥ 20 字符；充值 ≥ 1 元即可） |
| **OS** | Windows 10+ / macOS 12+ / Linux x86_64（Apple Silicon arm64 也通） |
| **网络** | 能访问 `https://api.krow.cn`（国内直连即可，无需代理） |

---

## 1. 安装（30 秒）

> **当前发布状态**（2026-05-16）：✅ **`krow-agent-sdk==0.8.12.5` 已发 PyPI 主站**：
> ```bash
> pip install krow-agent-sdk
> ```
> EULA 当前为 v1.1 DRAFT（含 good-faith 披露），等真律师签字后转 EFFECTIVE
> （详 [`roadmap.md`](./roadmap.md) Step 2 P2）。
> **runtime wheel** 处于 M9 v2 reverse-proxy **W1-W4 实施中**（2026-05-16 与 Cloud team 协议锁定）；
> 详见 [`runtime-install.md`](./runtime-install.md)。不影响写 plugin + record/replay 测试。
>
> 下文 §1.1-§1.2 是 **Krow team collaborator** 的开发模式入门（monorepo / dev wheel）；
> 外部开发者请直接用 §1.0 的 `pip install krow-agent-sdk`。

### 1.0 外部开发者一行装机（推荐）

```bash
pip install krow-agent-sdk                 # 13 项必需依赖
pip install "krow-agent-sdk[office]"       # +24 项 docx/pptx/excel/pdf
pip install "krow-agent-sdk[visual]"       # +4 项 cairosvg/cairocffi（PPTX 视觉质检，需系统库 libcairo2 + libpango，详 §4.5.1）
pip install "krow-agent-sdk[knowledge]"    # +4 项 networkx/jieba
pip install "krow-agent-sdk[remote]"       # +8 项 fastapi/uvicorn/websockets
pip install "krow-agent-sdk[all]"          # 一站式全装
```

**最小 import 验证**：

```bash
python -c "from krow_agent_sdk import AgentBuilder; print('SDK OK')"
# SDK OK
```

### 1.1 Collaborator 模式：克隆 krow 主仓 + 装 SDK extras

```bash
git clone https://github.com/aullik5/krow.git
cd krow
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS / Linux
pip install -e ".[sdk]"
```

**验证安装**（9 项 smoke 检查）：

```bash
python scripts/validate_sdk_install.py
# Krow Agent SDK · 安装 smoke 验证
# [PASS] 1. krow_agent_sdk top-level import
# [PASS] 2. AgentBuilder 可实例化（不 build）
# [PASS] 3. protocols / experimental.protocols 全套存在
# [PASS] 4. data / diagnostics facade 接通（zero-LLM）
# [PASS] 5. errors 全部异常类可 raise / catch
# [PASS] 6. telemetry opt-in 默认关
# [PASS] 7. deprecation 装饰器可用
# [PASS] 8a. replay framework public API
# [PASS] 9. entry_points opt-in 默认关
# 9/9 PASS
```

或最少 1 行 import 检查：

```bash
python -c "from krow_agent_sdk import AgentBuilder; print('SDK OK')"
# SDK OK
```

### 1.2 远程一行安装（git+pip）

```bash
pip install -e "git+https://github.com/aullik5/krow.git@main#egg=krow[sdk]"
```

### 1.2 Headless Docker 镜像里用 SDK（生产部署）

`deploy/Dockerfile.headless` 默认装 `pip install ".[headless,sdk]"` —— 镜像同时是 krow service runtime + SDK runtime。外部团队部署 plugin 项目可直接 `FROM krow-headless` 拿到 `krow_agent_sdk` 顶级包，无需自己装依赖：

```dockerfile
FROM ghcr.io/aullik5/krow-headless:latest
COPY my_plugins/ /workspace/my_plugins/
ENV KROW_API_KEY=sk-user-...
# headless service 入口或自定义启动器都可以
```

镜像构建期会跑 `python scripts/validate_sdk_install.py` 9 项 smoke 检查，确保 SDK 公共 API 在 Linux container 内 import 链完整。

---

## 2. Hello World：30 行代码跑通真实 LLM（2 分钟）

新建 `hello_krow.py`：

```python
"""Krow Agent SDK Hello World.

跑前：
1. set KROW_API_KEY=sk-user-xxx (Windows PowerShell: $env:KROW_API_KEY='sk-user-xxx')
2. python hello_krow.py
"""
from __future__ import annotations

import os
from pathlib import Path

from krow_agent_sdk import AgentBuilder


def main() -> None:
    api_key = os.environ["KROW_API_KEY"]
    project_root = Path.cwd() / "krow_workspace"
    project_root.mkdir(exist_ok=True)

    agent = (
        AgentBuilder()
        .with_krow_api_key(api_key)
        .with_project_root(project_root)
        .build()  # 自动注入凭证 + cloud 模型 fallback
    )

    try:
        result = agent.run(
            "用一句话告诉我现在是哪一年（不要解释，直接回答）",
        )
        print("Success :", result.success)
        print("Output  :", result.final_output)
    finally:
        agent.shutdown()


if __name__ == "__main__":
    main()
```

跑：

```bash
$env:KROW_API_KEY='sk-user-xxxxxxxxxxxxxxxx'
python hello_krow.py
```

期望输出（LLM 自然语言，准确性优先）：

```
Success : True
Output  : 现在是 2026 年。
```

> **第一次跑慢 60-90 秒是正常的**：krow 在 build 时会一次性 lazy-load 19 个内置 ACT（`modules/agent/act/acts/*/__act__.yaml`）、注册 ~120 个 tool、初始化 EventBus / BudgetController / ConcludeGuard 链；之后调用秒级返回。

### 流式输出（实时事件 + 最终结果）

如果你想做交互式 UI（实时 token / 步骤推进 / progress bar），用 `agent.run_stream()`：

```python
for item in agent.run_stream("写一份关于电池技术的报告"):
    if item.kind == "event":
        # 流式事件：macro 步骤 / micro 工具调用 / LLM 响应等
        print(f"[{item.event.type}] {item.event.payload.get('summary', '')}")
    elif item.kind == "result":
        # 最后一个 yield：完整 AgentV3Result
        print("DONE:", item.result.final_output)
    elif item.kind == "error":
        # 后台 agent 异常透传
        raise item.error
```

`run_stream()` 返回 `Iterator[StreamItem]`，3 种 kind：

| `kind` | 含义 | 字段 |
|---|---|---|
| `"event"` | 流式事件 | `item.event` 是 `Event(type, payload, trace_id, timestamp)` |
| `"result"` | 最终结果（恰好 yield 1 次） | `item.result` 是 `AgentV3Result` |
| `"error"` | 后台异常 / idle_timeout | `item.error` 是 `BaseException` |

默认订阅 topics（覆盖 macro/micro/LLM/task lifecycle）：

```python
topics=(
    "macro_react.plan_created", "macro_react.todo_updated",
    "progressive.step_start", "progressive.step_completed",
    "progressive.replan_start", "progressive.early_conclude",
    "planner.phase2_start", "planner.phase2_end",
    "react.step", "react.complete", "react.thinking_stream",
    "llm.request", "llm.response", "llm.error",
    "agent.task_start", "agent.task_complete",
    "agent.task_failed", "agent.task_cancelled",
)
```

可用 `topics=` 自定义，**但必须包含 `agent.task_complete` / `agent.task_failed` / `agent.task_cancelled` 至少 1 个终止 topic**（SDK fail-loud 校验，否则 `ValueError`）；用户提前 `break` for loop 时 SDK 自动清理 subscribe + 信号 stop_event 让 agent 协作 stop（详 `Agent.run_stream()` docstring）。

**故障排查**（异常类 SSOT：`modules/agent/sdk/errors.py`）：

| 现象 | 原因 | 修法 |
|---|---|---|
| `MissingKrowAPIKeyError` | 没设 `KROW_API_KEY` env var | 跑前 `set KROW_API_KEY=sk-user-...` |
| `KrowAPIKeyInvalidError` / `InvalidKrowAPIKeyError` | API key 无效 / 已撤销 | 在 krow 后台重新创建一个；`InvalidKrowAPIKeyError` 是格式校验错（`build()` 时），`KrowAPIKeyInvalidError` 是远端拒绝（`run()` 401 时） |
| `KrowQuotaExceededError`（HTTP 402） | 账户余额不足 / 配额耗尽 | 充值 ≥ 1 元；或检查 quota 限制 |
| `MissingProjectRootError` / `ProjectRootNotWritableError` | 没设 `with_project_root()` 或路径不可写 | 调用 `.with_project_root(Path("/some/writable/dir"))` |
| `LLMProviderError` | LLM 调用失败（如默认模型与 cloud 不匹配） | `build()` 会自动 fallback；如仍报错检查 `with_chat_model("qwen3.6-plus")` |
| 卡 60+ 秒不动 | 第一次 ACT lazy-load + tool registry 暖机 | 等待；第二次会快得多 |

---

## 3. 加一个 plugin：自定义 ACT（3 分钟）

> 这是 SDK 真正的价值——让你的垂直业务工具 / ACT / hint 不需要 check-in 到 krow 主仓即可被 Agent 使用。

> **协议 SSOT**：`modules/agent/sdk/protocols/act.py:ACTPlugin` —— `plugin_id` / `act_name` properties + `get_act_root()` / `get_act_file_path()` / `get_tool_names()` methods。`plugin_id` 必须 `<org>.<plugin_name>` 双段命名（ACT name 通常等于第二段）。

新建 `my_research_act.py`：

```python
"""自定义 ACT：科研论文阅读助手。

定义一个 ACT 让 Agent 在做"读 paper / 抽取 entity / 写 summary"类任务时
自动选择这个 ACT，进入更聚焦的工作模式。
"""
from __future__ import annotations

from pathlib import Path


class ResearchPaperReader:
    """科研论文阅读 ACT plugin（实现 krow_agent_sdk.protocols.ACTPlugin）."""

    plugin_id = "acme.research_paper"
    act_name = "research_paper"

    def get_act_root(self) -> Path:
        return Path(__file__).parent / "act_assets" / "research_paper"

    def get_act_file_path(self) -> Path:
        return self.get_act_root() / "ext_research_paper.md"

    def get_tool_names(self) -> list[str]:
        # 工具名以 ToolManager 实际快照为准（可用 diagnostics.get_tool_snapshot() 查看）
        return [
            "read_file",
            "read_document",
            "search_files",
            "ai_search",  # 联网搜索；如需"链式思考"请直接用 ReACT 引擎天然能力
        ]
```

`act_assets/research_paper/ext_research_paper.md`（YAML frontmatter + 扩展指南二合一）：

````markdown
---
name: research_paper
display_name: 科研论文阅读
description: |
  当用户要"读论文 / 抽取作者 / 总结实验结果 / 找引用关系"时进入此 ACT。
  本 ACT 内 Agent 会重点使用 native_fileops + reasoning_pipeline 组合。
when_to_enter:
  - "用户提到 paper / 论文 / arxiv / 学术 / 文献"
  - "用户上传了 .pdf 文件且文件名/路径中含 paper/article/journal"
tools:
  - read_file
  - read_document
  - search_files
  - ai_search  # 联网搜索；如需"链式思考"请直接用 ReACT 引擎天然能力
priority: 10
---

# 科研论文阅读 ACT — 扩展指南

## 推荐工作流

1. 调 `read_document` 把 PDF 抽成 markdown
2. 用 ReACT 引擎天然多步推理拆解出"作者 / 数据集 / 方法 / 结论"四要素（无需特殊"chain-of-thought"工具）
3. 用 `save_note` 落盘 evidence 后再做 cross-paper 综合

## 反模式

- ❌ 直接调 `read_file` 处理 PDF（不会自动 OCR）
- ❌ 跳过 evidence 直接给综合结论（不可追溯）
````

> **on_load / on_unload 是可选的**：实现 `BasePluginLifecycle` 子类才有；ACTPlugin Protocol 本身不要求 lifecycle 方法。`get_act_file_path()` 返回的路径必须存在且可读（fail-loud）。

注册到 hello world：

```python
from my_research_act import ResearchPaperReader

agent = (
    AgentBuilder()
    .with_krow_api_key(api_key)
    .with_project_root(project_root)
    .with_act_plugin(ResearchPaperReader())  # ← 加 plugin
    .build()
)
```

`AgentBuilder` 还支持加自定义 `Tool` / `Hint` / `Gate` / `EventListener` / `Observability` / `MCPServer` / `Security` / `DomainPack` / `VisualAdapter` plugin —— 完整 10 类 plugin protocol 详 [`api-reference.md`](./api-reference.md) §5；进阶最佳实践详 [`advanced-development-guide.md`](./advanced-development-guide.md) §3-§5。

---

## 4. 真实业务范式：5 类 plugin 一句话上手

| 我想... | 用什么 plugin | 一行代码 |
|---|---|---|
| 加新工具（如调用我们公司的 ERP API） | `ToolPlugin` | `.with_tool_plugin(MyERPTool())` |
| 自定义 Agent 工作流 / 工具组合（如"科研模式"） | `ACTPlugin` | `.with_act_plugin(MyACT())` |
| 给 LLM 加上下文软提示 | `HintPlugin` | `.with_hint_plugin(MyHint())` |
| 在 Agent 完成前做安全 / 合规校验 | `GatePlugin` | `.with_gate_plugin(ComplianceGate())` |
| 监听 agent 事件（如步骤完成时推送钉钉） | `EventListenerPlugin` | `.with_event_listener_plugin(MyListener())` |
| 接入第三方/远程 MCP server（自动注册工具到 Agent） | `MCPServerPlugin`（form-B/C） | `.with_mcp_server_plugin(MyMCP())` + `KROW_ENABLE_MCP_SERVER_PLUGIN=1` |

### MCPServerPlugin 三形态简表（详 `experimental/protocols/mcp_server.py`）

| 形态 | 何时用 | SDK 行为 |
|---|---|---|
| **A** `get_servers()` | 仅声明远程 MCP metadata，自己处理调用 | collect 到 `Agent.mcp_servers` facade，**不**自动注册工具 |
| **B** `get_in_process_servers()` 返**本进程** server | 内嵌 MCP server，避开网络 | 自动注册到 `ToolManager`（feature flag `KROW_ENABLE_MCP_SERVER_PLUGIN=1`） |
| **C** `get_in_process_servers()` 返**远程 client** | 接外部第三方 MCP server（HTTP/SSE/stdio…） | 与 B 同代码路径，额外在 `agent.shutdown()` 时自动调 `close()` / `aclose()` 优雅释放 |

**形态 C 例**（远程 MCP client 自动注册 + 优雅关闭）：

> 鸭型协议 SSOT：`server_instance` 必须实现 `list_tools() -> list[dict]` +
> `call_tool(name: str, args: dict) -> Any`，可选 `close()` / `aclose()`。
> SDK 不锁死 transport（HTTP / SSE / stdio / WebSocket / gRPC 都行），只要满足
> 上述鸭型即可。下面用一个最小自定义 client 演示（**不依赖任何特定上游 SDK，
> 直接抄即可跑**）：

```python
import os
from typing import Any
from krow_agent_sdk import AgentBuilder


class MyRemoteMCPClient:
    """最小远程 MCP client（鸭型协议；可换成 mcp 官方 SDK / 自家 transport）.

    主仓真实接入 mcp 官方 SDK 时，请用 ``mcp.ClientSession`` 包一个 stdio /
    http transport，再把 ``ClientSession`` 实例当作 ``server_instance`` 注入即可
    （SDK 不区分上游 client 库）；本示例为可独立运行版本。
    """

    def __init__(self, mcp_url: str, api_key: str):
        import httpx
        self._url = mcp_url
        self._api_key = api_key
        self._http = httpx.Client(timeout=30.0)

    def list_tools(self) -> list[dict]:
        # 远程拉工具元数据（实际协议见你接入的 MCP server 文档）
        r = self._http.get(
            f"{self._url}/tools",
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        r.raise_for_status()
        return r.json()["tools"]

    def call_tool(self, name: str, args: dict) -> Any:
        r = self._http.post(
            f"{self._url}/tools/{name}",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=args,
        )
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._http.close()


class MyRemoteMCPPlugin:
    plugin_id = "myorg.remote_mcp"

    def __init__(self, mcp_url: str, api_key: str) -> None:
        self._client = MyRemoteMCPClient(mcp_url, api_key)

    def get_servers(self) -> list[dict]:
        return [{"name": "remote_x", "url": "https://...", "transport": "sse"}]

    def get_in_process_servers(self) -> list[tuple[str, Any]]:
        return [("remote_x", self._client)]   # 远程 client 当 server 注入


os.environ["KROW_ENABLE_MCP_SERVER_PLUGIN"] = "1"
agent = (
    AgentBuilder()
    .with_krow_api_key(os.environ["KROW_API_KEY"])
    .with_project_root("./workspace")
    .with_mcp_server_plugin(MyRemoteMCPPlugin("https://your-mcp-server.example.com", "your-mcp-key"))
    .build()
)
try:
    result = agent.run("...")
finally:
    agent.shutdown()  # SDK 自动调用 self._client.close() 释放 httpx 连接
```

完整 protocols 见 `krow_agent_sdk.protocols`：

```python
from krow_agent_sdk.protocols import (
    ACTPlugin,
    ToolPlugin,
    HintPlugin,
    GatePlugin,
    EventListenerPlugin,
    ObservabilityPlugin,
)
# 实验性（Wave 2 才稳定）
from krow_agent_sdk.experimental.protocols import (
    MCPServerPlugin,
    SecurityPlugin,
    DomainPackPlugin,
)
```

---

## 4.5 PPTX 视觉质检：用 `visual_inspect` 让 VLM 给你的 PPT 打分

> PR-7 (`docs/governance/pptx-geometry-quality-roadmap.md` Batch 3, 2026-05-16)：headless 环境下 SDK 用户**一行**接入 PPTX 视觉质检。

### 4.5.1 依赖准备

```bash
# Python 包（PyPI 上之后）
pip install "krow-agent-sdk[visual]"

# 系统库（cairosvg / cairocffi 的底层）
# Linux:
sudo apt-get install -y libcairo2 libpango-1.0-0 fonts-noto-cjk
# macOS:
brew install cairo pango
# Windows:
conda install -c conda-forge cairo pango
# 或装 GTK3 runtime: https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer
```

### 4.5.2 函数式 API（推荐）

```python
from krow_agent_sdk.visual import register_default_pptx_adapter, visual_inspect

register_default_pptx_adapter()  # 进程内一次即可，注册 HeadlessPPTXVisualAdapter

result = visual_inspect(
    "/tmp/output.pptx",
    mode="verify",
    page_index=-1,            # -1 = 全部页
    expectation="标题包含 2026 OKR + 至少 8 页 + 每页有结论框",
)

if not result.get("success"):
    for issue in result.get("issues", []):
        print(f"[{issue['severity']}] page {issue.get('page')}: {issue['title']}")
        print(f"  → {issue.get('description', '')}")
```

返回字段：

- `success` (bool)：整体是否通过
- `issues` (list)：VLM 标记的问题列表（含 `severity` / `page` / `title` / `description`）
- `render_source` (str)：实际渲染来源（`cairosvg-pisma-svg` / `qgraphics-desktop` / `pil-image`）
- `render_fidelity_class` (str)：渲染保真度（`pixel_match` / `geometry_match` / `layout_only`）

### 4.5.3 Builder API（Agent 生命周期内自动 unregister）

```python
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key(api_key)
    .with_default_pptx_adapter()   # 一行打开 PPTX 视觉质检
    .build()
)

# agent.run() 内的 visual_inspect 工具调用现在能正确处理 .pptx
result = agent.run("生成 2026 H1 营收复盘 PPT，至少 8 页，每页带数字结论")
```

`agent.shutdown()` 时自动 unregister adapter，避免全局 registry 污染。

### 4.5.4 几何质检（Q105/106/107）— Batch 1+2 自动生效

PISMA-SVG 生成的 PPTX 在 `visual_inspect` 时会自动注入几何证据：

- **Q105 hub-spoke 对称性**：辐射图的辐射线角度是否均匀（标准差 > 5° 报警）
- **Q106 线长方差**：辐射图的辐射线长度是否一致（CV > 8% 报警）
- **Q107 marker 方向反向**：箭头是否指向枢纽而非辐射端（反向报警）
- **AlignReport snap drift**：自动对齐 pass 报告（snap 距离 > 阈值在 evidence 中标出）

```python
result = visual_inspect(pptx_path, expectation="...")
# 几何 issue 会出现在 issues 中，severity=warning（路线图 Batch 1+2 默认）
# 1 周观察期满后升 severity=error（Q107 marker 方向 / 严重几何漂移）

# 想强制阻断 conclude？打开 verify_completion gate (PR-5)：
# os.environ["PISMA_PPTX_GEOMETRY_VERIFY_GATE"] = "true"
# os.environ["PISMA_PPTX_GEOMETRY_VERIFY_GATE_ANY_SEVERITY"] = "true"  # opt-in
```

### 4.5.5 故障排除

| 现象 | 原因 | 处理 |
|---|---|---|
| `register_default_pptx_adapter` 抛 `RuntimeError: HeadlessPPTXVisualAdapter 不可导入` | wheel 边界异常 | 用 monorepo `pip install -e ".[sdk]"` 或检查 Python 路径 |
| `visual_inspect` 返回 `render_available=false` | 系统库 libcairo2 / libpango 缺 | 按 §4.5.1 装系统库 |
| 中文字体显示成 □ | 缺 CJK 字体 | Linux: `apt install fonts-noto-cjk`；macOS 自带；Windows 装"思源黑体" |
| `render_fidelity_class=layout_only` 且 VLM 报"图标对不上" | 非 PISMA-SVG 来源走 `ooxml_to_svg` 兜底 | 已是预期行为；图标位置 OK 但纹理可能丢失 |

---

## 5. Read-only 数据 / 诊断（侦察 Agent 内部状态）

```python
from krow_agent_sdk import data, diagnostics

# Read-only 状态快照
print(data.get_state_snapshot(agent))     # AgentV3 + StateManager 状态
print(data.get_memory_stats())            # 短/长记忆条数 + 大小
print(data.query_memories(query_text="paper"))  # 自然语言查记忆（首参 query_text，关键字必填）

# Plugin / tool 注册侦察
print(diagnostics.get_plugin_snapshot())  # 你的 plugin 是否真注册成功
print(diagnostics.get_tool_snapshot())    # ToolManager 内全部 tool
print(diagnostics.dump_state(agent))      # 完整 dump（debug 用）
```

**特点**：

- 所有 facade 都是**只读 + 无副作用 + 零 LLM 调用 + 异常吞掉返 dict** —— 即使 agent 状态异常也不会 crash 你的代码
- 适合在 plugin / 自定义 UI / 监控面板里调用

---

## 5.5 LLM Record / Replay：写自己的 plugin 测试不烧钱

外部 SDK 用户写 plugin 测试时面临一个矛盾：要保证质量需要真实 LLM 调用，但每次跑 CI 都烧 token + 慢。Krow SDK 提供了 record / replay 框架（来自 krow 主仓的 M6 工具，P1b 起作为 SDK 一等公民）。

**最简方式**（Step 2 P2 起，推荐）：链式 `with_replay_store(store)` 让 SDK 自动接入：

```python
from krow_agent_sdk import AgentBuilder
from krow_agent_sdk.replay import LLMReplayStore

store = LLMReplayStore.from_env("tests/fixtures/my_plugin.json")

agent = (
    AgentBuilder()
    .with_krow_api_key(api_key)
    .with_project_root(project_root)
    .with_replay_store(store)   # ← SDK 自动 wrap 所有 LLM provider
    .build()
)
try:
    result = agent.run("...")   # 本地 record / CI replay 自动切换
finally:
    agent.shutdown()             # 自动 uninstall replay swap
```

**手动方式**（如果你需要在 builder 之外 wrap）：

```python
from krow_agent_sdk.replay import LLMReplayStore, wrap_provider_manager_with_replay

store = LLMReplayStore.from_env("fixtures/my_test.json")
swap = wrap_provider_manager_with_replay(store)
try:
    # ... 你的测试 ...
finally:
    swap.uninstall()
```

支持的 mode（环境变量 `KROW_LLM_REPLAY_MODE`）：

| mode | 行为 | 何时用 |
|---|---|---|
| `record` | 真实 LLM 调 + 写 fixture（已存在则覆盖同 hash） | 本地首次录制 |
| `replay`（默认） | 不调真实 LLM，从 fixture 读 | CI / 日常测试 |
| `auto` | fixture 存在 → replay；不存在 → record | 增量演化 fixture |

如果 replay 模式撞 cache miss，默认 `LLMReplayMiss` 抛错防止悄悄烧钱。

完整 API：`from krow_agent_sdk.replay import ...`：`LLMReplayStore`、`RecordReplayWrapper`、`ReplayRecord`、`LLMReplayMiss`、`compute_request_hash`。

## 6. 配置 / 环境变量速查

| Env var | 默认 | 作用 |
|---|---|---|
| `KROW_API_KEY` | 必填 | 你的 sk-user-xxx 凭证 |
| `KROW_PROJECT_ROOT` | 可选 | 默认 project_root（被 `.with_project_root()` override） |
| `KROW_ENABLE_PLUGIN_ENTRY_POINTS` | `0` | opt-in entry_points 自动扫描（小心 supply-chain） |
| `KROW_SDK_TELEMETRY` | `0` | opt-in 上报 SDK 使用统计（不含敏感数据） |
| `KROW_SDK_HTTP_GATEWAY` | `0` | opt-in 启动 HTTP gateway，让外部 UI 通过 HTTP 调 SDK |
| `KROW_SDK_BUILD_VALIDATE_CONNECTION` | `1` | build() 内 GET /v1/models 验证 + 模型 fallback |

---

## 7. 下一步 + 完整 Roadmap

完成 hello world 后：

1. **业务上**：把第 3 节的 ACT 模板改成你领域的（工业设计 / 法律 / 教研 ...）
2. **架构上**：读 [`api-reference.md`](./api-reference.md) §5 的 10 类 plugin protocol（6 stable + 4 experimental）；[`advanced-development-guide.md`](./advanced-development-guide.md) §1 TURBO 哲学 / §4 ACT 最佳实践 / §6 测试方法论
3. **测试上**：用 `LLMReplayStore` + `AgentBuilder.with_replay_store()` 写 record / replay 单测（详 §5.5 + [`api-reference.md`](./api-reference.md) §7）；含 `tests/` 的 monorepo 安装可用 `from krow_agent_sdk.test_sdk import HeadlessAgentHarness`
4. **生产上**：set `KROW_SDK_TELEMETRY=1` 帮 krow 团队改进 SDK；set `KROW_SDK_HTTP_GATEWAY=1` 让外部 UI 接入

| Step | Wave | 状态 | 关键能力 |
|---|---|---|---|
| Step 1 | Wave 1-4 | ✅ 已落地 | mvp_critical 6 类 plugin protocol（ACT / Tool / Hint / Gate / EventListener / Observability）+ 3 类 experimental（MCPServer / Security / DomainPack）+ AgentBuilder + entry_points opt-in + telemetry opt-in + deprecation 框架 |
| Step 1 后续 | PR A1/A2/A3/A4 | ✅ 已落地 | API Key 认证 + read-only data facade + ACT extended.md 增量 + ReACT budget bugfix |
| Step 1 收尾 | PR #211 | ✅ 已落地 | build() 自动注入凭证 + cloud 模型自动 fallback（你正在用的版本） |
| Step 2 P0 | M1-M4 | ✅ 已落地 | `packages/krow-agent-sdk/` 子包 + dual-build CI + nightly + SBOM + OIDC publish workflow（待 release engineer 配 OIDC + 打 tag 即正式发布） |
| Step 2 P1 | PR #224 / #227 / #230 | ✅ 已落地 | `with_default_model`（已废弃，详 chore/sdk-model-selection-api 取代为 6 个 `with_<cat>_model`）/ `with_replay_store` / `MCPServerPlugin` form-C |
| Step 2 P2 | PR #239 | ✅ visual_inspect plugin 完整公开（独立 `VisualAdapterPlugin` protocol + `with_visual_adapter(ext, cls)` 链式 API + `from krow_agent_sdk.visual import VisualAdapter` namespace） |
| Step 3+ | 长期 | 计划中 | knowledge_compiler 开放式 domain pack ontology editor、多 plugin IPC、plugin marketplace |

完整路线图 + 每个 Wave 的待办：见 [`docs/sdk/roadmap.md`](./roadmap.md)（SSOT），`AGENTS.md` §十一 仅一行指针。

### 7.1 Step 2 P2：自定义视觉适配器（外部团队 视觉 QA / CAD / 工业图纸 用）

外部团队若需要让 Agent 处理**非内置**文件类型（如 CAD `.dwg` / STEP / 工业图纸 / 自定义报告页布局），可注册自己的 `VisualAdapter`：

```python
from typing import Any, List, Optional
from krow_agent_sdk import AgentBuilder
from krow_agent_sdk.visual import VisualAdapter, ElementEntry, SceneConfig

class CADVisualAdapter(VisualAdapter):
    """自定义 CAD 适配器：5 abstract method + 1 property（``scene_config``）."""

    def open(self, source: Any, **kwargs: Any) -> None:
        # 打开 .dwg 文件 + 缓存解析
        ...

    def close(self) -> None:
        ...

    def render(self, page_index: int, width: int = 960, height: int = 540) -> bytes:
        # 渲染指定 layout 为 PNG
        ...

    def inventory(self, page_index: int) -> List[ElementEntry]:
        # 抽结构化元素（block / dimension / annotation 等）
        ...

    def page_count(self) -> int:
        ...

    @property
    def scene_config(self) -> Optional[SceneConfig]:
        # 返回 None 即用 SDK 默认场景配置（_DEFAULT_SCENE_CONFIG 兜底）；
        # 自定义场景（背景色 / DPI / 尺寸单位）请构造 SceneConfig 返回。
        return None

agent = (
    AgentBuilder()
    .with_krow_api_key("sk-user-xxx")
    .with_project_root("./workspace")
    .with_visual_adapter(".dwg", CADVisualAdapter)   # inline 直接注册
    .with_visual_adapter(".step", CADVisualAdapter)
    .build()
)
# 此后 agent.run("检查图纸 D:/foo.dwg 的标注是否合规") 内部会自动用 CADVisualAdapter
```

> **协议 SSOT**：抽象方法签名 + `scene_config` property 见 `modules/agent/visual/protocol.py:VisualAdapter`
> （5 abstractmethod + 1 property）。漏 `scene_config` property 会导致 ABC 无法实例化。

或包装成 plugin 形态（推荐——支持 entry_points 自动加载 + lifecycle hook）：

```python
from krow_agent_sdk.experimental.protocols import VisualAdapterPlugin

class CADPlugin:
    plugin_id = "acme.cad_2026"  # 双段命名 "<org>.<plugin_name>"，详 _plugin_id_validator
    def get_visual_adapters(self):
        return [(".dwg", CADVisualAdapter), (".step", STEPVisualAdapter)]

agent = (
    AgentBuilder()
    .with_krow_api_key("sk-user-xxx")
    .with_visual_adapter_plugin(CADPlugin())
    .build()
)
```

---

## 8. 常见问题

### Q1：跑出来的 LLM 模型是什么？

由 cloud 端按你的 API Key 权限决定。`build()` 在 `validate_connection=True` 时会：

1. GET `https://api.krow.cn/v1/models` 拿你账号实际可用清单
2. 若你本地默认模型（`config/module_config.json` 里的 `default_chat_model`）不在清单 → 自动 fallback 到清单内第一个非 vision/reasoning 模型
3. 不存在的"幽灵模型"（如旧版本 `claude-opus-4.6`）会被自动绕过；你不会看到 `AuthExpiredError 401` 误诊

要按类别明确指定模型？SDK 提供 6 个链式 `with_<category>_model()` API（chore/sdk-model-selection-api · 2026-05-15）：

```python
agent = (
    AgentBuilder()
    .with_krow_api_key(api_key)
    .with_project_root(project_root)
    # 6 类全部可选；未指定的 category 走 cloud-model fallback
    .with_chat_model("qwen3.6-plus")                      # 对话 / 通用 / 代码
    .with_reasoning_model("deepseek-reasoner")            # 深度推理 / CoT
    .with_vision_model("qwen2.5-vl-72b-instruct")         # 视觉理解 (VLM)
    .with_image_gen_model("qwen-image")                   # 图像生成
    .with_image_edit_model("qwen-image-edit")             # 图像编辑
    .with_text_encoder_model("text-embedding-v2")         # 文本嵌入 / embedding
    .build()
)
```

cloud 当前可选清单 → `GET /v1/models`（按 capability 过滤；详 `modules.ai.providers.ModelCategory` enum 6 个值）。

优先级：`.with_<cat>_model(...)` > `module_config.json` > 自动 cloud-model fallback. 如果指定的模型 cloud 不返（打错字 / 模型已下线）→ log warning + 走 fallback，**不阻塞** build.

> **历史变更**：`with_default_model(chat_model, reasoning_model)` 于 chore/sdk-model-selection-api 移除. 用 `.with_chat_model(...) + .with_reasoning_model(...)` 替代（语义版本破坏性变更，详专家辩论 §五 / §六）.

### Q2：成本怎么估？

- 一次 hello world 约 0.001-0.005 元（visible-only 场景）
- 完整 ReACT cycle（含 plan_task → run_step ×N → verify_completion）约 0.05-0.3 元
- 跑 `KROW_SDK_TELEMETRY=1` 可以看每次 build / 每次 plugin 调用的 token / 钱

### Q3：可以离线跑吗（不调 krow cloud）？

不能。Krow SDK 强依赖 krow cloud LLM provider（设计 trade-off：保证统一计费 / 安全审计）。

如果你需要 BYO LLM provider（自己接 OpenAI / vLLM / Ollama），目前**没有**官方支持；这条路在 design doc §3 章节里被显式标记为"暂不开放"——避免破坏统一认证 / 计费 / 安全 invariant。

### Q4：plugin 报错 / 崩溃会拖垮 Agent 吗？

不会。`AgentBuilder.build()` 加载每个 plugin 时都有：

- **签名校验** fail-loud（`PluginSignatureMismatchError`）
- **lifecycle on_load 异常**会 fail-loud；on_unload 异常 log warning 不阻塞 shutdown
- 主仓 ConcludeGuard 8 gates 任何一个判 FAIL → Agent 会 replan / re-conclude，**不会**让 plugin 错误污染 final output

详 [`advanced-development-guide.md`](./advanced-development-guide.md) §6（测试方法论 + 故障排查）。

---

> 文档版本：v1.2（2026-05-16，配套 `0.8.12.5` PyPI release + cloud-team 协议锁定）
> 维护：在 SDK 主版本变化时更新；外部开发者反馈的 FAQ 直接累积到第 8 节。
