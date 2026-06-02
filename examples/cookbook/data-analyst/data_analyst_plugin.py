"""Data-analyst cookbook plugin SSOT (full version).

3 类 plugin 实现：
- DataAnalystToolPlugin: 注册 4 个 System 1 工具
  - data_analyst_read_csv：读 CSV（带 encoding 自动降级）
  - data_analyst_compute_stats：deterministic 统计（mean/std/missing/top5）
  - data_analyst_pick_palette：按数据类型查表配色（hex colors）
  - data_analyst_write_report：落盘 markdown
- DataAnalystACTPlugin: 自定义 "data_analyst" ACT 让 LLM 自动选入分析流
- DataAnalystProgressListener: 监听 EventBus 给 CLI 用户实时进度反馈

设计原则（与 advanced-development-guide.md / AGENTS.md §0.2 对齐）：
- **SSOT 不重复造轮子**：PDF 输出**复用** Krow 内置 ``word_smart_export`` 工具
  （SSOT = ``modules/tools/builtins/document_renderer.py:MarkdownDocumentRenderer``，
  自带 CJK 字体处理 / reportlab backend / 完整样式系统）。
  cookbook 教学点：**外部 plugin 与 Krow builtin 工具自动同 ToolManager 单例**——
  你写自己的 plugin 不等于"重头造每件事"，应该和内置工具组合。
- TURBO 边界：所有工具是 System 1（不调 LLM；deterministic；unit-test 100% 覆盖）
- 错误信息：黄金模板（原因 + 位置 + 修法）+ 错误降级演示（encoding fallback）
- 输入鲁棒：path 接受 str/Path、encoding 接受多种大小写
- 输出格式：扁平 JSON + summary 字段在首位（LLM 友好）
- 配色查表：按 data type → hex palette（颜色对查表，不让 LLM 凭感觉配）

v2 升级（2026-05-18，auditor scope）：
本文件从原 4 工具 demo 升级为完整 SDK 能力演示——加入 anomaly detection /
correlation matrix / GatePlugin × 2 / HintPlugin / AuditEventListener / BudgetSpec。
v2 教学价值：演示外部 plugin 如何在保持 SSOT 不重复造轮子前提下，仍然能补全
"内置工具+一个 ACT" 无法满足的真实业务能力（异常检测、PII 守门、合规审计日志）。
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# §1. 工具实现（System 1）
# ============================================================


def _normalize_path(p: str | Path) -> Path:
    """LLM 经常传 str / 反斜杠 / 相对路径 — 统一归一为 absolute Path。"""
    if isinstance(p, str):
        p = Path(p)
    return p.expanduser().resolve()


def _golden_error(
    msg: str, *, where: str, fixes: Iterable[str], related: Iterable[str] = ()
) -> dict[str, Any]:
    """统一黄金错误模板（advanced-development-guide §3.5）."""
    parts = [f"❌ {msg}", f"   位置：{where}"]
    parts.append("   修法：")
    for i, fix in enumerate(fixes, 1):
        parts.append(f"     {i}. {fix}")
    if related:
        parts.append(f"   相关：{' / '.join(related)}")
    return {"ok": False, "error": "\n".join(parts)}


def read_csv(path: str | Path, encoding: str = "utf-8") -> dict[str, Any]:
    """读 CSV 拿 metadata + 前 10 行预览。

    Args:
        path: CSV 路径（支持 str / Path / 相对路径）
        encoding: 编码（自动归一大小写；常见 utf-8 / gbk / cp1252）

    Returns:
        dict 含 ok/summary/columns/row_count/dtypes/preview_rows 平铺字段
    """
    try:
        import pandas as pd
    except ImportError:
        return _golden_error(
            "pandas 未装",
            where="data-analyst cookbook 依赖 pandas",
            fixes=["pip install pandas", "或 cd cookbook/data-analyst && pip install -e ."],
        )

    p = _normalize_path(path)
    if not p.exists():
        return _golden_error(
            f"CSV 文件不存在：{p}",
            where=f"path={path}",
            fixes=[
                "检查路径拼写",
                "用绝对路径而非相对路径",
                "确认 CSV 是否在 sample_data/ 目录下",
            ],
            related=["read_csv", "write_report"],
        )

    enc = (encoding or "utf-8").lower().strip()
    df = None
    fallback_used: str | None = None
    fallback_chain = [enc] + [c for c in ("utf-8", "utf-8-sig", "gbk", "cp1252") if c != enc]
    last_err: Exception | None = None
    for candidate in fallback_chain:
        try:
            df = pd.read_csv(p, encoding=candidate)
            if candidate != enc:
                fallback_used = candidate
                logger.warning(
                    "encoding 降级：%s 失败，自动 fallback → %s（成功）", enc, candidate
                )
            break
        except UnicodeDecodeError as e:
            last_err = e
            continue
        except Exception as e:
            return _golden_error(
                f"读 CSV 失败：{e}",
                where=f"path={p}",
                fixes=["检查 CSV 是否合法 / 是否含 BOM / 是否被锁定"],
                related=["read_csv"],
            )
    if df is None:
        return _golden_error(
            f"CSV 所有编码尝试都失败（试过 {' → '.join(fallback_chain)}）",
            where=f"path={p}",
            fixes=[
                "用 chardet/cchardet 检测真实编码",
                "若是日韩 CSV：试 encoding='shift_jis' / 'euc-kr'",
                f"最后一次错误：{last_err}",
            ],
            related=["read_csv"],
        )

    summary_parts = [
        f"读到 CSV：{len(df)} 行 × {len(df.columns)} 列",
        f"列名：{', '.join(df.columns[:8])}"
        f"{' ...' if len(df.columns) > 8 else ''}",
    ]
    if fallback_used:
        summary_parts.insert(
            1, f"⚠️  encoding 降级：声明 {enc} 失败，实际用 {fallback_used} 解析成功"
        )

    return {
        "ok": True,
        "summary": "；".join(summary_parts),
        "path": str(p),
        "row_count": len(df),
        "columns": list(df.columns),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "preview_rows": df.head(10).to_dict(orient="records"),
        "encoding_used": fallback_used or enc,
        "encoding_fallback_triggered": fallback_used is not None,
    }


def compute_stats(path: str | Path, encoding: str = "utf-8") -> dict[str, Any]:
    """对数值列算统计 + 对分类列算 value_counts top 5（System 1 deterministic）."""
    try:
        import pandas as pd
    except ImportError:
        return _golden_error(
            "pandas 未装",
            where="compute_stats 依赖 pandas",
            fixes=["pip install pandas"],
        )

    p = _normalize_path(path)
    if not p.exists():
        return _golden_error(
            f"CSV 文件不存在：{p}",
            where=f"path={path}",
            fixes=["先调 read_csv 验证路径", "或检查路径拼写"],
        )

    try:
        df = pd.read_csv(p, encoding=(encoding or "utf-8").lower())
    except Exception as e:
        return _golden_error(
            f"读 CSV 失败：{e}",
            where=f"path={p}",
            fixes=["先调 read_csv 看错误细节"],
        )

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = [c for c in df.columns if c not in numeric_cols]

    numeric_stats = {}
    for c in numeric_cols:
        s = df[c].dropna()
        if len(s) == 0:
            continue
        numeric_stats[c] = {
            "count": int(len(s)),
            "mean": float(s.mean()),
            "std": float(s.std()) if len(s) > 1 else 0.0,
            "min": float(s.min()),
            "max": float(s.max()),
            "missing_count": int(df[c].isna().sum()),
        }

    cat_stats = {}
    for c in cat_cols:
        vc = df[c].value_counts(dropna=False).head(5)
        cat_stats[c] = {
            "unique_count": int(df[c].nunique(dropna=False)),
            "top5": {str(k): int(v) for k, v in vc.items()},
            "missing_count": int(df[c].isna().sum()),
        }

    return {
        "ok": True,
        "summary": (
            f"统计完成：数值列 {len(numeric_cols)} 个，分类列 {len(cat_cols)} 个，"
            f"总缺失值 {int(df.isna().sum().sum())}"
        ),
        "row_count": len(df),
        "numeric_stats": numeric_stats,
        "categorical_stats": cat_stats,
    }


# ============================================================
# §1.4 异常检测工具（v2 新增；Krow 内置无此能力）
# ============================================================
#
# 为什么需要这个工具？
# - Krow 内置工具池**没有任何异常检测能力**（无 IsolationForest / IQR / z-score）
# - LLM 凭感觉判断 "异常值" 不可靠（容易把正常长尾说成异常 / 把异常说成离群点）
# - sklearn IsolationForest 需要拟合 + predict 两步，LLM 用 code_executor 跑容易出错
#   （随机种子、contamination 参数、return decision_function 还是 predict）
# - 工具化后：deterministic / 可 unit-test / 可记 audit log
#
# 设计：默认走 IQR（pandas-only，无依赖）；method="isolation_forest" 时才需 sklearn

_ANOMALY_METHODS = ("iqr", "zscore", "isolation_forest")


def detect_anomalies(
    path: str | Path,
    method: str = "iqr",
    contamination: float = 0.05,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    """对 CSV 数值列做异常检测（System 1 deterministic）.

    Args:
        path: CSV 路径
        method: ``iqr`` (默认；pandas-only)/ ``zscore`` (|z|>3) / ``isolation_forest``
                (需 sklearn ; 无监督异常检测；适合多列联合异常)
        contamination: ``isolation_forest`` 时的预期异常占比（0.01-0.5）
        encoding: CSV 编码

    Returns:
        dict 含 ok / summary / method / total_rows / anomaly_count /
        anomaly_indices / per_column_anomaly_count / anomaly_score（仅 IF）
    """
    try:
        import pandas as pd
    except ImportError:
        return _golden_error(
            "pandas 未装",
            where="detect_anomalies 依赖 pandas",
            fixes=["pip install pandas"],
        )

    p = _normalize_path(path)
    if not p.exists():
        return _golden_error(
            f"CSV 文件不存在：{p}",
            where=f"path={path}",
            fixes=["先调 read_csv 验证路径"],
        )

    m = (method or "iqr").lower().strip()
    if m not in _ANOMALY_METHODS:
        return _golden_error(
            f"method={method!r} 不支持",
            where=f"detect_anomalies(method={method})",
            fixes=[
                f"必须是 {' / '.join(_ANOMALY_METHODS)} 之一",
                "IQR：单列规则；快；解释性好",
                "zscore：|z|>3 规则；要求列近似正态分布",
                "isolation_forest：多列联合异常；需 sklearn",
            ],
        )

    if not isinstance(contamination, (int, float)) or not (0.001 <= contamination <= 0.5):
        return _golden_error(
            f"contamination={contamination!r} 不合法",
            where=f"detect_anomalies(contamination={contamination})",
            fixes=["范围 0.001-0.5；常用 0.05（5%）"],
        )

    try:
        df = pd.read_csv(p, encoding=(encoding or "utf-8").lower())
    except Exception as e:
        return _golden_error(
            f"读 CSV 失败：{e}",
            where=f"path={p}",
            fixes=["先调 read_csv 看错误细节"],
        )

    numeric_df = df.select_dtypes(include="number")
    if numeric_df.shape[1] == 0:
        return _golden_error(
            "CSV 无数值列，无法做异常检测",
            where=f"path={p}",
            fixes=[
                "先调 compute_stats 看列类型",
                "若所有列都是字符串：考虑做分类列的低频值检测（本工具不支持）",
            ],
        )

    anomaly_indices: list[int] = []
    per_column_count: dict[str, int] = {}
    anomaly_score: dict[str, float] | None = None

    if m == "iqr":
        for c in numeric_df.columns:
            s = numeric_df[c].dropna()
            if len(s) < 4:
                continue
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            mask = (numeric_df[c] < lo) | (numeric_df[c] > hi)
            col_indices = numeric_df.index[mask].tolist()
            per_column_count[c] = len(col_indices)
            anomaly_indices.extend(col_indices)
        anomaly_indices = sorted(set(anomaly_indices))

    elif m == "zscore":
        for c in numeric_df.columns:
            s = numeric_df[c].dropna()
            if len(s) < 2 or s.std() == 0:
                continue
            z = (numeric_df[c] - s.mean()).abs() / s.std()
            mask = z > 3
            col_indices = numeric_df.index[mask].tolist()
            per_column_count[c] = len(col_indices)
            anomaly_indices.extend(col_indices)
        anomaly_indices = sorted(set(anomaly_indices))

    else:  # isolation_forest
        try:
            from sklearn.ensemble import IsolationForest
        except ImportError:
            return _golden_error(
                "sklearn 未装",
                where="detect_anomalies(method='isolation_forest')",
                fixes=[
                    "pip install scikit-learn",
                    "或改用 method='iqr' / 'zscore'（仅依赖 pandas/numpy）",
                ],
            )
        clean = numeric_df.dropna()
        if len(clean) < 10:
            return _golden_error(
                f"isolation_forest 至少需 10 个无缺失行，当前 {len(clean)}",
                where=f"path={p}",
                fixes=["改用 method='iqr'", "或先填补缺失值"],
            )
        clf = IsolationForest(
            contamination=float(contamination), random_state=42, n_estimators=100
        )
        pred = clf.fit_predict(clean.values)
        scores = clf.decision_function(clean.values)
        mask_idx = clean.index[pred == -1].tolist()
        anomaly_indices = sorted(mask_idx)
        anomaly_score = {
            str(idx): float(scores[i]) for i, idx in enumerate(clean.index)
        }
        per_column_count = {c: int((numeric_df.loc[mask_idx, c].notna()).sum()) for c in numeric_df.columns}

    result = {
        "ok": True,
        "summary": (
            f"异常检测完成（method={m}）："
            f"{len(anomaly_indices)}/{len(df)} 行被标记为异常"
            f"（{len(anomaly_indices) / max(1, len(df)) * 100:.1f}%）"
        ),
        "method": m,
        "total_rows": int(len(df)),
        "anomaly_count": int(len(anomaly_indices)),
        "anomaly_rate": round(len(anomaly_indices) / max(1, len(df)), 4),
        "anomaly_indices": anomaly_indices[:50],  # 截断防 LLM context 爆
        "anomaly_indices_truncated": len(anomaly_indices) > 50,
        "per_column_anomaly_count": per_column_count,
    }
    if anomaly_score is not None:
        sorted_scores = sorted(anomaly_score.items(), key=lambda x: x[1])[:20]
        result["lowest_score_indices"] = dict(sorted_scores)
    return result


# ============================================================
# §1.5 相关性矩阵工具（v2 新增；防 LLM 凭感觉算 corr）
# ============================================================
#
# 为什么不让 LLM 用 code_executor 自己跑 pandas df.corr() ？
# - LLM 可能用错相关系数类型（pearson 假设线性 + 正态；spearman 是秩相关）
# - LLM 可能在含 NaN 的列上漏 .dropna()，导致结果错误
# - 工具化后保证 deterministic + 自动 top-N + audit log


def compute_correlation(
    path: str | Path,
    method: str = "pearson",
    top_n: int = 5,
    encoding: str = "utf-8",
) -> dict[str, Any]:
    """对 CSV 数值列算相关性矩阵 + 提取 top N 强相关对（System 1 deterministic）.

    Args:
        path: CSV 路径
        method: ``pearson`` (线性相关；默认) / ``spearman`` (秩相关；非线性单调更稳)
        top_n: 返回 top N 强相关对（按 |r| 降序）
        encoding: CSV 编码
    """
    try:
        import pandas as pd
    except ImportError:
        return _golden_error(
            "pandas 未装",
            where="compute_correlation 依赖 pandas",
            fixes=["pip install pandas"],
        )

    p = _normalize_path(path)
    if not p.exists():
        return _golden_error(
            f"CSV 文件不存在：{p}",
            where=f"path={path}",
            fixes=["先调 read_csv 验证路径"],
        )

    m = (method or "pearson").lower().strip()
    if m not in ("pearson", "spearman"):
        return _golden_error(
            f"method={method!r} 不支持",
            where=f"compute_correlation(method={method})",
            fixes=["pearson（线性）/ spearman（秩相关）"],
        )

    if not isinstance(top_n, int) or top_n < 1:
        return _golden_error(
            f"top_n 必须是 ≥1 整数，你传了 {top_n!r}",
            where=f"compute_correlation(top_n={top_n})",
            fixes=["top_n=5（默认）"],
        )

    try:
        df = pd.read_csv(p, encoding=(encoding or "utf-8").lower())
    except Exception as e:
        return _golden_error(
            f"读 CSV 失败：{e}",
            where=f"path={p}",
            fixes=["先调 read_csv 看错误细节"],
        )

    numeric_df = df.select_dtypes(include="number").dropna()
    if numeric_df.shape[1] < 2:
        return _golden_error(
            f"至少需 2 个数值列才能算相关性，当前 {numeric_df.shape[1]} 列",
            where=f"path={p}",
            fixes=["先调 compute_stats 看列类型", "确认 CSV 含多个数值列"],
        )

    corr = numeric_df.corr(method=m).round(4)

    pairs: list[tuple[str, str, float]] = []
    cols = corr.columns.tolist()
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            r = float(corr.loc[a, b])
            if r == r:  # filter NaN
                pairs.append((a, b, r))
    pairs.sort(key=lambda x: abs(x[2]), reverse=True)
    top_pairs = [
        {"col_a": a, "col_b": b, "r": r, "abs_r": round(abs(r), 4)}
        for a, b, r in pairs[:top_n]
    ]

    return {
        "ok": True,
        "summary": (
            f"相关性矩阵完成（method={m}，{len(cols)} 列）；"
            f"top {len(top_pairs)} 强相关对："
            + "、".join(f"{p['col_a']}↔{p['col_b']}={p['r']}" for p in top_pairs[:3])
        ),
        "method": m,
        "n_columns": len(cols),
        "n_rows_used": int(len(numeric_df)),
        "matrix": {a: {b: float(corr.loc[a, b]) for b in cols} for a in cols},
        "top_pairs": top_pairs,
    }


# ============================================================
# §1.6 配色查表工具（System 1 deterministic）
# ============================================================
#
# 数据可视化的配色不应该让 LLM 凭感觉配 —— 见 AGENTS.md §0.1 TURBO 哲学：
# "颜色对查表是 System 1 工具的范例（pptx_color_pair_picker）"。
#
# 这里 demo 一个最小 palette：按数据类型查色，调用方按 column index 取色。
# 真实业务用 d3.scale.category10 / Tableau / ggplot 等成熟 palette。

# Tableau 10-color categorical palette（业界共识；色盲友好）
_PALETTE_CATEGORICAL = [
    "#4E79A7",  # blue
    "#F28E2B",  # orange
    "#E15759",  # red
    "#76B7B2",  # teal
    "#59A14F",  # green
    "#EDC948",  # yellow
    "#B07AA1",  # purple
    "#FF9DA7",  # pink
    "#9C755F",  # brown
    "#BAB0AC",  # gray
]

# Sequential blue palette（数值列 / heatmap 用；ColorBrewer Blues 9）
_PALETTE_SEQUENTIAL = [
    "#F7FBFF",
    "#DEEBF7",
    "#C6DBEF",
    "#9ECAE1",
    "#6BAED6",
    "#4292C6",
    "#2171B5",
    "#08519C",
    "#08306B",
]

# Diverging red-blue palette（带正负的指标，如相关系数）
_PALETTE_DIVERGING = [
    "#67001F",
    "#B2182B",
    "#D6604D",
    "#F4A582",
    "#FDDBC7",
    "#F7F7F7",
    "#D1E5F0",
    "#92C5DE",
    "#4393C3",
    "#2166AC",
    "#053061",
]

_PALETTE_TABLE = {
    "categorical": _PALETTE_CATEGORICAL,
    "sequential": _PALETTE_SEQUENTIAL,
    "diverging": _PALETTE_DIVERGING,
}


def pick_palette(palette_kind: str = "categorical", n: int = 10) -> dict[str, Any]:
    """按数据类型查表返回 hex 色值 list（System 1 deterministic / 不调 LLM）.

    Args:
        palette_kind: ``categorical`` / ``sequential`` / ``diverging`` 之一
        n: 要几个颜色（自动循环或截取）

    Returns:
        dict 含 ok / summary / colors（list of hex）/ palette_kind / n
    """
    kind = (palette_kind or "categorical").lower().strip()
    if kind not in _PALETTE_TABLE:
        return _golden_error(
            f"不支持的 palette_kind={kind}",
            where=f"pick_palette(palette_kind={palette_kind})",
            fixes=[
                f"必须是 {' / '.join(sorted(_PALETTE_TABLE))} 之一",
                "数值列分布 → sequential",
                "分类列对比 → categorical",
                "正负指标（如相关系数）→ diverging",
            ],
            related=["pick_palette"],
        )

    if not isinstance(n, int) or n < 1:
        return _golden_error(
            f"n 必须是 ≥1 的整数，你传了 {n!r}",
            where=f"pick_palette(n={n})",
            fixes=["n=10（默认）", "categorical 上限 10、sequential 上限 9、diverging 上限 11"],
        )

    base = _PALETTE_TABLE[kind]
    if n <= len(base):
        colors = base[:n]
    else:
        colors = [base[i % len(base)] for i in range(n)]

    return {
        "ok": True,
        "summary": f"返回 {n} 个 {kind} palette 颜色（业界共识 palette；色盲友好）",
        "palette_kind": kind,
        "n": n,
        "colors": colors,
    }


# ============================================================
# §1.6 写报告 + PDF 渲染工具
# ============================================================


def _extract_h1_or_fallback(markdown_text: str, fallback: str) -> str:
    """从 markdown 提取首个 H1; 若无则用 fallback (通常 output_path.stem)."""
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return fallback


def _normalize_bold_headings(markdown_text: str) -> str:
    """独占一行的 ``**xxx**`` → ``## xxx`` (handler 内 System 1 normalize).

    教训驱动:
    qwen3.7-max 等模型在某些 cookbook 的 ACT 约束不足时, 会把章节标题写成
    ``**章节名**`` 而非 ``## 章节名``. 不靠模型自律 → handler 后处理 normalize.
    """
    import re

    out_lines = []
    for line in markdown_text.splitlines():
        stripped = line.strip()
        # 匹配独占一行的 **xxx**（前后无其他字符）
        m = re.fullmatch(r"\*\*(.+?)\*\*", stripped)
        if m:
            heading = m.group(1).strip()
            # 启发式: 跳过明显是"加粗短语"而非"章节标题"的内容（含句号 / 太长）
            if len(heading) <= 60 and not heading.endswith("。") and not heading.endswith("."):
                out_lines.append(f"## {heading}")
                continue
        out_lines.append(line)
    return "\n".join(out_lines)


def _dedupe_leading_h1(markdown_text: str, expected_title: str) -> str:
    """若 markdown 顶部有 `# {expected_title}` 与下一行又一个 `# 同标题` → 去重.

    具体场景: handler 旧实现拼 ``# {title}\n\n{content}``, 但 LLM 在 content
    里又自己写了 ``# {title}``, 结果 H1 出现 2 次 (开发者 zzp run1/run2 都复现).
    新实现走"成品契约" + 此 normalize 一并治理.
    """
    lines = markdown_text.splitlines()
    if len(lines) < 3:
        return markdown_text
    # 找前 5 行中所有 `# ` 起头
    h1_indices = [
        i for i, ln in enumerate(lines[:8])
        if ln.strip().startswith("# ") and not ln.strip().startswith("## ")
    ]
    if len(h1_indices) <= 1:
        return markdown_text
    # 保留第 1 个 H1，删除其余（仅当其它 H1 的文本 normalize 后与第 1 个或 expected_title 相同/相似）
    first_idx = h1_indices[0]
    first_text = lines[first_idx].strip()[2:].strip().lower()
    expected_lc = expected_title.strip().lower()
    keep = set(range(len(lines)))
    for idx in h1_indices[1:]:
        dup_text = lines[idx].strip()[2:].strip().lower()
        if dup_text == first_text or dup_text == expected_lc:
            keep.discard(idx)
    return "\n".join(lines[i] for i in sorted(keep))


def write_report(
    output_path: str | Path,
    markdown: str | None = None,
    title: str | None = None,
    content: str | None = None,
) -> dict[str, Any]:
    """把 markdown 报告写到磁盘（**成品契约 + handler 后处理 normalize**, System 1, 不调 LLM）.

    教训驱动:

    旧实现是 "零件契约"——把单一产物 (markdown 文档) 拆成两个 required 字段
    ``title`` + ``content`` 让 LLM 分别填, 且 handler 内拼 ``# {title}\\n{content}``.
    Qwen3.7-max 实测 2 次都漏 ``title`` (短路失败 → 降级 React) + content 自带
    ``#`` 导致 H1 重复 2 次. 不是模型 bug, 是接口契约引诱模型犯错.

    新实现接受两种调用形态 (向后兼容):

    1. **成品契约 (推荐)**: 只传 ``markdown`` 单字段 (完整 markdown 含 # 标题).
       title 从 ``markdown`` 首个 H1 自动提取; 无 H1 则用 ``output_path.stem``.
    2. **零件契约 (老调用方兼容)**: 传 ``title`` + ``content`` 双字段.
       handler 自动拼接, 但仍跑 H1 去重 + bold→heading normalize.

    无论哪种形态, handler 一律跑两道 System 1 normalize:
       a. ``_normalize_bold_headings``: 独占一行的 ``**xxx**`` → ``## xxx``
       b. ``_dedupe_leading_h1``: 防 H1 重复
    """
    p = _normalize_path(output_path)

    # 推断 markdown text + title (向后兼容两种形态)
    if markdown is not None and markdown.strip():
        # 成品契约
        markdown_text = markdown
        effective_title = _extract_h1_or_fallback(markdown_text, fallback=p.stem)
        # 若 markdown 没有 H1, 自动在头部补一个 (从 fallback 推导)
        if not _has_leading_h1(markdown_text):
            markdown_text = f"# {effective_title}\n\n{markdown_text.strip()}\n"
    elif content is not None and content.strip():
        # 零件契约 (老调用方 / LLM 漏 title 时 fallback 用 output_path.stem)
        effective_title = (title or "").strip() or _extract_h1_or_fallback(
            content, fallback=p.stem,
        )
        # 若 content 已自带 H1, 不再外层套 # title (防 H1 重复 root cause)
        if _has_leading_h1(content):
            markdown_text = content.strip() + "\n"
        else:
            markdown_text = f"# {effective_title}\n\n{content.strip()}\n"
    else:
        return _golden_error(
            "缺少报告内容: 必须传 ``markdown`` (成品契约, 推荐) 或 ``content`` (零件契约, 老路径)",
            where=f"output_path={p}",
            fixes=[
                "推荐用法 (成品契约): write_report(output_path='r.md', markdown='# 标题\\n正文...')",
                "兼容用法 (零件契约): write_report(output_path='r.md', title='标题', content='正文...')",
            ],
        )

    # System 1 后处理 normalize (不靠模型自律)
    markdown_text = _normalize_bold_headings(markdown_text)
    markdown_text = _dedupe_leading_h1(markdown_text, expected_title=effective_title)

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(markdown_text, encoding="utf-8")
    except OSError as e:
        return _golden_error(
            f"写文件失败: {e}",
            where=f"output_path={p}",
            fixes=[
                "检查父目录是否存在 / 是否有写权限",
                "改成绝对路径而非相对路径",
                "确认磁盘有空间",
            ],
        )

    return {
        "ok": True,
        "summary": f"报告已写入 {p}（{p.stat().st_size} 字节）",
        "output_path": str(p),
        "size_bytes": p.stat().st_size,
        "effective_title": effective_title,
    }


def _has_leading_h1(markdown_text: str) -> bool:
    """前 5 行是否含独立 `# ` H1（不含 ## / ### 等）。"""
    for line in markdown_text.splitlines()[:5]:
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return True
    return False


# ============================================================
# §1.7 PDF 输出策略：复用 Krow 内置 word_smart_export
# ============================================================
#
# **不要在这里写 render_pdf 工具**——违反 AGENTS.md §0.2 SSOT 原则。
#
# Krow 主应用内置 ``word_smart_export`` 工具（SSOT = ``MarkdownDocumentRenderer``，
# 在 ``modules/tools/builtins/document_renderer.py``），已支持 markdown → PDF：
#   - reportlab backend（业界 PDF 库）
#   - 自带 CJK 字体处理（中文不出豆腐块）
#   - 完整样式系统（heading 6 级 / table / blockquote / code block / image）
#   - 已注册到 ToolManager 单例
#
# 关键 SDK 教学点：**ToolManager 是全局单例**——
# 外部 SDK plugin（你写的）和 Krow 内置工具（word_smart_export 等）共享同一个 ToolManager。
# 你 build agent 时不需要"自己 import Krow 内部模块"，
# **只要在 ACT extended.md 里告诉 LLM"出 PDF 就调 word_smart_export"，
# LLM 自动会用**。
#
# 反模式（PR #359 v1 已修正）：cookbook 自己 ``import fpdf2`` 写 ``render_pdf`` 工具
#   → 1) 重复造轮子（违反 §0.2 SSOT） 2) 多了个外部依赖 3) 比 SSOT 实现差
#     （fpdf2 latin-1 only，需 ascii_safe 把中文换 '?'；MarkdownDocumentRenderer
#     直接 CJK-safe）4) 教坏 SDK 用户"凡功能不在我 plugin 里就要自己写"。
#
# 正确教学点（ACT extended.md §6 演示）：
#   user 要 PDF → LLM 调 data_analyst_write_report 写 markdown
#              → 然后调 word_smart_export(file_path=md_path, format="pdf",
#                                         output_path=pdf_path) 出 PDF
# 这才是 SDK 的真实用法：**plugin 只补内置没有的能力，不重写已有能力**。


# ============================================================
# §2. ToolPlugin 注册到 SDK
# ============================================================


class DataAnalystToolPlugin:
    """实现 ``krow_agent_sdk.protocols.ToolPlugin`` Protocol。

    工具命名规范（详 advanced-development-guide §3.2）：
    - 域前缀（``data_analyst_``）+ 动词（``read``/``compute``/``write``）+ 宾语
    - 不带版本号，不用 PascalCase
    """

    plugin_id = "data_analyst.tools"

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "data_analyst_read_csv",
                "description": (
                    "读 CSV 文件拿 metadata + 前 10 行预览。"
                    "LLM 看完后能决定下一步要 compute_stats 哪些列。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "CSV 文件路径（绝对或相对）",
                        },
                        "encoding": {
                            "type": "string",
                            "description": "编码（默认 utf-8；中文老 CSV 试 gbk）",
                            "default": "utf-8",
                        },
                    },
                    "required": ["path"],
                },
                "handler": read_csv,
            },
            {
                "name": "data_analyst_compute_stats",
                "description": (
                    "对 CSV 数值列算 mean/std/min/max/missing；"
                    "分类列算 unique + top5 频次。"
                    "System 1 确定性计算（不调 LLM）。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "encoding": {"type": "string", "default": "utf-8"},
                    },
                    "required": ["path"],
                },
                "handler": compute_stats,
            },
            {
                "name": "data_analyst_write_report",
                "description": (
                    "把已生成的 markdown 报告写到磁盘（成品契约：传整张 markdown 即可）。"
                    "LLM 推荐用法：`markdown` 单字段传完整 markdown（含 `# 标题`），"
                    "title 自动从首个 H1 提取（无 H1 用文件名 stem 兜底）。"
                    "向后兼容：仍接受 `title` + `content` 双字段调用，handler 内自动 normalize。"
                    "无论哪种形态，handler 一律跑 H1 去重 + 独占行 `**xxx**`→`## xxx` normalize。"
                    ""
                    " + lessons 2026-05-25-sdk-d1-gate-judge-decay-and-cookbook-feedback。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "output_path": {
                            "type": "string",
                            "description": "目标 .md 文件路径（绝对或相对）",
                        },
                        "markdown": {
                            "type": "string",
                            "description": (
                                "（推荐）完整 markdown 正文，含 `# 标题`；"
                                "handler 不再外层套 H1，避免标题重复。"
                            ),
                        },
                        "title": {
                            "type": "string",
                            "description": (
                                "（可选, 仅老调用方）报告标题；若 markdown 已含 H1 可省略。"
                                " optional 设计是为防 LLM 漏填 required → 短路失败"
                                "（详 lessons 2026-05-25 §教训3）。"
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": (
                                "（可选, 仅老调用方）markdown 正文；推荐改用 `markdown` 字段。"
                            ),
                        },
                    },
                    # required 仅保留无法 fallback 的字段 (output_path)。
                    # title/content/markdown 任一非空即可，handler 内自动推导:
                    #   - markdown 优先（成品契约）
                    #   - title+content 兼容（零件契约，handler normalize）
                    "required": ["output_path"],
                },
                "handler": write_report,
            },
            {
                "name": "data_analyst_detect_anomalies",
                "description": (
                    "对 CSV 数值列做异常检测（System 1 deterministic）。"
                    "method='iqr'（默认；快；解释性好）/ 'zscore'（要求列近似正态）/"
                    " 'isolation_forest'（多列联合异常；需 sklearn）。"
                    "**Krow 内置无此能力**——必须通过本工具调用。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "method": {
                            "type": "string",
                            "enum": list(_ANOMALY_METHODS),
                            "default": "iqr",
                        },
                        "contamination": {
                            "type": "number",
                            "description": "isolation_forest 时预期异常占比（0.001-0.5；默认 0.05）",
                            "default": 0.05,
                        },
                        "encoding": {"type": "string", "default": "utf-8"},
                    },
                    "required": ["path"],
                },
                "handler": detect_anomalies,
            },
            {
                "name": "data_analyst_compute_correlation",
                "description": (
                    "对 CSV 数值列算相关性矩阵 + top N 强相关对。"
                    "method='pearson'（线性）/ 'spearman'（秩相关，非线性单调更稳）。"
                    "返回平铺 matrix dict + top_pairs list。"
                    "**禁止 LLM 凭感觉判 column 间相关性**——必须调本工具。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "method": {
                            "type": "string",
                            "enum": ["pearson", "spearman"],
                            "default": "pearson",
                        },
                        "top_n": {"type": "integer", "default": 5},
                        "encoding": {"type": "string", "default": "utf-8"},
                    },
                    "required": ["path"],
                },
                "handler": compute_correlation,
            },
            {
                "name": "data_analyst_pick_palette",
                "description": (
                    "按数据类型查表返回 hex 配色（System 1 deterministic）。"
                    "数值列分布用 sequential，分类列对比用 categorical，"
                    "正负指标用 diverging。**不要让 LLM 自己配色**。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "palette_kind": {
                            "type": "string",
                            "enum": ["categorical", "sequential", "diverging"],
                            "default": "categorical",
                        },
                        "n": {
                            "type": "integer",
                            "description": "要几个颜色（自动循环或截取）",
                            "default": 10,
                        },
                    },
                    "required": [],
                },
                "handler": pick_palette,
            },
            # PDF 输出**不在本 plugin 注册** —— 见 §1.7 注释：
            # 用 Krow 内置 ``word_smart_export`` 工具（SSOT 复用，避免重复造轮子）。
        ]


# ============================================================
# §3. ACTPlugin（让 LLM 自动选这个 ACT）
# ============================================================


class DataAnalystACTPlugin:
    """实现 ``krow_agent_sdk.protocols.ACTPlugin`` Protocol。"""

    plugin_id = "data_analyst.act"
    act_name = "data_analyst"

    def get_act_root(self) -> Path:
        return Path(__file__).parent / "act_assets" / "data_analyst"

    def get_act_file_path(self) -> Path:
        return self.get_act_root() / "ext_data_analyst.md"

    def get_tool_names(self) -> list[str]:
        # 6 个 plugin 自带工具 + word_smart_export（Krow 内置）共 7 个供 LLM 调用。
        # 注：word_smart_export 不在本 plugin 注册（SSOT 复用 Krow 内置 PDF 管线）。
        # ACT 自动允许 LLM 同时看到本 plugin 的工具 + 全局工具池里的内置工具。
        # 详见 ext_data_analyst.md §6 推荐工作流。
        return [
            "data_analyst_read_csv",
            "data_analyst_compute_stats",
            "data_analyst_detect_anomalies",
            "data_analyst_compute_correlation",
            "data_analyst_pick_palette",
            "data_analyst_write_report",
        ]


# ============================================================
# §4. EventListenerPlugin（流式监听 → CLI 进度）
# ============================================================


class DataAnalystProgressListener:
    """实现 ``krow_agent_sdk.protocols.EventListenerPlugin`` Protocol。

    订阅 EventBus 把 agent 进度实时打印给 CLI 用户。
    （生产环境可以替换成钉钉 / Slack / WebSocket 推送给前端。）
    """

    plugin_id = "data_analyst.progress_listener"

    def __init__(self, *, verbose: bool = True) -> None:
        self._verbose = verbose
        self._step_count = 0

    def get_subscriptions(self) -> list[dict[str, Any]]:
        """SDK 内 EventListenerManager 按此订阅 EventBus topics。"""
        return [
            {"topic": "progressive.step_start", "handler": self._on_step_start},
            {"topic": "progressive.step_completed", "handler": self._on_step_done},
            {"topic": "agent.task_complete", "handler": self._on_task_done},
            {"topic": "agent.task_failed", "handler": self._on_task_failed},
        ]

    def _on_step_start(self, event: Any) -> None:
        self._step_count += 1
        if self._verbose:
            print(f"  [step {self._step_count}] {event.payload.get('description', '...')}")

    def _on_step_done(self, event: Any) -> None:
        if self._verbose:
            elapsed = event.payload.get("elapsed_seconds", 0)
            print(f"  [step {self._step_count}] ✓ done ({elapsed:.1f}s)")

    def _on_task_done(self, event: Any) -> None:
        print(f"\n✅ 任务完成：{self._step_count} 步执行完毕")

    def _on_task_failed(self, event: Any) -> None:
        reason = event.payload.get("reason", "unknown")
        print(f"\n❌ 任务失败：{reason}")


# ============================================================
# §5. GatePlugin × 2（v2 新增：硬守门 / fail-loud）
# ============================================================
#
# 设计哲学（与 AGENTS.md §0.1 TURBO 哲学对齐）：
# - Gate = System 1 deterministic 闸门（不调 LLM；零成本；100% 可重放）
# - Gate vs Hint：Gate 硬挡（block）；Hint 软提示（仅参考）
# - 真实业务理由：数据分析场景常含 PII（个人身份信息），LLM 上下文一旦
#   读到手机号/身份证就有合规风险——必须在 read_csv 之前就闸住
#
# Gate 工作流：
# 1. SDK build() 时调用 get_gate() + phase 注册到 macro/micro GateChain
# 2. macro phase：每次 macro ReACT conclude 之前评估
# 3. evaluate(parsed, context) → GateDecision(verdict, reason)
# 4. BLOCK 时 reason 文本回送 LLM（黄金错误模板格式）让其调整策略
#
# 参考：modules/knowledge/conclude_guard_gates.py:make_simple_gate

# PII 关键词字典（中英文 column 名常见模式）
_PII_KEYWORDS = {
    # 身份证 / ID
    "id_card", "idcard", "id-card", "identity", "ssn",
    "身份证", "证件号", "身份证号",
    # 手机 / phone
    "phone", "mobile", "tel", "telephone", "cell",
    "手机", "手机号", "电话",
    # 邮箱 / email
    "email", "e-mail", "mail",
    "邮箱",
    # 银行卡 / 账户
    "bank_card", "bankcard", "card_no", "account_no", "iban",
    "银行卡", "卡号", "账号",
    # 地址
    "home_address", "residence",
    "家庭住址", "户籍地址",
}


def _scan_pii_columns(columns: list[str]) -> list[str]:
    """扫描 column 名，返回命中 PII 关键词的 column list."""
    if not columns:
        return []
    hits: list[str] = []
    for col in columns:
        col_lower = str(col).lower().strip()
        col_normalized = re.sub(r"[\s_\-]+", "_", col_lower)
        for kw in _PII_KEYWORDS:
            if kw in col_lower or kw in col_normalized:
                hits.append(col)
                break
    return hits


class PIIDetectorGate:
    """合规守门：检测 column 名含 PII 关键词时 BLOCK conclude.

    实现 ``krow_agent_sdk.protocols.GatePlugin`` Protocol。

    工作机制：agent 每次 macro ReACT conclude 前，本 gate 检查 context 里
    最近一次 ``data_analyst_read_csv`` 工具的 columns 字段；命中 PII 关键词
    则返回 BLOCK + 修法说明（脱敏 / 显式声明 allow_pii=true）。

    真实业务价值：
    - GDPR / CCPA / 个保法合规：禁止把未脱敏 PII 流到 LLM 上下文
    - 防止 prompt injection 把客户隐私写进 system prompt 训练样本
    - fail-loud > fail-silent（让 LLM 知道为什么被挡，给出修法）
    """

    plugin_id = "data_analyst.pii_gate"
    phase = "macro"

    def __init__(self, *, allow_pii: bool = False) -> None:
        """allow_pii=True 时 gate 退化为 ALLOW（用户显式确认 demo / 测试场景）."""
        self._allow_pii = bool(allow_pii)

    def get_gate(self) -> Any:
        """构造 Gate 实例（满足 ``Gate`` Protocol）.

        Returns: gate instance with .name / .priority / .evaluate(parsed, context)
        """
        # SDK 公开 API 路径：``krow_agent_sdk.protocols`` 重导出 gate 构造工具
        # （外部 plugin **不应**直接 import ``modules.knowledge.*``，否则破坏 SDK 边界）
        from krow_agent_sdk.protocols import (
            GateDecision,
            GateVerdict,
            make_simple_gate,
        )

        allow_pii = self._allow_pii

        def evaluate(parsed: dict, context: dict) -> Any:
            if allow_pii:
                return GateDecision(
                    verdict=GateVerdict.ALLOW,
                    reason="allow_pii=True 已显式放行",
                    gate_name="pii_detector",
                )
            tool_results = context.get("recent_tool_results", []) or []
            for tr in tool_results:
                if not isinstance(tr, dict):
                    continue
                if tr.get("tool_name") != "data_analyst_read_csv":
                    continue
                cols = tr.get("result", {}).get("columns") or []
                hits = _scan_pii_columns(cols)
                if hits:
                    return GateDecision(
                        verdict=GateVerdict.BLOCK,
                        reason=(
                            "❌ PII 守门：检测到含敏感字段的列 "
                            f"{hits}（手机/身份证/邮箱/银行卡等）。\n"
                            "   位置：data_analyst_read_csv 返回 columns\n"
                            "   修法：\n"
                            "     1. 让用户先脱敏后再上传（hash / mask 末 4 位）\n"
                            "     2. 或者在工具调用层加 `allow_pii=True` flag 显式承担风险\n"
                            "     3. 或者在分析前先 drop 这些 PII 列（compute_stats 时不传）\n"
                            "   合规依据：GDPR Art.5 数据最小化原则 / 个保法第 6 条"
                        ),
                        gate_name="pii_detector",
                    )
            return GateDecision(
                verdict=GateVerdict.DEFER,
                gate_name="pii_detector",
            )

        return make_simple_gate(name="pii_detector", priority=50, evaluator=evaluate)


class OutputPathGate:
    """安全守门：拦 path traversal（写报告路径必须在 project_root 内）.

    实现 ``krow_agent_sdk.protocols.GatePlugin`` Protocol。

    真实业务价值：
    - 防止 prompt injection 让 agent 把 ../../../etc/passwd 之类路径写文件
    - 强制工作目录隔离（多租户 SaaS 场景必备）
    """

    plugin_id = "data_analyst.path_gate"
    phase = "macro"

    def __init__(self, project_root: str | Path) -> None:
        self._project_root = _normalize_path(project_root)

    def get_gate(self) -> Any:
        from krow_agent_sdk.protocols import (
            GateDecision,
            GateVerdict,
            make_simple_gate,
        )

        project_root = self._project_root

        def evaluate(parsed: dict, context: dict) -> Any:
            tool_results = context.get("recent_tool_results", []) or []
            for tr in tool_results:
                if not isinstance(tr, dict):
                    continue
                if tr.get("tool_name") != "data_analyst_write_report":
                    continue
                args = tr.get("args") or {}
                output_path = args.get("output_path", "")
                if not output_path:
                    continue
                try:
                    resolved = _normalize_path(output_path)
                    resolved.relative_to(project_root)
                except ValueError:
                    return GateDecision(
                        verdict=GateVerdict.BLOCK,
                        reason=(
                            f"❌ 输出路径守门：output_path={output_path!r} 不在 "
                            f"project_root={project_root} 内\n"
                            "   位置：data_analyst_write_report\n"
                            "   修法：\n"
                            "     1. 改用 project_root 子目录路径\n"
                            f"     2. 例：{project_root}/report.md\n"
                            "   合规依据：path traversal 防御（OWASP A01:2021）"
                        ),
                        gate_name="output_path",
                    )
            return GateDecision(verdict=GateVerdict.DEFER, gate_name="output_path")

        return make_simple_gate(name="output_path", priority=60, evaluator=evaluate)


# ============================================================
# §6. HintPlugin（v2 新增：System 2 软提示）
# ============================================================
#
# Hint vs Gate 的边界（重要）：
# - Hint：System 2 软建议，给 LLM 一段额外 prompt，**不强制**；LLM 可不接受
#   适合"领域 best practice"（如：时序数据建议加同环比分析）
# - Gate：System 1 硬守门，BLOCK 后 conclude 失败；适合"不许越界"（如 PII）


class DataInsightHintPlugin:
    """检测数据特征给 LLM 软提示（时序列 / 高基数列 / 全 NaN 列）.

    实现 ``krow_agent_sdk.protocols.HintPlugin`` Protocol。
    """

    plugin_id = "data_analyst.insight_hint"
    applicable_acts = ["data_analyst"]

    def hint_for(self, context: dict) -> str | None:
        """根据 context 返回 markdown hint 文本（None = 无提示）.

        SDK 在每次 macro ReACT 决策前调用 hint_for()，把 hint 拼到 LLM prompt。
        """
        # 提示 1：触发条件 = 已有 read_csv 结果
        tool_results = context.get("recent_tool_results", []) or []
        for tr in tool_results:
            if not isinstance(tr, dict) or tr.get("tool_name") != "data_analyst_read_csv":
                continue
            result = tr.get("result", {}) or {}
            cols = result.get("columns") or []
            dtypes = result.get("dtypes") or {}
            row_count = result.get("row_count", 0)
            preview = result.get("preview_rows") or []

            insights: list[str] = []

            # 时序列检测
            time_cols = [
                c for c in cols
                if any(kw in str(c).lower() for kw in ("date", "time", "timestamp", "日期", "时间"))
            ]
            if time_cols:
                insights.append(
                    f"- 检测到时间列 {time_cols}：建议 compute_stats 后加一段时序观察"
                    "（同环比、趋势、季节性）"
                )

            # 高基数分类列检测（unique > 100 且 row_count > 0）
            if preview and row_count > 0:
                for c in cols:
                    if dtypes.get(c, "").startswith(("int", "float")):
                        continue
                    sample_unique = len({row.get(c) for row in preview if c in row})
                    if sample_unique == len(preview) and row_count > 50:
                        insights.append(
                            f"- 列 `{c}` 在前 10 行已全 unique → 大概率是 ID 列，"
                            "建议从分析中剔除（不要做 value_counts）"
                        )

            # 全 NaN 列检测
            for c in cols:
                if all((row.get(c) is None or str(row.get(c)) in ("nan", "NaN", ""))
                       for row in preview):
                    insights.append(f"- 列 `{c}` 前 10 行全空 → 可能是无效列，建议 drop")

            # 大数据集提示
            if row_count > 100_000:
                insights.append(
                    f"- 数据规模 {row_count} 行较大 → "
                    "建议先 `compute_stats` 看分布而非 detect_anomalies 全量跑"
                )

            if insights:
                return "## 数据洞察建议（System 2 软提示）\n" + "\n".join(insights)
        return None


# ============================================================
# §7. AuditEventListener（v2 新增：合规审计日志）
# ============================================================
#
# 真实业务价值：
# - 合规审计：每个数据分析任务的工具调用 + 结果落到本地 .audit.jsonl
# - 可追溯：出错 / 投诉时按时间戳定位 LLM 决策路径
# - 与 ProgressListener 不同：Progress 是给用户看的实时进度，Audit 是给审计员看的归档
#
# 演示要点：
# - 同一 plugin_id 下可以多个 EventListenerPlugin 实例（OCP）
# - listener 不应抛异常打断 agent（容错；try/except 包住 file IO）


class AuditEventListener:
    """把工具调用 + 结果归档到本地 .audit.jsonl 文件（合规要求）.

    实现 ``krow_agent_sdk.protocols.EventListenerPlugin`` Protocol。
    """

    plugin_id = "data_analyst.audit_listener"

    def __init__(self, audit_log_path: str | Path) -> None:
        self._path = _normalize_path(audit_log_path)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.warning("AuditEventListener: 创建父目录失败 %s", e)

    def get_subscriptions(self) -> list[dict[str, Any]]:
        return [
            {"topic": "tool.call_started", "handler": self._on_tool_call_started},
            {"topic": "tool.call_completed", "handler": self._on_tool_call_completed},
            {"topic": "agent.task_complete", "handler": self._on_task_complete},
            {"topic": "agent.task_failed", "handler": self._on_task_failed},
        ]

    def _append(self, record: dict[str, Any]) -> None:
        try:
            record.setdefault("timestamp", time.time())
            record.setdefault("timestamp_iso", time.strftime("%Y-%m-%dT%H:%M:%S"))
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("AuditEventListener append failed: %s", exc)

    def _on_tool_call_started(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        self._append({
            "kind": "tool_call_started",
            "tool_name": payload.get("tool_name"),
            "args": payload.get("args"),
        })

    def _on_tool_call_completed(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        result = payload.get("result")
        if isinstance(result, dict):
            result = {k: result.get(k) for k in ("ok", "summary", "error", "method")
                     if k in result}
        self._append({
            "kind": "tool_call_completed",
            "tool_name": payload.get("tool_name"),
            "ok": payload.get("ok", True),
            "elapsed_ms": payload.get("elapsed_ms"),
            "result_summary": result,
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


__all__ = [
    # tools (functions)
    "read_csv",
    "compute_stats",
    "detect_anomalies",
    "compute_correlation",
    "pick_palette",
    "write_report",
    # plugins
    "DataAnalystToolPlugin",
    "DataAnalystACTPlugin",
    "DataAnalystProgressListener",
    "PIIDetectorGate",
    "OutputPathGate",
    "DataInsightHintPlugin",
    "AuditEventListener",
]
