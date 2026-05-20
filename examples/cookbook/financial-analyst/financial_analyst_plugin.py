"""Financial-analyst cookbook plugin SSOT.

> Cookbook v3 第 1 个 demo（设计依据：``COOKBOOK_DESIGN.md`` §2.1）。

业务场景：投行 / 私募 / 咨询的 junior analyst 每周做一次"行业横向对比 +
投资简报"——读 3-5 家上市公司年报 → 抽 KPI → 跨公司归一化 → 雷达图 +
对比表 → 写投资简报（≥5 段，含合规披露）。

本文件 SSOT 5 个 ToolPlugin 实现 + 2 个 GatePlugin（合规硬阻）+ 1 个
HintPlugin（3σ 异常 KPI 提示）+ 1 个 EventListenerPlugin（投资简报审计
留痕）+ 1 个 ObservabilityPlugin（Prometheus push gateway 集成）+
1 个 ACTPlugin（让 LLM 自动选入此 ACT）。

设计原则（与 ``AGENTS.md`` §0.1 TURBO 哲学 + §0.2 架构原则对齐）：

1. **System 1 vs System 2 严格区分**
   - 工具：纯 deterministic 算法（KPI 同口径归一化 / 雷达图几何计算 /
     行业基线统计）—— LLM 凭感觉算 ROE 会出事故
   - LLM：业务叙事 / 投资逻辑 / 风险定性 —— 让 LLM 在 ACT 流程内组织

2. **每个 plugin 都有具体业务理由**（不是为了凑齐 plugin 类型）
   - GatePlugin 守住的不是"理论合规"——是真实的金融行业法律红线
   - HintPlugin 推的不是"任意建议"——是 LLM 算不出的统计偏差信号
   - ObservabilityPlugin 不是 hello-world 演示——是投行内 BI 真实接入需求

3. **SSOT 复用** Krow 内置工具
   - 投资简报 PDF 输出 → ``word_smart_export``（reportlab + CJK 字体）
   - 雷达图 / 柱状图 → 不引第三方依赖；用 SVG 文本字符串（LLM 友好；
     可被 word_smart_export 以图片形式嵌入）

4. **TURBO 不混做**
   - 工具内绝不调 LLM（CI 红线）
   - hint 不教 LLM 算行业均值（系统能算的不让 LLM 凭感觉）

参考：
- ``packages/krow-agent-sdk/examples/cookbook/data-analyst/data_analyst_plugin.py``
  v2 data-analyst 同等结构（5 类 plugin + Budget）。
- ``COOKBOOK_DESIGN.md`` §3 plugin 覆盖矩阵。
"""
from __future__ import annotations

import json
import logging
import math
import re
import statistics
import time
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# §0. 通用工具（黄金错误模板 + 路径归一化）
# ============================================================


def _normalize_path(p: str | Path) -> Path:
    if isinstance(p, str):
        p = Path(p)
    return p.expanduser().resolve()


def _golden_error(
    msg: str, *, where: str, fixes: Iterable[str], related: Iterable[str] = ()
) -> dict[str, Any]:
    parts = [f"❌ {msg}", f"   位置：{where}", "   修法："]
    for i, fix in enumerate(fixes, 1):
        parts.append(f"     {i}. {fix}")
    if related:
        parts.append(f"   相关：{' / '.join(related)}")
    return {"ok": False, "error": "\n".join(parts)}


# ============================================================
# §1. KPI 抽取（PDF 年报 → 结构化 KPI）
# ============================================================
#
# 真实业务问题：
#   年报 PDF 里"营业收入" / "Revenue" / "营收" 都指同一指标但格式各异；
#   单位写法五花八门（"亿元" / "RMB Million" / "百万" / "亿"）；
#   要做横向对比必须先归一到同一单位 + 同一币种 + 同一指标编码。
#
# System 1 vs System 2 边界：
#   - System 1（本工具）：从年报 PDF/XBRL 用 regex + 关键词字典抽 KPI 数值；
#     单位识别 + 币种识别 + 指标 ID 映射全部走查表（KPI_DICT / UNIT_DICT）
#   - System 2（LLM）：业务解读 / 趋势分析 / 投资建议
#
# 为什么不让 LLM 直接抽 KPI？
#   1. KPI 名称对齐错就全盘错：LLM 可能把"营业总收入"和"营业收入"当一回事；
#      实际两者在 IFRS 下口径差 5-15%
#   2. 单位串错就掉一个数量级：LLM 把"24,576 百万"和"24,576 亿"看成等值
#      → 错 100 倍 → 投行报告事故
#   3. 抽 KPI 是确定性工作：同一份年报，跑 100 次结果应一致；
#      LLM 抽会有 1-3% 漂移率（不可接受）

# 标准 KPI 字典：把不同公司年报里的术语映射到统一指标 ID
# 参考：CSRC 上市公司财务报告披露规则 + IFRS / US GAAP 标准术语
KPI_DICT: dict[str, list[str]] = {
    "revenue": [
        "营业收入", "营业总收入", "总营收", "主营业务收入", "营收",
        "revenue", "total revenue", "net revenue", "net sales", "turnover",
    ],
    "net_profit": [
        "净利润", "归属于上市公司股东的净利润", "归母净利润", "归属母公司股东净利润",
        "net profit", "net income", "profit attributable", "net earnings",
    ],
    "gross_margin": [
        "毛利率", "销售毛利率",
        "gross margin", "gross profit margin",
    ],
    "operating_cash_flow": [
        "经营活动产生的现金流量净额", "经营性现金流", "经营现金流",
        "operating cash flow", "cash from operations", "cfo",
    ],
    "total_assets": [
        "总资产", "资产总计", "资产总额",
        "total assets",
    ],
    "total_equity": [
        "股东权益", "所有者权益", "归属于母公司股东权益合计",
        "total equity", "shareholders equity", "stockholders equity",
    ],
    "rd_ratio": [
        "研发投入占营业收入比例", "研发费用率", "研发投入比",
        "r&d ratio", "rd intensity", "research and development ratio",
    ],
    "roe": [
        "净资产收益率", "加权平均净资产收益率", "ROE",
        "return on equity",
    ],
    "debt_to_equity": [
        "资产负债率", "负债权益比",
        "debt to equity", "leverage ratio", "d/e",
    ],
    "earnings_per_share": [
        "每股收益", "基本每股收益", "EPS",
        "earnings per share",
    ],
}

# 单位归一化字典
UNIT_DICT = {
    "亿元": 1e8, "亿": 1e8, "亿人民币": 1e8,
    "百万元": 1e6, "百万": 1e6, "百万人民币": 1e6,
    "万元": 1e4, "万": 1e4,
    "元": 1.0,
    "billion": 1e9, "bn": 1e9,
    "million": 1e6, "mn": 1e6, "mm": 1e6,
    "thousand": 1e3, "k": 1e3,
    "%": 0.01,  # 百分比
    "percent": 0.01,
}


def _scan_pdf_text(path: Path) -> str:
    """从 PDF 抽出全文文本（小工具；不用 LLM）.

    Returns:
        full text or empty string on failure.
    """
    try:
        import pdfplumber
    except ImportError:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text
        except ImportError:
            return ""
    try:
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        logger.warning("pdfplumber 抽 %s 失败：%s", path, e)
        return ""


_NUMBER_PATTERN = re.compile(
    r"([-+]?\d{1,3}(?:[,，]\d{3})*(?:\.\d+)?|\d+\.?\d*)"
)


def _parse_number(s: str) -> float | None:
    """字符串 → float。识别中文/英文千分位、负号 / 括号负数。"""
    s = s.strip().replace("，", ",").replace(" ", "")
    if not s:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]
    s = s.replace(",", "")
    try:
        n = float(s)
        return -n if negative else n
    except ValueError:
        return None


def _detect_unit(window: str) -> tuple[str, float]:
    """在 KPI 数字前后窗口里找单位关键词，返回 (unit_label, multiplier).

    长度优先策略（与 ``_detect_unit_nearest`` 互补）:
      - 适用场景：``narrow_unit_window`` 只含数字紧后字符，单位在前列
      - 排序按 unit 长度降序 → "百万元"(3) 优先于 "百万"(2) 优先于 "亿"(1)
        防止 "亿" 短匹配吃掉 "亿元" / "百万人民币" 的歧义
    """
    w = window.lower()
    for unit, mult in sorted(UNIT_DICT.items(), key=lambda x: -len(x[0])):
        if unit.lower() in w:
            return unit, mult
    return "unit_unknown", 1.0


def _detect_unit_nearest(window: str) -> tuple[str, float]:
    """W5 修复（2026-05-19）：按"最近距离"找单位，纠正"长度优先"导致的误命中.

    Bug 复现
    --------
    PDF 文本：``Revenue (Total Revenue): 128.6 亿元 (12860 million CNY)``
    数字 ``128.6`` 紧后是 ``" 亿元 (12860 million CNY)..."``.

    旧策略 ``_detect_unit`` 按长度降序匹配 → ``million``(7) 比 ``亿元``(2)
    长 → 误命中 ``million``，导致 ``mult=1e6``，最终 ``revenue`` 变成
    ``128,600,000`` 元（实际应为 12,860,000,000 元 = 128.6 亿元）.

    新策略
    ------
    遍历 ``UNIT_DICT`` 找窗口内**位置最早**的 unit（同位置时取较长的）.
    与 ``_detect_unit`` 共用 ``UNIT_DICT`` SSOT（DRY · 数据源不变）.

    用法
    ----
    ``extract_kpi_from_pdf`` 优先调本函数（数字紧后 30 字符窗口）；
    若返回 ``unit_unknown`` 再退回 ``_detect_unit`` 全窗口扫描.
    """
    w = window.lower()
    candidates: list[tuple[int, int, str, float]] = []
    for unit, mult in UNIT_DICT.items():
        idx = w.find(unit.lower())
        if idx >= 0:
            # 排序键：(位置最早, 长度最长, ...)
            candidates.append((idx, -len(unit), unit, mult))
    if not candidates:
        return "unit_unknown", 1.0
    candidates.sort()
    _, _, unit, mult = candidates[0]
    return unit, mult


def _detect_currency(window: str) -> str:
    """识别币种：默认 CNY；命中 USD/EUR/HKD 关键词时返回对应代码."""
    w = window.lower()
    if any(kw in w for kw in ("usd", "$", "美元", "us dollar")):
        return "USD"
    if any(kw in w for kw in ("eur", "€", "欧元")):
        return "EUR"
    if any(kw in w for kw in ("hkd", "港元", "港币")):
        return "HKD"
    if any(kw in w for kw in ("jpy", "日元", "yen")):
        return "JPY"
    return "CNY"


# ════════════════════════════════════════════════════════════════════════
# alias 歧义消解（W5 修复 · 2026-05-19）
# ════════════════════════════════════════════════════════════════════════
#
# 事故复盘
# --------
#   实测 financial-analyst Tier 1 真实 LLM E2E（合成 PDF 含"净利润率维持
#   11.9%"）暴露：``net_profit`` 被抽成 11.9 而不是输入的 15.3.
#   根因：alias "净利润" 命中 "净利润率" 子串.
#
# 修复策略（System 1 严守，不调 LLM；详
# ``tests/test_extract_kpi_alias_disambiguation.py`` 回归测试）:
#   1. ``_KPI_ALIASES_SORTED``：alias 列表内部按长度降序排（更长 = 更具体）
#   2. ``_RATIO_SUFFIX_RE``：alias 后紧跟"率/比/ratio/margin/rate" 时，
#      若当前 KPI 不在 ``_RATIO_KPIS`` 集合内 → 跳过该位置继续搜
#   3. ``_VALUE_FOLLOWED_BY_PERCENT_RE``：候选数字紧后是 "%" 时，
#      若当前 KPI 不是 ratio → 跳过该数字（防 net_profit 误命中百分比数字）

_RATIO_KPIS = frozenset({"gross_margin", "rd_ratio", "roe", "debt_to_equity"})

# 紧跟 alias 之后会改变 KPI 语义的修饰词：
#   "净利润" + "率" → ratio（不是绝对值）
#   "营业收入" + "比" → 比率
_RATIO_SUFFIX_RE = re.compile(r"^(率|比|ratio|margin|rate|比率|占比)", re.IGNORECASE)

# 数字紧后是 "%"：表示百分比（如 "净利润率维持 11.9%" 里的 11.9 是 ratio）
_PERCENT_AFTER_NUM_RE = re.compile(r"\s*%")

# 预排序：alias 内部按长度降序（更长 = 更具体，优先匹配）
_KPI_ALIASES_SORTED: dict[str, list[str]] = {
    kpi: sorted(aliases, key=lambda a: -len(a))
    for kpi, aliases in KPI_DICT.items()
}


def _find_alias_position(
    text: str, kpi_id: str, aliases: list[str], is_ratio_kpi: bool
) -> tuple[int, str]:
    """找 ``kpi_id`` 第一个 **语义合规** 的 alias 命中位置.

    后置语义过滤：
      - 若命中位置后紧跟"率/比/ratio/margin"等修饰词 + 当前 KPI 不是 ratio
        类型 → 跳过该位置，继续找
      - 若命中位置后紧跟的数字紧跟 "%" + 当前 KPI 不是 ratio → 跳过

    Returns:
        ``(hit_pos, hit_alias)`` 或 ``(-1, "")`` 未找到
    """
    text_lower = text.lower()
    for alias in aliases:
        alias_lower = alias.lower()
        search_from = 0
        while True:
            idx = text_lower.find(alias_lower, search_from)
            if idx < 0:
                break
            # 检查 alias 后紧跟字符
            tail_start = idx + len(alias)
            tail = text[tail_start: tail_start + 8]
            if (not is_ratio_kpi) and _RATIO_SUFFIX_RE.match(tail):
                # alias 后紧跟"率/比"等修饰词，且当前 KPI 不是 ratio → 跳过
                search_from = idx + len(alias)
                continue
            return idx, alias
    return -1, ""


def extract_kpi_from_pdf(
    path: str | Path,
    company_name: str | None = None,
    target_kpis: list[str] | None = None,
) -> dict[str, Any]:
    """从年报 PDF 抽取标准 KPI（System 1 deterministic）.

    W5 升级（2026-05-19 · alias 歧义消解）:
      - alias 内部按长度降序排（更长更具体优先）
      - 后置语义过滤防止 ''净利润'' 命中 ''净利润率'' 子串等 bug
      - ratio KPI 数字紧跟 "%" 时跳过候选

    Args:
        path: 年报 PDF 路径
        company_name: 公司名（用于输出标识；None 时自动用文件名 stem）
        target_kpis: 要抽的指标 ID 列表（默认全 ``KPI_DICT.keys()``）

    Returns:
        dict 含 ok/summary/company/kpis（dict 嵌套：
            ``{kpi_id: {value, unit, currency, raw_text, source_window}}``）
    """
    p = _normalize_path(path)
    if not p.exists():
        return _golden_error(
            f"年报 PDF 不存在：{p}",
            where=f"path={path}",
            fixes=[
                "检查路径拼写（年报通常在 sample_data/ 下）",
                "支持 PDF / PDF.pdf 后缀",
                "PDF 需未加密；加密 PDF 先用 qpdf 解密",
            ],
            related=["extract_kpi_from_pdf", "normalize_kpi_table"],
        )
    if p.suffix.lower() != ".pdf":
        return _golden_error(
            f"非 PDF 文件：{p.suffix}",
            where=f"path={p}",
            fixes=[
                "本工具只读 PDF（年报标准格式）",
                "Excel / XBRL 数据请用 normalize_kpi_table 工具直传",
            ],
        )

    text = _scan_pdf_text(p)
    if not text or len(text) < 200:
        return _golden_error(
            "PDF 文本抽取失败 / 内容过短（< 200 字符）",
            where=f"path={p}",
            fixes=[
                "PDF 可能是扫描件 / 图像版（无文本层）→ 先用 OCR 转出来",
                "或 pdfplumber/PyMuPDF 装的不全 → pip install pdfplumber pymupdf",
                "也可能确实是空文档 → 换一份年报试试",
            ],
            related=["extract_kpi_from_pdf"],
        )

    target = target_kpis or list(KPI_DICT.keys())
    name = company_name or p.stem
    kpis: dict[str, dict[str, Any]] = {}
    miss: list[str] = []

    for kpi_id in target:
        # alias 内部按长度降序排，确保 "归属于母公司股东净利润" 优先于 "净利润"
        aliases = _KPI_ALIASES_SORTED.get(kpi_id) or KPI_DICT.get(kpi_id, [])
        if not aliases:
            miss.append(kpi_id)
            continue
        is_ratio = kpi_id in _RATIO_KPIS
        # W5: 后置语义过滤 — 跳过 "净利润率" 等子串误命中
        hit_pos, hit_alias = _find_alias_position(text, kpi_id, aliases, is_ratio)
        if hit_pos < 0:
            miss.append(kpi_id)
            continue

        # 在 alias 后 250 字符内找候选数字
        window_start = hit_pos + len(hit_alias)
        window = text[window_start: window_start + 250]
        # W5: 用 finditer 拿位置，配合"后置 % 检测"过滤候选
        value: float | None = None
        raw_match: str = ""
        raw_match_end_in_window: int = -1
        for m in _NUMBER_PATTERN.finditer(window):
            n_str = m.group(0)
            v = _parse_number(n_str)
            if v is None:
                continue
            # 候选数字紧后是 "%" 但当前 KPI 不是 ratio → 跳过
            tail = window[m.end(): m.end() + 3]
            if (not is_ratio) and _PERCENT_AFTER_NUM_RE.match(tail):
                continue
            value = v
            raw_match = n_str
            raw_match_end_in_window = m.end()
            break
        if value is None:
            miss.append(kpi_id)
            continue

        # W5 修复：unit detection 用"距离紧度"代替"长度优先".
        # 旧逻辑：``_detect_unit(全窗口 350 字符)`` → "million" 比 "亿元" 长 →
        # 优先命中，但实际"million" 在 "(12860 million CNY)" 与本数字无关.
        # 新逻辑：先在数字紧后 30 字符内用 ``_detect_unit_nearest`` 找最近 unit；
        # 找不到再退回全窗口（``_detect_unit`` 长度优先）.
        narrow_unit_window = window[raw_match_end_in_window: raw_match_end_in_window + 30]
        unit, mult = _detect_unit_nearest(narrow_unit_window)
        if unit == "unit_unknown":
            unit, mult = _detect_unit_nearest(
                text[max(0, hit_pos - 100): window_start + 250]
            )
        # ratio 类 KPI 的 unit 字段强制 normalize 到 "%"，
        # 避免 _detect_unit 在窗口内捕到 "million" 等英文字误标
        if is_ratio:
            unit = "%"
            mult = 0.01
        currency = _detect_currency(text[max(0, hit_pos - 100): window_start + 250])
        # 比例/百分比类 KPI 不做单位放大
        normalized = value if is_ratio else value * mult

        kpis[kpi_id] = {
            "value": normalized,
            "raw_value": value,
            "unit": unit,
            "currency": currency if not is_ratio else None,
            "raw_text": f"{hit_alias} ... {raw_match}",
            "source_window": window[:120].replace("\n", " "),
            "is_ratio": is_ratio,
        }

    return {
        "ok": True,
        "summary": (
            f"从 {name} 年报抽到 {len(kpis)}/{len(target)} 个 KPI"
            f"{'（缺：' + ', '.join(miss) + '）' if miss else ''}"
        ),
        "company": name,
        "kpis": kpis,
        "missed": miss,
        "source": str(p),
    }


# ============================================================
# §2. KPI 同口径归一化（跨公司、跨币种、跨期）
# ============================================================
#
# 真实业务问题：
#   公司 A 报"营业收入 245.76 亿元（CNY）"；公司 B 报"Revenue 3,840 USD million"。
#   投行做横向对比需要：
#   1. 单位统一（都换成 CNY 亿元 或 USD billion）
#   2. 币种统一（按报告期均价汇率换算）
#   3. 期数对齐（2024 年报 vs 2024 年报，不能拿 2024 H1 跟 2024 全年比）
#
# 这是纯算术工作，LLM 完全没必要做（也容易出错）。


_DEFAULT_FX_RATES = {
    # 占位汇率（cookbook demo 用）；生产环境应接 Wind / Bloomberg / 央行 API
    # 来源：2024 年央行公布平均价；真实使用时请替换为报告期均价
    "CNY": 1.0,
    "USD": 7.20,
    "EUR": 7.85,
    "HKD": 0.92,
    "JPY": 0.048,
}


def normalize_kpi_table(
    companies: list[dict[str, Any]],
    target_currency: str = "CNY",
    target_unit: str = "亿",
    fx_rates: dict[str, float] | None = None,
) -> dict[str, Any]:
    """把多公司 KPI 拉平到同口径表格.

    Args:
        companies: ``[{"company": "A", "kpis": {...}}, ...]``
            每个 entry 必须有 ``kpis`` 字段，结构同 ``extract_kpi_from_pdf`` 输出
        target_currency: 目标币种（CNY/USD/EUR/HKD/JPY）
        target_unit: 目标单位（"亿"/"百万"/"万"/"元"，默认"亿"）
        fx_rates: 自定义汇率（None 用 ``_DEFAULT_FX_RATES``；生产请传报告期实际汇率）

    Returns:
        dict 含 ok/summary/table/columns/period_warnings
    """
    if not companies:
        return _golden_error(
            "公司列表为空",
            where="normalize_kpi_table(companies=[])",
            fixes=["至少传 1 家公司的 KPI（来自 extract_kpi_from_pdf）"],
            related=["extract_kpi_from_pdf"],
        )

    rates = dict(_DEFAULT_FX_RATES)
    if fx_rates:
        rates.update(fx_rates)
    if target_currency not in rates:
        return _golden_error(
            f"target_currency={target_currency!r} 不在汇率表",
            where=f"target_currency={target_currency}",
            fixes=[
                f"支持的币种：{', '.join(rates.keys())}",
                "或在 fx_rates= 显式提供该币种汇率",
            ],
        )
    target_unit_mult = UNIT_DICT.get(target_unit, 1.0)
    if target_unit not in UNIT_DICT:
        return _golden_error(
            f"target_unit={target_unit!r} 未识别",
            where=f"target_unit={target_unit}",
            fixes=[f"支持的单位：{', '.join(sorted(UNIT_DICT))}"],
        )

    table: list[dict[str, Any]] = []
    period_warnings: list[str] = []
    columns: set[str] = set()

    target_rate = rates[target_currency]
    for entry in companies:
        company = entry.get("company") or "unknown"
        kpis = entry.get("kpis") or {}
        period = entry.get("period")
        if period and any(p != period for p in (e.get("period") for e in companies) if p):
            period_warnings.append(
                f"⚠️ {company} 报告期={period}，与基准不同 → 横向对比需注意"
            )
        row: dict[str, Any] = {"company": company, "period": period}
        for kpi_id, info in kpis.items():
            value = info.get("value")
            if value is None:
                row[kpi_id] = None
                continue
            currency = info.get("currency")
            is_ratio = info.get("is_ratio", False)
            if is_ratio:
                # 比率类（毛利率 / ROE）已是标准化数值，不做换算
                row[kpi_id] = value
            else:
                # 数值类：先换币种，再换单位
                src_rate = rates.get(currency, 1.0) if currency else 1.0
                # 源 → CNY → 目标币种（避免 USD-EUR 直接换算精度损失）
                in_target = value * src_rate / target_rate
                row[kpi_id] = in_target / target_unit_mult
            columns.add(kpi_id)
        table.append(row)

    # W5 修复（2026-05-19 · 2026-05-19 cookbook bug）：
    # 输出加 ``column_units`` 自描述 schema，让 LLM 不需要猜 ratio 数值含义.
    # 实测踩坑：LLM 把 ``gross_margin=42.5`` 误读为 42.5×10⁻⁶ → 报告写
    # "毛利率 0.0000425%" → 投资判断完全错位.
    column_units: dict[str, str] = {}
    for col in sorted(columns):
        if col in _RATIO_KPIS:
            column_units[col] = "percent"
        else:
            column_units[col] = f"{target_currency} {target_unit}"

    return {
        "ok": True,
        "summary": (
            f"归一化 {len(companies)} 家公司 → "
            + ", ".join(
                f"{c}={r.get(c) if r.get(c) is not None else 'N/A'}"
                + (
                    "%"
                    if c in _RATIO_KPIS and r.get(c) is not None
                    else (f" {target_unit}" if r.get(c) is not None else "")
                )
                for r in table[:1]
                for c in sorted(columns)
            )
            + (f"（{len(period_warnings)} 条期数警告）" if period_warnings else "")
        ),
        "table": table,
        "columns": sorted(columns),
        "column_units": column_units,
        "schema_notes": [
            "ratio KPI（gross_margin/roe/rd_ratio/debt_to_equity）数值已是百分比形式：",
            "  ➜ 42.5 表示 42.5%（不要 ÷100 或 ×100，直接 f'{v}%' 写报告）",
            f"绝对值 KPI（revenue/net_profit/operating_cash_flow/...）单位 = {target_currency} {target_unit}",
        ],
        "target_currency": target_currency,
        "target_unit": target_unit,
        "period_warnings": period_warnings,
    }


# ============================================================
# §3. 行业基线统计（Z-score 偏差判断的基础）
# ============================================================
#
# 业务理由：
#   LLM 看到"公司 A 毛利率 35%"无法判断这是高/低 —— 需要行业均值 / 中位数 / 标准差
#   做参考。本工具按归一化 KPI 表生成行业基线，HintPlugin 据此推 3σ 偏差信号。


def industry_baseline(
    normalized_table: list[dict[str, Any]],
    kpi_ids: list[str] | None = None,
) -> dict[str, Any]:
    """对归一化 KPI 表算行业基线（mean / median / std / quartiles）.

    Args:
        normalized_table: ``normalize_kpi_table().table`` 返回的 list[dict]
        kpi_ids: 要算的指标 ID（None 默认全表里的数值列）

    Returns:
        dict 含 baselines: {kpi_id: {n, mean, median, std, q1, q3, min, max}}
    """
    if not normalized_table:
        return _golden_error(
            "归一化表为空",
            where="industry_baseline(normalized_table=[])",
            fixes=["先用 normalize_kpi_table 生成归一化表"],
            related=["normalize_kpi_table"],
        )

    # 自动识别数值列
    if kpi_ids is None:
        kpi_ids = []
        for row in normalized_table:
            for k, v in row.items():
                if k in ("company", "period"):
                    continue
                if (
                    isinstance(v, (int, float))
                    and v is not None
                    and k not in kpi_ids
                ):
                    kpi_ids.append(k)

    baselines: dict[str, dict[str, Any]] = {}
    sparse: list[str] = []
    for kpi in kpi_ids:
        values = [
            row[kpi] for row in normalized_table
            if isinstance(row.get(kpi), (int, float))
        ]
        n = len(values)
        if n < 2:
            sparse.append(kpi)
            baselines[kpi] = {
                "n": n,
                "mean": values[0] if n == 1 else None,
                "median": values[0] if n == 1 else None,
                "std": None,
                "q1": None,
                "q3": None,
                "min": values[0] if n == 1 else None,
                "max": values[0] if n == 1 else None,
            }
            continue
        sorted_vals = sorted(values)
        baselines[kpi] = {
            "n": n,
            "mean": statistics.fmean(values),
            "median": statistics.median(values),
            "std": statistics.pstdev(values) if n >= 2 else None,
            "q1": sorted_vals[n // 4],
            "q3": sorted_vals[(3 * n) // 4],
            "min": min(values),
            "max": max(values),
        }

    return {
        "ok": True,
        "summary": (
            f"算了 {len(kpi_ids)} 个 KPI 的行业基线，{n} 家公司样本"
            + (
                f"；{len(sparse)} 个 KPI 数据稀疏（<2 公司）"
                if sparse else ""
            )
        ),
        "baselines": baselines,
        "kpi_ids": list(kpi_ids),
        "sparse_kpis": sparse,
    }


# ============================================================
# §4. 雷达图 SVG 生成（System 1 几何计算 → SVG 字符串）
# ============================================================
#
# 业务理由：
#   投行 deck 标配雷达图（用图形对比公司多维 KPI）。
#   System 1 算几何（角度 + 半径 + polygon points），不让 LLM 凭感觉算 cos/sin。
#   不引第三方依赖（不用 matplotlib），输出 SVG 字符串可被 word_smart_export 嵌入。


def radar_chart_svg(
    normalized_table: list[dict[str, Any]],
    kpi_ids: list[str],
    *,
    width: int = 560,
    height: int = 560,
    palette: list[str] | None = None,
    title: str = "公司 KPI 雷达图",
) -> dict[str, Any]:
    """从归一化 KPI 表生成多公司雷达图 SVG.

    Args:
        normalized_table: ``normalize_kpi_table().table``
        kpi_ids: 要画的 KPI（建议 5-8 个；少了图形扁平，多了字看不清）
        width / height: 画布尺寸
        palette: 公司线条配色（None 用内置 Tableau 10 色盲友好配色）
        title: 图标题

    Returns:
        dict 含 ok/summary/svg（完整 ``<svg>`` 字符串）
    """
    if not normalized_table:
        return _golden_error(
            "归一化表为空",
            where="radar_chart_svg",
            fixes=["先 normalize_kpi_table 生成归一化表"],
            related=["normalize_kpi_table"],
        )
    if not kpi_ids or len(kpi_ids) < 3:
        return _golden_error(
            "雷达图至少要 3 个 KPI 维度",
            where=f"kpi_ids={kpi_ids}",
            fixes=[
                "加更多 KPI 维度（建议 5-8 个）",
                "可用维度：" + str([
                    k for k in normalized_table[0]
                    if k not in ("company", "period")
                ]),
            ],
        )

    # 内置 Tableau 10 色盲友好配色（与 data-analyst pick_palette categorical 同源）
    default_palette = [
        "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
        "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
    ]
    colors = palette or default_palette

    # 每个 KPI 维度的 max（归一化到 [0,1] 用于绘图；防一家公司 KPI 极大压扁其他）
    n_dims = len(kpi_ids)
    cx, cy = width / 2, height / 2
    radius = min(width, height) * 0.36

    # 找每个 KPI 的 max（绝对值）
    kpi_max: dict[str, float] = {}
    for kpi in kpi_ids:
        vals = [
            abs(row[kpi]) for row in normalized_table
            if isinstance(row.get(kpi), (int, float))
        ]
        kpi_max[kpi] = max(vals) if vals else 1.0
        if kpi_max[kpi] == 0:
            kpi_max[kpi] = 1.0

    svg_parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        # 标题
        f'<text x="{cx}" y="30" text-anchor="middle" '
        'font-family="Helvetica,Arial,sans-serif" font-size="18" font-weight="bold" '
        f'fill="#2c3e50">{title}</text>',
    ]

    # 背景蛛网（5 圈）
    for i in range(1, 6):
        r = radius * i / 5
        ring_pts = []
        for d in range(n_dims):
            angle = 2 * math.pi * d / n_dims - math.pi / 2
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            ring_pts.append(f"{x:.1f},{y:.1f}")
        svg_parts.append(
            f'<polygon points="{" ".join(ring_pts)}" fill="none" '
            'stroke="#dfe6e9" stroke-width="1"/>'
        )

    # 维度轴 + 标签
    for d, kpi in enumerate(kpi_ids):
        angle = 2 * math.pi * d / n_dims - math.pi / 2
        x_end = cx + radius * math.cos(angle)
        y_end = cy + radius * math.sin(angle)
        x_label = cx + (radius + 30) * math.cos(angle)
        y_label = cy + (radius + 30) * math.sin(angle) + 5
        svg_parts.append(
            f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x_end:.1f}" y2="{y_end:.1f}" '
            'stroke="#b2bec3" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="{x_label:.1f}" y="{y_label:.1f}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="12" fill="#34495e">{kpi}</text>'
        )

    # 每家公司画一个 polygon
    for ci, row in enumerate(normalized_table):
        company = row.get("company", f"row{ci}")
        color = colors[ci % len(colors)]
        poly_pts: list[str] = []
        for d, kpi in enumerate(kpi_ids):
            v = row.get(kpi)
            if not isinstance(v, (int, float)):
                v = 0
            r = radius * (abs(v) / kpi_max[kpi])
            angle = 2 * math.pi * d / n_dims - math.pi / 2
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            poly_pts.append(f"{x:.1f},{y:.1f}")
        svg_parts.append(
            f'<polygon points="{" ".join(poly_pts)}" '
            f'fill="{color}" fill-opacity="0.15" stroke="{color}" stroke-width="2"/>'
        )

    # 图例
    legend_y = height - 40 - len(normalized_table) * 18
    for ci, row in enumerate(normalized_table):
        company = row.get("company", f"row{ci}")
        color = colors[ci % len(colors)]
        ly = legend_y + ci * 18
        svg_parts.append(
            f'<rect x="20" y="{ly}" width="14" height="14" fill="{color}" '
            f'fill-opacity="0.3" stroke="{color}"/>'
        )
        svg_parts.append(
            f'<text x="40" y="{ly + 11}" font-family="Helvetica,Arial,sans-serif" '
            f'font-size="12" fill="#2c3e50">{company}</text>'
        )

    svg_parts.append("</svg>")
    svg = "\n".join(svg_parts)
    return {
        "ok": True,
        "summary": (
            f"生成 {len(normalized_table)} 公司 × {n_dims} 维度雷达图 "
            f"({width}×{height}px, {len(svg)} bytes)"
        ),
        "svg": svg,
        "n_companies": len(normalized_table),
        "n_dims": n_dims,
    }


# ============================================================
# §5. 估值锚（PE / PB / PS 简化模型）
# ============================================================
#
# 业务理由：
#   投资简报需要给"估值水平"判断（贵 / 合理 / 便宜）。这是 System 1
#   工作（PE = price / EPS、PB = price / BPS）；LLM 不应凭感觉算。
#   生产环境应接 Wind / 同花顺 API 拿实时市值；cookbook demo 用占位 market_cap 入参。


def valuation_anchor(
    company: str,
    *,
    market_cap: float,
    net_profit: float,
    book_value: float | None = None,
    revenue: float | None = None,
    industry_pe_median: float | None = None,
    industry_pb_median: float | None = None,
) -> dict[str, Any]:
    """计算公司估值倍数 + 与行业中位数对比.

    Args:
        company: 公司名
        market_cap: 总市值（同币种、同单位 与 net_profit 一致）
        net_profit: 净利润（用于 PE）
        book_value: 净资产 / 股东权益（用于 PB；None 则不算 PB）
        revenue: 营业收入（用于 PS；None 则不算 PS）
        industry_pe_median: 行业 PE 中位数（用于偏差对比；None 则不对比）
        industry_pb_median: 行业 PB 中位数

    Returns:
        dict 含 ok/summary/multiples/comparison/verdict
    """
    if market_cap <= 0:
        return _golden_error(
            f"market_cap={market_cap} 必须 > 0",
            where=f"company={company}",
            fixes=["传当前总市值（同币种 / 同单位 与 net_profit 一致）"],
        )

    multiples: dict[str, float | None] = {}

    # PE = 市值 / 净利润
    if net_profit and net_profit > 0:
        multiples["pe"] = market_cap / net_profit
    elif net_profit and net_profit <= 0:
        multiples["pe"] = None  # 亏损公司 PE 无意义
    else:
        multiples["pe"] = None

    # PB = 市值 / 净资产
    if book_value and book_value > 0:
        multiples["pb"] = market_cap / book_value
    else:
        multiples["pb"] = None

    # PS = 市值 / 营收
    if revenue and revenue > 0:
        multiples["ps"] = market_cap / revenue
    else:
        multiples["ps"] = None

    comparison: dict[str, Any] = {}
    verdict_parts: list[str] = []

    if multiples["pe"] is not None and industry_pe_median:
        diff_pct = (multiples["pe"] - industry_pe_median) / industry_pe_median * 100
        comparison["pe_vs_industry_pct"] = round(diff_pct, 2)
        if diff_pct > 30:
            verdict_parts.append(f"PE 高于行业中位数 {diff_pct:.0f}% → 估值偏贵")
        elif diff_pct < -30:
            verdict_parts.append(f"PE 低于行业中位数 {-diff_pct:.0f}% → 估值偏便宜")
        else:
            verdict_parts.append("PE 在行业 ±30% 区间内 → 估值合理")

    if multiples["pb"] is not None and industry_pb_median:
        diff_pct = (multiples["pb"] - industry_pb_median) / industry_pb_median * 100
        comparison["pb_vs_industry_pct"] = round(diff_pct, 2)

    pe_part = (
        f"{company}：PE={multiples['pe']:.1f}" if multiples["pe"]
        else f"{company}：PE 不可算（亏损？）"
    )
    pb_part = f"，PB={multiples['pb']:.1f}" if multiples["pb"] else ""
    ps_part = f"，PS={multiples['ps']:.1f}" if multiples["ps"] else ""
    return {
        "ok": True,
        "summary": pe_part + pb_part + ps_part,
        "company": company,
        "multiples": multiples,
        "comparison": comparison,
        "verdict": "；".join(verdict_parts) or "无行业基线对比",
    }


# ============================================================
# §6. ToolPlugin（注册 5 个 System 1 工具到 SDK）
# ============================================================


class FinancialAnalystToolPlugin:
    """实现 ``krow_agent_sdk.protocols.ToolPlugin`` Protocol.

    注册 5 个 System 1 工具：
    - financial_analyst_extract_kpi_from_pdf
    - financial_analyst_normalize_kpi_table
    - financial_analyst_industry_baseline
    - financial_analyst_radar_chart_svg
    - financial_analyst_valuation_anchor

    投资简报 PDF 输出**复用** Krow 内置 ``word_smart_export``（SSOT；
    不在本 plugin 注册），与 data-analyst v2 保持一致。
    """

    plugin_id = "fin_analyst.tools"

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "financial_analyst_extract_kpi_from_pdf",
                "description": (
                    "从年报 PDF 抽取标准 KPI（System 1 deterministic）。"
                    "用 KPI_DICT 关键词字典识别 10 类指标"
                    "（revenue/net_profit/gross_margin/operating_cash_flow/total_assets/"
                    "total_equity/rd_ratio/roe/debt_to_equity/eps），"
                    "用 UNIT_DICT 识别单位（亿/百万/billion/...），用窗口扫描识别币种。"
                    "**禁止 LLM 凭感觉抽 KPI**——LLM 抽 KPI 漂移率 1-3% 不可接受。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "年报 PDF 路径"},
                        "company_name": {
                            "type": "string",
                            "description": "公司名（None 时用文件名 stem）",
                        },
                        "target_kpis": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要抽的 KPI ID 列表（默认全部 10 个）",
                        },
                    },
                    "required": ["path"],
                },
                "handler": extract_kpi_from_pdf,
            },
            {
                "name": "financial_analyst_normalize_kpi_table",
                "description": (
                    "把多公司 KPI 拉平到同口径表格（统一币种 + 统一单位）。"
                    "支持 CNY/USD/EUR/HKD/JPY 5 币种，自动按汇率换算。"
                    "**铁律**：横向对比前必须先归一，否则会撞数量级错误。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "companies": {
                            "type": "array",
                            "description": "[{company, kpis: {...}, period?}, ...]",
                        },
                        "target_currency": {
                            "type": "string",
                            "enum": ["CNY", "USD", "EUR", "HKD", "JPY"],
                            "default": "CNY",
                        },
                        "target_unit": {
                            "type": "string",
                            "default": "亿",
                            "description": "目标单位（亿/百万/万/元）",
                        },
                        "fx_rates": {
                            "type": "object",
                            "description": "自定义汇率（None 用内置占位汇率）",
                        },
                    },
                    "required": ["companies"],
                },
                "handler": normalize_kpi_table,
            },
            {
                "name": "financial_analyst_industry_baseline",
                "description": (
                    "对归一化 KPI 表算行业基线（mean/median/std/quartiles）。"
                    "HintPlugin 据此推 3σ 偏差信号。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "normalized_table": {"type": "array"},
                        "kpi_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["normalized_table"],
                },
                "handler": industry_baseline,
            },
            {
                "name": "financial_analyst_radar_chart_svg",
                "description": (
                    "从归一化 KPI 表生成多公司雷达图 SVG（System 1 几何）。"
                    "建议 5-8 个 KPI 维度；公司用色盲友好 Tableau 10 配色。"
                    "**禁止 LLM 凭感觉算 cos/sin**——这是几何计算，必须出工具。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "normalized_table": {"type": "array"},
                        "kpi_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "雷达图维度（建议 5-8 个）",
                        },
                        "width": {"type": "integer", "default": 560},
                        "height": {"type": "integer", "default": 560},
                        "title": {"type": "string"},
                    },
                    "required": ["normalized_table", "kpi_ids"],
                },
                "handler": radar_chart_svg,
            },
            {
                "name": "financial_analyst_valuation_anchor",
                "description": (
                    "计算公司 PE/PB/PS 估值倍数 + 与行业中位数对比给出 verdict。"
                    "亏损公司 PE 自动返回 None；行业基线缺失时 verdict 退化为单点信息。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "market_cap": {"type": "number"},
                        "net_profit": {"type": "number"},
                        "book_value": {"type": "number"},
                        "revenue": {"type": "number"},
                        "industry_pe_median": {"type": "number"},
                        "industry_pb_median": {"type": "number"},
                    },
                    "required": ["company", "market_cap", "net_profit"],
                },
                "handler": valuation_anchor,
            },
            # 投资简报 PDF 输出 → Krow 内置 word_smart_export（SSOT 复用，不在本 plugin 注册）
        ]


# ============================================================
# §7. ACTPlugin（让 LLM 自动选 financial_analyst ACT）
# ============================================================


class FinancialAnalystACTPlugin:
    """实现 ``krow_agent_sdk.protocols.ACTPlugin`` Protocol。"""

    plugin_id = "fin_analyst.act"
    act_name = "financial_analyst"

    def get_act_root(self) -> Path:
        return Path(__file__).parent / "act_assets" / "financial_analyst"

    def get_act_file_path(self) -> Path:
        return self.get_act_root() / "ext_financial_analyst.md"

    def get_tool_names(self) -> list[str]:
        # 5 个 plugin 工具 + word_smart_export（Krow 内置 PDF 出口）
        return [
            "financial_analyst_extract_kpi_from_pdf",
            "financial_analyst_normalize_kpi_table",
            "financial_analyst_industry_baseline",
            "financial_analyst_radar_chart_svg",
            "financial_analyst_valuation_anchor",
            "word_smart_export",
        ]


# ============================================================
# §8. GatePlugin × 2（金融行业合规硬阻）
# ============================================================
#
# 设计依据（与 data-analyst v2 同基因）：
#   Gate = System 1 deterministic 闸门（不调 LLM；零成本；100% 可重放）
#   适用场景 = "金融行业法律红线" —— 不是"建议关注"是"必须满足否则违法"
#
# 为什么这两个 Gate 不能用 hint 替代：
#   1. 简报披露完整性 = 监管要求（CSRC 投资者保护规则）；hint 提醒 LLM
#      "请记得写风险段"在 LLM 偷懒时会失效 → 必须 System 1 闸住
#   2. 内幕信息引用 = 法律红线（《证券法》第五十一条）；LLM 偶尔会把
#      "内部数据" / "未公开" / "尚未披露" 写进简报 → 必须扫描
#      conclude payload 一键阻断


# 投资简报标准 5 段（CSRC 第 17 号信息披露公告 + 投行内部规范）
_REQUIRED_DISCLOSURE_SECTIONS = [
    # (段名, 关键词列表 — 命中任一即视为本段已写)
    ("业务概览", ["业务概览", "业务介绍", "公司业务", "主营业务",
                "Business Overview"]),
    ("财务表现", ["财务表现", "财务分析", "财务概况", "经营业绩",
                "Financial Performance"]),
    ("行业地位", ["行业地位", "竞争格局", "市场份额", "行业对比",
                "Market Position"]),
    ("风险因素", ["风险因素", "主要风险", "风险提示", "投资风险", "Risk Factors"]),
    ("投资建议", ["投资建议", "估值结论", "投资逻辑", "买入", "卖出", "持有",
                "Investment Recommendation"]),
]

# 内幕信息触发关键词（一律视为高风险，提醒 LLM 修改措辞）
_INSIDER_KEYWORDS = [
    # 中文
    "内幕", "未公开", "尚未披露", "尚未公告", "内部数据", "私有调研",
    "知情人", "实质性进展（未披露）", "重大信息（未披露）",
    # 英文
    "inside information", "non-public", "undisclosed material",
    "material non-public", "MNPI",
]


class DisclosureCompletenessGate:
    """合规守门：投资简报必须含 5 段标准披露段，缺任一段 BLOCK conclude.

    实现 ``krow_agent_sdk.protocols.GatePlugin`` Protocol。

    工作机制：每次 macro ReACT conclude 前扫描 ``context.parsed`` /
    ``recent_tool_results`` 里 ``write_report`` 工具的 markdown 内容；
    缺段则返回 BLOCK + 缺哪几段 + 修法。

    真实业务价值：
    - CSRC 信息披露公告 17 号要求投资简报"完整、准确、不误导"
    - 缺风险段的简报投资人投诉率最高（监管处罚案例铁证）
    - 让 LLM "请记得写风险段" 是不够的——必须 System 1 闸住

    可关闭场景：``strict=False`` 时退化为 ``warn``（只在 reason 里提示，
    不 BLOCK）；用于早期草稿 / 测试场景。
    """

    plugin_id = "fin_analyst.disclosure_gate"
    phase = "macro"

    def __init__(
        self,
        *,
        required_sections: list[tuple[str, list[str]]] | None = None,
        strict: bool = True,
    ) -> None:
        self._sections = required_sections or _REQUIRED_DISCLOSURE_SECTIONS
        self._strict = bool(strict)

    def _scan_sections(self, text: str) -> list[str]:
        """返回缺失段名列表."""
        if not text:
            return [name for name, _ in self._sections]
        missing: list[str] = []
        text_lower = text.lower()
        for name, keywords in self._sections:
            if not any(kw.lower() in text_lower for kw in keywords):
                missing.append(name)
        return missing

    def get_gate(self) -> Any:
        from krow_agent_sdk.protocols import (
            GateDecision,
            GateVerdict,
            make_simple_gate,
        )

        sections = self._sections
        strict = self._strict
        scan = self._scan_sections

        def evaluate(parsed: dict, context: dict) -> Any:
            tool_results = context.get("recent_tool_results", []) or []
            # 找最近一次产出 markdown 报告的工具调用
            report_text: str = ""
            for tr in reversed(tool_results):
                if not isinstance(tr, dict):
                    continue
                tool_name = tr.get("tool_name", "")
                # 兼容多种 write 工具名（v3 cookbook 跨 demo 命名差异容错）
                if tool_name in (
                    "data_analyst_write_report",
                    "word_smart_export",
                ) or "write_report" in tool_name:
                    args = tr.get("args") or {}
                    report_text = args.get("content") or args.get("body") or ""
                    if not report_text:
                        # word_smart_export 走 file_path → 读文件
                        fp = args.get("file_path") or args.get("path")
                        if fp:
                            with suppress(Exception):
                                report_text = Path(fp).read_text(encoding="utf-8")
                    if report_text:
                        break

            # 如果还没生成报告 → DEFER（agent 还在构造，gate 不该现在闸）
            if not report_text:
                return GateDecision(
                    verdict=GateVerdict.DEFER,
                    gate_name="disclosure_completeness",
                )

            missing = scan(report_text)
            if not missing:
                return GateDecision(
                    verdict=GateVerdict.ALLOW,
                    reason=(
                        f"✅ 5 段标准披露齐全：{', '.join(name for name, _ in sections)}"
                    ),
                    gate_name="disclosure_completeness",
                )

            verdict = GateVerdict.BLOCK if strict else GateVerdict.ALLOW
            reason = (
                f"❌ 投资简报披露不完整：缺 {len(missing)}/{len(sections)} 段："
                f"{', '.join(missing)}\n"
                "   位置：write_report / word_smart_export 输出 markdown\n"
                "   修法：\n"
                "     1. 补齐每段并使用以下任一关键词作为段落标题：\n"
                + "\n".join(
                    f"        - {name}：{', '.join(kws[:3])}..."
                    for name, kws in sections if name in missing
                )
                + "\n"
                "     2. 重新调 write_report 出新报告\n"
                "   合规依据：CSRC 信息披露公告 17 号 / 投行内部模板"
            )
            return GateDecision(
                verdict=verdict,
                reason=reason,
                gate_name="disclosure_completeness",
            )

        return make_simple_gate(
            name="disclosure_completeness", priority=80, evaluator=evaluate
        )


class InsiderInfoGate:
    """合规守门：扫描简报文本含"内幕 / 未公开"等关键词时 BLOCK conclude.

    实现 ``krow_agent_sdk.protocols.GatePlugin`` Protocol。

    真实业务价值：
    - 《证券法》第 51 条：禁止内幕信息知情人、获取内幕信息的人在内幕信息
      公开前买卖发行人证券、向他人泄露
    - 投行 junior analyst 偶尔会把"内部调研"信息混进简报 → 法务事故
    - LLM 也可能在 prompt 里看到"未公开"字样后照搬到输出
    - 必须扫描 conclude payload 一键阻断（fail-loud > fail-silent）
    """

    plugin_id = "fin_analyst.insider_gate"
    phase = "macro"

    def __init__(self, *, custom_keywords: list[str] | None = None) -> None:
        # 允许用户加自家公司机密关键词（如"未上市子公司"）
        kws = list(_INSIDER_KEYWORDS)
        if custom_keywords:
            kws.extend(custom_keywords)
        self._keywords = kws

    def _scan_text(self, text: str) -> list[str]:
        if not text:
            return []
        hits: list[str] = []
        text_lower = text.lower()
        for kw in self._keywords:
            if kw.lower() in text_lower:
                hits.append(kw)
        return hits

    def get_gate(self) -> Any:
        from krow_agent_sdk.protocols import (
            GateDecision,
            GateVerdict,
            make_simple_gate,
        )

        scan = self._scan_text

        def evaluate(parsed: dict, context: dict) -> Any:
            tool_results = context.get("recent_tool_results", []) or []
            scanned: list[tuple[str, list[str]]] = []
            for tr in tool_results:
                if not isinstance(tr, dict):
                    continue
                tool_name = tr.get("tool_name", "")
                if tool_name in (
                    "data_analyst_write_report",
                    "word_smart_export",
                ) or "write_report" in tool_name:
                    args = tr.get("args") or {}
                    body = args.get("content") or args.get("body") or ""
                    if not body:
                        fp = args.get("file_path") or args.get("path")
                        if fp:
                            try:
                                body = Path(fp).read_text(encoding="utf-8")
                            except Exception:  # noqa: BLE001
                                continue
                    if body:
                        hits = scan(body)
                        if hits:
                            scanned.append((tool_name, hits))

            if not scanned:
                return GateDecision(
                    verdict=GateVerdict.DEFER,
                    gate_name="insider_info",
                )

            all_hits: set[str] = set()
            for _, h in scanned:
                all_hits.update(h)
            return GateDecision(
                verdict=GateVerdict.BLOCK,
                reason=(
                    f"❌ 内幕信息红线：检测到投资简报含 {len(all_hits)} 个"
                    f"高风险关键词：{sorted(all_hits)}\n"
                    "   位置：write_report / word_smart_export 输出 markdown\n"
                    "   修法：\n"
                    "     1. 删除所有未公开 / 内幕字样段落，只用已公开年报数据\n"
                    "     2. 若必须引用内部数据，先确认信息已公开（年报、公告、会议纪要）\n"
                    "     3. 修改后重调 write_report\n"
                    "   合规依据：《证券法》第 51 条 / 内幕交易规制"
                ),
                gate_name="insider_info",
            )

        return make_simple_gate(
            name="insider_info", priority=90, evaluator=evaluate
        )


# ============================================================
# §9. HintPlugin（System 2 软提示：3σ 偏差 KPI 自动标注）
# ============================================================
#
# 设计哲学：
#   System 1（industry_baseline 工具）已经算好行业 mean / std；
#   HintPlugin 把"哪家公司哪个 KPI 偏离 3σ"推给 LLM 让其在简报里点出。
#   这是 System 2 软提示——LLM 可选择采纳（如某指标行业波动本身极大，
#   LLM 可不在简报里强调）；但默认推就是降低"漏掉亮点 / 漏掉风险"概率。


class AnomalyMetricHintPlugin:
    """检测 3σ 偏差 KPI 给 LLM 软提示（亮点 / 风险点候选）.

    实现 ``krow_agent_sdk.protocols.HintPlugin`` Protocol。

    工作机制：
    - SDK 每次 macro ReACT 决策前调 hint_for(context)
    - 扫描 ``recent_tool_results`` 找最新的 ``industry_baseline`` 输出
    - 对每个 KPI，找各公司值偏离均值 > 3σ 的（极端值）
    - 返回 markdown hint 段拼到 LLM prompt（"亮点 / 风险点候选清单"）

    业务价值：
    - LLM 凭感觉看 KPI 表无法区分"3% 偏差是噪音 / 30% 偏差是亮点 /
      300% 偏差是异常报错"——必须有 std 标尺
    - 投行简报最大价值在"找到行业内的极端值"——这恰好是 statistics 的核心
    """

    plugin_id = "fin_analyst.anomaly_hint"
    applicable_acts = ["financial_analyst"]

    def __init__(self, *, sigma_threshold: float = 2.0) -> None:
        """sigma_threshold: 偏离均值多少 σ 才提示（默认 2σ；3σ 信号更强但样本要求高）."""
        self._sigma = float(sigma_threshold)

    def hint_for(self, context: dict) -> str | None:
        tool_results = context.get("recent_tool_results", []) or []

        # 找最新的 industry_baseline 输出 + 最新的 normalize_kpi_table 表
        baseline_result: dict[str, Any] | None = None
        normalized_table: list[dict[str, Any]] = []
        for tr in reversed(tool_results):
            if not isinstance(tr, dict):
                continue
            name = tr.get("tool_name", "")
            result = tr.get("result", {}) or {}
            if (
                name == "financial_analyst_industry_baseline"
                and not baseline_result
                and result.get("ok")
            ):
                baseline_result = result
            elif (
                name == "financial_analyst_normalize_kpi_table"
                and not normalized_table
                and result.get("ok")
            ):
                normalized_table = result.get("table") or []
            if baseline_result and normalized_table:
                break

        if not baseline_result or not normalized_table:
            return None

        baselines = baseline_result.get("baselines", {})
        sigma = self._sigma

        anomalies: list[tuple[str, str, float, float, str]] = []
        # (company, kpi, value, deviation_sigma, direction)

        for kpi, base in baselines.items():
            mean_v = base.get("mean")
            std_v = base.get("std")
            if mean_v is None or std_v is None or std_v <= 0:
                continue
            for row in normalized_table:
                v = row.get(kpi)
                if not isinstance(v, (int, float)):
                    continue
                deviation = (v - mean_v) / std_v
                if abs(deviation) >= sigma:
                    direction = "高于" if deviation > 0 else "低于"
                    anomalies.append((
                        row.get("company", "?"), kpi, v, deviation, direction
                    ))

        if not anomalies:
            return (
                "## 行业基线对比（System 2 软提示）\n"
                f"- 没有任何 KPI 偏离行业均值超过 {sigma:.1f}σ — "
                "所有公司 KPI 在正常波动范围；写简报时可以说『行业整体一致』。\n"
            )

        # 按偏差大小排序（最显著的优先提示）
        anomalies.sort(key=lambda x: -abs(x[3]))
        lines = [
            f"## 行业基线对比（System 2 软提示，{sigma:.1f}σ 阈值）",
            f"以下 KPI 偏离行业均值超过 {sigma:.1f}σ → 投资简报里"
            "**强烈建议**单独点出（亮点 / 风险候选）：",
            "",
        ]
        # 限 top 8 防 prompt 膨胀
        for company, kpi, value, deviation, direction in anomalies[:8]:
            lines.append(
                f"- **{company}**：{kpi} = {value:.2f} "
                f"（{direction}行业均值 {abs(deviation):.1f}σ）"
            )
        if len(anomalies) > 8:
            lines.append(f"- ... 另有 {len(anomalies) - 8} 项偏差未列出（按 σ 降序取前 8）")
        return "\n".join(lines)


# ============================================================
# §10. EventListenerPlugin（投资简报合规审计留痕）
# ============================================================
#
# 与 data-analyst v2 AuditEventListener 的区别：
#   data-analyst：通用合规审计（PII / OutputPath 类）
#   financial：投资简报专属—— 额外记录 KPI 抽取调用 + Gate 拦截事件
#   （金融行业法务审计要求每次 BLOCK 必须留痕，事后可追溯）


class InvestmentMemoAuditListener:
    """投资简报审计留痕（金融行业合规要求）.

    实现 ``krow_agent_sdk.protocols.EventListenerPlugin`` Protocol。

    与 data-analyst.AuditEventListener 区别：
    - 重点关注 KPI 抽取记录（合规：每个 KPI 数值的来源 / 单位 / 币种必须可追溯）
    - 重点关注 Gate BLOCK 事件（合规：法务事后审计需要看哪些简报草稿被合规拦下来过）
    - 落 .audit.jsonl（与 data-analyst 同 SSOT 格式，方便 BI 统一接入）
    """

    plugin_id = "fin_analyst.audit_listener"

    def __init__(self, audit_log_path: str | Path) -> None:
        self._path = _normalize_path(audit_log_path)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("InvestmentMemoAuditListener: 创建父目录失败 %s", e)

    def get_subscriptions(self) -> list[dict[str, Any]]:
        return [
            {"topic": "tool.call_started", "handler": self._on_tool_call_started},
            {"topic": "tool.call_completed", "handler": self._on_tool_call_completed},
            {"topic": "gate.blocked", "handler": self._on_gate_blocked},
            {"topic": "agent.task_complete", "handler": self._on_task_complete},
            {"topic": "agent.task_failed", "handler": self._on_task_failed},
        ]

    def _append(self, record: dict[str, Any]) -> None:
        try:
            record.setdefault("timestamp", time.time())
            record.setdefault("timestamp_iso", time.strftime("%Y-%m-%dT%H:%M:%S"))
            record.setdefault("audit_kind", "financial_analyst")
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001
            logger.debug("InvestmentMemoAuditListener append failed: %s", exc)

    def _on_tool_call_started(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        tool_name = payload.get("tool_name", "")
        # 重点关注 KPI 抽取调用（金融审计需追溯）
        is_kpi_extract = tool_name == "financial_analyst_extract_kpi_from_pdf"
        self._append({
            "kind": "tool_call_started",
            "tool_name": tool_name,
            "args": payload.get("args"),
            "highlight": "kpi_extract" if is_kpi_extract else None,
        })

    def _on_tool_call_completed(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        tool_name = payload.get("tool_name", "")
        result = payload.get("result")
        # KPI 抽取的结果完整保留（合规：可追溯每个数字的出处）
        kpi_summary: dict[str, Any] | None = None
        if tool_name == "financial_analyst_extract_kpi_from_pdf" and isinstance(result, dict):
            kpis = result.get("kpis") or {}
            kpi_summary = {
                k: {
                    "value": v.get("value"),
                    "unit": v.get("unit"),
                    "currency": v.get("currency"),
                    "source_window": (v.get("source_window") or "")[:80],
                }
                for k, v in kpis.items()
            }
        elif isinstance(result, dict):
            kpi_summary = {
                k: result.get(k) for k in ("ok", "summary", "error")
                if k in result
            }
        self._append({
            "kind": "tool_call_completed",
            "tool_name": tool_name,
            "ok": payload.get("ok", True),
            "elapsed_ms": payload.get("elapsed_ms"),
            "result_summary": kpi_summary,
        })

    def _on_gate_blocked(self, event: Any) -> None:
        # 金融行业关键审计点：每次 Gate BLOCK 必须留档
        payload = getattr(event, "payload", {}) or {}
        self._append({
            "kind": "gate_blocked",
            "gate_name": payload.get("gate_name"),
            "reason_excerpt": (payload.get("reason") or "")[:200],
            "compliance_event": True,
        })

    def _on_task_complete(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        self._append({
            "kind": "task_complete",
            "summary": payload.get("summary"),
            "step_count": payload.get("step_count"),
        })

    def _on_task_failed(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        self._append({
            "kind": "task_failed",
            "reason": payload.get("reason"),
        })


# ============================================================
# §11. ObservabilityPlugin（Prometheus push gateway 集成）
# ============================================================
#
# 这是 v3 cookbook 必演示的能力—— v2 没演示 ObservabilityPlugin。
#
# 真实业务问题：
#   投行内 BI dashboard 需要看：
#   - 平均 KPI 抽取耗时（用于 SLA 跟踪）
#   - 每天处理的简报数（用于 capacity planning）
#   - Gate BLOCK 率（用于发现合规风险趋势）
#   - LLM token 消耗（用于成本控制）
#
# 这些数据必须以 Prometheus metrics 形式 export 到 Grafana / VictoriaMetrics。
# Krow SDK 内部已经 record 这些事件（``modules/observability/``）；
# ObservabilityPlugin 的职责是把它们 forward 到外部 sink。


class FinancialMetricsObservabilityPlugin:
    """把 Krow agent 内部 metrics forward 到 Prometheus push gateway.

    实现 ``krow_agent_sdk.protocols.ObservabilityPlugin`` Protocol。

    工作机制：
    - SDK build() 时调 register(facade) 注入 ObservabilityFacade
    - plugin 在 register() 内调 facade.add_metric_sink(callback)
      让 SDK 内每次 metric event 都调 callback
    - callback 把 metric push 到 Prometheus push gateway HTTP 端点

    Demo 模式（无 prometheus-client 时）：
    - 自动降级为 stdout 输出（仍演示完整数据流；不阻塞 cookbook 跑）
    - 真实生产请装 ``prometheus-client>=0.19``
    """

    plugin_id = "fin_analyst.observability"

    def __init__(
        self,
        *,
        push_gateway_url: str | None = None,
        job_name: str = "krow_financial_analyst",
        verbose: bool = False,
    ) -> None:
        """
        Args:
            push_gateway_url: Prometheus pushgateway URL (e.g.
                "http://prometheus-pushgateway.bi.internal:9091")。
                None → 降级为 stdout demo 模式。
            job_name: Prometheus job 标签
            verbose: True 时每个 metric 都打印到 stdout（debug 用）
        """
        self._url = push_gateway_url
        self._job = job_name
        self._verbose = bool(verbose)

        # 尝试装 prometheus-client，失败则降级
        self._registry = None
        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}
        self._available = False
        try:
            from prometheus_client import (
                CollectorRegistry,
                Counter,
                Histogram,
            )
            self._Counter = Counter
            self._Histogram = Histogram
            self._registry = CollectorRegistry()
            self._available = True
        except ImportError:
            logger.info(
                "prometheus-client 未装 → ObservabilityPlugin 降级 stdout 模式 "
                "（pip install prometheus-client 启用真实 push gateway 上报）"
            )

    def register(self, observability_facade: Any) -> None:
        """SDK 注入 facade，本 plugin 注册 metric callback."""
        observability_facade.add_metric_sink(self._on_metric)
        observability_facade.add_audit_sink(self._on_audit)

    def _ensure_counter(self, name: str, help_text: str, labels: list[str]) -> Any:
        if name in self._counters:
            return self._counters[name]
        if not self._available:
            return None
        c = self._Counter(name, help_text, labelnames=labels, registry=self._registry)
        self._counters[name] = c
        return c

    def _ensure_histogram(self, name: str, help_text: str, labels: list[str]) -> Any:
        if name in self._histograms:
            return self._histograms[name]
        if not self._available:
            return None
        h = self._Histogram(name, help_text, labelnames=labels, registry=self._registry)
        self._histograms[name] = h
        return h

    def _on_metric(self, name: str, value: float, labels: dict[str, Any]) -> None:
        """SDK 内每次 metric event 走这里."""
        if self._verbose or not self._available:
            with suppress(Exception):
                safe_labels = {
                    k: v for k, v in labels.items()
                    if isinstance(v, (str, int, float, bool))
                }
                print(f"[obs:metric] {name}={value} labels={safe_labels}")
        if not self._available:
            return

        # 名字归一化（Prometheus 不允许 . / -；用 _ 替换）
        prom_name = re.sub(r"[^\w]", "_", name).strip("_")
        if not prom_name:
            return

        # 简单启发：counter（_total / _count 后缀）vs histogram（_seconds / _ms）
        is_histogram = any(
            prom_name.endswith(suffix)
            for suffix in ("_seconds", "_ms", "_duration", "_elapsed")
        )

        # 统一从 labels 提取标签 keys（值类型必须是 str）
        label_keys = sorted(
            k for k, v in labels.items()
            if isinstance(v, (str, int, float, bool))
        )
        label_values = {k: str(labels[k]) for k in label_keys}

        try:
            if is_histogram:
                hist = self._ensure_histogram(prom_name, name, label_keys)
                if hist is not None:
                    if label_values:
                        hist.labels(**label_values).observe(float(value))
                    else:
                        hist.observe(float(value))
            else:
                counter = self._ensure_counter(prom_name, name, label_keys)
                if counter is not None:
                    if label_values:
                        counter.labels(**label_values).inc(float(value))
                    else:
                        counter.inc(float(value))
        except Exception as exc:  # noqa: BLE001
            logger.debug("metric forward failed: %s", exc)

        # 推到 push gateway
        if self._url:
            try:
                from prometheus_client import push_to_gateway
                push_to_gateway(self._url, job=self._job, registry=self._registry)
            except Exception as exc:  # noqa: BLE001
                logger.debug("push_to_gateway failed: %s", exc)

    def _on_audit(self, event_kind: str, payload: dict[str, Any]) -> None:
        """audit sink：把高风险 audit 事件计数到 prometheus."""
        if event_kind == "gate_blocked":
            counter = self._ensure_counter(
                "financial_gate_blocked_total",
                "Number of times a Gate blocked conclude in financial-analyst",
                ["gate_name"],
            )
            if counter is not None:
                gate_name = str(payload.get("gate_name", "unknown"))
                counter.labels(gate_name=gate_name).inc()
        if self._verbose:
            with suppress(Exception):
                print(f"[obs:audit] {event_kind} payload={payload}")


__all__ = [
    # tools (functions)
    "extract_kpi_from_pdf",
    "normalize_kpi_table",
    "industry_baseline",
    "radar_chart_svg",
    "valuation_anchor",
    # constants
    "KPI_DICT",
    "UNIT_DICT",
    # plugins
    "FinancialAnalystToolPlugin",
    "FinancialAnalystACTPlugin",
    "DisclosureCompletenessGate",
    "InsiderInfoGate",
    "AnomalyMetricHintPlugin",
    "InvestmentMemoAuditListener",
    "FinancialMetricsObservabilityPlugin",
]
