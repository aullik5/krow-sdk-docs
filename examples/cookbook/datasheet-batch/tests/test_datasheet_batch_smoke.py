"""datasheet-batch cookbook smoke 测试（零 LLM，零网络）。

覆盖：
- §1 单份解析（正常 / 空 / 缺失 / 损坏 / 型号不匹配降级）
- §2 批量并发解析（per-item 归属 / 失败隔离 / 覆盖计数 / 续跑）
- §3 ToolPlugin / ACTPlugin Protocol 契约
- §4 DatasheetBatchCoverageGate（DEFER / BLOCK 全失败 / BLOCK 低覆盖 / ALLOW）
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import datasheet_batch_plugin as db

_SAMPLE = Path(__file__).resolve().parent.parent / "sample_data"


# ════════════════════════════════════════════════════════════════════════
# §1. 单份解析
# ════════════════════════════════════════════════════════════════════════


def test_parse_one_normal() -> None:
    res = db.parse_datasheet_file(str(_SAMPLE / "RES-0402-10K.txt"), model="RES-0402-10K")
    assert res["ok"] is True
    assert res["part_number"] == "RES-0402-10K"
    assert res["fields"]["manufacturer"] == "Yageo"
    assert res["fields"]["package"].startswith("0402")
    assert res["degraded"] is False


def test_parse_one_missing_file_fail_loud() -> None:
    res = db.parse_datasheet_file(str(_SAMPLE / "nope.txt"))
    assert res["ok"] is False and "不存在" in res["error"]


def test_parse_one_corrupt_no_fields_fail_loud() -> None:
    res = db.parse_datasheet_file(str(_SAMPLE / "CORRUPT-BROKEN.txt"))
    assert res["ok"] is False and "未抽到" in res["error"]


def test_parse_one_empty_fail_loud(tmp_path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    res = db.parse_datasheet_file(str(empty))
    assert res["ok"] is False and "为空" in res["error"]


def test_parse_one_model_mismatch_degraded() -> None:
    # 期望型号与解析出的 part_number 对不上 → 降级（可判定）
    res = db.parse_datasheet_file(str(_SAMPLE / "RES-0402-10K.txt"), model="WRONG-MODEL")
    assert res["ok"] is True
    assert res["degraded"] is True


# ════════════════════════════════════════════════════════════════════════
# §2. 批量并发解析
# ════════════════════════════════════════════════════════════════════════


def _all_items() -> list[dict[str, str]]:
    return [
        {"model": "RES-0402-10K", "path": str(_SAMPLE / "RES-0402-10K.txt")},
        {"model": "CAP-0603-100NF", "path": str(_SAMPLE / "CAP-0603-100NF.txt")},
        {"model": "MCU-STM32F103C8T6", "path": str(_SAMPLE / "MCU-STM32F103.txt")},
        {"model": "DIODE-1N4148", "path": str(_SAMPLE / "DIODE-1N4148.txt")},
    ]


@pytest.mark.skipif(
    not db._ORCHESTRATOR_AVAILABLE,
    reason="需 krow-agent-sdk-runtime 提供 modules.agent.batch_orchestrator",
)
def test_batch_all_success_and_identity(tmp_path) -> None:
    res = db.datasheet_batch_parse(_all_items(), project_root=str(tmp_path), max_workers=4)
    assert res["ok"] is True
    assert res["completed"] == 4
    assert res["failed"] == 0
    # per-item 身份归属：每个 model 绑对自己的 part_number
    by_model = {r["model"]: r for r in res["results"]}
    assert by_model["RES-0402-10K"]["part_number"] == "RES-0402-10K"
    assert by_model["CAP-0603-100NF"]["part_number"] == "CAP-0603-100NF"


@pytest.mark.skipif(not db._ORCHESTRATOR_AVAILABLE, reason="需 runtime")
def test_batch_failure_isolation(tmp_path) -> None:
    items = _all_items() + [
        {"model": "CORRUPT", "path": str(_SAMPLE / "CORRUPT-BROKEN.txt")},
        {"model": "MISSING", "path": str(_SAMPLE / "does-not-exist.txt")},
    ]
    res = db.datasheet_batch_parse(items, project_root=str(tmp_path), max_workers=6)
    assert res["completed"] == 4
    assert res["failed"] == 2
    # 失败份被单独记账、其余照常完成
    failed_models = {r["model"] for r in res["results"] if r["status"] == "failed"}
    assert failed_models == {"CORRUPT", "MISSING"}
    assert res["coverage"] == round(4 / 6, 4)


@pytest.mark.skipif(not db._ORCHESTRATOR_AVAILABLE, reason="需 runtime")
def test_batch_resumable(tmp_path) -> None:
    items = _all_items()
    r1 = db.datasheet_batch_parse(items, project_root=str(tmp_path), batch_size=2, max_workers=2)
    assert len(r1["results"]) == 2
    assert r1["remaining"] == 2
    assert r1["should_continue"] is True
    r2 = db.datasheet_batch_parse(items, project_root=str(tmp_path), batch_size=2, max_workers=2)
    assert len(r2["results"]) == 2
    assert r2["remaining"] == 0
    assert r2["should_continue"] is False


def test_batch_empty_fail_loud() -> None:
    res = db.datasheet_batch_parse([], project_root=tempfile.mkdtemp())
    assert res["ok"] is False and "items 为空" in res["error"]


# ════════════════════════════════════════════════════════════════════════
# §3. ToolPlugin / ACTPlugin Protocol
# ════════════════════════════════════════════════════════════════════════


def test_tool_plugin_registers_2_tools() -> None:
    names = {t["name"] for t in db.DatasheetBatchToolPlugin().get_tools()}
    assert names == {"datasheet_parse_one", "datasheet_batch_parse"}


def test_act_plugin_root_and_manifest_exist() -> None:
    plugin = db.DatasheetBatchACTPlugin()
    assert plugin.get_act_root().is_dir()
    assert (plugin.get_act_root() / "__act__.yaml").is_file()
    assert (plugin.get_act_root() / "ext_datasheet_batch.md").is_file()


def test_act_plugin_includes_smart_file_write() -> None:
    assert "smart_file_write" in db.DatasheetBatchACTPlugin().get_tool_names()


# ════════════════════════════════════════════════════════════════════════
# §4. DatasheetBatchCoverageGate（N4 覆盖可判定守门）
# ════════════════════════════════════════════════════════════════════════


@pytest.fixture
def verdict():
    from krow_agent_sdk.protocols import GateVerdict
    return GateVerdict


def _batch_tr(*, completed: int, failed: int, degraded: int = 0) -> dict:
    return {
        "tool_name": "datasheet_batch_parse",
        "result": {"ok": True, "completed": completed, "failed": failed, "degraded": degraded},
    }


def test_gate_defers_when_no_batch(verdict) -> None:
    gate = db.DatasheetBatchCoverageGate().get_gate()
    d = gate.evaluate({}, {"recent_tool_results": []})
    assert d.verdict == verdict.DEFER


def test_gate_blocks_all_failed(verdict) -> None:
    gate = db.DatasheetBatchCoverageGate().get_gate()
    d = gate.evaluate({}, {"recent_tool_results": [_batch_tr(completed=0, failed=5)]})
    assert d.verdict == verdict.BLOCK
    assert "全部失败" in d.reason


def test_gate_blocks_low_coverage(verdict) -> None:
    gate = db.DatasheetBatchCoverageGate().get_gate()
    # 2/10 = 20% < 50% 下限
    d = gate.evaluate({}, {"recent_tool_results": [_batch_tr(completed=2, failed=8)]})
    assert d.verdict == verdict.BLOCK
    assert "覆盖率过低" in d.reason


def test_gate_allows_good_coverage(verdict) -> None:
    gate = db.DatasheetBatchCoverageGate().get_gate()
    d = gate.evaluate({}, {"recent_tool_results": [_batch_tr(completed=8, failed=2)]})
    assert d.verdict == verdict.ALLOW
