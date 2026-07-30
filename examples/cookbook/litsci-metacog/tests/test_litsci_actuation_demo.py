"""litsci-metacog cookbook · 执行面冒烟测试（无 LLM · System-1 确定性）。

覆盖执行器的四条纪律，每条都对应一个真实踩过的坑：

- **自判适用性**：非本族任务不开火（靠注册顺序抢的执行器会误伤别族）；
- **饱和判据看产出、且只在有新尝试时观测**（读时间会在 agent 干正事时假开火）；
- **有界**：``MAX_FIRES`` 触顶让位（无界执行器把计划撑爆）；
- **记账**：动作带 ``decision``，且该名字真在契约表里（不登记 = 报表恒 0）。

执行面注册表在 runtime 里，缺 runtime 时整族 skip（与观测面 demo 同款）。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from litsci_actuation_demo import (
    DECISION_METADATA_FALLBACK,
    FALLBACK_TOOL,
    SATURATION_BEATS,
    MetadataFallbackActuator,
    register_actuation,
)

# 探针要探 **runtime**，不是探 facade：``krow_agent_sdk.actuation`` 在 SDK-only
# 安装下也 import 得动（facade 顶层刻意不碰 ``modules``），拿它当探针会让整族用例
# 在无 runtime 的 cookbook smoke job 里"以为有环境"，然后在第一次真调用时红。
try:
    import modules.agent.progressive.step_actuators  # noqa: F401

    _HAS_RUNTIME = True
except Exception:  # noqa: BLE001
    _HAS_RUNTIME = False

pytestmark = pytest.mark.skipif(
    not _HAS_RUNTIME,
    reason="执行面需 krow-agent-sdk[runtime]（PlanStep / 注册表 / 饱和计数器在 runtime 里）",
)


def _sr(tool: str, output: dict) -> SimpleNamespace:
    return SimpleNamespace(tool=tool, output=output)


def _world(papers: int = 8):
    """造一个与 ProgressiveExecutor 同形的最小世界（executor + plan）。"""
    plan = SimpleNamespace(steps=[])
    exe = SimpleNamespace(_step_results={}, _current_plan=plan)
    if papers:
        exe._step_results[0] = _sr(
            "paper_search", {"papers": [{"id": i} for i in range(papers)]}
        )
    return exe, plan


def _download_beat(exe, n: int, *, requested: int = 3, downloaded: int = 0) -> None:
    exe._step_results[n] = _sr(
        "download_pdf",
        {"counts": {
            "requested": requested,
            "downloaded": downloaded,
            "failed": requested - downloaded,
        }},
    )


class TestSelfGating:
    def test_non_litsci_task_is_silent(self):
        act = MetadataFallbackActuator()
        plan = SimpleNamespace(steps=[])
        exe = SimpleNamespace(
            _step_results={0: _sr("write_output", {"path": "r.md"})},
            _current_plan=plan,
        )
        for _ in range(SATURATION_BEATS + 2):
            assert act(exe, plan) is None
        assert plan.steps == []

    def test_downloads_working_is_silent(self):
        """有产出 = 这条路子还在走，别插手。"""
        act = MetadataFallbackActuator()
        exe, plan = _world()
        for n in range(1, SATURATION_BEATS + 3):
            _download_beat(exe, n, requested=3, downloaded=2)
            assert act(exe, plan) is None

    def test_garbage_executor_fails_soft(self):
        act = MetadataFallbackActuator()
        assert act(SimpleNamespace(), SimpleNamespace(steps=[])) is None


class TestSaturationDiscipline:
    def test_fires_only_after_repeated_futile_attempts(self):
        act = MetadataFallbackActuator()
        exe, plan = _world()
        fired_at = None
        for n in range(1, SATURATION_BEATS + 3):
            _download_beat(exe, n)
            if act(exe, plan) is not None:
                fired_at = n
                break
        assert fired_at is not None, "连续零下载却从不开火 —— 执行器等于不存在"
        assert fired_at > 1, "首拍就开火 = 把一次偶发失败当死路"

    def test_no_new_attempt_is_not_saturation(self):
        """不动 ≠ 饱和：agent 可能正在别处干正事，计数不涨不该被读成路子死了。

        这一条是本文件最值钱的断言。把判据写成"连续 N 拍没变化"（不看有没有
        新尝试）时，agent 一边读已下到的 PDF 一边被判"下载路饱和"，好路子会被撤。
        """
        act = MetadataFallbackActuator()
        exe, plan = _world()
        _download_beat(exe, 1)
        act(exe, plan)
        for _ in range(SATURATION_BEATS + 3):  # 没有新的下载尝试
            assert act(exe, plan) is None
        assert plan.steps == []


class TestBoundedAndAccounted:
    def _fire_once(self):
        act = MetadataFallbackActuator()
        exe, plan = _world()
        action = None
        for n in range(1, SATURATION_BEATS + 3):
            _download_beat(exe, n)
            action = act(exe, plan)
            if action is not None:
                break
        assert action is not None
        return act, exe, plan, action

    def test_action_shape(self):
        _, _, plan, action = self._fire_once()
        assert action.new_step.tool == FALLBACK_TOOL
        assert action.decision == DECISION_METADATA_FALLBACK
        assert action.has_effect
        assert [s.tool for s in plan.steps] == [FALLBACK_TOOL]

    def test_injected_step_is_best_effort(self):
        """自注入的补做步做不完只记 degraded，不把整个任务判失败。"""
        _, exe, plan, action = self._fire_once()
        sid = action.new_step.step_id
        assert sid in getattr(exe, "_best_effort_step_ids", set())

    def test_purpose_tells_the_llm_what_to_do_instead(self):
        """成品指令：说清改做什么 + 明确不要再做什么（TURBO 总则②）。"""
        _, _, _, action = self._fire_once()
        purpose = action.new_step.purpose
        assert "不要再重试下载" in purpose
        assert "元数据" in purpose

    def test_is_bounded(self):
        act, exe, plan, _ = self._fire_once()
        for n in range(50, 60):
            _download_beat(exe, n)
            assert act(exe, plan) is None, "MAX_FIRES 之后仍开火 = 无界"
        assert len(plan.steps) == 1


class TestRegistrationClosedLoop:
    def test_register_puts_both_halves_in_place(self):
        """注册两半都要在：执行器进表 **且** 决策名进契约表。

        只有前一半时执行器照常开火而 ``actuations_total`` 恒 0 —— 报表会说"决策脑
        从没动手"，据此复盘会得出与事实相反的结论。
        """
        import modules.agent.progressive.decision_contract as dc
        import modules.agent.progressive.step_actuators as sa

        a_before = list(sa._ACTUATOR_FQCNS)
        d_before = dict(dc._DOMAIN_CONTRACTS)
        try:
            out = register_actuation(strict=True)
            assert out["actuator"].endswith(":MetadataFallbackActuator")
            assert out["decision"] == DECISION_METADATA_FALLBACK
            assert out["actuator"] in sa._ACTUATOR_FQCNS
            spec = dc.contract_for(DECISION_METADATA_FALLBACK)
            assert spec is not None
            assert spec.prediction.axis == "litsci_download_gap"
            assert spec.max_fires == MetadataFallbackActuator.MAX_FIRES
        finally:
            sa._ACTUATOR_FQCNS[:] = a_before
            dc._DOMAIN_CONTRACTS.clear()
            dc._DOMAIN_CONTRACTS.update(d_before)

    def test_register_is_idempotent(self):
        import modules.agent.progressive.decision_contract as dc
        import modules.agent.progressive.step_actuators as sa

        a_before = list(sa._ACTUATOR_FQCNS)
        d_before = dict(dc._DOMAIN_CONTRACTS)
        try:
            register_actuation(strict=True)
            n = len(sa._ACTUATOR_FQCNS)
            register_actuation(strict=True)
            assert len(sa._ACTUATOR_FQCNS) == n
        finally:
            sa._ACTUATOR_FQCNS[:] = a_before
            dc._DOMAIN_CONTRACTS.clear()
            dc._DOMAIN_CONTRACTS.update(d_before)
