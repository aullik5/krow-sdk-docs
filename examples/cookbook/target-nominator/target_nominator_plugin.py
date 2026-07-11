"""Target-nominator cookbook plugin SSOT.

> Cookbook demo：借鉴 Cell《AI 发现 GPNMB CAR-T 靶点》那套"多库取数 + 多维打分 +
> LLM 提名"工作流，用 Krow SDK plugin 搭成可复现、可 fork 的靶点提名 demo。

业务场景：肿瘤免疫治疗（CAR-T / ADC / 抗体）靶点发现——给一批候选基因，从公开
数据库真取每候选的**安全 / 有效 / 可药 / 广谱**四维证据，确定性加权打分排序，最后
让 LLM 读打分矩阵 + 溯源提名单一最佳靶点。人工做这套要 1-2 周查库；本 cookbook
预期 30 分钟 ~ 数小时（长任务档，见 main.py BudgetSpec）。

本文件 SSOT：
- 3 个 ToolPlugin 工具：
  · target_nominator_fetch_expression   —— Human Protein Atlas 表达（安全/有效维）
  · target_nominator_fetch_associations —— Open Targets 关联分 + 可药性（可药/广谱维）
  · target_nominator_score_candidates   —— 多维加权打分 + 反幻觉接地校验（System 1）
- 1 个 GatePlugin：TargetNominationIntegrityGate（反编造：无真取数 / 全 ungrounded → BLOCK）
- 1 个 ACTPlugin：target_nominator（提名工作流 ACT）

设计原则（对齐 AGENTS.md TURBO 哲学 + litsci worker §13 增补设计）：

1. **TURBO 边界**
   - 取数（HTTP + 归一）、加权聚合（算术）、接地校验 = System 1 确定性工具
   - "选谁做最佳靶点、提名理由怎么写" = System 2（LLM 在 ACT 流程内决策）
   - 每维数值**必须来自工具返回**（带 source url）；无来源 → ungrounded → gate BLOCK

2. **反幻觉硬门槛**（准确性 > 完整性）
   - LLM 若凭记忆编造表达/关联分数 → 关键维无 source → gate 拦截
   - hint 提醒"请查库"在压缩任务时会失效 → 必须 System 1 闸住 conclude

3. **多候选竞争**（借鉴 Cell：GPNMB = 最常被提名 = 跨癌种最广谱 + 安全 + 可药）
   - 打分工具把候选当"竞争假设"，按综合有利度排序，收敛出最可提名者

参考：
- litsci worker 实现思路（本 cookbook 的上游 SSOT）：
  ``packages/krow-worker-litsci-plugin/krow_worker_litsci/tools/target_tools.py``
  ``packages/krow-worker-litsci-plugin/krow_worker_litsci/tools/biodb_direct.py``（HPA/OpenTargets adapter）
- 姊妹 cookbook：``examples/cookbook/literature-reviewer/``（多 PDF 综述）
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HPA_API = "https://www.proteinatlas.org/api/search_download.php"
_OPENTARGETS_GQL = "https://api.platform.opentargets.org/api/v4/graphql"
_HTTP_TIMEOUT = 30


# ============================================================
# §-1. 取数捕获（供 main.py 确定性收口结构化产物 + 溯源）
# ============================================================
#
# 为什么需要（TURBO"数据注入≠数据采用"铁证 · 2026-07-11 三连败）：
#   LLM 会稳定地调 fetch 工具真取数（报告里出现真 Ensembl id / OT 分），却**不采用**
#   打分工具的结构化输出——它自己在报告里重算 ranking、自己手写 target_scores.json
#   （缺 ranking/matrix/grounded）、用"Human Protein Atlas"名字而非 url 溯源。三次真跑
#   验证：靠 prompt/finished-artifact 提示都压不住。
#
#   解（System 1 收口）：把**确定性结构化产物**（打分矩阵 JSON + 数据来源 url）交给
#   orchestrator（main.py）从捕获的工具取数结果确定性生成；LLM 只管**叙事**（提名理由）。
#   这正是 TURBO"语义交 LLM、语法交系统"——ranking/matrix/溯源是语法（确定性），
#   提名论证是语义（LLM）。
#
# 捕获默认关闭（smoke 单测直调工具不应有全局副作用）；main.py 跑前显式 enable。

_CAPTURE_ENABLED = False
_CAPTURE: dict[str, dict[str, dict[str, Any]]] = {"expression": {}, "associations": {}}
# 最后一次成功的 score_target_candidates 返回（工具自产的结构化产物 · 供 main.py
# 确定性落 target_scores.json + 数据来源，不靠 LLM 手抄）。
_LAST_SCORE_RESULT: dict[str, Any] | None = None


def reset_capture() -> None:
    """清空并启用取数捕获（main.py 每次 run 前调）。"""
    global _CAPTURE_ENABLED, _LAST_SCORE_RESULT
    _CAPTURE_ENABLED = True
    _CAPTURE["expression"].clear()
    _CAPTURE["associations"].clear()
    _LAST_SCORE_RESULT = None


def get_capture() -> dict[str, dict[str, dict[str, Any]]]:
    """返回捕获到的成功取数结果（按 kind → gene(upper) → result）。"""
    return _CAPTURE


def get_last_score_result() -> dict[str, Any] | None:
    """返回最后一次成功打分的完整结构化产物（无则 None）。"""
    return _LAST_SCORE_RESULT


def collect_data_sources() -> list[str]:
    """确定性汇总本次 run 的所有数据来源 url（去重保序）。

    优先用打分工具返回的 ``data_sources``（LLM 真正传进打分的 source 全集）；
    兜底用捕获的 HPA / Open Targets 取数结果里的 ``source``（即便 LLM 打分时漏填
    source，只要真调过取数工具，url 也不会丢）。
    """
    out: list[str] = []

    def _add(url: Any) -> None:
        u = str(url or "").strip()
        if u and u.startswith("http") and u not in out:
            out.append(u)

    if isinstance(_LAST_SCORE_RESULT, dict):
        for s in _LAST_SCORE_RESULT.get("data_sources") or []:
            _add(s)
    for kind in ("expression", "associations"):
        for res in _CAPTURE[kind].values():
            _add(res.get("source"))
    return out


def build_data_sources_markdown() -> str:
    """把 collect_data_sources() 拼成可直接追加进报告的 "## 数据来源" 章节。"""
    urls = collect_data_sources()
    if not urls:
        return ""
    return "\n".join(["## 数据来源", "", *(f"- {u}" for u in urls)])


def _capture(kind: str, gene: str, result: dict[str, Any]) -> None:
    if _CAPTURE_ENABLED and isinstance(result, dict) and result.get("ok"):
        key = str(gene or result.get("gene") or "").strip().upper()
        if key:
            _CAPTURE[kind][key] = result


def _capture_score(result: dict[str, Any]) -> None:
    global _LAST_SCORE_RESULT
    if _CAPTURE_ENABLED and isinstance(result, dict) and result.get("ok"):
        _LAST_SCORE_RESULT = result


def _max_float_in(text: Any) -> float:
    """从 HPA 表达串里抠出最大数值（nTPM），确定性——无数字则 0.0。"""
    nums = re.findall(r"[-+]?\d*\.?\d+", str(text or ""))
    vals = [float(n) for n in nums] if nums else []
    return max(vals) if vals else 0.0


# ============================================================
# §0. 通用工具（黄金错误模板 + HTTP）
# ============================================================


def _golden_error(
    msg: str, *, where: str, fixes: Iterable[str], related: Iterable[str] = ()
) -> dict[str, Any]:
    parts = [f"❌ {msg}", f"   位置：{where}", "   修法："]
    for i, fix in enumerate(fixes, 1):
        parts.append(f"     {i}. {fix}")
    if related:
        parts.append(f"   相关：{' / '.join(related)}")
    return {"ok": False, "error": "\n".join(parts)}


def _http_get_json(url: str, *, timeout: int = _HTTP_TIMEOUT) -> Any:
    """GET → JSON（stdlib urllib；smoke 测试 monkeypatch 本函数脱网）."""
    req = urllib.request.Request(url, headers={"User-Agent": "krow-target-nominator/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _http_post_json(url: str, payload: dict[str, Any], *, timeout: int = _HTTP_TIMEOUT) -> Any:
    """POST JSON → JSON（stdlib urllib；smoke 测试 monkeypatch 本函数脱网）."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "krow-target-nominator/0.1",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


# ============================================================
# §1. 归一助手（输入鲁棒 + 数值归一 —— 与 litsci target_tools 同源）
# ============================================================


def _coerce_list(raw: Any) -> list[Any]:
    """把 None / 单值 / JSON 字符串 / list 统一成 list（输入鲁棒）."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        if s[0] in "[{":
            try:
                parsed = json.loads(s)
                return parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                pass
        # 逗号/换行分隔的裸清单
        parts = [p.strip() for p in s.replace("\n", ",").split(",")]
        return [p for p in parts if p]
    if isinstance(raw, dict):
        return [raw]
    return [raw]


_HIGH_WORDS = {"high", "strong", "enriched", "高", "强", "高表达"}
_MID_WORDS = {"medium", "moderate", "中", "中等"}
_LOW_WORDS = {"low", "weak", "not detected", "absent", "低", "弱", "无", "不表达"}


def _norm_conf(raw: Any) -> float | None:
    """数值归一到 0-1：数字（0-1 原样 / 0-100 除 100）+ 高中低词表 → 0-1，否则 None."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return 1.0 if raw else 0.0
    if isinstance(raw, (int, float)):
        v = float(raw)
        if v > 1.0:
            v = v / 100.0
        return max(0.0, min(1.0, v))
    t = str(raw).strip().lower()
    try:
        v = float(t.rstrip("%"))
        if "%" in t or v > 1.0:
            v = v / 100.0
        return max(0.0, min(1.0, v))
    except ValueError:
        pass
    if t in _HIGH_WORDS:
        return 1.0
    if t in _MID_WORDS:
        return 0.5
    if t in _LOW_WORDS:
        return 0.0
    return None


# 关键维（缺 source → ungrounded 红线适用）+ 同义词归一（非 strict 比对）。
_SAFETY, _EFFICACY, _DRUGGABILITY, _BREADTH = (
    "safety", "efficacy", "druggability", "breadth",
)
_KEY_DIMENSIONS: frozenset[str] = frozenset({_SAFETY, _EFFICACY, _DRUGGABILITY})
_DIM_SYNONYMS: dict[str, tuple[str, ...]] = {
    _SAFETY: ("safety", "safe", "安全", "健康组织", "正常组织", "normal", "off_tumor"),
    _EFFICACY: ("efficacy", "有效", "肿瘤表达", "肿瘤", "tumor", "cancer"),
    _DRUGGABILITY: ("druggability", "druggable", "可药", "成药性", "tractability", "tractable"),
    _BREADTH: ("breadth", "broad", "广谱", "跨癌种", "pan_cancer", "prevalence"),
}


def _norm_dimension(raw: Any) -> str:
    t = str(raw or "").strip().lower()
    if not t:
        return ""
    for canon, kws in _DIM_SYNONYMS.items():
        if t == canon or t in kws:
            return canon
    for canon, kws in _DIM_SYNONYMS.items():
        if any(kw and kw in t for kw in kws):
            return canon
    return t


# ============================================================
# §2. Human Protein Atlas 取数（安全维 = 健康组织低表达；有效维 = 肿瘤高表达）
# ============================================================
#
# 业务理由：
#   CAR-T / ADC 靶点第一道门 = "on-target off-tumor" 毒性——靶点在正常重要器官
#   低表达（安全），在肿瘤高表达（有效）。HPA 一次 REST 同时给 normal tissue /
#   pathology(cancer) / single-cell 分级，是这两维的黄金数据源。
#   LLM 不应凭记忆说"GPNMB 在皮肤高表达"——必须工具取数带 source。


_HPA_COLUMNS = "g,gs,eg,rnatsm,rnascm,t_RNA_skin,pathology_prognostics"


def fetch_target_expression(gene: str, *, timeout: int = _HTTP_TIMEOUT) -> dict[str, Any]:
    """从 Human Protein Atlas 取基因表达（安全维 + 有效维证据）.

    Args:
        gene: 基因符号（如 ``GPNMB``）或 Ensembl gene id（``ENSG...``）。

    Returns:
        dict 含 ok/summary/gene/ensembl/normal_expression/tumor_expression/
        single_cell/source。source = HPA 词条 url（接地锚点）。
    """
    g = str(gene or "").strip()
    if not g:
        return _golden_error(
            "gene 为空",
            where="fetch_target_expression(gene=...)",
            fixes=["传基因符号（如 GPNMB）或 Ensembl id（ENSG...）"],
        )
    url = (
        f"{_HPA_API}?search={urllib.parse.quote(g)}"
        f"&format=json&columns={_HPA_COLUMNS}&compress=no"
    )
    try:
        data = _http_get_json(url, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return _golden_error(
            f"HPA 取数失败：{exc}",
            where=f"fetch_target_expression(gene={g!r})",
            fixes=[
                "检查网络出网（proteinatlas.org 443）",
                "确认基因符号拼写（HPA 用 HGNC 官方符号）",
                "稍后重试（HPA 偶发限流）",
            ],
            related=("fetch_target_associations",),
        )
    rows = data if isinstance(data, list) else data.get("results", []) if isinstance(data, dict) else []
    if not rows:
        return _golden_error(
            f"HPA 无 {g} 记录",
            where=f"fetch_target_expression(gene={g!r})",
            fixes=["换用 HGNC 官方基因符号", "或传 Ensembl gene id"],
        )
    rec = rows[0] if isinstance(rows[0], dict) else {}
    ensembl = str(rec.get("Ensembl") or rec.get("eg") or "").strip()
    gene_sym = str(rec.get("Gene") or rec.get("gs") or g).strip()
    normal = rec.get("RNA tissue specific nTPM") or rec.get("rnatsm") or rec.get("RNA tissue specificity") or ""
    single_cell = rec.get("RNA single cell type specific nTPM") or rec.get("rnascm") or ""
    tumor = rec.get("Pathology prognostics") or rec.get("pathology_prognostics") or ""
    source = f"https://www.proteinatlas.org/{ensembl}-{gene_sym}" if ensembl else _HPA_API
    max_normal_ntpm = round(_max_float_in(normal), 2)
    result = {
        "ok": True,
        "summary": (
            f"HPA {gene_sym}（{ensembl or 'n/a'}）：normal={_trim(normal)}；"
            f"tumor={_trim(tumor)}；single_cell={_trim(single_cell)}；"
            f"max_normal_ntpm={max_normal_ntpm}。source={source}"
        ),
        "gene": gene_sym,
        "ensembl": ensembl,
        "normal_expression": normal,
        "tumor_expression": tumor,
        "single_cell": single_cell,
        # 确定性抠出的健康组织最高表达（nTPM）——安全维打分用（越低越安全）。
        "max_normal_ntpm": max_normal_ntpm,
        "source": source,
    }
    _capture("expression", gene_sym, result)
    return result


def _trim(v: Any, n: int = 80) -> str:
    s = str(v or "").replace("\n", " ")
    return s[:n] + ("…" if len(s) > n else "")


# ============================================================
# §3. Open Targets 取数（可药维 = tractability；广谱维 = 关联疾病分）
# ============================================================
#
# 业务理由：
#   可药性（有没有抗体/小分子可及口袋）+ 跨癌种关联广度是靶点提名的另两维。
#   Open Targets GraphQL 一次给 tractability（antibody/smallmolecule 桶）
#   + associatedDiseases.rows[].score（关联强度）。GPNMB 之所以"最常被提名"
#   正因它跨多癌种关联 + 抗体可药（glembatumumab vedotin ADC 背书）。


_OT_TARGET_QUERY = """
query TargetAssoc($ensemblId: String!, $size: Int!) {
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    tractability { modality label value }
    associatedDiseases(page: {index: 0, size: $size}) {
      count
      rows { disease { name } score }
    }
  }
}
"""


def _resolve_ensembl(gene: str, *, timeout: int) -> str:
    """基因符号 → Ensembl id（Open Targets search）；已是 ENSG 则原样返回."""
    g = gene.strip()
    if g.upper().startswith("ENSG"):
        return g
    query = (
        'query R($q: String!) { search(queryString: $q, entityNames: ["target"], '
        'page: {index: 0, size: 1}) { hits { id entity } } }'
    )
    try:
        data = _http_post_json(
            _OPENTARGETS_GQL, {"query": query, "variables": {"q": g}}, timeout=timeout
        )
    except (urllib.error.URLError, TimeoutError, ValueError):
        return ""
    hits = (((data or {}).get("data") or {}).get("search") or {}).get("hits") or []
    for h in hits:
        if h.get("entity") == "target" and str(h.get("id", "")).startswith("ENSG"):
            return str(h["id"])
    return str(hits[0]["id"]) if hits and str(hits[0].get("id", "")).startswith("ENSG") else ""


def fetch_target_associations(
    gene: str, *, disease_size: int = 10, timeout: int = _HTTP_TIMEOUT
) -> dict[str, Any]:
    """从 Open Targets 取靶点可药性 + 关联疾病分（可药维 + 广谱维证据）.

    Args:
        gene: 基因符号（如 ``GPNMB``）或 Ensembl gene id（``ENSG...``）。
        disease_size: 取前 N 个关联疾病（默认 10）。

    Returns:
        dict 含 ok/summary/gene/ensembl/tractability/antibody_tractable/
        top_diseases/n_associations/max_association_score/source。
    """
    g = str(gene or "").strip()
    if not g:
        return _golden_error(
            "gene 为空",
            where="fetch_target_associations(gene=...)",
            fixes=["传基因符号（如 GPNMB）或 Ensembl id（ENSG...）"],
        )
    ensembl = _resolve_ensembl(g, timeout=timeout)
    if not ensembl:
        return _golden_error(
            f"Open Targets 无法解析 {g} 到 Ensembl id",
            where=f"fetch_target_associations(gene={g!r})",
            fixes=["换用 HGNC 官方符号", "或直接传 ENSG 开头的 Ensembl id"],
            related=("fetch_target_expression",),
        )
    try:
        data = _http_post_json(
            _OPENTARGETS_GQL,
            {"query": _OT_TARGET_QUERY, "variables": {"ensemblId": ensembl, "size": disease_size}},
            timeout=timeout,
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return _golden_error(
            f"Open Targets 取数失败：{exc}",
            where=f"fetch_target_associations(ensembl={ensembl})",
            fixes=["检查网络出网（api.platform.opentargets.org 443）", "稍后重试"],
        )
    target = ((data or {}).get("data") or {}).get("target") or {}
    if not target:
        return _golden_error(
            f"Open Targets 无 {ensembl} 靶点数据",
            where=f"fetch_target_associations(ensembl={ensembl})",
            fixes=["确认 Ensembl id 有效（当前 Open Targets 版本收录）"],
        )
    tractability = target.get("tractability") or []
    antibody_tractable = any(
        (t.get("modality") == "AB" and t.get("value"))
        or ("antibod" in str(t.get("label", "")).lower() and t.get("value"))
        for t in tractability
    )
    assoc = target.get("associatedDiseases") or {}
    rows = assoc.get("rows") or []
    top_diseases = [
        {"disease": (r.get("disease") or {}).get("name"), "score": r.get("score")}
        for r in rows
    ]
    max_score = max((r.get("score") or 0.0 for r in rows), default=0.0)
    source = f"https://platform.opentargets.org/target/{ensembl}"
    symbol = target.get("approvedSymbol") or g
    result = {
        "ok": True,
        "summary": (
            f"Open Targets {symbol}（{ensembl}）：{assoc.get('count', len(rows))} 关联疾病，"
            f"max_score={round(max_score, 3)}，antibody_tractable={antibody_tractable}。source={source}"
        ),
        "gene": symbol,
        "ensembl": ensembl,
        "tractability": tractability,
        "antibody_tractable": antibody_tractable,
        "top_diseases": top_diseases,
        "n_associations": assoc.get("count", len(rows)),
        "max_association_score": round(max_score, 4),
        "source": source,
    }
    _capture("associations", symbol, result)
    return result


# ============================================================
# §4. 多维加权打分（System 1 · 确定性 · 与 litsci target_score 同算法）
# ============================================================


def _norm_candidates(raw: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for i, item in enumerate(_coerce_list(raw), start=1):
        if isinstance(item, dict):
            cid = str(item.get("id") or item.get("symbol") or item.get("name") or f"T{i}").strip() or f"T{i}"
            name = str(item.get("name") or item.get("symbol") or cid).strip()
        else:
            cid, name = str(item).strip() or f"T{i}", str(item).strip()
        out.append({"id": cid, "name": name})
    return out


def _norm_scores(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in _coerce_list(raw):
        if not isinstance(item, dict):
            continue
        cid = str(
            item.get("candidate_id") or item.get("candidate")
            or item.get("target_id") or item.get("target") or item.get("id") or ""
        ).strip()
        dim = _norm_dimension(item.get("dimension") or item.get("dim") or item.get("axis"))
        value = _norm_conf(item.get("value", item.get("score")))
        source = str(item.get("source") or item.get("citation") or item.get("evidence") or "").strip()
        if cid and dim:
            out.append({"candidate_id": cid, "dimension": dim, "value": value, "source": source})
    return out


def _norm_weights(raw: Any, dims_seen: list[str]) -> dict[str, float]:
    weights: dict[str, float] = {}
    if isinstance(raw, dict) and raw:
        for k, v in raw.items():
            d = _norm_dimension(k)
            try:
                w = float(v)
            except (TypeError, ValueError):
                continue
            if d and w > 0:
                weights[d] = w
    if not weights:
        weights = {d: 1.0 for d in dims_seen}
    total = sum(weights.values()) or 1.0
    return {d: w / total for d, w in weights.items()}


def score_target_candidates(
    candidates: Any, scores: Any, weights: Any = None
) -> dict[str, Any]:
    """多维加权靶点提名打分（System 1）+ 反幻觉接地校验（借鉴 Cell GPNMB 方法论）.

    把候选靶点当"竞争假设"，按各维（安全/有效/可药/广谱）**工具取到的**数值做确定性
    加权聚合，按综合有利度排序；关键维（安全/有效/可药）数值必须带 source（无 =
    ungrounded 疑似脑补）。**选谁做最佳靶点 + 提名理由留给 LLM**，本工具只做结构化 + 接地。

    Args:
        candidates: 候选靶点 ``[{"id","name"}]`` 或基因符号列表。
        scores: 每候选每维打分 ``[{"candidate_id","dimension","value","source"}]``。
            value ∈ 0-1（或 0-100 / 高中低自动归一），"越大越好"的有利度
            （安全维 = 健康组织低表达 → 有利度高），由 LLM 从 fetch_* 工具真取数后组织传入。
            source 必填才算接地（HPA/Open Targets 工具返回的 url）。
        weights: 可选各维权重；缺省对已出现维等权。

    Returns:
        dict 含 ok/summary/ranking/matrix/weights/issues/data_sources/
        data_sources_markdown。``data_sources_markdown`` 是可直接原样粘贴进报告的
        "## 数据来源"章节（逐条列 HPA / Open Targets url）——写报告时 COPY VERBATIM，
        确保产物可溯源（缺 url 用户无法核验 = 提名无效）。
        summary 末尾附机器标记 ``[target.score ungrounded=U candidates=M grounded_fetch=?]``。
    """
    cands = _norm_candidates(candidates)
    sc = _norm_scores(scores)
    if not cands:
        return _golden_error(
            "candidates 为空",
            where="score_target_candidates(candidates=...)",
            fixes=["先备好候选靶点清单，传 [{'id','name'}] 或基因符号列表（≥1 个）"],
            related=("fetch_target_expression", "fetch_target_associations"),
        )
    if not sc:
        return _golden_error(
            "scores 为空",
            where="score_target_candidates(scores=...)",
            fixes=[
                "先用 fetch_target_expression / fetch_target_associations 取每候选各维真数据",
                "组织成 [{'candidate_id','dimension','value','source'}]（value 0-1，source 必填）",
            ],
            related=("fetch_target_expression", "fetch_target_associations"),
        )

    cand_ids = {c["id"] for c in cands}
    issues: list[str] = []
    ungrounded_entries = 0
    scores_by_cand: dict[str, dict[str, dict[str, Any]]] = {c["id"]: {} for c in cands}
    dims_seen: list[str] = []
    for entry in sc:
        cid, dim = entry["candidate_id"], entry["dimension"]
        if cid not in cand_ids:
            issues.append(f"打分引用了不存在的候选 id：{cid}")
            continue
        if dim not in dims_seen:
            dims_seen.append(dim)
        is_key = dim in _KEY_DIMENSIONS
        if entry["value"] is not None and not entry["source"] and is_key:
            ungrounded_entries += 1
            issues.append(
                f"候选 {cid} 的关键维 {dim} 数值未标来源（ungrounded，疑似脑补）"
                "→ 回 HPA/Open Targets 工具补 source"
            )
        scores_by_cand[cid][dim] = entry

    weights = _norm_weights(weights, dims_seen)
    ranking_rows: list[dict[str, Any]] = []
    for c in cands:
        dim_vals: dict[str, float | None] = {}
        wsum = agg = 0.0
        grounded_all = True
        for dim, entry in scores_by_cand[c["id"]].items():
            v = entry["value"]
            dim_vals[dim] = v
            if v is None:
                continue
            w = weights.get(dim, 0.0)
            if w > 0:
                agg += w * v
                wsum += w
            if dim in _KEY_DIMENSIONS and not entry["source"]:
                grounded_all = False
        aggregate = round(agg / wsum, 4) if wsum > 0 else None
        missing_key = sorted(_KEY_DIMENSIONS - set(dim_vals.keys()))
        if missing_key:
            issues.append(
                f"候选 {c['id']} 缺关键维 {'/'.join(missing_key)}"
                "（提名需安全+有效+可药三维齐，回工具补取数）"
            )
        cand_sources = sorted(
            {e["source"] for e in scores_by_cand[c["id"]].values() if e.get("source")}
        )
        ranking_rows.append({
            "id": c["id"],
            "name": c["name"],
            "aggregate": aggregate,
            "dimensions": dim_vals,
            "grounded": grounded_all and not missing_key,
            "missing_dimensions": missing_key,
            "sources": cand_sources,
        })

    ranking = sorted(
        ranking_rows,
        key=lambda r: (r["aggregate"] is not None, r["aggregate"] or 0.0),
        reverse=True,
    )
    matrix = {
        c["id"]: {d: scores_by_cand[c["id"]].get(d, {}).get("value") for d in dims_seen}
        for c in cands
    }
    top = ranking[0] if ranking else None
    if top and top["aggregate"] is not None:
        verdict = f"综合有利度最高：{top['name']}（aggregate={top['aggregate']}）"
    else:
        verdict = "暂无可排序候选（缺有效打分）→ 回工具补各维数值"
    # grounded_fetch = 是否至少一条打分带 source（gate 据此判"有没有真取数"）
    any_grounded = any(e["source"] for e in sc)
    # 唯一化所有数据来源 url（保持传入顺序）→ 供 LLM COPY VERBATIM 的"数据来源"章节。
    # TURBO"数据注入≠数据采用"教训：只把 source 塞进工具返回不够，LLM 写报告时会
    # 丢掉；给一个可直接原样粘贴的 finished artifact（## 数据来源）才能稳定溯源。
    data_sources: list[str] = []
    for e in sc:
        s = e.get("source")
        if s and s not in data_sources:
            data_sources.append(s)
    if data_sources:
        data_sources_markdown = "\n".join(
            ["## 数据来源", "", *(f"- {s}" for s in data_sources)]
        )
    else:
        data_sources_markdown = ""
    summary = (
        f"靶点提名打分：{len(cands)} 候选 × {len(dims_seen)} 维"
        f"（{', '.join(dims_seen) or '无'}）。{verdict}"
        f"{'；⚠️ ' + str(len(issues)) + ' 个问题待修' if issues else '；打分完整接地'}"
        f"；数据来源 {len(data_sources)} 条（见 data_sources_markdown，写报告时原样粘贴）"
        f" [target.score ungrounded={ungrounded_entries} candidates={len(cands)} "
        f"grounded_fetch={'yes' if any_grounded else 'no'}]"
    )
    result = {
        "ok": True,
        "summary": summary,
        "ranking": ranking,
        "matrix": matrix,
        "weights": weights,
        "issues": issues,
        "any_grounded": any_grounded,
        "data_sources": data_sources,
        "data_sources_markdown": data_sources_markdown,
    }
    _capture_score(result)
    return result


# ============================================================
# §5. ToolPlugin（注册 3 个 System 1 工具）
# ============================================================


class TargetNominatorToolPlugin:
    """实现 ``krow_agent_sdk.protocols.ToolPlugin`` Protocol。

    注册 3 个 System 1 工具（HPA 取数 / Open Targets 取数 / 多维打分）。
    """

    plugin_id = "target_nominator.tools"

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "target_nominator_fetch_expression",
                "description": (
                    "从 Human Protein Atlas 取基因表达（安全维=健康组织低表达 + 有效维=肿瘤高表达）。"
                    "**禁止 LLM 凭记忆报表达水平**——必须工具取数带 source url。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {"gene": {"type": "string", "description": "基因符号或 Ensembl id"}},
                    "required": ["gene"],
                },
                "handler": fetch_target_expression,
            },
            {
                "name": "target_nominator_fetch_associations",
                "description": (
                    "从 Open Targets 取靶点可药性（tractability，可药维）+ 关联疾病分"
                    "（associatedDiseases.score，广谱维）。**禁止 LLM 凭记忆报关联分/可药性**。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "gene": {"type": "string", "description": "基因符号或 Ensembl id"},
                        "disease_size": {"type": "integer", "default": 10},
                    },
                    "required": ["gene"],
                },
                "handler": fetch_target_associations,
            },
            {
                "name": "target_nominator_score_candidates",
                "description": (
                    "多维加权靶点提名打分（System 1 确定性）+ 反幻觉接地校验。把候选当竞争假设，"
                    "按安全/有效/可药/广谱四维加权聚合排序。关键维数值必须带 source（无=ungrounded）。"
                    "返回 data_sources_markdown（可原样粘贴进报告的'## 数据来源'章节）。"
                    "**选谁 + 提名理由留给 LLM**，本工具只做结构化 + 接地。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "candidates": {"type": "array", "description": "[{id,name}] 或基因符号列表"},
                        "scores": {
                            "type": "array",
                            "description": "[{candidate_id,dimension,value,source}]，value 0-1，source 必填",
                        },
                        "weights": {"type": "object", "description": "各维权重（可选，缺省等权）"},
                    },
                    "required": ["candidates", "scores"],
                },
                "handler": score_target_candidates,
            },
        ]


# ============================================================
# §6. GatePlugin（反幻觉：无真取数 / 全 ungrounded → BLOCK conclude）
# ============================================================
#
# 设计依据（与 litsci TargetNominationIntegrityGate 同构）：
#   靶点提名的红线 = "不能凭记忆编造表达/关联分数就提名"。
#   hint 提醒"请查库"在压缩任务时会失效 → 必须 System 1 闸住 conclude：
#   - 调过 score_candidates 但**无一条打分带 source**（无真取数）→ BLOCK
#   - 或所有候选的关键维全 ungrounded → BLOCK


class TargetNominationIntegrityGate:
    """靶点提名反编造守门：无真取数 / 全 ungrounded → BLOCK conclude.

    实现 ``krow_agent_sdk.protocols.GatePlugin`` Protocol。
    """

    plugin_id = "target_nominator.integrity_gate"
    phase = "macro"

    def get_gate(self) -> Any:
        from krow_agent_sdk.protocols import (
            GateDecision,
            GateVerdict,
            make_simple_gate,
        )

        def evaluate(parsed: dict, context: dict) -> Any:
            tool_results = context.get("recent_tool_results", []) or []
            score_result: dict | None = None
            fetch_grounded = False
            for tr in tool_results:
                if not isinstance(tr, dict):
                    continue
                name = tr.get("tool_name", "")
                res = tr.get("result", {}) or {}
                if name in (
                    "target_nominator_fetch_expression",
                    "target_nominator_fetch_associations",
                ) and isinstance(res, dict) and res.get("ok") and res.get("source"):
                    fetch_grounded = True
                if name == "target_nominator_score_candidates" and isinstance(res, dict) and res.get("ok"):
                    score_result = res  # 取最后一次成功打分

            if score_result is None:
                # 没打过分 → 提名流程未走到收口，不拦（DEFER）
                return GateDecision(verdict=GateVerdict.DEFER, gate_name="target_nomination_integrity")

            any_grounded = bool(score_result.get("any_grounded")) or fetch_grounded
            if not any_grounded:
                return GateDecision(
                    verdict=GateVerdict.BLOCK,
                    reason=(
                        "❌ 靶点提名反编造红线：打分了但无一条维度带 source（未真取数）\n"
                        "   位置：target_nominator_score_candidates（scores 全无 source）\n"
                        "   修法：\n"
                        "     1. 先调 target_nominator_fetch_expression 取 HPA 表达（安全/有效维）\n"
                        "     2. 调 target_nominator_fetch_associations 取 Open Targets（可药/广谱维）\n"
                        "     3. 把工具返回的 source url 填进每条 score.source 后重新打分\n"
                        "   规范依据：准确性 > 完整性——提名必须基于真数据，不可凭记忆编造"
                    ),
                    gate_name="target_nomination_integrity",
                )

            ranking = score_result.get("ranking") or []
            if ranking and all(not r.get("grounded") for r in ranking):
                return GateDecision(
                    verdict=GateVerdict.BLOCK,
                    reason=(
                        "❌ 靶点提名接地不足：所有候选关键维（安全/有效/可药）均 ungrounded 或缺维\n"
                        "   位置：score_candidates.ranking（无一候选 grounded=true）\n"
                        "   修法：至少让排名靠前的候选三关键维齐 + 每维带 source，再收口提名\n"
                        "   规范依据：提名单一靶点前，该靶点的关键维证据必须完整可溯源"
                    ),
                    gate_name="target_nomination_integrity",
                )

            return GateDecision(
                verdict=GateVerdict.ALLOW,
                reason=f"✅ 提名接地校验通过：{len(ranking)} 候选已打分，关键维有真取数溯源",
                gate_name="target_nomination_integrity",
            )

        return make_simple_gate(
            name="target_nomination_integrity", priority=85, evaluator=evaluate
        )


# ============================================================
# §7. ACTPlugin（让 LLM 自动选 target_nominator ACT）
# ============================================================


class TargetNominatorACTPlugin:
    """实现 ``krow_agent_sdk.protocols.ACTPlugin`` Protocol。"""

    plugin_id = "target_nominator.act"
    act_name = "target_nominator"

    def get_act_root(self) -> Path:
        return Path(__file__).parent / "act_assets" / "target_nominator"

    def get_act_file_path(self) -> Path:
        return self.get_act_root() / "ext_target_nominator.md"

    def get_tool_names(self) -> list[str]:
        return [
            "target_nominator_fetch_expression",
            "target_nominator_fetch_associations",
            "target_nominator_score_candidates",
            "smart_file_write",
        ]


__all__ = [
    "fetch_target_expression",
    "fetch_target_associations",
    "score_target_candidates",
    "reset_capture",
    "get_capture",
    "get_last_score_result",
    "collect_data_sources",
    "build_data_sources_markdown",
    "TargetNominatorToolPlugin",
    "TargetNominationIntegrityGate",
    "TargetNominatorACTPlugin",
]
