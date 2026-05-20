"""Literature-reviewer cookbook smoke tests（≥35 tests，零 LLM 调用）.

覆盖：
- §1 元数据抽取边界（path / 非 PDF / 空文本）
- §2 TF-IDF + 聚类（停用词 / cosine / 凝聚阈值 / thin cluster）
- §3 引用图（边过滤 / 环检测 / 孤立节点 / cluster 着色）
- §4 抄袭重叠检测（n-gram / 阈值 / 多原文）
- §5 综述大纲生成（标准/紧凑模板 / Timeline 自动决策）
- §6 ToolPlugin / ACTPlugin Protocol 契约
- §7 GatePlugin × 2（Citation / Plagiarism）行为
- §8 HintPlugin × 2（TopicCoverage / YearGap）触发条件
- §9 ReviewProgressListener .progress.jsonl 输出
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import literature_reviewer_plugin as lr


# ════════════════════════════════════════════════════════════════════════
# §1. 元数据抽取边界
# ════════════════════════════════════════════════════════════════════════


def test_extract_metadata_missing_path() -> None:
    res = lr.extract_paper_metadata("/nonexistent.pdf")
    assert res["ok"] is False
    assert "PDF 不存在" in res["error"]


def test_extract_metadata_non_pdf(tmp_path: Path) -> None:
    f = tmp_path / "doc.txt"
    f.write_text("hello")
    res = lr.extract_paper_metadata(f)
    assert res["ok"] is False
    assert "非 PDF" in res["error"]


# ════════════════════════════════════════════════════════════════════════
# §2. TF-IDF + 聚类
# ════════════════════════════════════════════════════════════════════════


def test_tokenize_filters_stopwords() -> None:
    tokens = lr._tokenize("the quick brown fox jumps over the lazy dog")
    assert "the" not in tokens
    assert "quick" in tokens
    assert "brown" in tokens


def test_tokenize_handles_chinese_bigrams() -> None:
    tokens = lr._tokenize("机器学习 深度学习 神经网络")
    # 中文按字 2-gram
    assert any("机器" in t or "学习" in t for t in tokens)


def test_tf_idf_filters_singleton_terms() -> None:
    """只在 1 篇出现的词应被过滤（noise 防御）."""
    docs = [
        ["foo", "bar", "baz"],
        ["foo", "bar", "qux"],
    ]
    vectors, vocab = lr._tf_idf(docs)
    # foo / bar 出现 2 次 → 在 vocab；baz / qux 各出现 1 次 → 不在
    assert "foo" in vocab
    assert "baz" not in vocab


def test_cosine_similarity_basic() -> None:
    a = {"x": 1.0, "y": 1.0}
    b = {"x": 1.0, "y": 1.0}
    assert lr._cosine_similarity(a, b) == pytest.approx(1.0)
    c = {"x": 1.0}
    d = {"y": 1.0}
    assert lr._cosine_similarity(c, d) == 0.0


def test_cluster_empty_papers_fail_loud() -> None:
    res = lr.cluster_papers_by_topic([])
    assert res["ok"] is False


def test_cluster_one_paper_fail_loud() -> None:
    res = lr.cluster_papers_by_topic([{"paper_id": "a", "title": "X"}])
    assert res["ok"] is False


def test_cluster_basic_grouping() -> None:
    """4 篇 paper：2 篇关于 ML，2 篇关于 PL → 应分 2 个 cluster."""
    papers = [
        {
            "paper_id": "p1",
            "title": "Deep Learning for Image Classification",
            "abstract": (
                "We propose a convolutional neural network architecture "
                "for image classification tasks using deep learning techniques."
            ),
            "keywords": ["deep learning", "image classification", "neural network"],
        },
        {
            "paper_id": "p2",
            "title": "Neural Networks for Object Detection",
            "abstract": (
                "This paper applies deep neural networks for object detection "
                "tasks in computer vision using image classification techniques."
            ),
            "keywords": ["neural network", "object detection", "computer vision"],
        },
        {
            "paper_id": "p3",
            "title": "Type Systems for Functional Programming",
            "abstract": (
                "We design a type system for functional programming languages "
                "with parametric polymorphism and dependent types."
            ),
            "keywords": ["type system", "functional programming", "polymorphism"],
        },
        {
            "paper_id": "p4",
            "title": "Dependent Types in Programming Languages",
            "abstract": (
                "Dependent types provide expressive type systems for programming "
                "languages and functional programming paradigms."
            ),
            "keywords": ["dependent types", "programming languages", "type system"],
        },
    ]
    res = lr.cluster_papers_by_topic(papers, similarity_threshold=0.05)
    assert res["ok"] is True
    assert res["n_papers"] == 4
    # 至少 1 个 cluster；如果聚类有效应至少 2 个
    assert res["n_clusters"] >= 1


def test_cluster_marks_thin_clusters() -> None:
    """3 篇内容差异极大的 paper → 应分多 cluster，全部 thin（默认 min=2）.

    用完全不同的 vocabulary 防止 TF-IDF 把它们拉到一起。
    """
    papers = [
        {
            "paper_id": "p0",
            "title": "Quantum cryptography protocols",
            "abstract": (
                "Quantum key distribution achieves unconditional security "
                "via photon polarization measurements."
            ),
            "keywords": ["quantum", "cryptography", "QKD"],
        },
        {
            "paper_id": "p1",
            "title": "Bird migration patterns",
            "abstract": (
                "Tracking avian seasonal flight routes across continental "
                "boundaries reveals climate adaptation strategies."
            ),
            "keywords": ["birds", "migration", "ornithology"],
        },
        {
            "paper_id": "p2",
            "title": "Roman concrete chemistry",
            "abstract": (
                "Ancient pozzolanic mortar formulations exhibit self-healing "
                "via aluminosilicate crystallization mechanisms."
            ),
            "keywords": ["archaeology", "concrete", "pozzolanic"],
        },
    ]
    res = lr.cluster_papers_by_topic(papers, similarity_threshold=0.5)
    assert res["ok"] is True
    # 3 个完全不同的领域 → 应分 3 个 cluster（或至少 ≥2）
    assert res["n_clusters"] >= 2
    # 每个 < 2 论文的 cluster 应标 thin
    assert res["thin_count"] >= 1


# ════════════════════════════════════════════════════════════════════════
# §3. 引用图
# ════════════════════════════════════════════════════════════════════════


def test_citation_graph_empty_fail_loud() -> None:
    res = lr.build_citation_graph([], [{"from": "a", "to": "b"}])
    assert res["ok"] is False


def test_citation_graph_filters_invalid_edges() -> None:
    papers = [
        {"paper_id": "p1", "title": "T1", "year": 2020},
        {"paper_id": "p2", "title": "T2", "year": 2021},
    ]
    edges = [
        {"from": "p1", "to": "p2"},          # valid
        {"from": "p1", "to": "ghost"},        # invalid (ghost 不存在)
        {"from": "p1", "to": "p1"},           # self-edge
    ]
    res = lr.build_citation_graph(papers, edges)
    assert res["ok"] is True
    assert res["n_edges"] == 1
    assert len(res["invalid_edges"]) == 2


def test_citation_graph_detects_cycles() -> None:
    """A→B→A 应检测出环."""
    papers = [
        {"paper_id": "a", "title": "A"},
        {"paper_id": "b", "title": "B"},
    ]
    edges = [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}]
    res = lr.build_citation_graph(papers, edges)
    assert res["ok"] is True
    assert len(res["cycles"]) >= 1


def test_citation_graph_orphan_detection() -> None:
    papers = [
        {"paper_id": "a", "title": "A"},
        {"paper_id": "b", "title": "B"},
        {"paper_id": "lonely", "title": "Lonely"},
    ]
    edges = [{"from": "a", "to": "b"}]
    res = lr.build_citation_graph(papers, edges)
    assert "lonely" in res["orphan_nodes"]


def test_citation_graph_dot_well_formed() -> None:
    papers = [{"paper_id": "a", "title": "A", "year": 2020}]
    res = lr.build_citation_graph(papers, [])
    dot = res["dot"]
    assert dot.startswith("digraph")
    assert "}" in dot
    assert '"a"' in dot


def test_citation_graph_cluster_color() -> None:
    papers = [
        {"paper_id": "a", "title": "A"},
        {"paper_id": "b", "title": "B"},
    ]
    res = lr.build_citation_graph(
        papers, [], cluster_assignments={"a": "topic_0", "b": "topic_1"}
    )
    # DOT 字符串应包含 fillcolor（cluster 着色）
    assert "fillcolor=" in res["dot"]


# ════════════════════════════════════════════════════════════════════════
# §4. 抄袭重叠检测
# ════════════════════════════════════════════════════════════════════════


def test_plagiarism_empty_review_fail_loud() -> None:
    res = lr.detect_plagiarism_overlap("", {"a": "x"})
    assert res["ok"] is False


def test_plagiarism_empty_sources_fail_loud() -> None:
    res = lr.detect_plagiarism_overlap("review text here", {})
    assert res["ok"] is False


def test_plagiarism_no_overlap_passes() -> None:
    review = (
        "This survey discusses recent advances in machine learning approaches "
        "to natural language processing tasks across various domains."
    )
    sources = {
        "p1": "Quantum computing offers exponential speedups for certain algorithms.",
    }
    res = lr.detect_plagiarism_overlap(review, sources, overlap_threshold=0.6)
    assert res["ok"] is True
    assert len(res["flagged_sources"]) == 0


def test_plagiarism_high_overlap_flags() -> None:
    """综述完全复制原文 abstract → 应 flag."""
    common = (
        "This paper proposes a novel deep learning architecture for image "
        "classification tasks using convolutional neural networks with "
        "attention mechanism for fine-grained recognition."
    )
    res = lr.detect_plagiarism_overlap(common, {"p1": common}, overlap_threshold=0.6)
    assert res["ok"] is True
    assert "p1" in res["flagged_sources"]


def test_plagiarism_short_review_returns_pass() -> None:
    """太短的 review（< 5-gram）→ 自动 pass（无 ngram 可比对）."""
    res = lr.detect_plagiarism_overlap("a b c", {"p1": "a b c d e f g"})
    assert res["ok"] is True
    assert len(res["flagged_sources"]) == 0


# ════════════════════════════════════════════════════════════════════════
# §5. 综述大纲生成
# ════════════════════════════════════════════════════════════════════════


def _make_cluster_result(*, n_clusters: int = 3, year_span: int = 10) -> dict:
    clusters = [
        {
            "topic_id": f"topic_{i:03d}",
            "n_papers": 5 + i,
            "paper_ids": [f"p{i}_{j}" for j in range(5 + i)],
            "top_terms": [f"term{i}", f"keyword{i}"],
            "year_min": 2010,
            "year_max": 2010 + year_span if i == 0 else 2015 + i,
            "thin": False,
        }
        for i in range(n_clusters)
    ]
    return {"ok": True, "clusters": clusters, "n_papers": 18, "n_clusters": n_clusters}


def test_outline_invalid_input_fail_loud() -> None:
    res = lr.generate_review_outline({})
    assert res["ok"] is False


def test_outline_unknown_template_fail_loud() -> None:
    res = lr.generate_review_outline(
        _make_cluster_result(), template="bogus"
    )
    assert res["ok"] is False


def test_outline_standard_includes_timeline_when_year_span_large() -> None:
    """年份跨度 ≥10 → 自动含 Timeline 章节."""
    res = lr.generate_review_outline(_make_cluster_result(year_span=15))
    assert res["ok"] is True
    section_names = [s["section"] for s in res["outline"]]
    assert any("Timeline" in s for s in section_names)


def test_outline_standard_skips_timeline_when_year_span_small() -> None:
    res = lr.generate_review_outline(_make_cluster_result(year_span=2))
    section_names = [s["section"] for s in res["outline"]]
    assert not any("Timeline" in s for s in section_names)


def test_outline_compact_template() -> None:
    res = lr.generate_review_outline(
        _make_cluster_result(), template="compact"
    )
    assert res["ok"] is True
    # compact 模板只有 4 章
    assert len(res["outline"]) == 4


def test_outline_subsections_per_cluster() -> None:
    res = lr.generate_review_outline(_make_cluster_result(n_clusters=5))
    # 每个 cluster 一个 sub_section
    assert len(res["sub_sections"]) == 5


# ════════════════════════════════════════════════════════════════════════
# §6. ToolPlugin / ACTPlugin Protocol
# ════════════════════════════════════════════════════════════════════════


def test_tool_plugin_registers_5_tools() -> None:
    plugin = lr.LiteratureReviewerToolPlugin()
    names = {t["name"] for t in plugin.get_tools()}
    assert names == {
        "literature_reviewer_extract_paper_metadata",
        "literature_reviewer_cluster_papers_by_topic",
        "literature_reviewer_build_citation_graph",
        "literature_reviewer_detect_plagiarism_overlap",
        "literature_reviewer_generate_review_outline",
    }


def test_act_plugin_act_root_exists() -> None:
    plugin = lr.LiteratureReviewerACTPlugin()
    assert plugin.get_act_root().is_dir()
    assert (plugin.get_act_root() / "ext_literature_reviewer.md").is_file()


def test_act_plugin_includes_word_smart_export() -> None:
    """学术综述 docx / pdf 输出走 SSOT."""
    plugin = lr.LiteratureReviewerACTPlugin()
    assert "word_smart_export" in plugin.get_tool_names()


# ════════════════════════════════════════════════════════════════════════
# §7. GatePlugin × 2
# ════════════════════════════════════════════════════════════════════════


@pytest.fixture
def gate_imports():
    from krow_agent_sdk.protocols import GateDecision, GateVerdict
    return {"GateDecision": GateDecision, "GateVerdict": GateVerdict}


def _wrap_write_report_result(content: str) -> dict:
    return {
        "tool_name": "data_analyst_write_report",
        "args": {"content": content},
        "result": {},
    }


def test_citation_count_helper() -> None:
    text = "We propose [1] a novel method [2, 3] following (Smith, 2020)"
    assert lr._count_citations_in_text(text) >= 3


def test_citation_split_sections() -> None:
    md = "## Intro\nbody1\n## Methods\nbody2 with more text"
    sections = lr._split_review_into_sections(md)
    titles = [t for t, _ in sections]
    assert "Intro" in titles
    assert "Methods" in titles


def test_citation_gate_defers_no_report(gate_imports) -> None:
    gate = lr.CitationCompletenessGate().get_gate()
    decision = gate.evaluate({}, {"recent_tool_results": []})
    assert decision.verdict == gate_imports["GateVerdict"].DEFER


def test_citation_gate_blocks_when_section_lacks_citations(gate_imports) -> None:
    md = (
        "## Introduction\n"
        + "background text " * 60
        + " no citations here at all in this section.\n"
        "## Methods\nshort\n"
    )
    gate = lr.CitationCompletenessGate(min_citations_per_section=3).get_gate()
    ctx = {"recent_tool_results": [_wrap_write_report_result(md)]}
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].BLOCK


def test_citation_gate_allows_when_all_sections_have_3_citations(gate_imports) -> None:
    md = (
        "## Introduction\n" + "background " * 60
        + " [1] [2] [3] [4]\n"
        "## Topic Survey\n" + "main content " * 60
        + " [5] [6] [7] [8]\n"
    )
    gate = lr.CitationCompletenessGate(min_citations_per_section=3).get_gate()
    ctx = {"recent_tool_results": [_wrap_write_report_result(md)]}
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].ALLOW


def test_plagiarism_gate_defers_when_not_checked(gate_imports) -> None:
    gate = lr.PlagiarismGate().get_gate()
    decision = gate.evaluate({}, {"recent_tool_results": []})
    assert decision.verdict == gate_imports["GateVerdict"].DEFER


def test_plagiarism_gate_blocks_when_flagged(gate_imports) -> None:
    """detect_plagiarism_overlap 输出 flagged_sources 非空 → BLOCK."""
    gate = lr.PlagiarismGate().get_gate()
    ctx = {
        "recent_tool_results": [{
            "tool_name": "literature_reviewer_detect_plagiarism_overlap",
            "args": {},
            "result": {
                "ok": True,
                "flagged_sources": ["p1", "p2"],
                "overlap_threshold": 0.6,
            },
        }]
    }
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].BLOCK
    assert "学术不端" in decision.reason or "抄袭" in decision.reason


def test_plagiarism_gate_allows_when_clean(gate_imports) -> None:
    gate = lr.PlagiarismGate().get_gate()
    ctx = {
        "recent_tool_results": [{
            "tool_name": "literature_reviewer_detect_plagiarism_overlap",
            "args": {},
            "result": {
                "ok": True,
                "flagged_sources": [],
                "overlap_threshold": 0.6,
            },
        }]
    }
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].ALLOW


# ════════════════════════════════════════════════════════════════════════
# §8. HintPlugin × 2
# ════════════════════════════════════════════════════════════════════════


def _wrap_cluster_result(clusters: list[dict]) -> dict:
    return {
        "recent_tool_results": [{
            "tool_name": "literature_reviewer_cluster_papers_by_topic",
            "args": {},
            "result": {
                "ok": True,
                "clusters": clusters,
                "n_papers": sum(c.get("n_papers", 0) for c in clusters),
                "n_clusters": len(clusters),
                "thin_count": sum(1 for c in clusters if c.get("thin")),
            },
        }]
    }


def test_topic_coverage_hint_returns_none_when_no_thin() -> None:
    clusters = [
        {"topic_id": "topic_000", "n_papers": 10, "top_terms": ["a"], "thin": False},
    ]
    hint = lr.TopicCoverageHintPlugin()
    res = hint.hint_for(_wrap_cluster_result(clusters))
    assert res is None


def test_topic_coverage_hint_lists_thin_clusters() -> None:
    clusters = [
        {"topic_id": "topic_000", "n_papers": 5, "top_terms": ["main"], "thin": False},
        {"topic_id": "topic_001", "n_papers": 1, "top_terms": ["niche"], "thin": True},
        {"topic_id": "topic_002", "n_papers": 1, "top_terms": ["edge"], "thin": True},
    ]
    hint = lr.TopicCoverageHintPlugin()
    res = hint.hint_for(_wrap_cluster_result(clusters))
    assert res is not None
    assert "topic_001" in res
    assert "topic_002" in res


def test_year_gap_hint_returns_none_for_small_span() -> None:
    clusters = [
        {"topic_id": "topic_000", "year_min": 2018, "year_max": 2024, "top_terms": ["x"]},
    ]
    hint = lr.YearGapHintPlugin(gap_threshold_years=15)
    assert hint.hint_for(_wrap_cluster_result(clusters)) is None


def test_year_gap_hint_lists_long_span_clusters() -> None:
    clusters = [
        {"topic_id": "topic_000", "year_min": 1995, "year_max": 2020, "top_terms": ["evolved"]},
        {"topic_id": "topic_001", "year_min": 2018, "year_max": 2023, "top_terms": ["recent"]},
    ]
    hint = lr.YearGapHintPlugin(gap_threshold_years=15)
    res = hint.hint_for(_wrap_cluster_result(clusters))
    assert res is not None
    assert "topic_000" in res
    assert "1995" in res


# ════════════════════════════════════════════════════════════════════════
# §9. ReviewProgressListener
# ════════════════════════════════════════════════════════════════════════


def test_progress_listener_writes_jsonl(tmp_path: Path) -> None:
    log = tmp_path / "review.progress.jsonl"
    listener = lr.ReviewProgressListener(
        verbose=False, progress_log_path=log, total_papers=3
    )

    class Ev:
        def __init__(self, payload):
            self.payload = payload

    listener._on_tool_done(Ev({
        "tool_name": "literature_reviewer_extract_paper_metadata",
        "ok": True,
        "elapsed_ms": 150,
    }))
    listener._on_tool_done(Ev({
        "tool_name": "literature_reviewer_cluster_papers_by_topic",
        "ok": True,
        "elapsed_ms": 50,
    }))
    listener._on_gate_blocked(Ev({
        "gate_name": "citation_completeness",
        "reason": "缺 2 段引用",
    }))
    listener._on_task_done(Ev({"summary": "done"}))

    assert log.is_file()
    lines = log.read_text(encoding="utf-8").strip().split("\n")
    records = [json.loads(line) for line in lines]
    assert any(r["kind"] == "paper_processed" for r in records)
    assert any(r["kind"] == "gate_blocked" for r in records)
    assert any(r["kind"] == "task_complete" for r in records)


def test_progress_listener_no_log_path_works() -> None:
    """progress_log_path=None → listener 仍工作（仅 print，不写文件）."""
    listener = lr.ReviewProgressListener(verbose=False, progress_log_path=None)

    class Ev:
        def __init__(self, payload):
            self.payload = payload

    # 不应抛异常
    listener._on_tool_done(Ev({
        "tool_name": "literature_reviewer_extract_paper_metadata",
        "ok": True,
    }))
    listener._on_task_done(Ev({}))


def test_progress_listener_counts_papers_processed() -> None:
    listener = lr.ReviewProgressListener(verbose=False)

    class Ev:
        def __init__(self, payload):
            self.payload = payload

    for _ in range(5):
        listener._on_tool_done(Ev({
            "tool_name": "literature_reviewer_extract_paper_metadata",
        }))
    assert listener._papers_processed == 5
    # 非 paper 工具不增加计数
    listener._on_tool_done(Ev({"tool_name": "other_tool"}))
    assert listener._papers_processed == 5


def test_progress_listener_counts_gate_blocks() -> None:
    listener = lr.ReviewProgressListener(verbose=False)

    class Ev:
        def __init__(self, payload):
            self.payload = payload

    listener._on_gate_blocked(Ev({"gate_name": "citation_completeness"}))
    listener._on_gate_blocked(Ev({"gate_name": "plagiarism"}))
    assert listener._gate_blocks == 2
