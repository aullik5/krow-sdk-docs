# ACT · contract_auditor（合同审阅 · 6 步工作流）

> 本 ACT 由 Krow Cookbook v3 PR-C `contract-auditor` 提供。
> 业务场景：企业法务团队 / 采购部 review 商务合同 / NDA / 服务协议，
> 找潜在风险条款 + 出风险报告 + 必要时强制人工 review。
> 详见 `contract_auditor_plugin.py` 与同目录 `README.md`。

---

## 何时进入此 ACT

- 用户提供 1 份合同文件（`docx` / `pdf` / `txt`）
- 任务表述含"合同 review / 审阅 / 风险扫描 / 比对模板"等关键词
- 期望产物：风险报告（markdown / docx / pdf）+ redline + 审计日志

不要在以下场景进入本 ACT：

- 合同**起草**（写新合同）→ 走通用 writer
- 法律咨询 / 司法案件分析 → 走专业法律 ACT（cookbook 不覆盖）

---

## 6 步标准工作流

### Step 1：合同切分

调 `contract_auditor_split_clauses(contract_path=...)`。

**铁律**：

- 不要直接读 PDF 全文塞 prompt（10+ 页合同 = 上下文爆炸）
- 直接传文件路径，工具内部 pdfplumber / python-docx 抽文本

输出：`clauses` 列表（每项含 `clause_id` / `heading` / `text` / offset）。

### Step 2：条款分类

调 `contract_auditor_classify_clauses(clauses=step1.clauses)`。

工具按 15 类 taxonomy 给每条款打 top-3 标签（`liability_limitation` /
`indemnification` / `data_protection_gdpr` / ...）。

**System 1 触发**：
此处 SDK 自动调用 `MandatoryClauseGate.evaluate()`：

- 若分类结果**未命中** `data_protection_gdpr` / `antitrust_competition` /
  `export_control` 任一 → **BLOCK conclude**
- 修法：检查合同确实是否含这 3 类条款；若有但工具漏识别 → 报 bug 加关键词

### Step 3：风险评分

调 `contract_auditor_score_clause_risk(clauses=step1.clauses,
classifications=step2.classifications)`。

工具用 **baseline_risk + 风险加权词命中 + 长度异常** 三因子算 0-1 分：

- `≥0.75` = high；`≥0.50` = medium；< 0.50 = low

**System 2 软提示触发**：
SDK 自动调用 `AmbiguousLanguageHintPlugin.hint_for()`：

- 若合同含 `reasonable / best efforts / asap / 适当` 等模糊用语 →
  推 LLM "在风险报告里点出"

### Step 4：术语索引（可选但强烈推荐）

调 `contract_auditor_index_terms(contract_text=step1 拼接的全文)`。

输出 `defined_terms` / `undefined_terms`（≥2 次使用但未定义的疑似术语）。

**System 2 软提示触发**：
SDK 自动调用 `MissingDefinitionHintPlugin.hint_for()`：

- 若有 ≥1 个 `undefined_terms` → 推 LLM "在风险报告里要求对方补定义"

### Step 5：redline diff（可选 — 仅当传入公司模板）

若用户提供 `template_path`：

- 读模板 → `contract_auditor_redline_diff(template_text=..., contract_text=...)`
- 工具用 `difflib.SequenceMatcher` 给行级 diff（add/remove/keep）
- 输出 `diff_text` 嵌入风险报告"模板偏离"段

不传模板可跳过 step 5。

### Step 6：风险报告生成 + 输出

LLM 起草风险报告 markdown，**必须含**：

1. **执行摘要**（high/medium/low 计数 + 整体风险等级）
2. **必备条款检查**（GDPR / 反垄断 / 出口管制 三段，缺则点出）
3. **高风险条款**（每条单独说明 + 修订建议；若有 ≥1 条 high-risk
   → **必须**写「需法务复核 / REQUIRES LEGAL REVIEW」标记，否则
   `HighRiskBlockingGate` 会 BLOCK）
4. **条款语义风险**（模糊用语 + 未定义术语，结合 hint 输出）
5. **模板偏离**（仅 step 5 跑过时）
6. **建议下一步**（哪些条款需要谈判 / 修改）

落盘：

- `smart_file_write(operation="write", path=md_path, content=<markdown 文本>)` → 落 markdown
- `word_smart_export(file_path=md_path, format="docx", output_path=...)` → md → docx
- `word_smart_export(file_path=md_path, format="pdf", output_path=...)` → md → pdf

**铁律**：写新 markdown 文件必须用 `smart_file_write`；
`word_smart_export` 是格式转换工具（接受已存在的源文件 path），
传 .md 路径不存在 → 内部把空 docx binary 写进 .md → encoding 灾难。

**Gate 二次触发**：

- `HighRiskBlockingGate.evaluate()` 在 conclude 前扫描风险报告：
  - 检测到 ≥1 个 high-risk 条款 + 报告**未含** "需法务复核" 标记 → **BLOCK**
  - 修法：在执行摘要 / 高风险段加 "需法务复核" 标记

---

## 演示的 SDK 能力

本 ACT 是 Cookbook v3 三个 demo 中**最强 Gate 演示**：

- **MandatoryClauseGate**（GDPR / 反垄断 / 出口管制 必备）
- **HighRiskBlockingGate**（≥1 high-risk → 强制人工审核标记）

加上：

- **5 ToolPlugins**（条款切分 / 分类 / 风险评分 / redline / 术语索引）
- **2 HintPlugins**（模糊用语 / 未定义术语）
- **EventListenerPlugin**（法务审计 .audit.jsonl + sha256 文件指纹）
- **ObservabilityPlugin**（OpenTelemetry tracing；与 PR-A Prometheus 互补）
- **BudgetSpec**（推荐 60 LLM × 600s，合同 review 偏交互式不能等太久）

---

## 反模式（**禁止**）

| 反模式 | 正确做法 |
|---|---|
| ❌ LLM 把合同全文塞 prompt | ✅ `split_clauses` 切分后只对 high/medium 条款叙事 |
| ❌ LLM 凭感觉打"高 / 中 / 低"风险 | ✅ `score_clause_risk` 查表 + 风险加权词 |
| ❌ 风险报告写"整体无风险" | ✅ `HighRiskBlockingGate` 检测 ≥1 high-risk 即 BLOCK |
| ❌ 漏审 GDPR / 反垄断 / 出口管制 | ✅ `MandatoryClauseGate` 强制三段必含 |
| ❌ LLM 用 `difflib` 自己拼 redline | ✅ `redline_diff` 工具（SequenceMatcher 严谨） |
| ❌ 在 cookbook 加 reportlab 自己渲 PDF | ✅ `word_smart_export`（SSOT 复用 Krow 内置） |
| ❌ 用 hint "请记得检查 GDPR" 替代 Gate | ✅ 法务红线必须 System 1 闸住 |

---

## 与 PR-A / PR-B 的对照

| 维度 | PR-A 财经 | PR-B 学术 | **PR-C 法务（本 ACT）** |
|---|---|---|---|
| 步骤数 | 8 | 10 | **6**（合同 review 偏快速） |
| 强阻断 Gate | Disclosure / InsiderInfo | Citation / Plagiarism | **Mandatory / HighRisk**（最强） |
| Hint | AnomalyMetric (3σ) | TopicCoverage / YearGap | Ambiguous / MissingDef |
| Observability | Prometheus push gateway | (复用 listener) | **OpenTelemetry tracing** |
| Budget | 80 LLM × 900s | 120 LLM × 1800s | **60 LLM × 600s**（最紧） |

`HighRiskBlockingGate` 是 cookbook 三 demo 中最强的 Gate ——
**直接断 LLM "盖章权"**，不允许自动给"无风险"结论。
