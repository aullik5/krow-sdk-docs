# Sample data — literature-reviewer cookbook

本目录用于放真实可跑的样例论文 PDF。**未默认附带 PDF**，因为：

1. 学术论文 PDF 普遍受版权约束（出版商 / arXiv 协议）
2. cookbook 不预置任何特定方向论文，避免"领域偏见"
3. 论文 PDF 通常 1-15 MB，git 仓库不应承载

## 自助跑通的 3 种方式

### 方式 A：手动下载若干 arXiv 论文（最简单合规路径）

```bash
# arXiv 是开放获取的（CC BY），适合 demo
# 例：选一个研究主题（如 Retrieval-Augmented Generation），下载 8-15 篇

mkdir -p sample_data
cd sample_data
wget https://arxiv.org/pdf/2005.11401  # RAG 原论文
wget https://arxiv.org/pdf/2312.10997  # Retrieval-Augmented Generation Survey
wget https://arxiv.org/pdf/2402.09353  # In-Context RALM
# ... 凑够 8-15 篇 ...

ls -lh sample_data/
# rag_2020.pdf
# rag_survey_2023.pdf
# in_context_ralm_2024.pdf
# ...
```

然后跑：

```bash
cd examples/cookbook/literature-reviewer
python main.py sample_data/*.pdf --topic "Retrieval-Augmented Generation" --pdf
```

### 方式 B：用学校 / 实验室的私有论文库

把内部已下载的 PDF 软链到 `sample_data/`：

```bash
ln -s /path/to/your/lab/papers/*.pdf sample_data/
python main.py sample_data/*.pdf --topic "你的研究主题"
```

### 方式 C：跑单元测试（**推荐 CI 路径，零 PDF 依赖**）

不需要 PDF — `tests/test_literature_reviewer_smoke.py` 46 个 unit test 全部
mock 输入数据：

```bash
cd examples/cookbook/literature-reviewer
pip install -e .[test]
pytest tests/
# 46 passed in <1s
```

## 真实研究环境集成建议

**不要**把出版商版权 PDF 提交到本仓 —— 走以下任一方式：

1. **本地 sample_data/**：`.gitignore` 已忽略 `*.pdf`（防误 commit）
2. **arXiv 镜像**：合规、API 稳定（推荐）
3. **学校订阅库**：通过 Web of Science / Scopus 导出 RIS / BibTeX 元数据，
   再批量下载 PDF（注意单位许可范围内使用）

cookbook 不为你做"论文采集"——这是研究者 / 数据团队的职责，cookbook 只演示
"拿到一批论文 PDF 后如何用 Krow SDK 高效做综述"。

## 推荐的论文规模

| 论文数 | 典型耗时 | 备注 |
|---|---|---|
| 5-8 篇 | 2-5 min | 试跑、验证管线 |
| 10-20 篇 | 8-15 min | 真实"小综述"规模（**默认推荐**） |
| 30-50 篇 | 30-60 min | 系统性综述（建议加 `--budget-walltime 3600`） |
| > 100 篇 | 不推荐 | 主题聚类质量下降，应先按子领域拆分跑 |

> 提示：cookbook 默认 `BudgetSpec(max_total_llm_calls=180, max_walltime_s=2400)`，
> 大批量论文请按 §main.py 顶部说明调高预算。
