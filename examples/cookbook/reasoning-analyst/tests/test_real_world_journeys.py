"""real_world_journeys 预设 smoke tests（零 LLM · PR-B）.

覆盖 2026-07-06 三议题辩论 议题 3 的三个真实世界 journey 预设：
- §1 PRESETS 定义完整性（三个预设 · 策略 · env · 合成子目录）
- §2 get_preset fail-loud
- §3 resolve_journey_sources 优先级（override > env > 合成）
- §4 合成微样例存在 + 零版权声明
- §5 expected_card 文件存在
- §6 main.py --preset CLI 接线
"""
from __future__ import annotations

from pathlib import Path

import pytest
import real_world_journeys as rw

_HERE = Path(__file__).resolve().parent
_COOKBOOK = _HERE.parent


# ════════════════════════════════════════════════════════════════════════
# §1. PRESETS 定义完整性
# ════════════════════════════════════════════════════════════════════════


def test_three_presets_present() -> None:
    assert set(rw.PRESETS) == {"target_discovery", "whodunit_x", "whodunit_z"}


def test_preset_strategies_valid() -> None:
    """预设策略必须落在 cookbook 支持集合内（否则 build_task_context 会 fail-loud）。"""
    import reasoning_journeys as rj

    for name, preset in rw.PRESETS.items():
        assert preset.strategy in rj.SUPPORTED_STRATEGIES, name


def test_target_discovery_is_causal() -> None:
    assert rw.PRESETS["target_discovery"].strategy == "causal_discovery"


def test_whodunits_are_hypothesis_test() -> None:
    assert rw.PRESETS["whodunit_x"].strategy == "hypothesis_test"
    assert rw.PRESETS["whodunit_z"].strategy == "hypothesis_test"


def test_presets_declare_data_env_and_hint() -> None:
    for name, preset in rw.PRESETS.items():
        assert preset.data_env.startswith("KROW_JOURNEY_"), name
        assert preset.data_hint.strip(), name
        assert preset.question.strip(), name


# ════════════════════════════════════════════════════════════════════════
# §2. get_preset
# ════════════════════════════════════════════════════════════════════════


def test_get_preset_ok() -> None:
    assert rw.get_preset("whodunit_x").name == "whodunit_x"


def test_get_preset_unknown_fail_loud() -> None:
    with pytest.raises(rw.UnknownPresetError) as exc:
        rw.get_preset("nope")
    assert "nope" in str(exc.value)
    assert "target_discovery" in str(exc.value)  # 黄金错误模板列可选项


# ════════════════════════════════════════════════════════════════════════
# §3. resolve_journey_sources 优先级
# ════════════════════════════════════════════════════════════════════════


def test_resolve_falls_back_to_synthetic(monkeypatch: pytest.MonkeyPatch) -> None:
    preset = rw.PRESETS["whodunit_x"]
    monkeypatch.delenv(preset.data_env, raising=False)
    path, is_real = rw.resolve_journey_sources(preset)
    assert is_real is False
    assert path == rw.synthetic_dir(preset)
    assert path.exists()


def test_resolve_env_real_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preset = rw.PRESETS["whodunit_z"]
    real = tmp_path / "real_novel.md"
    real.write_text("全文……", encoding="utf-8")
    monkeypatch.setenv(preset.data_env, str(real))
    path, is_real = rw.resolve_journey_sources(preset)
    assert is_real is True
    assert path == real


def test_resolve_env_missing_fail_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    preset = rw.PRESETS["target_discovery"]
    monkeypatch.setenv(preset.data_env, r"D:\definitely\not\here\papers")
    with pytest.raises(FileNotFoundError) as exc:
        rw.resolve_journey_sources(preset)
    assert preset.data_env in str(exc.value)


def test_resolve_override_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preset = rw.PRESETS["whodunit_x"]
    monkeypatch.setenv(preset.data_env, str(tmp_path / "env_data.md"))
    override = tmp_path / "override.md"
    override.write_text("x", encoding="utf-8")
    path, is_real = rw.resolve_journey_sources(preset, override=str(override))
    assert is_real is True
    assert path == override


# ════════════════════════════════════════════════════════════════════════
# §4. 合成微样例（随仓 · 零版权）
# ════════════════════════════════════════════════════════════════════════


def test_synthetic_samples_present_and_nonempty() -> None:
    for name in ("whodunit_x", "target_discovery"):
        preset = rw.PRESETS[name]
        d = rw.synthetic_dir(preset)
        assert d.exists() and d.is_dir(), name
        docs = [p for p in d.rglob("*") if p.is_file()]
        assert docs, f"{name} 无合成样例"
        assert sum(p.stat().st_size for p in docs) > 300, name


def test_synthetic_samples_declare_copyright_free() -> None:
    """合成样例头部必须声明零版权（防止误当真实作品分发）。"""
    for name in ("whodunit_x", "target_discovery"):
        d = rw.synthetic_dir(rw.PRESETS[name])
        for p in d.rglob("*.md"):
            head = p.read_text(encoding="utf-8")[:400]
            assert ("零版权" in head) or ("合成" in head), p


# ════════════════════════════════════════════════════════════════════════
# §5. expected_card
# ════════════════════════════════════════════════════════════════════════


def test_expected_cards_exist() -> None:
    cards = _COOKBOOK / "tests" / "expected_cards"
    for preset in rw.PRESETS.values():
        assert (cards / preset.expected_card).exists(), preset.expected_card


# ════════════════════════════════════════════════════════════════════════
# §6. main.py --preset CLI 接线
# ════════════════════════════════════════════════════════════════════════


def test_main_imports_preset_helpers() -> None:
    """main.py 已接线 real_world_journeys（--preset CLI 依赖）。"""
    import main

    assert set(main.PRESETS) == {"target_discovery", "whodunit_x", "whodunit_z"}
    assert callable(main.get_preset)
    assert callable(main.resolve_journey_sources)
