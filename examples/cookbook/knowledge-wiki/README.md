# Knowledge & Wiki Studio — 知识编译 + wiki 编译 + 前端预览 cookbook

> Krow SDK Cookbook 第 1 个**知识管理**类 demo。把一批领域资料端到端编译成结构化
> 知识库：抽出本体（Ontology：概念 / 实体 / 关系）→ 为每个核心节点生成可浏览、
> 可互链的百科词条（wiki）→ **渲染成可双击打开的前端富百科站点**。

## 两档词条模型（架构公理 D · 务必先理解）

| 档位 | 谁来写 | 怎么写 |
|------|--------|--------|
| 🔴 **stub 红链**（`tier: stub`） | **系统零-LLM 确定性物化** | 本体里每个达标节点自动派生为轻量词条（定义 + 关系导航 + 出处）。`knowledge_wiki_materialize` 工具一次覆盖全部节点；**不要逐个手写** |
| 🔵 **essay 蓝链**（`tier: essay`） | **LLM 精写** | top-K 高价值节点的论述正文，由 `smart_file_write` 写入。这是 publish 阶段唯一的写盘动作，只针对少数重点 |

> ⚠️ 这是 2026-06-08 修复的核心：旧引导让 LLM 把**所有**词条当 `smart_file_write`
> 手写，撞 `wiki_gate` 空转。现在 stub 由系统物化，LLM 只写 top-K essay。
> `agent.run(task_context={"strategy":"knowledge_compile"})` 路径已内置 System-1
> stub 自动物化（对齐桌面 `KnowledgeLifecycleManager`）。

## 业务场景

知识工作者 / 研究团队 / 企业知识库管理员手上有一批领域资料（markdown / txt /
PDF / Office），想把它们沉淀成**结构化、可检索、可互链**的知识库。人工梳理
1-2 天；用本 cookbook 预期 20-40 分钟。

**输入**：一个资料目录（≥1 份 ≥200B 的 .md / .txt / .pdf / .docx）
**输出**：
- `<project>/.krow/ontology/global.db` — 本体 SSOT（概念 / 实体 / 关系 / chunk）
- `<project>/.krow/wiki/**/*.md` — 百科词条（stub 红链 + essay 蓝链，带 frontmatter + wiki-link 互链）
- `output/compile_report.md` — 编译验收报告（覆盖率 + 词条清单，确定性生成）
- `output/ontology_snapshot.json` — 本体计数快照
- `output/wiki_preview/index.html` — **前端富渲染百科站点**（双击即看，复用 `@krow/wiki-render`）

## 与前 4 个 cookbook 的本质差异

| 维度 | financial / literature / contract / data | **knowledge-wiki** |
|---|---|---|
| 核心工作由谁做 | cookbook 自带领域工具（KPI / 聚类 / 条款分类） | **Krow 引擎内置工具**（本体抽取 + wiki 编译） |
| cookbook 工具角色 | 主力 | **辅助**（ingest 规划 + 覆盖验收） |
| 驱动方式 | ACT 步骤 | ACT + `task_context.strategy="knowledge_compile"` 三阶段契约 |

**SSOT 铁律**：抽本体复用内置 `extract_entities_from_text`，stub 物化复用内置
`ontology_stub_compiler`，essay 精写复用 `smart_file_write`，前端渲染复用官方包
`packages/wiki-render`（`@krow/wiki-render`，与桌面 WikiView 同源），**绝不重复造这些轮子**。

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
# 前端预览：双击或用浏览器打开
open output/wiki_preview/index.html      # macOS（Windows: start ...；Linux: xdg-open ...）
```

## 前端预览 / Web Handoff（端到端）

`render_wiki_preview`（`wiki_preview.py`，零 LLM）读 `.krow/wiki/**/*.md` 生成一个
**框架无关、可离线打开**的静态站点 `output/wiki_preview/index.html`：

- 三栏布局（词条树 + 正文 + 信息栏），左侧按 concepts / entities / sources 分组
- 复用官方渲染器 `@krow/wiki-render`：Markdown + `[[wiki-link]]` 站内跳转 +
  ```mermaid 关系图 + KaTeX 公式 + 代码高亮（mermaid/katex/highlight 从 CDN 按需加载）
- 渲染逻辑与桌面 WikiView **同源**（`ui/static/wiki/`），不重写轮子

**接入生产前端**：本 demo 把页面数据内联进 HTML（适合本地走查）；上 Web/Cloud 时
按 `docs/zeru/wiki_web_handoff/` 三件套接 BFF（`GET /api/wiki/page` 等）+ Web shell +
`@krow/wiki-render`。详见该目录 README。

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
3a.物化   knowledge_wiki_materialize（零 LLM）          → stub 红链词条（全部达标节点）
3b.精写   smart_file_write（top-K · tier: essay）       → essay 蓝链词条（少数重点）
4. 验收   knowledge_wiki_coverage_report               → 覆盖率（WikiCoverageGate 守门）
5. lint   wiki_info(validate) + summarize_ontology     → 健康检查 + 总览
6. 预览   render_wiki_preview（零 LLM）                  → output/wiki_preview/index.html
```

## 真实 LLM E2E

```bash
pip install -e ".[test]"
pytest tests/ -v -s        # 无 KROW_API_KEY 时 journey 自动 skip
```

详见 `act_assets/knowledge_wiki_studio/ext_knowledge_wiki_studio.md`（完整工作流 +
反模式）与 `COOKBOOK_DESIGN.md` §2.4。
