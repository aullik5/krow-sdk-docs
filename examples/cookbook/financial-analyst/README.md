# Cookbook · Financial Analyst Demo

> **投行 / 私募 / 咨询 junior analyst 高频场景**：
> N 家上市公司年报横向对比 + 投资简报生成。
> 演示 SDK 全部 6 类 production plugin（ACTPlugin / ToolPlugin / HintPlugin / GatePlugin / EventListenerPlugin / ObservabilityPlugin）。

---

## 业务背景

投行 / 私募 / 咨询的 junior analyst 每周做一次"行业横向对比 + 投资简报"：
读 3-5 家上市公司年报 → 抽 KPI → 跨公司 / 跨币种归一化 → 雷达图 + 对比表 →
写投资简报（≥5 段，含合规披露段）。

人工每次任务 **8-12 小时**：

- ~3 小时：读 5 份 PDF + 抄 KPI 到 Excel
- ~2 小时：单位 / 币种 / 期数对齐（最容易出错的环节）
- ~3 小时：画雷达图 + 写简报正文 + 配色 + 估值锚

**用本 cookbook 后预期 30-60 分钟**：deterministic 工具承担 KPI 抽取 / 归一化 /
统计 / 几何计算（System 1），LLM 只做业务叙事 / 投资逻辑（System 2）。

---

## 三档跑法

### Tier 1（最小跑通）：单文件 KPI 抽取

```bash
cd financial-analyst
pip install -e .

# Linux / macOS
export KROW_API_KEY=sk-user-xxx
# Windows PowerShell:
# $env:KROW_API_KEY = "sk-user-xxx"
krow-sdk-install --api-key $KROW_API_KEY

python main.py sample_data/company_a.pdf --company-names "公司A"
```

输出：`output/investment_memo.md` —— 单公司简化简报。

### Tier 2（业务可用）：3-5 家公司横向对比 + 雷达图 + PDF

```bash
python main.py sample_data/*.pdf --pdf --target-currency CNY --target-unit 亿
```

新增产物：

- `output/investment_memo.pdf` — 走 SDK 内置 `word_smart_export` 渲染（reportlab + CJK）
- `output/radar_chart.svg` — 雷达图

### Tier 3（合规 / 生产）：守门 + 审计 + Prometheus 集成

```bash
python main.py sample_data/*.pdf \
    --pdf \
    --audit-log output/memo.audit.jsonl \
    --observability \
    --prometheus-url http://prometheus-pushgateway.bi.internal:9091 \
    --budget-llm-calls 80 \
    --budget-walltime 900
```

启用：

- **DisclosureCompletenessGate**：投资简报必须含 5 段（业务概览 / 财务表现 / 行业地位 / 风险因素 / 投资建议），缺段 **BLOCK**
- **InsiderInfoGate**：扫描"内幕 / 未公开 / MNPI"等关键词，命中 **BLOCK**
- **InvestmentMemoAuditListener**：每个工具调用 + Gate BLOCK 落 `.audit.jsonl`
- **FinancialMetricsObservabilityPlugin**：metrics 推 Prometheus push gateway
- **BudgetSpec**：硬约束防 LLM 调用 / 墙钟超支

---

## 演示的 SDK 能力

| Plugin 类型 | 实现类 | 业务理由 |
|---|---|---|
| **ToolPlugin** × 5 | `FinancialAnalystToolPlugin` | KPI 抽取 / 归一化 / 行业基线 / 雷达图 / 估值锚 全部是 deterministic 算法（LLM 凭感觉算 ROE 会出 100× 数量级事故） |
| **ACTPlugin** | `FinancialAnalystACTPlugin` | 8 步标准工作流让 LLM 跟着走 |
| **GatePlugin** × 2 | `DisclosureCompletenessGate` `InsiderInfoGate` | 信披要求 + 内幕信息红线；hint 提醒不够，必须 System 1 闸住 |
| **HintPlugin** | `AnomalyMetricHintPlugin` | LLM 凭感觉看 KPI 表区分不了 3% vs 30% vs 300% 偏差，必须 σ 标尺 |
| **EventListenerPlugin** | `InvestmentMemoAuditListener` | 金融行业每次输出 + Gate BLOCK 必须留痕（合规审计 / SOX） |
| **ObservabilityPlugin** | `FinancialMetricsObservabilityPlugin` | 投行内 BI dashboard 看 SLA / 容量 / 异常率（Prometheus push gateway） |

---

## 文件结构

```
financial-analyst/
├── README.md                        # 本文档
├── pyproject.toml                   # name = krow-cookbook-financial-analyst
├── main.py                          # CLI 入口（三档跑法）
├── financial_analyst_plugin.py      # 全部 plugin 实现（5 tools + 6 plugin classes）
├── act_assets/financial_analyst/
│   └── ext_financial_analyst.md     # ACT 8 步工作流
├── sample_data/
│   └── README.md                    # 自助跑通指南（不预置 PDF）
├── tests/
│   ├── conftest.py
│   └── test_financial_analyst_smoke.py  # 53 unit test（System 1 only · 0 LLM 调用）
└── .gitignore                       # 排除 output/ *.pdf *.audit.jsonl
```

---

## 关键设计权衡（Trade-offs）

### 为什么不用 LLM 直接看 PDF 抽 KPI？

LLM 抽 KPI 漂移率 **1-3%** 且**单位错位灾难**：

- "营业收入 245.76 **亿元**" vs "营业收入 245.76 **百万元**" 数量级差 **100×**
- LLM 把"营业**总**收入"和"营业收入"当一回事 → 口径差 **5-15%**

本 cookbook 用 `KPI_DICT` + `UNIT_DICT` 字典查表，零漂移。

### 为什么 PDF 输出**不**自己渲染（不引 fpdf2 / reportlab 依赖）？

**SSOT 复用**——SDK 内置 `word_smart_export` 已经有：

- CJK 字体处理（reportlab CJK 字体注册 + 中文换行 + 标点处理）
- markdown 完整样式系统（标题 / 列表 / 表格 / 代码块）
- 错误降级（reportlab 缺失 → markdown-only 不阻塞）

cookbook 重新实现 PDF 渲染 = 重复造轮子。LLM 在 ACT step 7 调用 `word_smart_export` 即可。

### 为什么 `radar_chart_svg` 是 SVG 字符串而不是文件路径？

LLM 友好——SVG 字符串可以：

- 直接嵌入 markdown 段落
- 由 `word_smart_export` 自动转 base64 嵌入 PDF
- 可被 LLM "看见"内容（虽然 LLM 不读 SVG 像素，但便于 debug）

文件路径 = 必须用 `read_file` 才能验证内容，多一步且打断 ReACT 循环。

### 为什么 ObservabilityPlugin 选 Prometheus？

财经 BI dashboard 主流是 **Prometheus + Grafana**（投行 IT 部署最多）；
contract-auditor demo 演示 **OpenTelemetry**（企业法务侧主流），两个 demo 各演示一种 sink，覆盖真实生态。

### 为什么不直接接 Wind / Bloomberg API 拿真实市值？

**Cookbook 的目标是演示 SDK，不是构建生产 BI 系统**：

- 真实接 Wind / Bloomberg 需要 token / 计费 / 网络代理
- 让 demo 在任何环境跑通比"集成生产数据源"重要
- 用户 fork 后**自己接** Wind API 替换 `valuation_anchor` 入参即可

---

## 反模式（禁止）

| 反模式 | 正确做法 |
|---|---|
| ❌ LLM 直接看 PDF 文本抽 KPI | ✅ 调 `extract_kpi_from_pdf`（dict 查表 + 单位识别） |
| ❌ LLM 凭感觉算"24,576 百万 vs 24,576 亿" | ✅ 调 `normalize_kpi_table` 强制单位归一 |
| ❌ LLM 自己算 polygon 顶点画雷达图 | ✅ 调 `radar_chart_svg`（System 1 几何） |
| ❌ 简报里写"根据内幕信息..." | ✅ `InsiderInfoGate` 会 BLOCK；只用年报已公开数据 |
| ❌ 简报缺风险段直接 conclude | ✅ `DisclosureCompletenessGate` 会 BLOCK；补齐 5 段后重写 |
| ❌ 在 cookbook 加 fpdf2 / reportlab 自己渲 PDF | ✅ 调 `word_smart_export`（SDK 内置） |
| ❌ 用 hint "请记得写风险段" 替代 Gate | ✅ 法务红线必须 System 1 闸住，hint 不够强 |
| ❌ 不算行业基线就让 LLM 凭感觉判断"高 / 低" | ✅ `industry_baseline` + `AnomalyMetricHint` 推 σ 偏差信号 |

---

## 测试

```bash
pip install -e .[test]
pytest tests/
# 53 passed in <1s
```

测试内容：53 个 System 1 unit test 覆盖 KPI 字典完整性 / 数字解析边界 /
单位检测 / 跨币种归一化 / 行业基线统计 / 雷达图 SVG 输出 / 估值锚边界 /
ToolPlugin / ACTPlugin Protocol 契约 / 2 个 GatePlugin 行为 /
AnomalyMetricHintPlugin 触发条件 / AuditEventListener `.audit.jsonl` 输出 /
ObservabilityPlugin 降级模式。

**0 LLM 调用，CI 可频繁跑**（全部 < 1 秒）。

真实 LLM E2E 测试（本地跑，需 `KROW_API_KEY`）：

```bash
pytest tests/test_financial_analyst_journey_e2e.py -v -s
```
