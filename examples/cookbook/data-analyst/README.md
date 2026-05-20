# Cookbook · Data Analyst Demo

> **数据分析师 / 合规分析师高频场景**：CSV 自动统计 + 异常检测 + 相关性分析
> + PII 守门 + 合规审计日志。
> 演示 SDK 5 类 plugin（ToolPlugin / ACTPlugin / GatePlugin / HintPlugin /
> EventListenerPlugin）+ BudgetSpec 预算控制。

---

## 业务背景

数据分析师 / 合规分析师每天都会拿到一批 CSV—— payments / users / transactions /
medical claims …—— 跑常规审计：

- 统计每列的均值 / 中位数 / 缺失率 / top-5
- 找数值异常（IsolationForest / IQR / z-score）
- 看列间相关性（pearson / spearman）
- 出报告（markdown / PDF）
- 留审计日志（合规 / SOX / GDPR）

人工每张表 **30-60 分钟**：

- 翻 pandas notebook 写一遍统计
- 反复调参 IsolationForest 阈值
- markdown 报告手抄
- 审计留痕反复忘

**用本 cookbook 后预期 5-10 分钟**：deterministic 工具承担统计 / 异常 / 相关性
（System 1），LLM 只做"哪些列异常值得关注"叙事 + 报告写作（System 2）。

**最关键**：`PIIDetectorGate` 让 LLM **不能**误把含手机号 / 邮箱 / 身份证的
CSV 内容直接写进报告 —— 这是 GDPR / 个保法的最后一道防线。

---

## 三档跑法

### Tier 1（最小跑通）：CSV → markdown 报告

```bash
cd data-analyst
pip install -e .

# Linux / macOS
export KROW_API_KEY=sk-user-xxx
# Windows PowerShell:
# $env:KROW_API_KEY = "sk-user-xxx"
krow-sdk-install --api-key $KROW_API_KEY

python main.py sample_data/titanic.csv
```

输出：`output/titanic_report.md` —— 含每列统计 + LLM 叙事的 markdown 报告。

### Tier 2（业务可用）：异常检测 + 相关性 + PDF

```bash
python main.py sample_data/titanic.csv --audit --pdf
```

新增产物：

- `output/titanic_report.pdf` — 走 SDK 内置 `word_smart_export`
- 报告内含 **异常检测** 段（IsolationForest / IQR / z-score 三选一）
- 报告内含 **相关性矩阵** 段（pearson / spearman）

### Tier 3（合规审计）：守门 + 预算 + 审计日志

```bash
python main.py sample_data/payments.csv \
    --audit --pdf \
    --anomaly-method isolation_forest \
    --budget-llm-calls 15 \
    --budget-walltime 300 \
    --audit-log output/payments.audit.jsonl
```

启用：

- **PIIDetectorGate**：CSV 含 phone / email / id_card 列 → BLOCK conclude（防止
  PII 泄漏）
- **OutputPathGate**：LLM 想写 `../../etc/passwd` → BLOCK（path traversal 防御）
- **DataInsightHintPlugin**：检测时序列 / 高基数列 / 全 NaN 列 → 软提示
- **AuditEventListener**：每次工具调用 + Gate BLOCK + LLM 决策路径 →
  `.audit.jsonl`（GDPR / SOX / 合规审计强制留痕）
- **BudgetSpec**：15 LLM × 300s（防"每列跑一次解读"循环爆 token）

---

## 演示的 SDK 能力

| Plugin 类型 | 实现类 | 业务理由 |
|---|---|---|
| **ToolPlugin** × 6 | `DataAnalystToolPlugin` | read_csv / compute_stats / detect_anomalies / compute_correlation / pick_palette / write_report 全部 deterministic（LLM 凭感觉判断"这一列有没有异常"会出严重事故） |
| **ACTPlugin** | `DataAnalystACTPlugin` | 8 步标准审计工作流（含 PII 检查 / 异常 / 相关性 / 报告） |
| **GatePlugin** × 2 | `PIIDetectorGate` `OutputPathGate` | 合规红线必须 System 1 闸住——PIIDetectorGate 防 LLM 把含 PII 的列直接写报告；OutputPathGate 防 path traversal |
| **HintPlugin** | `DataInsightHintPlugin` | LLM 看到时间戳列 / 高基数 categorical 列不会自动调整分析策略；hint 推一把 |
| **EventListenerPlugin** × 2 | `DataAnalystProgressListener` `AuditEventListener` | 进度打印 + `.audit.jsonl` 合规归档 |
| **BudgetSpec** | `main.py --budget-llm-calls` | 防 LLM 陷入"每列跑一次"循环爆 token |

---

## 文件结构

```
data-analyst/
├── README.md                          # 本文档
├── pyproject.toml                     # name = krow-cookbook-data-analyst
├── main.py                            # CLI 入口（三档跑法）
├── data_analyst_plugin.py             # 全部 plugin 实现（6 tools + 6 plugin classes）
├── act_assets/data_analyst/
│   └── ext_data_analyst.md            # ACT 8 步工作流
├── sample_data/
│   └── titanic.csv                    # 公开 demo 数据
├── tests/
│   ├── conftest.py
│   └── test_data_analyst_smoke.py     # 47 unit test（System 1 only · 0 LLM 调用）
└── .gitignore                         # 排除 output/ *.pdf *.audit.jsonl
```

---

## 关键设计权衡（Trade-offs）

### 为什么 `detect_anomalies` 是 System 1 工具不是 LLM 推理？

按 TURBO 哲学，**异常检测是确定性数值计算**——必须 System 1 化：

| | System 1（本工具） | System 2（LLM 凭感觉判断） |
|---|---|---|
| 准确率 | 100%（IsolationForest / IQR 数值精确） | 60-80%（漏报 / 编造异常） |
| 成本 | 毫秒级，零 token | 5K+ token / 表 |
| 可重放 | 严格 deterministic | 每次结果不同 |
| 可审计 | sklearn 可证明的算法 | LLM 黑盒 |

LLM 在数据审计任务里**会编造"看起来异常"的行**——这是数据合规团队不能接受的。

### 为什么 PII 守门用 GatePlugin 不用 HintPlugin？

| | GatePlugin | HintPlugin |
|---|---|---|
| **触发** | conclude 前 | 每次 macro 决策前 |
| **行为** | BLOCK conclude | 软提示 LLM |
| **强度** | System 1 硬挡 | System 2 软建议 |
| **适用** | 合规底线（PII / path traversal） | 领域 best practice |
| **失败模式** | LLM 收到错误模板，必须改方案 | LLM 可不接受建议 |

GDPR / 个保法**必须**走 Gate——LLM 不能靠 hint 自觉守住。

### 为什么要 BudgetSpec？

数据审计任务 LLM 容易陷入"每列都跑一次 anomaly_score 解读"的循环：

- 10 数值列 × 每列 3 次 LLM call = 30 call
- 不锁预算就爆 token（$0.5+ per task）

`BudgetSpec(max_total_llm_calls=15, max_walltime_s=300, max_replans=2)` 硬约束：

- 强制 LLM 用 batch 接口（一次解读所有列）
- 防 replan 反复（最多 2 次重新规划）
- 5 分钟硬超时（防思考死循环）

### 错误降级演示（三种独立路径）

cookbook 主动演示了三种生产级错误处理：

1. **encoding fallback**：CSV utf-8 失败 → 自动尝试 gbk / gb18030 / latin-1
2. **sklearn 缺失降级**：未装 `[ml]` extra → IsolationForest 自动降级到 IQR
3. **reportlab 缺失降级**：未装 PDF 依赖 → 自动降级到 markdown only

每条降级都给 LLM 黄金错误模板（一句话 + 原因 + 1-3 个修法）。

---

## 反模式（禁止）

| 反模式 | 正确做法 |
|---|---|
| ❌ LLM 直接把 CSV 全文塞 prompt 找异常 | ✅ 调 `read_csv` → `compute_stats` → `detect_anomalies` |
| ❌ LLM 凭感觉判断"这两列相关" | ✅ `compute_correlation` 工具（pearson / spearman 数值） |
| ❌ LLM 自动给"无 PII"结论 | ✅ `PIIDetectorGate` 检测到 phone/email/id_card 列 → BLOCK |
| ❌ LLM 用 reportlab 自己拼 PDF | ✅ `write_report` 内部调 `word_smart_export`（SDK 内置） |
| ❌ 把含 PII 的内部 CSV 提交到本仓 | ✅ 脱敏后放本地 / `.gitignore` 已忽略 `output/` |
| ❌ 用 hint "请记得检查 PII" 替代 Gate | ✅ 合规底线必须 System 1 闸住 |
| ❌ 跑 100+ 列宽表不限制 budget | ✅ 必填 `--budget-llm-calls 15`，超大表先按 schedule 拆 |

---

## 测试

```bash
pip install -e .[test]
pytest tests/
# 47 passed in <1s
```

测试内容：47 个 System 1 unit test 覆盖：

- 通用 helpers（`_normalize_path` / `_golden_error`）
- `read_csv` 边界（utf-8 / gbk fallback / 空文件 / 不存在路径）
- `compute_stats` 数值/分类列（mean / std / missing_rate / top5）
- `detect_anomalies` 三方法（IsolationForest / IQR / z-score + sklearn 降级）
- `compute_correlation` 矩阵（pearson / spearman + top-N 强相关对）
- `pick_palette` 配色查表（categorical / sequential / diverging）
- `write_report` 路径守门（与 `OutputPathGate` 配对）
- ToolPlugin / ACTPlugin Protocol 契约
- **`PIIDetectorGate`** 行为（命中 phone/email/id_card → BLOCK / 无 PII → ALLOW）
- **`OutputPathGate`** 行为（路径 traversal → BLOCK / 项目内路径 → ALLOW）
- `DataInsightHintPlugin` 触发条件（时序 / 高基数 / 全 NaN）
- `DataAnalystProgressListener` / `AuditEventListener` 事件归档

**0 LLM 调用，CI 可频繁跑**（全部 < 1 秒）。

如果要跑 ML 异常检测：

```bash
pip install -e .[ml,test]    # 加装 sklearn
pytest tests/ -v
```

真实 LLM E2E 测试（本地跑，需 `KROW_API_KEY`）：

```bash
pytest tests/test_data_analyst_journey_e2e.py -v -s
```

---

## 引用

- 合规依据：GDPR Art.5 (data minimization) / Art.32 (security of processing) /
  PIPL §10 (基本原则) / SOX §404 (internal control)
- 异常检测：sklearn IsolationForest / Tukey IQR / Standard Z-score
