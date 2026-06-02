# 文献综述员 ACT — 扩展指南

## 本 ACT 的定位

本 ACT 是 Krow SDK Cookbook v3 的第 2 个 demo（详 ``COOKBOOK_DESIGN.md`` §2.2），
覆盖**真实学术 PI / 博士生 / 智库分析师**的高频任务：50-200 篇 paper PDF →
综述章节起草 + 引用核对。

与 v3 PR-A `financial_analyst` 的差别：

| 维度 | financial_analyst | literature_reviewer |
|---|---|---|
| 输入规模 | 3-5 家公司年报 | 50-200 篇 paper |
| 核心算法 | KPI 抽取 / 单位归一化 / 估值 | 元数据抽取 / 主题聚类 / 引用图 |
| Gate | 信披完整 / 内幕红线（金融法律） | 引用完整 / 抄袭红线（学术规范） |
| Hint | σ 偏差 KPI | thin cluster + 年份跨度 |
| ObservabilityPlugin | ✅ Prometheus | ❌ 学术场景一般不接 BI |
| BudgetSpec 推荐 | 80 LLM × 900s | 120 LLM × 1800s |

## 推荐工作流（**10 步**）

### 1. **批量调 `literature_reviewer_extract_paper_metadata`** — 抽 N 篇 paper 元数据

- 对**每篇 PDF** 调用一次（建议并行 / pipelining；EventListener 实时报进度）
- 抽出 title / authors / year / abstract / keywords / ref_count
- **铁律**：不要让 LLM 读 PDF 全文塞 prompt（50 paper × 5K token = 上下文爆炸）

### 2. **`literature_reviewer_cluster_papers_by_topic(papers, similarity_threshold)`** — TF-IDF 聚类

- 输入：step 1 输出的 paper 元数据列表
- 默认零 sklearn 依赖（纯 Python TF-IDF + 凝聚层次聚类）；装了 sklearn 自动用更准的算法
- 返回 clusters: `[{topic_id, paper_ids, top_terms, n_papers, year_min, year_max, thin}]`
- **铁律**：不要让 LLM 凭感觉看摘要分组（5-10% 漂移率不可重放）

### 3. **HintPlugin 自动激活**（无需 LLM 主动调用）

- **TopicCoverageHintPlugin**：检测 thin cluster（< 2 篇） → 推 LLM 合并 / 单独提一笔
- **YearGapHintPlugin**：检测年份跨度 ≥15 年的 cluster → 推 LLM 在该章节内分 era

### 4. **`literature_reviewer_build_citation_graph(papers, edges, cluster_assignments)`** — 引用图

- 输入：step 1 papers + 用户提供的 edges（A 引用 B 的关系列表）
- **trade-off**：不从 PDF 自动抽引用关系（学术 PDF 引用格式不标准化），
  让用户传入；真实使用建议接 OpenAlex / Semantic Scholar API
- 输出：DOT 字符串（可被 Graphviz 渲染）+ 自动检测引用环 / 孤立节点

### 5. **`literature_reviewer_generate_review_outline(cluster_result, template)`** — 章节大纲

- template='standard'（8 章）or 'compact'（4 章）
- 自动决策是否含 Timeline 章节（年份跨度 ≥10 年自动含）
- 为每节标 citations_required（学术规范 ≥ N 篇引用）

### 6. **基于以上数据起草综述 markdown**（System 2，LLM 在 ReACT 循环内组织）

- **结构**：按 step 5 outline 写
- **每段 ≥ 3 篇引用**（CitationCompletenessGate 守门铁律）
- **不允许大段抄原文**（PlagiarismGate 守门）
- LLM 应：把 paper abstract 用自己的话改写（paraphrase），不直接复制
- 引用格式：[N] 数字风格 / (Author, Year) 作者-年份风格 任选其一

### 7. **`literature_reviewer_detect_plagiarism_overlap(review_text, source_texts)`** — 抄袭检测

- 输入：综述 markdown + {paper_id: abstract} 字典
- 默认 5-gram word + 60% 阈值
- **PlagiarismGate 守门触发**：flagged_sources 非空 → BLOCK conclude

### 8. **如 Gate BLOCK：根据 reason 修改综述 → 重写 markdown → 重检测**

- CitationCompletenessGate BLOCK → 看缺哪几段引用 → 补齐
- PlagiarismGate BLOCK → 找命中段落 → 用自己的话改写

### 9. **PDF / docx 渲染**（可选）

- 调 Krow 内置 ``word_smart_export(format='docx')`` 出 docx（学术界更常用）
- 或 ``word_smart_export(format='pdf')`` 出 PDF
- **不要在本 cookbook 引入 fpdf2 / python-docx 依赖**——SSOT 复用 Krow 内置

### 10. **Listener 自动留进度日志**（无需 LLM 主动）

- ReviewProgressListener 已订阅 EventBus，每个 paper 抽完打印进度
- 启用 progress_log_path 时还会写 .progress.jsonl 给后台用

## SDK 高级能力演示

### GatePlugin × 2 演示要点

| Gate | 守的什么 | 触发后 LLM 应该怎么做 |
|---|---|---|
| `CitationCompletenessGate` | 综述每段 ≥3 篇引用 | 看 reason 里"哪几段不够"→ 补引用 |
| `PlagiarismGate` | 综述 n-gram overlap ≥60% 命中原文 | 找命中段落 → 用自己的话改写 |

### HintPlugin × 2 演示要点

| Hint | 触发条件 | 推给 LLM 什么 |
|---|---|---|
| `TopicCoverageHintPlugin` | cluster_papers_by_topic 输出有 thin cluster | thin cluster 列表 + 合并建议 |
| `YearGapHintPlugin` | cluster 年份跨度 ≥15 年 | "建议章节内分 early/modern era" |

**关键**：两个 hint 共享同一 trigger 工具（cluster_papers_by_topic），但
推送的内容**完全不同**——这演示了 plugin 的"按需触发"原则（HintPlugin
不是"任何时候都喷文本"，是"特定 condition 才推"）。

### BudgetSpec 演示要点（与 financial 对比）

学术场景推荐预算：

```python
BudgetSpec(
    max_total_llm_calls=120,   # 每个 cluster ~5-10 次 LLM call × 10-20 cluster ≈ 100
    max_walltime_s=1800,       # 30 分钟（PDF 抽取 + 聚类 + 起草）
    max_replans=2,             # gate BLOCK 各允许 1 次修正
)
```

为什么是 120 / 1800 / 2：

- 120 LLM calls：100 篇任务上限；超出说明 LLM 陷入循环
- 1800s：50 PDF × ~10s 抽取 + 聚类 ~30s + 起草 ~25 min ≈ 1700s
- 2 replan：CitationCompletenessGate / PlagiarismGate 各允许 1 次

## 反模式

| 反模式 | 正确做法 |
|---|---|
| ❌ LLM 直接读 50 PDF 全文塞 prompt | ✅ 调 `extract_paper_metadata` 批量抽元数据 |
| ❌ LLM 凭感觉看摘要分组聚类 | ✅ 调 `cluster_papers_by_topic` deterministic TF-IDF |
| ❌ LLM 自己写 DOT 字符串画引用图 | ✅ 调 `build_citation_graph`（System 1 图论） |
| ❌ 综述某段直接复制原文 abstract | ✅ PlagiarismGate 会 BLOCK；用自己的话改写 |
| ❌ 综述某段没有引用就 conclude | ✅ CitationCompletenessGate 会 BLOCK；补齐到 ≥3 篇 |
| ❌ 用 hint 教 LLM "请加引用" 替代 Gate | ✅ 学术规范红线必须 System 1 闸住 |
| ❌ 在 cookbook 加 python-docx / fpdf2 自己渲文档 | ✅ 调 `word_smart_export`（SSOT 复用） |
| ❌ 不聚类直接让 LLM 写综述章节 | ✅ 先聚类得到 outline，按主题展开 |

## 引用

- 设计文档：`packages/krow-agent-sdk/examples/cookbook/COOKBOOK_DESIGN.md` §2.2
- 同系列 v3 demo：`packages/krow-agent-sdk/examples/cookbook/financial-analyst/`
- TURBO 哲学：`AGENTS.md` §0.1
- 规范依据：综述论文学术规范 / 学术不端处置办法
