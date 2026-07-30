"""Krow SDK Cookbook · 决策脑**执行面** demo（文献检索：下不动就转元数据交付）。

与同目录 ``litsci_metacog_demo.py`` 配对：那边是**观测面**（让决策脑看见"文献
下载缺口"），这边是**执行面**（让它对这个缺口做**针对性**的事）。

为什么两边都要有
----------------
只有观测面时，你能做的极限是把信号发出去，然后期待通用决策（``replan`` /
``converge``）恰好对症。真实体感是：传感器天天报"零下载"，而系统只会让 LLM 再
replan 一次同样的检索——**换个说法撞同一堵墙**。执行面让你说清"这时候该改做什
么"：付费墙下不动就别再下了，把已拿到的题录导出成元数据清单诚实交付。

本 demo 演示一个 **StepActuator**（步骤边界执行器）：

- 判据零 LLM、确定性、可 unit test（``requested`` 在涨而 ``downloaded`` 不涨）；
- 自判适用性（非文献任务直接闭嘴，不靠注册顺序抢）；
- 有界（``MAX_FIRES``），触顶让位 ``converge``；
- 记账（``register_reflex_decision`` 登记契约，否则开火不进 ``actuations_total``）。

需要 runtime
------------
执行面注册表在 runtime 里（``krow-agent-sdk[runtime]``）。缺 runtime 时本模块仍
可 import，但 :func:`register_actuation` 与执行器本身会 fail-soft 跳过——观测面
的 demo 不受影响。
"""
from __future__ import annotations

import logging
from typing import Any

from litsci_metacog_demo import (
    AXIS_DOWNLOAD_GAP,
    MIN_PAPERS_FOR_GAP,
    aggregate_counts,
)

logger = logging.getLogger(__name__)

#: 决策名（进 ``actuations`` 计数）。带域前缀防与核心 / 其他插件撞名。
DECISION_METADATA_FALLBACK = "litsci_metadata_fallback"

#: 换到的那一步用什么工具。真实插件写你自己注册的工具名。
FALLBACK_TOOL = "litsci_export_metadata"

#: 连续几拍"有新尝试但零新下载"判定这条路子饱和。2 是权衡：1 会把一次偶发失败
#: 当死路（付费墙外还有开放获取源值得再试一轮），3 以上则是白烧两轮预算。
SATURATION_BEATS = 2


class MetadataFallbackActuator:
    """下载路子饱和 → 追加"导出元数据清单"补做步。

    契约：``__call__(executor, plan) -> ActuatorAction | None``。返回 ``None`` =
    本次不适用。每个任务一个新实例（计数器是 per-task 状态，绝不跨任务共享）。
    """

    MAX_FIRES = 1

    def __init__(self) -> None:
        self._fired = 0
        self._last_attempts = -1
        self._counter = _saturation_counter(SATURATION_BEATS, label="litsci_download")

    def __call__(self, exe: Any, plan: Any) -> Any:
        if self._fired >= self.MAX_FIRES or self._counter is None:
            return None
        try:
            counts = aggregate_counts(exe)
        except Exception as exc:  # noqa: BLE001 — 执行器出错绝不拖垮主流程
            logger.debug("metadata fallback actuator 跳过：%s", exc)
            return None

        # ① 自判适用性：没检索过 / 没下载过 = 不是本族任务。
        if counts["papers_found"] < MIN_PAPERS_FOR_GAP or counts["requested"] <= 0:
            return None
        # ② 有产出 = 这条路子还在走，别插手。
        if counts["downloaded"] > 0:
            return None

        # ③ 饱和判定：**只在"有新尝试"时观测**。不动 ≠ 饱和——agent 可能正在别处
        #    干正事（读已下到的 PDF、写综述），此时计数不涨不该被读成"这条路死了"。
        attempts = counts["requested"]
        if attempts <= self._last_attempts:
            return None
        self._last_attempts = attempts
        if not self._counter.observe_signature(counts["downloaded"]).saturated:
            return None

        return self._fire(exe, plan, counts)

    def _fire(self, exe: Any, plan: Any, counts: dict[str, int]) -> Any:
        from krow_agent_sdk.actuation import append_plan_step, make_actuator_action

        papers = counts["papers_found"]
        step = append_plan_step(
            exe,
            plan,
            tool=FALLBACK_TOOL,
            purpose=(
                f"System-1 补做（确定性判定，不可跳过）：{counts['requested']} 次下载"
                f"尝试零成功，全文这条路已证明走不通（多为付费墙）。**不要再重试下载**"
                f"——改为把检索到的 {papers} 篇题录导出成元数据清单（标题 / 作者 / "
                "年份 / DOI / 摘要 / 获取途径），在交付里如实标注「全文未获取」。"
            ),
        )
        if step is None:
            return None  # plan 不可变 —— 放弃本次注入（fail-soft）
        self._fired += 1
        return make_actuator_action(
            new_step=step,
            decision=DECISION_METADATA_FALLBACK,
            observation=(
                f"下载路径饱和（{counts['requested']} 次尝试 0 成功），"
                f"已改走元数据交付。"
            ),
            telemetry={
                "requested": counts["requested"],
                "papers_found": papers,
                "beats": SATURATION_BEATS,
            },
        )


def _saturation_counter(threshold: int, *, label: str) -> Any:
    """取内建饱和计数器；无 runtime 返 ``None``（执行器随之整体静默）。

    别自己写第十份"连续 N 次没变化"——它的坑（首次观测不计入、签名相等判定、
    重置时机）都已经在内建实现里踩过了。
    """
    try:
        from krow_agent_sdk.actuation import saturation_counter

        return saturation_counter(threshold, label=label)
    except Exception:  # noqa: BLE001 — 无 SDK/runtime 环境（import 得动、调不动）
        return None


def register_actuation(strict: bool = True) -> dict[str, str]:
    """登记执行面：反射决策契约 + 步骤边界执行器（幂等 · fail-soft）。

    **两步都要**，顺序无所谓但缺一不可：

    - 只注册执行器：它照常开火，但 ``actuations_total`` 不计——报表会说"决策脑
      从没动手"，而基于这种读数最容易做的决定恰恰是退化功能（本仓真实事故）。
    - 只登记契约：没有执行器认领，满秩矩阵报"声明了没生效"。

    Args:
        strict: True 时缺 SDK/runtime 直接抛；False 时静默跳过（真实插件用这个，
            独立分发无决策脑时不拖垮 boot）。

    Returns:
        ``{"decision": 决策名, "actuator": FQCN}``；跳过时返 ``{}``。
    """
    # 注意 try 覆盖到**调用**而不只是 import：facade 顶层刻意不碰 ``modules``，
    # 所以 SDK-only 安装下 import 是成功的，缺 runtime 要到真调用时才 fail-loud。
    # 只包 import 的写法会让"无 runtime 时静默跳过"这条承诺在半路失效。
    try:
        from krow_agent_sdk.actuation import (
            AUTHORITY_PLAN,
            register_reflex_decision,
            register_step_actuator,
        )
        from krow_agent_sdk.metacognition import register_domain_axis

        # 轴要先登记极性再被决策认领。这里复用观测面用的同一条轴——传感器报的
        # 缺口与执行器认领的缺口必须是**同一条轴**，否则满秩矩阵上是两个互不
        # 相干的格子。
        register_domain_axis(AXIS_DOWNLOAD_GAP)
        fqcn = f"{__name__}:MetadataFallbackActuator"
        decision = register_reflex_decision(
            DECISION_METADATA_FALLBACK,
            authority=AUTHORITY_PLAN,  # A3 = 动计划（追加一步）
            actuator=fqcn,
            axis=AXIS_DOWNLOAD_GAP,
            max_fires=MetadataFallbackActuator.MAX_FIRES,
            note="下载连续零成功 → 转元数据清单交付（不再重试全文）",
        )
        return {"decision": decision, "actuator": register_step_actuator(fqcn)}
    except Exception:  # noqa: BLE001 — 无 SDK/runtime 环境
        if strict:
            raise
        logger.info("执行面注册跳过（无 krow-agent-sdk[runtime]）")
        return {}


__all__ = [
    "DECISION_METADATA_FALLBACK",
    "FALLBACK_TOOL",
    "SATURATION_BEATS",
    "MetadataFallbackActuator",
    "register_actuation",
]
