"""Cookbook 真实 LLM E2E 通用 helper.

设计要点
========

1. **零外部依赖（除 reportlab + yaml）**：reportlab 已经在 SDK ``office`` extras
   里。任何 cookbook 用 ``pip install -e .[obs]`` 装完都能直接用。
2. **小而合成**：合成 PDF 只够 LLM 把"年报 / 文献 / 合同"三类工件认出来；目的是
   走通管线、验工具被调用 / Gate 工作 / 产物落盘，不是验内容质量。
3. **多维断言**（与主仓 ``tests/e2e_real/_journey_runner.py`` 风格一致）：
   - ``status``：``RunResult.success``
   - ``artifacts``：必须存在的文件清单（按 expected card）
   - ``budget``：``llm_calls <= max_total_llm_calls``、wall <= ``max_walltime_s``
   - ``forbidden_keywords``：关键禁词（如 "MNPI"，对应 InsiderInfoGate）
   - ``required_sections``：产物 markdown 必须含的段落标题（DisclosureCompletenessGate）
4. **跳过策略**：``KROW_API_KEY`` 未设 → ``pytest.skip``；CI 上无 key 直接 skip，
   本地或 nightly 走真实路径。

使用模板（每个 cookbook 内 ``tests/test_<id>_journey_e2e.py``）
================================================================

```python
from cookbook._journey_e2e_helpers import (
    require_real_llm,
    synthesize_annual_report_pdf,
    run_journey,
    assert_journey,
)

@require_real_llm
def test_financial_analyst_tier1_journey(tmp_path):
    pdf = synthesize_annual_report_pdf(
        company="Skyline Tech",
        revenue_yi=12.3,
        net_profit_yi=2.5,
        out_path=tmp_path / "skyline_2024.pdf",
    )
    result = run_journey(
        cookbook_dir="financial-analyst",
        argv=[str(pdf), "--no-valuation", "--quiet"],
    )
    assert_journey(
        result,
        expected_card="financial_analyst_tier1.yaml",
        artifacts_root=tmp_path / "output",
    )
```
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

# ════════════════════════════════════════════════════════════════════════
# 跳过装饰器
# ════════════════════════════════════════════════════════════════════════
require_real_llm = pytest.mark.skipif(
    not os.environ.get("KROW_API_KEY", "").strip(),
    reason=(
        "real-LLM E2E：未设 KROW_API_KEY。本地跑前 export KROW_API_KEY=pk-pilot-xxx。"
    ),
)


# ════════════════════════════════════════════════════════════════════════
# Lazy yaml import（W4 fix · 2026-05-19）
# ════════════════════════════════════════════════════════════════════════
# 顶层 ``import yaml`` 会让 cookbook ``[test]`` extras 没声明 PyYAML 时 pytest
# collection 阶段崩溃（``ModuleNotFoundError: No module named 'yaml'``），即便
# 测试本身被 ``@require_real_llm`` skip 也无济于事（collect 在 skip 之前）。
# 改 lazy 后：无 KROW_API_KEY → require_real_llm skip → 不调 ``load_expected_card``
# → 不 import yaml → CI smoke matrix（无 PyYAML）能 collect 通过.
def _ensure_yaml() -> Any:
    """Lazy import PyYAML；缺则 fail-loud + 友好错误提示."""
    try:
        import yaml  # noqa: WPS433
    except ImportError as exc:
        raise RuntimeError(
            "❌ Cookbook E2E 需要 PyYAML 来读 expected_cards/*.yaml；当前未装。\n"
            "你可以：\n"
            "  1) `pip install PyYAML>=6.0`\n"
            "  2) 装 cookbook test extras：`pip install -e .[test]`\n"
            "  3) 见 docs/sdk/cookbook-e2e-results.md §1 SOP"
        ) from exc
    return yaml


# ════════════════════════════════════════════════════════════════════════
# §1. 合成 PDF 生成器（reportlab，最小可识别）
# ════════════════════════════════════════════════════════════════════════


def _ensure_reportlab() -> Any:
    try:
        from reportlab.pdfgen import canvas as _canvas
        return _canvas
    except ImportError as exc:  # pragma: no cover
        raise pytest.skip.Exception(
            "reportlab 未装。pip install krow-agent-sdk[office] 或 pip install reportlab。"
        ) from exc


_CHINESE_FONT_NAME = "STSong-Light"


def _register_chinese_font() -> str:
    """注册 reportlab 自带中文 CID 字体；返回字体名。

    W4 fix（2026-05-19）：之前用 Helvetica → 中文渲染为空白方块 → pdfplumber
    抽出空文本 → LLM "基于空数据生成"。改用 reportlab 自带 CID STSong-Light（不
    需要外部 .ttf 文件，跨平台稳定）。
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    if _CHINESE_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(_CHINESE_FONT_NAME))
    return _CHINESE_FONT_NAME


def synthesize_annual_report_pdf(
    *,
    company: str,
    revenue_yi: float,
    net_profit_yi: float,
    gross_margin_pct: float = 38.5,
    roe_pct: float = 15.2,
    debt_to_equity: float = 0.45,
    out_path: Path,
) -> Path:
    """合成最简年报 PDF（financial-analyst 用）.

    含 KPI 关键词：营业收入 / 净利润 / 毛利率 / ROE / 资产负债率，单位"亿元 / %"。
    LLM + financial_analyst_extract_kpi_from_pdf 可识别。
    """
    canvas = _ensure_reportlab()
    font = _register_chinese_font()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=(595, 842))  # A4
    c.setFont(font, 14)
    c.drawString(60, 800, f"{company} - 2024 Annual Report")
    c.setFont(font, 10)
    body = [
        "Section 1: Business Overview",
        f"  Revenue (Total Revenue):  {revenue_yi} 亿元 ({revenue_yi*100} million CNY)",
        f"  Net Profit (Net Income):  {net_profit_yi} 亿元",
        f"  Gross Margin:             {gross_margin_pct}%",
        f"  ROE (Return on Equity):   {roe_pct}%",
        f"  Debt-to-Equity Ratio:     {debt_to_equity}",
        "",
        "Section 2: Industry Position",
        f"  {company} 主营业务为电子制造、智能硬件、消费品。",
        f"  2024 年营收 {revenue_yi} 亿元，同比增长 12.3%。",
        "",
        "Section 3: Risk Factors",
        "  原材料价格波动、汇率风险、监管政策变化。",
        "",
        "Section 4: Outlook",
        f"  预计 2025 年营收增长 8-10%，净利润率维持 {round(net_profit_yi/revenue_yi*100,1)}%。",
    ]
    y = 770
    for line in body:
        c.drawString(60, y, line)
        y -= 16
        if y < 60:
            c.showPage()
            c.setFont(font, 10)
            y = 800
    c.save()
    return out_path


def synthesize_research_paper_pdf(
    *,
    title: str,
    authors: list[str],
    abstract: str,
    keywords: list[str],
    out_path: Path,
) -> Path:
    """合成最简学术论文 PDF（literature-reviewer 用）."""
    canvas = _ensure_reportlab()
    font = _register_chinese_font()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=(595, 842))
    c.setFont(font, 12)
    c.drawString(60, 800, title[:80])
    c.setFont(font, 10)
    body = [
        "Authors: " + ", ".join(authors),
        "Keywords: " + ", ".join(keywords),
        "",
        "Abstract:",
    ]
    body.extend(_wrap_text(abstract, width=80))
    body.extend([
        "",
        "1. Introduction",
        f"  This paper studies {keywords[0] if keywords else 'the topic'}.",
        "  Recent advances [1, 2] show progress in this domain.",
        "",
        "2. Methodology",
        "  We propose a novel framework integrating signals from various sources.",
        "  Equation 1: y = f(x; θ) where θ is learned.",
        "",
        "3. Results",
        "  Table 1: Accuracy on benchmark XYZ = 92.5% (sota +1.3%).",
        "",
        "References:",
        "  [1] Smith et al., ICLR 2023.",
        "  [2] Liu and Zhang, NeurIPS 2022.",
    ])
    y = 770
    for line in body:
        c.drawString(60, y, line[:90])
        y -= 14
        if y < 60:
            c.showPage()
            c.setFont(font, 10)
            y = 800
    c.save()
    return out_path


def synthesize_contract_pdf(
    *,
    title: str,
    parties: tuple[str, str],
    contract_value_cny: int,
    out_path: Path,
    include_unbalanced_liability: bool = True,
    include_no_termination_clause: bool = False,
) -> Path:
    """合成最简商业合同 PDF（contract-auditor 用）.

    可控开关：
      ``include_unbalanced_liability=True`` → 触发 "甲方免责" 风险条款
      ``include_no_termination_clause=True`` → 缺合同终止条款
    """
    canvas = _ensure_reportlab()
    font = _register_chinese_font()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_path), pagesize=(595, 842))
    c.setFont(font, 12)
    c.drawString(60, 800, title[:80])
    c.setFont(font, 10)
    body = [
        "甲方：" + parties[0],
        "乙方：" + parties[1],
        "",
        "第一条 标的与价款",
        f"  合同总金额：人民币 {contract_value_cny:,} 元（CNY）。",
        "  支付方式：合同签订后 7 日内支付 30%，验收合格后支付 70%。",
        "",
        "第二条 交付与验收",
        "  乙方应于合同生效之日起 60 日内交付。",
        "  甲方应于交付后 15 日内书面验收。",
        "",
        "第三条 违约责任",
    ]
    if include_unbalanced_liability:
        body.extend([
            "  乙方逾期交付的，每日按合同总金额 0.5% 支付违约金；累计超过 30 日，",
            "  甲方有权解除合同并要求 30% 违约金。",
            "  甲方免责条款：甲方逾期付款的，免除违约责任，乙方不得主张。",
        ])
    else:
        body.extend([
            "  任一方违约的，按合同总金额 0.5% / 日支付违约金。",
            "  累计超过 30 日，对方有权解除合同并要求 30% 违约金。",
        ])
    if not include_no_termination_clause:
        body.extend([
            "",
            "第四条 合同解除",
            "  双方协商一致可解除本合同。",
            "  任一方根本性违约的，对方有权单方解除并要求赔偿。",
        ])
    body.extend([
        "",
        "第五条 保密义务",
        "  双方应对在履行合同过程中知悉的对方商业秘密承担保密义务，期限 5 年。",
        "",
        "第六条 争议解决",
        "  本合同适用中华人民共和国法律。争议提交北京仲裁委员会仲裁。",
    ])
    y = 770
    for line in body:
        c.drawString(60, y, line[:90])
        y -= 14
        if y < 60:
            c.showPage()
            c.setFont(font, 10)
            y = 800
    c.save()
    return out_path


def _wrap_text(text: str, width: int = 80) -> list[str]:
    out = []
    cur = []
    cur_len = 0
    for word in text.split():
        if cur_len + len(word) + 1 > width and cur:
            out.append(" ".join(cur))
            cur = [word]
            cur_len = len(word)
        else:
            cur.append(word)
            cur_len += len(word) + 1
    if cur:
        out.append(" ".join(cur))
    return out


# ════════════════════════════════════════════════════════════════════════
# §2. Journey 跑器（直接调 cookbook main.py）
# ════════════════════════════════════════════════════════════════════════


@dataclass
class JourneyResult:
    """journey 跑结果（与主仓 ``RunResult`` 风格对齐，cookbook 简化版）."""

    cookbook: str
    exit_code: int
    walltime_s: float
    output_dir: Path
    stdout: str
    stderr: str
    artifacts: dict[str, Path] = field(default_factory=dict)


def run_journey(
    *,
    cookbook_dir: str,
    argv: list[str],
    cwd: Path | None = None,
    timeout_s: int = 1200,
) -> JourneyResult:
    """通用 cookbook journey 跑器（subprocess 隔离）.

    ``cookbook_dir``：cookbook 目录名（如 ``financial-analyst``）.
    ``argv``：传给 cookbook ``main.py`` 的 CLI 参数（如 ``["sample.pdf", "--quiet"]``）.
    ``cwd``：默认为 cookbook 目录本身.
    """
    cookbook_root = Path(__file__).parent / cookbook_dir
    if not cookbook_root.exists():
        raise FileNotFoundError(f"cookbook 不存在：{cookbook_root}")
    cwd = cwd or cookbook_root

    cmd = [sys.executable, str(cookbook_root / "main.py"), *argv]
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        env={**os.environ},
    )
    walltime = time.time() - started

    output_dir = _resolve_output_dir(argv, cwd)
    artifacts: dict[str, Path] = {}
    if output_dir and output_dir.exists():
        for f in output_dir.iterdir():
            if f.is_file():
                artifacts[f.name] = f

    return JourneyResult(
        cookbook=cookbook_dir,
        exit_code=proc.returncode,
        walltime_s=walltime,
        output_dir=output_dir,
        stdout=proc.stdout,
        stderr=proc.stderr,
        artifacts=artifacts,
    )


def _resolve_output_dir(argv: list[str], cwd: Path) -> Path:
    """从 CLI args 提取 ``--output-dir``（cookbook 默认 ``output``）."""
    out = "output"
    for i, a in enumerate(argv):
        if a == "--output-dir" and i + 1 < len(argv):
            out = argv[i + 1]
            break
    p = Path(out)
    return (cwd / p) if not p.is_absolute() else p


# ════════════════════════════════════════════════════════════════════════
# §3. 多维断言（按 expected card YAML）
# ════════════════════════════════════════════════════════════════════════


def load_expected_card(card_name: str, *, cookbook_dir: str) -> dict[str, Any]:
    """从 cookbook ``tests/expected_cards/<card_name>`` 读 yaml."""
    yaml = _ensure_yaml()
    cookbook_root = Path(__file__).parent / cookbook_dir
    card_path = cookbook_root / "tests" / "expected_cards" / card_name
    if not card_path.exists():
        raise FileNotFoundError(f"expected card 不存在：{card_path}")
    return yaml.safe_load(card_path.read_text(encoding="utf-8")) or {}


def assert_journey(result: JourneyResult, *, card: dict[str, Any]) -> None:
    """按预期结果卡多维断言.

    Card schema 已有维度（System 1 · 功能可用性）:
      ``exit_code``: int (默认 0)
      ``max_walltime_s``: float (硬上限)
      ``required_artifacts``: list[str] (产物文件名)
      ``required_keywords_in``: dict[str, list[str|list[str]]] (产物 -> 必含关键词；list 内 list = OR alternatives)
      ``forbidden_keywords_in``: dict[str, list[str]] (产物 -> 禁词)
      ``required_sections_in``: dict[str, list[str|list[str]]] (markdown 必含 section 标题；OR alternatives)
      ``min_artifact_bytes``: dict[str, int] (产物最小字节，过滤空文件)

    Card schema 新增维度（W5 · 用户价值导向 · System 1 严守）:
      ``numeric_grounding``: dict[str, list[NumericRef]]
        防 LLM 幻觉/编造数字 — 报告里关键数值必须能在原始数据中找到对应数字.
        ``NumericRef`` schema: ``{"value": float, "tolerance": float (默认 0.01),
        "format_alts": list[str] (可选额外字符串变体，如 "128.6 亿元" / "128.6亿")}``.
        匹配策略：value × (1 ± tolerance) 浮点等价 + format_alts 任一字面匹配.

      ``markdown_structure``: dict[str, dict]
        防 LLM 重复输出 bug + 强制结构化报告. 子字段:
          ``min_h2_sections``: int (markdown ## 标题至少 N 个)
          ``no_duplicate_h2``: bool (默认 false；true 时禁止重复 H2 标题)
          ``min_bullet_items``: int (`- ` / `* ` 起头的列表项至少 N 个)

      ``must_address``: dict[str, list[QuestionRef]]
        强制报告必须回答用户的核心决策问题（每条 QuestionRef 任一 keyword 命中即通过）.
        ``QuestionRef`` schema: ``{"question": str (描述用), "any_keywords": list[str]}``.
        例：投资简报必须给出明确动作 → ``{"question": "投资建议",
        "any_keywords": ["买入", "卖出", "持有", "观望"]}``.

      ``max_repeated_paragraphs``: dict[str, int]
        相同段落（≥ 80 字符）的最大允许重复次数. 0 = 严格禁止任何重复.
        防 financial-analyst Tier 1 实测发现的"投资建议（结论）段重复输出" bug.

    设计哲学（与主仓 ``tests/e2e_real/_journey_runner.py`` 对齐）:
      - **System 1 严守**：所有新维度都是文本 / regex / markdown 结构解析，零 LLM 调用.
      - **不发明 LLM-as-judge 二级判官**（DRY · 主仓 _journey_runner.py:1089 同样原则）.
      - **OCP**：新字段全部 default None / 空，老 expected_card 不修即工作.
      - **fail-loud**：错误信息含具体 missing keyword + 字段名 + 1 行修法.
    """
    expected_exit = card.get("exit_code", 0)
    assert result.exit_code == expected_exit, (
        f"[{result.cookbook}] exit_code {result.exit_code} != {expected_exit}\n"
        f"stdout:\n{result.stdout[-2000:]}\n"
        f"stderr:\n{result.stderr[-2000:]}"
    )

    max_wall = card.get("max_walltime_s")
    if max_wall is not None:
        assert result.walltime_s <= max_wall, (
            f"[{result.cookbook}] walltime {result.walltime_s:.1f}s > {max_wall}s"
        )

    for required in card.get("required_artifacts", []):
        assert required in result.artifacts, (
            f"[{result.cookbook}] 缺产物 {required}；现有 {list(result.artifacts)}"
        )

    for fname, min_bytes in (card.get("min_artifact_bytes") or {}).items():
        if fname in result.artifacts:
            actual = result.artifacts[fname].stat().st_size
            assert actual >= min_bytes, (
                f"[{result.cookbook}] {fname} 太小 {actual}B < {min_bytes}B"
            )

    for fname, keywords in (card.get("required_keywords_in") or {}).items():
        if fname not in result.artifacts:
            continue
        text = _read_artifact_text(result.artifacts[fname])
        missing: list[str] = []
        for entry in keywords:
            if isinstance(entry, str):
                if entry not in text:
                    missing.append(entry)
            elif isinstance(entry, list):
                if not any(alt in text for alt in entry):
                    missing.append(" | ".join(entry))
            else:
                raise AssertionError(
                    f"[{result.cookbook}] required_keywords_in 元素类型错: {type(entry).__name__}\n"
                    "  支持：str（单关键词）或 list[str]（OR alternatives）"
                )
        assert not missing, (
            f"[{result.cookbook}] {fname} 缺关键词 {missing}"
        )

    for fname, forbidden in (card.get("forbidden_keywords_in") or {}).items():
        if fname not in result.artifacts:
            continue
        text = _read_artifact_text(result.artifacts[fname])
        hit = [k for k in forbidden if k in text]
        assert not hit, (
            f"[{result.cookbook}] {fname} 含禁词 {hit}（Gate 应阻断或 LLM 应避免）"
        )

    for fname, sections in (card.get("required_sections_in") or {}).items():
        if fname not in result.artifacts:
            continue
        text = _read_artifact_text(result.artifacts[fname])
        missing: list[str] = []
        for entry in sections:
            if isinstance(entry, str):
                if entry not in text:
                    missing.append(entry)
            elif isinstance(entry, list):
                if not any(alt in text for alt in entry):
                    missing.append(" | ".join(entry))
            else:
                raise AssertionError(
                    f"[{result.cookbook}] required_sections_in 元素类型错: {type(entry).__name__}\n"
                    "  支持：str（单关键词）或 list[str]（OR alternatives）"
                )
        assert not missing, (
            f"[{result.cookbook}] {fname} 缺章节 {missing}"
        )

    # ════════════════════════════════════════════════════════════════════
    # W5 新增维度（用户价值导向 · 全 System 1 严守）
    # ════════════════════════════════════════════════════════════════════

    for fname, refs in (card.get("numeric_grounding") or {}).items():
        if fname not in result.artifacts:
            continue
        text = _read_artifact_text(result.artifacts[fname])
        missing_nums: list[str] = []
        for entry in refs:
            if not isinstance(entry, dict) or "value" not in entry:
                raise AssertionError(
                    f"[{result.cookbook}] numeric_grounding 元素必须是 dict 且含 'value' 字段;"
                    f" got {entry!r}"
                )
            value = float(entry["value"])
            tolerance = float(entry.get("tolerance", 0.01))
            format_alts = entry.get("format_alts") or []
            if _check_numeric_grounded(text, value, tolerance, format_alts):
                continue
            missing_nums.append(
                f"value={value} (±{tolerance:.2%})"
                + (f" alts={format_alts}" if format_alts else "")
            )
        assert not missing_nums, (
            f"[{result.cookbook}] {fname} numeric_grounding 失败：报告未含原始数据中的数字\n"
            f"  缺：{missing_nums}\n"
            f"  这通常表明 LLM 编造了数字 / 没正确调 KPI 抽取工具 / 工具产出未传给写报告 step"
        )

    for fname, struct in (card.get("markdown_structure") or {}).items():
        if fname not in result.artifacts:
            continue
        if not isinstance(struct, dict):
            raise AssertionError(
                f"[{result.cookbook}] markdown_structure[{fname}] 必须是 dict;"
                f" got {type(struct).__name__}"
            )
        text = _read_artifact_text(result.artifacts[fname])
        h2_lines = [
            ln.strip() for ln in text.splitlines()
            if ln.strip().startswith("## ") and not ln.strip().startswith("### ")
        ]
        min_h2 = struct.get("min_h2_sections")
        if min_h2 is not None:
            assert len(h2_lines) >= min_h2, (
                f"[{result.cookbook}] {fname} markdown_structure.min_h2_sections "
                f"= {min_h2}, 实际 {len(h2_lines)} 个 H2\n"
                f"  实有 H2：{h2_lines}\n"
                f"  这通常表明报告未结构化分章节，用户难以 skim"
            )
        if struct.get("no_duplicate_h2"):
            seen: dict[str, int] = {}
            for h in h2_lines:
                seen[h] = seen.get(h, 0) + 1
            dups = {h: c for h, c in seen.items() if c > 1}
            assert not dups, (
                f"[{result.cookbook}] {fname} markdown_structure.no_duplicate_h2 失败：\n"
                f"  重复 H2：{dups}\n"
                f"  这是 LLM 重复输出 bug（同一段落写多次）；用户体验灾难."
            )
        min_bullet = struct.get("min_bullet_items")
        if min_bullet is not None:
            bullets = [
                ln for ln in text.splitlines()
                if ln.lstrip().startswith(("- ", "* ", "+ "))
            ]
            assert len(bullets) >= min_bullet, (
                f"[{result.cookbook}] {fname} markdown_structure.min_bullet_items "
                f"= {min_bullet}, 实际 {len(bullets)} 条列表项\n"
                f"  报告缺可执行建议清单 — 用户拿到报告但不知道要做什么."
            )

    for fname, questions in (card.get("must_address") or {}).items():
        if fname not in result.artifacts:
            continue
        text = _read_artifact_text(result.artifacts[fname])
        unaddressed: list[str] = []
        for entry in questions:
            if not isinstance(entry, dict) or "any_keywords" not in entry:
                raise AssertionError(
                    f"[{result.cookbook}] must_address 元素必须是"
                    f" dict 且含 'any_keywords' 字段; got {entry!r}"
                )
            keywords = entry["any_keywords"]
            if not isinstance(keywords, list) or not keywords:
                raise AssertionError(
                    f"[{result.cookbook}] must_address.any_keywords 必须非空 list[str]"
                )
            if not any(kw in text for kw in keywords):
                qname = entry.get("question", "<unnamed>")
                unaddressed.append(f"{qname} ({keywords})")
        assert not unaddressed, (
            f"[{result.cookbook}] {fname} must_address 失败：报告未回答用户核心问题\n"
            f"  未答覆：{unaddressed}\n"
            f"  这表明 LLM 写完报告但未给出明确的行动建议 / 决策结论."
        )

    for fname, max_dup in (card.get("max_repeated_paragraphs") or {}).items():
        if fname not in result.artifacts:
            continue
        text = _read_artifact_text(result.artifacts[fname])
        para_counts: dict[str, int] = {}
        # 60 字符阈值：中文里 ~30 字（半段长句），过短的 bullet 不应被算重复.
        _MIN_PARA_LEN = 60
        for raw_para in text.split("\n\n"):
            para = raw_para.strip()
            if len(para) < _MIN_PARA_LEN:
                continue
            para_counts[para] = para_counts.get(para, 0) + 1
        # ``c`` = 出现总次数；``c - 1`` = 重复次数. ``max_dup=0`` → 不允许任何重复（c<=1）.
        repeated = {p[:100] + "...": c for p, c in para_counts.items() if c - 1 > max_dup}
        assert not repeated, (
            f"[{result.cookbook}] {fname} max_repeated_paragraphs={max_dup} 失败：\n"
            f"  含重复段落 {len(repeated)} 处\n"
            f"  样例：{list(repeated.items())[:2]}\n"
            f"  这是 LLM 重复输出 bug（write_artifact 追加而非覆盖；或 verify_completion 后又 write 一次）."
        )


def _check_numeric_grounded(
    text: str, value: float, tolerance: float, format_alts: list[str]
) -> bool:
    """检查 ``value`` 是否以任一形式出现在 ``text`` 中.

    匹配策略（任一命中即通过 — System 1 严守，零 LLM）:
      1. format_alts 任一 substring 命中（如 "128.6亿元" / "12,860,000,000"）
      2. 抽 ``text`` 中所有数字（含千分位 / 百分号 / 小数），与 value × (1 ± tolerance) 等价

    设计取舍（与主仓 ``_check_field_type`` 同样的 syntax-only 哲学）:
      - 不做 LLM 推断"这个数字是不是你想要的"语义判断
      - 不做单位换算（亿 vs 万 由调用方在 ``format_alts`` 里写明）
      - 单纯 fuzzy 浮点匹配 + 字面匹配
    """
    for alt in format_alts:
        if alt and alt in text:
            return True

    pattern = re.compile(r"-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?")
    found_numbers: list[float] = []
    for m in pattern.finditer(text):
        s = m.group(0).replace(",", "")
        try:
            found_numbers.append(float(s))
        except ValueError:
            continue

    if value == 0:
        return any(abs(n) <= max(tolerance, 1e-9) for n in found_numbers)
    abs_tol = abs(value * tolerance)
    return any(abs(n - value) <= abs_tol for n in found_numbers)


def _read_artifact_text(p: Path) -> str:
    if p.suffix.lower() in {".md", ".txt", ".jsonl", ".json", ".yaml", ".yml", ".svg"}:
        try:
            return p.read_text(encoding="utf-8")
        except Exception:
            return ""
    return ""


# ════════════════════════════════════════════════════════════════════════
# §4. Audit log 解析（EventListenerPlugin 留痕检查）
# ════════════════════════════════════════════════════════════════════════


def parse_audit_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def assert_audit_event_types(audit: list[dict[str, Any]], expected_types: set[str]) -> None:
    actual = {e.get("event_type") or e.get("type") or "" for e in audit}
    missing = expected_types - actual
    assert not missing, f"audit 缺事件类型 {missing}；实有 {actual}"


__all__ = [
    "require_real_llm",
    "synthesize_annual_report_pdf",
    "synthesize_research_paper_pdf",
    "synthesize_contract_pdf",
    "JourneyResult",
    "run_journey",
    "load_expected_card",
    "assert_journey",
    "parse_audit_jsonl",
    "assert_audit_event_types",
]
