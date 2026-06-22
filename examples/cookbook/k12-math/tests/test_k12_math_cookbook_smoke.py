"""k12-math cookbook smoke tests（零 LLM 调用）。

覆盖：
- §1 main.py helper（_validate_learning_path / _write_report）确定性行为
- §2 sample_data 自带 3 份 K12 资料齐全
- §3 校本包 k12_school_pack.yaml 合法 + 继承内置 k12_math（registry 视角）
- §4 System 1 K12 评分工具（环检测 / 权重归一）在 cookbook 语境可用

不调 AgentBuilder.build() / agent.run（无需 API key），符合 cookbook smoke 约定。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import main as cookbook_main

# cookbook-smoke CI 只装 krow-agent-sdk（force-include 仅 modules/agent/sdk），
# 不装完整 runtime（modules.knowledge.* 不可导入）。§3/§4 依赖 runtime 的用例用
# skipif 优雅跳过——其真实覆盖在主仓 tests/knowledge/* + tests/sdk/*；§1/§2 仅依赖
# main.py（runtime 缺失时 fail-soft）与 sample_data，恒跑。
def _runtime_available() -> bool:
    # find_spec("modules.knowledge.domain_packs") 会先 import 父包 modules.knowledge，
    # 若顶层 modules 不在 sys.path（cookbook-smoke 仅装 SDK）则**抛** ModuleNotFoundError
    # 而非返回 None → 必须 try/except 否则模块级炸点导致整个 test 模块收集失败。
    try:
        return importlib.util.find_spec("modules.knowledge.domain_packs") is not None
    except (ImportError, ValueError):
        return False


_HAS_RUNTIME = _runtime_available()
_needs_runtime = pytest.mark.skipif(
    not _HAS_RUNTIME,
    reason="modules.knowledge.* 不可导入（cookbook-smoke 仅装 SDK）",
)

_COOKBOOK_ROOT = Path(__file__).resolve().parent.parent


# ════════════════════════════════════════════════════════════════════
# §1. main.py helpers
# ════════════════════════════════════════════════════════════════════


def test_validate_learning_path_returns_shape(tmp_path: Path) -> None:
    """空/无本体项目 → 优雅返回 DAG（不抛错）。"""
    rep = cookbook_main._validate_learning_path(tmp_path)
    assert set(rep) >= {"is_dag", "detail", "cycles", "edge_count"}
    assert isinstance(rep["is_dag"], bool)


def test_write_report_renders_markdown(tmp_path: Path) -> None:
    out = tmp_path / "k12_compile_report.md"
    docs = [tmp_path / "a.md", tmp_path / "b.md"]
    cookbook_main._write_report(
        out, tmp_path, docs,
        {"is_dag": True, "detail": "无环（3 节点 / 2 前置边）", "edge_count": 2},
    )
    text = out.read_text(encoding="utf-8")
    assert "学习路径校验" in text
    assert "a.md" in text and "b.md" in text
    assert "是 ✅" in text


# ════════════════════════════════════════════════════════════════════
# §2. sample_data
# ════════════════════════════════════════════════════════════════════


def test_sample_data_has_three_docs() -> None:
    sample = _COOKBOOK_ROOT / "sample_data"
    md = sorted(p.name for p in sample.glob("*.md"))
    assert md == [
        "derivative_application.md",
        "probability_basics.md",
        "solid_geometry.md",
    ]


def test_mock_question_bank_present() -> None:
    # 题库层 mock 数据（与知识资料分目录，避免污染默认知识编译）。
    qb = _COOKBOOK_ROOT / "mock_question_bank" / "derivative_questions.md"
    assert qb.exists(), "mock_question_bank 题库样例缺失"
    text = qb.read_text(encoding="utf-8")
    # 题库层关键概念齐全（题目/解答/步骤/错误模式/考查关系）。
    for kw in ("题目", "解答", "步骤", "ErrorPattern", "变式", "考查知识点"):
        assert kw in text, f"题库样例缺关键概念 {kw}"


# ════════════════════════════════════════════════════════════════════
# §3. 校本包 manifest（继承内置 k12_math）
# ════════════════════════════════════════════════════════════════════


@_needs_runtime
def test_school_pack_yaml_loads_and_inherits() -> None:
    import yaml
    from modules.knowledge.domain_packs import get_registry

    pack_path = _COOKBOOK_ROOT / "k12_school_pack.yaml"
    data = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    assert data["id"] == "k12_school"
    assert data["parent_pack"] == "k12_math"

    reg = get_registry(force_reload=True)
    pid = reg.register_manifest(data, activate=True)
    assert pid == "k12_school"
    kinds = reg.get_allowed_entity_kinds()
    assert "question" in kinds            # 校本追加
    assert "knowledge_point" in kinds     # 继承 k12_math
    rels = reg.get_allowed_relation_kinds()
    assert "tests" in rels                # 校本追加
    assert "prerequisite_of" in rels      # 继承 k12_math


@_needs_runtime
def test_school_pack_field_specs_present() -> None:
    import yaml
    from modules.knowledge.domain_packs import get_registry

    pack_path = _COOKBOOK_ROOT / "k12_school_pack.yaml"
    data = yaml.safe_load(pack_path.read_text(encoding="utf-8"))
    reg = get_registry(force_reload=True)
    reg.register_manifest(data, activate=True)
    edge_specs = reg.get_field_specs("edge")
    assert "tests" in edge_specs
    assert "weight" in edge_specs["tests"]


# ════════════════════════════════════════════════════════════════════
# §4. System 1 K12 评分工具
# ════════════════════════════════════════════════════════════════════


@_needs_runtime
def test_scoring_detects_prerequisite_cycle() -> None:
    from modules.knowledge.k12_scoring import detect_prerequisite_cycles

    dag = detect_prerequisite_cycles([("求导", "判断单调性"), ("判断单调性", "求极值")])
    assert dag.is_dag is True

    cyc = detect_prerequisite_cycles([("A", "B"), ("B", "A")])
    assert cyc.is_dag is False


@_needs_runtime
def test_scoring_normalize_weights_sum_to_one() -> None:
    from modules.knowledge.k12_scoring import normalize_weights

    w = normalize_weights({"k1": 2.0, "k2": 2.0})
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert abs(w["k1"] - 0.5) < 1e-9
