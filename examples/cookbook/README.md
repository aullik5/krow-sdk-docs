# Krow Agent SDK Cookbook

> **不是 snippet，是端到端可 fork 的完整 demo**。
> 每个目录是一个独立、可单独装、可单独跑的小项目。
> 设计目标：让一个"AI Agent 工作流"开发者上手时，先 fork 一个 cookbook 改吧改吧 = MVP 上线。

---

## Demo 列表

| # | Demo | 路径 | 业务场景 | 难度 | 演示的 SDK 能力 |
|---|---|---|---|---|---|
| 1 | **data-analyst** | [`data-analyst/`](./data-analyst/) | CSV → 文字摘要 + 关键统计 + 数据质量审计（异常 / 相关 / PII）+ 多 model fallback | ⭐⭐ | ToolPlugin · ACTPlugin · HintPlugin · GatePlugin（PII / OutputPath）· EventListenerPlugin · BudgetSpec · LLMReplayStore · 多 model 切换 |
| 2 | **financial-analyst** | [`financial-analyst/`](./financial-analyst/) | 上市公司年报横向对比 + 投资简报 + Prometheus | ⭐⭐⭐ | 6 类 plugin 全用（含 ObservabilityPlugin Prometheus）+ BudgetSpec |
| 3 | **literature-reviewer** | [`literature-reviewer/`](./literature-reviewer/) | 多 PDF 文献综述（主题聚类 + 章节生成 + 抄袭检测） | ⭐⭐⭐ | 5 类 plugin（CitationCompletenessGate / PlagiarismGate 等）+ BudgetSpec |
| 4 | **contract-auditor** | [`contract-auditor/`](./contract-auditor/) | 合同审阅（强阻断 Gate + OpenTelemetry tracing） | ⭐⭐⭐⭐ | 6 类 plugin 全用（含 ObservabilityPlugin OpenTelemetry） |
| 5 | **knowledge-wiki** | [`knowledge-wiki/`](./knowledge-wiki/) | 一批资料 → 结构化知识库（本体 Ontology + 可浏览互链百科词条 wiki） | ⭐⭐⭐⭐ | ToolPlugin × 5（扫描 / 抽取 / 关系 / 物化 / 覆盖核对）· ACTPlugin · GatePlugin（WikiCoverageGate 防"假编译"）· EventListenerPlugin（三阶段进度）+ BudgetSpec |
| 6 | **hitl-assistant** | [`hitl-assistant/`](./hitl-assistant/) | CAD/仿真参数变更助手（Agent 中途停下来问工程师 → 答复可带截图 → 断点续跑） | ⭐⭐ | **HITL 全 API**（`with_hitl` 强制确认门 / `request_human_input` LLM 自主发问 / `agent.resume` 多模态续跑 / durable checkpoint 跨进程恢复 / 断点管理；需 `krow-agent-sdk >= 0.9.0.5`）· ToolPlugin · ACTPlugin |
| 7 | **datasheet-batch** | [`datasheet-batch/`](./datasheet-batch/) | 批量并发解析一批元器件 datasheet（建库）→ per-item 结构化规格 + 覆盖报告 | ⭐⭐ | **生产 agent 认知回路内并发批处理**：per-item 身份归属 / 单份失败隔离 / 覆盖可判定（N 中完成 M / 失败 K）/ 大批量分块续跑 · ToolPlugin（parse_one / batch_parse）· 覆盖守门 GatePlugin · ACTPlugin · 零 LLM 确定性演示（`python main.py --demo`；需 `krow-agent-sdk >= 0.9.0.51`）|

> 前 6 个 cookbook 共演示 SDK 全部 6 类 production plugin（ACTPlugin / ToolPlugin / HintPlugin / GatePlugin / EventListenerPlugin / ObservabilityPlugin）+ BudgetSpec 预算硬约束。knowledge-wiki 额外演示 **System 1 确定性流水线编排 + System 2 单发 LLM**：知识编译走"扫描 → 逐文件抽取 → 关系推断 → wiki 物化 → 覆盖验收"五步确定性流程，而非易空转的巨型 macro-ReACT。第 7 个 **datasheet-batch** 演示**生产 agent 认知回路内的并发批处理**——把「批量解析一批 datasheet」交给 agent，同时保证并行吞吐 / per-item 身份归属（A 的规格绝不串到 B）/ 单份失败隔离 / 覆盖可判定 / 大批量续跑；支持 `python main.py --demo` 零 LLM 确定性演示。

---

## 5 分钟跑通第一个 demo

```bash
# 1. 选一个 cookbook（推荐从 financial-analyst 开始）
cd financial-analyst

# 2. 装依赖（每个 cookbook 独立 venv 推荐）
pip install -e .

# 3. 装 Krow runtime（一次性，所有 cookbook 共用）
pip install krow-sdk-install
krow-sdk-install --api-key sk-user-xxxxxx          # 到 https://krow.cn 拿 API key

# 4. 跑 demo（合成 sample data 已在 sample_data/ 里）
export KROW_API_KEY=sk-user-xxxxxx                  # Linux / macOS
# $env:KROW_API_KEY = "sk-user-xxxxxx"              # Windows PowerShell

python main.py sample_data/*.pdf --pdf
```

输出在 `output/` 目录（`.md` / `.pdf` / `.docx` / `.audit.jsonl` / `.svg` 等，按 demo 不同）。

---

## 真实 LLM E2E 测试（本地跑）

每个 cookbook 内置 journey-style E2E 测试（合成 sample data + 真实 LLM 调用），跑法：

```bash
cd financial-analyst
pip install -e ".[test]"
pytest tests/test_*_journey_e2e.py -v -s
```

预期：< 10 min 单 demo（约 5-15 LLM 调用）。**没有 `KROW_API_KEY` 时自动 skip**（测试装饰器 `@require_real_llm` 守门）。

零 LLM 的 unit smoke 测试（< 1 秒，无 API key 也能跑）：

```bash
pytest tests/test_*_smoke.py -v
```

---

## 各 cookbook 的预期结果卡

每个 cookbook 在 `tests/expected_cards/tier1_minimal.yaml` 内声明 journey E2E 的多维断言（exit_code / max_walltime_s / required_artifacts / required_sections_in / forbidden_keywords_in / min_artifact_bytes）：

| Cookbook | 关键断言 |
|---|---|
| financial-analyst | 5 段标准披露 + InsiderInfoGate 禁词 + ≥800 字节 |
| literature-reviewer | 引言 / 方法 / 参考文献 + ≥1.5 KB + 学术夸大词禁用 |
| contract-auditor | 5 段审阅结构 + 含"免责"风险识别 + ≥1 KB |
| data-analyst | 数据摘要 + 异常 + 相关性段 + ≥500 字节 |
| knowledge-wiki | ontology 节点数 ≥ 阈值 + wiki 词条数 ≥ 阈值 + 词条含 YAML frontmatter + `compile_report.md` 含领域关键词 |

---

## 与 SDK 文档的关系

| 文档 | 你看哪个 |
|---|---|
| [`quickstart.md`](../quickstart.md) | **第一次接触 SDK** — 5 分钟跑通 hello world |
| [`advanced-development-guide.md`](../advanced-development-guide.md) | **写自己 plugin 时回查** — 实战最佳实践 |
| [`api-reference.md`](../api-reference.md) | **查具体 API signature** |
| **本目录 cookbook** | **想要 MVP 起手** — 直接 fork 改的真实业务 demo |

---

## 设计原则（cookbook 通用）

每个 cookbook 目录满足：

- ✅ **真实业务价值** — 跑出来能解决一个具体问题（不是 hello world）
- ✅ **可独立运行** — 1 个目录 + `pyproject.toml` + `.env.example` + `README.md` + `python main.py`
- ✅ **覆盖广度** — 至少演示 3 类 plugin + 1 个错误处理路径
- ✅ **真实 LLM E2E 可跑** — 本地跑 `test_*_journey_e2e.py` 5-10 min 内完成
- ✅ **可读性** — 关键 API 调用旁边有注释；trade-off 明示

---

## fork 改成自己业务的步骤

1. 选最贴近你业务的 cookbook（或选最复杂的 contract-auditor 当模板）
2. `cp -r contract-auditor my-cookbook`
3. 改 `pyproject.toml` `name`、改 `main.py` CLI args、改 `*_plugin.py` 工具实现
4. 改 `act_assets/<your_act>/__act__.yaml` + `ext_<your_act>.md` —— ACT 引导 LLM 跟着你的工作流走
5. 改 `tests/test_*_smoke.py` 单测（System 1 路径，0 LLM 成本）
6. 改 `tests/expected_cards/tier1_minimal.yaml`（journey E2E 多维断言）
7. 跑通 `pytest tests/` 后再考虑跑真实 LLM

预期 fork 改造时间：2-3 小时（视业务复杂度）。

---

## 反馈 / 支持

- [GitHub Issues](https://github.com/aullik5/krow-sdk-docs/issues) — bug / 文档错误
- [GitHub Discussions](https://github.com/aullik5/krow-sdk-docs/discussions) — 用法 / plugin 设计讨论
- `support@krow.cn` — 紧急生产问题
