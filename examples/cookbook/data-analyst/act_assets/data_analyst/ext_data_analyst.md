# 数据审计员 ACT — 扩展指南（v2 升级版）

## v2 升级要点

本 ACT 从 v1 "data-analyst basic"（4 工具，仅基础统计 + markdown 报告）升级到
v2 "data-analyst + auditor scope"（6 工具 + 2 GatePlugin + HintPlugin + AuditEventListener +
BudgetSpec），覆盖真实业务场景：

- **必须用 plugin 工具的能力**（Krow 内置无）：异常检测 / 相关性矩阵
- **必须用 GatePlugin 守住的合规底线**：PII 字段检测 / path traversal 防御
- **必须用 BudgetSpec 限制的资源消耗**：防 LLM 陷入"每列都跑一次 anomaly"的爆 token 循环

## 推荐工作流（合规审计 8 步）

1. **`data_analyst_read_csv(path)`** — 拿 metadata 和前 10 行预览
   - LLM 看 columns / dtypes 决定分析方向
   - 不要直接读全量数据塞 prompt（context 爆炸）
   - **错误降级**：encoding 自动 fallback（utf-8 → utf-8-sig → gbk → cp1252）
   - **守门触发**：PIIDetectorGate 在 conclude 前扫描 columns，命中
     `phone / email / id_card / 手机 / 身份证` 等关键词时 BLOCK，让用户脱敏后再分析

2. **`data_analyst_compute_stats(path)`** — 算基础统计指标（System 1）
   - 数值列：mean / std / min / max / missing_count
   - 分类列：unique_count / top5 频次 / missing_count
   - **铁律**：不要让 LLM 自己算 mean / 算分布；交给工具

3. **`data_analyst_detect_anomalies(path, method, contamination)`** — 异常检测（v2 新增）
   - method='iqr'（默认；快；解释性好；适合单列分布异常）
   - method='zscore'（要求列近似正态）
   - method='isolation_forest'（多列联合异常；需 sklearn；适合"组合特征下的异常"）
   - **重要**：Krow 内置工具池**没有任何异常检测工具**——必须通过本工具
   - 工具自动截断 anomaly_indices 到前 50 个（防 LLM context 爆）
   - LLM 解读：异常率 > 10% 多半是 method 选错；< 1% 多半是真异常需关注

4. **`data_analyst_compute_correlation(path, method, top_n)`** — 相关性矩阵（v2 新增）
   - method='pearson'（线性，默认）/ 'spearman'（秩相关，非线性单调更稳）
   - 返回完整 matrix dict + top N 强相关对（按 |r| 降序）
   - **重要**：禁止 LLM 凭感觉判断 "A 和 B 应该有相关"——必须调本工具看真实 r 值
   - LLM 解读：|r| > 0.8 是强相关需调查（多重共线性 / 业务等价指标）；
     |r| < 0.2 视为基本不相关

5. **`data_analyst_pick_palette(palette_kind, n)`** — 查表配色（System 1）
   - 数值列分布 → `sequential`（ColorBrewer Blues 9）
   - 分类列对比 → `categorical`（Tableau 10，色盲友好）
   - 正负指标（如相关系数）→ `diverging`（红蓝 11）
   - **铁律**：不要让 LLM 凭感觉配色（违反 §0.1 TURBO 哲学）

6. **基于数据 + 异常 + 相关性 + 配色写 markdown**（System 2，LLM 在 ReACT 循环内组织）
   - **6 段结构**（合规审计标准格式）：
     ① 数据概览（行/列数 / 编码 / 大小）
     ② 数值列统计（每列 mean/std/min/max/缺失率）
     ③ 分类列统计（每列 unique 数 / top5 频次 / 缺失率）
     ④ **异常审计**（method / 异常率 / 重点异常行 indices / per-column 分布）
     ⑤ **相关性洞察**（top N 强相关对解读 / 多重共线性提示）
     ⑥ **合规建议**（数据质量问题 / 异常处置建议 / 后续动作）
   - 每个 section 引用具体数字（mean=12.3 / r=0.87 / 异常率=3.2%）
   - 配色 hex 引用工具返回值（不要自己造 hex）
   - **不要**编造工具未返回的数字

7. **`data_analyst_write_report(output_path, title, content)`** — 落盘 markdown
   - title 不带 `#` 前缀
   - content 是完整 markdown 正文（多段）
   - **守门触发**：OutputPathGate 在 conclude 前检查 output_path，
     命中 "不在 project_root 内" 时 BLOCK（防 path traversal）

8. **（可选 PDF）`word_smart_export(file_path=md_path, format="pdf", output_path=pdf_path)`**
   - **这是 Krow 内置工具，不是本 plugin 注册的工具**——演示 SDK 教学要点：
     ToolManager 是全局单例，外部 plugin agent 自动继承所有 Krow 内置工具。
   - SSOT = `MarkdownDocumentRenderer`（reportlab backend + CJK 字体支持 +
     完整样式系统 / heading 6 级 / table / blockquote / code block）
   - **不要让 cookbook plugin 自己写 PDF 渲染工具**（违反 §0.2 SSOT 原则）
   - 错误降级：若用户没装 reportlab → tool 返回错误，LLM 应告知"PDF 输出需要 reportlab，
     已降级仅 markdown"

9. **完成 conclude** — markdown（必出）+ PDF（可选）+ 审计日志（自动）三路径告知用户

## SDK 高级能力演示（v2 升级亮点）

### GatePlugin（System 1 硬守门）

| Gate | 触发条件 | BLOCK 行为 |
|---|---|---|
| **PIIDetectorGate** | column 名命中 PII 关键词字典（手机/身份证/邮箱/银行卡/地址） | 返回黄金错误模板，要求脱敏 / 显式 allow_pii=True |
| **OutputPathGate** | write_report 的 output_path 不在 project_root 内 | 返回黄金错误模板，要求改用 project_root 子目录 |

**Gate 与 Hint 的边界**：
- Gate = **System 1 硬挡**（fail-loud；BLOCK 后 conclude 失败；零成本）
- Hint = **System 2 软建议**（仅参考；LLM 可不接受；用 token）
- 合规需求**必须**走 Gate，不能仅靠 Hint 提醒 LLM "别这么做"

### HintPlugin（System 2 软提示）

`DataInsightHintPlugin` 在每次 macro ReACT 决策前注入 markdown hint：
- 检测时序列（含 date / time / timestamp / 日期 / 时间）→ 建议加同环比分析
- 检测高基数 ID 列（unique = row_count）→ 建议从分析剔除
- 检测全 NaN 列 → 建议 drop
- 检测大数据集（> 100k 行）→ 建议先 stats 再 anomaly（防爆 token）

### BudgetSpec（资源约束）

`main.py --budget-llm-calls 15 --budget-walltime 300` 演示：
- `max_total_llm_calls=15`：本任务最多 15 次 LLM 调用（read/stats/anomaly/corr/palette/write 各 1
  + macro plan 2-3 + micro reasoning 2-5 ≈ 12-15）
- `max_walltime_s=300`：5 分钟硬超时（防 LLM 思考死循环）
- `max_replans=2`：最多 2 次 replan（防 LLM 反复改方案）

**真实业务必要性**：数据审计任务 LLM 容易陷入"每列都跑一次 anomaly_score 解读"
的循环（10 列 × 每列 3 次 LLM call = 30 call），不锁预算就爆 token。

### AuditEventListener（合规归档）

`main.py --audit-log output/audit.jsonl` 启用后：
- 每个 tool.call_started / tool.call_completed 事件 → 落 jsonl 一行
- task_complete / task_failed 事件 → 落 jsonl 一行
- 后续审计员可按时间戳追溯 LLM 决策路径

**与 ProgressListener 区别**：Progress 是给用户看的实时打印；
Audit 是给审计员看的归档（保留 90 天 / 1 年）。

## 反模式

| ❌ 错误 | ✅ 正确 |
|---|---|
| LLM 看 preview_rows 自己算 mean | 调 `data_analyst_compute_stats` |
| LLM 凭感觉判断 "A 和 B 应该有相关" | 调 `data_analyst_compute_correlation` |
| LLM 凭感觉判断"哪行是异常" | 调 `data_analyst_detect_anomalies` |
| LLM 凭感觉配色（违反 TURBO 哲学）| 调 `data_analyst_pick_palette` |
| 跳过 read_csv 直接 compute_stats | 先 read 看 columns 再决定要 stats 哪些列 |
| 跳过 write_report 直接 word_smart_export | 必须先 write_report 落 markdown，再 word_smart_export |
| **cookbook plugin 自己造 render_pdf 工具** | 用 Krow 内置 `word_smart_export`（SSOT 复用） |
| 在含 PII 列的 CSV 上直接分析 | PIIDetectorGate 会 BLOCK，先脱敏 / 显式 allow_pii |
| 写报告到 ../../etc/passwd | OutputPathGate 会 BLOCK，必须在 project_root 内 |
| 把全部 row 数据写到 markdown | 只写聚合统计 + 关键洞察 |
| 中文报告里夹大量英文术语 | 全中文（如 "数值列" 而非 "numeric columns"） |
| 数据质量问题不报 | 缺失率 > 30% 的列必须报名 + 给"是否要清理"的建议 |
| **不锁 BudgetSpec 跑数据审计** | 至少 max_total_llm_calls=15-30 + max_walltime_s=300 |

## SDK 教学重点：Plugin 与 Krow 内置工具组合

**外部 SDK plugin 不需要"重头造每件事"**——`ToolManager` 是全局单例，
你写自己的 `ToolPlugin` 注册的工具会**和 Krow 内置工具同时存在**。

ACT 的 `tools:` 列表可以同时声明：
- 你 plugin 里 `get_tools()` 返回的工具（如 `data_analyst_*`）
- Krow 主应用内置的工具（如 `word_smart_export` / `smart_read_document` / `pptx_*`）

LLM 在 ReACT 循环内会**统一看到这两类工具**，按 ACT 推荐工作流串起来用。

**判定准则**（写 plugin 前先想）：
1. Krow 已有这个能力？→ **不写**，在 ACT extended.md 教 LLM 调内置工具
2. 这是新领域 / 业务专属？→ 写自己的 plugin 工具
3. 内置工具 90% 满足但缺 10%？→ 写**包装/补全**工具，内部调用内置工具

**v2 验证**：本 cookbook 6 个工具是否真的必要？
- ✅ `read_csv`：Krow 内置 smart_read_document 不专门优化 CSV encoding fallback；保留
- ✅ `compute_stats`：deterministic 化 + 自动归一返回结构；保留
- ✅ `detect_anomalies`：Krow 内置**完全无**异常检测能力；**必须保留**
- ✅ `compute_correlation`：deterministic 化 + 自动 top-N + 防 LLM 编造；保留
- ✅ `pick_palette`：deterministic 配色查表（违反 TURBO 给 LLM 凭感觉配色）；保留
- ✅ `write_report`：薄包装 + OutputPathGate 守门；保留
- ❌ ~~`render_pdf`~~：Krow 已有 word_smart_export；**不写**（v2 移除）

## 错误降级演示（demo 重点）

- **CSV 编码错（中文老 excel 导出）**
  - read_csv 自动尝试 utf-8 → utf-8-sig → gbk → cp1252
  - LLM 应在报告 footer 注明"原始文件 GBK 编码"

- **CSV 含 PII 列**
  - PIIDetectorGate BLOCK，黄金错误模板告知 LLM 哪些列含 PII
  - LLM 应告知用户脱敏要求 / 或在工具调用层加 allow_pii flag（合规风险用户承担）

- **写报告路径越界**
  - OutputPathGate BLOCK，告知正确路径模板
  - LLM 应在重试时改路径到 project_root 子目录

- **isolation_forest 在 sklearn 缺失环境**
  - tool 返回黄金错误模板（含 `pip install scikit-learn` 修法）
  - LLM 应自动降级到 `method='iqr'` 重试

- **预算超限（max_total_llm_calls 触顶）**
  - SDK 自动 conclude 任务为 partial complete
  - LLM 应在 final_output 里说明"预算限制提前结束，已完成 X / Y 步"

- **PDF 渲染依赖缺失（reportlab 未装）**
  - `word_smart_export` 工具返回错误（含 `pip install reportlab` 修法）
  - LLM 应优雅降级：告知用户"PDF 渲染未启用，仅生成 markdown；如需 PDF 请装 reportlab"

- **CSV 太大（> 100MB）**
  - DataInsightHintPlugin 检测到 row_count > 100k 时给软提示
  - LLM 应主动建议"用 head -n 10000 file.csv > sample.csv 缩样"

- **数值列全是缺失**
  - compute_stats 自动跳过该列
  - DataInsightHintPlugin 给"建议 drop 全 NaN 列"软提示
