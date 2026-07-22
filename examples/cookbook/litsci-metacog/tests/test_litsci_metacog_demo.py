"""litsci-metacog cookbook 冒烟测试（无 LLM · System-1 确定性）。

覆盖：
- 观测层 contributor：applicable 收窄 + error_vector/signals 三场景；
- 唤醒层 trigger：形态 A（零下载）/ 形态 B（失败率越阈）/ 不误报；
- 注册闭环（需 runtime）：register → SDK load_situation_contributors → applicable。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from litsci_metacog_demo import (
    DownloadCompletenessContributor,
    register,
    wake_zero_download_with_hits,
)


def _exe(**step_results) -> SimpleNamespace:
    return SimpleNamespace(_step_results=step_results)


def _sr(tool: str, output: dict) -> SimpleNamespace:
    return SimpleNamespace(tool=tool, output=output)


def _snap(contributor, executor):
    data = contributor(executor)
    return SimpleNamespace(
        signals=data.get("signals", {}), error_vector=data.get("error_vector", {})
    )


class TestContributor:
    def test_zero_download_error_vector(self):
        c = DownloadCompletenessContributor()
        exe = _exe(
            s1=_sr("paper_search", {"papers": [{"id": i} for i in range(5)]}),
            s2=_sr("download_pdf", {"counts": {"requested": 5, "downloaded": 0, "failed": 5}}),
        )
        assert c.applicable(exe) is True
        out = c(exe)
        assert out["error_vector"]["download_gap"] == 1.0
        assert out["signals"]["papers_found"] == 5
        assert out["signals"]["dl_downloaded"] == 0

    def test_partial_success_error_vector(self):
        c = DownloadCompletenessContributor()
        exe = _exe(
            s1=_sr("paper_search", {"papers": [{"id": i} for i in range(5)]}),
            s2=_sr("download_pdf", {"counts": {"requested": 5, "downloaded": 4, "failed": 1}}),
        )
        assert c(exe)["error_vector"]["download_gap"] == 0.2

    def test_non_litsci_task_not_applicable(self):
        c = DownloadCompletenessContributor()
        exe = _exe(s1=_sr("write_output", {"path": "report.md"}))
        assert c.applicable(exe) is False
        assert c(exe) == {}

    def test_fail_soft_on_garbage(self):
        c = DownloadCompletenessContributor()
        assert c(SimpleNamespace()) == {}  # 无 _step_results → 不抛，返 {}


class TestWakeTrigger:
    def test_form_a_zero_download_fires(self):
        c = DownloadCompletenessContributor()
        exe = _exe(
            s1=_sr("paper_search", {"papers": [{"id": i} for i in range(5)]}),
            s2=_sr("download_pdf", {"counts": {"requested": 5, "downloaded": 0, "failed": 5}}),
        )
        reason = wake_zero_download_with_hits(None, _snap(c, exe), {}, None)
        assert reason is not None and "zero_download" in reason

    def test_form_b_high_failure_fires(self):
        c = DownloadCompletenessContributor()
        exe = _exe(
            s1=_sr("paper_search", {"papers": [{"id": i} for i in range(10)]}),
            s2=_sr("download_pdf", {"counts": {"requested": 10, "downloaded": 3, "failed": 7}}),
        )
        reason = wake_zero_download_with_hits(None, _snap(c, exe), {}, None)
        assert reason is not None and "download_gap" in reason

    def test_healthy_does_not_fire(self):
        c = DownloadCompletenessContributor()
        exe = _exe(
            s1=_sr("paper_search", {"papers": [{"id": i} for i in range(5)]}),
            s2=_sr("download_pdf", {"counts": {"requested": 5, "downloaded": 4, "failed": 1}}),
        )
        assert wake_zero_download_with_hits(None, _snap(c, exe), {}, None) is None

    def test_non_litsci_snapshot_does_not_fire(self):
        snap = SimpleNamespace(signals={"unrelated": 1}, error_vector={})
        assert wake_zero_download_with_hits(None, snap, {}, None) is None


class TestRegistrationClosedLoop:
    """注册≠激活闭环（需 krow-agent-sdk[runtime]；缺则 skip）。"""

    def test_register_then_load_and_activate(self):
        try:
            import modules.agent.progressive.metacognitive_situation as ms
        except Exception:  # noqa: BLE001 — 无 runtime → 该闭环不适用
            pytest.skip("krow-agent-sdk[runtime] 不可用，跳过注册闭环")

        c_before = list(ms._CONTRIBUTOR_FQCNS)
        w_before = list(ms._WAKE_TRIGGER_FQCNS)
        try:
            fqcns = register(strict=True)
            assert fqcns["contributor"].endswith(":DownloadCompletenessContributor")
            # 注册 → SDK load → 能实例化出来（注册≠激活的激活侧）
            loaded = ms.load_situation_contributors()
            assert any(
                type(i).__name__ == "DownloadCompletenessContributor" for i in loaded
            )
        finally:
            ms._CONTRIBUTOR_FQCNS[:] = c_before
            ms._WAKE_TRIGGER_FQCNS[:] = w_before
