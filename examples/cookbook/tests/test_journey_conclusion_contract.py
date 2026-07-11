"""Cookbook ``assert_journey`` conclusion_contract 维度 contract tests（C3 · 2026-07-11）.

Z悲剧走查铁证：真机 run 胜出假设「未具名第三者」赢在不可证伪（真凶=典狱长
被无接地反驳边假排除）。C3 契约：结论要么具名 winner，要么诚实声明证据
不足——禁止"确定地宣布一个不知名者是凶手"。

本测试不跑真实 journey，直接构造 JourneyResult + 产物文件验证 helper 逻辑
（同 test_journey_walltime_split.py 范式）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

COOKBOOK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COOKBOOK_ROOT))

from _journey_e2e_helpers import (  # noqa: E402
    JourneyResult,
    assert_journey,
)


def _make_result(tmp_path: Path, report_text: str) -> JourneyResult:
    report = tmp_path / "reasoning_hypothesis_test.md"
    report.write_text(report_text, encoding="utf-8")
    return JourneyResult(
        cookbook="testcookbook",
        exit_code=0,
        walltime_s=1.0,
        output_dir=tmp_path,
        stdout="",
        stderr="",
        artifacts={"reasoning_hypothesis_test.md": report},
    )


_CARD = {
    "conclusion_contract": {
        "reasoning_hypothesis_test.md": {
            "named_winner_or_honest_uncertainty": {
                "vague_winner_markers": ["不知名第三", "未具名", "身份不明的凶手"],
                "honest_uncertainty_markers": ["无法确定", "证据不足", "存疑"],
            },
        },
    },
}


class TestNamedWinnerOrHonestUncertainty:
    def test_named_winner_passes(self, tmp_path: Path) -> None:
        assert_journey(
            _make_result(tmp_path, "## 结论\n真凶是马格纳斯典狱长。"),
            card=_CARD,
        )

    def test_vague_winner_without_honesty_fails(self, tmp_path: Path) -> None:
        with pytest.raises(AssertionError) as exc:
            assert_journey(
                _make_result(
                    tmp_path, "## 结论\n凶手是一名不知名第三者，可以确定。",
                ),
                card=_CARD,
            )
        assert "conclusion_contract" in str(exc.value)
        assert "vague_winner" in str(exc.value)

    def test_vague_winner_with_honesty_passes(self, tmp_path: Path) -> None:
        assert_journey(
            _make_result(
                tmp_path,
                "## 结论\n最可能是不知名第三者，但证据不足，无法确定。",
            ),
            card=_CARD,
        )

    def test_honest_undecided_passes(self, tmp_path: Path) -> None:
        assert_journey(
            _make_result(tmp_path, "## 结论\n现有证据不足，无法确定真凶。"),
            card=_CARD,
        )

    def test_missing_artifact_skipped(self, tmp_path: Path) -> None:
        result = JourneyResult(
            cookbook="testcookbook",
            exit_code=0,
            walltime_s=1.0,
            output_dir=tmp_path,
            stdout="",
            stderr="",
            artifacts={},
        )
        assert_journey(result, card=_CARD)  # 产物缺失由 required_artifacts 管

    def test_bad_spec_fail_loud(self, tmp_path: Path) -> None:
        bad_card = {
            "conclusion_contract": {
                "reasoning_hypothesis_test.md": {
                    "named_winner_or_honest_uncertainty": {
                        "vague_winner_markers": [],
                        "honest_uncertainty_markers": ["无法确定"],
                    },
                },
            },
        }
        with pytest.raises(AssertionError) as exc:
            assert_journey(_make_result(tmp_path, "x"), card=bad_card)
        assert "必须同时给非空" in str(exc.value)

    def test_old_cards_without_field_unaffected(self, tmp_path: Path) -> None:
        assert_journey(_make_result(tmp_path, "任意内容"), card={})
