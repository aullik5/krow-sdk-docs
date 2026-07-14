"""Datasheet 批量并发解析 cookbook plugin SSOT（模拟 KAD 生产场景）.

> 场景：KAD 工程团队在 Krow agent 下批量解析元器件 datasheet PDF（电阻/电容/芯片
> 建库）。现状全程串行（100 份≈2h）。本 cookbook 演示如何用 SDK 在**生产 agent 认知
> 回路内**做并发批量解析，同时保证 per-item 身份/失败隔离/覆盖可判定/大批量续跑
> （KAD 需求 N1–N5）。

复用而非重复造轮子（DRY）：批量并发/账本/续跑一律复用主仓
``modules.agent.batch_orchestrator.orchestrate_batch``（该编排器抽象自 reasoning 管线
``research_corpus_targets`` 的生产验证范式）。本 cookbook **不自造线程池 / 账本**，只：
- 提供 per-item「解析单份 datasheet」的业务工具（datasheet_parse_one）；
- 用 datasheet_batch_parse 把一批交给编排器，产 per-item 覆盖报告；
- 用 DatasheetBatchCoverageGate 守门（全失败 / 覆盖率过低 → BLOCK conclude）。

TURBO 边界：解析单份的**结构化字段抽取**可交 LLM（这里 cookbook 用确定性正则解析
合成 datasheet 以便零 LLM smoke；真实场景把 parse_one 换成 VLM/文档解析即可）；
并发编排 / 身份归属 / 覆盖记账 = System 1 确定性（编排器负责）。
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# ── 复用主仓通用并发编排器（严禁重复造轮子）──────────────────────────────
# 运行期（SDK runtime 已装）可直接 import modules.*；smoke 测试在纯 SDK 环境下若
# import 失败，datasheet_batch_parse 会 fail-loud 指引安装 runtime。
try:
    from modules.agent.batch_orchestrator import (  # type: ignore
        STATUS_COMPLETED,
        STATUS_DEGRADED,
        STATUS_FAILED,
        BatchItem,
        ItemResult,
        orchestrate_batch,
    )
    _ORCHESTRATOR_AVAILABLE = True
except Exception:  # noqa: BLE001 — 纯 SDK 无 runtime 时降级（工具 fail-loud 提示）
    _ORCHESTRATOR_AVAILABLE = False
    STATUS_COMPLETED, STATUS_FAILED, STATUS_DEGRADED = "completed", "failed", "degraded"


# ============================================================
# §0. 黄金错误模板
# ============================================================


def _golden_error(msg: str, *, where: str, fixes: Iterable[str]) -> dict[str, Any]:
    parts = [f"❌ {msg}", f"   位置：{where}", "   修法："]
    for i, fix in enumerate(fixes, 1):
        parts.append(f"     {i}. {fix}")
    return {"ok": False, "error": "\n".join(parts)}


# ============================================================
# §1. per-item：解析单份 datasheet（业务工具）
# ============================================================
#
# 真实 kad 场景：单份内部是 IO 密集远程往返（逐候选页选页、逐页文档解析、VLM/LLM）。
# cookbook 为可零 LLM smoke，用**确定性正则**从合成 datasheet 文本抽取关键规格字段。
# 把本函数换成真实的 VLM/PDF 解析即可用于生产（编排契约不变）。

# 合成 datasheet 关键字段（电子元器件通用规格）。
_FIELD_PATTERNS: dict[str, str] = {
    "part_number": r"(?:Part\s*Number|型号)\s*[:：]\s*([^\n]+)",
    "manufacturer": r"(?:Manufacturer|厂商)\s*[:：]\s*([^\n]+)",
    "package": r"(?:Package|封装)\s*[:：]\s*([^\n]+)",
    "operating_voltage": r"(?:Operating\s*Voltage|工作电压)\s*[:：]\s*([^\n]+)",
    "operating_temp": r"(?:Operating\s*Temperature|工作温度)\s*[:：]\s*([^\n]+)",
}


def parse_datasheet_file(path: str, *, model: str = "", project_root: str = "") -> dict[str, Any]:
    """解析单份 datasheet 文件 → 结构化规格字段（per-item 业务逻辑）.

    Args:
        path: datasheet 文件路径（cookbook 用 .txt/.md 合成；真实场景传 PDF 路径）。
            支持项目内相对路径（如 ``upload/x.txt``），配合 project_root 解析。
        model: 期望型号（用于 per-item 身份校验：解析出的 part_number 应与之匹配）。
        project_root: 项目根；用于把相对 path 解析到项目内（贴合 agent 沙箱约定）。

    Returns:
        dict 含 ok / model / fields / raw_chars / source。ok=False 表示单份解析失败
        （文件缺失 / 空 / 关键字段全缺）——由编排器隔离记 failed，不拖垮整批。
    """
    p = Path(path)
    # 相对路径优先相对 project_root 解析（agent 传项目内相对路径），再退回 CWD。
    if not p.is_absolute() and project_root:
        candidate = Path(project_root) / path
        if candidate.is_file():
            p = candidate
    if not p.is_file():
        return _golden_error(
            f"datasheet 文件不存在：{path}",
            where=f"parse_datasheet_file(path={path!r})",
            fixes=["确认路径正确", "确认文件已放入项目"],
        )
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return _golden_error(
            f"读取失败：{exc}",
            where=f"parse_datasheet_file(path={path!r})",
            fixes=["确认文件可读", "确认编码 UTF-8"],
        )
    if not text.strip():
        return _golden_error(
            "datasheet 内容为空",
            where=f"parse_datasheet_file(path={path!r})",
            fixes=["确认文件非空"],
        )

    fields: dict[str, str] = {}
    for key, pat in _FIELD_PATTERNS.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fields[key] = m.group(1).strip()

    if not fields:
        return _golden_error(
            "未抽到任何规格字段（疑似格式不识别或损坏 datasheet）",
            where=f"parse_datasheet_file(path={path!r})",
            fixes=["确认 datasheet 含 Part Number / Package 等标准字段"],
        )

    part_number = fields.get("part_number", "")
    # per-item 身份一致性：若给了期望 model 但解析出的 part_number 对不上 → 降级（可判定）。
    degraded = bool(model) and bool(part_number) and model.lower() not in part_number.lower()
    return {
        "ok": True,
        "model": model or part_number,
        "part_number": part_number,
        "fields": fields,
        "raw_chars": len(text),
        "source": str(p),
        "degraded": degraded,
        "n_fields": len(fields),
    }


# ============================================================
# §2. 批量编排工具（复用 orchestrate_batch）
# ============================================================


def _coerce_items(raw: Any) -> list[dict[str, str]]:
    """归一 items 输入为 [{model, path}]（输入鲁棒）."""
    out: list[dict[str, str]] = []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [raw]
    for i, item in enumerate(raw or [], start=1):
        if isinstance(item, dict):
            model = str(item.get("model") or item.get("id") or item.get("part") or f"item{i}").strip()
            path = str(item.get("path") or item.get("file") or item.get("pdf") or "").strip()
        else:
            model, path = f"item{i}", str(item).strip()
        if path:
            out.append({"model": model or f"item{i}", "path": path})
    return out


def datasheet_batch_parse(
    items: Any,
    *,
    project_root: str = "",
    max_workers: int = 8,
    batch_size: int = 50,
    budget_s: float = 800.0,
) -> dict[str, Any]:
    """并发批量解析 datasheet（复用 orchestrate_batch）+ per-item 覆盖报告.

    满足 KAD N1–N5：并行吞吐 / per-item 身份归属 / 失败隔离 / 覆盖可判定 / 续跑。

    Args:
        items: [{model, path}] 或路径列表。model = 确定性身份（结果据此归属）。
        project_root: 项目根（账本落 <root>/.krow/batch/）。缺省用当前目录。
        max_workers: 并发度（N1）。
        batch_size: 单次调用最多处理数（N5，超量留待续跑）。
        budget_s: 软预算秒（N5）。

    Returns:
        dict 含 ok/summary/total/completed/failed/degraded/remaining/coverage/
        should_continue/results/ledger_path。results 每项 per-item 归属确定。
    """
    if not _ORCHESTRATOR_AVAILABLE:
        return _golden_error(
            "并发编排器不可用（modules.agent.batch_orchestrator 未装）",
            where="datasheet_batch_parse",
            fixes=[
                "确认 krow-agent-sdk-runtime 已安装（krow-sdk-install --api-key ...）",
                "本工具依赖 runtime 提供的 modules.* 通用编排基础设施",
            ],
        )

    norm = _coerce_items(items)
    if not norm:
        return _golden_error(
            "items 为空",
            where="datasheet_batch_parse(items=...)",
            fixes=["传 [{'model','path'}] 或 datasheet 路径列表（≥1）"],
        )

    root = Path(project_root).resolve() if project_root else Path.cwd()
    ledger_dir = root / ".krow" / "batch"

    batch_items = [BatchItem(item_id=it["model"], payload=it) for it in norm]

    def _process_one(bi: "BatchItem") -> "ItemResult":
        payload = bi.payload or {}
        res = parse_datasheet_file(
            str(payload.get("path", "")),
            model=str(payload.get("model", "")),
            project_root=str(root),
        )
        if not res.get("ok"):
            return ItemResult(item_id=bi.item_id, status=STATUS_FAILED, error=res.get("error"))
        status = STATUS_DEGRADED if res.get("degraded") else STATUS_COMPLETED
        return ItemResult(item_id=bi.item_id, status=status, output=res)

    report = orchestrate_batch(
        batch_items,
        _process_one,
        ledger_key="datasheet_batch",
        ledger_dir=ledger_dir,
        max_workers=max_workers,
        batch_size=batch_size,
        budget_s=budget_s,
    )

    results = []
    for it in report.items:
        entry = {"model": it.item_id, "status": it.status, "duration_ms": it.duration_ms}
        if it.status == STATUS_FAILED:
            entry["error"] = it.error
        elif isinstance(it.output, dict):
            entry["fields"] = it.output.get("fields")
            entry["part_number"] = it.output.get("part_number")
        results.append(entry)

    return {
        "ok": True,
        "summary": report.summary_line(),
        "total": report.total,
        "completed": report.completed,
        "failed": report.failed,
        "degraded": report.degraded,
        "remaining": report.remaining,
        "coverage": report.coverage,
        "should_continue": report.should_continue,
        "converged": report.converged,
        "ledger_path": report.ledger_path,
        "results": results,
    }


# ============================================================
# §3. ToolPlugin
# ============================================================


# runtime 用 handler(**filtered_args) 按 input_schema property 名注入关键字参数
# （见 modules/tools/manager.py:_validate_handler_signature / handler(**handler_args)）。
# 因此 handler 形参名必须与 schema properties 对齐，并收 **kwargs 容忍注入的元数据。
def _tool_parse_one(
    path: str = "", model: str = "", **_: Any
) -> dict[str, Any]:
    return parse_datasheet_file(str(path or ""), model=str(model or ""))


def _tool_batch_parse(
    items: Any = None,
    project_root: str = "",
    max_workers: int = 8,
    batch_size: int = 50,
    budget_s: float = 800.0,
    **_: Any,
) -> dict[str, Any]:
    return datasheet_batch_parse(
        items,
        project_root=str(project_root or ""),
        max_workers=int(max_workers or 8),
        batch_size=int(batch_size or 50),
        budget_s=float(budget_s or 800.0),
    )


class DatasheetBatchToolPlugin:
    """实现 ``krow_agent_sdk.protocols.ToolPlugin``。注册 2 个 System 1 工具。"""

    plugin_id = "datasheet_batch.tools"

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "datasheet_parse_one",
                "description": (
                    "解析单份 datasheet → 结构化规格字段（Part Number/封装/电压/温度等）。"
                    "per-item 业务工具；批量场景请优先用 datasheet_batch_parse。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "datasheet 文件路径"},
                        "model": {"type": "string", "description": "期望型号（身份校验用）"},
                    },
                    "required": ["path"],
                },
                "handler": _tool_parse_one,
            },
            {
                "name": "datasheet_batch_parse",
                "description": (
                    "并发批量解析一批 datasheet（复用主仓通用并发编排器）。"
                    "保证 per-item 身份归属 + 失败隔离 + 覆盖可判定（N 中完成 M/失败 K/降级 L）"
                    "+ 大批量分块续跑。返回 per-item 结果 + 覆盖报告。"
                    "**批量任务首选此工具**，不要逐份串行调 datasheet_parse_one。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "description": "[{model,path}] 或路径列表；model=确定性身份",
                        },
                        "project_root": {"type": "string", "description": "项目根（账本落盘）"},
                        "max_workers": {"type": "integer", "default": 8, "description": "并发度"},
                        "batch_size": {"type": "integer", "default": 50, "description": "单次处理上限（续跑）"},
                        "budget_s": {"type": "number", "default": 800.0, "description": "软预算秒（超时主动收尾，剩余留待续跑）"},
                    },
                    "required": ["items"],
                },
                "handler": _tool_batch_parse,
            },
        ]


# ============================================================
# §4. GatePlugin（覆盖可判定守门 · N4）
# ============================================================
#
# 红线：批量解析若「全失败」或「覆盖率过低」，不应让 agent 静默 conclude 成功。
# 覆盖率对收尾可判定是 KAD N4 的核心诉求。


_MIN_COVERAGE = 0.5  # 覆盖率下限（可按业务调）；低于此且非空批 → BLOCK


class DatasheetBatchCoverageGate:
    """批量覆盖率守门：全失败 / 覆盖率过低 → BLOCK conclude（N4 可判定）。

    实现 ``krow_agent_sdk.protocols.GatePlugin``。
    """

    plugin_id = "datasheet_batch.coverage_gate"
    phase = "macro"

    def get_gate(self) -> Any:
        from krow_agent_sdk.protocols import (
            GateDecision,
            GateVerdict,
            make_simple_gate,
        )

        def evaluate(parsed: dict, context: dict) -> Any:
            tool_results = context.get("recent_tool_results", []) or []
            batch_result: dict | None = None
            for tr in tool_results:
                if not isinstance(tr, dict):
                    continue
                if tr.get("tool_name") == "datasheet_batch_parse":
                    res = tr.get("result", {}) or {}
                    if isinstance(res, dict) and res.get("ok"):
                        batch_result = res

            if batch_result is None:
                return GateDecision(
                    verdict=GateVerdict.DEFER, gate_name="datasheet_batch_coverage"
                )

            total_this = batch_result.get("completed", 0) + batch_result.get("failed", 0) + batch_result.get("degraded", 0)
            if total_this == 0:
                return GateDecision(verdict=GateVerdict.DEFER, gate_name="datasheet_batch_coverage")

            completed = batch_result.get("completed", 0)
            coverage = completed / total_this if total_this else 0.0
            if completed == 0:
                return GateDecision(
                    verdict=GateVerdict.BLOCK,
                    reason=(
                        "❌ 批量解析全部失败（0 份成功）\n"
                        "   位置：datasheet_batch_parse（completed=0）\n"
                        "   修法：\n"
                        "     1. 检查 datasheet 路径/格式是否正确\n"
                        "     2. 查看 per-item results[].error 定位失败原因\n"
                        "   规范依据：批量解析全失败不能报成功 conclude（N4 覆盖可判定）"
                    ),
                    gate_name="datasheet_batch_coverage",
                )
            if coverage < _MIN_COVERAGE:
                return GateDecision(
                    verdict=GateVerdict.BLOCK,
                    reason=(
                        f"❌ 批量解析覆盖率过低（{coverage:.0%} < {_MIN_COVERAGE:.0%}）\n"
                        f"   位置：datasheet_batch_parse（completed={completed}/{total_this}）\n"
                        "   修法：修复失败份或说明为何可接受该覆盖率，再 conclude\n"
                        "   规范依据：低覆盖率交付需显式判定，不可静默报成功"
                    ),
                    gate_name="datasheet_batch_coverage",
                )
            return GateDecision(
                verdict=GateVerdict.ALLOW,
                reason=f"✅ 批量覆盖率校验通过：{completed}/{total_this}（{coverage:.0%}）",
                gate_name="datasheet_batch_coverage",
            )

        return make_simple_gate(
            name="datasheet_batch_coverage", priority=85, evaluator=evaluate
        )


# ============================================================
# §5. ACTPlugin
# ============================================================


class DatasheetBatchACTPlugin:
    """实现 ``krow_agent_sdk.protocols.ACTPlugin``。"""

    plugin_id = "datasheet_batch.act"
    act_name = "datasheet_batch"

    def get_act_root(self) -> Path:
        return Path(__file__).parent / "act_assets" / "datasheet_batch"

    def get_act_file_path(self) -> Path:
        return self.get_act_root() / "ext_datasheet_batch.md"

    def get_tool_names(self) -> list[str]:
        return [
            "datasheet_parse_one",
            "datasheet_batch_parse",
            "smart_file_write",
        ]


__all__ = [
    "parse_datasheet_file",
    "datasheet_batch_parse",
    "DatasheetBatchToolPlugin",
    "DatasheetBatchCoverageGate",
    "DatasheetBatchACTPlugin",
]
