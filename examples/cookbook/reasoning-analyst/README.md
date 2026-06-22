# Reasoning Analyst · SDK Cookbook

纯 SDK（无 UI）启动 Krow 引擎的**推理洞察管线**：把一份资料 + 一个分析问题，交给
链式证据核验（`evidence_chain`）/ 竞争假设排除（`hypothesis_test`）等策略，输出
**带证据落点的结论**，并自助落盘成 markdown + json。

> 这是面向 **SDK 开发者** 的范例：演示如何在没有桌面推理工作台 UI 的情况下，直接
> 用 `agent.run(...)` 把问题路由进 reasoning 管线，并正确判定"推理是否真的完成"。

## 这个 cookbook 演示什么

1. **纯 SDK 启动 reasoning 管线**：复刻桌面推理工作台的提交语义
   `task_context = {"source": "reasoning_panel", "strategy": ...}`，并**显式 pin**
   `act_name="reasoning_pipeline"`（该 ACT 无 disclosure_triggers，单靠 strategy
   不保证 macro planner 选中它）。
2. **`success` vs `final_output` 判定经验**：复杂 journey（如 evidence_chain）在
   纯 SDK 下可能 `success=False` 却已 commit 完整结论（桌面 / 后台任务队列有
   partial 接受层兜底，纯 SDK 没有）。本 cookbook 的"推理完成"判据是
   `final_output 非空 且（success 或 conclusion committed 事件）`。
3. **过程可观测**：订阅 EventBus 采集工具调用 / `cognitive.load`（双环快环元认知）
   / `reasoning.conclusion.committed` 等事件，量化推理工具链是否真跑。
4. **自助落盘**：纯 SDK 不自动写 `.krow/reasoning/{id}.json`（那条路由只在桌面 /
   BTQ 集成时挂载），cookbook 把结论落盘成 `reasoning_<strategy>.md` + `.json` 补齐缺口。

## 跑前

```bash
# 1. 设 API key
export KROW_API_KEY=sk-user-xxx      # PowerShell: $env:KROW_API_KEY='sk-user-xxx'
# 2. 安装 runtime
krow-sdk-install --api-key $KROW_API_KEY
# 3. 装本 cookbook
cd examples/cookbook/reasoning-analyst && pip install -e .
```

## 跑法

```bash
# 最小跑（自带病例资料 · 默认 evidence_chain 链式证据核验）
python main.py

# 指定策略 + 自定义问题
python main.py hypothesis_test --question "呼吸困难更可能心源性还是肺源性？"

# 一次跑两个 journey（evidence_chain + hypothesis_test）
python main.py --all

# 进阶：覆盖模型 / 预算 / endpoint（默认无需指定）
python main.py --chat-model qwen3.6-plus --reasoning-model qwen3.6-plus \
  --budget-llm-calls 40 --budget-walltime 600 \
  --base-url https://api.krow.cn   # staging / 私有部署才需要改
```

可用 flag（`python main.py -h` 查全量）：`--question` 自定义问题、`--all` 跑两个
journey、`--sources` 换资料、`--output-dir` / `--project-dir` 改落点、
`--budget-llm-calls` / `--budget-walltime` / `--budget-replans` 调预算、
`--chat-model` / `--reasoning-model` 覆盖模型、`--base-url` 改 cloud endpoint
（亦可用 `KROW_BASE_URL` 环境变量，默认 `https://api.krow.cn`）。

支持的策略（`SUPPORTED_STRATEGIES`）：`evidence_chain` / `hypothesis_test` /
`comparative_analysis` / `temporal_trace`。全量推理策略见引擎
`modules.knowledge.reasoning_strategies.STRATEGIES`（含需 CSV 定量依赖
DoWhy/causal-learn 的因果发现类策略，本 cookbook 不默认演示）。

## 输出

```
<output-dir>/reasoning_<strategy>.md     # 结论报告（证据落点 + 过程指标）
<output-dir>/reasoning_<strategy>.json   # 结构化结论（success / concluded / metrics）
<output-dir>/summary.json                # 多 journey 汇总（n_completed / n_journeys）
```

## 关键 API（二次开发速查）

```python
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key(api_key)
    .with_project_root(project_dir)   # 资料放在 project_dir 供推理工具读取
    .build()
)
result = agent.run(
    "核实论断：本病例支持下壁急性心肌梗死诊断。",
    task_context={
        "source": "reasoning_panel",       # ← 激活推理专属行为
        "act_name": "reasoning_pipeline",  # ← 显式 pin 推理 ACT
        "strategy": "evidence_chain",      # ← 选策略
    },
)

# 关键：别只看 result.success —— 复杂 journey 可能 success=False 却已 commit 结论
completed = bool((result.final_output or "").strip()) and (
    result.success  # 或：采集到 reasoning.conclusion.committed 事件
)
```

`reasoning_journeys.py` 把这套封装成可复用、可单测的 System-1 函数：
`build_reasoning_task_context` / `ReasoningEventCollector` /
`extract_reasoning_outcome` / `persist_reasoning_outcome` / `run_reasoning`。

## 查看慢环蒸馏结果（双环元认知）

reasoning 跑多了，引擎的**慢环**会在睡眠期把高频认知负荷蒸馏成 learned overlay
教训。只读查看：

```python
from krow_agent_sdk.diagnostics import get_overlay_snapshot
import json
print(json.dumps(get_overlay_snapshot(), ensure_ascii=False, indent=2))
```

字段语义 / 晋级阈值 / 维护方式见 `advanced-development-guide.md`「双环元认知与运行时
自进化」一章。

## 测试

零 LLM 的 smoke（< 1 秒，无 API key 也能跑）：

```bash
pip install -e ".[test]"
pytest tests/test_reasoning_analyst_smoke.py -v
```

真实 LLM E2E（本地跑，需 `KROW_API_KEY`；无 key 自动 skip）：

```bash
pytest tests/test_reasoning_analyst_journey_e2e.py -v -s
```

## 反馈 / 支持

- GitHub Issues — bug / 文档错误
- GitHub Discussions — 用法 / 推理策略讨论
- support@krow.cn — 紧急生产问题
