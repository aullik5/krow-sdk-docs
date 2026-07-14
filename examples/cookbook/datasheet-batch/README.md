# Cookbook · Datasheet 批量并发解析（Datasheet Batch）

> 模拟 **KAD 工程团队生产场景**：在 Krow agent 下批量解析元器件 datasheet PDF
> （电阻/电容/芯片建库）。现状全程串行（100 份≈2h），本 cookbook 演示如何在
> **生产 agent 认知回路内**做并发批量解析，同时保证 per-item 正确性。

## 解决什么问题（KAD 需求 N1–N5）

| 需求 | 本 cookbook 如何满足 |
|---|---|
| **N1 并行吞吐** | `datasheet_batch_parse` 用 `max_workers` 并发处理整批（复用通用编排器的 ThreadPoolExecutor），墙钟随并行度下降 |
| **N2 per-item 身份归属** | 每份 `model`（型号）是确定性身份；结果由编排器按 model 绑定，A 的规格绝不串到 B——**不靠 LLM 在一次上下文里记住谁是谁** |
| **N3 失败隔离** | 单份损坏/缺失被单独记 `failed`，不中断、不污染同批其它份 |
| **N4 覆盖可判定** | 返回 `completed/failed/degraded/coverage`；`DatasheetBatchCoverageGate` 在全失败/低覆盖时 BLOCK conclude |
| **N5 大批量续跑** | `batch_size` 分块 + 软预算主动收尾；`should_continue=true` 时用相同 items 续跑，账本幂等跳过已处理份 |

## 不重复造轮子（架构原则）

批量并发 / per-item 账本 / 续跑逻辑**全部复用**主仓通用编排器
`modules.agent.batch_orchestrator.orchestrate_batch`（该编排器抽象自 reasoning 管线
`research_corpus_targets` 的生产验证范式）。本 cookbook **不自造线程池 / 账本**，只提供
per-item 的「解析单份 datasheet」业务工具 + 覆盖守门 gate + ACT。

## 快速开始

### 零 LLM 确定性演示（不需 API key）
```bash
cd examples/cookbook/datasheet-batch
python main.py --demo
```
输出：并发解析随仓 5 份样例（含 1 份故意损坏演示 N3 隔离），打印 per-item 归属 +
覆盖报告（如 `完成 4 / 失败 1 / 覆盖率 80%`）。

### Agent 路径（真实生产形态，需 API key）
```bash
export KROW_API_KEY=sk-user-xxx
krow-sdk-install --api-key $KROW_API_KEY
pip install -e .
python main.py
```
Krow agent 进入 `datasheet_batch` ACT，自主选并发工具、读覆盖报告、在覆盖率守门下收尾。

### 跑 smoke 测试（零 LLM / 零网络）
```bash
pip install -e ".[test]"
pytest tests/ -v
```

## 用于真实生产

把 `datasheet_batch_plugin.parse_datasheet_file`（cookbook 用确定性正则解析合成 .txt）
替换为你的真实 **VLM / PDF 文档解析**（单份 PDF → 结构化字段）即可——批量编排契约
（per-item 归属/隔离/覆盖/续跑）完全不变，直接获得 N1–N5 能力。

## 文件结构

- `datasheet_batch_plugin.py` — ToolPlugin（parse_one / batch_parse）+ GatePlugin（覆盖守门）+ ACTPlugin
- `act_assets/datasheet_batch/` — ACT manifest + 扩展指令
- `sample_data/` — 5 份合成 datasheet（4 正常 + 1 损坏）
- `main.py` — 入口（--demo 零 LLM / 默认 Agent 路径）
- `tests/` — smoke 测试
