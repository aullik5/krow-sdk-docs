"""reasoning-analyst cookbook smoke tests（零 LLM 调用）.

覆盖：
- §1 build_reasoning_task_context（task_context 形状 / 策略校验 fail-loud / id 生成）
- §2 ReasoningEventCollector（事件归类 / 工具统计 / cognitive.load / 结论事件）
- §3 extract_reasoning_outcome（success vs final_output 判定经验）
- §4 persist_reasoning_outcome（markdown + json 落盘）
- §5 sample_data + main 可导入
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
import reasoning_journeys as rj

# ════════════════════════════════════════════════════════════════════════
# §1. build_reasoning_task_context
# ════════════════════════════════════════════════════════════════════════


def test_supported_strategies_nonempty() -> None:
    assert "evidence_chain" in rj.SUPPORTED_STRATEGIES
    assert "hypothesis_test" in rj.SUPPORTED_STRATEGIES


def test_build_task_context_shape() -> None:
    ctx = rj.build_reasoning_task_context(
        strategy="evidence_chain", question="核实论断 X"
    )
    assert ctx["source"] == "reasoning_panel"
    assert ctx["act_name"] == "reasoning_pipeline"
    assert ctx["strategy"] == "evidence_chain"
    assert ctx["question"] == "核实论断 X"
    assert ctx["reasoning_id"].startswith("reasoning-evidence_chain-")


def test_build_task_context_includes_project_root() -> None:
    ctx = rj.build_reasoning_task_context(
        strategy="hypothesis_test", question="Q", project_root="/tmp/p"
    )
    assert ctx["project_root"] == "/tmp/p"


def test_build_task_context_custom_id() -> None:
    ctx = rj.build_reasoning_task_context(
        strategy="evidence_chain", question="Q", reasoning_id="rid-123"
    )
    assert ctx["reasoning_id"] == "rid-123"


def test_build_task_context_unknown_strategy_fail_loud() -> None:
    with pytest.raises(rj.UnknownStrategyError) as exc:
        rj.build_reasoning_task_context(strategy="nonexistent", question="Q")
    assert "nonexistent" in str(exc.value)
    assert "evidence_chain" in str(exc.value)  # 黄金错误模板列可选项


def test_build_task_context_empty_question_fail_loud() -> None:
    with pytest.raises(ValueError):
        rj.build_reasoning_task_context(strategy="evidence_chain", question="  ")


# ════════════════════════════════════════════════════════════════════════
# §2. ReasoningEventCollector（用 fake 事件，零 EventBus 依赖）
# ════════════════════════════════════════════════════════════════════════


@dataclass
class _FakeEvent:
    type: str
    payload: dict


def test_collector_counts_tool_calls() -> None:
    c = rj.ReasoningEventCollector()
    c.handle(_FakeEvent("tool.call_completed", {"tool_name": "evaluate_hypotheses"}))
    c.handle(_FakeEvent("tool.call_completed", {"tool_name": "link_evidence"}))
    c.handle(_FakeEvent("tool.call_completed", {"tool_name": "smart_file_search"}))
    assert c.tool_calls["evaluate_hypotheses"] == 1
    assert sum(c.tool_calls.values()) == 3


def test_collector_classifies_reasoning_tools() -> None:
    c = rj.ReasoningEventCollector()
    c.handle(_FakeEvent("tool.call_completed", {"tool_name": "evaluate_hypotheses"}))
    c.handle(_FakeEvent("tool.call_completed", {"tool_name": "smart_file_search"}))
    rt = c.reasoning_tool_calls()
    assert "evaluate_hypotheses" in rt
    assert "smart_file_search" not in rt


def test_collector_counts_cognitive_load() -> None:
    c = rj.ReasoningEventCollector()
    c.handle(_FakeEvent("cognitive.load", {"state": "overload", "load_axis": "goal"}))
    c.handle(_FakeEvent("cognitive.load", {"state": "nominal", "load_axis": "budget"}))
    assert len(c.cognitive_load_events) == 2
    assert c.cognitive_load_events[0]["load_axis"] == "goal"


def test_collector_counts_conclusion_and_task_complete() -> None:
    c = rj.ReasoningEventCollector()
    c.handle(_FakeEvent("reasoning.conclusion.committed", {}))
    c.handle(_FakeEvent("agent.task_complete", {}))
    assert c.conclusion_committed == 1
    assert c.task_complete == 1


def test_collector_ignores_empty_type() -> None:
    c = rj.ReasoningEventCollector()
    c.handle(_FakeEvent("", {"tool_name": "x"}))
    assert sum(c.event_counts.values()) == 0


def test_collector_summary_shape() -> None:
    c = rj.ReasoningEventCollector()
    c.handle(_FakeEvent("tool.call_completed", {"tool_name": "challenge_hypothesis"}))
    s = c.summary()
    for key in (
        "event_types", "tool_calls_total", "reasoning_tool_calls",
        "cognitive_load_events", "conclusion_committed", "task_complete",
    ):
        assert key in s


def test_event_type_compat_legacy_field() -> None:
    @dataclass
    class _Legacy:
        event_type: str
        payload: dict
    assert rj._event_type(_Legacy("tool.call_completed", {})) == "tool.call_completed"


# ════════════════════════════════════════════════════════════════════════
# §3. extract_reasoning_outcome（success vs final_output 经验）
# ════════════════════════════════════════════════════════════════════════


@dataclass
class _FakeResult:
    success: bool
    final_output: str


def test_outcome_success_true_completed() -> None:
    out = rj.extract_reasoning_outcome(_FakeResult(True, "结论文本足够长。" * 5))
    assert out["reasoning_completed"] is True
    assert out["success_flag"] is True


def test_outcome_success_false_but_concluded_via_event() -> None:
    """关键经验：success=False 但有 conclusion 事件 + 非空输出 → 算完成."""
    c = rj.ReasoningEventCollector()
    c.handle(_FakeEvent("reasoning.conclusion.committed", {}))
    out = rj.extract_reasoning_outcome(_FakeResult(False, "完整结论内容。" * 5), c)
    assert out["success_flag"] is False
    assert out["concluded"] is True
    assert out["reasoning_completed"] is True


def test_outcome_empty_output_not_completed() -> None:
    c = rj.ReasoningEventCollector()
    c.handle(_FakeEvent("reasoning.conclusion.committed", {}))
    out = rj.extract_reasoning_outcome(_FakeResult(False, ""), c)
    assert out["reasoning_completed"] is False


def test_outcome_no_collector_no_event_falls_back_to_success() -> None:
    out = rj.extract_reasoning_outcome(_FakeResult(False, "有输出但无结论事件且 success=False"))
    assert out["concluded"] is False
    assert out["reasoning_completed"] is False


# ════════════════════════════════════════════════════════════════════════
# §4. persist_reasoning_outcome
# ════════════════════════════════════════════════════════════════════════


def test_persist_writes_markdown_and_json(tmp_path: Path) -> None:
    c = rj.ReasoningEventCollector()
    c.handle(_FakeEvent("tool.call_completed", {"tool_name": "evaluate_hypotheses"}))
    outcome = rj.extract_reasoning_outcome(
        _FakeResult(True, "# 结论\n下壁 STEMI 诊断成立。"), c
    )
    paths = rj.persist_reasoning_outcome(
        outcome,
        output_dir=tmp_path,
        strategy="evidence_chain",
        question="核实论断",
        reasoning_id="rid-xyz",
    )
    assert paths["markdown"].exists()
    assert paths["json"].exists()
    md = paths["markdown"].read_text(encoding="utf-8")
    assert "evidence_chain" in md
    assert "下壁 STEMI 诊断成立" in md
    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert payload["reasoning_id"] == "rid-xyz"
    assert payload["strategy"] == "evidence_chain"
    assert payload["reasoning_completed"] is True


# ════════════════════════════════════════════════════════════════════════
# §5. sample_data + main 可导入
# ════════════════════════════════════════════════════════════════════════


def test_sample_data_present() -> None:
    sample = Path(__file__).resolve().parents[1] / "sample_data"
    docs = list(sample.glob("*.md"))
    assert len(docs) >= 2


def test_main_importable_and_builds_parser() -> None:
    import main
    # main.main 存在且 _DEFAULT_QUESTIONS 覆盖默认策略
    assert callable(main.main)
    assert "evidence_chain" in main._DEFAULT_QUESTIONS
    assert "hypothesis_test" in main._DEFAULT_QUESTIONS
