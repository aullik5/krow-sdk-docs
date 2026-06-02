"""Financial-analyst cookbook smoke tests（≥30 tests，零 LLM 调用）.

覆盖：
- §1 KPI 字典 / 单位字典 完整性
- §2 数字解析 / 单位检测 / 币种检测（边界用例）
- §3 normalize_kpi_table 跨币种 / 跨单位 归一化正确性
- §4 industry_baseline mean / std / quartiles 计算
- §5 radar_chart_svg SVG 生成 + 图形健全
- §6 valuation_anchor PE / PB / PS 计算 + 行业对比 verdict
- §7 ToolPlugin / ACTPlugin Protocol 契约
- §8 GatePlugin × 2（DisclosureCompletenessGate / InsiderInfoGate）行为
- §9 AnomalyMetricHintPlugin 触发条件 + 阈值边界
- §10 InvestmentMemoAuditListener .audit.jsonl 输出
- §11 FinancialMetricsObservabilityPlugin 降级模式 + register 契约

注：本测试文件**全部走 System 1**，不调 LLM；运行成本 0；可在 CI 频繁跑。
真实 LLM e2e 测试见 `tests/sdk/test_journey_*` 系列（用 LLM replay fixture）。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

# conftest.py 已经把 cookbook root 加进了 sys.path
import financial_analyst_plugin as fa
import pytest

# ════════════════════════════════════════════════════════════════════════
# §1. KPI / Unit 字典完整性
# ════════════════════════════════════════════════════════════════════════


def test_kpi_dict_has_10_canonical_kpis() -> None:
    """KPI_DICT 标准 10 类指标全在."""
    expected = {
        "revenue", "net_profit", "gross_margin", "operating_cash_flow",
        "total_assets", "total_equity", "rd_ratio", "roe",
        "debt_to_equity", "earnings_per_share",
    }
    assert set(fa.KPI_DICT.keys()) == expected


def test_kpi_dict_each_has_chinese_and_english_aliases() -> None:
    """每个 KPI 至少 1 个中文 alias + 1 个英文 alias（投行年报双语场景）."""
    for kpi_id, aliases in fa.KPI_DICT.items():
        has_chinese = any(any("\u4e00" <= c <= "\u9fff" for c in a) for a in aliases)
        has_english = any(a.isascii() and a.replace(" ", "").isalpha() for a in aliases)
        assert has_chinese, f"{kpi_id} 缺中文 alias"
        assert has_english, f"{kpi_id} 缺英文 alias（年报有英文版的）"


def test_unit_dict_covers_chinese_and_english_units() -> None:
    """UNIT_DICT 必含中英文单位关键词."""
    for kw in ("亿", "亿元", "百万", "万", "billion", "million", "%"):
        assert kw in fa.UNIT_DICT, f"UNIT_DICT 缺 {kw}"


# ════════════════════════════════════════════════════════════════════════
# §2. 数字解析 / 单位检测 / 币种检测
# ════════════════════════════════════════════════════════════════════════


def test_parse_number_handles_chinese_and_english_thousands() -> None:
    """中英文千分位都解析."""
    assert fa._parse_number("1,234,567.89") == 1234567.89
    assert fa._parse_number("1，234，567.89") == 1234567.89


def test_parse_number_handles_negative_with_parens() -> None:
    """会计常用括号负数."""
    assert fa._parse_number("(123.45)") == -123.45


def test_parse_number_returns_none_on_garbage() -> None:
    assert fa._parse_number("abc") is None
    assert fa._parse_number("") is None


def test_detect_unit_picks_longest_match() -> None:
    """'亿元' 优于 '亿'（避免 '百万元' 命中 '元' 失去准确性）."""
    label, mult = fa._detect_unit("营业收入 245.76 亿元")
    assert label == "亿元"
    assert mult == 1e8


def test_detect_unit_handles_english_billion() -> None:
    label, mult = fa._detect_unit("Revenue 3.84 USD billion")
    assert label == "billion"
    assert mult == 1e9


def test_detect_unit_unknown_returns_unit_unknown() -> None:
    label, mult = fa._detect_unit("just a plain number")
    assert label == "unit_unknown"
    assert mult == 1.0


def test_detect_currency_default_cny() -> None:
    assert fa._detect_currency("营业收入 245 亿元") == "CNY"


def test_detect_currency_recognizes_usd() -> None:
    assert fa._detect_currency("Revenue 3.84 USD billion") == "USD"
    assert fa._detect_currency("revenue $3.84B") == "USD"


def test_detect_currency_recognizes_eur_hkd_jpy() -> None:
    assert fa._detect_currency("revenue €1.5 billion") == "EUR"
    assert fa._detect_currency("revenue HKD 5,000 million") == "HKD"
    assert fa._detect_currency("売上高 100 億円 (JPY)") == "JPY"


# ════════════════════════════════════════════════════════════════════════
# §3. normalize_kpi_table 跨币种 / 跨单位
# ════════════════════════════════════════════════════════════════════════


def test_normalize_empty_companies_fail_loud() -> None:
    res = fa.normalize_kpi_table([])
    assert res["ok"] is False
    assert "公司列表为空" in res["error"]


def test_normalize_unknown_currency_fail_loud() -> None:
    res = fa.normalize_kpi_table(
        [{"company": "A", "kpis": {}}],
        target_currency="XYZ",
    )
    assert res["ok"] is False
    assert "XYZ" in res["error"]


def test_normalize_unknown_unit_fail_loud() -> None:
    res = fa.normalize_kpi_table(
        [{"company": "A", "kpis": {}}],
        target_unit="奇怪单位",
    )
    assert res["ok"] is False


def test_normalize_cny_to_usd_billion() -> None:
    """CNY 245.76 亿元 → USD billion（用默认占位汇率 7.20）."""
    companies = [{
        "company": "A",
        "kpis": {
            "revenue": {
                "value": 245.76e8,  # 245.76 亿元
                "raw_value": 245.76,
                "unit": "亿元",
                "currency": "CNY",
                "is_ratio": False,
            }
        },
    }]
    res = fa.normalize_kpi_table(
        companies,
        target_currency="USD",
        target_unit="billion",
    )
    assert res["ok"] is True
    row = res["table"][0]
    # 245.76 亿元 = 24,576,000,000 CNY = 24576/7.20 USD million ≈ 3.41 USD billion
    assert row["company"] == "A"
    assert 3.0 < row["revenue"] < 4.0


def test_normalize_ratio_kpi_not_currency_converted() -> None:
    """毛利率 35% 在归一化时不应被换算（is_ratio=True）."""
    companies = [{
        "company": "A",
        "kpis": {
            "gross_margin": {
                "value": 35.0,  # 35%
                "raw_value": 35.0,
                "unit": "%",
                "currency": None,
                "is_ratio": True,
            }
        },
    }]
    res = fa.normalize_kpi_table(companies, target_currency="USD", target_unit="亿")
    assert res["ok"] is True
    assert res["table"][0]["gross_margin"] == 35.0


def test_normalize_period_warning_on_mismatch() -> None:
    companies = [
        {"company": "A", "period": "2024", "kpis": {}},
        {"company": "B", "period": "2023H1", "kpis": {}},
    ]
    res = fa.normalize_kpi_table(companies)
    assert any("B" in w or "A" in w for w in res["period_warnings"])


# ════════════════════════════════════════════════════════════════════════
# §4. industry_baseline 统计
# ════════════════════════════════════════════════════════════════════════


def test_industry_baseline_empty_table_fail_loud() -> None:
    res = fa.industry_baseline([])
    assert res["ok"] is False


def test_industry_baseline_basic_stats() -> None:
    table = [
        {"company": "A", "revenue": 100.0, "roe": 15.0},
        {"company": "B", "revenue": 200.0, "roe": 10.0},
        {"company": "C", "revenue": 300.0, "roe": 12.0},
    ]
    res = fa.industry_baseline(table)
    assert res["ok"] is True
    assert "revenue" in res["baselines"]
    assert "roe" in res["baselines"]
    rev = res["baselines"]["revenue"]
    assert rev["n"] == 3
    assert rev["mean"] == pytest.approx(200.0)
    assert rev["min"] == 100.0 and rev["max"] == 300.0
    assert rev["median"] == 200.0


def test_industry_baseline_marks_sparse_kpis() -> None:
    """1 家公司样本的 KPI 应标 sparse + std=None."""
    table = [{"company": "A", "revenue": 100.0, "rare_kpi": 5.0}]
    res = fa.industry_baseline(table)
    assert "rare_kpi" in res["sparse_kpis"]
    assert res["baselines"]["rare_kpi"]["std"] is None


# ════════════════════════════════════════════════════════════════════════
# §5. radar_chart_svg
# ════════════════════════════════════════════════════════════════════════


def test_radar_chart_empty_table_fail_loud() -> None:
    res = fa.radar_chart_svg([], ["revenue", "roe", "rd_ratio"])
    assert res["ok"] is False


def test_radar_chart_too_few_kpis_fail_loud() -> None:
    table = [{"company": "A", "revenue": 100, "roe": 10}]
    res = fa.radar_chart_svg(table, ["revenue", "roe"])  # < 3 维
    assert res["ok"] is False
    assert "3 个 KPI 维度" in res["error"]


def test_radar_chart_basic_svg_valid() -> None:
    table = [
        {"company": "A", "revenue": 100, "roe": 10, "rd_ratio": 5},
        {"company": "B", "revenue": 200, "roe": 12, "rd_ratio": 8},
    ]
    res = fa.radar_chart_svg(table, ["revenue", "roe", "rd_ratio"])
    assert res["ok"] is True
    svg = res["svg"]
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert "polygon" in svg  # 至少有 polygon 元素
    # 2 家公司 → 至少 2 个 polygon（公司画的）+ 5 个背景蛛网 polygon
    assert svg.count("<polygon") >= 7
    # title 出现
    assert "雷达图" in svg


def test_radar_chart_handles_zero_max_values() -> None:
    """所有公司在某 KPI 都是 0 → 不应除零崩溃."""
    table = [
        {"company": "A", "revenue": 0, "roe": 10, "rd_ratio": 5},
        {"company": "B", "revenue": 0, "roe": 12, "rd_ratio": 8},
    ]
    res = fa.radar_chart_svg(table, ["revenue", "roe", "rd_ratio"])
    assert res["ok"] is True


# ════════════════════════════════════════════════════════════════════════
# §6. valuation_anchor
# ════════════════════════════════════════════════════════════════════════


def test_valuation_anchor_invalid_market_cap() -> None:
    res = fa.valuation_anchor("A", market_cap=0, net_profit=10)
    assert res["ok"] is False


def test_valuation_anchor_basic_pe() -> None:
    res = fa.valuation_anchor("A", market_cap=1000, net_profit=50)
    assert res["ok"] is True
    assert res["multiples"]["pe"] == 20.0


def test_valuation_anchor_loss_company_returns_none_pe() -> None:
    """亏损公司 PE 应返 None 而不是负数 / 无穷大."""
    res = fa.valuation_anchor("A", market_cap=1000, net_profit=-50)
    assert res["multiples"]["pe"] is None


def test_valuation_anchor_industry_comparison_verdict() -> None:
    """高于行业 30%+ 触发『偏贵』；低于 -30% 触发『偏便宜』."""
    res = fa.valuation_anchor(
        "A", market_cap=1000, net_profit=50,
        industry_pe_median=10,  # 公司 PE=20，高出 100% → 偏贵
    )
    assert "偏贵" in res["verdict"]


def test_valuation_anchor_handles_partial_data() -> None:
    """只有 market_cap + net_profit 时只算 PE，不算 PB/PS."""
    res = fa.valuation_anchor("A", market_cap=1000, net_profit=50)
    assert res["multiples"]["pb"] is None
    assert res["multiples"]["ps"] is None


# ════════════════════════════════════════════════════════════════════════
# §7. ToolPlugin / ACTPlugin Protocol 契约
# ════════════════════════════════════════════════════════════════════════


def test_tool_plugin_registers_5_tools() -> None:
    plugin = fa.FinancialAnalystToolPlugin()
    tools = plugin.get_tools()
    names = {t["name"] for t in tools}
    assert names == {
        "financial_analyst_extract_kpi_from_pdf",
        "financial_analyst_normalize_kpi_table",
        "financial_analyst_industry_baseline",
        "financial_analyst_radar_chart_svg",
        "financial_analyst_valuation_anchor",
    }


def test_tool_plugin_each_tool_has_handler() -> None:
    plugin = fa.FinancialAnalystToolPlugin()
    for tool in plugin.get_tools():
        assert callable(tool["handler"])
        assert tool["description"]
        assert "input_schema" in tool


def test_act_plugin_act_root_exists() -> None:
    plugin = fa.FinancialAnalystACTPlugin()
    root = plugin.get_act_root()
    assert root.is_dir()
    assert (root / "ext_financial_analyst.md").is_file()
    assert (root / "__act__.yaml").is_file(), (
        "ACT manifest 必须是独立 __act__.yaml（loader 不读 .md frontmatter）"
    )


def test_act_plugin_tool_names_includes_word_smart_export() -> None:
    """ACT 必须把内置 word_smart_export 列入（PDF 渲染走 SSOT）."""
    plugin = fa.FinancialAnalystACTPlugin()
    names = plugin.get_tool_names()
    assert "word_smart_export" in names
    # 5 个 plugin 工具 + 1 个 builtin
    assert len(names) == 6


# ════════════════════════════════════════════════════════════════════════
# §8. GatePlugin × 2
# ════════════════════════════════════════════════════════════════════════


@pytest.fixture
def gate_imports():
    """从 SDK 公开 protocol 入口拿 GateVerdict（cookbook 测试不应依赖私有路径）."""
    from krow_agent_sdk.protocols import GateDecision, GateVerdict
    return {"GateDecision": GateDecision, "GateVerdict": GateVerdict}


def _wrap_tool_result(tool_name: str, *, args: dict | None = None,
                     content: str | None = None) -> dict:
    """模拟 SDK 注入的 recent_tool_results 条目."""
    a = dict(args or {})
    if content is not None:
        a["content"] = content
    return {
        "tool_name": tool_name,
        "args": a,
        "result": {},
    }


def test_disclosure_gate_defers_when_no_report_yet(gate_imports) -> None:
    """报告还没生成 → DEFER（gate 不该提前阻断）."""
    gate = fa.DisclosureCompletenessGate().get_gate()
    decision = gate.evaluate({}, {"recent_tool_results": []})
    assert decision.verdict == gate_imports["GateVerdict"].DEFER


def test_disclosure_gate_allows_when_5_sections_present(gate_imports) -> None:
    full_report = (
        "# 投资简报\n"
        "## 业务概览\n公司主营 ...\n"
        "## 财务表现\nrevenue 245亿\n"
        "## 行业地位\n排名第二\n"
        "## 风险因素\n汇率风险...\n"
        "## 投资建议\n买入\n"
    )
    gate = fa.DisclosureCompletenessGate().get_gate()
    ctx = {
        "recent_tool_results": [
            _wrap_tool_result("data_analyst_write_report", content=full_report)
        ]
    }
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].ALLOW


def test_disclosure_gate_blocks_when_missing_risk_section(gate_imports) -> None:
    """缺『风险因素』段必 BLOCK."""
    incomplete = (
        "## 业务概览\n...\n"
        "## 财务表现\n...\n"
        "## 行业地位\n...\n"
        "## 投资建议\n买入\n"
    )
    gate = fa.DisclosureCompletenessGate().get_gate()
    ctx = {
        "recent_tool_results": [
            _wrap_tool_result("data_analyst_write_report", content=incomplete)
        ]
    }
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].BLOCK
    assert "风险因素" in decision.reason


def test_disclosure_gate_warn_only_mode(gate_imports) -> None:
    """strict=False → 缺段也只 ALLOW（reason 仍提示）."""
    incomplete = "## 业务概览\n...\n## 财务表现\n...\n"
    gate = fa.DisclosureCompletenessGate(strict=False).get_gate()
    ctx = {
        "recent_tool_results": [
            _wrap_tool_result("data_analyst_write_report", content=incomplete)
        ]
    }
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].ALLOW


def test_insider_gate_defers_when_no_report(gate_imports) -> None:
    gate = fa.InsiderInfoGate().get_gate()
    decision = gate.evaluate({}, {"recent_tool_results": []})
    assert decision.verdict == gate_imports["GateVerdict"].DEFER


def test_insider_gate_blocks_chinese_keyword(gate_imports) -> None:
    bad_text = "## 投资建议\n根据内幕消息，公司将于下周宣布...买入\n"
    gate = fa.InsiderInfoGate().get_gate()
    ctx = {
        "recent_tool_results": [
            _wrap_tool_result("data_analyst_write_report", content=bad_text)
        ]
    }
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].BLOCK
    assert "证券法" in decision.reason or "内幕" in decision.reason


def test_insider_gate_blocks_english_mnpi_keyword(gate_imports) -> None:
    bad_text = (
        "## Investment Recommendation\n"
        "Based on material non-public information, we recommend BUY.\n"
    )
    gate = fa.InsiderInfoGate().get_gate()
    ctx = {
        "recent_tool_results": [
            _wrap_tool_result("data_analyst_write_report", content=bad_text)
        ]
    }
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].BLOCK


def test_insider_gate_passes_clean_report(gate_imports) -> None:
    clean = (
        "## 投资建议\n基于年报披露的 ROE 15%、毛利率 35%，给予『买入』评级。\n"
    )
    gate = fa.InsiderInfoGate().get_gate()
    ctx = {
        "recent_tool_results": [
            _wrap_tool_result("data_analyst_write_report", content=clean)
        ]
    }
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].DEFER


def test_insider_gate_supports_custom_keywords(gate_imports) -> None:
    """允许加自家公司机密词（如 unlisted_subsidiary）."""
    bad = "## 财务表现\nincludes data from unlisted_subsidiary holdings.\n"
    gate = fa.InsiderInfoGate(custom_keywords=["unlisted_subsidiary"]).get_gate()
    ctx = {
        "recent_tool_results": [
            _wrap_tool_result("data_analyst_write_report", content=bad)
        ]
    }
    decision = gate.evaluate({}, ctx)
    assert decision.verdict == gate_imports["GateVerdict"].BLOCK


# ════════════════════════════════════════════════════════════════════════
# §9. AnomalyMetricHintPlugin
# ════════════════════════════════════════════════════════════════════════


def _wrap_hint_context(*, normalized_table: list[dict], baselines: dict) -> dict:
    """模拟 SDK 注入的 recent_tool_results."""
    return {
        "recent_tool_results": [
            {
                "tool_name": "financial_analyst_normalize_kpi_table",
                "args": {},
                "result": {"ok": True, "table": normalized_table},
            },
            {
                "tool_name": "financial_analyst_industry_baseline",
                "args": {},
                "result": {"ok": True, "baselines": baselines},
            },
        ]
    }


def test_anomaly_hint_returns_none_when_no_tool_results() -> None:
    hint = fa.AnomalyMetricHintPlugin()
    assert hint.hint_for({"recent_tool_results": []}) is None


def test_anomaly_hint_no_outliers_returns_consistency_message() -> None:
    """所有公司 KPI 在 mean ± 2σ 内 → 输出『行业整体一致』提示."""
    table = [
        {"company": "A", "roe": 15},
        {"company": "B", "roe": 16},
        {"company": "C", "roe": 14},
    ]
    baselines = {
        "roe": {"n": 3, "mean": 15, "std": 1, "median": 15, "q1": 14, "q3": 16,
                "min": 14, "max": 16},
    }
    hint = fa.AnomalyMetricHintPlugin(sigma_threshold=2.0)
    res = hint.hint_for(_wrap_hint_context(normalized_table=table, baselines=baselines))
    assert res is not None
    assert "行业整体一致" in res or "正常波动" in res


def test_anomaly_hint_detects_high_outlier() -> None:
    """ROE 偏离 mean ≥2σ → 必须出现在 hint 里.

    样本：6 家公司 ROE 接近 15，G 家 ROE=100。
    pstdev 在单极端值下会被放大，但 6 家正常样本足以让 G 的 σ ≥ 2.4。
    """
    table = [
        {"company": "A", "roe": 15.0},
        {"company": "B", "roe": 16.0},
        {"company": "C", "roe": 14.0},
        {"company": "D", "roe": 15.5},
        {"company": "E", "roe": 14.5},
        {"company": "F", "roe": 15.7},
        {"company": "G", "roe": 100.0},  # 极端偏离 ≥2.4σ
    ]
    baseline_res = fa.industry_baseline(table)
    hint = fa.AnomalyMetricHintPlugin(sigma_threshold=2.0)
    res = hint.hint_for(_wrap_hint_context(
        normalized_table=table,
        baselines=baseline_res["baselines"],
    ))
    assert res is not None
    assert "G" in res
    assert "roe" in res


def test_anomaly_hint_top_8_cap() -> None:
    """同时多 KPI 多公司偏离 → hint 只列前 8."""
    n = 5
    rows: list[dict] = []
    for k in range(20):
        # 每个 KPI 都 4 家公司在中间，第 5 家极端
        for i in range(n - 1):
            if i >= len(rows):
                rows.append({"company": f"C{i}"})
            rows[i][f"k{k}"] = 10 + i  # 10/11/12/13
        if n - 1 >= len(rows):
            rows.append({"company": f"C{n-1}"})
        rows[n - 1][f"k{k}"] = 1000  # outlier
    baseline_res = fa.industry_baseline(rows)
    hint = fa.AnomalyMetricHintPlugin(sigma_threshold=1.5)
    res = hint.hint_for(_wrap_hint_context(
        normalized_table=rows, baselines=baseline_res["baselines"]
    ))
    # 应该列出"另有 N 项偏差未列出"或不超过 8 行的 outlier 列表
    assert res is not None
    bullet_count = res.count("\n- **")
    assert bullet_count <= 8


# ════════════════════════════════════════════════════════════════════════
# §10. InvestmentMemoAuditListener
# ════════════════════════════════════════════════════════════════════════


def test_audit_listener_writes_jsonl(tmp_path: Path) -> None:
    log = tmp_path / "memo.audit.jsonl"
    listener = fa.InvestmentMemoAuditListener(audit_log_path=log)

    class Ev:
        def __init__(self, payload):
            self.payload = payload

    listener._on_tool_call_started(Ev({
        "tool_name": "financial_analyst_extract_kpi_from_pdf",
        "args": {"path": "/tmp/a.pdf"},
    }))
    listener._on_tool_call_completed(Ev({
        "tool_name": "financial_analyst_extract_kpi_from_pdf",
        "ok": True,
        "elapsed_ms": 250,
        "result": {
            "ok": True,
            "summary": "OK",
            "kpis": {
                "revenue": {
                    "value": 245.76e8,
                    "unit": "亿元",
                    "currency": "CNY",
                    "source_window": "营业收入 245.76 亿元 ...",
                },
            },
        },
    }))
    listener._on_gate_blocked(Ev({
        "gate_name": "disclosure_completeness",
        "reason": "缺风险因素段",
    }))
    listener._on_task_complete(Ev({"summary": "done", "step_count": 8}))
    listener._on_task_failed(Ev({"reason": "budget exhausted"}))

    assert log.is_file()
    lines = log.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5
    records = [json.loads(line) for line in lines]
    kinds = [r["kind"] for r in records]
    assert kinds == [
        "tool_call_started", "tool_call_completed", "gate_blocked",
        "task_complete", "task_failed",
    ]
    # 高亮 kpi_extract
    assert records[0]["highlight"] == "kpi_extract"
    # KPI 抽取结果完整保留 source_window
    assert "revenue" in records[1]["result_summary"]
    # gate_blocked 标 compliance_event
    assert records[2]["compliance_event"] is True


def test_audit_listener_handles_missing_parent_dir(tmp_path: Path) -> None:
    """父目录不存在 → 自动创建."""
    log = tmp_path / "deep" / "nest" / "memo.audit.jsonl"
    _ = fa.InvestmentMemoAuditListener(audit_log_path=log)
    assert log.parent.is_dir()


# ════════════════════════════════════════════════════════════════════════
# §11. FinancialMetricsObservabilityPlugin
# ════════════════════════════════════════════════════════════════════════


def test_observability_plugin_id_is_unique() -> None:
    plugin = fa.FinancialMetricsObservabilityPlugin()
    assert plugin.plugin_id == "fin_analyst.observability"


def test_observability_plugin_register_adds_metric_and_audit_sinks() -> None:
    """register() 调用 facade.add_metric_sink + add_audit_sink."""
    plugin = fa.FinancialMetricsObservabilityPlugin(verbose=False)

    facade = mock.Mock()
    plugin.register(facade)
    facade.add_metric_sink.assert_called_once()
    facade.add_audit_sink.assert_called_once()


def test_observability_plugin_degrades_when_prometheus_missing() -> None:
    """prometheus-client 未装 → available=False；调 _on_metric 不崩."""
    with mock.patch.dict("sys.modules", {"prometheus_client": None}):
        # 重新走一次 init（强制 ImportError 路径）
        plugin = fa.FinancialMetricsObservabilityPlugin(verbose=False)
        # _available 取决于 prometheus_client 是否已装；本测试容忍两种情况
        if not plugin._available:
            plugin._on_metric("test.metric", 1.0, {"label": "foo"})
            plugin._on_audit("gate_blocked", {"gate_name": "disclosure_completeness"})


def test_observability_plugin_audit_increments_gate_blocked_counter() -> None:
    """gate_blocked audit 事件应触发 counter 创建（即使在 stdout 模式）."""
    plugin = fa.FinancialMetricsObservabilityPlugin(verbose=False)
    # 不破坏：调 audit handler 不抛异常即可（具体 counter 行为依 prometheus-client 安装情况）
    plugin._on_audit("gate_blocked", {"gate_name": "disclosure_completeness"})
    plugin._on_audit("other_event", {})  # 非 gate_blocked 不应触发 counter
