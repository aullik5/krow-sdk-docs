# Cookbook · Literature Reviewer Demo

> **研究生 / 博士生 / 学者高频场景**：
> 多 PDF 抽取 → 主题聚类 → 综述章节生成 + 引用 / 查重守门。
> 演示 SDK 5 类 plugin（ACTPlugin / ToolPlugin / GatePlugin / HintPlugin / EventListenerPlugin）。

---

## 业务背景

研究生 / 博士生 / 工业研究员每开一个新课题前必做一次"文献综述"——
读 10-30 篇相关论文 → 抽元数据（标题 / 作者 / 年份 / 关键词 / 引用）→
按子主题聚类 → 写"研究背景 / 已有方法 / 研究空白"≥3 段综述。

人工每次任务 **20-50 小时**：

- ~10 小时：读 20 份 PDF + 抄元数据 + 整理 BibTeX
- ~5 小时：人脑分类（按方法 / 按数据集 / 按年份 / 按团队 — 选哪个维度都纠结）
- ~10 小时：写综述正文 + 校引用 + 查重 + 检查时间跨度
- ~5 小时：返工（导师指出"某个子领域漏读" / "某段查重偏高" / "引用格式不一致"）

**用本 cookbook 后预期 2-4 小时**：deterministic 工具承担元数据抽取 / TF-IDF
聚类 / 引用计数 / N-gram 查重 / 时间跨度统计（System 1），LLM 只做综述叙事 /
"研究空白"识别（System 2）。

---

## 三档跑法

### Tier 1（最小跑通）：5-10 篇 paper → 简单综述

```bash
cd literature-reviewer
pip install -e .

# Linux / macOS
export KROW_API_KEY=sk-user-xxx
# Windows PowerShell:
# $env:KROW_API_KEY = "sk-user-xxx"
krow-sdk-install --api-key $KROW_API_KEY

python main.py sample_data/paper_*.pdf --review-topic rag_basics
```

输出：`output/review_rag_basics.md` —— 单主题简化综述。

### Tier 2（业务可用）：30-50 篇 paper + 引用图 + docx

```bash
python main.py sample_data/*.pdf \
    --review-topic rag_survey_2025 \
    --docx \
    --citation-edges citation_relations.json
```

`citation_relations.json` 格式：

```json
[
  {"from": "rag_2020", "to": "in_context_ralm_2024"},
  {"from": "rag_survey_2023", "to": "rag_2020"}
]
```

新增产物：

- `output/review_rag_survey_2025.docx` — 走 SDK 内置 `word_smart_export`（reportlab + CJK）
- `output/citation_graph.dot` — Graphviz DOT 引用图（可 `dot -Tsvg` 渲）

### Tier 3（生产 / 系统综述）：100+ paper + 进度日志 + 严格守门

```bash
python main.py sample_data/*.pdf \
    --review-topic systematic_review_2025 \
    --docx --pdf \
    --citation-edges citation_relations.json \
    --progress-log output/review.progress.jsonl \
    --min-citations-per-section 5 \
    --year-gap-threshold 10 \
    --budget-llm-calls 180 \
    --budget-walltime 2400
```

启用：

- **CitationCompletenessGate**（`min ≥5`）：综述每段必须 ≥5 篇引用，否则 **BLOCK**
- **PlagiarismGate**：5-gram 重叠 ≥60% 即抄袭红线 **BLOCK**
- **TopicCoverageHintPlugin**：thin cluster（仅 1 篇）→ 推 LLM "考虑合并 / 标 'misc'"
- **YearGapHintPlugin**：跨度 ≥10 年 → 推 LLM "按 era 分阶段写"
- **ReviewProgressListener**：每个 PDF 抽完 / 每段 Gate 决议 → `.progress.jsonl`
- **BudgetSpec**：100+ paper 时硬约束防 LLM 调用爆掉

---

## 演示的 SDK 能力

| Plugin 类型 | 实现类 | 业务理由 |
|---|---|---|
| **ToolPlugin** × 5 | `LiteratureReviewerToolPlugin` | 元数据抽取 / TF-IDF 聚类 / 引用图 / N-gram 查重 / 大纲生成 全部是 deterministic 算法（LLM 凭感觉聚类同一篇会进 3 个簇） |
| **ACTPlugin** | `LiteratureReviewerACTPlugin` | 10 步标准工作流让 LLM 跟着走 |
| **GatePlugin** × 2 | `CitationCompletenessGate` `PlagiarismGate` | 学术规范 + 学术诚信红线；hint 提醒不够，必须 System 1 闸住 |
| **HintPlugin** × 2 | `TopicCoverageHintPlugin` `YearGapHintPlugin` | LLM 看 cluster 表区分不了"thin cluster 该并 / 不该并"；看年份跨度区分不了"该按 era 分 / 不分" |
| **EventListenerPlugin** | `ReviewProgressListener` | 100+ PDF 任务 1-2 小时跑，研究者必须实时看到 "已读 47/120 PDF / 当前抽 X / 段 3 通过 Gate" |

> 学术场景一般不接 BI dashboard，所以本 demo 不演示 ObservabilityPlugin —— financial-analyst 演示 Prometheus，contract-auditor 演示 OpenTelemetry，覆盖真实生态。

---

## 文件结构

```
literature-reviewer/
├── README.md                          # 本文档
├── pyproject.toml                     # name = krow-cookbook-literature-reviewer
├── main.py                            # CLI 入口（三档跑法）
├── literature_reviewer_plugin.py      # 全部 plugin 实现（5 tools + 7 plugin classes）
├── act_assets/literature_reviewer/
│   └── ext_literature_reviewer.md     # ACT 10 步工作流
├── sample_data/
│   └── README.md                      # 自助跑通指南（不预置 PDF · arXiv 推荐）
├── tests/
│   ├── conftest.py
│   └── test_literature_reviewer_smoke.py  # 46 unit test（System 1 only · 0 LLM 调用）
└── .gitignore                         # 排除 output/ *.pdf *.audit.jsonl review_*.md
```

---

## 关键设计权衡（Trade-offs）

### 为什么不用 LLM 直接看 PDF 抽元数据？

LLM 抽元数据**漂移率高且单点失败**：

- 把 "Smith, J., Jones, A., Brown, R. (2024)" 当成 1 个作者 "Smith Jones Brown"
- 抽不到 abstract（被 figure caption 误识别）→ 后续聚类全跑偏
- 100 篇 paper 规模下，LLM 调用量 ≈ 100 × 1500 token ≈ **150K input token / 篇**，
  纯成本比 deterministic 元数据抽取贵 **50×**

本 cookbook 用 `pdfplumber` + 正则 + 启发式 dict 查表（标题 / 作者 / 年份 / 关键词
都有结构化锚点），**0 token 成本**，准确率 > 95%。

### 为什么用 TF-IDF + Agglomerative 聚类，不用 LLM embedding 聚类？

按场景划分边界：

| 维度 | TF-IDF + Agglomerative | LLM embedding |
|---|---|---|
| 成本 | 0 token，毫秒级 | 100 篇 × 1500 token × 嵌入费 |
| 可解释 | `top_terms` 直接告诉用户每簇关键词 | embedding 是黑盒，topic 名要再调一次 LLM |
| 语义理解 | 中等（够分粗类） | 强（能分细微语义） |
| 多语言混合 | 弱 | 强 |

文献综述 80% 场景是单一语言 + 中等粒度聚类（5-15 簇），TF-IDF 性价比远超 LLM embedding。
真要做"跨语言细粒度聚类"用户可以 fork 替换聚类工具（`literature_reviewer_plugin.py`
的 `cluster_papers_by_topic` 是单一职责函数，OCP 友好）。

### 为什么综述输出**不**自己渲染 docx / pdf？

**SSOT 复用**——SDK 内置 `word_smart_export` 已经有：

- markdown → docx（python-docx）/ pdf（reportlab + CJK 字体）
- 完整样式系统（标题 / 列表 / 表格 / 引用块）
- 错误降级（依赖缺失 → markdown-only 不阻塞）

cookbook 重新实现 = 重复造轮子。LLM 在 ACT step 9-10 调用 `word_smart_export` 即可。

### 为什么 PlagiarismGate 用 5-gram 而不是更复杂的语义相似度？

**学术诚信红线必须可解释**：

- 5-gram 重叠 ≥60% = "复制了 5 词以上的连续短语" 在所有期刊都是清晰红线
- 语义相似度 ≥0.85 = ？ 不同评审 / 不同模型给的分不一样，不能作为 "BLOCK" 依据
- 5-gram 是 Turnitin 等查重产品的工业级实现，研究者熟悉

`detect_plagiarism_overlap` 输出 **命中段落 + 哪句重叠 + 重叠比例**，
LLM 可以根据 reason 精准修改（不是模糊"再改写一下"）。

### 为什么 YearGapHintPlugin 是 hint 不是 Gate？

**风格选择不是红线**：

- 综述按年份分 era 写还是按方法分簇写，不同导师 / 不同期刊偏好不同
- 不该用 BLOCK 强制；用 hint 提醒 LLM "你抽了 1995-2025 跨度 30 年，可能值得分 era"
- LLM 决定要不要按 era 写，最终决策权在 LLM（System 2）

这是 hint vs gate 的标准分界：**红线 → Gate / 偏好建议 → Hint**。

---

## 反模式（禁止）

| 反模式 | 正确做法 |
|---|---|
| ❌ LLM 直接把 PDF 文本塞 prompt 抽元数据 | ✅ 调 `extract_paper_metadata`（pdfplumber + 正则） |
| ❌ LLM 凭感觉"这两篇主题差不多"打 cluster 标签 | ✅ 调 `cluster_papers_by_topic`（TF-IDF 余弦） |
| ❌ 综述里写"参考了大量文献..."但不给具体编号 | ✅ `CitationCompletenessGate` 强制每段 ≥3 引用 |
| ❌ 大段 copy abstract 当综述 | ✅ `PlagiarismGate` 5-gram 60% 阈值会 BLOCK |
| ❌ LLM 直接画 ASCII 引用图 | ✅ 调 `build_citation_graph`（DOT 字符串）+ Graphviz 渲 SVG |
| ❌ 在 cookbook 加 networkx / sklearn 重写聚类 | ✅ 默认纯 Python TF-IDF；用户需要再装 `pip install -e .[ml]` |
| ❌ 在 cookbook 加 python-docx / reportlab 自己渲 docx | ✅ 调 `word_smart_export`（SDK 内置） |
| ❌ 用 hint "请记得每段引用 3 篇" 替代 Gate | ✅ 学术规范必须 System 1 闸住，hint 不够强 |
| ❌ 一次性写完 100+ paper 综述（30K+ token 输出） | ✅ ACT step 5-7 拆段写 + Gate 逐段过 + 累积合并 |

---

## 测试

```bash
pip install -e .[test]
pytest tests/
# 46 passed in <1s
```

测试内容：46 个 System 1 unit test 覆盖元数据抽取边界 / TF-IDF + 聚类正确性 /
引用图 DOT 输出 / N-gram 重叠率计算 / 大纲生成 / ToolPlugin / ACTPlugin
Protocol 契约 / 2 个 GatePlugin 行为（ALLOW / BLOCK / DEFER 与 strict
mode）/ 2 个 HintPlugin 触发条件 / ReviewProgressListener `.progress.jsonl` 输出。

**0 LLM 调用，CI 可频繁跑**（全部 < 1 秒）。

真实 LLM E2E 测试（本地跑，需 `KROW_API_KEY`）：

```bash
pytest tests/test_literature_reviewer_journey_e2e.py -v -s
```

---

## 引用

- 学术规范：APA 7th / IEEE 引用格式
- 学术诚信红线（5-gram 60%）参考 Turnitin
