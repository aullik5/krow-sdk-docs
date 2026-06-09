# Krow Agent SDK Runtime 安装指南（外部开发者）

> **当前状态（2026-05-19 W5 closeout）** ✅：v2 reverse-proxy 协议**全部上线，外部开发者可一行装齐**：
> ```bash
> pip install krow-agent-sdk krow-sdk-install
> export KROW_API_KEY=sk-user-xxxxxxxxxxxxxxxxxxxxx
> krow-sdk-install
> # → 走 prod gateway api.krow.cn/sdk/runtime/pypi/simple/ + files/
> # → 装上 krow-agent-sdk-runtime + 100+ deps
> # → agent.run("...") 真实跑通
> ```
> **变更历史**：
> - 2026-05-23（hotfix 28 closeout）：`krow-agent-sdk==0.8.12.28` + `krow-agent-sdk-runtime==0.8.12.28` 已发布。
>   修复 wheel-only 部署模式下 `ai_search` 等 P0 内置工具未注册的回归（KrowChat 反馈 round 2 / hf24/27 都未根治）。
>   `AgentBuilder().build()` 完成时 `ToolManager` 一定含 `ai_search` / `llm_generate` / `smart_read_document` / `save_image`。
>   反模式 "主仓 dev mode ≠ wheel 部署 mode" 已加入 AGENTS.md §0.1。。
> - 2026-05-19（W5 closeout）：`krow-sdk-install` 首次上 PyPI prod（trusted publisher 配置完成）；三 cookbook real LLM E2E 多次 stable PASSED；W5 修复 5 个 P0 bug（详 [`CHANGELOG_v0.8.12.11.md`](./CHANGELOG_v0.8.12.11.md)）
> - 2026-05-19（W4 closeout）：完整 install 链路 SDK team 实测跑通（4 分 33 秒装 runtime + SDK + 100+ deps）；prod gateway DNS cutover 完成
> - 2026-05-16：v2 reverse-proxy 协议与 Krow Cloud team 锁定
> **设计 v2 reverse-proxy**：
> - 私有 runtime wheel 走 **Krow Cloud 反向代理** 分发：
>   `https://api.krow.cn/sdk/runtime/pypi/{simple,files}/...`
> - Storage：火山引擎 TOS（cn-shanghai，bucket `krow-sdk-runtime`；HK transit + CRR）
> - 鉴权：`KROW_API_KEY` Bearer token，gateway 内套餐 entitlement + rate limit + 计量
> - 客户感知：与装公开 wheel 体感一致，但走 Krow Cloud 一站式鉴权（不需要 GitHub PAT，不需要单独配 index-url）
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

✅ **2026-05-19 W5 起：`krow-sdk-install` 已上 PyPI prod**：
- 验证版本：https://pypi.org/project/krow-sdk-install/0.8.12.11/
- 无需任何 staging / private registry 配置 → `pip install krow-sdk-install` 直接走 PyPI 公网

---

## 2. 装 Runtime Wheel（一行）

```bash
krow-sdk-install --api-key $KROW_API_KEY
```

工作流程（v2 reverse-proxy）：

1. CLI 调 Krow Cloud `GET /sdk/runtime/pypi/simple/krow-agent-sdk-runtime/`
   （Bearer ``$KROW_API_KEY``）拉 PEP 503 index
2. Krow Cloud gateway 鉴权（仅检查 key 是否被撤销 — wheel 下载本身**不计费**，所有套餐均可正常 install；详 §6.1）+ rate limit（10/min simple + 5/min files）
3. CLI 取 manifest 内对应当前 OS / Python 版本的 wheel，调 `GET /sdk/runtime/pypi/files/...` 走 TOS 流式下载
4. CLI 校验 wheel SHA256 与 manifest 一致 → `pip install` 本地

**整个过程不需要你接触 GitHub PAT 或外部 PyPI index**；客户机只与 `api.krow.cn` 一个 endpoint 通信。

### 2.1 升级到最新 runtime

```bash
krow-sdk-install --api-key $KROW_API_KEY --upgrade   # 或 -U
```

`--upgrade` 会向 `pip install` 传 `--upgrade`，确保已装旧版本时强制升级（修复"pip 报
already satisfied 拒绝升级"的体验问题）。CLI 选 wheel 时**总是**在当前 host 兼容的所有
版本里按 PEP 440 选**最新**（不再受 index HTML 顺序影响）。

本地安装损坏 / 想强制重装同版本时加 `--force-reinstall`（隐含 `--upgrade` 行为）：

```bash
krow-sdk-install --api-key $KROW_API_KEY --force-reinstall
```

### 2.2 安装指定版本

```bash
krow-sdk-install --api-key $KROW_API_KEY --version 0.8.12.60   # 精确版本
krow-sdk-install --api-key $KROW_API_KEY --version 0.8.12      # 段前缀：命中 0.8.12.* 里最新
```

`--version` 支持**精确**或**段前缀**匹配（按 `.` 分段）：`0.8.12` 命中 `0.8.12.60`，但
`0.8.1` **不会**误命中 `0.8.12.*`（段比对 `1` ≠ `12`）。指定版本在当前 host 兼容范围内
不存在时 fail-loud（列出可用版本清单）。

### 2.2.1 自定义 Cloud endpoint（staging / 私有部署）

99% 用户**不用看**这一节 — 默认走 `https://api.krow.cn` 就 OK。

需要切走时（pilot / staging 联调 / 私有化部署）调 `--base-url` flag 或 `KROW_BASE_URL` env var：

```bash
# 走 staging gateway（pk-pilot- key 必须配 staging endpoint）
krow-sdk-install --api-key pk-pilot-xxx --base-url https://api-staging.krow.cn

# 私有化部署
KROW_BASE_URL=https://krow-gateway.acme.internal krow-sdk-install --api-key sk-tenant-xxx
```

> SDK 端 `AgentBuilder.with_base_url("...")` 与本 flag 一一对应；保持一致才能让 `krow-sdk-install` + `agent.run()` 两端走同一个 cloud endpoint。详 [`api-reference.md` §2.4 `with_base_url`](./api-reference.md#22-工厂方法)。

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

## 3.5 Aux model 注册（provider-registration）

除 chat / reasoning 外，agent 还会用到 4 个**辅助（aux）能力**：

| aux 类别 | 用途 | 真实运行时消费者（SSOT） |
| --- | --- | --- |
| `vision` | 视觉质检 / 截图理解（PPT、网页 grounding） | `modules/agent/visual/grounding_service.py` |
| `image_gen` | 文生图 | `modules/ai/krow/image.py::resolve_default_image_gen_model` |
| `image_edit` | 图像编辑 | `modules/ai/krow/image.py::resolve_default_image_edit_model` |
| `text_encoder` | 文本向量化（知识库 / 检索） | `modules/ai/krow/embedding.py` |

**关键事实**：aux 4 类的真实消费者各有独立的模型解析器，**不**走
`AIProviderManager` 的 category 注册表。因此 headless 场景**无需**为 aux 单独注册
provider，只要把模型 id 喂给对应解析器即可。三种等价注入方式（优先级高→低）：

**① SDK builder（推荐，指定即采用）**

```python
agent = (
    AgentBuilder()
    .with_krow_api_key(os.environ["KROW_API_KEY"])
    .with_project_root(workspace)
    .with_vision_model("qwen2.5-vl-72b-instruct")   # 桥接到 grounding_service
    .with_image_gen_model("seedream-4.0")            # 桥接到 image 解析器
    .with_text_encoder_model("bge-m3")               # 桥接到 embedding 解析器
    .build()
)
```

`build()` 会把每个 `.with_<aux>_model()` 桥接到对应消费者的进程级 override
（最高优先级）。即使底层 `AIProviderManager` 为空（headless 常态）也能生效——
不再像旧版本（≤ 0.8.x）那样抛 `ExplicitAuxModelNotApplicableError`。

**② 环境变量（pod-manager / 不改代码场景，与 ① 等价）**

```bash
export KROW_VISION_MODEL=qwen2.5-vl-72b-instruct
export KROW_IMAGE_GEN_MODEL=seedream-4.0
export KROW_IMAGE_EDIT_MODEL=seededit-3.0
export KROW_TEXT_ENCODER_MODEL=bge-m3
```

**③ 自带完整 `AIProviderManager`（桌面 IDE 路径消费者，如 context_enhancer 读 vision provider）**

```python
AgentBuilder().with_ai_manager(my_ai_manager).build()
```

> **`KROW_AI_CONFIG_OVERLAY_PATH` 的边界**：该 env 仅被 headless server 主程序
> （`app/headless_main.py::_apply_ai_overlay`）消费，用于覆盖 `ai.providers[category]`，
> **不**被 `AgentBuilder.build()` SDK 路径读取。SDK 嵌入式接入请用上面 ①/② 注入 aux
> 模型，不要依赖 overlay。

---

## 4. 常见问题

### Q1: 跑 ``krow-sdk-install`` 报 ``❌ Krow API key 校验失败 (HTTP 401)``

**原因**：API key 错 / 被撤销 / 旧版 SDK 不识别新格式.

**修法**：

1. **首先确认 SDK 版本**（2026-05-20 起 Krow Dashboard 升级到 **48 位 user key**
   格式 `sk-user-` + 40 字符）：
   ```bash
   pip install -U "krow-sdk-install>=0.8.12.12" "krow-agent-sdk>=0.8.12.12"
   ```
   - `krow-sdk-install` 0.8.12.12 起：用 PEP 425 wheel matching，48 位 key 长度
     不影响 install 路径（CLI 端只透传 Bearer token，不做长度校验）
   - `krow-agent-sdk` 0.8.12.12 起：`API_KEY_PATTERN` 正则
     `^(sk-[A-Za-z0-9_\-]{17,}|pk-pilot-[A-Za-z0-9_\-]{17,})$` 接受 ≥ 20 字符的
     `sk-` / `pk-pilot-` 前缀 key，48 位 user key 完全兼容

2. 到 [https://krow.cn/dashboard](https://krow.cn/dashboard) **重新生成** API key
   （旧 dashboard 生成的短格式 key 在 cloud 端 sk auth 升级后已失效；
   2026-05-20 起请用 dashboard 生成的 48 位 user key）

3. 检查 key 拼写：注意首尾空格 / 引号 / 截断（`sk-user-` 前缀 + 40 字符 = 48 字符整）

4. 如以上都查过仍 401：联系 [support@krow.cn](mailto:support@krow.cn) 带上响应
   header 里的 `X-Request-Id`

### Q2: 跑 ``krow-sdk-install`` 报 ``402 InsufficientBalance``

**原因**：账户 CP 余额不足。Cloud team 2026-05-19 W4 release 起，**install 阶段不计费**，
所有套餐（含 Free）都可正常装 `krow-agent-sdk-runtime`；但**LLM 调用按 CP 计费**，
首次调 LLM 时若余额（`member_cp + wallet_cp`）为 0 会返回 402.

**修法**：

- 充值：访问 [https://krow.cn/wallet](https://krow.cn/wallet) 加充 wallet CP（永久有效）
- 升级会员：访问 [https://krow.cn/membership](https://krow.cn/membership) 购买 Basic / Pro / Premium 月度套餐（详 §6.2 套餐表）
- 联系 [sales@krow.cn](mailto:sales@krow.cn) 申请 dev/test 套餐扩额

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

### Q3.5: 装时报 ``❌ 当前 host 没匹配的 runtime wheel`` (PEP 425 mismatch)

**原因**：你的 host platform tag 不在 runtime wheel matrix 内，或 `krow-sdk-install`
< 0.8.12.12 的旧版本因 bug 把 macOS / Linux 兼容 wheel 也误判为 mismatch（见
[CHANGELOG_v0.8.12.12](./CHANGELOG_v0.8.12.12.md)）。

**先升级 installer**（**强烈推荐**）：

```bash
pip install -U krow-sdk-install   # 必须 ≥ 0.8.12.12
krow-sdk-install --api-key $KROW_API_KEY
```

0.8.12.12+ 用 `packaging.tags.sys_tags()` 做 PEP 425 兼容性匹配（与 `pip` 行为
一致），自动识别：

- macOS arm64 / x86_64 ↔ `universal2` wheel
- Linux x86_64 ↔ `manylinux_*_x86_64` / `linux_x86_64` wheel
- 任意 Python ABI ↔ `abi3` 通用 wheel
- macOS deployment target 向后兼容（10.13 wheel 可装 14.0 系统）

**升级后仍 mismatch**：runtime 当前矩阵是 **3 OS（Linux / macOS / Windows）× 3
Python（3.11 / 3.12 / 3.13）= 9 wheels**。其他平台（aarch64-linux / FreeBSD /
Python 3.10 ↓）暂不支持，可：

1. **切到支持的 Python**（推荐）：`pyenv install 3.13` 或装 conda env 锁 3.13
2. **联系 Krow 扩矩阵**：mailto:support@krow.cn 申请你的目标平台（注明 OS /
   架构 / Python 版本 / 业务场景）
3. **手动挑 wheel**：`krow-sdk-install --api-key $KROW_API_KEY --download-only`
   拿到 9 wheels 后，自行选最接近的手 `pip install`

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

## 8. Public Beta 时间表（**任何 Krow Cloud 用户即可装**）

**最新决策（2026-05-17）**：跳过封闭 Pilot 阶段，**直接公开**。
任何 Krow Cloud 注册用户拿到 ``KROW_API_KEY`` 即可装 runtime — **无需邀请、无需审核**。

**当前状态**：runtime 已与 Krow Cloud team 签 v2 协议（2026-05-16），W1 测试 wheel +
W3 install CLI 子包 + W4 真实 LLM E2E 测试已交付（[`roadmap.md`](./roadmap.md) M9 W1+W3+W4）。
W2 staging gateway + IAM 凭据由 Cloud team 在 2026-05-23 周交付，W3 联调通过即开 Public Beta。

### 8.1 时间表

| 日期 | 阶段 | 你需要做什么 |
|---|---|---|
| **2026-05-23 周** | W2：Cloud team 交付 staging gateway + IAM；SDK team 真实 cython 编译 + 上传 9 wheels 到 TOS | 等通知（关注 [aullik5/krow-sdk-docs](https://github.com/aullik5/krow-sdk-docs) `roadmap.md` 更新）|
| **2026-05-30 周** | W3：staging 联调全过；切到 prod gateway | 同上 |
| **2026-06-06** | **Public Beta 开放** — 所有持 ``KROW_API_KEY`` 的开发者直接装 | 跑 ``krow-sdk-install --api-key $KROW_API_KEY``（详 §3 上面）|
| **2026-06-15** | GA — ``pip install krow-agent-sdk[runtime-installer]`` 一键 | 升级到 ``[runtime-installer]`` extras |

### 8.2 套餐与 CP 计费（W4 cloud-team-reply 2026-05-19 起）

**重要**：W4 起 install 阶段**不计费**，所有套餐（含 Free）都可正常装 runtime。
计费维度从"次/天"改为**统一 CP**（Krow Cloud 全平台共享一套 wallet）。

| 套餐 | 月度会员 CP（`member_cp`） | 说明 |
|---|---|---|
| Free | 0 | 可正常装 SDK Runtime；LLM 调用首次会撞 `402 InsufficientBalance` 提示充值或购买会员 |
| Basic | 500,000 | 按购买日历月重置 |
| Pro | 2,000,000 | 按购买日历月重置 |
| Premium | 10,000,000 | 按购买日历月重置 |

#### 统一 CP 抽象

```
total_cp = member_cp + wallet_cp
```

- **`member_cp`**：会员月度阅读额度，每月按购买日历重置；非会员该项为 0
- **`wallet_cp`**：钱包余额（充值 / 邀请奖励 / 活动赠送），永久有效，不重置

扣费顺序：先扣 `member_cp`，用尽后自动转 `wallet_cp`，用户无感（详 [w4-cloud-team-reply.md §2](https://github.com/aullik5/krow/blob/main/docs/sdk/w4-cloud-team-reply.md#%C2%A72-%E4%BC%9A%E5%91%98%E4%BD%93%E7%B3%BB%E4%B8%8E%E8%AE%A1%E8%B4%B9)）。

升级会员：[krow.cn/membership](https://krow.cn/membership) 或充值钱包：[krow.cn/wallet](https://krow.cn/wallet) 或联系 [sales@krow.cn](mailto:sales@krow.cn)。

### 8.3 W2-W3 期间想提前体验？

W2-W3 期间（2026-05-23 ~ 2026-06-06）staging endpoint 上线但**仅**接 SDK team 联调用 key（前缀 ``pk-pilot-``）。
你**仍然**可以：

- ✅ 装公开 ``krow-agent-sdk`` 写 plugin 协议代码（``ToolPlugin`` / ``ACTPlugin``）
- ✅ 用 ``LLMReplayStore`` 做 record/replay 单元测试（无需 runtime）
- ✅ 阅读 [``advanced-development-guide.md``](./advanced-development-guide.md) 提前学最佳实践
- ✅ 加入 [krow.cn](https://krow.cn) 邮件订阅，Public Beta 上线第一时间收到通知

### 8.4 早期问题反馈

Public Beta 期遇问题？

- 公开渠道：[GitHub Issues](https://github.com/aullik5/krow-sdk-docs/issues) / [Discussions](https://github.com/aullik5/krow-sdk-docs/discussions)
- 私邮：[support@krow.cn](mailto:support@krow.cn)（24h 内应答）
- 错误信息**强烈建议**贴黄金模板原文（含 ``X-Request-Id``，便于后端追踪）

---

## 9. 进一步阅读

- [``quickstart.md``](./quickstart.md)：写 plugin 入门
- [``api-reference.md``](./api-reference.md)：完整 API 手册
- [``advanced-development-guide.md``](./advanced-development-guide.md)：进阶 plugin 设计哲学
- [``roadmap.md``](./roadmap.md)：M9 W1-W4 上线节奏
