# Reasoning Analyst · SDK Cookbook

纯 SDK（无 UI）启动 Krow 引擎的**推理洞察管线**：把一份资料 + 一个分析问题，交给
链式证据核验（`evidence_chain`）/ 竞争假设排除（`hypothesis_test`）/ **因果发现**
（`causal_discovery`）/ **概率推理**（`bayes_inference`）等策略，输出**带证据落点的
结论**，并自助落盘成 markdown + json。覆盖推理洞察管线的全部范式（UI 除外，与桌面
推理工作台等价）。

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
   / `reasoning.conclusion.committed` / `reasoning.mechanism_chain`（胜出假设定性
   机制链）/ `provider.transient_storm`（供给层瞬断风暴——量化"墙钟去哪了"）等
   事件，量化推理工具链是否真跑。
4. **自助落盘**：纯 SDK 不自动写 `.krow/reasoning/{id}.json`（那条路由只在桌面 /
   BTQ 集成时挂载），cookbook 把结论落盘成 `reasoning_<strategy>.md` + `.json` 补齐缺口。
5. **深度模式**（`--depth-mode`）：长文本 ACH 任务（如整本小说 whodunit）显式声明
   "值得跑满"→ 引擎把墙钟预算抬到策略契约 max_wallclock（hypothesis_test 7200s），
   与桌面推理工作台深挖开关同语义，避免中途 forced conclude 只交一半矩阵。

## 跑前

```bash
# 1. 设 API key
export KROW_API_KEY=sk-user-xxx      # PowerShell: $env:KROW_API_KEY='sk-user-xxx'
# 2. 安装 runtime
krow-sdk-install --api-key $KROW_API_KEY
# 3. 装 reasoning 依赖（因果发现 / 概率推理的定量能力需要）
pip install "krow-agent-sdk[reasoning]"   # dowhy / causal-learn / pgmpy + ontology 轻量栈
# 4. 装本 cookbook
cd examples/cookbook/reasoning-analyst && pip install -e .
```

> **依赖分层**：只跑定性策略（`evidence_chain` / `hypothesis_test` /
> `comparative_analysis` / `temporal_trace`）装 `krow-agent-sdk[ontology]` 即可。
> `causal_discovery` 的**定性路径**（LLM 提因果边 + 定性反驳，无数据集）也只需
> `[ontology]`；其**定量路径**（统计因果发现/估计）和 `bayes_inference`（贝叶斯网
> 推断）需 `krow-agent-sdk[reasoning]`（含 dowhy / causal-learn / pgmpy）。缺重型库时
> 引擎会 fail-loud 指引降级到定性路径，不会静默出错。

## 跑法

```bash
# 最小跑（自带病例资料 · 默认 evidence_chain 链式证据核验）
python main.py

# 指定策略 + 自定义问题
python main.py hypothesis_test --question "呼吸困难更可能心源性还是肺源性？"

# 因果发现六阶段科研闭环（定性可跑；定量需 [reasoning]）
python main.py causal_discovery

# 贝叶斯网概率推理（需 [reasoning] 的 pgmpy）
python main.py bayes_inference --question "量化心源性 vs 肺源性呼吸困难的后验概率"

# 一次跑两个 journey（evidence_chain + hypothesis_test）
python main.py --all

# 进阶：覆盖模型 / 预算 / endpoint（默认无需指定）
python main.py --chat-model qwen3.6-plus --reasoning-model qwen3.6-plus \
  --budget-llm-calls 40 --budget-walltime 600 \
  --base-url https://api.krow.cn   # staging / 私有部署才需要改

# 深度模式（长文本 ACH 任务防中途 forced conclude · 引擎抬满策略契约墙钟）
python main.py --preset whodunit_z --depth-mode
```

可用 flag（`python main.py -h` 查全量）：`--question` 自定义问题、`--all` 跑两个
journey、`--sources` 换资料、`--output-dir` / `--project-dir` 改落点、
`--budget-llm-calls` / `--budget-walltime` / `--budget-replans` 调预算、
`--chat-model` / `--reasoning-model` 覆盖模型、`--base-url` 改 cloud endpoint
（亦可用 `KROW_BASE_URL` 环境变量，默认 `https://api.krow.cn`）。

支持的策略（`SUPPORTED_STRATEGIES`）：

| 策略 | 范式 | 依赖 |
|------|------|------|
| `evidence_chain` | 链式证据逐级抬升后验 | `[ontology]` |
| `hypothesis_test` | ACH 竞争假设排除 | `[ontology]` |
| `comparative_analysis` | 多对象横向对比 | `[ontology]` |
| `temporal_trace` | 时间线追踪 | `[ontology]` |
| `causal_discovery` | 因果发现六阶段科研闭环 | 定性 `[ontology]` / 定量 `[reasoning]` |
| `bayes_inference` | 贝叶斯网概率推理 | `[reasoning]`（pgmpy） |

全量推理策略见引擎 `modules.knowledge.reasoning_strategies.STRATEGIES`（如
`causal_effect` / `counterfactual_analysis` / `knowledge_compile` 等）。

## 真实世界 journey 预设（`--preset`）

三个贴近真实科研 / 推理场景的完整 journey，与桌面推理工作台**除 UI 外等价**：

| 预设 | 场景 | 策略 | 真数据环境变量 |
|------|------|------|----------------|
| `target_discovery` | 肺癌论文找靶点（区分因果致因 vs 相关） | `causal_discovery` | `KROW_JOURNEY_LUNG_CANCER_PAPERS` |
| `whodunit_x` | X 的悲剧推理真凶（ACH 竞争假设排除） | `hypothesis_test` | `KROW_JOURNEY_TRAGEDY_X` |
| `whodunit_z` | Z 的悲剧推理真凶（ACH 竞争假设排除） | `hypothesis_test` | `KROW_JOURNEY_TRAGEDY_Z` |

```bash
# smoke（无真数据也能跑通全链路）—— 自动用随仓的零版权合成微样例
python main.py --preset whodunit_x
python main.py --preset target_discovery

# 复现完整效果 —— 指向你自备的真数据（期刊 PDF / 小说全文）
$env:KROW_JOURNEY_TRAGEDY_X = 'D:\...\X的悲剧-隐藏结尾版本.txt'   # PowerShell
python main.py --preset whodunit_x
# 或直接传 --sources 覆盖
python main.py --preset target_discovery --sources D:\...\肺癌科研智能体\papers
```

> **版权合规**：期刊 PDF（出版商版权）与侦探小说译本（作者/译者版权）**都不进公开
> 仓**。仓里只随发**自撰的零版权合成微样例**（`sample_data/real_world_synthetic/`：
> 一篇仿写密室短篇 + 一组合成肺癌文献摘要，均为演示虚构、不代表真实医学证据），
> 够 smoke 跑通管线。设对应环境变量或 `--sources` 指向你自己的资料即复现完整 journey。
> 预设定义见 `real_world_journeys.py`。

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
