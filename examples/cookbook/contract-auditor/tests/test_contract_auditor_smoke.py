"""Smoke tests for contract-auditor cookbook (System 1 only, 0 LLM calls).

测试范围：
  §1. 通用 helpers（_normalize_path / _golden_error / _scan_text_from_path）
  §2. CLAUSE_TAXONOMY 完整性（15 类，必备 3 类，高风险 6 类）
  §3. split_clauses 切分边界
  §4. classify_clauses 标签准确性
  §5. score_clause_risk 风险分上下界 + 风险加权词
  §6. redline_diff（add/remove/keep）
  §7. index_terms（已定义 / 未定义 / 引号包裹但只用 1 次跳过）
  §8. ToolPlugin / ACTPlugin Protocol 契约
  §9. MandatoryClauseGate 行为（ALLOW / BLOCK / DEFER / strict mode）
  §10. HighRiskBlockingGate 行为（无 high-risk → ALLOW；有但无标记 → BLOCK；
       有且有标记 → ALLOW）
  §11. AmbiguousLanguageHintPlugin / MissingDefinitionHintPlugin 触发条件
  §12. LegalAuditTrailListener .audit.jsonl 输出 + sha256 文件指纹

要求：全部 < 1 秒跑完，0 LLM 调用，100% deterministic。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


from contract_auditor_plugin import (
    AMBIGUOUS_PHRASES,
    AmbiguousLanguageHintPlugin,
    CLAUSE_TAXONOMY,
    ContractAuditorACTPlugin,
    ContractAuditorToolPlugin,
    HIGH_RISK_CLAUSE_TYPES,
    HighRiskBlockingGate,
    LegalAuditTrailListener,
    MANDATORY_CLAUSE_TYPES,
    MandatoryClauseGate,
    MissingDefinitionHintPlugin,
    classify_clauses,
    index_terms,
    redline_diff,
    score_clause_risk,
    split_clauses,
)
from contract_auditor_plugin import _golden_error, _normalize_path


# ============================================================
# §1. 通用 helpers
# ============================================================
def test_normalize_path_handles_str_and_path(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi", encoding="utf-8")
    p1 = _normalize_path(str(f))
    p2 = _normalize_path(f)
    assert p1 == p2 == f.resolve()


def test_golden_error_format() -> None:
    err = _golden_error(
        error_msg="bad input",
        location="test_location",
        fixes=["check param", "use absolute path"],
        related="see AGENTS.md §五",
    )
    assert err.startswith("❌ bad input")
    assert "test_location" in err
    assert "1. check param" in err
    assert "2. use absolute path" in err
    assert "AGENTS.md" in err


# ============================================================
# §2. CLAUSE_TAXONOMY 完整性
# ============================================================
def test_taxonomy_has_15_categories() -> None:
    assert len(CLAUSE_TAXONOMY) == 15


def test_taxonomy_each_category_has_keywords_and_baseline() -> None:
    for label, spec in CLAUSE_TAXONOMY.items():
        assert "keywords_en" in spec, f"{label} 缺 keywords_en"
        assert "keywords_zh" in spec, f"{label} 缺 keywords_zh"
        assert "baseline_risk" in spec, f"{label} 缺 baseline_risk"
        assert 0.0 <= spec["baseline_risk"] <= 1.0
        assert spec["keywords_en"], f"{label} keywords_en 不能为空"
        assert spec["keywords_zh"], f"{label} keywords_zh 不能为空"


def test_mandatory_clause_types_subset_of_taxonomy() -> None:
    assert MANDATORY_CLAUSE_TYPES.issubset(set(CLAUSE_TAXONOMY.keys()))
    # 必备 3 类必须有：data_protection_gdpr / antitrust_competition / export_control
    assert {
        "data_protection_gdpr",
        "antitrust_competition",
        "export_control",
    } == MANDATORY_CLAUSE_TYPES


def test_high_risk_types_includes_mandatory_and_more() -> None:
    assert MANDATORY_CLAUSE_TYPES.issubset(HIGH_RISK_CLAUSE_TYPES)
    # 高风险至少 6 类
    assert len(HIGH_RISK_CLAUSE_TYPES) >= 6


def test_ambiguous_phrases_have_pattern_and_advice() -> None:
    assert len(AMBIGUOUS_PHRASES) >= 5
    for pat, label, advice in AMBIGUOUS_PHRASES:
        assert isinstance(pat, re.Pattern)
        assert isinstance(label, str) and label
        assert isinstance(advice, str) and advice


# ============================================================
# §3. split_clauses
# ============================================================
SAMPLE_CONTRACT = """
1. Term

This Agreement shall commence on the Effective Date and continue for 3 years.

2. Payment

Customer agrees to pay the fees within 30 days of invoice.

7. Limitation of Liability

Vendor's total liability shall not exceed the amount paid in the past 12 months.
This limitation shall apply notwithstanding any failure of essential purpose.

11. Data Protection (GDPR / PIPL)

Each party shall comply with applicable data protection laws including GDPR and PIPL.
Data subjects have the right to access their personal data.

12. Antitrust Compliance

Parties shall not engage in any anti-competitive conduct.
No exclusive arrangements that violate competition law.

13. Export Control

The Software is subject to U.S. export control laws including EAR.
No transfer to denied parties on OFAC sanctions list.
"""


def test_split_clauses_with_text_returns_clauses() -> None:
    res = split_clauses(contract_text=SAMPLE_CONTRACT)
    assert res["ok"] is True
    assert res["clause_count"] >= 4
    headings = [c["heading"] for c in res["clauses"]]
    assert any("Term" in h for h in headings)
    assert any("Liability" in h for h in headings)


def test_split_clauses_missing_input_errors() -> None:
    res = split_clauses()
    assert res["ok"] is False
    assert "contract_path" in res["error"]


def test_split_clauses_nonexistent_path_errors() -> None:
    res = split_clauses(contract_path="/nonexistent/contract.docx")
    assert res["ok"] is False
    assert "不存在" in res["error"]


def test_split_clauses_empty_text_errors() -> None:
    res = split_clauses(contract_text="   \n\n  ")
    assert res["ok"] is False
    assert "为空" in res["error"]


def test_split_clauses_no_headings_falls_back_to_single_clause() -> None:
    """无 heading 的纯文本应该当成 1 个 clause."""
    res = split_clauses(contract_text="Just plain text without any heading.")
    assert res["ok"] is True
    assert res["clause_count"] == 1
    assert "未识别到分段标题" in res["clauses"][0]["heading"]


# ============================================================
# §4. classify_clauses
# ============================================================
def test_classify_clauses_detects_liability() -> None:
    clauses = [
        {
            "clause_id": "C-001",
            "heading": "7. Limitation of Liability",
            "text": "Vendor shall not be liable for indirect damages. Cap on damages is $1M.",
        }
    ]
    res = classify_clauses(clauses)
    assert res["ok"] is True
    top_labels = res["classifications"][0]["top_labels"]
    assert "liability_limitation" in top_labels


def test_classify_clauses_detects_data_protection() -> None:
    clauses = [
        {
            "clause_id": "C-002",
            "heading": "Data Protection",
            "text": "Each party shall comply with GDPR. Personal data must be encrypted.",
        }
    ]
    res = classify_clauses(clauses)
    assert "data_protection_gdpr" in res["classifications"][0]["top_labels"]


def test_classify_clauses_chinese_keywords() -> None:
    clauses = [
        {
            "clause_id": "C-003",
            "heading": "保密",
            "text": "本合同涉及商业秘密 / 保密信息 / 不得泄露给第三方",
        }
    ]
    res = classify_clauses(clauses)
    assert "confidentiality_nda" in res["classifications"][0]["top_labels"]


def test_classify_clauses_misc_other_for_unmatched() -> None:
    clauses = [{"clause_id": "C-X", "heading": "Misc", "text": "foo bar baz"}]
    res = classify_clauses(clauses)
    assert res["classifications"][0]["top_labels"] == ["misc_other"]


def test_classify_clauses_invalid_input_errors() -> None:
    res = classify_clauses("not a list")  # type: ignore[arg-type]
    assert res["ok"] is False


# ============================================================
# §5. score_clause_risk
# ============================================================
def test_score_clause_risk_high_for_liability_with_amplifiers() -> None:
    clauses = [{
        "clause_id": "C-001",
        "heading": "Limitation",
        "text": "Vendor's liability is unlimited and irrevocable. No cap on damages.",
    }]
    classifications = [{"clause_id": "C-001", "top_labels": ["liability_limitation"]}]
    res = score_clause_risk(clauses, classifications)
    assert res["ok"] is True
    risk = res["risks"][0]
    assert risk["level"] == "high"
    assert risk["risk_score"] >= 0.85
    assert any("unlimited" in d for d in risk["drivers"])


def test_score_clause_risk_low_for_force_majeure() -> None:
    clauses = [{
        "clause_id": "C-002",
        "heading": "Force Majeure",
        "text": "Neither party shall be liable for delay due to force majeure.",
    }]
    classifications = [{"clause_id": "C-002", "top_labels": ["force_majeure"]}]
    res = score_clause_risk(clauses, classifications)
    assert res["risks"][0]["level"] == "low"


def test_score_clause_risk_chinese_amplifier() -> None:
    clauses = [{
        "clause_id": "C-003",
        "heading": "责任",
        "text": "供方责任无上限。永久免除责任。",
    }]
    classifications = [{"clause_id": "C-003", "top_labels": ["liability_limitation"]}]
    res = score_clause_risk(clauses, classifications)
    drivers = res["risks"][0]["drivers"]
    assert any("无上限" in d for d in drivers)


def test_score_clause_risk_clipped_to_one() -> None:
    """加权词命中再多也不能 > 1.0."""
    big_text = (
        "unlimited no cap irrevocable perpetual exclusive sole discretion "
        "shall not be liable indemnify and hold harmless without limitation "
        + "无上限 不可撤销 永久 独家 排他 全权 概不负责 免除一切责任 并赔偿 "
    )
    clauses = [{"clause_id": "C-X", "heading": "X", "text": big_text * 10}]
    classifications = [{"clause_id": "C-X", "top_labels": ["liability_limitation"]}]
    res = score_clause_risk(clauses, classifications)
    assert 0.0 <= res["risks"][0]["risk_score"] <= 1.0


def test_score_clause_risk_length_mismatch_errors() -> None:
    res = score_clause_risk([{}], [{}, {}])
    assert res["ok"] is False
    assert "长度不一致" in res["error"]


# ============================================================
# §6. redline_diff
# ============================================================
def test_redline_diff_detects_add_remove() -> None:
    template = "1. Term\nVendor liability is capped at $1M.\n2. Payment\nNet 30."
    contract = "1. Term\nVendor liability is unlimited.\n2. Payment\nNet 30."
    res = redline_diff(template, contract)
    assert res["ok"] is True
    assert res["add_count"] >= 1
    assert res["remove_count"] >= 1
    assert "liability is unlimited" in res["diff_text"]


def test_redline_diff_identical_no_changes() -> None:
    text = "Same text\nSecond line\n"
    res = redline_diff(text, text)
    assert res["add_count"] == 0
    assert res["remove_count"] == 0


def test_redline_diff_invalid_input_errors() -> None:
    res = redline_diff(123, "abc")  # type: ignore[arg-type]
    assert res["ok"] is False


# ============================================================
# §7. index_terms
# ============================================================
def test_index_terms_finds_defined_and_undefined() -> None:
    text = (
        '"Confidential Information" means any data marked confidential. '
        '"Confidential Information" includes trade secrets. '
        '"Force Majeure Event" must be communicated within 5 days. '
        '"Force Majeure Event" applies to natural disasters. '
        '"Force Majeure Event" excludes financial crisis.'
    )
    res = index_terms(text)
    assert res["ok"] is True
    assert "Confidential Information" in res["defined_terms"]
    # Force Majeure Event 用了 3 次但没定义
    undef_terms = [u["term"] for u in res["undefined_terms"]]
    assert "Force Majeure Event" in undef_terms


def test_index_terms_chinese_definition() -> None:
    text = '"机密信息"是指标记为机密的数据。"机密信息"包括商业秘密。'
    res = index_terms(text)
    assert "机密信息" in res["defined_terms"]


def test_index_terms_skip_single_use() -> None:
    """只用 1 次的术语不当作 undefined（噪音过滤）."""
    text = '"Some Term" appears only once and should not be flagged.'
    res = index_terms(text)
    undef_terms = [u["term"] for u in res["undefined_terms"]]
    assert "Some Term" not in undef_terms


def test_index_terms_invalid_input() -> None:
    res = index_terms(123)  # type: ignore[arg-type]
    assert res["ok"] is False


# ============================================================
# §8. ToolPlugin / ACTPlugin
# ============================================================
def test_tool_plugin_registers_5_tools() -> None:
    """W4 fix（2026-05-19）：``get_tools() -> list[ToolSpec]`` 与 SDK 同形.

    之前的 dict 形态 → SDK ToolPlugin Protocol 校验不过 → 工具未注册 →
    cookbook real LLM E2E "contract_auditor_* 工具未注册"。改回 list 后修复.
    """
    plugin = ContractAuditorToolPlugin()
    tools = plugin.get_tools()
    assert isinstance(tools, list), (
        "get_tools() 必须返回 list[ToolSpec]（与 SDK ToolPlugin Protocol 一致）"
    )
    assert len(tools) == 5
    names = {t["name"] for t in tools}
    assert names == {
        "contract_auditor_split_clauses",
        "contract_auditor_classify_clauses",
        "contract_auditor_score_clause_risk",
        "contract_auditor_redline_diff",
        "contract_auditor_index_terms",
    }


def test_tool_plugin_each_tool_has_schema() -> None:
    """每个 ToolSpec 必须含 SDK 标准 4 字段：name / description / input_schema / handler."""
    plugin = ContractAuditorToolPlugin()
    for spec in plugin.get_tools():
        name = spec["name"]
        assert "description" in spec, f"{name} 缺 description"
        assert "input_schema" in spec, f"{name} 缺 input_schema（SDK Protocol 规定）"
        assert "handler" in spec, f"{name} 缺 handler（SDK Protocol 规定）"
        assert callable(spec["handler"])


def test_act_plugin_returns_act_dir() -> None:
    """W4 fix（2026-05-19）：ACTPlugin 改为 SDK 5-method 标准形态.

    旧 ``get_act_directories() -> list[Path]`` 已被替换为标准 ``get_act_root()`` /
    ``get_act_file_path()`` / ``act_name`` / ``get_tool_names()``（与 financial-analyst
    / literature-reviewer / data-analyst 同源）.
    """
    plugin = ContractAuditorACTPlugin()
    assert plugin.act_name == "contract_auditor"
    assert plugin.plugin_id == "contract_auditor.act"
    act_root = plugin.get_act_root()
    assert act_root.exists()
    assert act_root.name == "contract_auditor"
    assert (act_root / "__act__.yaml").exists()
    assert (act_root / "ext_contract_auditor.md").exists()
    act_file = plugin.get_act_file_path()
    assert act_file.exists()
    assert act_file.name == "ext_contract_auditor.md"
    tool_names = plugin.get_tool_names()
    assert len(tool_names) >= 5
    assert "contract_auditor_split_clauses" in tool_names
    assert "word_smart_export" in tool_names


# ============================================================
# §9. MandatoryClauseGate
# ============================================================
def _make_classify_tool_result(
    label_counts: dict[str, int]
) -> dict:
    return {
        "tool_name": "contract_auditor_classify_clauses",
        "result": {"ok": True, "label_counts": label_counts},
    }


def test_mandatory_gate_allows_when_all_present() -> None:
    gate_plugin = MandatoryClauseGate(strict=True)
    gate = gate_plugin.get_gate()
    label_counts = {
        "data_protection_gdpr": 1,
        "antitrust_competition": 1,
        "export_control": 1,
    }
    decision = gate.evaluate(
        {}, {"recent_tool_results": [_make_classify_tool_result(label_counts)]}
    )
    assert decision.verdict.name == "ALLOW"


def test_mandatory_gate_blocks_strict_mode_missing() -> None:
    gate_plugin = MandatoryClauseGate(strict=True)
    gate = gate_plugin.get_gate()
    label_counts = {"data_protection_gdpr": 1}  # 缺 antitrust + export_control
    decision = gate.evaluate(
        {}, {"recent_tool_results": [_make_classify_tool_result(label_counts)]}
    )
    assert decision.verdict.name == "BLOCK"
    assert "反垄断" in decision.reason or "antitrust" in decision.reason


def test_mandatory_gate_defers_non_strict_mode() -> None:
    gate_plugin = MandatoryClauseGate(strict=False)
    gate = gate_plugin.get_gate()
    label_counts = {"data_protection_gdpr": 1}
    decision = gate.evaluate(
        {}, {"recent_tool_results": [_make_classify_tool_result(label_counts)]}
    )
    assert decision.verdict.name == "DEFER"


def test_mandatory_gate_defers_when_no_classification_yet() -> None:
    gate_plugin = MandatoryClauseGate()
    gate = gate_plugin.get_gate()
    decision = gate.evaluate({}, {"recent_tool_results": []})
    assert decision.verdict.name == "DEFER"


# ============================================================
# §10. HighRiskBlockingGate
# ============================================================
def _make_risk_tool_result(risks: list[dict]) -> dict:
    high = sum(1 for r in risks if r.get("risk_score", 0) >= 0.75)
    med = sum(1 for r in risks if 0.5 <= r.get("risk_score", 0) < 0.75)
    return {
        "tool_name": "contract_auditor_score_clause_risk",
        "result": {
            "ok": True, "risks": risks, "high_count": high, "medium_count": med,
        },
    }


def test_high_risk_gate_allows_when_no_high_risk() -> None:
    gate_plugin = HighRiskBlockingGate()
    gate = gate_plugin.get_gate()
    risks = [{"clause_id": "C-1", "risk_score": 0.4, "level": "low",
              "label": "force_majeure", "heading": "FM"}]
    decision = gate.evaluate(
        {}, {"recent_tool_results": [_make_risk_tool_result(risks)]}
    )
    assert decision.verdict.name == "ALLOW"


def test_high_risk_gate_blocks_when_high_risk_no_marker() -> None:
    gate_plugin = HighRiskBlockingGate()
    gate = gate_plugin.get_gate()
    risks = [
        {"clause_id": "C-7", "risk_score": 0.92, "level": "high",
         "label": "liability_limitation", "heading": "Liability"},
    ]
    decision = gate.evaluate(
        {"final_output": "整体风险可控，无需进一步审核"},
        {"recent_tool_results": [_make_risk_tool_result(risks)]},
    )
    assert decision.verdict.name == "BLOCK"
    assert "high-risk" in decision.reason or "高风险" in decision.reason


def test_high_risk_gate_allows_when_high_risk_has_marker() -> None:
    gate_plugin = HighRiskBlockingGate()
    gate = gate_plugin.get_gate()
    risks = [
        {"clause_id": "C-7", "risk_score": 0.92, "level": "high",
         "label": "liability_limitation", "heading": "Liability"},
    ]
    final_text_with_marker = (
        "## 执行摘要\n本合同检测到 1 处高风险条款。\n"
        "**需法务复核** — 请法务团队进一步 review 第 7 条。"
    )
    write_tool = {
        "tool_name": "data_analyst_write_report",
        "args": {"content": final_text_with_marker},
    }
    decision = gate.evaluate(
        {},
        {"recent_tool_results": [_make_risk_tool_result(risks), write_tool]},
    )
    assert decision.verdict.name == "ALLOW"


def test_high_risk_gate_threshold_configurable() -> None:
    """阈值 0.95 时，0.85 的条款不算 high-risk."""
    gate_plugin = HighRiskBlockingGate(threshold=0.95)
    gate = gate_plugin.get_gate()
    risks = [{"clause_id": "C-1", "risk_score": 0.85, "level": "high",
              "label": "x", "heading": "x"}]
    decision = gate.evaluate(
        {}, {"recent_tool_results": [_make_risk_tool_result(risks)]}
    )
    assert decision.verdict.name == "ALLOW"


# ============================================================
# §11. HintPlugins
# ============================================================
def test_ambiguous_hint_detects_phrases() -> None:
    plugin = AmbiguousLanguageHintPlugin()
    text_with_ambiguous = (
        "Vendor shall use reasonable best efforts to deliver as soon as possible."
    )
    split_tool = {
        "tool_name": "contract_auditor_split_clauses",
        "args": {"contract_text": text_with_ambiguous},
        "result": {"ok": True, "clauses": []},
    }
    hint = plugin.hint_for({"recent_tool_results": [split_tool]})
    assert hint is not None
    assert "reasonable" in hint
    assert "best efforts" in hint
    assert "as soon as possible" in hint or "ASAP" in hint


def test_ambiguous_hint_returns_none_when_clean() -> None:
    plugin = AmbiguousLanguageHintPlugin()
    clean_text = "Vendor shall deliver within 30 calendar days."
    split_tool = {
        "tool_name": "contract_auditor_split_clauses",
        "args": {"contract_text": clean_text},
        "result": {"ok": True, "clauses": []},
    }
    hint = plugin.hint_for({"recent_tool_results": [split_tool]})
    assert hint is None


def test_missing_def_hint_triggers_on_undefined_terms() -> None:
    plugin = MissingDefinitionHintPlugin()
    index_tool = {
        "tool_name": "contract_auditor_index_terms",
        "result": {
            "ok": True,
            "undefined_terms": [
                {"term": "Force Majeure Event", "usage_count": 5},
                {"term": "Affiliate", "usage_count": 3},
            ],
        },
    }
    hint = plugin.hint_for({"recent_tool_results": [index_tool]})
    assert hint is not None
    assert "Force Majeure Event" in hint
    assert "Affiliate" in hint


def test_missing_def_hint_returns_none_when_all_defined() -> None:
    plugin = MissingDefinitionHintPlugin()
    index_tool = {
        "tool_name": "contract_auditor_index_terms",
        "result": {"ok": True, "undefined_terms": []},
    }
    hint = plugin.hint_for({"recent_tool_results": [index_tool]})
    assert hint is None


# ============================================================
# §12. LegalAuditTrailListener
# ============================================================
class _FakeEvent:
    def __init__(self, payload: dict) -> None:
        self.payload = payload


def test_audit_listener_writes_session_start_with_sha256(tmp_path: Path) -> None:
    contract_file = tmp_path / "test_contract.txt"
    contract_file.write_text("This is a test contract.", encoding="utf-8")
    expected_sha = hashlib.sha256(contract_file.read_bytes()).hexdigest()
    audit_log = tmp_path / "audit.jsonl"

    _listener = LegalAuditTrailListener(
        verbose=False,
        audit_log_path=audit_log,
        contract_path=contract_file,
    )
    assert audit_log.exists()
    lines = audit_log.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert first["kind"] == "audit_session_start"
    assert first["contract_sha256"] == expected_sha


def test_audit_listener_records_tool_calls(tmp_path: Path) -> None:
    audit_log = tmp_path / "audit.jsonl"
    listener = LegalAuditTrailListener(
        verbose=False, audit_log_path=audit_log, contract_path=None,
    )
    listener._on_tool_done(_FakeEvent({  # type: ignore[arg-type]
        "tool_name": "contract_auditor_split_clauses", "ok": True,
    }))
    listener._on_tool_done(_FakeEvent({  # type: ignore[arg-type]
        "tool_name": "contract_auditor_score_clause_risk",
        "result": {"high_count": 2, "medium_count": 5},
    }))
    lines = audit_log.read_text(encoding="utf-8").splitlines()
    kinds = [json.loads(line)["kind"] for line in lines]
    assert "tool_call_completed" in kinds
    assert "risk_score_summary" in kinds


def test_audit_listener_records_gate_block(tmp_path: Path) -> None:
    audit_log = tmp_path / "audit.jsonl"
    listener = LegalAuditTrailListener(
        verbose=False, audit_log_path=audit_log, contract_path=None,
    )
    listener._on_gate_blocked(_FakeEvent({  # type: ignore[arg-type]
        "gate_name": "high_risk_blocking",
        "reason": "❌ 检测到 3 个 high-risk 条款但报告未标记人工审核",
    }))
    last_line = audit_log.read_text(encoding="utf-8").splitlines()[-1]
    record = json.loads(last_line)
    assert record["kind"] == "gate_blocked"
    assert record["compliance_event"] is True
    assert "high_risk_blocking" in record["gate_name"]


def test_audit_listener_subscriptions_topics() -> None:
    listener = LegalAuditTrailListener(verbose=False)
    subs = listener.get_subscriptions()
    topics = {s["topic"] for s in subs}
    assert "tool.call_completed" in topics
    assert "gate.blocked" in topics
    assert "agent.task_complete" in topics


# ============================================================
# §13. 端到端 5 步管线测试（不调 LLM）
# ============================================================
def test_end_to_end_pipeline_runs_without_llm() -> None:
    """完整跑一遍 split → classify → score → index 4 步，验证管线不崩."""
    res1 = split_clauses(contract_text=SAMPLE_CONTRACT)
    assert res1["ok"]
    res2 = classify_clauses(res1["clauses"])
    assert res2["ok"]
    res3 = score_clause_risk(res1["clauses"], res2["classifications"])
    assert res3["ok"]
    # 应该至少检出 1 个 high-risk（liability + GDPR + antitrust + export 各算）
    assert res3["high_count"] >= 1
    res4 = index_terms(SAMPLE_CONTRACT)
    assert res4["ok"]


def test_end_to_end_mandatory_gate_passes_on_sample() -> None:
    """SAMPLE_CONTRACT 含全部 3 类必备条款，MandatoryClauseGate 应 ALLOW."""
    res1 = split_clauses(contract_text=SAMPLE_CONTRACT)
    res2 = classify_clauses(res1["clauses"])
    label_counts = res2["label_counts"]
    assert "data_protection_gdpr" in label_counts
    assert "antitrust_competition" in label_counts
    assert "export_control" in label_counts

    gate_plugin = MandatoryClauseGate(strict=True)
    gate = gate_plugin.get_gate()
    decision = gate.evaluate(
        {},
        {"recent_tool_results": [
            {"tool_name": "contract_auditor_classify_clauses",
             "result": {"ok": True, "label_counts": label_counts}}
        ]},
    )
    assert decision.verdict.name == "ALLOW"
