# Sample data — contract-auditor cookbook

本目录用于放真实可跑的样例合同 docx / pdf。**未默认附带任何合同**，因为：

1. 真实商务合同 / NDA 普遍受**保密协议约束**（合同自身常常是 Confidential
   Information），不能提交到公开仓库
2. 不同地区合同受当地法律 / 税务规则影响，cookbook 默认不预置
3. 合同 PDF 通常 0.5-3 MB，git 仓库不应承载

## 自助跑通的 3 种方式

### 方式 A：用脱敏后的真实合同（推荐）

把内部合同**脱敏**（公司名 / 价格 / 日期 → 替换占位符）后放到 `sample_data/`：

```bash
mkdir -p sample_data
cp /path/to/redacted_contract.docx sample_data/contract.docx
# 如有公司模板：
cp /path/to/redacted_template.docx sample_data/template.docx

cd examples/cookbook/contract-auditor
python main.py sample_data/contract.docx --template sample_data/template.docx --docx
```

### 方式 B：用公开示例合同（学习 / 演示用）

合规获取公开示例合同：

- **MSA / NDA / DPA 模板**：SEC EDGAR / Sigma Computing legal-templates / GitHub
  公开 sample contracts repo（非生产用，仅学习）
- **GDPR Article 28 DPA 模板**：欧盟委员会 standard contractual clauses（公开）
- **开源 NDA 模板**：CommonAccord / OpenLawNYC（CC0 license）

```bash
# 例：从公开 SEC EDGAR 下载某家公司的 commercial agreement
wget -O sample_data/sample_msa.pdf "<EDGAR official URL>"
python main.py sample_data/sample_msa.pdf --docx
```

### 方式 C：跑单元测试（**推荐 CI 路径，零合同依赖**）

不需要任何真实合同 — `tests/test_contract_auditor_smoke.py` 50 个 unit test
全部用内置 SAMPLE_CONTRACT 字符串 mock 输入：

```bash
cd examples/cookbook/contract-auditor
pip install -e .[test]
pytest tests/
# 50 passed in <1s
```

## 真实业务环境集成建议

**不要**把生产合同 docx / pdf 提交到本仓 —— 走以下任一方式：

1. **本地 sample_data/**：`.gitignore` 已忽略 `*.docx` / `*.pdf` / `*.doc`
2. **公司私有合同库**：DocuSign / iManage / SharePoint 拉取
3. **直接传文件路径**：`python main.py /secure/contracts/vendor_xyz.docx`

cookbook 不为你做"合同采集 / 脱敏"——这是法务 / 数据团队的职责，
cookbook 只演示"拿到合同后如何用 Krow SDK 高效做风险审阅"。

## 推荐的合同复杂度

| 合同规模 | 典型耗时 | 备注 |
|---|---|---|
| 单页 NDA（5-10 条款） | 30s-1min | 试跑、验证管线 |
| 5-10 页 MSA / 服务协议 | 2-5 min | 真实"小合同" review（**默认推荐**） |
| 30-50 页大型商务合同 | 8-15 min | 跨国采购合同 / DPA / SaaS contract |
| > 100 页 | 不推荐 | 建议先按 schedule / annex 拆分 |

> 提示：cookbook 默认 `BudgetSpec(max_total_llm_calls=60, max_walltime_s=600)`，
> 大型合同请按 §main.py 顶部说明调高预算。

## OpenTelemetry 配置示例

Tier 3（合规 / 生产）默认启用 OTel tracing。本地起 Jaeger 看 trace：

```bash
docker run -d --name jaeger \
    -e COLLECTOR_OTLP_ENABLED=true \
    -p 4317:4317 -p 16686:16686 \
    jaegertracing/all-in-one:latest

python main.py sample_data/contract.docx \
    --observability \
    --otlp-endpoint http://localhost:4317

# 浏览 Jaeger UI: http://localhost:16686
# 选 service: krow_contract_auditor → 看每个 tool span
```
