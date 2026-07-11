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


def test_supported_strategies_cover_causal_and_bayes() -> None:
    """2026-06-29 缺口B：补齐因果发现 + 概率推理，覆盖推理管线全部范式。"""
    assert "causal_discovery" in rj.SUPPORTED_STRATEGIES
    assert "bayes_inference" in rj.SUPPORTED_STRATEGIES


def test_reasoning_extra_strategies_set() -> None:
    """因果/概率策略标注为需 [reasoning] 重型依赖（UX 提示用）。"""
    expected = {"causal_discovery", "bayes_inference"}
    assert set(rj.REASONING_EXTRA_STRATEGIES) == expected
    # 必须是 SUPPORTED_STRATEGIES 的子集（否则提示了一个跑不了的策略）
    supported = set(rj.SUPPORTED_STRATEGIES)
    assert set(rj.REASONING_EXTRA_STRATEGIES).issubset(supported)


def test_build_task_context_causal_discovery() -> None:
    ctx = rj.build_reasoning_task_context(
        strategy="causal_discovery", question="挖掘因果结构"
    )
    assert ctx["strategy"] == "causal_discovery"
    assert ctx["act_name"] == "reasoning_pipeline"


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


def test_build_task_context_depth_mode() -> None:
    """PR-S2（2026-07-10）：depth_mode=True 才写入 ctx；默认不写（省长预算）。"""
    ctx = rj.build_reasoning_task_context(
        strategy="hypothesis_test", question="Q", depth_mode=True
    )
    assert ctx["depth_mode"] is True
    ctx_default = rj.build_reasoning_task_context(
        strategy="hypothesis_test", question="Q"
    )
    assert "depth_mode" not in ctx_default


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
        "intent_seeded", "mechanism_chain_events",
        "transient_storms", "transient_storm_recoveries",
    ):
        assert key in s


def test_collector_counts_s_series_events() -> None:
    """PR-S3/S5/S7（2026-07-10）事件观测：seed / 机制链 / 瞬断风暴。"""
    c = rj.ReasoningEventCollector()
    c.handle(_FakeEvent("intent.seeded", {"session_key": "s1"}))
    c.handle(_FakeEvent(
        "reasoning.mechanism_chain",
        {"attempted": True, "built": 3, "winner_id": "h2", "reason": "ok"},
    ))
    c.handle(_FakeEvent("provider.transient_storm", {"consecutive_failures": 3}))
    c.handle(_FakeEvent("provider.transient_storm_recovered", {}))
    assert c.intent_seeded == 1
    assert c.mechanism_chain_events == [
        {"attempted": True, "built": 3, "winner_id": "h2", "reason": "ok"}
    ]
    assert c.transient_storms == 1
    assert c.transient_storm_recoveries == 1


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


def test_archive_reasoning_json_copies_newest(tmp_path: Path) -> None:
    """P2（2026-07-11）：项目 .krow/reasoning/**/*.json 归档进 output。"""
    project = tmp_path / "proj"
    src = project / ".krow" / "reasoning"
    (src / "checkpoints").mkdir(parents=True)
    (src / "reasoning-a.json").write_text('{"a":1}', encoding="utf-8")
    (src / "checkpoints" / "ckpt-1.json").write_text('{"c":1}', encoding="utf-8")
    out = tmp_path / "out"
    copied = rj.archive_reasoning_json(project, out)
    names = sorted(p.name for p in copied)
    assert names == [
        "reasoning_archive_ckpt-1.json",
        "reasoning_archive_reasoning-a.json",
    ]
    assert all(p.exists() for p in copied)


def test_archive_reasoning_json_missing_dir_failsoft(tmp_path: Path) -> None:
    assert rj.archive_reasoning_json(tmp_path / "nope", tmp_path / "out") == []


def test_persist_with_project_dir_archives(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    src = project / ".krow" / "reasoning"
    src.mkdir(parents=True)
    (src / "reasoning-b.json").write_text('{"b":2}', encoding="utf-8")
    outcome = rj.extract_reasoning_outcome(_FakeResult(True, "结论"))
    rj.persist_reasoning_outcome(
        outcome,
        output_dir=tmp_path / "out",
        strategy="hypothesis_test",
        question="q",
        reasoning_id="rid-arch",
        project_dir=project,
    )
    assert (tmp_path / "out" / "reasoning_archive_reasoning-b.json").exists()


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


def test_main_default_questions_cover_all_strategies() -> None:
    """每个支持的策略都要有默认问题，否则裸跑 ``python main.py <strategy>`` 会落空。"""
    import main
    for strat in rj.SUPPORTED_STRATEGIES:
        assert strat in main._DEFAULT_QUESTIONS, f"缺默认问题：{strat}"


def test_ensure_utf8_stdio_no_crash() -> None:
    """缺口A 回归：UTF-8 stdio 守护可幂等调用、不抛异常（Windows GBK emoji 崩溃根治）。"""
    import main
    main._ensure_utf8_stdio()
    main._ensure_utf8_stdio()  # 幂等


def test_warn_if_reasoning_extra_missing_no_crash(capsys) -> None:
    """选定性策略时不应给重型依赖提示；选因果策略时函数本身不崩。"""
    import main
    main._warn_if_reasoning_extra_missing(["evidence_chain"])
    out = capsys.readouterr()
    assert "krow-agent-sdk[reasoning]" not in out.err
    # 因果策略：无论本机是否装齐 dowhy/pgmpy，函数都不应抛异常
    main._warn_if_reasoning_extra_missing(["causal_discovery"])
