"""extract_kpi_from_pdf alias 歧义消解 bug 回归测试.

事故复盘
========

W5 真实 LLM E2E（2026-05-19）首次启用 ``numeric_grounding`` 维度后暴露
``financial-analyst`` cookbook 的**致命 bug**：

  - 输入合成年报 PDF 写明 ``Net Profit: 15.3 亿元`` + ``净利润率维持 11.9%``
  - ``extract_kpi_from_pdf`` 抽出 ``net_profit = 11.9 亿元``（应为 15.3）
  - 根因：alias 列表含 ``"净利润"``，被 ``"净利润率"`` 的子串命中
  - 后果：LLM 拿到错值，整篇投资简报内的 KPI 数字全错

这是**确定性 bug**（按 AGENTS.md §4.2.1）— 单步复现、单文件修复.

修复方案（最小 diff）
====================

在 ``extract_kpi_from_pdf::alias 匹配``加"后置语义过滤"：

  1. alias 列表内部按长度降序排（更长 = 更具体；"归属于母公司股东净利润"
     优先于"净利润"）
  2. 找到 alias 命中后，检查 alias **后紧跟**的字符是否是会改变 KPI 语义的
     修饰词（如 ``率`` / ``比`` / ``ratio`` / ``margin``）；
     - 若紧跟修饰词且当前 KPI 不是 ratio 类型 → 跳过该位置，继续搜下一个
       alias 命中
  3. 防御性：检查 alias 命中后窗口里的"%"是否在数字紧后 ≤ 5 字符内；
     是 + 当前 KPI 不是 ratio 类型 → 该数字大概率是 ratio 误命中，跳过.

这套规则是 System 1 deterministic，零 LLM；防 LLM 拿到错值后**无论怎么写
报告都会偏离用户真实意图**.

为什么不用 LLM-as-extractor 替代
================================

- KPI 抽取必须 deterministic（同一 PDF 同一输入 → 同一输出，不能漂移）
- LLM 抽取按 token 计费、慢 + 不稳；System 1 查表 + regex 是正解
- 与主仓 ``modules/agent/progressive/tool_traits.py:CONTENT_SOURCE`` 哲学一致
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_COOKBOOK_ROOT = Path(__file__).resolve().parents[1]
if str(_COOKBOOK_ROOT) not in sys.path:
    sys.path.insert(0, str(_COOKBOOK_ROOT))

# Cookbook root for _journey_e2e_helpers
_COOKBOOK_ROOT_PARENT = _COOKBOOK_ROOT.parent
if str(_COOKBOOK_ROOT_PARENT) not in sys.path:
    sys.path.insert(0, str(_COOKBOOK_ROOT_PARENT))

from financial_analyst_plugin import extract_kpi_from_pdf, normalize_kpi_table  # noqa: E402

from _journey_e2e_helpers import synthesize_annual_report_pdf  # noqa: E402


@pytest.fixture
def synth_pdf(tmp_path: Path):
    """合成 W5 实测出 bug 的同款年报：含"净利润率"会误命中 alias "净利润"."""
    return synthesize_annual_report_pdf(
        company="Skyline Tech Corp",
        revenue_yi=128.6,
        net_profit_yi=15.3,
        gross_margin_pct=42.5,
        roe_pct=18.1,
        debt_to_equity=0.32,
        out_path=tmp_path / "skyline.pdf",
    )


# ════════════════════════════════════════════════════════════════════════
# §1. 核心回归：净利润 alias 不能被"净利润率"误命中
# ════════════════════════════════════════════════════════════════════════


def test_net_profit_not_hijacked_by_net_profit_ratio(synth_pdf):
    """W5 实测 bug：net_profit 应为 15.3，不是"净利润率 11.9%"里的 11.9.

    回归保护：任何修改 ``extract_kpi_from_pdf::alias 匹配``的 PR 都
    必须先过这条断言.
    """
    res = extract_kpi_from_pdf(str(synth_pdf), company_name="Skyline")
    assert res["ok"], res
    assert "net_profit" in res["kpis"], (
        f"net_profit 必须能抽出；实抽：{list(res['kpis'])}"
    )
    raw = res["kpis"]["net_profit"]["raw_value"]
    assert abs(raw - 15.3) < 0.5, (
        f"❌ net_profit raw_value={raw} 偏离输入 15.3 太远！\n"
        f"  极可能是 alias '净利润' 被 '净利润率' 误命中.\n"
        f"  修法：在 ``extract_kpi_from_pdf`` 的 alias 匹配后置过滤"
        f" '率/比/ratio/margin'."
    )


def test_revenue_grounded_to_input(synth_pdf):
    """revenue raw_value 必须 = 128.6（合成 PDF 输入）."""
    res = extract_kpi_from_pdf(str(synth_pdf), company_name="Skyline")
    assert "revenue" in res["kpis"]
    assert abs(res["kpis"]["revenue"]["raw_value"] - 128.6) < 1.0


def test_normalized_table_grounded(synth_pdf):
    """normalize 后的表必须含原值（防 unit detection 走偏）."""
    res = extract_kpi_from_pdf(str(synth_pdf), company_name="Skyline")
    n = normalize_kpi_table([{"company": "Skyline", "kpis": res["kpis"]}])
    assert n["ok"], n
    row = n["table"][0]
    # ratio 类型应为原始百分比值（W5 实测 _detect_unit 把 "ROE 18.1%" 后的
    # "million" 当单位 — 但 is_ratio=True 不应受 mult 影响）
    if row.get("gross_margin") is not None:
        assert abs(row["gross_margin"] - 42.5) < 1.0, (
            f"gross_margin = {row['gross_margin']}，应 ≈ 42.5"
        )
    if row.get("roe") is not None:
        assert abs(row["roe"] - 18.1) < 1.0, (
            f"roe = {row['roe']}，应 ≈ 18.1"
        )
    if row.get("revenue") is not None:
        assert abs(row["revenue"] - 128.6) < 5.0
    if row.get("net_profit") is not None:
        assert abs(row["net_profit"] - 15.3) < 1.0, (
            f"net_profit = {row['net_profit']}，应 ≈ 15.3 — alias 歧义 bug"
        )


# ════════════════════════════════════════════════════════════════════════
# §2. 防御性：unit 字段不能被 "million" 误覆盖（gross_margin/roe 类）
# ════════════════════════════════════════════════════════════════════════


def test_ratio_kpi_unit_label_not_million(synth_pdf):
    """ratio 类 KPI（gross_margin/roe）的 unit 字段不应为 'million'.

    实测 bug：``_detect_unit`` 在窗口里看到英文 "(Return on Equity)" 附近的
    "million" 当作 unit. 虽然 ``is_ratio=True`` 时 multiplier 不被使用，
    但给 LLM 的字段标签错了会误导.
    """
    res = extract_kpi_from_pdf(str(synth_pdf), company_name="Skyline")
    if "gross_margin" in res["kpis"]:
        unit = res["kpis"]["gross_margin"].get("unit", "").lower()
        assert "million" not in unit, (
            f"gross_margin.unit = {unit!r}（应为 '%' / 空 / 'percent'）—— "
            f"_detect_unit 错把窗口内的 'million' 当单位"
        )
    if "roe" in res["kpis"]:
        unit = res["kpis"]["roe"].get("unit", "").lower()
        assert "million" not in unit, (
            f"roe.unit = {unit!r}（应为 '%' / 空 / 'percent'）"
        )


# ════════════════════════════════════════════════════════════════════════
# §3. 直接 alias 子串测试（无需 PDF）
# ════════════════════════════════════════════════════════════════════════


def test_alias_disambiguation_mini():
    """直接给 ``extract_kpi_from_pdf`` 喂"含子串歧义"的合成 PDF.

    更长更具体的 alias（''归属于母公司股东净利润''）应该优先于短 alias（''净利润''）.
    """
    # CI 上无 reportlab → 没法合成 PDF，与同文件其他测试一致 skip.
    pytest.importorskip(
        "reportlab",
        reason="reportlab 未装。pip install krow-agent-sdk[office]",
    )
    # 注意：``_scan_pdf_text`` 要求文本 ≥ 200 字符；填充足够内容
    pdf_path = _make_minimal_pdf(
        text=(
            "Section 1: Annual Performance Overview\n"
            "  归属于母公司股东净利润：23.7 亿元（同比增长 18.5%）\n"
            "  净利润率维持 11.9%（行业中位 9.2%）\n"
            "  营业收入：256.8 亿元，毛利率 38.2%\n"
            "  Section 2: Industry Position\n"
            "  公司在云计算行业排名 Top 5，市场份额 12.3%\n"
            "  ROE 22.5%，资产负债率 35.6%\n"
            "  Section 3: Risk Factors\n"
            "  原材料价格波动、汇率风险、监管政策变化、宏观经济下行风险\n"
        )
    )
    res = extract_kpi_from_pdf(pdf_path, company_name="Test")
    assert res.get("ok"), f"extract failed: {res}"
    assert "net_profit" in res["kpis"], (
        f"net_profit 必须能抽出；实抽：{list(res.get('kpis', {}))}"
    )
    raw = res["kpis"]["net_profit"]["raw_value"]
    assert abs(raw - 23.7) < 0.5, (
        f"net_profit raw_value = {raw}（应 ≈ 23.7）"
        f"——alias '归属于母公司股东净利润' 应优先于 '净利润'"
    )


def _make_minimal_pdf(text: str) -> str:
    """生成只含给定文本的迷你 PDF（用于单测，不依赖 _journey_e2e_helpers 合成器）."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    out = Path(tempfile.mkdtemp()) / "mini.pdf"
    c = canvas.Canvas(str(out), pagesize=(595, 842))
    c.setFont("STSong-Light", 12)
    y = 800
    for line in text.splitlines():
        c.drawString(60, y, line)
        y -= 20
    c.save()
    return str(out)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
