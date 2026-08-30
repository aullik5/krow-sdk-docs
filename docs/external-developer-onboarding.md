# 外部开发者 Onboarding（第 1 周）

> 给外部团队（科研 / 工业 / 业务）的"我刚收到 Krow SDK 邀请，怎么开工？"指南.
> 以"周一上班 → 周五能 demo"为节奏，约 30 分钟读完，5 天动手.
> **Krow Team 承诺**：你卡 1 天没进展 → 发邮件到 [support@krow.cn](mailto:support@krow.cn) 我们 24 小时内响应.

---

## Day 1: 装机 + Hello, Krow（30 分钟）

### Step 1: 拿到 API key

1. 你应该已收到 Krow Team 的邀请邮件，含一个 `sk-...` 前缀的 API key
2. 充值至少 **¥1**（够你跑 1 周 hello-world 实验，约 50-100 个 LLM 调用）
3. （可选）登录 [krow.cn](https://krow.cn) 客户端确认 key 状态 + 余额

### Step 2: 装 SDK（公开包 + 私有 runtime）

> **当前发布状态**（2026-05-19 W5 closeout）：✅ **PyPI 三件套全齐 + 一行装齐**：
> - ✅ `krow-agent-sdk==0.8.12.28` 已发 PyPI 主站（hotfix 28 — entry-agnostic `ai_search` 注册修复）
> - ✅ `krow-sdk-install==0.8.12.11` 已发 PyPI 主站（W5 首发，CLI 自身无 hotfix 28 影响）
> - ✅ `krow-agent-sdk-runtime==0.8.12.28` 在 prod TOS（hotfix 28 closeout，9 wheel matrix + CI P0 tool registration smoke 守门）
> - ✅ 三 cookbook real LLM E2E **多次 stable PASSED**（W5 user-value oriented + 5 P0 bug 治本）
> 详见 [`CHANGELOG_v0.8.12.11.md`](./CHANGELOG_v0.8.12.11.md) + [`v0.8.12.11-readiness-status.md`](./v0.8.12.11-readiness-status.md)。

#### 推荐：一行 PyPI 装机（公开 SDK + install CLI）

```bash
pip install krow-agent-sdk krow-sdk-install
# 或带 extras：
pip install "krow-agent-sdk[office,visual,reasoning,remote]"
# 推理洞察管线全能力（因果发现/估计/反事实 + 贝叶斯网概率推理）：
pip install "krow-agent-sdk[reasoning]"
# 全装：
pip install "krow-agent-sdk[all]"
```

#### Collaborator 模式：monorepo 直装（仅 Krow team collaborator）

```bash
git clone https://github.com/aullik5/krow.git
cd krow
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # macOS / Linux
pip install -e ".[sdk]"
```

#### 装私有 runtime wheel（一行）

```bash
# 用你的 KROW_API_KEY 通过 Krow Cloud 反向代理拉 wheel
export KROW_API_KEY=sk-user-xxxxxxxxxxxxxxxxxxxxx
krow-sdk-install
# → 拉 prod gateway simple index → 选 host-compatible wheel → sha256 校验 → pip install
# → 装上 runtime + 100+ 依赖（reportlab/pdfplumber/matplotlib/pymupdf 等）
# → agent.run("...") 真实跑通
# 详细机制见 runtime-install.md（v2 reverse-proxy）
```

### Step 3: 跑通 Hello, Krow

```python
# hello.py
import os
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key(os.environ["KROW_API_KEY"])
    .with_project_root("./workspace")        # agent 写文件的边界
    # 模型选择（可选，6 类按需）：
    # .with_chat_model("qwen3.6-plus")        # 对话 / 通用 / 代码
    # .with_reasoning_model("deepseek-v4-pro")  # 深度推理 / CoT
    # .with_vision_model("qwen2.5-vl-72b-instruct")  # VLM
    # .with_image_gen_model("qwen-image")     # 图像生成
    # .with_image_edit_model("qwen-image-edit")  # 图像编辑
    # .with_text_encoder_model("text-embedding-v2")  # embedding
    .build()
)

result = agent.run("帮我写一个 Python 函数计算斐波那契数")
print("=" * 50)
print(result.final_output)         # ← 注意是 final_output 不是 summary
print("=" * 50)
agent.shutdown()
```

```bash
# Linux / macOS
export KROW_API_KEY="sk-user-..."
python hello.py

# Windows PowerShell
$env:KROW_API_KEY="sk-user-..."
python hello.py
```

**预期**：~30 秒后看到一个实际能跑的 Python 斐波那契函数. 第一次跑因为初始化 19 内置 ACT + 120+ tool 会花 60-90 秒，**后续秒级**.

### Step 4: 故障排查（如果上一步失败）

| 错误 | 修法 |
|---|---|
| `MissingKrowAPIKeyError` | `KROW_API_KEY` 环境变量没设；用 `os.environ` 设 |
| `InvalidKrowAPIKeyError` | API key 格式错（必须 `sk-` 前缀 + ≥20 字符） |
| `KrowQuotaExceededError` (HTTP 402) | 余额不足；去 krow 客户端充值 |
| `LLMProviderError` (401) | API key 失效 / 已被禁用；重新创建 |
| `ModuleNotFoundError: 'modules'` | runtime wheel 没装；跑 `krow-sdk-install --api-key $KEY` |
| `第一次 build() 慢 60-90s` | **正常**，不是 bug；后续秒级 |

更多 troubleshooting 见 [`README.md`](./README.md) §8.

### 今日交付

- [x] 装好 SDK + runtime
- [x] 跑通 hello.py 看到 LLM 输出
- [x] 知道 `result.final_output` 是顶层输出字段（不是 `result.summary`）

**下一步** → Day 2：写你的第一个 ACT plugin.

---

## Day 2: 写你的第一个 ACT Plugin（半天）

ACT (Agent Capability Topic) 是 Krow 的"领域能力包"概念. 你给 agent 一个 `research_paper` ACT，agent 就知道遇到论文任务该怎么调工具.

### Step 1: 起 plugin 骨架

```bash
mkdir -p my_research_pack/acts/research_paper
cd my_research_pack
```

`my_research_pack/__init__.py`：

```python
from pathlib import Path
from krow_agent_sdk.protocols import ACTPlugin


class ResearchPaperReader:
    """让 agent 学会"读论文 → 抽四要素 → 落 evidence" 的 ACT plugin.

    协议 SSOT: krow_agent_sdk.protocols.ACTPlugin
        - plugin_id (property, str) — 双段 "<org>.<plugin_name>"
        - act_name (property, str) — ACT 名称
        - get_act_root() -> Path — ACT 资源根目录
        - get_act_file_path() -> Path — 主 ACT markdown 文件 (ext_<name>.md)
        - get_tool_names() -> list[str] — 该 ACT 启用的工具白名单
    """

    plugin_id = "acme.research_paper"  # 双段 "<org>.<plugin_name>"，正则
                                       # ^[a-z0-9_-]{3,20}\.[a-z0-9_]{3,30}$
    act_name = "research_paper"        # 通常等于 plugin_id 的第二段

    def get_act_root(self) -> Path:
        return Path(__file__).parent / "acts" / "research_paper"

    def get_act_file_path(self) -> Path:
        return self.get_act_root() / "ext_research_paper.md"

    def get_tool_names(self) -> list[str]:
        return [
            "read_file",
            "read_document",
            "search_files",
            "ai_search",
        ]


def get_act_plugin() -> ACTPlugin:
    return ResearchPaperReader()
```

### Step 2: 写 ACT 主文件（YAML frontmatter + 扩展指南二合一）

`my_research_pack/acts/research_paper/ext_research_paper.md`：

````markdown
---
name: research_paper
display_name: 科研论文阅读
description: |
  当用户要"读论文 / 抽取作者 / 总结实验结果 / 找引用关系"时进入此 ACT.
  本 ACT 内 Agent 会重点使用 native_fileops + ai_search 组合.
when_to_enter:
  - "用户提到 paper / 论文 / arxiv / 学术 / 文献"
  - "用户上传了 .pdf 文件且文件名/路径中含 paper/article/journal"
tools:
  - read_file
  - read_document
  - search_files
  - ai_search
priority: 10
---

# 科研论文阅读 ACT — 扩展指南
（ACT 主体内容紧接 frontmatter，agent 会读全文）
````

如果倾向把 yaml 与 markdown 分开（兼容 monorepo `__act__.yaml` 风格），把 `get_act_file_path()` 仍指向 `ext_research_paper.md`，并在 `acts/research_paper/__act__.yaml` 单独维护 frontmatter（SDK 加载时优先读 `ext_*.md` 主体；frontmatter 缺失 fail-loud）。

`my_research_pack/acts/research_paper/extended.md`（自然语言扩展指南，agent 会读）：

```markdown
# 科研论文阅读 ACT — 扩展指南

## 推荐工作流

1. 调 `read_document` 把 PDF 抽成 markdown
2. 用 ReACT 引擎天然多步推理拆解出"作者 / 数据集 / 方法 / 结论"四要素
   （无需特殊"chain-of-thought"工具）
3. 用 `save_note` 落盘 evidence 后再做 cross-paper 综合

## 反模式

- ❌ 直接调 `read_file` 处理 PDF（不会自动 OCR）
- ❌ 跳过 evidence 直接给综合结论（不可追溯）
```

### Step 3: 注册到 agent

```python
# hello_with_plugin.py
import os
from krow_agent_sdk import AgentBuilder
from my_research_pack import ResearchPaperReader

agent = (
    AgentBuilder()
    .with_krow_api_key(os.environ["KROW_API_KEY"])
    .with_project_root("./workspace")
    .with_act_plugin(ResearchPaperReader())   # ← 加 plugin
    .build()
)

result = agent.run("帮我读 ./papers/transformer.pdf 抽出作者和方法")
print(result.final_output)
agent.shutdown()
```

> 完整 ACT plugin 范例（含 hint / gate / event listener / observability 5 类 plugin）→ [`quickstart.md`](./quickstart.md) §3-§5.

### Step 4：ACT 加载自检（5 分钟兜底，强烈推荐）

很多 P0 故障来自"ACT 写了但 SDK 没解析到工具" —— LLM 凭工具名瞎填参数 / 跳步骤 /
顺序错。在跑 agent 前先**用 1 个文件兜底**：

```python
# tests/test_my_act_loading.py（每个 plugin 都写一份）
def test_my_act_doc_coverage():
    """反退化：保证 ACT 被 SDK 正确解析。"""
    from modules.agent.act.act_hierarchy import get_hierarchy_loader
    from modules.agent.act.act_loader import get_act_loader

    # 触发 plugin 加载（用你 builder 的代码）
    from my_plugin import build_my_agent
    agent = build_my_agent()
    try:
        loader = get_hierarchy_loader()
        # 你的 ACT name（ext_ 前缀）
        ext_name = "ext_my_act"
        extended = loader.load_extended(ext_name)
        assert extended is not None, f"{ext_name} 未注册 / 未加载"

        # 覆盖率：声明的工具数 vs 解析出的工具数
        declared = ["my_tool_a", "my_tool_b", "my_tool_c"]
        parsed = set(extended.all_tools.keys())
        coverage = sum(1 for t in declared if t in parsed) / len(declared)
        assert coverage >= 0.8, (
            f"工具覆盖率 {coverage:.0%} < 80%；声明 {declared}；"
            f"已解析 {sorted(parsed)}；缺 {[t for t in declared if t not in parsed]}"
        )

        # Phase-2 prompt 完整性：每个工具应能取到 ≥ 100 字符的文档
        for t in declared:
            doc = extended.get_tool_doc(t)
            assert doc and len(doc) > 100, (
                f"工具 {t} 文档过短 ({len(doc or '')}b)；"
                f"检查 ACT extended.md 是否用了 §4.6 推荐的写法 A 或 B"
            )
    finally:
        agent.shutdown()
```

跑 `pytest tests/test_my_act_loading.py -v`。

| 失败信号 | 检查方向 |
|---|---|
| `extended is None` | ACT 未注册（检查 `with_act_plugin()` 调用是否在 build 链里） |
| `工具覆盖率 < 80%` | extended.md 用了 SDK 不识别的 heading 风格（用中文章节名 / 编号列表）→ 改成 §4.6 写法 A 或 B |
| `工具 X 文档过短` | 工具未在 `ToolPlugin.get_tools()` 写 `input_schema`（SDK 自动文档生成失败）→ 补全 schema |

### 今日交付

- [x] 写出第一个 ACT plugin（自己起 `<org>.<name>` 双段 ID）
- [x] 知道 ACT yaml + extended.md 双层结构
- [x] 知道 ACT 内推荐用真实存在的 tool（不要捏造 `reasoning_chain_of_thought` 这种）
- [x] **跑通 ACT 加载自检 test**（防 P0：写完 ACT 但 SDK 解析不到工具）

**下一步** → Day 3：加 Tool / Hint / Gate plugin（按需做你领域的定制扩展）.

---

## Day 3: 加 Tool Plugin（半天）

Tool Plugin 是给 agent 加新工具. 比如你要让 agent 调你公司的 CAD API.

### 最小可跑示例

> **协议 SSOT**：`krow_agent_sdk.protocols.ToolPlugin` —— 只需 `plugin_id` (property) + `get_tools() -> list[ToolSpec]`。每个 `ToolSpec` 必含 `name / description / input_schema / handler`，可选 `category / direct_output / user_visible / output_schema / complexity / dependencies`。**不再分 `get_tool_definitions / execute_tool` 两步**——`handler` 是 Callable，ToolManager 调用工具时直接调它。

```python
# my_cad_pack/__init__.py
from typing import Any
from krow_agent_sdk.protocols import ToolPlugin


def _cad_query_part(part_id: str) -> dict:
    """工具 handler：参数走 keyword-only；返回值会作为工具输出回到 agent。"""
    # 这里调你公司真实 CAD API
    return {
        "part_id": part_id,
        "name": "Bracket-2026-A1",
        "weight_kg": 0.42,
        "material": "AL-6061-T6",
    }


class CADQueryPlugin:
    plugin_id = "acme.cad_query"

    def get_tools(self) -> list[dict]:
        return [{
            "name": "acme_cad_query_part",  # 推荐前缀 "<plugin_name>_" 防撞 native
            "description": "查询 CAD 系统里某个零件的元数据。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "part_id": {"type": "string", "description": "零件 ID"},
                },
                "required": ["part_id"],
            },
            "handler": _cad_query_part,        # ← 直接 Callable
            "category": "custom",
            "user_visible": True,
        }]


def get_tool_plugin() -> ToolPlugin:
    return CADQueryPlugin()
```

```python
agent = (
    AgentBuilder()
    .with_krow_api_key(...)
    .with_project_root("./workspace")
    .with_tool_plugin(CADQueryPlugin())
    .build()
)
result = agent.run("查询零件 P-1234 的材料和重量")
```

### Day 3 + Day 4 还能加这些 plugin（按需选）

| Plugin | 用途 | 详细文档 |
|---|---|---|
| `HintPlugin` | 给 agent 加领域专家提示（"科研论文要先看 abstract 再读 method"）| [`quickstart.md`](./quickstart.md) §4.2 |
| `GatePlugin` | 给 agent 加输出守门（"工业图纸 BOM 必须含 material 字段"）| [`quickstart.md`](./quickstart.md) §4.3 |
| `EventListenerPlugin` | 监听 agent 内部事件（debug / 监控）| [`quickstart.md`](./quickstart.md) §4.4 |
| `ObservabilityPlugin` | 接入你的 Datadog / Prometheus | [`quickstart.md`](./quickstart.md) §4.5 |
| `MCPServerPlugin` | 接入 MCP 协议（远程工具）| [`api-reference.md`](./api-reference.md) §5.7 + [`quickstart.md`](./quickstart.md) §4 |
| `VisualAdapter` | 视觉 QA（图纸 / 报告 layout 校验）| [`api-reference.md`](./api-reference.md) §5.10 + [`quickstart.md`](./quickstart.md) §7.1 |

### 今日交付

- [x] 写出至少 1 个 Tool plugin 接通你领域的真实 API
- [x] （可选）写出 Hint / Gate plugin 中的 1 个

**下一步** → Day 5：写离线单元测试（不烧 token）.

---

## Day 5: 用 LLMReplayStore 写离线单元测试（半天）

外部团队的 plugin 写完后，要进自己的 CI. 但每跑一次测试烧 LLM token 不可持续 — Krow 提供 **LLMReplayStore** 让你录制一次后无限重放.

### 录制 → 重放 范式

```python
# tests/test_my_plugin.py
import pytest
from pathlib import Path
from krow_agent_sdk import AgentBuilder
from krow_agent_sdk.replay import LLMReplayStore
from my_research_pack import ResearchPaperReader


@pytest.fixture
def replay_store(tmp_path):
    """每个测试一个独立 replay 文件夹."""
    return LLMReplayStore(store_dir=tmp_path / "llm_replay")


def test_research_paper_plugin_with_real_llm_recording(replay_store):
    """第一次跑：真实 LLM + 录制（CI 不跑此条；本地 dev 时跑 1 次）."""
    pytest.skip("仅本地 record mode 跑")

    agent = (
        AgentBuilder()
        .with_krow_api_key(os.environ["KROW_API_KEY"])
        .with_project_root("./workspace")
        .with_act_plugin(ResearchPaperReader())
        .with_replay_store(replay_store, mode="record")  # ← 录制
        .build()
    )
    result = agent.run("读 ./papers/transformer.pdf")
    assert result.final_output


def test_research_paper_plugin_replay(replay_store):
    """CI 跑此条：用之前录的 LLM 输出重放，零网络 / 零 token."""
    # 先把 record mode 录制的 replay 文件 copy 到 tmp_path / "llm_replay"

    agent = (
        AgentBuilder()
        .with_krow_api_key("sk-user-fake-for-replay-mode")  # 任何合法 key 都行
        .with_project_root("./workspace")
        .with_act_plugin(ResearchPaperReader())
        .with_replay_store(replay_store, mode="replay")    # ← 重放
        .build()
    )
    result = agent.run("读 ./papers/transformer.pdf")

    # Multi-dim 断言（详 quickstart §5.4）
    assert result.success
    assert "作者" in result.final_output or "author" in result.final_output.lower()
    assert len(result.final_output) > 100  # 非空有意义输出
```

### 把测试纳入 CI

```yaml
# .github/workflows/my-team-ci.yml
name: my-team CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      - run: |
          pip install krow-agent-sdk
          pip install -e .
          pytest tests/ -v -m "not record_mode"  # 仅跑 replay 测试
```

### 完整 record/replay 文档

[`quickstart.md`](./quickstart.md) §5.5 + [`api-reference.md`](./api-reference.md) §7（含 `LLMReplayStore` 全部 mode / API 表 + `wrap_provider_manager_with_replay` 手动 wrap 路径）。

### 今日交付

- [x] 学会 record + replay 两阶段范式
- [x] 自己 plugin 进 CI 不烧 token
- [x] Multi-dim 断言（不仅看 success，看输出含特定关键词）

---

## Week 2: 进阶（按需选）

到 Week 1 末你已经能：装机 → 写第一个 ACT plugin → 加 Tool plugin → 离线单测 进 CI. 第二周可以挑重点深入：

### 路径 A：性能调优

- **BudgetController**：自定义"每个 macro step 最多 N 个 LLM 调用 / M 秒"
- **自定义 Hint**：给 agent 加领域专家直觉降低 LLM 调用次数
- **自动 adapt / replan**：当 agent 卡住时让它换思路（不用你写 if/else）

→ [`advanced-development-guide.md`](./advanced-development-guide.md) §6 测试 + §7 进阶基础设施 + [`api-reference.md`](./api-reference.md) §4.2 BudgetSpec / §5.3 HintPlugin

### 路径 B：视觉 QA（工业 / 科研团队特别有用）

- **VisualAdapter**：把 agent 输出（CAD 图 / 论文 layout / 流程图）丢给视觉模型做合规校验
- **verify_fix 协议**：视觉模型发现问题 → agent 自动修

→ [`api-reference.md`](./api-reference.md) §5.10 + [`quickstart.md`](./quickstart.md) §4.5 / §7.1

### 路径 C：数据层接入

- **DomainPackPlugin**：自定义实体抽取规则（科研：抽 author / venue / dataset；工业：抽 part / supplier / certification）
- **wiki_compiler**：让 agent 把多文档抽出的 evidence 自动汇总成 wiki

→ [`api-reference.md`](./api-reference.md) §5.9 DomainPackPlugin + §11 数据 facade

### 路径 D：MCP 协议（接入第三方 MCP server）

- 你公司有 MCP server？用 `MCPServerPlugin` form-A/B/C 三种形态接入
- 完整范例 → [`api-reference.md`](./api-reference.md) §5.7 + [`quickstart.md`](./quickstart.md) §4 (MCP 三形态简表)

### 路径 E：自定义 Cloud endpoint（staging / 私有部署 / 本地 mock）

99% 用户**不用看**这一节 — 默认走 `https://api.krow.cn` 就 OK。

需要切走时（pilot 联调 / 私有化部署 / 自动化测试）调 `with_base_url(url)`：

```python
agent = (
    AgentBuilder()
    .with_krow_api_key("pk-pilot-xxx")               # SDK pilot key 仅 staging 可用
    .with_base_url("https://api-staging.krow.cn")    # 切到 staging gateway
    .with_project_root("/data/x")
    .build()
)
```

格式校验（违反任一抛 `InvalidKrowBaseURLError`）：必须 `https://` 前缀；禁尾斜杠；禁含 path 段（如 `/v1`）；禁空字符串。

完整说明：[`api-reference.md` §2.4 `with_base_url`](./api-reference.md#22-工厂方法) + [`quickstart.md` §6.1](./quickstart.md#61-自定义-cloud-endpointstaging--私有部署--自动化测试)。

### 路径 F：让决策脑对你的任务"看得见、叫得醒"（垂直场景团队几乎都需要）

- **SituationContributor**：把"离交付还差多少"写进元认知工作站 —— 不接这一层，决策脑对你的任务族是**全盲**的，停滞 / 恶化一条都判不出来
- **WakeTrigger / DecisionClassifier**：领域专属的"该惊动了"与信用结算
- **控制反射 / StepActuator**：知道之后**动手**那一格（只接观测层 = 有传感器没执行器）
- 先读能力边界三档（可见 ≠ 能止损 ≠ 可修复），免得把"缺口被看见了"验收成"产物被修好了"

→ [`advanced-development-guide.md`](./advanced-development-guide.md) §10（含 §10.10 能力边界 / §10.11 决策请求块装了什么）+ [`api-reference.md`](./api-reference.md) §9.6 / §9.7 + 可跑范例 `examples/cookbook/litsci-metacog/`（零 LLM）

---

## 常见问题（Troubleshooting 索引）

### A. 装机问题

| 现象 | 常见原因 | 修法 |
|---|---|---|
| `pip install` 报 Python 版本不兼容 | SDK 要求 Python ≥ 3.11 | `python --version` 确认；用 pyenv / conda 切版本 |
| `krow-sdk-install` 报 401 | API key 无效 / 被禁用 | 重新创建 key |
| `krow-sdk-install` 报 GitHub Packages 拉不到 | 短期 PAT 签发服务挂 / 网络问题 | 等 5 分钟重试；持续失败发邮件 [support@krow.cn](mailto:support@krow.cn) |
| Windows 装机 `pip install --upgrade pip` 失败 | Windows venv pip 自我升级 bug | 用 `python -m pip install --upgrade pip` |
| 装完 import 报 `UnicodeEncodeError: 'charmap' codec` | Windows 默认 cp1252 stdout | 设 `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` |

### B. 运行时问题

| 现象 | 常见原因 | 修法 |
|---|---|---|
| 第一次 `build()` 慢 60-90s | 正常 lazy-load | 不是 bug；后续秒级 |
| `agent.run()` 卡住几分钟不动 | LLM 后端慢 / 网络 / agent 长任务 | `BudgetController` 默认 5min timeout 会触发 |
| `ModuleNotFoundError: 'modules'` | 仅装公开 SDK 没装 runtime | `krow-sdk-install` |
| `NotImplementedError: vendor stub` | 同上 | 同上 |
| Plugin 没被加载 | `plugin_id` 格式错（必须双段 `<org>.<name>`） | 检查 `_plugin_id_validator` 正则 |

### C. 计费 / 配额问题

| 现象 | 常见原因 | 修法 |
|---|---|---|
| `KrowQuotaExceededError` (HTTP 402) | 余额不足 | krow 客户端充值 |
| `LLMProviderError` (401) | API key 失效 / `pk-pilot-` key 调了 prod endpoint | 重新创建 sk-；或调 `with_base_url("https://api-staging.krow.cn")` |
| `InvalidKrowBaseURLError` | `with_base_url(url)` 格式不符 | URL 必须 `https://...`；不能尾斜杠；不能含 `/v1` 等 path 段 |
| LLM 调用很慢但没报错 | 速率限制 / 后端排队 | 看 krow 客户端的"配额状态" |
| 余额一夜被烧光 | plugin 死循环调 LLM / `BudgetController` 没设硬上限 | 加 `BudgetController` 限制 |

### D. 何时找 Krow Team

| 场景 | 联系方式 | 期望响应时间 |
|---|---|---|
| 装机 / API key 问题 | [support@krow.cn](mailto:support@krow.cn) | 24h |
| 文档错误 / 改进建议 | [GitHub issue](https://github.com/aullik5/krow/issues) | 1-3 天 |
| Plugin 设计咨询 | DevRel slack（邀请邮件附 invite） | 实时 |
| 商务合同 / 大客户接入 | [support@krow.cn](mailto:support@krow.cn) cc [business@krow.cn](mailto:business@krow.cn) | 48h |
| 紧急生产事故 | DevRel slack #incident channel | 实时 |

---

## 资源 / 进一步学习

| 资源 | 用途 |
|---|---|
| [`quickstart.md`](./quickstart.md) | 5 分钟跑通；含 5 类 plugin 范例 |
| [`api-reference.md`](./api-reference.md) | 完整 API 手册（15 章 / 57 子节）— 写 plugin 必看 |
| [`advanced-development-guide.md`](./advanced-development-guide.md) | TURBO 哲学 / 工具设计 / 测试方法论 |
| [`runtime-install.md`](./runtime-install.md) | runtime wheel 装机详细步骤（v2 reverse proxy）|
| [`roadmap.md`](./roadmap.md) | SDK 进度 SSOT |
| [`EULA.md`](./EULA.md) | 商用条款（v1.1 DRAFT）|

---

## 反馈渠道

我们承诺：

- **24h** 响应技术问题（[support@krow.cn](mailto:support@krow.cn)）
- **1 周** review 你提的 GitHub issue（如果是 bug 优先修）
- **1 月** 一次外部团队 RoadMap review meeting（你的需求会被整合）

**最后一句**：Krow SDK 是为了让你**少写 boilerplate，多关注业务**. 如果你发现自己在重复造轮子，stop and ask — 大概率 Krow 已有一个 API 解决你的问题.

欢迎入坑！

— Krow Team · 2026-05-16（配套 `0.8.12.5` PyPI release + cloud-team 协议锁定）
