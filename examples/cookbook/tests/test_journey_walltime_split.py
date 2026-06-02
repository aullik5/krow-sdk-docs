"""Cookbook ``_journey_e2e_helpers.assert_journey`` walltime serial/parallel split tests (P2-A).

教训驱动:

开发者 zzp 2026-05-25 真跑 literature-reviewer cookbook 与 contract-auditor 并行
跑 846s > card 上限 800s，内容维度全 OK 但 walltime 维度先挂导致内容维度未及评估.

修法 (P2-A):
- ``expected_card`` 字段拆 ``max_walltime_s_serial`` + ``max_walltime_s_parallel``
- 自动检测并行 (PYTEST_XDIST_WORKER / KROW_COOKBOOK_JOURNEY_PARALLEL /
  KROW_COOKBOOK_PARALLEL_JOURNEYS) → 用对应阈值
- 老字段 ``max_walltime_s`` 仍兼容 (作 serial fallback; 无 parallel 时取 serial * 1.5)

本测试不跑真实 cookbook journey, 直接构造 JourneyResult fixture 验证 helper 逻辑.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# 添加 cookbook 根目录到 sys.path 以 import helpers
import sys
COOKBOOK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COOKBOOK_ROOT))

from _journey_e2e_helpers import (  # noqa: E402
    JourneyResult,
    _is_parallel_journey_run,
    assert_journey,
)


def _make_result(walltime_s: float) -> JourneyResult:
    return JourneyResult(
        cookbook="testcookbook",
        exit_code=0,
        walltime_s=walltime_s,
        output_dir=Path("/tmp"),
        stdout="",
        stderr="",
        artifacts={},
    )


# ────────────────────────────────────────────────────────────────────────
# §1 _is_parallel_journey_run 三套 env SSOT
# ────────────────────────────────────────────────────────────────────────


class TestParallelDetection:
    def test_no_env_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        monkeypatch.delenv("KROW_COOKBOOK_JOURNEY_PARALLEL", raising=False)
        monkeypatch.delenv("KROW_COOKBOOK_PARALLEL_JOURNEYS", raising=False)
        assert _is_parallel_journey_run() is False

    def test_pytest_xdist_worker_makes_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
        assert _is_parallel_journey_run() is True

    def test_journey_parallel_env_truthy_makes_true(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        for truthy in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv("KROW_COOKBOOK_JOURNEY_PARALLEL", truthy)
            assert _is_parallel_journey_run() is True, f"{truthy} should mean parallel"

    def test_journey_parallel_env_falsy_keeps_false(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        monkeypatch.delenv("KROW_COOKBOOK_PARALLEL_JOURNEYS", raising=False)
        for falsy in ("0", "false", ""):
            monkeypatch.setenv("KROW_COOKBOOK_JOURNEY_PARALLEL", falsy)
            assert _is_parallel_journey_run() is False, f"{falsy} should NOT mean parallel"

    def test_parallel_journeys_count_above_one_makes_true(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        monkeypatch.delenv("KROW_COOKBOOK_JOURNEY_PARALLEL", raising=False)
        monkeypatch.setenv("KROW_COOKBOOK_PARALLEL_JOURNEYS", "2")
        assert _is_parallel_journey_run() is True

        monkeypatch.setenv("KROW_COOKBOOK_PARALLEL_JOURNEYS", "1")
        assert _is_parallel_journey_run() is False


# ────────────────────────────────────────────────────────────────────────
# §2 assert_journey walltime serial/parallel 双阈值
# ────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_parallel_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个 test 默认 clean parallel env, 让 test 显式 set 才并行."""
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.delenv("KROW_COOKBOOK_JOURNEY_PARALLEL", raising=False)
    monkeypatch.delenv("KROW_COOKBOOK_PARALLEL_JOURNEYS", raising=False)


class TestWalltimeSerialParallelSplit:
    def test_serial_within_threshold_passes(self) -> None:
        card = {"max_walltime_s_serial": 700, "max_walltime_s_parallel": 1050}
        assert_journey(_make_result(walltime_s=600), card=card)  # no raise

    def test_serial_exceeds_threshold_fails(self) -> None:
        card = {"max_walltime_s_serial": 700, "max_walltime_s_parallel": 1050}
        with pytest.raises(AssertionError, match=r"walltime.*serial threshold"):
            assert_journey(_make_result(walltime_s=750), card=card)

    def test_parallel_env_uses_parallel_threshold(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """开发者 zzp 真实场景: 846s 在 parallel 下用 1200s 阈值应通过."""
        monkeypatch.setenv("KROW_COOKBOOK_JOURNEY_PARALLEL", "1")
        card = {"max_walltime_s_serial": 800, "max_walltime_s_parallel": 1200}
        # zzp 846s 内容全 OK 但 walltime 失败 — parallel 阈值 1200s 下应通过
        assert_journey(_make_result(walltime_s=846), card=card)

    def test_parallel_env_exceeds_parallel_threshold_still_fails(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """parallel 阈值仍是 fail-loud, 不是无脑放行."""
        monkeypatch.setenv("KROW_COOKBOOK_JOURNEY_PARALLEL", "1")
        card = {"max_walltime_s_serial": 800, "max_walltime_s_parallel": 1200}
        with pytest.raises(AssertionError, match=r"walltime.*parallel threshold"):
            assert_journey(_make_result(walltime_s=1300), card=card)

    def test_pytest_xdist_worker_uses_parallel_threshold(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
        card = {"max_walltime_s_serial": 700, "max_walltime_s_parallel": 1050}
        assert_journey(_make_result(walltime_s=1000), card=card)  # parallel: 1050 OK

    def test_legacy_max_walltime_s_works_as_serial(self) -> None:
        """老 expected_card 用 max_walltime_s 字段, 应作 serial fallback."""
        card = {"max_walltime_s": 700}
        assert_journey(_make_result(walltime_s=600), card=card)
        with pytest.raises(AssertionError, match=r"walltime.*serial threshold"):
            assert_journey(_make_result(walltime_s=750), card=card)

    def test_legacy_max_walltime_s_parallel_defaults_to_1_5x(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """老 expected_card 在 parallel 环境下, parallel 阈值 fallback = serial * 1.5."""
        monkeypatch.setenv("KROW_COOKBOOK_JOURNEY_PARALLEL", "1")
        card = {"max_walltime_s": 700}
        # parallel fallback = 700 * 1.5 = 1050
        assert_journey(_make_result(walltime_s=1000), card=card)
        with pytest.raises(AssertionError, match=r"walltime.*parallel threshold"):
            assert_journey(_make_result(walltime_s=1100), card=card)

    def test_no_walltime_constraint_passes_anything(self) -> None:
        """card 不声明 walltime → 跳过校验."""
        card = {}
        assert_journey(_make_result(walltime_s=9999), card=card)


# ────────────────────────────────────────────────────────────────────────
# §3 反退化: 错误信息含诊断键
# ────────────────────────────────────────────────────────────────────────


class TestErrorDiagnostics:
    def test_serial_failure_message_includes_both_thresholds(self) -> None:
        card = {"max_walltime_s_serial": 700, "max_walltime_s_parallel": 1050}
        with pytest.raises(AssertionError) as exc_info:
            assert_journey(_make_result(walltime_s=900), card=card)
        msg = str(exc_info.value)
        assert "serial=700" in msg
        assert "parallel=1050" in msg
        assert "detected=serial" in msg

    def test_parallel_failure_message_points_to_lessons_doc(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("KROW_COOKBOOK_JOURNEY_PARALLEL", "1")
        card = {"max_walltime_s_serial": 700, "max_walltime_s_parallel": 1050}
        with pytest.raises(AssertionError) as exc_info:
            assert_journey(_make_result(walltime_s=1200), card=card)
        msg = str(exc_info.value)
        assert "2026-05-25-sdk-d1-gate-judge-decay" in msg, (
            "错误信息必须指向 lessons 文档让用户能 diagnose"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
