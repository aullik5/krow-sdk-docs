# 知识编译工作室 ACT — 扩展指南

## 本 ACT 的定位

本 ACT 是 Krow SDK Cookbook 的第 1 个**知识管理**类 demo（详 `COOKBOOK_DESIGN.md` §2.4），
覆盖**知识工作者 / 研究团队 / 企业知识库管理员**的高频任务：一批领域资料 →
结构化知识库（本体 Ontology）+ 可浏览互链的百科词条（wiki）。

与前 4 个 cookbook 的**本质差异**：

| 维度 | financial / literature / contract / data | knowledge-wiki |
|---|---|---|
| 核心工作由谁做 | cookbook 自带领域工具（KPI/聚类/条款分类） | **Krow 引擎内置工具**（本体抽取 + wiki 编译） |
| cookbook 工具角色 | 主力 | **辅助**（ingest 规划 + 覆盖验收） |
| 驱动方式 | ACT 步骤 | ACT + `task_context.strategy="knowledge_compile"` 三阶段契约 |

**关键**：本 cookbook 严守 SSOT——抽本体用内置 `extract_entities_from_text`，
写词条用内置 `wiki_info` + `smart_file_write`，**不重复造这些轮子**。cookbook 的
两个工具（`scan_sources` / `coverage_report`）只补内置工具没有的"ingest 规划"
和"本体↔wiki 覆盖验收"环节。

## 推荐工作流（知识编译三阶段 + 规划/验收）

### 0. **`knowledge_wiki_scan_sources(docs_dir)`** — 确定性 ingest 规划

- 递归扫描资料目录 → 产出可编译源清单（path / ext / size / est_chunks）
- 自动排除 `.krow/`（引擎产出物，防自激环）+ 过小占位文件
- **为什么必要**：内置工具没有"我该编入哪些文件"的规划器；让 LLM 自己 ls 会
  漏文件 / 把 wiki 产出物反向编入

### 1. **抽取阶段（extract）** — `extract_entities_from_text`

- 对清单里**每个源文件**调用一次，把概念 / 实体 / 事件写入 GlobalOntology
- **铁律**：不要把源文件全文塞进 prompt（上下文爆炸）；让工具读文件
- 同时隐式写入 DocumentChunk + appears_in 关系（供后续溯源）

### 2. **关联阶段（relate）** — `add_relation`

- 每个核心概念**至少 1 条**向上 `is_a`（建立分类骨架，否则 graph 视图层级聚合失效）
- 关键实体之间补领域 specific 关系：`causes` / `part_of` / `uses` / `depends_on`
- 失败时（schema 拒绝）用 `summarize_ontology` 看 advice 改用合法 kind

### 3. **发布阶段（publish）** — `wiki_info(get_template)` + `smart_file_write`

- 对核心概念 / 实体**逐个**建页：先 `wiki_info(operation="get_template")` 拿模板
- `smart_file_write` 写 `.krow/wiki/{concepts|entities|comparisons}/名称.md`
- frontmatter 必填 `title/tags/sources/status/type`；status 仅 `{draft,reviewed,mature,archived}`
- 必含 H2 骨架（concept 页：`## 定义 / ## 重要属性 / ## 关联 / ## 参考`）
- wiki-link 用相对路径 + 语义标注：`[[concepts/foo.md|rel:depends_on]]`

### 4. **验收阶段** — `knowledge_wiki_coverage_report`

- 交叉核对本体核心节点数（概念+实体）vs wiki 页数 → 覆盖率
- `under_populated=true` → **WikiCoverageGate 会 BLOCK**，必须补写词条
- **为什么必要**：内置 `summarize_ontology` 只看本体、`wiki_info(validate)` 只 lint
  wiki，**没人做"本体↔wiki 覆盖"核对**——这正是"编译完词条有没有变丰富"的度量

### 5. **lint + 总览** — `wiki_info(validate)` + `summarize_ontology`

- `wiki_info(operation="validate")` 检查 frontmatter / H2 / wiki-link 健康
- `summarize_ontology` 给编译总结

## SDK 高级能力演示

### GatePlugin 演示要点（WikiCoverageGate）

| Gate | 守的什么 | 触发后 LLM 应该怎么做 |
|---|---|---|
| `WikiCoverageGate` | 本体有核心节点但 wiki 页 < 阈值（假编译） | 看 reason → 用 get_template 对核心节点逐个建页 → 重调 coverage_report |

**为什么不能用 hint 替代**：真实用户反馈"编译完没感觉词条变丰富"，根因正是
本体抽完但词条几乎没写。hint 提醒 LLM "记得写 wiki" 在压缩任务时会被跳过；
必须 System 1 在 conclude 前闸住。

### EventListenerPlugin 演示要点（CompileProgressListener）

- 按工具名归类三阶段进度：extract（`extract_entities_from_text`）/
  relate（`add_relation`）/ publish（`smart_file_write`）
- 实时 print + 可选写 `.progress.jsonl` 审计

### BudgetSpec 演示要点

知识编译推荐预算（对齐内置 `knowledge_compile` 契约）：

```python
BudgetSpec(
    max_total_llm_calls=120,   # 多文件抽本体 + 多页 wiki
    max_walltime_s=3600,       # 编译是长任务
    max_replans=8,             # gate BLOCK + 关系 schema 修正各留余量
)
```

## 反模式

| 反模式 | 正确做法 |
|---|---|
| ❌ LLM 把源文件全文塞 prompt 抽概念 | ✅ 调 `extract_entities_from_text`（工具读文件） |
| ❌ 自己写一个本体抽取 / wiki 写入工具 | ✅ 复用内置 `extract_entities_from_text` / `wiki_info` / `smart_file_write`（SSOT） |
| ❌ 把 `.krow/wiki` 产出页再次编入 | ✅ ingest 清单以 `knowledge_wiki_scan_sources` 为准（已排除 .krow） |
| ❌ 抽完本体就 conclude，不写词条 | ✅ WikiCoverageGate 会 BLOCK；按 coverage_report 补写 |
| ❌ status 写 `published` / `active` | ✅ 仅 `{draft,reviewed,mature,archived}` |
| ❌ wiki-link 用裸 slug / 中文标签 | ✅ 相对路径 + slug：`[[entities/inverter.md]]` |
| ❌ 概念页没有向上 is_a | ✅ 每个 concept 至少 1 条 `is_a`（分类骨架） |

## 引用

- 设计文档：`packages/krow-agent-sdk/examples/cookbook/COOKBOOK_DESIGN.md` §2.4
- 内置编译 E2E 金标准：`tests/fixtures/expected_cards/journey_wiki_compile_medical_v2.yaml`
- 编译策略 SSOT：`modules/knowledge/reasoning_strategies.py::Strategy(id="knowledge_compile")`
- 内置 wiki ACT：`modules/agent/act/acts/wiki_compiler/__act__.yaml`
- TURBO 哲学：`AGENTS.md` §0.1
