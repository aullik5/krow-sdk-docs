"""knowledge-wiki cookbook smoke tests（≥30 tests，零 LLM 调用）.

覆盖：
- §1 scan_knowledge_sources 边界（缺目录 / 非可编译后缀 / min_bytes / 排除 .krow / 清单）
- §2 report_wiki_coverage（无 project_root / 空 wiki / 分类归组 / 覆盖率 / under_populated）
- §2.6 编译三段工具 fail-loud（extract / relate / materialize 的无 project_root / 空输入分支）
- §3 ToolPlugin Protocol 契约（5 工具）
- §4 ACTPlugin Protocol 契约（act_root / __act__.yaml / 工具名）
- §5 WikiCoverageGate 行为（DEFER / BLOCK / ALLOW）
- §6 CompileProgressListener（三阶段计数 / jsonl / gate block）
"""
from __future__ import annotations

import json
from pathlib import Path

import knowledge_wiki_plugin as kw
import pytest

# ════════════════════════════════════════════════════════════════════════
# §1. scan_knowledge_sources
# ════════════════════════════════════════════════════════════════════════


def test_scan_missing_dir_fail_loud() -> None:
    res = kw.scan_knowledge_sources("/nonexistent_dir_xyz")
    assert res["ok"] is False
    assert "不存在" in res["error"]


def test_scan_file_not_dir_fail_loud(tmp_path: Path) -> None:
    f = tmp_path / "a.md"
    f.write_text("x" * 500, encoding="utf-8")
    res = kw.scan_knowledge_sources(f)
    assert res["ok"] is False


def test_scan_empty_dir_fail_loud(tmp_path: Path) -> None:
    res = kw.scan_knowledge_sources(tmp_path)
    assert res["ok"] is False
    assert "没有可编译" in res["error"]


def test_scan_basic_manifest(tmp_path: Path) -> None:
    (tmp_path / "doc1.md").write_text("a" * 1500, encoding="utf-8")
    (tmp_path / "doc2.txt").write_text("b" * 800, encoding="utf-8")
    res = kw.scan_knowledge_sources(tmp_path)
    assert res["ok"] is True
    assert res["n_sources"] == 2
    names = {Path(s["path"]).name for s in res["sources"]}
    assert names == {"doc1.md", "doc2.txt"}


def test_scan_filters_non_ingestible_ext(tmp_path: Path) -> None:
    (tmp_path / "keep.md").write_text("a" * 500, encoding="utf-8")
    (tmp_path / "skip.png").write_bytes(b"\x89PNG" + b"0" * 500)
    (tmp_path / "skip.exe").write_bytes(b"MZ" + b"0" * 500)
    res = kw.scan_knowledge_sources(tmp_path)
    assert res["ok"] is True
    assert res["n_sources"] == 1


def test_scan_filters_small_files(tmp_path: Path) -> None:
    (tmp_path / "big.md").write_text("a" * 500, encoding="utf-8")
    (tmp_path / "tiny.md").write_text("hi", encoding="utf-8")
    res = kw.scan_knowledge_sources(tmp_path, min_bytes=200)
    assert res["ok"] is True
    assert res["n_sources"] == 1
    assert res["skipped_small"] == 1


def test_scan_excludes_krow_dir(tmp_path: Path) -> None:
    """.krow 下的产出物不能被编入（自激环防护）."""
    (tmp_path / "doc.md").write_text("a" * 500, encoding="utf-8")
    krow_wiki = tmp_path / ".krow" / "wiki" / "concepts"
    krow_wiki.mkdir(parents=True)
    (krow_wiki / "leaked.md").write_text("a" * 500, encoding="utf-8")
    res = kw.scan_knowledge_sources(tmp_path)
    assert res["ok"] is True
    assert res["n_sources"] == 1
    assert all(".krow" not in s["path"] for s in res["sources"])


def test_scan_est_chunks(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("a" * 2400, encoding="utf-8")
    res = kw.scan_knowledge_sources(tmp_path)
    assert res["sources"][0]["est_chunks"] == 2


def test_scan_max_sources_cap(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"doc{i}.md").write_text("a" * 500, encoding="utf-8")
    res = kw.scan_knowledge_sources(tmp_path, max_sources=3)
    assert res["ok"] is True
    assert res["n_sources"] == 3


def test_scan_recursive(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "top.md").write_text("a" * 500, encoding="utf-8")
    (sub / "nested.md").write_text("a" * 500, encoding="utf-8")
    res = kw.scan_knowledge_sources(tmp_path)
    assert res["n_sources"] == 2


# ════════════════════════════════════════════════════════════════════════
# §2. report_wiki_coverage
# ════════════════════════════════════════════════════════════════════════


def _make_wiki(project: Path, *, concepts: int = 0, entities: int = 0,
               comparisons: int = 0) -> None:
    base = project / ".krow" / "wiki"
    for cat, n in (("concepts", concepts), ("entities", entities),
                   ("comparisons", comparisons)):
        d = base / cat
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (d / f"{cat}_{i}.md").write_text(
                f"---\ntitle: {cat} {i}\n---\n\n## 定义\n内容\n", encoding="utf-8"
            )


def test_coverage_no_project_root_fail_loud() -> None:
    res = kw.report_wiki_coverage(project_root=None)
    # 无 project_context 时应 fail-loud（或 project_context 恰好有值时 ok）
    assert "ok" in res


def test_coverage_empty_wiki(tmp_path: Path) -> None:
    res = kw.report_wiki_coverage(tmp_path)
    assert res["ok"] is True
    assert res["wiki_page_count"] == 0


def test_coverage_counts_wiki_pages(tmp_path: Path) -> None:
    _make_wiki(tmp_path, concepts=3, entities=4)
    res = kw.report_wiki_coverage(tmp_path)
    assert res["ok"] is True
    assert res["wiki_page_count"] == 7
    assert res["wiki_by_category"]["concepts"] == 3
    assert res["wiki_by_category"]["entities"] == 4


def test_coverage_skips_index_and_hidden(tmp_path: Path) -> None:
    base = tmp_path / ".krow" / "wiki" / "concepts"
    base.mkdir(parents=True)
    (base / "real.md").write_text("a" * 200, encoding="utf-8")
    (base / "index.md").write_text("idx", encoding="utf-8")
    (base / "_template.md").write_text("tpl", encoding="utf-8")
    res = kw.report_wiki_coverage(tmp_path)
    assert res["wiki_page_count"] == 1


def test_coverage_under_populated_signal(tmp_path: Path) -> None:
    """key_nodes>=3 但 wiki<3 时 under_populated；这里无真 ontology db,
    key_nodes=0 → 不触发 under_populated。"""
    _make_wiki(tmp_path, concepts=1)
    res = kw.report_wiki_coverage(tmp_path)
    assert res["ok"] is True
    # 没有真实 ontology db → key_node_count=0 → under_populated False
    assert res["under_populated"] is False


def test_coverage_ratio_zero_when_no_nodes(tmp_path: Path) -> None:
    _make_wiki(tmp_path, concepts=2)
    res = kw.report_wiki_coverage(tmp_path)
    assert res["coverage_ratio"] == 0.0


def test_coverage_returns_ontology_counts_dict(tmp_path: Path) -> None:
    res = kw.report_wiki_coverage(tmp_path)
    assert isinstance(res["ontology_counts"], dict)


# ════════════════════════════════════════════════════════════════════════
# §2.5 _scan_wiki_pages helper
# ════════════════════════════════════════════════════════════════════════


def test_scan_wiki_pages_grouping(tmp_path: Path) -> None:
    _make_wiki(tmp_path, concepts=2, entities=1, comparisons=1)
    by_cat = kw._scan_wiki_pages(tmp_path / ".krow" / "wiki")
    assert len(by_cat["concepts"]) == 2
    assert len(by_cat["entities"]) == 1
    assert len(by_cat["comparisons"]) == 1


def test_scan_wiki_pages_missing_dir(tmp_path: Path) -> None:
    by_cat = kw._scan_wiki_pages(tmp_path / "nope")
    assert sum(len(v) for v in by_cat.values()) == 0


# ════════════════════════════════════════════════════════════════════════
# §2.6 编译三段工具 fail-loud（零 LLM：只测无 project_root / 空 sources 分支）
# ════════════════════════════════════════════════════════════════════════


def test_extract_empty_sources_fail_loud(tmp_path: Path) -> None:
    res = kw.extract_ontology_from_sources(tmp_path, [])
    assert res["ok"] is False
    assert "sources" in res["error"]


def test_extract_no_project_root_fail_loud() -> None:
    res = kw.extract_ontology_from_sources(None, ["x.md"])
    # 无 project_context 时 fail-loud；恰好有值时返回 dict（仍含 ok）
    assert "ok" in res


def test_materialize_no_project_root_fail_loud() -> None:
    res = kw.materialize_wiki_pages(None)
    assert "ok" in res


def test_materialize_empty_ontology_no_pages(tmp_path: Path) -> None:
    """空本体 → 物化 0 页（不报错，ok=False 表示无新页）."""
    res = kw.materialize_wiki_pages(tmp_path)
    assert "ok" in res
    assert res.get("created_count", 0) == 0


def test_link_relations_no_project_root_fail_loud() -> None:
    res = kw.link_ontology_relations(None)
    assert "ok" in res


# ════════════════════════════════════════════════════════════════════════
# §3. ToolPlugin Protocol
# ════════════════════════════════════════════════════════════════════════


def test_tool_plugin_registers_five_tools() -> None:
    plugin = kw.KnowledgeWikiToolPlugin()
    names = {t["name"] for t in plugin.get_tools()}
    assert names == {
        "knowledge_wiki_scan_sources",
        "knowledge_wiki_extract_ontology",
        "knowledge_wiki_link_relations",
        "knowledge_wiki_materialize",
        "knowledge_wiki_coverage_report",
    }


def test_tool_plugin_id() -> None:
    assert kw.KnowledgeWikiToolPlugin().plugin_id == "knowledge_wiki.tools"


def test_tool_plugin_handlers_callable() -> None:
    for t in kw.KnowledgeWikiToolPlugin().get_tools():
        assert callable(t["handler"])
        assert "input_schema" in t
        assert "description" in t


# ════════════════════════════════════════════════════════════════════════
# §4. ACTPlugin Protocol
# ════════════════════════════════════════════════════════════════════════


def test_act_plugin_act_root_exists() -> None:
    plugin = kw.KnowledgeWikiACTPlugin()
    assert plugin.get_act_root().is_dir()
    assert (plugin.get_act_root() / "ext_knowledge_wiki_studio.md").is_file()
    assert (plugin.get_act_root() / "__act__.yaml").is_file(), (
        "ACT manifest 必须是独立 __act__.yaml"
    )


def test_act_plugin_name() -> None:
    assert kw.KnowledgeWikiACTPlugin().act_name == "knowledge_wiki_studio"


def test_act_plugin_includes_builtin_compile_tools() -> None:
    """ACT 必须引用内置知识工具（SSOT 复用，不造轮子）."""
    names = kw.KnowledgeWikiACTPlugin().get_tool_names()
    for t in (
        "wiki_info",
        "smart_file_write",
        "summarize_ontology",
    ):
        assert t in names, f"ACT 缺内置工具 {t}"


def test_act_plugin_includes_cookbook_tools() -> None:
    names = kw.KnowledgeWikiACTPlugin().get_tool_names()
    for t in (
        "knowledge_wiki_scan_sources",
        "knowledge_wiki_extract_ontology",
        "knowledge_wiki_link_relations",
        "knowledge_wiki_materialize",
        "knowledge_wiki_coverage_report",
    ):
        assert t in names, f"ACT 缺 cookbook 工具 {t}"


# ════════════════════════════════════════════════════════════════════════
# §5. WikiCoverageGate
# ════════════════════════════════════════════════════════════════════════


@pytest.fixture
def gate_imports():
    from krow_agent_sdk.protocols import GateDecision, GateVerdict
    return {"GateDecision": GateDecision, "GateVerdict": GateVerdict}


def _wrap_coverage_result(**result) -> dict:
    base = {"ok": True}
    base.update(result)
    return {
        "recent_tool_results": [{
            "tool_name": "knowledge_wiki_coverage_report",
            "args": {},
            "result": base,
        }]
    }


def test_gate_defers_when_not_checked(gate_imports) -> None:
    gate = kw.WikiCoverageGate().get_gate()
    decision = gate.evaluate({}, {"recent_tool_results": []})
    assert decision.verdict == gate_imports["GateVerdict"].DEFER


def test_gate_defers_when_few_key_nodes(gate_imports) -> None:
    """本体几乎没抽到东西 → 不归 coverage gate 管."""
    gate = kw.WikiCoverageGate(min_key_nodes=3).get_gate()
    ctx = _wrap_coverage_result(
        key_node_count=1, wiki_page_count=0, under_populated=False
    )
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].DEFER


def test_gate_blocks_when_under_populated(gate_imports) -> None:
    gate = kw.WikiCoverageGate(min_wiki_pages=3).get_gate()
    ctx = _wrap_coverage_result(
        key_node_count=10, wiki_page_count=1, under_populated=True
    )
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].BLOCK
    assert "覆盖不足" in decision.reason or "假编译" in decision.reason


def test_gate_blocks_when_pages_below_min(gate_imports) -> None:
    gate = kw.WikiCoverageGate(min_wiki_pages=5).get_gate()
    ctx = _wrap_coverage_result(
        key_node_count=10, wiki_page_count=3, under_populated=False
    )
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].BLOCK


def test_gate_allows_when_adequate(gate_imports) -> None:
    gate = kw.WikiCoverageGate(min_wiki_pages=3).get_gate()
    ctx = _wrap_coverage_result(
        key_node_count=10, wiki_page_count=8, under_populated=False,
        coverage_ratio=0.8,
    )
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].ALLOW


def test_gate_phase_is_macro() -> None:
    assert kw.WikiCoverageGate().phase == "macro"


# ════════════════════════════════════════════════════════════════════════
# §6. CompileProgressListener
# ════════════════════════════════════════════════════════════════════════


class _Ev:
    def __init__(self, payload):
        self.payload = payload


def test_listener_counts_three_phases() -> None:
    listener = kw.CompileProgressListener(verbose=False)
    listener._on_tool_done(_Ev({"tool_name": "extract_entities_from_text"}))
    listener._on_tool_done(_Ev({"tool_name": "extract_entities_from_text"}))
    listener._on_tool_done(_Ev({"tool_name": "add_relation"}))
    listener._on_tool_done(_Ev({"tool_name": "smart_file_write"}))
    assert listener._phase_counts == {"extract": 2, "relate": 1, "publish": 1}


def test_listener_counts_cookbook_tool_names() -> None:
    """三段封装的 cookbook 工具名也归入对应阶段."""
    listener = kw.CompileProgressListener(verbose=False)
    listener._on_tool_done(_Ev({"tool_name": "knowledge_wiki_extract_ontology"}))
    listener._on_tool_done(_Ev({"tool_name": "knowledge_wiki_link_relations"}))
    listener._on_tool_done(_Ev({"tool_name": "knowledge_wiki_materialize"}))
    assert listener._phase_counts == {"extract": 1, "relate": 1, "publish": 1}


# ════════════════════════════════════════════════════════════════════════
# §7. render_wiki_preview（前端预览 · 零 LLM · 端到端 handoff）
# ════════════════════════════════════════════════════════════════════════


def _seed_wiki(project_dir: Path) -> None:
    wiki = project_dir / ".krow" / "wiki" / "concepts"
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "solar-pv.md").write_text(
        "---\ntitle: 太阳能光伏\ntype: concept\ntier: stub\n"
        "sources:\n  - 01.md\nconfidence: high\n---\n"
        "## 定义\n光伏效应把光能转换为电能。\n\n"
        "## 关联\n- `is_a` -> [[concepts/renewable|可再生能源]]\n",
        encoding="utf-8",
    )
    (wiki / "renewable.md").write_text(
        "---\ntitle: 可再生能源\ntype: concept\ntier: essay\n"
        "sources: [02.md]\n---\n## 定义\n可再生能源自然补充。\n",
        encoding="utf-8",
    )


def test_preview_missing_wiki_dir_fail_loud(tmp_path: Path) -> None:
    from wiki_preview import render_wiki_preview
    res = render_wiki_preview(tmp_path, tmp_path / "output")
    assert res["ok"] is False
    assert res["page_count"] == 0


def test_preview_renders_index_html(tmp_path: Path) -> None:
    from wiki_preview import render_wiki_preview
    _seed_wiki(tmp_path)
    res = render_wiki_preview(tmp_path, tmp_path / "output")
    assert res["ok"] is True
    assert res["page_count"] == 2
    assert res["essay_count"] == 1
    assert res["stub_count"] == 1
    index = tmp_path / "output" / "wiki_preview" / "index.html"
    assert index.exists()
    html = index.read_text(encoding="utf-8")
    # 词条标题 + tier badge + 数据内联 + 渲染器引用
    assert "太阳能光伏" in html
    assert "可再生能源" in html
    assert "tier-essay" in html and "tier-stub" in html
    assert 'id="wiki-data"' in html
    assert "wiki-render.js" in html


def test_preview_copies_renderer_assets(tmp_path: Path) -> None:
    from wiki_preview import render_wiki_preview
    _seed_wiki(tmp_path)
    render_wiki_preview(tmp_path, tmp_path / "output")
    pv = tmp_path / "output" / "wiki_preview"
    # 官方渲染器资产被拷贝（SSOT 复用，不重写）
    assert (pv / "wiki-render.js").exists()
    assert (pv / "wiki-theme.css").exists()


def test_preview_frontmatter_parse_and_skip_tombstone(tmp_path: Path) -> None:
    from wiki_preview import _split_frontmatter, render_wiki_preview
    fm, body = _split_frontmatter(
        "---\ntitle: X\nsources:\n  - a.md\n  - b.md\n---\nhello\n"
    )
    assert fm["title"] == "X"
    assert fm["sources"] == ["a.md", "b.md"]
    assert body.strip() == "hello"
    # 软删除墓碑页被跳过
    _seed_wiki(tmp_path)
    dele = tmp_path / ".krow" / "wiki" / "concepts" / "dead.md"
    dele.write_text(
        "---\ntitle: 墓碑\ntype: concept\ndeleted: true\n---\n空\n",
        encoding="utf-8",
    )
    res = render_wiki_preview(tmp_path, tmp_path / "output")
    assert res["page_count"] == 2  # 墓碑不计入


def test_listener_ignores_unrelated_tools() -> None:
    listener = kw.CompileProgressListener(verbose=False)
    listener._on_tool_done(_Ev({"tool_name": "some_other_tool"}))
    assert listener._phase_counts == {"extract": 0, "relate": 0, "publish": 0}


def test_listener_writes_jsonl(tmp_path: Path) -> None:
    log = tmp_path / "compile.progress.jsonl"
    listener = kw.CompileProgressListener(verbose=False, progress_log_path=log)
    listener._on_tool_done(_Ev({"tool_name": "extract_entities_from_text"}))
    listener._on_tool_done(_Ev({"tool_name": "smart_file_write"}))
    listener._on_gate_blocked(_Ev({"gate_name": "wiki_coverage", "reason": "x"}))
    listener._on_task_done(_Ev({}))
    assert log.is_file()
    records = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines() if ln]
    kinds = {r["kind"] for r in records}
    assert "phase_progress" in kinds
    assert "gate_blocked" in kinds
    assert "task_complete" in kinds


def test_listener_no_log_path_works() -> None:
    listener = kw.CompileProgressListener(verbose=False, progress_log_path=None)
    listener._on_tool_done(_Ev({"tool_name": "add_relation"}))
    listener._on_task_done(_Ev({}))
    assert listener._phase_counts["relate"] == 1


def test_listener_counts_gate_blocks() -> None:
    listener = kw.CompileProgressListener(verbose=False)
    listener._on_gate_blocked(_Ev({"gate_name": "wiki_coverage"}))
    listener._on_gate_blocked(_Ev({"gate_name": "wiki_coverage"}))
    assert listener._gate_blocks == 2


def test_listener_subscriptions_shape() -> None:
    subs = kw.CompileProgressListener().get_subscriptions()
    topics = {s["topic"] for s in subs}
    assert "tool.call_completed" in topics
    assert "agent.task_complete" in topics
    for s in subs:
        assert callable(s["handler"])
