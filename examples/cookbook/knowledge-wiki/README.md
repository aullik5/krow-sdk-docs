# Knowledge & Wiki Studio — 知识编译 + wiki 编译 cookbook

> Krow SDK Cookbook 第 1 个**知识管理**类 demo。把一批领域资料编译成结构化
> 知识库：抽出本体（Ontology：概念 / 实体 / 关系），并为每个核心节点生成一篇
> 可浏览、可互链的百科词条（wiki）。

## 业务场景

知识工作者 / 研究团队 / 企业知识库管理员手上有一批领域资料（markdown / txt /
PDF / Office），想把它们沉淀成**结构化、可检索、可互链**的知识库。人工梳理
1-2 天；用本 cookbook 预期 20-40 分钟。

**输入**：一个资料目录（≥1 份 ≥200B 的 .md / .txt / .pdf / .docx）
**输出**：
- `<project>/.krow/ontology/global.db` — 本体 SSOT（概念 / 实体 / 关系 / chunk）
- `<project>/.krow/wiki/**/*.md` — 百科词条（每个核心节点一篇，带 frontmatter + wiki-link 互链）
- `output/compile_report.md` — 编译验收报告（覆盖率 + 词条清单，确定性生成）
- `output/ontology_snapshot.json` — 本体计数快照

## 与前 4 个 cookbook 的本质差异

| 维度 | financial / literature / contract / data | **knowledge-wiki** |
|---|---|---|
| 核心工作由谁做 | cookbook 自带领域工具（KPI / 聚类 / 条款分类） | **Krow 引擎内置工具**（本体抽取 + wiki 编译） |
| cookbook 工具角色 | 主力 | **辅助**（ingest 规划 + 覆盖验收） |
| 驱动方式 | ACT 步骤 | ACT + `task_context.strategy="knowledge_compile"` 三阶段契约 |

**SSOT 铁律**：抽本体复用内置 `extract_entities_from_text`，写词条复用内置
`wiki_info` + `smart_file_write`，**绝不重复造这些轮子**。

## 跑法

```bash
# 1. 设凭证
export KROW_API_KEY=sk-user-xxx          # PowerShell: $env:KROW_API_KEY='sk-user-xxx'

# 2. 装 SDK + cookbook
krow-sdk-install --api-key $KROW_API_KEY
cd packages/krow-agent-sdk/examples/cookbook/knowledge-wiki
pip install -e .

# 3. 最小跑（用自带 3 篇光伏资料）
python main.py

# 4. 编译自己的资料
python main.py path/to/my_docs --project-dir ./my_kb \
    --budget-llm-calls 120 --budget-walltime 3600
```

跑完看产物：

```bash
cat output/compile_report.md            # 编译验收报告
ls -R my_kb/.krow/wiki/                  # 生成的百科词条
```

## SDK plugin 清单（按需省略 Hint / Observability）

| 类型 | 类 | 作用 |
|---|---|---|
| **ToolPlugin** | `KnowledgeWikiToolPlugin` | 2 个差异化 System 1 工具：`knowledge_wiki_scan_sources`（确定性 ingest 规划）+ `knowledge_wiki_coverage_report`（本体↔wiki 覆盖验收） |
| **ACTPlugin** | `KnowledgeWikiACTPlugin` | `knowledge_wiki_studio` ACT，打包知识编译三阶段工作流 + 内置工具栈 |
| **GatePlugin** | `WikiCoverageGate` | 防"假编译"：本体抽完但 wiki 页几乎没写 → BLOCK conclude |
| **EventListenerPlugin** | `CompileProgressListener` | 三阶段（抽取 / 关联 / 发布）实时进度 + 审计 jsonl |

**为什么省略 HintPlugin / ObservabilityPlugin**（设计 §3 "按需而生"）：
- Hint：编译流程由 `knowledge_compile` 契约 + ACT 强引导，软提示价值低。
- Observability：个人 / 团队知识库一般不接 BI dashboard。

## 两个 cookbook 工具的差异化与必要性

| 工具 | 与内置工具的差异 | 必要性 |
|---|---|---|
| `knowledge_wiki_scan_sources` | 内置无"该编入哪些文件"的规划器 | 给 LLM 确定性 ingest 清单，自动排除 `.krow` 防自激环，避免漏编 |
| `knowledge_wiki_coverage_report` | `summarize_ontology` 只看本体、`wiki_info(validate)` 只 lint wiki，**都不做本体↔wiki 覆盖核对** | "编译完词条到底有没有变丰富"的确定性度量；`under_populated` 是假编译信号，驱动 `WikiCoverageGate` |

## 三阶段编译工作流

```
0. 规划   knowledge_wiki_scan_sources(docs_dir)        → ingest 清单
1. 抽取   extract_entities_from_text × N               → GlobalOntology 概念/实体/事件
2. 关联   add_relation × N                             → causal / hierarchical 关系边
3. 发布   wiki_info(get_template) + smart_file_write   → .krow/wiki/*.md 词条
4. 验收   knowledge_wiki_coverage_report               → 覆盖率（WikiCoverageGate 守门）
5. lint   wiki_info(validate) + summarize_ontology     → 健康检查 + 总览
```

## 真实 LLM E2E

```bash
pip install -e ".[test]"
pytest tests/ -v -s        # 无 KROW_API_KEY 时 journey 自动 skip
```

详见 `act_assets/knowledge_wiki_studio/ext_knowledge_wiki_studio.md`（完整工作流 +
反模式）。
