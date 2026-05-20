# Sample data — financial-analyst cookbook

本目录用于放真实可跑的样例年报 PDF。**未默认附带 PDF**，因为：

1. 真实上市公司年报 PDF 大（5-30 MB），git 仓库不应承载
2. 不同地区上市公司年报受版权 / 信息披露规则约束，cookbook 默认不预置

## 自助跑通的 3 种方式

### 方式 A：手动下载几份 A 股 / 美股年报（推荐）

```bash
# 中国证监会指定信披平台：cninfo.com.cn / sse.com.cn
# 美股：sec.gov/edgar
# 例：贵州茅台 2024 年报（cninfo）
wget -O guizhou_maotai_2024.pdf "<official URL from cninfo>"

# 把 3-5 份不同公司的年报 PDF 放到本目录
ls -lh sample_data/
# guizhou_maotai_2024.pdf
# wuliangye_2024.pdf
# yanghe_2024.pdf
```

然后：

```bash
cd examples/cookbook/financial-analyst
python main.py sample_data/*.pdf --pdf
```

### 方式 B：用其他 PDF 文件先验证管线（不抽 KPI）

cookbook 工具对**任何文本可抽 PDF** 都能跑（KPI 抽取会大量 missed，但管线
不崩），可用任意财报 / 招股书测：

```bash
python main.py path/to/any_business_pdf.pdf --no-valuation
```

### 方式 C：跑单元测试（**推荐 CI 路径**）

不需要 PDF — `tests/test_financial_analyst_smoke.py` 53 个 unit test 全部
mock 输入数据：

```bash
cd examples/cookbook/financial-analyst
pip install -e .[test]
pytest tests/
# 53 passed in <1s
```

## 真实业务环境集成建议

**不要**把生产年报 PDF 提交到本仓 —— 走以下任一方式：

1. **本地 sample_data/**：`.gitignore` 已忽略 `*.pdf`（防误 commit）
2. **私有对象存储**：从公司内部 OSS / S3 / TOS 拉取
3. **直接传文件路径**：`python main.py /data/research/pdfs/maotai.pdf`

cookbook 不为你做"年报数据采集"——这是数据团队的职责，cookbook 只演示
"拿到年报后如何用 Krow SDK 高效横向对比 + 出投资简报"。
