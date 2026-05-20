# Cookbook · Contract Auditor Demo

> **企业法务 / 采购部高频场景**：商务合同 / NDA / 服务协议风险审阅 + redline + 合规审计。
> 演示 SDK 全部 6 类 production plugin，特别是**最强 Gate 演示**（`HighRiskBlockingGate` 直接断 LLM "盖章权"）+ OpenTelemetry tracing 集成。

---

## 业务背景

企业法务团队 / 采购部每周 review 5-15 份合同——
读合同 → 找潜在风险条款 → 与公司模板比对 → 出风险报告 + redline →
若发现高风险条款交给资深法务复核。

人工每次任务 **2-4 小时 / 合同**：

- ~30 min：通读 docx / pdf + 用 Word 标黄高风险条款
- ~30 min：与公司模板逐条对比，写 redline
- ~30 min：写风险报告（执行摘要 / GDPR 检查 / 反垄断 / 出口管制 ...）
- ~30 min：审计留痕 + 等资深法务排期复核

**用本 cookbook 后预期 15-30 分钟 / 合同**：deterministic 工具承担条款切分 /
分类 / 风险评分 / redline diff（System 1），LLM 只做风险叙事 / 修订建议（System 2）。

**最关键**：`HighRiskBlockingGate` 让 LLM **不能**自动给"无风险"结论，必须显式
标记 "需法务复核" —— 这是法务事故的最后一道防线。

---

## 三档跑法

### Tier 1（最小跑通）：1 份合同 → 风险报告 markdown

```bash
cd contract-auditor
pip install -e .

# Linux / macOS
export KROW_API_KEY=sk-user-xxx
# Windows PowerShell:
# $env:KROW_API_KEY = "sk-user-xxx"
krow-sdk-install --api-key $KROW_API_KEY

python main.py sample_data/contract.docx
```

输出：`output/risk_report.md` —— 单合同风险报告 markdown。

### Tier 2（业务可用）：合同 + 公司模板 → redline + docx

```bash
python main.py sample_data/contract.docx \
    --template sample_data/template.docx \
    --docx
```

新增产物：

- `output/risk_report.docx` — 走 SDK 内置 `word_smart_export`（reportlab + CJK）
- 报告内含「模板偏离」段（基于 `redline_diff` 输出 add/remove 计数）

### Tier 3（合规 / 生产）：审计 jsonl + OTel tracing + 严格守门

```bash
python main.py sample_data/contract.docx \
    --template sample_data/template.docx \
    --docx --pdf \
    --audit-log output/contract.audit.jsonl \
    --observability \
    --otlp-endpoint http://otel-collector.legal.internal:4317 \
    --high-risk-threshold 0.70 \
    --budget-llm-calls 60 \
    --budget-walltime 600
```

启用：

- **MandatoryClauseGate**（strict=BLOCK）：必含 GDPR / 反垄断 / 出口管制，缺则 BLOCK
- **HighRiskBlockingGate**（thr=0.70）：≥1 high-risk + 缺人工审核标记 → BLOCK
- **AmbiguousLanguageHintPlugin**：reasonable / best efforts / asap 等模糊用语提醒
- **MissingDefinitionHintPlugin**：引号包裹但 ≥2 次未定义术语提醒
- **LegalAuditTrailListener**：每次工具调用 + Gate BLOCK + sha256 文件指纹 →
  `.audit.jsonl`（SOX / 公司合规审计强制留痕）
- **OTelTracingObservabilityPlugin**：每个 tool 一个 span + Gate BLOCK 标 ERROR；
  推 OTLP collector → Jaeger / Tempo / Datadog APM
- **BudgetSpec**：60 LLM × 600s（合同 review 偏交互式不能等太久）

---

## 演示的 SDK 能力

| Plugin 类型 | 实现类 | 业务理由 |
|---|---|---|
| **ToolPlugin** × 5 | `ContractAuditorToolPlugin` | 条款切分 / 15 类分类 / 风险评分 / redline / 术语索引 全部 deterministic（LLM 凭感觉打风险等级会出"高风险打成中风险"事故） |
| **ACTPlugin** | `ContractAuditorACTPlugin` | 6 步标准工作流（合同 review 偏快速） |
| **GatePlugin** × 2（**最强**） | `MandatoryClauseGate` `HighRiskBlockingGate` | 法务红线必须 System 1 闸住——MandatoryClauseGate 强制 GDPR/反垄断/出口管制三类必含；HighRiskBlockingGate 直接断 LLM "盖章权"——不允许自动给"无风险"结论 |
| **HintPlugin** × 2 | `AmbiguousLanguageHintPlugin` `MissingDefinitionHintPlugin` | LLM 看到 reasonable / best efforts 不会自动联想风险；hint 推一把 |
| **EventListenerPlugin** | `LegalAuditTrailListener` | 法务 review 是 SOX / 公司合规强制留痕场景；含合同 sha256 文件指纹保证可追溯 |
| **ObservabilityPlugin** | `OTelTracingObservabilityPlugin` | 企业 IT 普遍用 OpenTelemetry —— 每个工具一个 span 方便事后审计 / 性能调优 / 异常定位 |

---

## 文件结构

```
contract-auditor/
├── README.md                          # 本文档
├── pyproject.toml                     # name = krow-cookbook-contract-auditor
├── main.py                            # CLI 入口（三档跑法）
├── contract_auditor_plugin.py         # 全部 plugin 实现（5 tools + 7 plugin classes）
├── act_assets/contract_auditor/
│   ├── __act__.yaml                   # ACT frontmatter
│   └── ext_contract_auditor.md        # ACT 6 步工作流
├── sample_data/
│   └── README.md                      # 自助跑通指南（不预置合同 · 公开模板推荐）
├── tests/
│   ├── conftest.py
│   └── test_contract_auditor_smoke.py # 50 unit test（System 1 only · 0 LLM 调用）
└── .gitignore                         # 排除 output/ *.pdf *.docx *.audit.jsonl
```

---

## 关键设计权衡（Trade-offs）

### 为什么不用 LLM 直接看合同打风险等级？

LLM 抽风险**漂移率高且严重低估**：

- LLM 看到 "Vendor liability is unlimited" 会按训练分布给出 "标准条款" 等错判
- 100 份合同实测：LLM 漏报 high-risk 率 **15-30%**，远高于规则引擎的 < 1%
- 法务事故"漏审 GDPR Art.28 被罚"通常 7 位数美元起 —— 任何漏报都不能容忍

本 cookbook 用 `CLAUSE_TAXONOMY`（15 类查表）+ `RISK_AMPLIFIERS_*`（中英双语）+
长度异常三因子算分，零漂移、可解释、可审计。

### 为什么 `HighRiskBlockingGate` 这么"强"（不让 LLM conclude）？

**法务事故的最后一道防线**：

- LLM 在 ReACT 循环里有"想结案"的 bias —— 看到风险也倾向给"整体可控"结论
- 法务 review 的核心价值是"找到风险" + "明确告诉法务团队哪里需要复核"
- Gate 强制要求报告里写 `需法务复核` / `REQUIRES LEGAL REVIEW` 标记 → 让 LLM
  必须显式承认 "我标了高风险，需要人来看"
- **直接断 LLM "盖章权"** —— 这是 cookbook 中最强的 Gate

### 为什么 redline 用 `difflib.SequenceMatcher` 不用 LLM？

按场景划分边界：

| 维度 | difflib | LLM |
|---|---|---|
| 准确率 | 100%（行级精确）| 70-85%（漏 / 错位） |
| 成本 | 0 token，毫秒级 | 模板 5K + 合同 5K = 10K token |
| 可审计 | unified diff 标准格式 | LLM 输出格式漂移 |
| 顺序保证 | 严格保留顺序 | 可能乱序 |

合同 redline 是法律文件**精确比对**场景，必须 deterministic。LLM 只需要在
风险报告里基于 diff 写**叙事**（"模板要求 cap $1M，合同改成 unlimited"）。

### 为什么 ObservabilityPlugin 选 OpenTelemetry？

企业法务 / 合规侧主流是 **APM (OpenTelemetry → Jaeger / Tempo / Datadog)**；
financial-analyst demo 演示 Prometheus push gateway（投行 BI 主流），两个 demo 各演示一种 sink，覆盖真实生态。

### 为什么 `LegalAuditTrailListener` 要算合同 sha256？

**审计可追溯性**：

- SOX / 公司合规要求审计日志能证明"我审的是这份合同，不是别的"
- 文件 sha256 + 时间戳 + actor (USERNAME) 让审计员能验证完整性
- 未来若合同被篡改 / 替换，sha256 不匹配立即暴露
- 这是法务 review 与"普通文档处理"的最大差异

### 为什么 `AMBIGUOUS_PHRASES` 是 hint 不是 Gate？

**条款语义风险是建议级而非红线**：

- "reasonable" / "best efforts" 在某些 jurisdiction 是合法的标准条款
- BLOCK 会过分阻塞合理的合同
- Hint 推 LLM "在风险报告里点出，让法务团队判断" 是更合理的处理方式

---

## 反模式（禁止）

| 反模式 | 正确做法 |
|---|---|
| ❌ LLM 直接把合同全文塞 prompt 打风险等级 | ✅ 调 `split_clauses` → `classify_clauses` → `score_clause_risk` |
| ❌ LLM 凭感觉判断"GDPR 合规没问题" | ✅ `MandatoryClauseGate` 强制三类必含 |
| ❌ LLM 给"整体无风险"结论 | ✅ `HighRiskBlockingGate` 检测到 ≥1 high-risk + 无 marker → BLOCK |
| ❌ LLM 用 diff 自己拼 redline | ✅ `redline_diff` 工具（SequenceMatcher 严谨） |
| ❌ 把内部合同提交到本仓 | ✅ 脱敏后放本地 / `.gitignore` 已忽略 `*.docx` `*.pdf` |
| ❌ 在 cookbook 加 reportlab 自己渲 PDF | ✅ `word_smart_export`（SDK 内置） |
| ❌ 用 hint "请记得检查 GDPR" 替代 Gate | ✅ 法务红线必须 System 1 闸住 |
| ❌ 审计日志只记 tool_calls，不算 sha256 | ✅ `LegalAuditTrailListener` 算合同文件指纹 |
| ❌ 跑 100+ 页大型合同不限制 budget | ✅ 必填 `--budget-llm-calls 60 --budget-walltime 600`，超大合同先按 schedule 拆 |

---

## 测试

```bash
pip install -e .[test]
pytest tests/
# 50 passed in <1s
```

测试内容：50 个 System 1 unit test 覆盖：

- 通用 helpers（`_normalize_path` / `_golden_error`）
- `CLAUSE_TAXONOMY` 完整性（15 类 / 必备 3 类 / 高风险 6 类 / 双语关键词）
- `split_clauses` 切分边界（heading 多种格式 / 空文本 / 不存在路径）
- `classify_clauses` 标签准确性（中英双语 / 命中 vs misc_other）
- `score_clause_risk` 风险分（baseline + amplifier + 长度异常 + clip 上下界）
- `redline_diff` add/remove/keep 计数
- `index_terms` 已定义 / 未定义 / 引号包裹但只用 1 次跳过
- ToolPlugin / ACTPlugin Protocol 契约
- **`MandatoryClauseGate`** 行为（ALLOW / BLOCK / DEFER + strict mode）
- **`HighRiskBlockingGate`** 行为（无 high-risk → ALLOW / 有但无 marker → BLOCK /
  有且有 marker → ALLOW / 阈值可配）
- `AmbiguousLanguageHintPlugin` / `MissingDefinitionHintPlugin` 触发条件
- `LegalAuditTrailListener` `.audit.jsonl` 输出 + sha256 文件指纹

**0 LLM 调用，CI 可频繁跑**（全部 < 1 秒）。

真实 LLM E2E 测试（本地跑，需 `KROW_API_KEY`）：

```bash
pytest tests/test_contract_auditor_journey_e2e.py -v -s
```

---

## 引用

- 合规依据：GDPR Article 28 / PIPL §52 / 反垄断法 §13-14 / EAR / OFAC sanctions
- SOX 审计：Section 404 internal control documentation
