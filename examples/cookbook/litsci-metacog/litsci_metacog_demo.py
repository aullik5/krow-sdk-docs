"""Krow SDK Cookbook · 决策脑三注册表配置 demo（文献检索完整度）。

演示如何把一个垂直功能（这里以"文献检索下载完整度"为例）的信号接进 Krow
**决策脑**（GWT 全局工作站），让它对你的任务"看得见、叫得醒、算得清"。

本文件自包含——不依赖任何真实 litsci 内部实现，用一个最小的"执行器"对象
（暴露 ``_step_results``，与 Krow 真实 ``ProgressiveExecutor`` 同形）来说明
contributor 如何读工具返回值。真实 litsci 的等价实现见主仓
``packages/krow-worker-litsci-plugin/krow_worker_litsci/litsci_situation_contributors.py``。

三注册表回顾：
- **SituationContributor**（观测层）：``applicable`` + ``__call__ -> {"error_vector","signals"}``
- **WakeTrigger**（唤醒层）：``(prev, curr, delta, ledger) -> str | None``
- **DecisionClassifier**（结算层）：``(action, snap, ledger) -> str | None``（本 demo 复用核心）
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── System-1 常量（集中，不散落）─────────────────────────────────────────────
#: 下载失败率达此阈 = 交付完整度告急。
DOWNLOAD_GAP_THRESHOLD = 0.5
#: 判"检索有果却零下载"的最小候选篇数（低于此波动噪声大，不唤醒）。
MIN_PAPERS_FOR_GAP = 3


def _iter_tool_outputs(executor: Any, tool_prefix: str):
    """遍历 executor 工具历史里指定前缀工具的 output dict（复用 executor SSOT）。"""
    results = getattr(executor, "_step_results", None)
    if not isinstance(results, dict):
        return
    for sr in results.values():
        tool = str(getattr(sr, "tool", "") or "")
        if tool.startswith(tool_prefix):
            out = getattr(sr, "output", None)
            if isinstance(out, dict):
                yield out


def _aggregate_counts(executor: Any) -> dict[str, int]:
    """聚合检索/下载计数（复用工具返回值 SSOT，不新造账本）。"""
    downloaded = failed = requested = papers_found = search_ran = 0
    for out in _iter_tool_outputs(executor, "download_pdf"):
        counts = out.get("counts")
        if isinstance(counts, dict):
            downloaded += int(counts.get("downloaded", 0) or 0)
            failed += int(counts.get("failed", 0) or 0)
            requested += int(counts.get("requested", 0) or 0)
    for out in _iter_tool_outputs(executor, "paper_search"):
        papers = out.get("papers")
        if isinstance(papers, list):
            search_ran += 1
            papers_found = max(papers_found, len(papers))
    return {
        "downloaded": downloaded,
        "failed": failed,
        "requested": requested,
        "papers_found": papers_found,
        "search_ran": search_ran,
    }


class DownloadCompletenessContributor:
    """观测层：把"文献下载完整度"写进决策脑工作站。

    - ``error_vector.download_gap`` = failed/requested —— 喂核心
      ``_trigger_stall`` / ``_trigger_worsening`` 的"持续不降 / 变差"判定；
    - ``signals`` = 计数明细 —— 供 :func:`wake_zero_download_with_hits` 语义判定。
    """

    def applicable(self, executor: Any) -> bool:
        # 收窄：有检索或下载活动才自报适用（防"传感器失活"假阳）。
        c = _aggregate_counts(executor)
        return bool(c["search_ran"] or c["requested"])

    def __call__(self, executor: Any) -> dict[str, Any]:
        try:
            c = _aggregate_counts(executor)
            if not (c["search_ran"] or c["requested"]):
                return {}
            signals: dict[str, Any] = {
                "papers_found": c["papers_found"],
                "dl_requested": c["requested"],
                "dl_downloaded": c["downloaded"],
                "dl_failed": c["failed"],
                "search_ran": c["search_ran"],
            }
            error_vector: dict[str, float] = {}
            if c["requested"] > 0:
                error_vector["download_gap"] = round(c["failed"] / c["requested"], 4)
            out: dict[str, Any] = {"signals": signals}
            if error_vector:
                out["error_vector"] = error_vector
            return out
        except Exception as exc:  # noqa: BLE001 — 领域信号纯增益，绝不拖垮态势装配
            logger.debug("download completeness contributor 跳过：%s", exc)
            return {}


def wake_zero_download_with_hits(prev: Any, curr: Any, delta: Any, ledger: Any) -> str | None:
    """唤醒层：检索有果却零下载 / 下载失败率越阈 → 唤醒决策脑（L2 · advisory）。

    门禁靠 signals 键天然隔离——非本领域任务的 snapshot 没有这些键，返 None。
    去重（每任务一次）由调用方 ``ledger.note_wake`` 冷却拍负责，这里保持纯谓词。
    """
    try:
        sig = getattr(curr, "signals", None) or {}
        papers = sig.get("papers_found")
        requested = sig.get("dl_requested")
        downloaded = sig.get("dl_downloaded")
        failed = sig.get("dl_failed")
        if not isinstance(requested, int):
            return None
        # 形态 A：有候选却零下载。
        if (
            isinstance(papers, int)
            and papers >= MIN_PAPERS_FOR_GAP
            and requested > 0
            and downloaded == 0
        ):
            return (
                f"zero_download:检索到{papers}篇候选却零下载——"
                f"放宽约束/换源继续，或诚实转交付元数据清单"
            )
        # 形态 B：下载失败率越阈。
        if (
            requested > 0
            and isinstance(failed, int)
            and failed / requested >= DOWNLOAD_GAP_THRESHOLD
        ):
            return f"download_gap:{failed}/{requested} 下载失败（多为付费墙）——转交付元数据清单"
    except Exception as exc:  # noqa: BLE001 — 领域触发器纯增益
        logger.debug("zero download trigger 跳过：%s", exc)
    return None


def register(strict: bool = True) -> dict[str, str]:
    """向决策脑三注册表登记本 demo 的 contributor + wake trigger（幂等 · fail-soft）。

    Args:
        strict: True 时缺 SDK/runtime 直接抛（demo 期望装好环境）；False 时静默跳过
            （独立分发无决策脑时不拖垮 boot——真实插件用这个模式）。

    Returns:
        实际登记的 FQCN dict（``{"contributor": ..., "wake_trigger": ...}``）。
    """
    try:
        from krow_agent_sdk.metacognition import (
            register_situation_contributor,
            register_wake_trigger,
        )
    except Exception:  # noqa: BLE001 — 无 SDK/runtime 环境
        if strict:
            raise
        return {}
    return {
        "contributor": register_situation_contributor(DownloadCompletenessContributor),
        "wake_trigger": register_wake_trigger(wake_zero_download_with_hits),
    }


__all__ = [
    "DownloadCompletenessContributor",
    "wake_zero_download_with_hits",
    "register",
    "DOWNLOAD_GAP_THRESHOLD",
    "MIN_PAPERS_FOR_GAP",
]
