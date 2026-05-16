# Krow Agent SDK Runtime 安装指南（外部开发者）

> **当前状态（2026-05-16）** 🚀：v2 reverse-proxy 协议**已与 Krow Cloud team 锁定**，
> 进入 **W1-W4 实施期**（详 [`roadmap.md`](./roadmap.md) Step 2 P3 / M9）。
> 真实的"装包就能 ``agent.run()``"路径预计 **2026-06** 完成上线。
>
> **现阶段（2026-05）外部开发者实际可用路径**：
> - ✅ ``pip install krow-agent-sdk`` → 写 plugin + 用 `LLMReplayStore` record/replay 测试
> - 🚧 ``agent.run("...")`` 真实跑：等 W4 完成；可加入 pilot 名单优先体验
>     （联系 [support@krow.cn](mailto:support@krow.cn)）
>
> **设计 v2 reverse-proxy（2026-05-16 锁定）**：
> - 私有 runtime wheel 走 **Krow Cloud 反向代理** 分发：
>   `https://api.krow.cn/sdk/runtime/pypi/{simple,files}/...`
> - Storage：火山引擎 TOS（cn-shanghai，bucket `krow-sdk-runtime`）
> - 鉴权：`KROW_API_KEY` Bearer token，gateway 内套餐 entitlement + rate limit + 计量
> - 客户感知：与装公开 wheel 体感一致，但走 Krow Cloud 一站式鉴权（不需要 GitHub PAT，不需要单独配 index-url）
>
> 前置阅读：[``quickstart.md``](./quickstart.md)（5 分钟上手公开 SDK）

---

## 0. 你需要的两个 wheel

| Wheel | 是什么 | 在哪装 | 鉴权 |
|---|---|---|---|
| ``krow-agent-sdk`` | 公开 SDK：协议 + facade + vendor stub | PyPI（公开） | 无 |
| ``krow-agent-sdk-runtime`` | 私有 runtime：核心算法 + ACT 工具实现（Cython 编译） | Krow Cloud 反向代理（TOS-backed） | `KROW_API_KEY` Bearer token |

只装公开 SDK 时：可写 plugin、跑 plugin 单元测试，但不能 ``agent.run()``.
装上 runtime 后：可调真正的 ReACT 引擎、跑完整 agent 任务.

---

## 1. 前置准备

### 1.1 Krow API key

1. 注册账号：https://krow.cn/signup
2. 登录后进 Dashboard → Settings → API Keys
3. 点 "Generate New Key"，选 "SDK Runtime Access" scope
4. 复制 key（形如 ``sk-user-xxxx``，**这是唯一一次能看到完整 key 的机会**）
5. 保存到 ``$KROW_API_KEY`` 环境变量（推荐）或密码管理器

### 1.2 Python 版本

Runtime wheel 当前支持：

- Python **3.11 / 3.12 / 3.13**
- Linux / macOS / Windows

确认你的 Python：

```bash
python --version
# Python 3.13.x ← OK
```

### 1.3 装 ``krow-sdk-install`` CLI

```bash
# 推荐用 pipx（隔离）
pipx install krow-sdk-install

# 或直接 pip
pip install krow-sdk-install
```

---

## 2. 装 Runtime Wheel（一行）

```bash
krow-sdk-install --api-key $KROW_API_KEY
```

工作流程（v2 reverse-proxy）：

1. CLI 调 Krow Cloud `GET /sdk/runtime/pypi/simple/krow-agent-sdk-runtime/`
   （Bearer ``$KROW_API_KEY``）拉 PEP 503 index
2. Krow Cloud gateway 鉴权 + 套餐 entitlement（Free 无 / Basic 10 次/天 / Pro 50 / Premium 无限）+ rate limit（10/min simple + 5/min files）
3. CLI 取 manifest 内对应当前 OS / Python 版本的 wheel，调 `GET /sdk/runtime/pypi/files/...` 走 TOS 流式下载
4. CLI 校验 wheel SHA256 与 manifest 一致 → `pip install` 本地

**整个过程不需要你接触 GitHub PAT 或外部 PyPI index**；客户机只与 `api.krow.cn` 一个 endpoint 通信。

### 2.1 升级到最新 runtime

```bash
krow-sdk-install --api-key $KROW_API_KEY --upgrade
```

### 2.2 安装指定版本

```bash
krow-sdk-install --api-key $KROW_API_KEY --version 0.8.12  # 与 krow-agent-sdk 同名版本号
```

### 2.3 校验安装

**推荐路径**（外部开发者）—— 走公共 SDK API：

```python
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key("sk-...")  # 任何合法 sk- 前缀的 key（详 §3.1）
    .with_project_root("./workspace")
    .build(validate_connection=False)  # 离线校验只看初始化是否抛异常
)
agent.shutdown()
print("✓ Runtime wheel 装好了")
```

**进阶**（仅 monorepo / runtime 装好后可用，外部开发者一般不需要）：

```python
import modules.agent.react_engine
import modules.agent.progressive.budget_controller
print("✓ runtime modules 可 import")
```

---

## 3. 用 SDK + Runtime 跑第一个 Agent

```python
import os
from pathlib import Path
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key(os.environ["KROW_API_KEY"])
    .with_project_root(Path.cwd() / "workspace")
    .build(validate_connection=True)
)

try:
    result = agent.run("写一个 hello world Python 文件到 ./workspace/")
    print("Success:", result.success)
    print("Output :", result.final_output)
finally:
    agent.shutdown()
```

> API SSOT：`AgentBuilder` 链式 API 完整签名见 `modules/agent/sdk/builder.py`；
> `AgentV3Result` 字段（`success` / `report` / `error` / `final_output` property）见
> `modules/agent/agent_v3.py`。

---

## 4. 常见问题

### Q1: 跑 ``krow-sdk-install`` 报 ``❌ Krow API key 校验失败 (HTTP 401)``

**原因**：API key 错或被撤销.

**修法**：

1. 检查 key 拼写（注意首尾空格 / 引号）
2. 到 https://krow.cn/dashboard 查 key 状态
3. 如已撤销 → 生成新 key

### Q2: 跑 ``krow-sdk-install`` 报 ``❌ 您的账户未开通 SDK Runtime``

**原因**：免费（Free）套餐默认不含 SDK Runtime entitlement.

**修法**：联系 [sales@krow.cn](mailto:sales@krow.cn) 升级到 **Basic** 套餐及以上（Basic 10 次/天 / Pro 50 次/天 / Premium 无限；详 cloud-team 协议锁定 §3.1）.

### Q3: ``import modules.agent.react_engine`` 报 ``ModuleNotFoundError``

**原因**：runtime wheel 没装上（或装了但平台不匹配）.

**修法**：

```bash
# 检查
pip show krow-agent-sdk-runtime
# 如果没有：
krow-sdk-install --api-key $KROW_API_KEY
# 如果有但仍报错：
python --version  # 确认 3.11 / 3.12 / 3.13
```

### Q4: Krow Cloud 不可达 (HTTP 504 / DNS error)

**原因**：

- 你的网络封禁了 ``api.krow.cn``
- Krow Cloud 暂时故障

**修法**：

1. 测试 ``curl https://api.krow.cn/healthz``
2. 查 https://status.krow.cn 看 Krow Cloud 状态
3. 公司网络 → 与 IT 协调白名单 ``*.krow.cn``

### Q5: 装 runtime 后体积多大？

```
krow-agent-sdk:         ~150 KB（公开协议 + facade + vendor stub）
krow-agent-sdk-runtime: ~60 MB（Cython 编译 .so/.pyd + 324 .py 基础设施 + 19 ACT yaml + 121 extended.md）
合计：约 60 MB（wheel 自身）+ 三方 Python 依赖（pip 自动拉，约 200-300 MB）
```

> wheel 体积是**仅 krow 自家代码 + 资源**；三方依赖（pyyaml / python-pptx / lxml /
> Pillow / pandas / openpyxl / python-docx / numpy / networkx / PyMuPDF / matplotlib /
> svglib / reportlab / fastapi / uvicorn / httpx / pydantic / loguru / 等）由 wheel 的
> ``Requires-Dist`` 元数据声明，``pip install`` 时自动拉取。

vs 主仓 ``krow_lite`` 桌面版（~280 MB Nuitka 单文件）—— wheel 形态把"代码"与"依赖"
分离开装，部署更灵活但首次安装时间稍长（带宽决定）。

### Q6: 我**只**装 runtime + sdk，会触发 ``ModuleNotFoundError`` 吗？

**不会**（M8e+ 起）。runtime wheel 的 ``install_requires`` 已声明完整三方依赖
（``pyyaml`` / ``python-pptx`` / ``lxml`` / ``Pillow`` / ``pandas`` / ``openpyxl`` /
``python-docx`` / ``numpy`` / ``networkx`` / ``PyMuPDF`` / 等），``pip install
krow-agent-sdk-runtime`` 会全部自动拉取。

**例外**：``[remote]`` extra（``fastapi`` / ``uvicorn`` / ``websockets`` / ``psutil``）
仅在你启用 ``with_http_gateway()`` 给前端做 SSE 时才需要——按需 ``pip install
krow-agent-sdk-runtime[remote]``。

---

## 5. 离线安装

如果你的客户机不能访问 `api.krow.cn`（防火墙严格），有 2 个备选：

### 方案 A: 在 internal mirror 上托管

1. 由你公司 IT 在能联网的机器上跑 ``krow-sdk-install --api-key $KROW_KEY --download-only``
2. 从下载的 ``*.whl`` 上传到内部 PyPI mirror（如 DevPI）
3. 客户机配 ``pip --index-url <internal-mirror>`` 装

### 方案 B: 申请离线包（企业套餐）

联系 [sales@krow.cn](mailto:sales@krow.cn) 申请 "Air-Gap License" → 获取离线 wheel + license 文件.

---

## 6. 卸载

```bash
pip uninstall krow-agent-sdk-runtime krow-agent-sdk krow-sdk-install
```

注意：runtime wheel 卸载后，你的 plugin 代码（依赖 ``krow_agent_sdk``）仍可
import，但 ``agent.run()`` 会报错，因为没有 runtime.

---

## 7. 安全说明

| 数据 | 落地位置 | 留存 | 谁能访问 |
|---|---|---|---|
| ``KROW_API_KEY`` | 你的环境 / .env | 不上传 | 仅你 |
| 反向代理鉴权 token | 内存 + HTTPS 链路 | 单次请求 | 仅本次 download 进程 |
| 安装审计日志 | Krow Cloud | 90 天 | Krow team（用于支持 + 审计） |
| 你写的 plugin 代码 | 你的机器 | 永久 | 仅你 |
| 你的 agent 跑的内容 | 你的机器 + Krow Cloud LLM 调用记录 | 见 LLM provider 隐私政策 | 你 + LLM provider |

---

## 8. 进一步阅读

- [``quickstart.md``](./quickstart.md)：写 plugin 入门
- [``api-reference.md``](./api-reference.md)：完整 API 手册
- [``advanced-development-guide.md``](./advanced-development-guide.md)：进阶 plugin 设计哲学
- [``roadmap.md``](./roadmap.md)：M9 W1-W4 上线节奏 + pilot 名单
