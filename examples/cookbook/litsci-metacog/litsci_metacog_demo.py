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

**唤醒声明面**（2026-07-27 起，本 demo 一并演示——不声明的代价是实打实的）：
- ``value_axis``：这条唤醒争的是哪一类价值（accuracy / completeness / speed /
  cost）。裁决按"价值轴权重 × 强度"排序，不声明 = 落最低档。
- ``error_axis`` + ``handled_by``：谁来处置。不声明会被满秩校验点名——你的触发器
  会一直唤醒而系统不知道该拿它怎么办。
- **自报强度**：返 ``(事由, magnitude)`` 二元组。**只返字符串则强度恒 1.0**，
  而核心触发器都在自报强度 —— 恒 1.0 的域触发器同拍竞争时会系统性垫底
  （生产 litsci 曾出现连续 25 拍命中、一次没赢过裁决）。
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
#: 本 demo 的领域轴名。领域轴要带域前缀防撞名；``register_domain_axis`` 在
#: :func:`register` 里登记（模块导入期不碰 SDK，保持无 runtime 也能 import）。
AXIS_DOWNLOAD_GAP = "litsci_download_gap"
#: 谁来处置这条轴。必须是**真实存在且有执行器**的决策——写 advisory/planned
#: 那种空头支票会在注册期被拒。这两条决策的语义正好对应我们的两条出路：
#: ``replan`` 换源/放宽约束重试，``converge`` 诚实转交付元数据清单。
HANDLED_BY = ("replan", "converge")


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


def aggregate_counts(executor: Any) -> dict[str, int]:
    """聚合检索/下载计数（复用工具返回值 SSOT，不新造账本）。

    公开给同 cookbook 的执行面 demo（``litsci_actuation_demo``）复用：观测与执行
    必须读**同一份**计数，各算各的就会出现"传感器说缺、执行器说不缺"。
    """
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

    - ``error_vector[AXIS_DOWNLOAD_GAP]`` = failed/requested —— 喂核心
      ``_trigger_stall`` / ``_trigger_worsening`` 的"持续不降 / 变差"判定；
    - ``signals`` = 计数明细 —— 供 :func:`wake_zero_download_with_hits` 语义判定。
    """

    def applicable(self, executor: Any) -> bool:
        # 收窄：有检索或下载活动才自报适用（防"传感器失活"假阳）。
        c = aggregate_counts(executor)
        return bool(c["search_ran"] or c["requested"])

    def __call__(self, executor: Any) -> dict[str, Any]:
        try:
            c = aggregate_counts(executor)
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
                error_vector[AXIS_DOWNLOAD_GAP] = round(
                    c["failed"] / c["requested"], 4
                )
            out: dict[str, Any] = {"signals": signals}
            if error_vector:
                out["error_vector"] = error_vector
            return out
        except Exception as exc:  # noqa: BLE001 — 领域信号纯增益，绝不拖垮态势装配
            logger.debug("download completeness contributor 跳过：%s", exc)
            return {}


def _magnitude(observed: float, threshold: float) -> float:
    """自报强度：超阈多少倍 → 合法强度。缺 SDK 时退回 1.0（demo 可离线跑）。

    **不要自己写这个换算**——真实插件直接 import
    ``krow_agent_sdk.metacognition.wake_magnitude_from_ratio``。这里包一层只是
    为了让 cookbook 在没装 runtime 时也能被 import 和单测。
    """
    try:
        from krow_agent_sdk.metacognition import wake_magnitude_from_ratio
    except Exception:  # noqa: BLE001 — 无 SDK 环境
        return 1.0
    return wake_magnitude_from_ratio(observed, threshold)


def wake_zero_download_with_hits(
    prev: Any, curr: Any, delta: Any, ledger: Any
) -> tuple[str, float] | None:
    """唤醒层：检索有果却零下载 / 下载失败率越阈 → 唤醒决策脑。

    返回 ``(事由, 强度)`` 二元组——**自报强度**。只返字符串也合法，但强度会被
    当成 1.0，而核心触发器都在自报；同拍竞争时恒 1.0 的域触发器系统性垫底。
    这里两种形态的强度算法不同，正是"强度是领域语义"的例子：
    - 形态 A（零下载）：完整度归零，直接报满强度；
    - 形态 B（失败率越阈）：按超阈倍数线性给，60% 失败比 51% 失败更该被听见。

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
                f"放宽约束/换源继续，或诚实转交付元数据清单",
                _magnitude(1.0, DOWNLOAD_GAP_THRESHOLD),
            )
        # 形态 B：下载失败率越阈。
        if (
            requested > 0
            and isinstance(failed, int)
            and failed / requested >= DOWNLOAD_GAP_THRESHOLD
        ):
            ratio = failed / requested
            return (
                f"download_gap:{failed}/{requested} 下载失败（多为付费墙）"
                f"——转交付元数据清单",
                _magnitude(ratio, DOWNLOAD_GAP_THRESHOLD),
            )
    except Exception as exc:  # noqa: BLE001 — 领域触发器纯增益
        logger.debug("zero download trigger 跳过：%s", exc)
    return None


# ── 唤醒声明面（属性写在函数上，注册期被读取并校验）─────────────────────────
#: 争的是**完整度**：该拿到的文献没拿到，是"交付不全"而不是"算错了"。
#: 写字面量是为了让 demo 不装 SDK 也能 import；真实插件请从
#: ``krow_agent_sdk.metacognition.VALUE_AXIS_COMPLETENESS`` 取，typo 会在注册
#: 期 fail-loud，而手打的字符串错了只会静默落最低档。
wake_zero_download_with_hits.value_axis = "completeness"
#: 处置对象 = 本 demo 自己的领域轴（:func:`register` 里 register_domain_axis 登记）。
wake_zero_download_with_hits.error_axis = AXIS_DOWNLOAD_GAP
#: 指名处置者。没有这一条，满秩校验会拒：一条轴报了误差却没有任何决策认领它
#: ＝"感知通胀、调节停滞"（传感器齐全但执行器不读，开环）。
wake_zero_download_with_hits.handled_by = HANDLED_BY


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
            register_domain_axis,
            register_situation_contributor,
            register_wake_trigger,
        )
    except Exception:  # noqa: BLE001 — 无 SDK/runtime 环境
        if strict:
            raise
        return {}
    # 领域轴要先登记极性，再被 error_axis 指名。极性默认 worse_higher
    #（数值越大越差）——本轴是"失败占比"，正合默认；反向轴（越大越好）必须
    # 显式声明，否则预期结算会把好事记成违背。
    register_domain_axis(AXIS_DOWNLOAD_GAP)
    return {
        "contributor": register_situation_contributor(DownloadCompletenessContributor),
        "wake_trigger": register_wake_trigger(wake_zero_download_with_hits),
    }


def report_download_gap(failed: int, requested: int) -> bool:
    """零注册的另一条路：直接发**信号包络**（对照演示 · 不必写 contributor）。

    什么时候用哪条：
    - 本模块的 contributor —— **每拍都要被询问**的聚合型传感器，走注册表；
    - 本函数 —— 事件式、一次性、突发的信号（某次批量下载刚失败），发完就走，
      决策脑下一 macro 拍自动收进态势，**不需要**类、不需要 FQCN、不需要
      ``applicable``。

    Returns:
        是否投递成功（fail-soft：无 runtime / 总线不可用返 False，绝不抛）。
    """
    if requested <= 0:
        return False
    try:
        from krow_agent_sdk.metacognition import publish_signal_envelope
    except Exception:  # noqa: BLE001 — 无 SDK/runtime 环境
        return False
    return publish_signal_envelope(
        f"litsci.{AXIS_DOWNLOAD_GAP}",
        min(1.0, failed / requested),
        kind="pdf_missing",
        source="litsci-metacog-cookbook",
    )


__all__ = [
    "DownloadCompletenessContributor",
    "aggregate_counts",
    "wake_zero_download_with_hits",
    "register",
    "report_download_gap",
    "AXIS_DOWNLOAD_GAP",
    "HANDLED_BY",
    "DOWNLOAD_GAP_THRESHOLD",
    "MIN_PAPERS_FOR_GAP",
]
