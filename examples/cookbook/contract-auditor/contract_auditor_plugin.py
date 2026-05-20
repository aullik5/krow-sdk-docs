"""Contract Auditor cookbook plugins (v3 PR-C).

==============================================================================
本文件实现 Cookbook v3 第 3 个 demo（行政办公 · 合同审阅）的全部插件：

  - 5 个 ToolPlugin：split_clauses / classify_clauses / score_clause_risk /
    redline_diff / index_terms
  - 1 个 ACTPlugin：contract_auditor ACT（6 步标准工作流）
  - 2 个 GatePlugin（**强阻断**）：MandatoryClauseGate / HighRiskBlockingGate
  - 2 个 HintPlugin：AmbiguousLanguageHint / MissingDefinitionHint
  - 1 个 EventListenerPlugin：LegalAuditTrailListener
  - 1 个 ObservabilityPlugin（OpenTelemetry tracing，与 PR-A Prometheus 互补）

设计原则（详 ../../AGENTS.md §0.0-0.2）：
  - System 1（确定性）：条款切分 / 分类 / 风险评分 / diff / 术语索引
    全部走查表 + 正则 + 启发式（LLM 凭感觉评分会出"高风险打成中风险"事故）
  - System 2（语义）：仅"风险叙事"和"修订建议"由 LLM 写
  - SSOT 复用：风险报告 PDF 走 word_smart_export，不引 reportlab
==============================================================================
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from krow_agent_sdk.protocols import GateDecision, GateVerdict

logger = logging.getLogger(__name__)


# =============================================================================
# §1. 通用 helpers
# =============================================================================
def _normalize_path(p: str | Path) -> Path:
    if isinstance(p, str):
        p = Path(p).expanduser()
    return p.resolve() if p.exists() else p.absolute()


def _golden_error(
    *,
    error_msg: str,
    location: str,
    fixes: list[str],
    related: str | None = None,
) -> str:
    """黄金错误模板（详 AGENTS.md §五·错误信息）."""
    parts = [f"❌ {error_msg}", f"   位置：{location}", "   修法："]
    parts.extend(f"     {i}. {f}" for i, f in enumerate(fixes, 1))
    if related:
        parts.append(f"   相关：{related}")
    return "\n".join(parts)


def _scan_text_from_path(path: Path) -> str:
    """从 docx / pdf / txt 抽文本.

    优先级：txt > docx (python-docx) > pdf (pdfplumber) > 兜底 utf-8 read.
    """
    suf = path.suffix.lower()
    if suf in {".txt", ".md", ""}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suf == ".docx":
        try:
            from docx import Document
            doc = Document(str(path))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            logger.warning("python-docx 未装，docx 抽取退回 raw 读取（可能含乱码）")
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            logger.warning("docx 抽取失败 %s：%s", path, exc)
            return ""
    if suf == ".pdf":
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text() or ""
                    if t.strip():
                        text_parts.append(t)
            return "\n\n".join(text_parts)
        except ImportError:
            logger.warning("pdfplumber 未装")
            return ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("pdf 抽取失败 %s：%s", path, exc)
            return ""
    return path.read_text(encoding="utf-8", errors="replace")


# =============================================================================
# §2. 条款分类法（15 类，企业合同标准 taxonomy）
# =============================================================================
# 每类对应：display_name + 正向关键词（中英双语）+ baseline 风险分（0-1）
CLAUSE_TAXONOMY: dict[str, dict[str, Any]] = {
    "term_termination": {
        "name": "期限与终止",
        "keywords_en": [
            "term", "termination", "expir", "renewal", "auto-renew",
        ],
        "keywords_zh": ["期限", "终止", "解除", "到期", "续约", "自动续期"],
        "baseline_risk": 0.55,
    },
    "payment_settlement": {
        "name": "付款与结算",
        "keywords_en": [
            "payment", "invoice", "settlement", "due date",
            "late fee", "interest",
        ],
        "keywords_zh": ["付款", "结算", "发票", "逾期", "滞纳金", "利息"],
        "baseline_risk": 0.50,
    },
    "liability_limitation": {
        "name": "责任限制",
        "keywords_en": [
            "liability", "limitation of liability", "cap on damages",
            "indirect damages", "consequential",
        ],
        "keywords_zh": ["责任限制", "赔偿上限", "间接损失", "不承担"],
        "baseline_risk": 0.85,
    },
    "indemnification": {
        "name": "赔偿与保护",
        "keywords_en": ["indemnif", "hold harmless", "defend"],
        "keywords_zh": ["赔偿", "免于责任", "免受损害", "辩护"],
        "baseline_risk": 0.80,
    },
    "ip_ownership": {
        "name": "知识产权",
        "keywords_en": [
            "intellectual property", "ip rights", "copyright",
            "trademark", "patent", "work for hire", "ownership",
        ],
        "keywords_zh": ["知识产权", "著作权", "商标", "专利", "权属"],
        "baseline_risk": 0.75,
    },
    "confidentiality_nda": {
        "name": "保密",
        "keywords_en": [
            "confidential", "nda", "non-disclosure", "trade secret",
        ],
        "keywords_zh": ["保密", "保密信息", "商业秘密"],
        "baseline_risk": 0.45,
    },
    "data_protection_gdpr": {
        "name": "数据保护 / GDPR / PIPL",
        "keywords_en": [
            "gdpr", "data protection", "personal data", "data subject",
            "data processor", "privacy",
        ],
        "keywords_zh": [
            "数据保护", "个人信息", "个人数据", "隐私", "数据主体",
            "数据处理者", "PIPL", "个保法",
        ],
        "baseline_risk": 0.85,
    },
    "antitrust_competition": {
        "name": "反垄断 / 竞争法",
        "keywords_en": [
            "antitrust", "competition law", "non-compete", "exclusive",
            "tying", "monopoli",
        ],
        "keywords_zh": ["反垄断", "竞争法", "排他", "独家", "搭售", "垄断"],
        "baseline_risk": 0.80,
    },
    "export_control": {
        "name": "出口管制 / 制裁",
        "keywords_en": [
            "export control", "sanction", "ofac", "ear", "itar",
            "embargo", "denied parties",
        ],
        "keywords_zh": [
            "出口管制", "制裁", "禁运", "受限实体", "实体清单",
        ],
        "baseline_risk": 0.90,
    },
    "force_majeure": {
        "name": "不可抗力",
        "keywords_en": ["force majeure", "act of god"],
        "keywords_zh": ["不可抗力", "天灾", "战争"],
        "baseline_risk": 0.30,
    },
    "warranty_disclaimer": {
        "name": "保证与免责",
        "keywords_en": [
            "warrant", "as is", "fitness for purpose", "merchantability",
        ],
        "keywords_zh": ["保证", "现状交付", "适销性", "适用性", "免责"],
        "baseline_risk": 0.55,
    },
    "dispute_jurisdiction": {
        "name": "争议解决与管辖",
        "keywords_en": [
            "arbitration", "jurisdiction", "governing law",
            "venue", "court of",
        ],
        "keywords_zh": ["仲裁", "管辖", "适用法律", "法院"],
        "baseline_risk": 0.50,
    },
    "assignment": {
        "name": "转让",
        "keywords_en": ["assignment", "assign", "transfer of rights"],
        "keywords_zh": ["转让", "权利转让"],
        "baseline_risk": 0.40,
    },
    "audit_compliance": {
        "name": "审计与合规",
        "keywords_en": [
            "audit", "right to audit", "compliance",
            "anti-corruption", "fcpa", "uk bribery",
        ],
        "keywords_zh": ["审计", "合规", "反腐败", "反贿赂"],
        "baseline_risk": 0.60,
    },
    "sla_performance": {
        "name": "SLA / 服务水平",
        "keywords_en": [
            "service level", "sla", "uptime", "availability",
            "response time",
        ],
        "keywords_zh": ["服务水平", "可用性", "响应时间", "在线时长"],
        "baseline_risk": 0.45,
    },
}

# 高风险类别（风险报告必须列入）
HIGH_RISK_CLAUSE_TYPES: set[str] = {
    "liability_limitation",
    "indemnification",
    "ip_ownership",
    "data_protection_gdpr",
    "antitrust_competition",
    "export_control",
}

# 必备条款（生效合同必须含 —— MandatoryClauseGate 守门）
MANDATORY_CLAUSE_TYPES: set[str] = {
    "data_protection_gdpr",
    "antitrust_competition",
    "export_control",
}


# 模糊用语（HintPlugin 预警）
AMBIGUOUS_PHRASES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\breasonable\b", re.IGNORECASE), "reasonable",
     "需明确判断标准（哪个 jurisdiction 的 reasonable / 谁的视角）"),
    (re.compile(r"\bbest efforts?\b", re.IGNORECASE), "best efforts",
     "未量化（建议改为'commercially reasonable efforts'+ 具体 KPI）"),
    (re.compile(r"\bas soon as possible\b|\bASAP\b", re.IGNORECASE),
     "as soon as possible / ASAP",
     "未量化时间窗（建议改为 N business days）"),
    (re.compile(r"\bmaterial(ly)?\b", re.IGNORECASE), "material(ly)",
     "未定义重要性阈值（建议给百分比 / 美元金额定义）"),
    (re.compile(r"\b(适当|合理|尽快|尽量)\b"), "适当 / 合理 / 尽快 / 尽量",
     "未量化的中文模糊词（同上需要补量化标准）"),
]


__all__: list[str] = []


# =============================================================================
# §3. Tool 函数（5 个 System 1 工具）
# =============================================================================
@dataclass
class Clause:
    """单个条款的结构化表示."""

    clause_id: str           # contract scoped id, e.g. "C-007"
    heading: str             # "7. Limitation of Liability"
    text: str                # 条款全文
    start_offset: int        # 在原始合同里的起始字符位置
    end_offset: int
    section_path: list[str] = field(default_factory=list)


_SECTION_HEADING_PATTERNS = [
    # 1. / 1.1 / 1.1.1 ...
    re.compile(r"^(\d+(?:\.\d+){0,3})\s*[.、]?\s+(.{1,80})$", re.MULTILINE),
    # Article 1 / Section 1 / 第一条 / 第1条
    re.compile(r"^(Article|Section|第[一二三四五六七八九十百千万0-9]+条)\s*[:.：]?\s*(.{1,80})$",
               re.MULTILINE | re.IGNORECASE),
    # 大写标题 LIMITATION OF LIABILITY
    re.compile(r"^([A-Z][A-Z\s\d]{4,80})$", re.MULTILINE),
]


def split_clauses(contract_path: str | Path | None = None,
                  *, contract_text: str | None = None) -> dict[str, Any]:
    """把合同切分为离散条款列表.

    支持：标题型（"1. Term"、"7.1 Liability"）/ Article-Section 型 /
    全大写标题型 三种切分启发式。命中任一即触发切分。

    Args:
        contract_path: docx / pdf / txt 合同路径（与 contract_text 二选一）
        contract_text: 直接传文本（适合测试 / 流式抽取后传入）

    Returns:
        dict {ok, summary, clause_count, clauses: [Clause...]}
    """
    if contract_text is None and contract_path is None:
        return {
            "ok": False,
            "error": _golden_error(
                error_msg="必须传 contract_path 或 contract_text 之一",
                location="split_clauses",
                fixes=[
                    "调 split_clauses(contract_path='/path/to/contract.docx')",
                    "或 split_clauses(contract_text='1. Term...\\n2. Payment...')",
                ],
            ),
        }
    if contract_text is None:
        path = _normalize_path(contract_path)  # type: ignore[arg-type]
        if not path.exists():
            return {
                "ok": False,
                "error": _golden_error(
                    error_msg=f"合同文件不存在：{path}",
                    location="split_clauses",
                    fixes=[
                        "检查路径拼写",
                        "用绝对路径而非相对路径",
                        "确认文件未被锁（其他程序占用）",
                    ],
                ),
            }
        contract_text = _scan_text_from_path(path)

    if not contract_text.strip():
        return {
            "ok": False,
            "error": _golden_error(
                error_msg="合同文本为空 / 未抽到任何文字",
                location="split_clauses",
                fixes=[
                    "确认 PDF 不是扫描件（OCR 缺失）",
                    "确认 docx 不是受保护 / 加密",
                    "用 word_smart_export 先转 markdown 看实际内容",
                ],
            ),
        }

    # 收集所有 heading 候选
    headings: list[tuple[int, str, str]] = []
    seen_offsets: set[int] = set()
    for pat in _SECTION_HEADING_PATTERNS:
        for m in pat.finditer(contract_text):
            offset = m.start()
            if offset in seen_offsets:
                continue
            seen_offsets.add(offset)
            groups = m.groups()
            if len(groups) >= 2:
                heading_label = f"{groups[0].strip()} {groups[1].strip()}".strip()
            else:
                heading_label = groups[0].strip()
            headings.append((offset, heading_label, m.group(0)))

    headings.sort(key=lambda x: x[0])

    # 切分：每个条款从 heading 到下一个 heading 之间
    clauses: list[Clause] = []
    if not headings:
        # 退化：整篇合同当一个 clause
        clauses.append(
            Clause(
                clause_id="C-001",
                heading="(合同全文 · 未识别到分段标题)",
                text=contract_text.strip(),
                start_offset=0,
                end_offset=len(contract_text),
            )
        )
    else:
        for idx, (offset, heading_label, _raw) in enumerate(headings):
            end = headings[idx + 1][0] if idx + 1 < len(headings) else len(contract_text)
            text = contract_text[offset:end].strip()
            clauses.append(
                Clause(
                    clause_id=f"C-{idx + 1:03d}",
                    heading=heading_label[:120],
                    text=text,
                    start_offset=offset,
                    end_offset=end,
                )
            )

    return {
        "ok": True,
        "summary": f"切分出 {len(clauses)} 个条款",
        "clause_count": len(clauses),
        "clauses": [
            {
                "clause_id": c.clause_id,
                "heading": c.heading,
                "text": c.text,
                "start_offset": c.start_offset,
                "end_offset": c.end_offset,
            }
            for c in clauses
        ],
    }


def classify_clauses(clauses: list[dict[str, Any]]) -> dict[str, Any]:
    """对条款列表做 15 类标签分类.

    按 CLAUSE_TAXONOMY 关键词匹配（中英双语）；同时命中多个返回 top-3。
    LLM 凭感觉分类会把 "indemnification" 错归到 "warranty"，必须查表。

    Returns:
        dict {ok, summary, classifications: [{clause_id, top_labels, scores}]}
    """
    if not isinstance(clauses, list):
        return {
            "ok": False,
            "error": _golden_error(
                error_msg=f"clauses 必须是 list[dict]，传入 {type(clauses).__name__}",
                location="classify_clauses",
                fixes=[
                    "先调 split_clauses 拿到 clauses 列表",
                    "确认每个 clause 含 clause_id / heading / text 字段",
                ],
            ),
        }

    classifications = []
    for c in clauses:
        if not isinstance(c, dict):
            continue
        text = (c.get("heading", "") + " " + c.get("text", "")).lower()
        scores: dict[str, int] = {}
        for label, spec in CLAUSE_TAXONOMY.items():
            hit = 0
            for kw in spec["keywords_en"]:
                if kw.lower() in text:
                    hit += 2
            for kw in spec["keywords_zh"]:
                if kw in text:
                    hit += 2
            if hit > 0:
                scores[label] = hit

        if scores:
            top = sorted(scores.items(), key=lambda x: -x[1])[:3]
            top_labels = [label for label, _ in top]
        else:
            top_labels = ["misc_other"]

        classifications.append({
            "clause_id": c.get("clause_id"),
            "heading": c.get("heading"),
            "top_labels": top_labels,
            "scores": scores,
        })

    label_counts: dict[str, int] = {}
    for cls in classifications:
        for label in cls["top_labels"]:
            label_counts[label] = label_counts.get(label, 0) + 1

    return {
        "ok": True,
        "summary": (
            f"分类完成 {len(classifications)} 个条款，命中类别："
            + ", ".join(f"{k}={v}" for k, v in
                        sorted(label_counts.items(), key=lambda x: -x[1])[:5])
        ),
        "classifications": classifications,
        "label_counts": label_counts,
    }

# 风险加权词（命中提升风险分）
RISK_AMPLIFIERS_EN: dict[str, float] = {
    "unlimited": 0.15,
    "no cap": 0.15,
    "irrevocable": 0.10,
    "perpetual": 0.10,
    "exclusive": 0.10,
    "sole discretion": 0.08,
    "shall not be liable": 0.10,
    "indemnify and hold harmless": 0.12,
    "without limitation": 0.06,
}
RISK_AMPLIFIERS_ZH: dict[str, float] = {
    "无上限": 0.15,
    "不可撤销": 0.10,
    "永久": 0.10,
    "独家": 0.10,
    "排他": 0.10,
    "全权": 0.08,
    "概不负责": 0.10,
    "免除一切责任": 0.12,
    "并赔偿": 0.06,
}


def score_clause_risk(clauses: list[dict[str, Any]],
                      classifications: list[dict[str, Any]]) -> dict[str, Any]:
    """给每个条款打风险分（0.0 = 低风险，1.0 = 极高风险）.

    算法：baseline_risk（按分类查 CLAUSE_TAXONOMY） +
          风险加权词命中（最多 +0.4）+
          长度异常（>800 char 且分类是 high-risk → +0.05）。
    最终 clip 到 [0, 1]。

    Returns:
        dict {ok, summary, risks: [{clause_id, label, risk_score, level, drivers}]}
    """
    if not isinstance(clauses, list) or not isinstance(classifications, list):
        return {
            "ok": False,
            "error": _golden_error(
                error_msg="clauses 与 classifications 都必须是 list",
                location="score_clause_risk",
                fixes=[
                    "先调 split_clauses → classify_clauses 拿到两个列表",
                    "调用：score_clause_risk(clauses=cls_out, classifications=cls_result)",
                ],
            ),
        }
    if len(clauses) != len(classifications):
        return {
            "ok": False,
            "error": _golden_error(
                error_msg=(
                    f"clauses 与 classifications 长度不一致：{len(clauses)} vs "
                    f"{len(classifications)}"
                ),
                location="score_clause_risk",
                fixes=[
                    "确保 classifications 由同一批 clauses 调 classify_clauses 得到",
                    "不要在中间过滤 clauses",
                ],
            ),
        }

    risks = []
    for clause, classification in zip(clauses, classifications):
        text = (clause.get("text") or "").lower()
        top_labels = classification.get("top_labels") or ["misc_other"]
        primary_label = top_labels[0]
        baseline = CLAUSE_TAXONOMY.get(primary_label, {}).get("baseline_risk", 0.20)

        # 风险加权
        amp_score = 0.0
        drivers: list[str] = []
        for word, w in RISK_AMPLIFIERS_EN.items():
            if word in text:
                amp_score += w
                drivers.append(f"含 '{word}' (+{w:.2f})")
        for word, w in RISK_AMPLIFIERS_ZH.items():
            if word in text:
                amp_score += w
                drivers.append(f"含 '{word}' (+{w:.2f})")
        amp_score = min(amp_score, 0.4)

        # 长度异常
        len_score = 0.0
        if primary_label in HIGH_RISK_CLAUSE_TYPES and len(text) > 800:
            len_score = 0.05
            drivers.append(f"高风险类条款超长 ({len(text)} chars, +0.05)")

        score = max(0.0, min(1.0, baseline + amp_score + len_score))

        if score >= 0.75:
            level = "high"
        elif score >= 0.50:
            level = "medium"
        else:
            level = "low"

        risks.append({
            "clause_id": clause.get("clause_id"),
            "heading": clause.get("heading"),
            "label": primary_label,
            "risk_score": round(score, 3),
            "level": level,
            "drivers": drivers,
        })

    high_count = sum(1 for r in risks if r["level"] == "high")
    medium_count = sum(1 for r in risks if r["level"] == "medium")

    return {
        "ok": True,
        "summary": (
            f"评估完成 {len(risks)} 个条款 — high={high_count} / "
            f"medium={medium_count} / low={len(risks) - high_count - medium_count}"
        ),
        "risks": risks,
        "high_count": high_count,
        "medium_count": medium_count,
    }


def _diff_blocks(a: str, b: str) -> list[dict[str, Any]]:
    """简化 unified diff：返回 ADD / REMOVE / KEEP 块."""
    from difflib import SequenceMatcher
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    sm = SequenceMatcher(a=a_lines, b=b_lines)
    out: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append({
                "op": "keep",
                "text": "\n".join(a_lines[i1:i2]),
            })
        elif tag == "delete":
            out.append({
                "op": "remove",
                "text": "\n".join(a_lines[i1:i2]),
            })
        elif tag == "insert":
            out.append({
                "op": "add",
                "text": "\n".join(b_lines[j1:j2]),
            })
        elif tag == "replace":
            out.append({
                "op": "remove",
                "text": "\n".join(a_lines[i1:i2]),
            })
            out.append({
                "op": "add",
                "text": "\n".join(b_lines[j1:j2]),
            })
    return out


def redline_diff(template_text: str, contract_text: str) -> dict[str, Any]:
    """对比公司模板 vs 实际合同的 redline diff（行级）.

    LLM 凭感觉抓 diff 漏 / 顺序错；用 difflib SequenceMatcher 才严谨。
    """
    if not isinstance(template_text, str) or not isinstance(contract_text, str):
        return {
            "ok": False,
            "error": _golden_error(
                error_msg="template_text 与 contract_text 都必须是 str",
                location="redline_diff",
                fixes=[
                    "先用 split_clauses 抽出条款 text 字段",
                    "或读模板文件：Path(...).read_text()",
                ],
            ),
        }

    blocks = _diff_blocks(template_text, contract_text)
    add_count = sum(1 for b in blocks if b["op"] == "add")
    remove_count = sum(1 for b in blocks if b["op"] == "remove")

    # 按行号 / 字符级别给一个简化 diff text（≤ 200 行避免 LLM token 爆炸）
    diff_lines: list[str] = []
    for b in blocks[:80]:
        if b["op"] == "keep":
            sample = b["text"].splitlines()[:1]
            for line in sample:
                diff_lines.append(f"   {line[:120]}")
            if len(b["text"].splitlines()) > 1:
                diff_lines.append(
                    f"   ... ({len(b['text'].splitlines())} unchanged lines)"
                )
        elif b["op"] == "add":
            for line in b["text"].splitlines()[:8]:
                diff_lines.append(f"+  {line[:120]}")
        elif b["op"] == "remove":
            for line in b["text"].splitlines()[:8]:
                diff_lines.append(f"-  {line[:120]}")

    return {
        "ok": True,
        "summary": f"redline：{add_count} 处新增 / {remove_count} 处删除",
        "add_count": add_count,
        "remove_count": remove_count,
        "diff_text": "\n".join(diff_lines),
        "blocks": blocks,
    }

_DEFINITION_PATTERN = re.compile(
    r'"(?P<term>[A-Z][A-Za-z0-9 \-_/]{2,80})"\s*(?:means|shall mean|refers to)|'
    r'"(?P<term2>[A-Z][A-Za-z0-9 \-_/]{2,80})"\s*[—\-]\s*[A-Z]',
    re.IGNORECASE,
)
# 中文定义模式："X" 是指 / 系指 / 即
_DEFINITION_PATTERN_ZH = re.compile(r'"([^"]{2,40})"\s*(?:是指|系指|即|指)')
_TERM_USAGE_PATTERN = re.compile(r'"([A-Z][A-Za-z0-9 \-_/]{2,80})"')


def index_terms(contract_text: str) -> dict[str, Any]:
    """术语索引：找已定义术语 + 使用次数 + 未定义但被引号包裹的疑似术语.

    Returns:
        dict {ok, summary, defined_terms, undefined_terms, term_usage_counts}
    """
    if not isinstance(contract_text, str):
        return {
            "ok": False,
            "error": _golden_error(
                error_msg="contract_text 必须是 str",
                location="index_terms",
                fixes=[
                    "先 read_text(contract_path)",
                    "或调 split_clauses 拿到 contract_text",
                ],
            ),
        }

    defined_terms: dict[str, int] = {}
    for m in _DEFINITION_PATTERN.finditer(contract_text):
        term = (m.group("term") or m.group("term2") or "").strip()
        if term:
            defined_terms[term] = defined_terms.get(term, 0) + 1
    for m in _DEFINITION_PATTERN_ZH.finditer(contract_text):
        term = m.group(1).strip()
        if term:
            defined_terms[term] = defined_terms.get(term, 0) + 1

    # 找全部疑似 term usage（首字母大写 + 引号包裹）
    usage_counts: dict[str, int] = {}
    for m in _TERM_USAGE_PATTERN.finditer(contract_text):
        term = m.group(1).strip()
        if not term or len(term) < 3:
            continue
        usage_counts[term] = usage_counts.get(term, 0) + 1

    undefined: list[dict[str, Any]] = []
    for term, count in usage_counts.items():
        if term not in defined_terms and count >= 2:
            undefined.append({"term": term, "usage_count": count})
    undefined.sort(key=lambda x: -x["usage_count"])

    return {
        "ok": True,
        "summary": (
            f"术语索引：已定义 {len(defined_terms)} 个 / "
            f"疑似未定义 {len(undefined)} 个"
        ),
        "defined_terms": defined_terms,
        "undefined_terms": undefined[:30],
        "term_usage_counts": dict(
            sorted(usage_counts.items(), key=lambda x: -x[1])[:30]
        ),
    }

# =============================================================================
# §4. ToolPlugin —— 注册 5 个工具到 SDK
# =============================================================================
class ContractAuditorToolPlugin:
    """合同审阅 5 个 System 1 工具的注册器.

    实现 ``krow_agent_sdk.protocols.ToolPlugin`` Protocol（``get_tools() -> list[ToolSpec]``）.

    W4 fix（2026-05-19）：之前的 ``get_tools() -> dict[str, dict]`` 不符合 SDK
    Protocol（要求 ``list[ToolSpec]`` with ``{name, description, input_schema, handler}``），
    导致 5 个工具**全部注册失败**，cookbook real LLM E2E 时 LLM 报"contract_auditor_*
    工具未注册"，被迫降级用 llm_generate 兜底。改回标准 list 形态后工具正常注册.
    """

    plugin_id = "contract_auditor.tools"

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "contract_auditor_split_clauses",
                "description": (
                    "把合同文本切分为离散条款列表（按 1./Article/全大写标题）。"
                    "输入：contract_path 或 contract_text。输出 list[Clause dict]"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contract_path": {
                            "type": "string",
                            "description": "docx / pdf / txt 合同路径",
                        },
                        "contract_text": {
                            "type": "string",
                            "description": "直接传文本（与 contract_path 二选一）",
                        },
                    },
                    "required": [],
                },
                "handler": split_clauses,
            },
            {
                "name": "contract_auditor_classify_clauses",
                "description": (
                    "对条款列表做 15 类分类（期限/付款/责任限制/赔偿/IP/保密/"
                    "数据保护/反垄断/出口管制/不可抗力/保证/争议/转让/审计/SLA）。"
                    "LLM 凭感觉分类会把 indemnification 错归到 warranty"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "clauses": {
                            "type": "array",
                            "description": "split_clauses 返回的 clauses 字段",
                            "items": {"type": "object"},
                        },
                    },
                    "required": ["clauses"],
                },
                "handler": classify_clauses,
            },
            {
                "name": "contract_auditor_score_clause_risk",
                "description": (
                    "给每个条款打风险分（0-1，high≥0.75 / medium≥0.50 / low）。"
                    "baseline + 风险加权词（unlimited / 无上限 / irrevocable）+ 长度异常"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "clauses": {
                            "type": "array", "items": {"type": "object"},
                        },
                        "classifications": {
                            "type": "array", "items": {"type": "object"},
                        },
                    },
                    "required": ["clauses", "classifications"],
                },
                "handler": score_clause_risk,
            },
            {
                "name": "contract_auditor_redline_diff",
                "description": (
                    "对比公司模板 vs 实际合同的行级 diff（add/remove/keep）。"
                    "用 difflib SequenceMatcher，不要让 LLM 凭感觉对比"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "template_text": {"type": "string"},
                        "contract_text": {"type": "string"},
                    },
                    "required": ["template_text", "contract_text"],
                },
                "handler": redline_diff,
            },
            {
                "name": "contract_auditor_index_terms",
                "description": (
                    "扫描合同找已定义术语 + 使用次数 + 引号包裹但未定义的疑似术语。"
                    "MissingDefinitionHint 依赖此输出"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contract_text": {"type": "string"},
                    },
                    "required": ["contract_text"],
                },
                "handler": index_terms,
            },
        ]


# =============================================================================
# §5. ACTPlugin —— 注册 contract_auditor ACT
# =============================================================================
_ACT_DIR = Path(__file__).parent / "act_assets"


class ContractAuditorACTPlugin:
    """注册 contract_auditor ACT 到 SDK.

    实现 ``krow_agent_sdk.protocols.ACTPlugin`` Protocol（与 financial-analyst /
    literature-reviewer / data-analyst 同源 5-method 形态：``plugin_id`` /
    ``act_name`` / ``get_act_root`` / ``get_act_file_path`` / ``get_tool_names``）.

    W4 fix（2026-05-19）：之前用的是 v0 形态 ``get_act_directories() -> list[Path]``，
    与 SDK ACTPlugin Protocol 不匹配，会导致 ``standalone-import`` smoke 失败 +
    ``AgentBuilder.build()`` 内部 ``register_extension_act`` 拿不到 act_name 报错.
    """

    plugin_id = "contract_auditor.act"
    act_name = "contract_auditor"

    def get_act_root(self) -> Path:
        return _ACT_DIR / "contract_auditor"

    def get_act_file_path(self) -> Path:
        return self.get_act_root() / "ext_contract_auditor.md"

    def get_tool_names(self) -> list[str]:
        # 5 个 plugin 工具 + word_smart_export（Krow 内置 Word/PDF 出口）
        return [
            "contract_auditor_split_clauses",
            "contract_auditor_classify_clauses",
            "contract_auditor_score_clause_risk",
            "contract_auditor_redline_diff",
            "contract_auditor_index_terms",
            "word_smart_export",
        ]

# =============================================================================
# §6. GatePlugin × 2（强阻断 —— 这是法务 demo 最强的 Gate 演示）
# =============================================================================
class MandatoryClauseGate:
    """法务红线守门：风险报告 / 合同 review 输出必须含 GDPR / 反垄断 / 出口管制 三段.

    实现 ``krow_agent_sdk.protocols.GatePlugin`` Protocol.

    工作机制：扫描最近 score_clause_risk + write_report 输出，确认风险报告
    内确实点出了三类必备条款（按公司法务模板），缺则 BLOCK conclude。

    真实业务价值：
    - GDPR/PIPL/反垄断/出口管制是企业合同的 3 条法律红线
    - hint "请记得检查这三类条款" 在压缩任务时会被 LLM 偷懒跳过
    - 法务事故"漏审 GDPR 条款被罚"通常 7 位数美元起，必须 fail-loud
    """

    plugin_id = "contract_auditor.mandatory_clause_gate"
    phase = "macro"

    def __init__(
        self,
        *,
        required_types: set[str] | None = None,
        strict: bool = True,
    ) -> None:
        self._required = set(required_types or MANDATORY_CLAUSE_TYPES)
        self._strict = bool(strict)

    def get_gate(self) -> Any:
        from krow_agent_sdk.protocols import make_simple_gate

        required = self._required
        strict = self._strict

        def evaluate(parsed: dict, context: dict) -> Any:
            tool_results = context.get("recent_tool_results", []) or []

            # 找最近 classify_clauses 的 label_counts
            classified_labels: set[str] = set()
            for tr in reversed(tool_results):
                if not isinstance(tr, dict):
                    continue
                tn = tr.get("tool_name", "")
                if tn == "contract_auditor_classify_clauses":
                    res = tr.get("result") or {}
                    label_counts = res.get("label_counts") or {}
                    classified_labels = {
                        label for label, cnt in label_counts.items() if cnt > 0
                    }
                    break

            if not classified_labels:
                return GateDecision(
                    verdict=GateVerdict.DEFER,
                    gate_name="mandatory_clause",
                )

            missing = sorted(required - classified_labels)
            if not missing:
                return GateDecision(
                    verdict=GateVerdict.ALLOW,
                    reason=(
                        f"✅ 必备条款齐全：{', '.join(sorted(required))} 全部命中"
                    ),
                    gate_name="mandatory_clause",
                )

            zh_missing = [
                CLAUSE_TAXONOMY.get(m, {}).get("name", m) for m in missing
            ]

            verdict = GateVerdict.BLOCK if strict else GateVerdict.DEFER
            reason = (
                f"❌ 必备条款缺失（{verdict.name}）：合同未识别到 {len(missing)} 类\n"
                f"   缺失类别：{' / '.join(zh_missing)}\n"
                f"   位置：classify_clauses 命中 label 列表\n"
                "   修法：\n"
                "     1. 确认合同里**确实**没有这些条款 → 联系对方补充\n"
                "     2. 条款表述模糊 → 修改 split_clauses 启发式 / 调大 keywords\n"
                "     3. 法务标准强制：缺失即 BLOCK；需 strict=False 才能 DEFER\n"
                "   规范依据：GDPR Art.28 / 反垄断法 / EAR / 公司合规 SOP"
            )
            return GateDecision(
                verdict=verdict,
                reason=reason,
                gate_name="mandatory_clause",
            )

        return make_simple_gate(
            name="mandatory_clause", priority=95, evaluator=evaluate
        )


class HighRiskBlockingGate:
    """法务红线守门：检测到 ≥1 个 high-risk 条款时强制人工审核.

    实现 ``krow_agent_sdk.protocols.GatePlugin`` Protocol.

    业务理由：
    - LLM 看到合同里"无限赔偿 / 不可撤销 IP 转让"会按 LLM 训练分布
      给出"合理范围" / "标准条款"等错判
    - 高风险条款必须人工法务介入，绝不允许 LLM 自动 conclude "无风险"
    - 这是 **3 个 cookbook demo 中最强的 Gate**——直接断 LLM "盖章权"
    """

    plugin_id = "contract_auditor.high_risk_block"
    phase = "macro"

    def __init__(
        self,
        *,
        threshold: float = 0.75,
        require_human_review_marker: bool = True,
    ) -> None:
        self._thr = float(threshold)
        self._marker = bool(require_human_review_marker)

    def get_gate(self) -> Any:
        from krow_agent_sdk.protocols import make_simple_gate

        thr = self._thr
        marker_required = self._marker

        def evaluate(parsed: dict, context: dict) -> Any:
            tool_results = context.get("recent_tool_results", []) or []

            high_risks: list[dict[str, Any]] = []
            for tr in reversed(tool_results):
                if not isinstance(tr, dict):
                    continue
                if tr.get("tool_name") != "contract_auditor_score_clause_risk":
                    continue
                res = tr.get("result") or {}
                risks = res.get("risks") or []
                high_risks = [r for r in risks if r.get("risk_score", 0) >= thr]
                break

            if not high_risks:
                return GateDecision(
                    verdict=GateVerdict.ALLOW,
                    reason="✅ 无 high-risk 条款（risk_score ≥ thr）",
                    gate_name="high_risk_blocking",
                )

            # 检查 final_output / report_text 是否标记了人工审核
            final_text = ""
            for tr in reversed(tool_results):
                if not isinstance(tr, dict):
                    continue
                tn = tr.get("tool_name", "")
                if tn in ("data_analyst_write_report", "word_smart_export"):
                    args = tr.get("args") or {}
                    final_text = args.get("content") or args.get("body") or ""
                    if not final_text:
                        fp = args.get("file_path") or args.get("path")
                        if fp:
                            with suppress(Exception):
                                final_text = Path(fp).read_text(encoding="utf-8")
                    if final_text:
                        break
            if not final_text:
                final_text = str(parsed.get("final_output") or "")

            human_marker = any(
                kw in final_text
                for kw in [
                    "需法务复核", "需要法务审核", "建议人工 review",
                    "REQUIRES LEGAL REVIEW", "Human Review Required",
                    "human-review-required",
                ]
            )

            if marker_required and not human_marker:
                # 列出前 5 条 high-risk
                lines = [
                    f"     - {r['clause_id']} 「{r.get('heading', '')[:40]}」 "
                    f"risk={r['risk_score']:.2f} ({r.get('label')})"
                    for r in high_risks[:5]
                ]
                return GateDecision(
                    verdict=GateVerdict.BLOCK,
                    reason=(
                        f"❌ 检测到 {len(high_risks)} 个 high-risk 条款"
                        f"（risk ≥ {thr:.2f}）但报告未标记人工审核\n"
                        + "\n".join(lines)
                        + "\n"
                        "   修法：\n"
                        "     1. 在风险报告显眼位置加 '需法务复核' / "
                        "'REQUIRES LEGAL REVIEW' 标记\n"
                        "     2. 给每条 high-risk 条款单独一段说明 + 修订建议\n"
                        "     3. 不允许结论里写'整体无风险' / 'low overall risk'\n"
                        "   规范依据：公司合规 SOP §legal-review-mandatory"
                    ),
                    gate_name="high_risk_blocking",
                )

            return GateDecision(
                verdict=GateVerdict.ALLOW,
                reason=(
                    f"✅ 检测到 {len(high_risks)} 个 high-risk 条款，已标记人工审核"
                ),
                gate_name="high_risk_blocking",
            )

        return make_simple_gate(
            name="high_risk_blocking", priority=90, evaluator=evaluate
        )

# =============================================================================
# §7. HintPlugin × 2（软提示）
# =============================================================================
class AmbiguousLanguageHintPlugin:
    """检测合同里的模糊用语，推 LLM 在风险报告里点出.

    实现 ``krow_agent_sdk.protocols.HintPlugin`` Protocol.

    业务理由：
    - reasonable / best efforts / asap / 适当 / 尽快 全是合同纠纷高发短语
    - 法务 review 这类条款时必须明确"哪个 jurisdiction 的 reasonable"
    - LLM 看到这些词不会自动联想到风险，需要 hint 推一把
    """

    plugin_id = "contract_auditor.ambiguous_hint"
    applicable_acts = ["contract_auditor"]

    def hint_for(self, context: dict) -> str | None:
        tool_results = context.get("recent_tool_results", []) or []
        contract_text = ""
        for tr in reversed(tool_results):
            if not isinstance(tr, dict):
                continue
            if tr.get("tool_name") != "contract_auditor_split_clauses":
                continue
            args = tr.get("args") or {}
            res = tr.get("result") or {}
            text_in = args.get("contract_text") or ""
            if text_in:
                contract_text = text_in
            else:
                for c in res.get("clauses", []):
                    contract_text += "\n" + c.get("text", "")
            if contract_text:
                break
        if not contract_text:
            return None

        # 命中模糊词
        hits: list[tuple[str, str, str]] = []
        for pat, label, advice in AMBIGUOUS_PHRASES:
            for m in pat.finditer(contract_text):
                start = max(0, m.start() - 30)
                end = min(len(contract_text), m.end() + 30)
                ctx_snippet = (
                    contract_text[start:end].replace("\n", " ").strip()
                )
                hits.append((label, advice, ctx_snippet))
                if len(hits) >= 8:
                    break
            if len(hits) >= 8:
                break

        if not hits:
            return None

        lines = [
            "## 模糊用语提醒（System 2 软提示）",
            f"检测到 {len(hits)} 处模糊用语 → 写风险报告时建议在「条款语义」段单独列出：",
            "",
        ]
        for label, advice, ctx_snippet in hits:
            lines.append(f"- **`{label}`** ({advice})")
            lines.append(f"  上下文：『...{ctx_snippet}...』")
        return "\n".join(lines)


class MissingDefinitionHintPlugin:
    """检测引号包裹但未定义的疑似术语，推 LLM 标注为风险.

    实现 ``krow_agent_sdk.protocols.HintPlugin`` Protocol.

    业务理由：
    - 合同里出现 "Confidential Information" / "Force Majeure Event" 但没定义
      → 双方理解可能不一致 → 纠纷高发
    - System 1 用 index_terms 找出疑似列表，hint 推 LLM 在风险报告里点出
    """

    plugin_id = "contract_auditor.missing_def_hint"
    applicable_acts = ["contract_auditor"]

    def hint_for(self, context: dict) -> str | None:
        tool_results = context.get("recent_tool_results", []) or []
        for tr in reversed(tool_results):
            if not isinstance(tr, dict):
                continue
            if tr.get("tool_name") != "contract_auditor_index_terms":
                continue
            res = tr.get("result") or {}
            if not res.get("ok"):
                continue
            undefined = res.get("undefined_terms") or []
            if not undefined:
                return None
            lines = [
                "## 未定义术语提醒（System 2 软提示）",
                f"检测到 {len(undefined)} 个引号包裹但未定义的疑似术语 → 风险报告应单独说明：",
                "",
            ]
            for u in undefined[:8]:
                lines.append(
                    f"- **`{u['term']}`**：使用 {u['usage_count']} 次但未见 'means / 是指' 定义"
                )
            lines.append("")
            lines.append(
                "   建议：在风险报告「条款语义」段列出，要求对方补充定义条款"
            )
            return "\n".join(lines)
        return None


# =============================================================================
# §8. EventListenerPlugin（法务审计强制留痕）
# =============================================================================
class LegalAuditTrailListener:
    """法务合规审计：每个工具调用 + Gate BLOCK + 任务结束都落 .audit.jsonl.

    实现 ``krow_agent_sdk.protocols.EventListenerPlugin`` Protocol.

    业务理由：
    - 法务 review 是公司合规 / SOX 审计强制留痕场景
    - "什么时候、谁、用什么工具、怎么决策" 全部需要可追溯
    - 文件名 + sha256 hash 让审计员能验证文件完整性
    """

    plugin_id = "contract_auditor.legal_audit"

    def __init__(
        self,
        *,
        verbose: bool = True,
        audit_log_path: str | Path | None = None,
        contract_path: str | Path | None = None,
    ) -> None:
        self._verbose = bool(verbose)
        self._tool_calls = 0
        self._gate_blocks = 0
        self._high_risk_count = 0
        self._path: Path | None = (
            _normalize_path(audit_log_path) if audit_log_path else None
        )
        self._contract_path: Path | None = (
            _normalize_path(contract_path) if contract_path else None
        )
        self._contract_sha256: str | None = None
        if self._contract_path and self._contract_path.exists():
            with suppress(Exception):
                self._contract_sha256 = hashlib.sha256(
                    self._contract_path.read_bytes()
                ).hexdigest()
        if self._path:
            with suppress(OSError):
                self._path.parent.mkdir(parents=True, exist_ok=True)
            # 文件头：审计开始
            self._append({
                "kind": "audit_session_start",
                "contract_path": (
                    str(self._contract_path) if self._contract_path else None
                ),
                "contract_sha256": self._contract_sha256,
                "actor": os.environ.get("USERNAME") or os.environ.get("USER"),
            })

    def get_subscriptions(self) -> list[dict[str, Any]]:
        return [
            {"topic": "tool.call_completed", "handler": self._on_tool_done},
            {"topic": "gate.blocked", "handler": self._on_gate_blocked},
            {"topic": "agent.task_complete", "handler": self._on_task_done},
            {"topic": "agent.task_failed", "handler": self._on_task_failed},
        ]

    def _append(self, record: dict[str, Any]) -> None:
        if not self._path:
            return
        with suppress(Exception):
            record.setdefault("timestamp", time.time())
            record.setdefault(
                "timestamp_iso",
                datetime.now(timezone.utc).isoformat(),
            )
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _on_tool_done(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        tool_name = payload.get("tool_name", "")
        self._tool_calls += 1
        if tool_name == "contract_auditor_score_clause_risk":
            res = payload.get("result") or {}
            high = res.get("high_count", 0)
            self._high_risk_count = max(self._high_risk_count, int(high))
            if self._verbose:
                print(
                    f"  📋 风险评分：high={high} / "
                    f"medium={res.get('medium_count', 0)}"
                )
            self._append({
                "kind": "risk_score_summary",
                "tool_name": tool_name,
                "high_count": high,
                "medium_count": res.get("medium_count"),
            })
            return

        if self._verbose and tool_name.startswith("contract_auditor_"):
            print(f"  🔧 {tool_name}")

        self._append({
            "kind": "tool_call_completed",
            "tool_name": tool_name,
            "ok": payload.get("ok", True),
            "elapsed_ms": payload.get("elapsed_ms"),
        })

    def _on_gate_blocked(self, event: Any) -> None:
        self._gate_blocks += 1
        payload = getattr(event, "payload", {}) or {}
        if self._verbose:
            print(
                f"  ⛔ gate BLOCK: {payload.get('gate_name')} — "
                f"{(payload.get('reason') or '')[:80]}..."
            )
        # 法务合规事件：落审计 jsonl + 标 compliance_event
        self._append({
            "kind": "gate_blocked",
            "gate_name": payload.get("gate_name"),
            "reason_excerpt": (payload.get("reason") or "")[:300],
            "compliance_event": True,
        })

    def _on_task_done(self, event: Any) -> None:
        if self._verbose:
            print(
                f"\n✅ 合同审阅完成：tool_calls={self._tool_calls} / "
                f"gate_blocks={self._gate_blocks} / "
                f"high_risk={self._high_risk_count}"
            )
        self._append({
            "kind": "audit_session_end",
            "tool_calls": self._tool_calls,
            "gate_blocks": self._gate_blocks,
            "high_risk_count": self._high_risk_count,
            "outcome": "complete",
        })

    def _on_task_failed(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        if self._verbose:
            print(f"\n❌ 审阅失败：{payload.get('reason', 'unknown')}")
        self._append({
            "kind": "audit_session_end",
            "tool_calls": self._tool_calls,
            "gate_blocks": self._gate_blocks,
            "high_risk_count": self._high_risk_count,
            "outcome": "failed",
            "reason": payload.get("reason"),
        })

# =============================================================================
# §9. ObservabilityPlugin（OpenTelemetry tracing —— 与 PR-A Prometheus 互补）
# =============================================================================
class OTelTracingObservabilityPlugin:
    """把 Krow agent 内部 metrics + audit 事件 forward 到 OpenTelemetry Tracer.

    实现 ``krow_agent_sdk.protocols.ObservabilityPlugin`` Protocol.

    工作机制：
    - SDK build() 时调 register(facade) 注入 ObservabilityFacade
    - 每个 tool / step / gate event 起一个 span
    - tool 调用嵌套在 step span 下；gate BLOCK 标 ERROR 状态
    - 真实部署：通过 OTLP exporter 推到 Jaeger / Tempo / Datadog APM

    Demo 模式（无 opentelemetry-sdk 时）：
    - 自动降级为 stdout（仍演示完整数据流；不阻塞 cookbook 跑）
    - 真实生产请装 ``opentelemetry-api>=1.20`` + ``opentelemetry-sdk>=1.20``
      + ``opentelemetry-exporter-otlp>=1.20``
    """

    plugin_id = "contract_auditor.observability"

    def __init__(
        self,
        *,
        otlp_endpoint: str | None = None,
        service_name: str = "krow_contract_auditor",
        verbose: bool = False,
    ) -> None:
        """
        Args:
            otlp_endpoint: OTLP gRPC endpoint
                (e.g. "http://otel-collector:4317")
                None → demo 模式（不发送到 collector）
            service_name: OTel service.name 标签
            verbose: True 时每个 metric / span 都 print
        """
        self._endpoint = otlp_endpoint
        self._service_name = service_name
        self._verbose = bool(verbose)

        self._tracer = None
        self._meter = None
        self._available = False
        self._counter_metrics: dict[str, Any] = {}
        self._tool_call_counter = None
        self._gate_block_counter = None
        self._span_stack: list[Any] = []

        try:
            from opentelemetry import metrics, trace
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import (
                ConsoleMetricExporter,
                PeriodicExportingMetricReader,
            )
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import (
                BatchSpanProcessor,
                ConsoleSpanExporter,
            )

            resource = Resource.create({"service.name": service_name})

            tracer_provider = TracerProvider(resource=resource)
            if self._endpoint:
                with suppress(Exception):
                    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                        OTLPSpanExporter,
                    )
                    tracer_provider.add_span_processor(
                        BatchSpanProcessor(OTLPSpanExporter(endpoint=self._endpoint))
                    )
            if self._verbose:
                tracer_provider.add_span_processor(
                    BatchSpanProcessor(ConsoleSpanExporter())
                )
            trace.set_tracer_provider(tracer_provider)
            self._tracer = trace.get_tracer("krow.contract_auditor")

            metric_reader = PeriodicExportingMetricReader(
                ConsoleMetricExporter() if self._verbose else _NoopMetricExporter()
            )
            metric_provider = MeterProvider(
                resource=resource, metric_readers=[metric_reader]
            )
            metrics.set_meter_provider(metric_provider)
            self._meter = metrics.get_meter("krow.contract_auditor")
            self._tool_call_counter = self._meter.create_counter(
                "contract_tool_calls_total",
                description="Number of tool calls in contract-auditor",
            )
            self._gate_block_counter = self._meter.create_counter(
                "contract_gate_blocks_total",
                description="Number of Gate BLOCKs in contract-auditor",
            )

            self._available = True
        except ImportError:
            logger.info(
                "opentelemetry-* 未装 → ObservabilityPlugin 降级 stdout 模式 "
                "（pip install opentelemetry-api opentelemetry-sdk 启用真实 OTel 上报）"
            )

    def register(self, observability_facade: Any) -> None:
        """SDK 注入 facade，本 plugin 注册 metric / audit callback."""
        observability_facade.add_metric_sink(self._on_metric)
        observability_facade.add_audit_sink(self._on_audit)

    def _on_metric(self, name: str, value: float, labels: dict[str, Any]) -> None:
        if self._verbose:
            with suppress(Exception):
                safe_labels = {
                    k: v for k, v in labels.items()
                    if isinstance(v, (str, int, float, bool))
                }
                print(f"[obs:metric] {name}={value} labels={safe_labels}")

        if not self._available:
            return

        # 启动 span (per-tool-call) —— 用 tool_name 作为 span 名
        try:
            tool_name = (
                labels.get("tool_name") if isinstance(labels, dict) else None
            )
            if tool_name and self._tracer is not None:
                # 记录 counter
                if self._tool_call_counter is not None:
                    safe_attrs = {
                        k: str(v) for k, v in labels.items()
                        if isinstance(v, (str, int, float, bool))
                    }
                    self._tool_call_counter.add(1, attributes=safe_attrs)
                # 起一个简短 span（不 nest，因为 SDK 没传 step context）
                with self._tracer.start_as_current_span(
                    f"tool.{tool_name}"
                ) as span:
                    safe_attrs = {
                        k: str(v) for k, v in labels.items()
                        if isinstance(v, (str, int, float, bool))
                    }
                    for k, v in safe_attrs.items():
                        span.set_attribute(k, v)
                    span.set_attribute("metric.value", float(value))
        except Exception as exc:  # noqa: BLE001
            logger.debug("OTel metric forward failed: %s", exc)

    def _on_audit(self, event_kind: str, payload: dict[str, Any]) -> None:
        if self._verbose:
            with suppress(Exception):
                print(f"[obs:audit] {event_kind} payload={payload}")
        if not self._available:
            return
        try:
            if event_kind == "gate_blocked" and self._gate_block_counter is not None:
                gate_name = str(payload.get("gate_name", "unknown"))
                self._gate_block_counter.add(1, attributes={"gate_name": gate_name})
            if self._tracer is not None:
                with self._tracer.start_as_current_span(
                    f"audit.{event_kind}"
                ) as span:
                    for k, v in payload.items():
                        if isinstance(v, (str, int, float, bool)):
                            span.set_attribute(k, str(v))
                    if event_kind == "gate_blocked":
                        from opentelemetry.trace import Status, StatusCode
                        span.set_status(Status(StatusCode.ERROR))
        except Exception as exc:  # noqa: BLE001
            logger.debug("OTel audit forward failed: %s", exc)


# 内部 noop exporter 用来 demo 模式抑制控制台噪音
class _NoopMetricExporter:
    def export(self, metrics_data: Any, timeout_millis: float = 10_000) -> Any:
        return None

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 10_000) -> None:
        return None


__all__ = [
    "Clause",
    "split_clauses",
    "classify_clauses",
    "score_clause_risk",
    "redline_diff",
    "index_terms",
    "ContractAuditorToolPlugin",
    "ContractAuditorACTPlugin",
    "MandatoryClauseGate",
    "HighRiskBlockingGate",
    "AmbiguousLanguageHintPlugin",
    "MissingDefinitionHintPlugin",
    "LegalAuditTrailListener",
    "OTelTracingObservabilityPlugin",
    "CLAUSE_TAXONOMY",
    "HIGH_RISK_CLAUSE_TYPES",
    "MANDATORY_CLAUSE_TYPES",
    "AMBIGUOUS_PHRASES",
]