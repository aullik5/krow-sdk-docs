"""Target-nominator cookbook smoke tests（零 LLM，零网络：monkeypatch HTTP）.

覆盖：
- §1 HPA 取数（归一 / 空基因 / 无记录 / 网络错误 fail-loud）
- §2 Open Targets 取数（Ensembl 解析 / tractability / 关联分归一 / 空基因）
- §3 多维加权打分（权重 / 排序 / ungrounded 标记 / 维名同义词 / 值归一 / 空输入）
- §4 ToolPlugin / ACTPlugin Protocol 契约
- §5 TargetNominationIntegrityGate（DEFER / BLOCK 无取数 / BLOCK 全 ungrounded / ALLOW）
"""
from __future__ import annotations

import pytest

import target_nominator_plugin as tn


# ════════════════════════════════════════════════════════════════════════
# §1. HPA 取数
# ════════════════════════════════════════════════════════════════════════


def test_fetch_expression_empty_gene_fail_loud() -> None:
    res = tn.fetch_target_expression("")
    assert res["ok"] is False and "gene 为空" in res["error"]


def test_fetch_expression_normalizes(monkeypatch) -> None:
    def fake_get(url, timeout=30):
        assert "GPNMB" in url
        return [{
            "Gene": "GPNMB",
            "Ensembl": "ENSG00000136235",
            "RNA tissue specific nTPM": "skin: 42.1",
            "RNA single cell type specific nTPM": "melanocytes: high",
            "Pathology prognostics": "melanoma: high expression",
        }]

    monkeypatch.setattr(tn, "_http_get_json", fake_get)
    res = tn.fetch_target_expression("GPNMB")
    assert res["ok"] is True
    assert res["gene"] == "GPNMB"
    assert res["ensembl"] == "ENSG00000136235"
    assert "proteinatlas.org" in res["source"]
    assert "melanoma" in res["tumor_expression"]


def test_fetch_expression_no_record_fail_loud(monkeypatch) -> None:
    monkeypatch.setattr(tn, "_http_get_json", lambda url, timeout=30: [])
    res = tn.fetch_target_expression("NOTAGENE")
    assert res["ok"] is False and "无" in res["error"]


def test_fetch_expression_network_error_fail_loud(monkeypatch) -> None:
    import urllib.error

    def boom(url, timeout=30):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(tn, "_http_get_json", boom)
    res = tn.fetch_target_expression("GPNMB")
    assert res["ok"] is False and "HPA 取数失败" in res["error"]


# ════════════════════════════════════════════════════════════════════════
# §2. Open Targets 取数
# ════════════════════════════════════════════════════════════════════════


def test_fetch_associations_empty_gene_fail_loud() -> None:
    res = tn.fetch_target_associations("")
    assert res["ok"] is False and "gene 为空" in res["error"]


def test_fetch_associations_normalizes(monkeypatch) -> None:
    def fake_post(url, payload, timeout=30):
        variables = payload.get("variables", {})
        # 第一次调是 search 解析 Ensembl；第二次是 target 查询
        if "q" in variables:
            return {"data": {"search": {"hits": [
                {"id": "ENSG00000136235", "entity": "target"}
            ]}}}
        return {"data": {"target": {
            "id": "ENSG00000136235",
            "approvedSymbol": "GPNMB",
            "tractability": [
                {"modality": "AB", "label": "Antibody", "value": True},
                {"modality": "SM", "label": "Small molecule", "value": False},
            ],
            "associatedDiseases": {
                "count": 3,
                "rows": [
                    {"disease": {"name": "melanoma"}, "score": 0.72},
                    {"disease": {"name": "glioblastoma"}, "score": 0.55},
                ],
            },
        }}}

    monkeypatch.setattr(tn, "_http_post_json", fake_post)
    res = tn.fetch_target_associations("GPNMB")
    assert res["ok"] is True
    assert res["ensembl"] == "ENSG00000136235"
    assert res["antibody_tractable"] is True
    assert res["max_association_score"] == pytest.approx(0.72)
    assert "platform.opentargets.org" in res["source"]
    assert len(res["top_diseases"]) == 2


def test_fetch_associations_ensembl_passthrough(monkeypatch) -> None:
    calls = {"post": 0}

    def fake_post(url, payload, timeout=30):
        calls["post"] += 1
        return {"data": {"target": {
            "id": "ENSG00000136235", "approvedSymbol": "GPNMB",
            "tractability": [], "associatedDiseases": {"count": 0, "rows": []},
        }}}

    monkeypatch.setattr(tn, "_http_post_json", fake_post)
    res = tn.fetch_target_associations("ENSG00000136235")
    assert res["ok"] is True
    # 已是 ENSG → 不再走 search 解析，只有 1 次 POST（target 查询）
    assert calls["post"] == 1


# ════════════════════════════════════════════════════════════════════════
# §3. 多维加权打分
# ════════════════════════════════════════════════════════════════════════


def _grounded_scores(cid: str, safety: float, efficacy: float, drug: float, breadth: float):
    return [
        {"candidate_id": cid, "dimension": "safety", "value": safety, "source": "hpa://x"},
        {"candidate_id": cid, "dimension": "efficacy", "value": efficacy, "source": "hpa://x"},
        {"candidate_id": cid, "dimension": "druggability", "value": drug, "source": "ot://x"},
        {"candidate_id": cid, "dimension": "breadth", "value": breadth, "source": "ot://x"},
    ]


def test_score_empty_candidates_fail_loud() -> None:
    assert tn.score_target_candidates([], [{"candidate_id": "a", "dimension": "safety", "value": 1}])["ok"] is False


def test_score_empty_scores_fail_loud() -> None:
    assert tn.score_target_candidates(["GPNMB"], [])["ok"] is False


def test_score_ranks_by_aggregate() -> None:
    cands = ["GPNMB", "MLANA"]
    scores = _grounded_scores("GPNMB", 0.9, 0.9, 0.9, 0.9) + _grounded_scores("MLANA", 0.3, 0.3, 0.2, 0.2)
    res = tn.score_target_candidates(cands, scores)
    assert res["ok"] is True
    assert res["ranking"][0]["name"] == "GPNMB"
    assert res["ranking"][0]["aggregate"] > res["ranking"][1]["aggregate"]
    assert res["ranking"][0]["grounded"] is True
    assert res["any_grounded"] is True


def test_score_flags_ungrounded_key_dim() -> None:
    scores = [
        {"candidate_id": "GPNMB", "dimension": "safety", "value": 0.9},  # 无 source → ungrounded
        {"candidate_id": "GPNMB", "dimension": "efficacy", "value": 0.9, "source": "hpa://x"},
        {"candidate_id": "GPNMB", "dimension": "druggability", "value": 0.8, "source": "ot://x"},
    ]
    res = tn.score_target_candidates(["GPNMB"], scores)
    assert res["ok"] is True
    assert any("ungrounded" in i for i in res["issues"])
    assert res["ranking"][0]["grounded"] is False


def test_score_dimension_synonyms_normalize() -> None:
    scores = [
        {"candidate_id": "GPNMB", "dimension": "安全", "value": "high", "source": "hpa://x"},
        {"candidate_id": "GPNMB", "dimension": "tractability", "value": "strong", "source": "ot://x"},
    ]
    res = tn.score_target_candidates(["GPNMB"], scores)
    assert res["ok"] is True
    dims = set(res["matrix"]["GPNMB"].keys())
    assert "safety" in dims and "druggability" in dims


def test_score_value_normalization_percent_and_words() -> None:
    scores = [
        {"candidate_id": "GPNMB", "dimension": "safety", "value": "80%", "source": "s"},
        {"candidate_id": "GPNMB", "dimension": "efficacy", "value": "high", "source": "s"},
        {"candidate_id": "GPNMB", "dimension": "druggability", "value": 90, "source": "s"},
    ]
    res = tn.score_target_candidates(["GPNMB"], scores)
    m = res["matrix"]["GPNMB"]
    assert m["safety"] == pytest.approx(0.8)
    assert m["efficacy"] == pytest.approx(1.0)
    assert m["druggability"] == pytest.approx(0.9)


def test_score_weights_applied() -> None:
    scores = _grounded_scores("GPNMB", 1.0, 0.0, 0.0, 0.0)
    # safety 权重压满 → 聚合接近 1.0
    res = tn.score_target_candidates(
        ["GPNMB"], scores, weights={"safety": 10, "efficacy": 1, "druggability": 1, "breadth": 1}
    )
    assert res["ranking"][0]["aggregate"] > 0.7


def test_score_flags_missing_key_dimension() -> None:
    # 只给 safety，缺 efficacy/druggability
    scores = [{"candidate_id": "GPNMB", "dimension": "safety", "value": 0.9, "source": "s"}]
    res = tn.score_target_candidates(["GPNMB"], scores)
    assert any("缺关键维" in i for i in res["issues"])


def test_score_emits_data_sources_markdown_verbatim() -> None:
    # 反幻觉硬验收门：打分工具必须回一个可原样粘贴的"## 数据来源"章节（唯一化 url，保序）。
    scores = [
        {"candidate_id": "GPNMB", "dimension": "safety", "value": 0.9,
         "source": "https://www.proteinatlas.org/ENSG00000136235-GPNMB"},
        {"candidate_id": "GPNMB", "dimension": "efficacy", "value": 0.9,
         "source": "https://www.proteinatlas.org/ENSG00000136235-GPNMB"},  # 重复 → 去重
        {"candidate_id": "GPNMB", "dimension": "druggability", "value": 0.8,
         "source": "https://platform.opentargets.org/target/ENSG00000136235"},
    ]
    res = tn.score_target_candidates(["GPNMB"], scores)
    assert res["ok"] is True
    md = res["data_sources_markdown"]
    assert md.startswith("## 数据来源")
    assert "proteinatlas.org" in md
    assert "platform.opentargets.org" in md
    # 去重：proteinatlas url 只出现一次
    assert md.count("https://www.proteinatlas.org/ENSG00000136235-GPNMB") == 1
    assert res["data_sources"] == [
        "https://www.proteinatlas.org/ENSG00000136235-GPNMB",
        "https://platform.opentargets.org/target/ENSG00000136235",
    ]
    # 每候选也带自己的 sources（供逐候选段落引用）
    assert res["ranking"][0]["sources"] == sorted(res["data_sources"])


def test_score_no_source_yields_empty_data_sources() -> None:
    # 全无 source（ungrounded）→ data_sources_markdown 为空串（gate 另拦 conclude）
    scores = [
        {"candidate_id": "GPNMB", "dimension": "safety", "value": 0.9},
        {"candidate_id": "GPNMB", "dimension": "efficacy", "value": 0.9},
    ]
    res = tn.score_target_candidates(["GPNMB"], scores)
    assert res["data_sources"] == []
    assert res["data_sources_markdown"] == ""


# ════════════════════════════════════════════════════════════════════════
# §4. ToolPlugin / ACTPlugin Protocol
# ════════════════════════════════════════════════════════════════════════


def test_tool_plugin_registers_3_tools() -> None:
    names = {t["name"] for t in tn.TargetNominatorToolPlugin().get_tools()}
    assert names == {
        "target_nominator_fetch_expression",
        "target_nominator_fetch_associations",
        "target_nominator_score_candidates",
    }


def test_tool_plugin_id_nonempty() -> None:
    assert tn.TargetNominatorToolPlugin().plugin_id


def test_act_plugin_root_and_manifest_exist() -> None:
    plugin = tn.TargetNominatorACTPlugin()
    assert plugin.get_act_root().is_dir()
    assert (plugin.get_act_root() / "__act__.yaml").is_file()
    assert (plugin.get_act_root() / "ext_target_nominator.md").is_file()


def test_act_plugin_includes_smart_file_write() -> None:
    assert "smart_file_write" in tn.TargetNominatorACTPlugin().get_tool_names()


# ════════════════════════════════════════════════════════════════════════
# §5. TargetNominationIntegrityGate
# ════════════════════════════════════════════════════════════════════════


@pytest.fixture
def verdict():
    from krow_agent_sdk.protocols import GateVerdict
    return GateVerdict


def _score_tr(*, any_grounded: bool, ranking: list) -> dict:
    return {
        "tool_name": "target_nominator_score_candidates",
        "args": {},
        "result": {"ok": True, "any_grounded": any_grounded, "ranking": ranking},
    }


def test_gate_defers_when_no_score(verdict) -> None:
    gate = tn.TargetNominationIntegrityGate().get_gate()
    d = gate.evaluate({}, {"recent_tool_results": []})
    assert d.verdict == verdict.DEFER


def test_gate_blocks_when_no_grounded_fetch(verdict) -> None:
    gate = tn.TargetNominationIntegrityGate().get_gate()
    ctx = {"recent_tool_results": [
        _score_tr(any_grounded=False, ranking=[{"id": "GPNMB", "grounded": False}])
    ]}
    d = gate.evaluate({}, ctx)
    assert d.verdict == verdict.BLOCK
    assert "反编造" in d.reason or "真取数" in d.reason


def test_gate_blocks_when_all_ungrounded(verdict) -> None:
    gate = tn.TargetNominationIntegrityGate().get_gate()
    ctx = {"recent_tool_results": [
        _score_tr(any_grounded=True, ranking=[
            {"id": "GPNMB", "grounded": False}, {"id": "MLANA", "grounded": False},
        ])
    ]}
    d = gate.evaluate({}, ctx)
    assert d.verdict == verdict.BLOCK


def test_gate_allows_when_grounded(verdict) -> None:
    gate = tn.TargetNominationIntegrityGate().get_gate()
    ctx = {"recent_tool_results": [
        _score_tr(any_grounded=True, ranking=[
            {"id": "GPNMB", "grounded": True}, {"id": "MLANA", "grounded": False},
        ])
    ]}
    d = gate.evaluate({}, ctx)
    assert d.verdict == verdict.ALLOW


def test_gate_grounded_via_fetch_result(verdict) -> None:
    """打分 any_grounded=False 但有成功 fetch 带 source → 视为有真取数（不因 flag 漏判 BLOCK）."""
    gate = tn.TargetNominationIntegrityGate().get_gate()
    ctx = {"recent_tool_results": [
        {
            "tool_name": "target_nominator_fetch_expression",
            "result": {"ok": True, "source": "https://www.proteinatlas.org/ENSG00000136235-GPNMB"},
        },
        _score_tr(any_grounded=False, ranking=[{"id": "GPNMB", "grounded": True}]),
    ]}
    d = gate.evaluate({}, ctx)
    assert d.verdict == verdict.ALLOW


# ════════════════════════════════════════════════════════════════════════
# §6. 取数捕获 + System 1 确定性收口（main.py 用；TURBO"数据注入≠数据采用"治本）
# ════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=False)
def _capture_off():
    """每个捕获测试跑完关掉捕获 + 清状态，避免污染其他直调工具的 smoke 测试。"""
    yield
    tn._CAPTURE_ENABLED = False
    tn._CAPTURE["expression"].clear()
    tn._CAPTURE["associations"].clear()
    tn._LAST_SCORE_RESULT = None


def test_capture_disabled_by_default_no_side_effect() -> None:
    # 直调工具（smoke 场景）不应有全局副作用 → 捕获默认关闭
    tn._CAPTURE_ENABLED = False
    tn._LAST_SCORE_RESULT = None
    tn.score_target_candidates(
        ["GPNMB"],
        [{"candidate_id": "GPNMB", "dimension": "safety", "value": 0.9, "source": "s"}],
    )
    assert tn.get_last_score_result() is None


def test_reset_capture_enables_and_clears(_capture_off) -> None:
    tn._LAST_SCORE_RESULT = {"stale": True}
    tn._CAPTURE["expression"]["OLD"] = {"ok": True}
    tn.reset_capture()
    assert tn.get_last_score_result() is None
    assert tn.get_capture()["expression"] == {}


def test_capture_collects_score_and_data_sources(monkeypatch, _capture_off) -> None:
    tn.reset_capture()
    scores = [
        {"candidate_id": "GPNMB", "dimension": "safety", "value": 0.9,
         "source": "https://www.proteinatlas.org/ENSG00000136235-GPNMB"},
        {"candidate_id": "GPNMB", "dimension": "druggability", "value": 0.8,
         "source": "https://platform.opentargets.org/target/ENSG00000136235"},
    ]
    res = tn.score_target_candidates(["GPNMB"], scores)
    assert tn.get_last_score_result() is res
    urls = tn.collect_data_sources()
    assert urls == [
        "https://www.proteinatlas.org/ENSG00000136235-GPNMB",
        "https://platform.opentargets.org/target/ENSG00000136235",
    ]
    md = tn.build_data_sources_markdown()
    assert md.startswith("## 数据来源")
    assert "proteinatlas.org" in md and "platform.opentargets.org" in md


def test_collect_data_sources_falls_back_to_fetch_capture(monkeypatch, _capture_off) -> None:
    # LLM 打分时漏填 source（scores 无 source）→ 但真调过取数工具 → url 仍从 fetch 捕获兜回
    tn.reset_capture()
    monkeypatch.setattr(tn, "_http_get_json", lambda url, timeout=30: [{
        "Gene": "GPNMB", "Ensembl": "ENSG00000136235",
        "RNA tissue specific nTPM": "skin: 42.1",
    }])
    tn.fetch_target_expression("GPNMB")
    # 打分全无 source
    tn.score_target_candidates(
        ["GPNMB"],
        [{"candidate_id": "GPNMB", "dimension": "safety", "value": 0.9}],
    )
    urls = tn.collect_data_sources()
    assert any("proteinatlas.org" in u for u in urls)
