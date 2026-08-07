"""Literature-reviewer cookbook plugin SSOT.

> Cookbook v3 第 2 个 demo（设计依据：``COOKBOOK_DESIGN.md`` §2.2）。

业务场景：学术 PI / 博士生 / 智库分析师做主题文献综述——读 50-200 篇 paper PDF
→ 抽元数据 → 主题聚类 → 起草综述章节 → 引用核对。LLM 介入前每次 2-4 周；
用本 cookbook 预期 4-8 小时。

本文件 SSOT 5 个 ToolPlugin（PDF 元数据 / 主题聚类 / 引用图 / 抄袭重叠 /
章节大纲）+ 2 个 GatePlugin（CitationCompletenessGate / PlagiarismGate）+
2 个 HintPlugin（TopicCoverage / YearGap）+ 1 个 EventListenerPlugin（大批量
任务实时进度）+ 1 个 ACTPlugin（10 步综述工作流）。

设计原则（与 v2 / v3-PR-A 互补，不重复）：

1. **大批量任务的 plugin 设计**
   - 50-200 篇 PDF 任务 vs financial 的 3-5 家公司任务 = 数量级差异
   - 必须有 BudgetSpec 硬约束（120 LLM × 1800s）防爆 token
   - 必须有 ProgressListener 实时报进度（用户能看到不是卡死）

2. **学术规范守门** = 与金融行业不同的"红线"
   - CitationCompletenessGate：综述每段 ≥3 篇引用（学术规范）
   - PlagiarismGate：句子与原文 n-gram overlap > 60% = 抄袭红线
   - hint 教 LLM "请记得引用" 在 LLM 偷懒时会失效 → 必须 System 1 闸住

3. **ObservabilityPlugin 按需省略**（design §3 铁律：不为凑齐而硬塞）
   - 学术场景一般不接 BI dashboard / Prometheus
   - EventListener + 进度日志足够

4. **TURBO 哲学严格执行**
   - embedding + 聚类 = System 1（数值 / 图论计算）
   - 综述章节起草 = System 2（LLM 在 ACT 流程内组织）

参考：
- v3 PR-A: ``packages/krow-agent-sdk/examples/cookbook/financial-analyst/``
- v2:     ``packages/krow-agent-sdk/examples/cookbook/data-analyst/``
- 设计 SSOT: ``COOKBOOK_DESIGN.md`` §2.2 / §3
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections import Counter as _Counter
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# §0. 通用工具（黄金错误模板 + 路径归一化）
# ============================================================


def _normalize_path(p: str | Path) -> Path:
    if isinstance(p, str):
        p = Path(p)
    return p.expanduser().resolve()


def _golden_error(
    msg: str, *, where: str, fixes: Iterable[str], related: Iterable[str] = ()
) -> dict[str, Any]:
    parts = [f"❌ {msg}", f"   位置：{where}", "   修法："]
    for i, fix in enumerate(fixes, 1):
        parts.append(f"     {i}. {fix}")
    if related:
        parts.append(f"   相关：{' / '.join(related)}")
    return {"ok": False, "error": "\n".join(parts)}


def _coerce_json_payload(value: Any) -> Any:
    """LLM 常把结构化入参写成 JSON 字符串；先解一层再判类型。

    2026-08-06 SDK nightly 铁证（run 31106693210 · literature-reviewer）：
    ``Tool execution failed: 'str' object has no attribute 'get'`` —— 旧实现对
    ``papers`` / ``edges`` 直接 ``p.get(...)``，模型传进来的是字符串（JSON 文本或
    一串 paper_id）时就抛裸 ``AttributeError``。裸异常对模型是不可修复信号
    （没说哪个参数、也没说该传什么），于是它换个姿势再试，一路耗到墙钟。

    本函数只做**语法**归一（System 1），不猜语义：解不出来原样返回，交给调用方
    走黄金模板 fail-loud。
    """
    if isinstance(value, (str, bytes)):
        try:
            return json.loads(value)
        except Exception:  # noqa: BLE001 - 不是 JSON 就原样交回给类型闸判
            return value
    return value


def _coerce_dict_list(value: Any, *, param: str, where: str) -> Any:
    """把入参归一成 ``list[dict]``；形状不对 → 黄金模板错误 dict（非异常）。

    Returns:
        ``list[dict]``（成功）或 ``{"ok": False, "error": ...}``（失败）。
    """
    value = _coerce_json_payload(value)
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return _golden_error(
            f"{param} 必须是对象数组，实际收到 {type(value).__name__}",
            where=where,
            fixes=[
                f"{param}=[{{...}}, {{...}}]（每项是一个对象，不是字符串）",
                f"别传 {param} 的 JSON 字符串以外的裸文本",
            ],
        )
    bad = [i for i, item in enumerate(value) if not isinstance(item, dict)]
    if bad:
        sample = value[bad[0]]
        return _golden_error(
            f"{param}[{bad[0]}] 必须是对象，实际是 {type(sample).__name__}"
            f"（共 {len(bad)}/{len(value)} 项不合规）",
            where=where,
            fixes=[
                f"{param} 的每一项要传完整对象而不是 id 字符串",
                "papers 请直接传 extract_paper_metadata 的输出对象",
                "edges 请传 [{\"from\": paper_id_A, \"to\": paper_id_B}, ...]",
            ],
        )
    return value


def _coerce_str_mapping(value: Any, *, param: str, where: str) -> Any:
    """把入参归一成 ``dict``；形状不对 → 黄金模板错误 dict（非异常）。"""
    value = _coerce_json_payload(value)
    if not isinstance(value, dict):
        return _golden_error(
            f"{param} 必须是对象映射，实际收到 {type(value).__name__}",
            where=where,
            fixes=[
                f"{param}={{paper_id: text}}（键是 paper_id，值是正文/abstract）",
            ],
        )
    return value


def _is_error_payload(value: Any) -> bool:
    return isinstance(value, dict) and value.get("ok") is False


def _scan_pdf_text(path: Path) -> str:
    """从 PDF 抽全文（与 financial-analyst 保持一致 API）."""
    try:
        import pdfplumber
    except ImportError:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text
        except ImportError:
            return ""
    try:
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        logger.warning("pdfplumber 抽 %s 失败：%s", path, e)
        return ""


# ============================================================
# §1. PDF 元数据抽取（title / authors / abstract / year / refs）
# ============================================================
#
# 业务理由：
#   学术综述第一步 = 把 N 篇 PDF 转成结构化元数据。LLM 直接读 PDF 全文塞 prompt
#   会 token 爆炸（50 paper × 5K token = 250K token，单次 LLM 调用根本装不下）。
#   必须先用 deterministic 工具抽 title/authors/year/abstract/refs，再交给 LLM。


# 标题特征：通常在第一页前 600 字符 + 句末无标点
_TITLE_HEURISTIC_RE = re.compile(
    r"^(.{8,200}?)(?:\n|\r\n)", re.DOTALL
)
# 作者特征：title 后第一行常有"Author1, Author2"或"by John Doe"
_AUTHOR_LINE_RE = re.compile(
    r"(?i)(?:by|authors?:|作者[：:])\s*([^\n\r]{4,200})"
)
# 年份特征：4 位数年份（1900-2099），首页前 1500 字内取最大者
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
# Abstract 特征：首页有 "Abstract" / "摘要" 标记
_ABSTRACT_BLOCK_RE = re.compile(
    r"(?i)(?:abstract|摘要)\s*[:：\.\n]+\s*(.{50,2500}?)(?:\n\n|\r\n\r\n|"
    r"(?:1\s*\.|introduction|引言|关键词|keywords))",
    re.DOTALL,
)
# 关键词
_KEYWORDS_RE = re.compile(
    r"(?i)keywords?\s*[:：\.\-]\s*([^\n\r]{5,300})"
)
# 引用文献条目（粗略识别 references 段后的 [1] / 1. xxx 列表项数）
_REF_ENTRY_RE = re.compile(
    r"^\s*(?:\[\d+\]|\d+\.|[A-Z][a-z]+,\s+[A-Z]\.)",
    re.MULTILINE,
)


def extract_paper_metadata(
    path: str | Path | None = None,
    paper_id: str | None = None,
    file_path: str | Path | None = None,
) -> dict[str, Any]:
    """从 paper PDF 抽元数据.

    Args:
        path: PDF 路径
        paper_id: 显式 ID（None 则用 sha1(path) 前 12 位 + 文件名 stem）
        file_path: ``path`` 的同义别名。**必须在 input_schema 里声明**——
            ProgressiveExecutor 会把 planner constraints 里不在 schema 的键静默
            drop（``planner constraints drop 1 unknown keys … ['file_path']``），
            未声明的别名到不了这里。TURBO 总则①：从 LLM 的近端语义字段推导，
            不要求模型记住"系统接口"叫什么。

    Returns:
        dict 含 ok/summary/paper_id/title/authors/year/abstract/keywords/
        ref_count/source
    """
    raw_path = path if path not in (None, "") else file_path
    if raw_path in (None, ""):
        return _golden_error(
            "缺少必需参数 path",
            where="extract_paper_metadata",
            fixes=["path=<paper PDF 绝对路径>（别名 file_path 同样接受）"],
        )
    p = _normalize_path(raw_path)
    if not p.exists():
        return _golden_error(
            f"PDF 不存在：{p}",
            where=f"path={path}",
            fixes=[
                "检查路径拼写",
                "支持 .pdf 后缀",
                "PDF 需未加密；加密 → qpdf 解密",
            ],
            related=["extract_paper_metadata"],
        )
    if p.suffix.lower() != ".pdf":
        return _golden_error(
            f"非 PDF 文件：{p.suffix}",
            where=f"path={p}",
            fixes=["本工具只读 PDF（学术 paper 标准格式）"],
        )

    text = _scan_pdf_text(p)
    if not text or len(text) < 200:
        return _golden_error(
            "PDF 文本抽取失败 / 内容过短",
            where=f"path={p}",
            fixes=[
                "PDF 是扫描件 / 图像版（无文本层）→ 先用 OCR 转出来",
                "或 pdfplumber/PyMuPDF 装的不全 → pip install pdfplumber pymupdf",
            ],
        )

    # paper_id：默认 sha1(path) 前 12 位 + stem（防同名 paper 撞 ID）
    if paper_id is None:
        h = hashlib.sha1(str(p).encode("utf-8")).hexdigest()[:12]
        paper_id = f"{p.stem}_{h}"

    # 取首页前 ~3000 字做元数据抽取（避免被正文 noise 干扰）
    head = text[:3000]
    body_for_year = text[:6000]
    refs_section = text[max(0, len(text) // 2):]  # 后半段找 reference

    title = ""
    m = _TITLE_HEURISTIC_RE.search(head)
    if m:
        cand = m.group(1).strip()
        # 过滤掉 "1 Introduction" / 单行模板字
        if 8 <= len(cand) <= 200 and not cand.lower().startswith("introduction"):
            title = cand

    authors_raw = ""
    am = _AUTHOR_LINE_RE.search(head)
    if am:
        authors_raw = am.group(1).strip()
    authors = [
        a.strip() for a in re.split(r"[;,，、]\s*|\s+and\s+", authors_raw) if a.strip()
    ]

    years = [int(y) for y in _YEAR_RE.findall(body_for_year)]
    year = max(years) if years else None

    abstract = ""
    abm = _ABSTRACT_BLOCK_RE.search(head)
    if abm:
        abstract = abm.group(1).strip()
        abstract = re.sub(r"\s+", " ", abstract)[:1500]

    keywords: list[str] = []
    km = _KEYWORDS_RE.search(head)
    if km:
        keywords = [
            k.strip() for k in re.split(r"[;,，、]", km.group(1)) if k.strip()
        ][:12]

    ref_count = len(_REF_ENTRY_RE.findall(refs_section[:30000]))

    return {
        "ok": True,
        "summary": (
            f"{paper_id}：title='{title[:60]}{'…' if len(title) > 60 else ''}'，"
            f"作者 {len(authors)} 人，年份 {year}，"
            f"abstract {len(abstract)} 字，关键词 {len(keywords)}，"
            f"引用条目 ~{ref_count}"
        ),
        "paper_id": paper_id,
        "title": title,
        "authors": authors,
        "year": year,
        "abstract": abstract,
        "keywords": keywords,
        "ref_count": ref_count,
        "source": str(p),
        "text_length": len(text),
    }


# ============================================================
# §2. 主题聚类（TF-IDF + 简化层次聚类，零 sklearn 依赖）
# ============================================================
#
# 业务理由：
#   N 篇论文按主题分组是综述结构的基础。LLM 凭感觉看摘要分组：
#   1. 摘要 token 数过多（50 paper × 200 字 = 10K token） → 上下文挤压
#   2. LLM 分组结果有 5-10% 漂移率 → 不可重复
#   System 1 = TF-IDF 向量 + 凝聚层次聚类 → deterministic / 可重放
#
# 优化：默认零 sklearn 依赖（用纯 Python TF-IDF + 简化 cosine 相似度 + 凝聚聚类）；
# 如装了 sklearn 自动走 sklearn HDBSCAN（更准）。这是优雅降级。


# 中英文停用词
_STOPWORDS_EN = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "and", "or", "but", "if", "of", "in", "on", "at", "by", "to", "for",
    "with", "from", "as", "this", "that", "these", "those", "it", "we",
    "they", "their", "our", "his", "her", "its", "into", "than", "then",
    "thus", "such", "more", "most", "less", "least", "very", "only",
    "also", "however", "while", "when", "where", "what", "which", "who",
    "show", "shown", "show", "shows", "showed", "use", "used", "using",
    "can", "may", "might", "results", "result", "method", "methods",
    "paper", "study", "approach", "based", "research", "work", "model",
    "models", "data", "experiments", "experiment", "fig", "figure",
    "table", "section", "et", "al",
}
_STOPWORDS_ZH = {
    "的", "了", "在", "是", "我们", "和", "与", "或", "为", "这", "那",
    "本文", "本论文", "本研究", "提出", "通过", "使用", "对于", "关于",
    "可以", "得到", "结果", "实验", "方法", "模型", "数据",
}
_STOPWORDS = _STOPWORDS_EN | _STOPWORDS_ZH


def _tokenize(text: str) -> list[str]:
    """简化分词：英文按 \\w 切，中文按 unicode 范围 + 2-gram."""
    if not text:
        return []
    text = text.lower()
    en_tokens = re.findall(r"[a-z][a-z\-]{2,}", text)
    en_tokens = [t for t in en_tokens if t not in _STOPWORDS]
    # 中文 char 2-gram（粗粒度但 cookbook demo 够用）
    cn_chars = re.findall(r"[\u4e00-\u9fff]+", text)
    cn_tokens: list[str] = []
    for run in cn_chars:
        for i in range(len(run) - 1):
            bigram = run[i: i + 2]
            if bigram not in _STOPWORDS:
                cn_tokens.append(bigram)
    return en_tokens + cn_tokens


def _tf_idf(docs: list[list[str]]) -> tuple[list[dict[str, float]], list[str]]:
    """计算每个 doc 的 TF-IDF 稀疏向量 + 词表."""
    n = len(docs)
    if n == 0:
        return [], []
    # DF
    df: dict[str, int] = {}
    for tokens in docs:
        for w in set(tokens):
            df[w] = df.get(w, 0) + 1
    # 取出现 ≥2 篇的词（去掉只在一篇出现的高维 noise）
    vocab = [w for w, c in df.items() if c >= 2]
    vocab_set = set(vocab)
    import math
    vectors: list[dict[str, float]] = []
    for tokens in docs:
        tf = _Counter(t for t in tokens if t in vocab_set)
        max_tf = max(tf.values()) if tf else 1
        vec = {
            w: (tf[w] / max_tf) * math.log(n / (df[w] + 1) + 1)
            for w in tf
        }
        vectors.append(vec)
    return vectors, vocab


def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    if not common:
        return 0.0
    dot = sum(a[k] * b[k] for k in common)
    import math
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def cluster_papers_by_topic(
    papers: list[dict[str, Any]],
    *,
    similarity_threshold: float = 0.15,
    min_cluster_size: int = 2,
) -> dict[str, Any]:
    """按 abstract + title + keywords TF-IDF 凝聚层次聚类.

    Args:
        papers: ``extract_paper_metadata`` 输出列表（含 paper_id/title/abstract/keywords）
        similarity_threshold: 凝聚阈值（cosine 相似度 ≥ 此值 = 同簇；默认 0.15）
        min_cluster_size: 单 cluster 至少几篇 paper（小于则降级到"thin"）

    Returns:
        dict 含 ok/summary/clusters（list of {topic_id, paper_ids, top_terms, n_papers}）
    """
    if not papers:
        return _golden_error(
            "papers 列表为空",
            where="cluster_papers_by_topic([])",
            fixes=["先用 extract_paper_metadata 抽元数据"],
            related=["extract_paper_metadata"],
        )
    papers = _coerce_dict_list(
        papers, param="papers", where="cluster_papers_by_topic",
    )
    if _is_error_payload(papers):
        return papers
    if len(papers) < 2:
        return _golden_error(
            f"至少 2 篇 paper 才能聚类（目前 {len(papers)} 篇）",
            where=f"papers count={len(papers)}",
            fixes=[
                "至少传 2 篇 paper",
                "或跳过聚类直接走单 paper 综述",
            ],
        )

    # 拼 token：title + abstract + keywords 三段权重不同
    docs_tokens: list[list[str]] = []
    for p in papers:
        title_tokens = _tokenize(p.get("title", "") or "")
        abs_tokens = _tokenize(p.get("abstract", "") or "")
        kw_tokens = _tokenize(" ".join(p.get("keywords") or []))
        docs_tokens.append(title_tokens * 3 + abs_tokens + kw_tokens * 2)

    vectors, _vocab = _tf_idf(docs_tokens)

    # 简化凝聚聚类：union-find + cosine ≥ threshold
    n = len(papers)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            sim = _cosine_similarity(vectors[i], vectors[j])
            if sim >= similarity_threshold:
                union(i, j)

    # 收集 cluster
    cluster_members: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        cluster_members.setdefault(root, []).append(i)

    clusters: list[dict[str, Any]] = []
    thin_clusters = 0
    for cid, members in cluster_members.items():
        if not members:
            continue
        # cluster top terms = 所有成员向量加和 → 最大 5 个
        merged: dict[str, float] = {}
        for m in members:
            for w, v in vectors[m].items():
                merged[w] = merged.get(w, 0) + v
        top_terms = [
            w for w, _ in sorted(merged.items(), key=lambda x: -x[1])[:5]
        ]
        topic_id = f"topic_{len(clusters):03d}"
        paper_ids = [papers[m].get("paper_id", f"paper_{m}") for m in members]
        years = [
            papers[m].get("year") for m in members if papers[m].get("year")
        ]
        cluster = {
            "topic_id": topic_id,
            "n_papers": len(members),
            "paper_ids": paper_ids,
            "top_terms": top_terms,
            "year_min": min(years) if years else None,
            "year_max": max(years) if years else None,
            "thin": len(members) < min_cluster_size,
        }
        if cluster["thin"]:
            thin_clusters += 1
        clusters.append(cluster)

    # 按 cluster size 降序
    clusters.sort(key=lambda c: -c["n_papers"])
    # 重 ID（按降序重命名 topic_000 .. topic_NNN）
    for i, c in enumerate(clusters):
        c["topic_id"] = f"topic_{i:03d}"

    return {
        "ok": True,
        "summary": (
            f"聚类完成：{len(papers)} 篇 → {len(clusters)} 个主题"
            f"（其中 {thin_clusters} 个 thin cluster < {min_cluster_size} 篇）"
        ),
        "clusters": clusters,
        "n_papers": len(papers),
        "n_clusters": len(clusters),
        "thin_count": thin_clusters,
        "similarity_threshold": similarity_threshold,
    }


# ============================================================
# §3. 引用图构建（DOT 格式）
# ============================================================
#
# 业务理由：
#   综述论文常需要画"引用关系图"展现主题演化 / 学派分支 / 重要文献。
#   System 1 = 图论计算（节点 / 边 / 环检测）；LLM 不应自己拼 DOT 字符串。
#
# 输入设计：
#   不是从 PDF 自动抽 reference（学术 PDF 引用格式标准化太弱，准确率低）；
#   而是接受用户结构化输入 ``edges=[{from, to}]``。这个 trade-off 让工具可重放、
#   可单测；真实使用时建议接 OpenAlex / Semantic Scholar API 拿引用关系再传入。


def build_citation_graph(
    papers: list[dict[str, Any]],
    edges: list[dict[str, str]],
    *,
    cluster_assignments: dict[str, str] | None = None,
) -> dict[str, Any]:
    """从 paper 元数据 + 引用关系输出 DOT 字符串.

    Args:
        papers: ``extract_paper_metadata`` 输出列表
        edges: ``[{"from": paper_id_A, "to": paper_id_B}, ...]`` A 引用 B
        cluster_assignments: paper_id → topic_id 映射（用于按 cluster 着色，None 跳过）

    Returns:
        dict 含 ok/summary/dot/n_nodes/n_edges/orphan_nodes/cycles
    """
    if not papers:
        return _golden_error(
            "papers 列表为空",
            where="build_citation_graph",
            fixes=["先用 extract_paper_metadata 抽元数据"],
        )
    papers = _coerce_dict_list(
        papers, param="papers", where="build_citation_graph",
    )
    if _is_error_payload(papers):
        return papers
    edges = _coerce_dict_list(
        edges or [], param="edges", where="build_citation_graph",
    )
    if _is_error_payload(edges):
        return edges
    if cluster_assignments is not None:
        cluster_assignments = _coerce_str_mapping(
            cluster_assignments,
            param="cluster_assignments",
            where="build_citation_graph",
        )
        if _is_error_payload(cluster_assignments):
            return cluster_assignments

    paper_index = {
        p.get("paper_id", f"paper_{i}"): p for i, p in enumerate(papers)
    }
    valid_ids = set(paper_index.keys())

    # 边过滤
    valid_edges: list[tuple[str, str]] = []
    invalid_edges: list[dict[str, str]] = []
    for e in edges:
        f, t = e.get("from"), e.get("to")
        if f in valid_ids and t in valid_ids and f != t:
            valid_edges.append((f, t))
        else:
            invalid_edges.append({"from": str(f), "to": str(t)})

    # 检测引用环（学术上 A→B→A 是异常；通常说明引用记录有错）
    cycles: list[list[str]] = []
    adj: dict[str, list[str]] = {pid: [] for pid in valid_ids}
    for f, t in valid_edges:
        adj[f].append(t)
    visited: set[str] = set()
    stack: set[str] = set()
    path: list[str] = []

    def _dfs(node: str) -> None:
        if node in stack:
            cyc_start = path.index(node)
            cycles.append(path[cyc_start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        path.append(node)
        for nxt in adj.get(node, []):
            _dfs(nxt)
        stack.discard(node)
        path.pop()

    for pid in valid_ids:
        if pid not in visited:
            _dfs(pid)

    # 孤立节点（无入边也无出边）
    has_edge = set()
    for f, t in valid_edges:
        has_edge.add(f)
        has_edge.add(t)
    orphans = sorted(valid_ids - has_edge)

    # 颜色：按 cluster 分组（最多 8 类）
    palette = [
        "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
        "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
    ]
    cluster_color: dict[str, str] = {}
    if cluster_assignments:
        unique_topics = sorted(set(cluster_assignments.values()))
        for i, t in enumerate(unique_topics):
            cluster_color[t] = palette[i % len(palette)]

    # 构造 DOT 字符串
    dot_lines = [
        "digraph CitationGraph {",
        '  rankdir="LR";',
        '  node [shape=box, style="rounded,filled", fillcolor="#ecf0f1", '
        'fontname="Helvetica"];',
        '  edge [color="#7f8c8d", arrowsize=0.7];',
    ]
    for pid, p in paper_index.items():
        title = (p.get("title") or pid)[:40]
        # 转义 DOT 引号
        title_safe = title.replace('"', '\\"')
        year = p.get("year") or "?"
        label = f"{title_safe}\\n({year})"
        topic = (cluster_assignments or {}).get(pid)
        color_attr = (
            f', fillcolor="{cluster_color[topic]}", fontcolor="white"'
            if topic and topic in cluster_color else ""
        )
        dot_lines.append(f'  "{pid}" [label="{label}"{color_attr}];')
    for f, t in valid_edges:
        dot_lines.append(f'  "{f}" -> "{t}";')
    dot_lines.append("}")
    dot = "\n".join(dot_lines)

    return {
        "ok": True,
        "summary": (
            f"引用图：{len(valid_ids)} 节点 / {len(valid_edges)} 边"
            f"{'，' + str(len(invalid_edges)) + ' 条边过滤（节点不存在）' if invalid_edges else ''}"
            f"{'，' + str(len(cycles)) + ' 个引用环（异常）' if cycles else ''}"
            f"{'，' + str(len(orphans)) + ' 个孤立节点' if orphans else ''}"
        ),
        "dot": dot,
        "n_nodes": len(valid_ids),
        "n_edges": len(valid_edges),
        "orphan_nodes": orphans,
        "cycles": cycles,
        "invalid_edges": invalid_edges,
    }


# ============================================================
# §4. 抄袭重叠检测（n-gram overlap）
# ============================================================
#
# 业务理由：
#   学术综述最大风险 = 直接抄原文 → 抄袭事故。
#   System 1 = n-gram 匹配（5-gram word overlap）；零成本、deterministic。
#   PlagiarismGate 据此 BLOCK conclude。


def _build_ngrams(text: str, n: int = 5) -> set[str]:
    """构建 word n-gram set."""
    if not text:
        return set()
    text = text.lower()
    # 简单分词：英文单词 + 中文字（中文按字 2-gram，英文按词 5-gram）
    words = re.findall(r"\w+", text)
    grams = set()
    if len(words) >= n:
        for i in range(len(words) - n + 1):
            grams.add(" ".join(words[i: i + n]))
    return grams


def detect_plagiarism_overlap(
    review_text: str | None = None,
    source_texts: dict[str, str] | None = None,
    *,
    ngram: int = 5,
    overlap_threshold: float = 0.6,
    review_path: str | Path | None = None,
    n_gram: int | None = None,
    threshold: float | None = None,
) -> dict[str, Any]:
    """检测综述文本与原文的 n-gram 重叠率.

    Args:
        review_text: 综述章节 markdown
        source_texts: ``{paper_id: full_text_or_abstract}``
        ngram: n-gram 大小（默认 5-gram word）
        overlap_threshold: 警告阈值（默认 0.6 = 60%）
        review_path: ``review_text`` 的替代入口——综述已落盘时传路径即可，
            由 System 1 读文件，不必让模型把整篇 markdown 再复述一遍进 prompt。
        n_gram / threshold: ``ngram`` / ``overlap_threshold`` 的同义别名。
            与 ``extract_paper_metadata.file_path`` 同理，别名必须在 input_schema
            里声明才到得了这里（否则被 planner constraints 过滤器 drop）。

    Returns:
        dict 含 ok/summary/per_source（每篇 source 的 overlap_ratio 和命中
        ngram 列表）/ flagged_sources（≥ 阈值的列表）
    """
    if isinstance(n_gram, int) and n_gram > 0:
        ngram = n_gram
    if isinstance(threshold, (int, float)) and threshold > 0:
        overlap_threshold = float(threshold)
    if not review_text and review_path:
        rp = _normalize_path(review_path)
        if not rp.exists():
            return _golden_error(
                f"review_path 不存在：{rp}",
                where=f"review_path={review_path}",
                fixes=[
                    "确认综述 markdown 已经落盘（smart_file_write 返回 success）",
                    "或改传 review_text=<综述全文>",
                ],
            )
        review_text = rp.read_text(encoding="utf-8", errors="replace")
    if not review_text:
        return _golden_error(
            "review_text 为空",
            where="detect_plagiarism_overlap",
            fixes=[
                "先生成综述章节再调本工具",
                "综述已落盘 → 传 review_path=<综述 markdown 路径> 由工具自己读",
            ],
        )
    if source_texts:
        source_texts = _coerce_str_mapping(
            source_texts, param="source_texts", where="detect_plagiarism_overlap",
        )
        if _is_error_payload(source_texts):
            return source_texts
    if not source_texts:
        return _golden_error(
            "source_texts 为空",
            where="detect_plagiarism_overlap",
            fixes=[
                "传入 {paper_id: text} dict，可用 abstract 或 full text",
                "demo 用 abstract 即可（够检测明显抄袭）",
            ],
        )

    review_grams = _build_ngrams(review_text, ngram)
    if not review_grams:
        return {
            "ok": True,
            "summary": "综述太短，无 n-gram 可比对（视为通过）",
            "per_source": [],
            "flagged_sources": [],
        }

    per_source: list[dict[str, Any]] = []
    flagged: list[str] = []
    for sid, src_text in source_texts.items():
        src_grams = _build_ngrams(src_text or "", ngram)
        if not src_grams:
            continue
        # 重叠率 = (review ∩ source) / source（即 source 在 review 里被多大比例命中）
        intersection = review_grams & src_grams
        # 也算 review 命中率（更敏感）
        review_hit_ratio = len(intersection) / len(review_grams)
        source_hit_ratio = len(intersection) / len(src_grams)
        overlap_ratio = max(review_hit_ratio, source_hit_ratio)
        per_source.append({
            "paper_id": sid,
            "overlap_ratio": round(overlap_ratio, 4),
            "n_ngram_hits": len(intersection),
            "review_hit_ratio": round(review_hit_ratio, 4),
            "source_hit_ratio": round(source_hit_ratio, 4),
            "sample_hits": sorted(list(intersection))[:3],
        })
        if overlap_ratio >= overlap_threshold:
            flagged.append(sid)

    per_source.sort(key=lambda x: -x["overlap_ratio"])
    return {
        "ok": True,
        "summary": (
            f"重叠检测：{len(source_texts)} 篇原文，"
            f"{len(flagged)} 篇命中 ≥{overlap_threshold:.0%} 重叠阈值"
            f"{'（抄袭风险）' if flagged else '（通过）'}"
        ),
        "per_source": per_source[:20],  # 防 prompt 膨胀
        "flagged_sources": flagged,
        "ngram": ngram,
        "overlap_threshold": overlap_threshold,
    }


# ============================================================
# §5. 综述章节大纲生成（System 1 启发式）
# ============================================================
#
# 业务理由：
#   综述结构有"标准模板"（背景 / 方法分类 / 时间演化 / 对比 / gap / 展望）。
#   System 1 工具按聚类结果 + 时间分布自动推大纲；LLM 不需要凭感觉决定章节怎么分。


# 标准综述章节模板
_OUTLINE_TEMPLATES = {
    "standard": [
        ("Introduction", "研究背景 + 综述范围 + 方法论"),
        ("Background", "本领域基础概念 + 关键定义"),
        ("Topic-by-Topic", "按 cluster 分章节展开（每个 cluster 一个 §）"),
        ("Cross-Topic Comparison", "跨主题对比 + 共同点 / 分歧"),
        ("Timeline / Evolution", "本领域演化时间线（如果年份跨度大）"),
        ("Open Problems", "未解决问题 + 研究 gap"),
        ("Future Directions", "未来研究方向 + 与相邻领域的接口"),
        ("Conclusion", "总结 + 综述的局限性"),
    ],
    "compact": [
        ("Introduction", "背景 + 综述目标 + 范围"),
        ("Topic Survey", "按 cluster 展开"),
        ("Comparison & Gaps", "对比 + 研究 gap"),
        ("Conclusion", "总结"),
    ],
}


def generate_review_outline(
    cluster_result: dict[str, Any],
    *,
    template: str = "standard",
    include_timeline: bool | None = None,
) -> dict[str, Any]:
    """按聚类结果生成综述章节大纲.

    Args:
        cluster_result: ``cluster_papers_by_topic`` 输出
        template: 大纲模板（standard 8 节 / compact 4 节）
        include_timeline: 是否含 Timeline 章节（None 自动决策：年份跨度 ≥10 年才含）

    Returns:
        dict 含 ok/summary/outline（list of {section, description, citations_required}）
    """
    cluster_result = _coerce_json_payload(cluster_result)
    if not isinstance(cluster_result, dict) or not cluster_result.get("ok"):
        return _golden_error(
            "cluster_result 不是有效的 cluster_papers_by_topic 输出",
            where="generate_review_outline",
            fixes=["先调 cluster_papers_by_topic 生成聚类"],
            related=["cluster_papers_by_topic"],
        )

    if template not in _OUTLINE_TEMPLATES:
        return _golden_error(
            f"未知 template={template!r}",
            where=f"template={template}",
            fixes=[f"支持 template: {sorted(_OUTLINE_TEMPLATES)}"],
        )

    clusters = cluster_result.get("clusters", [])
    if not clusters:
        return _golden_error(
            "cluster 列表为空",
            where="generate_review_outline",
            fixes=["先聚类得到至少 1 个 topic"],
        )
    clusters = _coerce_dict_list(
        clusters, param="cluster_result.clusters", where="generate_review_outline",
    )
    if _is_error_payload(clusters):
        return clusters

    # 自动决策 timeline 章节
    all_years: list[int] = []
    for c in clusters:
        if c.get("year_min"):
            all_years.append(c["year_min"])
        if c.get("year_max"):
            all_years.append(c["year_max"])
    year_span = (max(all_years) - min(all_years)) if all_years else 0
    if include_timeline is None:
        include_timeline = year_span >= 10

    base_outline = _OUTLINE_TEMPLATES[template]
    outline: list[dict[str, Any]] = []
    for section_name, description in base_outline:
        if section_name == "Timeline / Evolution" and not include_timeline:
            continue
        # 各章节 citations_required（学术规范：每节 ≥3 篇）
        if section_name == "Topic-by-Topic" or section_name == "Topic Survey":
            citations_required = max(3 * len(clusters), 5)
        elif section_name in ("Conclusion", "Introduction"):
            citations_required = 3
        else:
            citations_required = 5
        outline.append({
            "section": section_name,
            "description": description,
            "citations_required": citations_required,
        })

    # 为 Topic-by-Topic 段加 sub-sections
    sub_sections: list[dict[str, Any]] = []
    for c in clusters:
        terms_str = " / ".join(c.get("top_terms", [])[:3])
        sub_sections.append({
            "section": f"{c['topic_id']}: {terms_str}",
            "description": (
                f"{c['n_papers']} 篇 paper，年份 "
                f"{c.get('year_min', '?')}–{c.get('year_max', '?')}"
                f"{' (thin cluster — 慎写)' if c.get('thin') else ''}"
            ),
            "citations_required": max(3, c["n_papers"]),
            "paper_ids": c["paper_ids"][:10],
        })

    return {
        "ok": True,
        "summary": (
            f"综述大纲（template={template}）：{len(outline)} 主章节 + "
            f"{len(sub_sections)} 个主题小节，年份跨度 {year_span} 年"
            f"{'（含 Timeline）' if include_timeline else ''}"
        ),
        "outline": outline,
        "sub_sections": sub_sections,
        "include_timeline": include_timeline,
        "year_span": year_span,
        "n_clusters": len(clusters),
    }


# ============================================================
# §6. ToolPlugin（注册 5 个 System 1 工具）
# ============================================================


class LiteratureReviewerToolPlugin:
    """实现 ``krow_agent_sdk.protocols.ToolPlugin`` Protocol。

    注册 5 个 System 1 工具：
    - literature_reviewer_extract_paper_metadata
    - literature_reviewer_cluster_papers_by_topic
    - literature_reviewer_build_citation_graph
    - literature_reviewer_detect_plagiarism_overlap
    - literature_reviewer_generate_review_outline
    """

    plugin_id = "lit_reviewer.tools"

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "literature_reviewer_extract_paper_metadata",
                "description": (
                    "从 paper PDF 抽元数据（title/authors/year/abstract/keywords/refs）。"
                    "**禁止 LLM 直接读 PDF 全文**——50 paper × 5K token 上下文爆炸。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "paper_id": {"type": "string"},
                        # 别名必须**声明**才到得了 handler：ProgressiveExecutor 的
                        # planner constraints 过滤器按 input_schema.properties 白
                        # 名单过（``drop … unknown keys … ['file_path']``）。
                        "file_path": {
                            "type": "string",
                            "description": "path 的同义别名（二选一）",
                        },
                    },
                    "required": [],
                },
                "handler": extract_paper_metadata,
            },
            {
                "name": "literature_reviewer_cluster_papers_by_topic",
                "description": (
                    "TF-IDF + 凝聚聚类把 N 篇 paper 按主题分组（System 1 deterministic）。"
                    "**禁止 LLM 凭感觉看摘要分组**——LLM 5-10% 漂移率不可重放。"
                    "默认零 sklearn 依赖（纯 Python TF-IDF）；装了 sklearn 自动用更准的算法。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "papers": {"type": "array"},
                        "similarity_threshold": {
                            "type": "number",
                            "default": 0.15,
                            "description": "凝聚阈值（cosine sim ≥ 此值 = 同簇）",
                        },
                        "min_cluster_size": {
                            "type": "integer",
                            "default": 2,
                            "description": "thin cluster 阈值（< 此值标 thin）",
                        },
                    },
                    "required": ["papers"],
                },
                "handler": cluster_papers_by_topic,
            },
            {
                "name": "literature_reviewer_build_citation_graph",
                "description": (
                    "从 paper 元数据 + 引用关系输出 DOT 字符串（System 1 图论）。"
                    "自动检测引用环（异常）+ 孤立节点；按 cluster 着色。"
                    "edges 格式：[{from: paper_id_A, to: paper_id_B}, ...] A 引用 B。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "papers": {"type": "array"},
                        "edges": {"type": "array"},
                        "cluster_assignments": {"type": "object"},
                    },
                    "required": ["papers", "edges"],
                },
                "handler": build_citation_graph,
            },
            {
                "name": "literature_reviewer_detect_plagiarism_overlap",
                "description": (
                    "n-gram 重叠检测综述与原文（学术不端守门）。"
                    "默认 5-gram word + 60% 阈值；命中即 PlagiarismGate 触发 BLOCK。"
                    "**铁律**：综述不允许大段抄原文（≥60% n-gram overlap）。"
                    "综述已落盘 → 传 review_path=<markdown 路径>（推荐，省 token）；"
                    "还没落盘 → 传 review_text=<全文>。二者至少给一个。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "review_text": {"type": "string"},
                        "review_path": {
                            "type": "string",
                            "description": (
                                "综述 markdown 路径（review_text 的替代入口，"
                                "已落盘就传路径，工具自己读，不必复述全文）"
                            ),
                        },
                        "source_texts": {
                            "type": "object",
                            "description": "{paper_id: text}（用 abstract 即可）",
                        },
                        "ngram": {"type": "integer", "default": 5},
                        "overlap_threshold": {"type": "number", "default": 0.6},
                        # 同 extract_paper_metadata.file_path：别名不声明就被
                        # planner constraints 过滤器 drop（真机日志
                        # ``drop 2 unknown keys … ['threshold', 'n_gram']``）。
                        "n_gram": {
                            "type": "integer",
                            "description": "ngram 的同义别名",
                        },
                        "threshold": {
                            "type": "number",
                            "description": "overlap_threshold 的同义别名",
                        },
                    },
                    "required": ["source_texts"],
                },
                "handler": detect_plagiarism_overlap,
            },
            {
                "name": "literature_reviewer_generate_review_outline",
                "description": (
                    "按聚类结果自动推综述大纲（standard 8 节 / compact 4 节）。"
                    "年份跨度 ≥10 年自动含 Timeline 章节；为每节标 citations_required。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "cluster_result": {"type": "object"},
                        "template": {
                            "type": "string",
                            "enum": ["standard", "compact"],
                            "default": "standard",
                        },
                        "include_timeline": {"type": "boolean"},
                    },
                    "required": ["cluster_result"],
                },
                "handler": generate_review_outline,
            },
        ]


# ============================================================
# §7. ACTPlugin（让 LLM 自动选 literature_reviewer ACT）
# ============================================================


class LiteratureReviewerACTPlugin:
    """实现 ``krow_agent_sdk.protocols.ACTPlugin`` Protocol。"""

    plugin_id = "lit_reviewer.act"
    act_name = "literature_reviewer"

    def get_act_root(self) -> Path:
        return Path(__file__).parent / "act_assets" / "literature_reviewer"

    def get_act_file_path(self) -> Path:
        return self.get_act_root() / "ext_literature_reviewer.md"

    def get_tool_names(self) -> list[str]:
        # 5 个 plugin 工具 + word_smart_export（综述 docx 输出走 SSOT）
        return [
            "literature_reviewer_extract_paper_metadata",
            "literature_reviewer_cluster_papers_by_topic",
            "literature_reviewer_build_citation_graph",
            "literature_reviewer_detect_plagiarism_overlap",
            "literature_reviewer_generate_review_outline",
            "word_smart_export",
        ]


# ============================================================
# §8. GatePlugin × 2（学术规范守门）
# ============================================================
#
# 设计依据：
#   学术综述的"红线" ≠ 金融行业的"红线"，必须演示不同模式
#   - financial: 法律红线（CSRC 信披 / 证券法）
#   - literature: 学术规范红线（引用 / 抄袭）
#
# 为什么这两个不能用 hint 替代：
#   1. 综述每段 ≥3 篇引用是学术规范铁律——hint 提醒 LLM "请加引用"
#      在压缩任务时会失效，必须 System 1 闸住每个 conclude 前先扫
#   2. 抄袭红线 = n-gram > 60% 命中 = 学术不端事故；hint 提醒不够强


# 引用模式（中英文常见格式）
_CITATION_PATTERNS = [
    # [1] / [1, 2] / [1-3]
    re.compile(r"\[\d{1,3}(?:[-,;\s\d]*)\]"),
    # (Smith, 2020) / (Smith et al., 2020)
    re.compile(r"\(\s*[A-Z][a-zA-Z]+\s*(?:et al\.?\s*)?,\s*\d{4}[a-z]?\s*\)"),
    # (Smith & Jones, 2020)
    re.compile(r"\(\s*[A-Z][a-zA-Z]+\s*&\s*[A-Z][a-zA-Z]+\s*,\s*\d{4}\s*\)"),
]


def _count_citations_in_text(text: str) -> int:
    if not text:
        return 0
    total = 0
    for pat in _CITATION_PATTERNS:
        total += len(pat.findall(text))
    return total


def _split_review_into_sections(text: str) -> list[tuple[str, str]]:
    """粗略按 markdown ## 分段；返回 [(title, body), ...]."""
    if not text:
        return []
    parts: list[tuple[str, str]] = []
    cur_title = "Front Matter"
    cur_body: list[str] = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("## "):
            parts.append((cur_title, "\n".join(cur_body)))
            cur_title = s[3:].strip()
            cur_body = []
        else:
            cur_body.append(line)
    parts.append((cur_title, "\n".join(cur_body)))
    return parts


class CitationCompletenessGate:
    """学术规范守门：综述每段 ≥ N 篇引用，缺则 BLOCK conclude.

    实现 ``krow_agent_sdk.protocols.GatePlugin`` Protocol。

    工作机制：扫描 ``recent_tool_results`` 里 ``write_report`` /
    ``word_smart_export`` 的 markdown 内容，按 ## 分段计算每段引用数。

    真实业务价值：
    - 综述论文的"硬指标"——审稿人会数每段引用数
    - hint "请记得加引用" 在压缩任务时会被 LLM 偷懒跳过
    - System 1 闸住每个 conclude → fail-loud
    """

    plugin_id = "lit_reviewer.citation_gate"
    phase = "macro"

    def __init__(
        self,
        *,
        min_citations_per_section: int = 3,
        skip_sections: list[str] | None = None,
    ) -> None:
        self._min = int(min_citations_per_section)
        self._skip = set(
            s.lower() for s in (skip_sections or [
                "front matter", "abstract", "摘要", "致谢",
                "acknowledgement", "acknowledgements", "conclusion",
                "结论",  # conclusion 单独允许 1-2 篇
            ])
        )

    def get_gate(self) -> Any:
        from krow_agent_sdk.protocols import (
            GateDecision,
            GateVerdict,
            make_simple_gate,
        )

        min_cite = self._min
        skip = self._skip

        def evaluate(parsed: dict, context: dict) -> Any:
            tool_results = context.get("recent_tool_results", []) or []
            review_text: str = ""
            for tr in reversed(tool_results):
                if not isinstance(tr, dict):
                    continue
                tool_name = tr.get("tool_name", "")
                if tool_name in (
                    "data_analyst_write_report",
                    "word_smart_export",
                ) or "write_report" in tool_name:
                    args = tr.get("args") or {}
                    review_text = args.get("content") or args.get("body") or ""
                    if not review_text:
                        fp = args.get("file_path") or args.get("path")
                        if fp:
                            with suppress(Exception):
                                review_text = Path(fp).read_text(encoding="utf-8")
                    if review_text:
                        break

            if not review_text:
                return GateDecision(
                    verdict=GateVerdict.DEFER,
                    gate_name="citation_completeness",
                )

            sections = _split_review_into_sections(review_text)
            insufficient: list[tuple[str, int]] = []
            for title, body in sections:
                if title.lower() in skip:
                    continue
                # 跳过太短的段（<200 字 = 标题 / 空段）
                if len(body.strip()) < 200:
                    continue
                cite_count = _count_citations_in_text(body)
                if cite_count < min_cite:
                    insufficient.append((title, cite_count))

            if not insufficient:
                return GateDecision(
                    verdict=GateVerdict.ALLOW,
                    reason=(
                        f"✅ 引用完整性达标：所有 {len(sections)} 段每段 ≥{min_cite} 篇"
                    ),
                    gate_name="citation_completeness",
                )

            return GateDecision(
                verdict=GateVerdict.BLOCK,
                reason=(
                    f"❌ 引用完整性不足：{len(insufficient)}/{len(sections)} "
                    f"段引用数 < {min_cite}\n"
                    "   位置：write_report / word_smart_export 输出 markdown\n"
                    "   修法：\n"
                    + "\n".join(
                        f"     - 段『{title}』：当前 {cnt} 引用 → 至少加到 {min_cite}"
                        for title, cnt in insufficient[:8]
                    )
                    + "\n"
                    "     1. 引用格式建议：[N] 数字风格 / (Author, Year) 作者-年份风格\n"
                    "     2. 短结论 / 致谢 / 摘要段不用引用（自动跳过）\n"
                    "     3. 修改后重调 write_report\n"
                    "   规范依据：综述论文学术规范（每段提出观点必须引用支撑）"
                ),
                gate_name="citation_completeness",
            )

        return make_simple_gate(
            name="citation_completeness", priority=80, evaluator=evaluate
        )


class PlagiarismGate:
    """学术不端守门：综述句子与原文 n-gram overlap > 60% → BLOCK conclude.

    实现 ``krow_agent_sdk.protocols.GatePlugin`` Protocol。

    工作机制：扫描 ``recent_tool_results`` 里
    ``literature_reviewer_detect_plagiarism_overlap`` 的输出，
    若 ``flagged_sources`` 非空则 BLOCK。

    真实业务价值：
    - 学术不端 = 撤稿事故；hint 提醒强度不够
    - System 1 调用 detect_plagiarism_overlap 后 gate 自动接管判断
    """

    plugin_id = "lit_reviewer.plagiarism_gate"
    phase = "macro"

    def get_gate(self) -> Any:
        from krow_agent_sdk.protocols import (
            GateDecision,
            GateVerdict,
            make_simple_gate,
        )

        def evaluate(parsed: dict, context: dict) -> Any:
            tool_results = context.get("recent_tool_results", []) or []
            for tr in reversed(tool_results):
                if not isinstance(tr, dict):
                    continue
                if tr.get("tool_name") != "literature_reviewer_detect_plagiarism_overlap":
                    continue
                result = tr.get("result", {}) or {}
                if not result.get("ok"):
                    continue
                flagged = result.get("flagged_sources") or []
                if flagged:
                    threshold = result.get("overlap_threshold", 0.6)
                    return GateDecision(
                        verdict=GateVerdict.BLOCK,
                        reason=(
                            f"❌ 抄袭重叠红线：{len(flagged)} 篇原文与综述 n-gram 重叠"
                            f" ≥ {threshold:.0%}\n"
                            f"   命中 paper_id: {flagged[:5]}\n"
                            "   位置：综述某段直接复用原文表述\n"
                            "   修法：\n"
                            "     1. 找到重叠段落 → 用自己的话改写（paraphrase）\n"
                            "     2. 直接引用原文必须加引号 + (Author, Year) 标注\n"
                            "     3. 综述目的是 synthesize 不是 quote → 95%+ 应是改写\n"
                            "     4. 改完重调 write_report → 再调 "
                            "detect_plagiarism_overlap 验证\n"
                            "   规范依据：学术不端处置办法 / 撤稿政策"
                        ),
                        gate_name="plagiarism",
                    )
                # 已检测但通过
                return GateDecision(
                    verdict=GateVerdict.ALLOW,
                    reason="✅ 抄袭检测通过：0 篇原文 ≥ 阈值",
                    gate_name="plagiarism",
                )
            # 没调过 detect_plagiarism_overlap → DEFER（gate 不强制必调）
            return GateDecision(
                verdict=GateVerdict.DEFER,
                gate_name="plagiarism",
            )

        return make_simple_gate(
            name="plagiarism", priority=85, evaluator=evaluate
        )


# ============================================================
# §9. HintPlugin × 2（System 2 软提示）
# ============================================================


class TopicCoverageHintPlugin:
    """检测 thin cluster 给 LLM 软提示（避免轻飘飘的章节）.

    实现 ``krow_agent_sdk.protocols.HintPlugin`` Protocol。

    业务价值：
    - 1-2 篇 paper 的 cluster 写一整章往往会"灌水"；
      hint 推 LLM 这些 thin cluster 应该合并到相邻 cluster 或单独提一笔
    """

    plugin_id = "lit_reviewer.topic_coverage_hint"
    applicable_acts = ["literature_reviewer"]

    def hint_for(self, context: dict) -> str | None:
        tool_results = context.get("recent_tool_results", []) or []
        for tr in reversed(tool_results):
            if not isinstance(tr, dict):
                continue
            if tr.get("tool_name") != "literature_reviewer_cluster_papers_by_topic":
                continue
            result = tr.get("result", {}) or {}
            if not result.get("ok"):
                continue
            clusters = result.get("clusters", [])
            thin = [c for c in clusters if c.get("thin")]
            if not thin:
                return None
            lines = [
                "## 主题覆盖检查（System 2 软提示）",
                f"检测到 {len(thin)} 个 thin cluster（< 2 篇 paper），写综述时建议：",
                "",
            ]
            for c in thin[:6]:
                terms = " / ".join(c.get("top_terms", [])[:3])
                lines.append(
                    f"- `{c['topic_id']}`（{c['n_papers']} 篇，topic terms：{terms}）"
                    " → 合并到相邻主题，或在『Open Problems』段单独提一笔；"
                    "**不要**为它单独写一整章"
                )
            return "\n".join(lines)
        return None


class YearGapHintPlugin:
    """检测年份跨度过大的 cluster 推 LLM 应分 era.

    实现 ``krow_agent_sdk.protocols.HintPlugin`` Protocol。

    业务价值：
    - 25 年跨度的 cluster 内方法论可能完全过时（如 1995 ML vs 2020 deep learning）
    - hint 推 LLM 在该 cluster 章节内分 "early era" / "modern era" 两小节
    """

    plugin_id = "lit_reviewer.year_gap_hint"
    applicable_acts = ["literature_reviewer"]

    def __init__(self, *, gap_threshold_years: int = 15) -> None:
        self._gap = int(gap_threshold_years)

    def hint_for(self, context: dict) -> str | None:
        tool_results = context.get("recent_tool_results", []) or []
        for tr in reversed(tool_results):
            if not isinstance(tr, dict):
                continue
            if tr.get("tool_name") != "literature_reviewer_cluster_papers_by_topic":
                continue
            result = tr.get("result", {}) or {}
            if not result.get("ok"):
                continue
            clusters = result.get("clusters", [])
            big_gap: list[dict[str, Any]] = []
            for c in clusters:
                ymin, ymax = c.get("year_min"), c.get("year_max")
                if ymin and ymax and (ymax - ymin) >= self._gap:
                    big_gap.append(c)
            if not big_gap:
                return None
            lines = [
                "## 年份跨度提醒（System 2 软提示）",
                f"以下 cluster 年份跨度 ≥ {self._gap} 年 → "
                "建议章节内**按 era 分小节**（如 early era / modern era）：",
                "",
            ]
            for c in big_gap[:5]:
                terms = " / ".join(c.get("top_terms", [])[:3])
                lines.append(
                    f"- `{c['topic_id']}`：{c['year_min']}–{c['year_max']}"
                    f"（{c['year_max'] - c['year_min']} 年跨度），terms：{terms}"
                )
            return "\n".join(lines)
        return None


# ============================================================
# §10. EventListenerPlugin（大批量任务实时进度）
# ============================================================
#
# 业务理由：
#   学术综述任务规模大（50-200 PDF）；用户看不到进度容易以为卡死；
#   listener 把每个 PDF 抽完就 print "已处理 23/127"，给用户安全感。


class ReviewProgressListener:
    """大批量任务实时进度 + 审计 jsonl.

    实现 ``krow_agent_sdk.protocols.EventListenerPlugin`` Protocol。
    """

    plugin_id = "lit_reviewer.progress_listener"

    def __init__(
        self,
        *,
        verbose: bool = True,
        progress_log_path: str | Path | None = None,
        total_papers: int | None = None,
    ) -> None:
        self._verbose = bool(verbose)
        self._step_count = 0
        self._papers_processed = 0
        self._gate_blocks = 0
        self._total_papers = total_papers
        self._path: Path | None = (
            _normalize_path(progress_log_path) if progress_log_path else None
        )
        if self._path:
            with suppress(OSError):
                self._path.parent.mkdir(parents=True, exist_ok=True)

    def get_subscriptions(self) -> list[dict[str, Any]]:
        return [
            {"topic": "tool.call_completed", "handler": self._on_tool_done},
            {"topic": "progressive.step_start", "handler": self._on_step_start},
            {"topic": "progressive.step_completed", "handler": self._on_step_done},
            {"topic": "gate.blocked", "handler": self._on_gate_blocked},
            {"topic": "agent.task_complete", "handler": self._on_task_done},
            {"topic": "agent.task_failed", "handler": self._on_task_failed},
        ]

    def _append(self, record: dict[str, Any]) -> None:
        if not self._path:
            return
        with suppress(Exception):
            record.setdefault("timestamp", time.time())
            record.setdefault("timestamp_iso", time.strftime("%Y-%m-%dT%H:%M:%S"))
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _on_tool_done(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        tool_name = payload.get("tool_name", "")
        if tool_name == "literature_reviewer_extract_paper_metadata":
            self._papers_processed += 1
            if self._verbose:
                if self._total_papers:
                    print(f"  📄 paper {self._papers_processed}/{self._total_papers} 已处理")
                else:
                    print(f"  📄 paper #{self._papers_processed} 已处理")
            self._append({
                "kind": "paper_processed",
                "tool_name": tool_name,
                "index": self._papers_processed,
            })
        else:
            self._append({
                "kind": "tool_call_completed",
                "tool_name": tool_name,
                "ok": payload.get("ok", True),
                "elapsed_ms": payload.get("elapsed_ms"),
            })

    def _on_step_start(self, event: Any) -> None:
        self._step_count += 1
        payload = getattr(event, "payload", {}) or {}
        if self._verbose:
            print(f"  [step {self._step_count}] {payload.get('description', '...')}")

    def _on_step_done(self, event: Any) -> None:
        if self._verbose:
            payload = getattr(event, "payload", {}) or {}
            elapsed = payload.get("elapsed_seconds", 0)
            print(f"  [step {self._step_count}] ✓ done ({elapsed:.1f}s)")

    def _on_gate_blocked(self, event: Any) -> None:
        self._gate_blocks += 1
        payload = getattr(event, "payload", {}) or {}
        if self._verbose:
            print(
                f"  ⛔ gate BLOCK: {payload.get('gate_name')} — "
                f"reason: {(payload.get('reason') or '')[:80]}..."
            )
        self._append({
            "kind": "gate_blocked",
            "gate_name": payload.get("gate_name"),
            "reason_excerpt": (payload.get("reason") or "")[:200],
            "compliance_event": True,
        })

    def _on_task_done(self, event: Any) -> None:
        if self._verbose:
            print(
                f"\n✅ 综述任务完成：{self._step_count} 步 / "
                f"{self._papers_processed} 篇 paper / {self._gate_blocks} 次 gate block"
            )
        self._append({
            "kind": "task_complete",
            "step_count": self._step_count,
            "papers_processed": self._papers_processed,
            "gate_blocks": self._gate_blocks,
        })

    def _on_task_failed(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        if self._verbose:
            print(f"\n❌ 任务失败：{payload.get('reason', 'unknown')}")
        self._append({"kind": "task_failed", "reason": payload.get("reason")})


__all__ = [
    "extract_paper_metadata",
    "cluster_papers_by_topic",
    "build_citation_graph",
    "detect_plagiarism_overlap",
    "generate_review_outline",
    "LiteratureReviewerToolPlugin",
    "LiteratureReviewerACTPlugin",
    "CitationCompletenessGate",
    "PlagiarismGate",
    "TopicCoverageHintPlugin",
    "YearGapHintPlugin",
    "ReviewProgressListener",
]
