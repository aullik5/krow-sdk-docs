# Target Nominator · AI 靶点提名 cookbook

> 借鉴 **Cell《AI 发现 GPNMB CAR-T 靶点》**（AI 驱动的肿瘤表面抗原靶点发现）：把候选
> 靶点当"竞争假设"，从公开数据库真取数 → 多维加权打分 → LLM 提名单一最佳靶点。
> 这是一个**可 fork、可单独跑**的 Krow SDK plugin demo，演示如何用
> **ToolPlugin + GatePlugin + ACTPlugin + BudgetSpec** 把"数据 + 打分 + LLM 提名"
> 搭成可复现工作流。

## 它演示了什么

| SDK 能力 | 本 cookbook 的用法 |
| --- | --- |
| **ToolPlugin** | 3 个 System 1 工具：HPA 表达取数 / Open Targets 关联+可药取数 / 多维加权打分 |
| **GatePlugin** | `TargetNominationIntegrityGate`：无真取数 / 全 ungrounded → BLOCK conclude（反编造） |
| **ACTPlugin** | `target_nominator` ACT：提名工作流（逐候选取数 → 打分 → 提名 → 落盘） |
| **BudgetSpec** | `--depth-mode` 抬高墙钟上限，逐候选多库取数的长任务不被兜底提前 kill |

## TURBO 哲学（为什么这么拆）

- **System 1（确定性工具）**：HTTP 取数 + 归一、加权聚合算术、接地校验——可单测、可重放、零 token。
- **System 2（LLM）**：从工具数据推断每维有利度、选谁做最佳靶点、写提名理由。
- **反幻觉红线**：每维数值**必须**带工具返回的 `source` url；LLM 凭记忆编造 → 关键维无
  source → gate 拦截。**准确性 > 完整性**。

## 四维打分（借鉴 GPNMB "最常被提名"）

| 维度 | 含义 | 数据源 |
| --- | --- | --- |
| **安全 safety** | 健康重要器官低表达（on-target off-tumor 毒性低） | Human Protein Atlas normal / single-cell |
| **有效 efficacy** | 肿瘤组织高表达 | Human Protein Atlas pathology |
| **可药 druggability** | 抗体 / 小分子可及 | Open Targets tractability |
| **广谱 breadth** | 跨多癌种关联强 | Open Targets associatedDiseases.score |

GPNMB 之所以"最常被提名"，正因它跨癌种关联广 + 黑色素瘤高表达 + 抗体可药
（glembatumumab vedotin ADC 背书）——四维俱佳。

## 快速开始

```bash
# 1. 装 SDK runtime（首次）
export KROW_API_KEY=sk-user-xxx     # Windows: $env:KROW_API_KEY='sk-user-xxx'
krow-sdk-install --api-key $KROW_API_KEY

# 2. 装 cookbook
cd examples/cookbook/target-nominator
pip install -e .

# 3. 跑 GPNMB journey（黑色素瘤候选清单 → 提名报告）
python main.py --cancer-type melanoma \
    --candidates GPNMB MLANA PMEL TYRP1 MCAM CSPG4
```

输出：

- `output/target_nomination.md` —— 提名报告（候选四维打分表 + 最佳靶点 + 溯源 url）
- `output/target_scores.json` —— 打分矩阵（ranking / matrix / weights / issues）
- `output/summary.json` —— 运行摘要

## fork 改成你自己的业务

1. 换数据源：把 `fetch_target_expression` / `fetch_target_associations` 改成你的库
   （DepMap / cBioPortal / 自建 scRNA-seq），保持"返回带 `source` url"的契约。
2. 换打分维：改 `_DIM_SYNONYMS` + `_KEY_DIMENSIONS`，`score_target_candidates` 的加权
   聚合算法通用（越大越好 + 关键维接地校验）。
3. 换守门规则：`TargetNominationIntegrityGate` 是"无真取数 → BLOCK"模板，按你的红线改判据。
4. 换工作流：改 `act_assets/target_nominator/ext_target_nominator.md`（LLM 看的指令）。

## 测试

```bash
# System 1 smoke（零 LLM，零网络：monkeypatch HTTP）
pytest tests/test_target_nominator_smoke.py -v

# 真 LLM journey（需 KROW_API_KEY；无 key 自动 skip）
pytest tests/test_target_nominator_journey_e2e.py -v -s
```

## 上游 SSOT

本 cookbook 的取数 / 打分 / gate 思路来自 litsci worker 的 `target_nomination` 能力
（`packages/krow-worker-litsci-plugin/krow_worker_litsci/tools/{target_tools,biodb_direct}.py`）。
两者共享同一打分算法（多维加权 + 接地校验），cookbook 是其独立可 fork 的 demo 化。
