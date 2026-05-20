---
name: financial_analyst
display_name: 财经分析员（Financial Analyst）
description: |
  当用户提供 N 家上市公司年报 PDF（或 XBRL 数据）且要"行业横向对比 / 投资简报 /
  KPI 抽取 / 估值锚 / 雷达图"时进入此 ACT。
  本 ACT 内 Agent 会：
  - 用 deterministic 工具从年报 PDF 抽 KPI（不让 LLM 凭感觉抽，避免单位错位）
  - 用 normalize_kpi_table 拉平到同币种同单位（横向对比的前提）
  - 用 industry_baseline 算行业 mean/std/quartiles（HintPlugin 据此推 3σ 信号）
  - 用 radar_chart_svg 生成雷达图（System 1 几何，不让 LLM 算 cos/sin）
  - 用 valuation_anchor 算 PE/PB/PS + 行业对比 verdict
  - 在合规守门 (DisclosureCompletenessGate / InsiderInfoGate) 监督下产出投资简报
when_to_enter:
  - "用户提到 上市公司年报 / annual report / 10-K / 招股书"
  - "用户提到 投资简报 / 投资逻辑 / 投资建议 / IPO 研究"
  - "用户提到 KPI 对比 / 财务指标 / 营收 / 利润 / 毛利率 / ROE"
  - "用户提到 行业对比 / 同行对标 / peer comparison"
  - "用户上传了多份 PDF 文件并要求横向比较"
  - "用户提到 估值 / PE / PB / PS / 雷达图"
tools:
  - financial_analyst_extract_kpi_from_pdf
  - financial_analyst_normalize_kpi_table
  - financial_analyst_industry_baseline
  - financial_analyst_radar_chart_svg
  - financial_analyst_valuation_anchor
  - word_smart_export
priority: 10
---

# 财经分析员 ACT — 扩展指南

## 本 ACT 的定位

本 ACT 是 Krow SDK Cookbook v3 的第 1 个 demo（详 ``COOKBOOK_DESIGN.md`` §2.1），
覆盖**真实投行 / 私募 / 咨询 junior analyst 的高频任务**：横向对比 N 家公司
年报 + 写投资简报。

与 v2 data-analyst（auditor scope）的差别：

| 维度 | data-analyst (v2) | financial-analyst (v3) |
|---|---|---|
| 输入 | 单 CSV 文件 | 多家公司年报 PDF |
| 核心算法 | 异常检测 / 相关性 | KPI 抽取 / 单位归一化 / 行业基线 / 估值 |
| Gate | PII / OutputPath（数据合规） | DisclosureCompleteness / InsiderInfo（金融行业法律） |
| Hint | DataInsight（时序列 / 高基数） | AnomalyMetric（3σ 行业偏差） |
| Observability | ❌ | ✅ Prometheus push gateway |

## 推荐工作流（**8 步**，含合规守门触发点）

### 1. **`financial_analyst_extract_kpi_from_pdf(path, company_name?)`** — 从每份年报抽 KPI

- 对每家公司**分别调用一次**
- LLM 看到 missed 列表（缺哪些 KPI）后可以决定是否补抽（如重传 target_kpis= 列表）
- **铁律**：不要让 LLM 凭眼睛看年报抽 KPI——单位错位（亿 vs 百万）会导致投资判断
  错 100 倍。本工具用 KPI_DICT + UNIT_DICT 字典查表，零漂移
- 错误降级：PDF 是扫描件无文本层时报"先 OCR"；pdfplumber/PyMuPDF 缺时给安装命令

### 2. **`financial_analyst_normalize_kpi_table(companies, target_currency, target_unit)`** — 拉平到同口径

- 把 step 1 多家公司输出收集为 `[{"company": ..., "kpis": ...}, ...]` 传入
- target_currency 默认 "CNY"；target_unit 默认 "亿"
- **铁律**：横向对比前**必须**先归一化；否则 USD-million × CNY-亿元 直接相加 = 数量级灾难
- 输出 ``period_warnings`` 提示用户"公司 A 是 2023 H1 vs 公司 B 2024 全年"等期数不齐情况

#### **数据 schema 重要约定（防 LLM 误读 · W5 实测踩坑修复）**

```yaml
table[i]:
  revenue: float        # 单位 = target_unit（亿/百万/万/元；默认"亿"），CNY
  net_profit: float     # 单位 = target_unit（亿/百万/万/元；默认"亿"），CNY
  gross_margin: float   # 百分比形式（如 42.5 表示 42.5%），不要 ÷100
  roe: float            # 百分比形式（如 18.1 表示 18.1%），不要 ÷100
  debt_to_equity: float # 百分比形式（如 32.0 表示 32%），不要 ÷100
  rd_ratio: float       # 百分比形式（如 5.5 表示 5.5%），不要 ÷100
```

- ⚠️ **铁律**：ratio 类 KPI（``gross_margin`` / ``roe`` / ``rd_ratio`` / ``debt_to_equity``）的数值
  **已经是百分比形式**（如 ``42.5`` 表示 ``42.5%``）.
- ⚠️ 写报告时**直接用** `f"{value}%"` 即可；**禁止再 ÷100 或 ×100** 转换.
- ⚠️ industry_baseline 的 ``mean`` / ``median`` 等统计量同样保持百分比形式.
- 实测踩坑（2026-05-19）：LLM 凭感觉把 ``gross_margin = 42.5`` 误读成
  ``42.5 × 10⁻⁶`` → 报告写"毛利率 0.0000425%" → 投资判断完全错位.

### 3. **`financial_analyst_industry_baseline(normalized_table)`** — 算行业基线

- 自动对全部数值列算 mean / median / std / q1 / q3 / min / max
- 样本 < 2 家公司时该 KPI 标记 sparse（HintPlugin 自动跳过）
- **HintPlugin AnomalyMetric 触发条件**：本工具输出后 + 归一化表都在 context →
  hint 自动算每家公司每个 KPI 的 σ 偏差，把 |σ| ≥ 2 的列出来

### 4. **`financial_analyst_radar_chart_svg(normalized_table, kpi_ids)`** — 生成雷达图

- 选 5-8 个核心 KPI 维度（建议 revenue/net_profit/gross_margin/roe/operating_cash_flow）
- 输出 SVG 字符串（可直接嵌入 markdown 或交给 word_smart_export 渲染）
- **System 1 几何**：cos / sin 都是工具算的；LLM 不应自己写 polygon points

### 5. **`financial_analyst_valuation_anchor(company, market_cap, net_profit, ...)`** — 估值锚

- 对**每家公司**分别调一次
- 必须传 market_cap / net_profit；book_value 和 revenue 可选（缺则不算 PB / PS）
- 传 industry_pe_median / industry_pb_median 启用行业对比 verdict
- **铁律**：估值倍数必须工具算；LLM 算"市值 / 净利润"会粗心错位（亏损公司 PE 应返 None
  而不是负数 / 无穷大）

### 6. **基于以上数据写中文投资简报 markdown**（System 2，LLM 在 ReACT 循环内组织）

- **5 段标准披露结构**（DisclosureCompletenessGate 守门铁律）：
  ① **业务概览** —— 公司主营业务 / 核心产品 / 商业模式
  ② **财务表现** —— 用 step 2 归一化数据 + step 3 行业基线对比；
     在 HintPlugin 推的偏差信号处单独点出"亮点 / 风险候选"
  ③ **行业地位** —— 用 step 4 雷达图说明对手优劣势
  ④ **风险因素** —— 至少 3 类（业务 / 财务 / 行业 / 政策），每类 1-2 句
  ⑤ **投资建议** —— 基于 step 5 估值锚 + 综合上述给"买入 / 持有 / 卖出"verdict

- **InsiderInfoGate 守门铁律**：**禁止**简报里出现"内幕 / 未公开 / 尚未披露 /
  inside information / non-public" 等关键词。所有数据必须来自年报已公开内容。
  违反 = BLOCK + 重写

### 7. **PDF 渲染**（可选）

- 调用 Krow 内置 ``word_smart_export(file_path=<md>, format='pdf', output_path=<pdf>)``
- 内置工具自带 CJK 字体处理 + reportlab 后端；reportlab 缺失时会输出降级提示
- **不要在本 cookbook 引入 fpdf2 / reportlab 依赖**——SSOT 复用 Krow 内置

### 8. **审计留痕 + Observability metric**（自动；无需 LLM 主动调用）

- InvestmentMemoAuditListener 已订阅 EventBus 自动写 .audit.jsonl
- FinancialMetricsObservabilityPlugin 已订阅 metric / audit sinks 自动 forward
  到 Prometheus push gateway
- **重点**：每次 GatePlugin BLOCK 都被记录（合规审计要求）+ counter 累加
  （`financial_gate_blocked_total{gate_name=...}`）

## SDK 高级能力演示

### GatePlugin × 2 演示要点

| Gate | 守的什么 | 触发后 LLM 应该怎么做 |
|---|---|---|
| `DisclosureCompletenessGate` | 投资简报必须含 5 段标准披露 | 看 reason 里"缺哪几段"清单 → 补齐对应段 + 重新 write_report |
| `InsiderInfoGate` | 简报含"内幕 / 未公开 / MNPI"等关键词 | 删除违规段落改为只引用年报已公开内容 → 重新 write_report |

### HintPlugin 演示要点

`AnomalyMetricHintPlugin(sigma_threshold=2.0)` 是 v3 cookbook 的核心 hint 演示：

- **场景**：industry_baseline + normalize_kpi_table 都在 context 时自动激活
- **输出**：top 8 偏离 ≥2σ 的 (公司, KPI) 对，按 |σ| 降序排列
- **真实业务价值**：投行简报最大价值在"找到行业内的极端值"——这恰好是
  statistics 的核心；LLM 凭感觉看 KPI 表区分不了"3% 偏差是噪音 / 30% 偏差是亮点 /
  300% 偏差是异常报错"

### ObservabilityPlugin 演示要点（v2 没有的能力）

`FinancialMetricsObservabilityPlugin(push_gateway_url=...)`：

- **真实业务**：投行内 BI dashboard / Grafana 看简报生产线 SLA / 容量 / 异常率
- **Demo 模式**：未装 prometheus-client 时降级 stdout（仍演示完整数据流）
- **生产模式**：传入 push gateway URL 后自动每个 metric event 都 PUT
- **特别 audit metric**：``financial_gate_blocked_total{gate_name}`` —— 让 BI
  能跟踪合规风险趋势

### BudgetSpec 演示要点

财经分析任务推荐预算：

```python
BudgetSpec(
    max_total_llm_calls=80,    # 5 公司 × 10-15 次 LLM call ≈ 50-75
    max_walltime_s=900,        # 15 分钟（含 PDF 抽取耗时）
    max_replans=2,             # KPI 抽错 / 简报缺段时允许 2 次 replan 修正
)
```

为什么这些数字：

- 80 LLM calls：每家公司 ~10-15 次（KPI 解读 + 简报段落起草 + Gate 拦截后 replan）；
  超出说明 LLM 陷入循环或 ACT 流程没收敛
- 900s 墙钟：5 个 PDF × ~30s 抽取 + LLM 拼简报 ~5 min + 渲染 PDF ~30s ≈ 800s；
  留 100s buffer
- 2 replan：DisclosureCompletenessGate / InsiderInfoGate 各允许 1 次拦截；多了
  说明 LLM 没理解修法，应人工介入

## 反模式

| 反模式 | 正确做法 |
|---|---|
| ❌ LLM 直接看 PDF 文本抽 KPI | ✅ 调 ``extract_kpi_from_pdf``（dict 查表 + 单位识别） |
| ❌ LLM 凭感觉算"24,576 百万 vs 24,576 亿" | ✅ 调 ``normalize_kpi_table`` 强制单位归一 |
| ❌ LLM 自己算 polygon 顶点画雷达图 | ✅ 调 ``radar_chart_svg``（System 1 几何） |
| ❌ 简报里写"根据内幕信息..." | ✅ InsiderInfoGate 会 BLOCK；只用年报已公开数据 |
| ❌ 简报缺风险段直接 conclude | ✅ DisclosureCompletenessGate 会 BLOCK；补齐 5 段后重写 |
| ❌ 在 cookbook 加 fpdf2 / reportlab 自己渲 PDF | ✅ 调 ``word_smart_export``（SSOT 复用 Krow 内置） |
| ❌ 用 hint "请记得写风险段" 替代 Gate | ✅ 法务红线必须 System 1 闸住，hint 不够强 |
| ❌ 不算行业基线就让 LLM 凭感觉判断"高 / 低" | ✅ industry_baseline + AnomalyMetricHint 推 σ 偏差信号 |

## 引用

- 设计文档：``packages/krow-agent-sdk/examples/cookbook/COOKBOOK_DESIGN.md`` §2.1
- 上游 v2 demo：``packages/krow-agent-sdk/examples/cookbook/data-analyst/``
- TURBO 哲学：``AGENTS.md`` §0.1
- 合规依据：CSRC 信息披露公告 17 号 / 《证券法》第 51 条
