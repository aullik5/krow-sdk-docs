"""Cookbook ``run_journey`` 内置 retry 兜底逻辑 contract test (PR #624 · 2026-05-27).

教训驱动:

opus-4.6 在 literature-reviewer 等 long-form 场景偶发 plan 步骤重复执行
(步骤 1-6 + 10-15 重复) → 步骤预算耗尽, ``smart_file_write`` 没真调 →
``output/literature_review.md`` 空, ``main.py`` exit_code=1. 这是真 ReACT
引擎 bug, 但 System 1 plan-repeat 闸门治本前, 用 retry 兜底避免误伤
nightly 信号可信度.

本 test 不真跑 LLM, 通过 monkey-patch ``subprocess.run`` 构造各种 exit
路径 fixture 验证 retry 决策逻辑.

判据 (System 1 严守):
  1) exit_code=0 单跑就 break → ``attempts=1``
  2) exit_code!=0 + 非 cloud env-error → retry 1 次 (默认 ``max_attempts=2``)
  3) exit_code!=0 + 命中 cloud env-error 关键词 → 立即 break 不浪费 LLM
  4) ``max_attempts`` 上限 N 时, exit!=0 跑满 N 次 break
  5) stderr 含 ``[attempt N/M]`` 标记可被诊断脚本 grep
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

COOKBOOK_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COOKBOOK_ROOT))

from _journey_e2e_helpers import (  # noqa: E402
    JourneyResult,
    run_journey,
)


class _StubProc:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    sequence: list[_StubProc],
) -> list[int]:
    """patch ``subprocess.run`` 按 sequence 顺序返回不同 exit code; 记录调用次数."""
    counter = {"calls": 0}

    def fake_run(*args, **kwargs):  # noqa: ANN002, ANN003
        idx = min(counter["calls"], len(sequence) - 1)
        counter["calls"] += 1
        return sequence[idx]

    monkeypatch.setattr(subprocess, "run", fake_run)
    return counter  # type: ignore[return-value]


@pytest.fixture
def cookbook_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Mock cookbook 目录存在 + main.py 文件，避免 ``run_journey`` FileNotFoundError."""
    fake = tmp_path / "_fake_cookbook"
    fake.mkdir()
    (fake / "main.py").write_text("# stub\n", encoding="utf-8")
    # 让 ``Path(__file__).parent / cookbook_dir`` 解析到 tmp_path
    monkeypatch.setattr(
        "_journey_e2e_helpers.Path",
        Path,  # 不替换 Path 本身（避免破坏其他逻辑）
    )

    # 直接把 fake 目录加到 cookbook 根（用 symlink/复制方案不靠谱，
    # 改: monkey-patch ``_journey_e2e_helpers.__file__`` 让 ``Path(__file__).parent`` 指 tmp_path）
    import _journey_e2e_helpers as h
    monkeypatch.setattr(h, "__file__", str(tmp_path / "_journey_e2e_helpers.py"))

    return "_fake_cookbook"


def test_run_journey_exit_0_single_attempt(
    cookbook_dir: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """exit_code=0 时只跑 1 次, 不 retry."""
    counter = _patch_subprocess(
        monkeypatch,
        [_StubProc(returncode=0, stdout="ok", stderr="")],
    )
    monkeypatch.setenv("KROW_COOKBOOK_JOURNEY_MAX_ATTEMPTS", "2")

    result = run_journey(cookbook_dir=cookbook_dir, argv=[])

    assert counter["calls"] == 1, f"exit=0 不该 retry, 实际跑了 {counter['calls']} 次"
    assert result.exit_code == 0
    assert "[attempt 1/2" in result.stderr


def test_run_journey_exit_1_retries_then_pass(
    cookbook_dir: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """首次 exit=1 (非 env-error), retry 第 2 次 exit=0 → 最终 PASS."""
    counter = _patch_subprocess(
        monkeypatch,
        [
            _StubProc(returncode=1, stdout="", stderr="smart_file_write 未执行"),
            _StubProc(returncode=0, stdout="", stderr="ok"),
        ],
    )
    monkeypatch.setenv("KROW_COOKBOOK_JOURNEY_MAX_ATTEMPTS", "2")

    result = run_journey(cookbook_dir=cookbook_dir, argv=[])

    assert counter["calls"] == 2, f"exit=1 应 retry 1 次, 实际 {counter['calls']}"
    assert result.exit_code == 0, "retry 后第 2 次 PASS, 最终 result 应 exit=0"


def test_run_journey_cloud_env_error_no_retry(
    cookbook_dir: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cloud 5xx env-error 关键词命中 → 不 retry (避免浪费 LLM)."""
    counter = _patch_subprocess(
        monkeypatch,
        [_StubProc(returncode=1, stdout="", stderr="服务端临时错误 500")],
    )
    monkeypatch.setenv("KROW_COOKBOOK_JOURNEY_MAX_ATTEMPTS", "3")

    result = run_journey(cookbook_dir=cookbook_dir, argv=[])

    assert counter["calls"] == 1, f"env-error 不该 retry, 实际 {counter['calls']}"
    assert result.exit_code == 1


def test_run_journey_max_attempts_capped(
    cookbook_dir: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """所有 attempt 都 exit!=0 时, 严格不超过 max_attempts 上限."""
    counter = _patch_subprocess(
        monkeypatch,
        [
            _StubProc(returncode=1, stdout="", stderr="fail 1"),
            _StubProc(returncode=1, stdout="", stderr="fail 2"),
            _StubProc(returncode=1, stdout="", stderr="fail 3"),
        ],
    )

    result = run_journey(cookbook_dir=cookbook_dir, argv=[], max_attempts=3)

    assert counter["calls"] == 3, f"max_attempts=3 应跑 3 次, 实际 {counter['calls']}"
    assert result.exit_code == 1
    assert "[attempt 3/3" in result.stderr, "最终 stderr 应保留最后一次 attempt marker"


def test_run_journey_max_attempts_env_default(
    cookbook_dir: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``KROW_COOKBOOK_JOURNEY_MAX_ATTEMPTS`` env var 应被读到; 不设时默认 2."""
    monkeypatch.delenv("KROW_COOKBOOK_JOURNEY_MAX_ATTEMPTS", raising=False)
    counter = _patch_subprocess(
        monkeypatch,
        [
            _StubProc(returncode=1, stdout="", stderr="fail"),
            _StubProc(returncode=1, stdout="", stderr="fail"),
            _StubProc(returncode=1, stdout="", stderr="fail"),
        ],
    )

    result = run_journey(cookbook_dir=cookbook_dir, argv=[])

    assert counter["calls"] == 2, (
        f"env 未设 → 默认 max_attempts=2, 实际跑了 {counter['calls']} 次"
    )
    assert result.exit_code == 1
