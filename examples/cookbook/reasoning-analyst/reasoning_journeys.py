"""reasoning-analyst cookbook 的 System-1 库（可单测、零 LLM）。

把"纯 SDK、无 UI 启动 reasoning 洞察管线"沉淀成几个确定性函数：

- ``build_reasoning_task_context`` —— 复刻桌面推理工作台的提交语义（``source=
  reasoning_panel`` + 显式 pin ``act_name=reasoning_pipeline`` + ``strategy``）。
- ``ReasoningEventCollector`` —— 订阅 EventBus 采集工具调用 / cognitive.load /
  结论事件（观测快环元认知 + 推理工具链是否真跑）。
- ``extract_reasoning_outcome`` —— 把 ``AgentV3Result`` + 采集到的事件归一成结论
  判定。**关键经验**：纯 SDK 下复杂 journey（如 evidence_chain）可能 ``success=
  False`` 却产出了完整结论；别只看 ``success`` 标志，要结合 ``final_output`` 非空
  + ``reasoning.conclusion.committed`` 事件。
- ``persist_reasoning_outcome`` —— 把结论落盘成 markdown + json。纯 SDK 不自动写
  ``.krow/reasoning/{id}.json``（那条 ``ReasoningResultRouter`` 链路只在桌面 / BTQ
  集成时挂载），所以这里自助落盘补齐缺口。

真正调用引擎的 ``run_reasoning`` 才 lazy import ``krow_agent_sdk``，让 smoke 单测
不依赖完整 runtime。
"""
from __future__ import annotations

import contextlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 本 cookbook 演示的策略子集（推理策略 SSOT 在引擎
# ``modules.knowledge.reasoning_strategies.STRATEGIES``）。
# 这里只列「不依赖 CSV 定量统计依赖（DoWhy/causal-learn）即可跑」的常用策略，
# 让外部开发者装 ``krow-agent-sdk[ontology]`` 默认就能跑通。
SUPPORTED_STRATEGIES: tuple[str, ...] = (
    "evidence_chain",        # 链式证据逐级抬升后验（单论断核实）
    "hypothesis_test",       # ACH 竞争假设排除分析
    "comparative_analysis",  # 多对象横向对比
    "temporal_trace",        # 时间线追踪
)

# reasoning 管线由 task_context.source == "reasoning_panel" 驱动；reasoning_pipeline
# ACT 无 disclosure_triggers，单靠 strategy 不保证 macro planner 选中它，故显式 pin。
REASONING_ACT_NAME = "reasoning_pipeline"
REASONING_SOURCE = "reasoning_panel"


class UnknownStrategyError(ValueError):
    """策略不在本 cookbook 支持集合时 fail-loud（黄金错误模板）。"""


def build_reasoning_task_context(
    *,
    strategy: str,
    question: str,
    reasoning_id: str | None = None,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    """构造启动 reasoning 管线的 ``task_context``（纯 System-1，零 LLM）。

    Args:
        strategy: 推理策略 id（必须在 ``SUPPORTED_STRATEGIES`` 内）。
        question: 分析问题（自然语言）。
        reasoning_id: 落盘 / 追踪用 id；缺省自动生成。
        project_root: 可选，供 wiki/graph/seed 数据定位。

    Returns:
        透传给 ``agent.run(task_context=...)`` 的 dict。

    Raises:
        UnknownStrategyError: strategy 不被支持。
        ValueError: question 为空。
    """
    strategy = (strategy or "").strip()
    if strategy not in SUPPORTED_STRATEGIES:
        raise UnknownStrategyError(
            f"不支持的推理策略 {strategy!r}。\n"
            f"  原因：本 cookbook 仅演示无需 CSV 定量依赖的策略。\n"
            f"  可选：{', '.join(SUPPORTED_STRATEGIES)}\n"
            f"  全量策略见引擎 modules.knowledge.reasoning_strategies.STRATEGIES。"
        )
    if not (question or "").strip():
        raise ValueError("question 不能为空。")

    rid = reasoning_id or f"reasoning-{strategy}-{uuid.uuid4().hex[:8]}"
    ctx: dict[str, Any] = {
        "source": REASONING_SOURCE,
        "act_name": REASONING_ACT_NAME,
        "strategy": strategy,
        "question": question.strip(),
        "reasoning_id": rid,
    }
    if project_root is not None:
        ctx["project_root"] = str(project_root)
    return ctx


# ════════════════════════════════════════════════════════════════════════
# 事件采集（观测快环元认知 + 推理工具链）
# ════════════════════════════════════════════════════════════════════════

# 归类为"推理工具"的子串（用于统计推理管线是否真跑）。
_REASONING_TOOL_HINTS: tuple[str, ...] = (
    "hypothes", "evidence", "ontology", "link", "causal", "challenge",
    "summarize", "recompute", "decompose", "evaluate", "score", "conclude",
    "counterfactual",
)


def _event_type(ev: Any) -> str:
    """兼容引擎 ``Event.type``（SSOT）+ 历史 ``event_type`` 字段。"""
    return str(getattr(ev, "type", "") or getattr(ev, "event_type", "") or "")


def _event_payload(ev: Any) -> dict[str, Any]:
    p = getattr(ev, "payload", None)
    return p if isinstance(p, dict) else {}


def classify_tool_name(payload: dict[str, Any]) -> str:
    """从工具事件 payload 里提取工具名（多字段兼容）。"""
    return str(
        payload.get("tool_name")
        or payload.get("tool")
        or payload.get("name")
        or (payload.get("context") or {}).get("tool_name")
        or "?"
    )


@dataclass
class ReasoningEventCollector:
    """订阅 EventBus 采集推理过程指标（零 LLM · System 1）。

    用法::

        collector = ReasoningEventCollector()
        collector.attach()
        try:
            result = agent.run(...)
        finally:
            collector.detach()
        summary = collector.summary()
    """

    event_counts: dict[str, int] = field(default_factory=dict)
    tool_calls: dict[str, int] = field(default_factory=dict)
    cognitive_load_events: list[dict[str, Any]] = field(default_factory=list)
    conclusion_committed: int = 0
    task_complete: int = 0
    _token: str | None = None

    def handle(self, ev: Any) -> None:
        """处理单条事件（可直接喂 fake 事件做单测）。"""
        et = _event_type(ev)
        if not et:
            return
        payload = _event_payload(ev)
        self.event_counts[et] = self.event_counts.get(et, 0) + 1
        low = et.lower()
        if "tool" in low and any(k in low for k in ("call", "exec", "invoke", "finish")):
            name = classify_tool_name(payload)
            self.tool_calls[name] = self.tool_calls.get(name, 0) + 1
        if et == "cognitive.load":
            self.cognitive_load_events.append(
                {
                    "state": payload.get("state"),
                    "load_axis": payload.get("load_axis"),
                    "budget_divergence": payload.get("budget_divergence"),
                }
            )
        elif et == "reasoning.conclusion.committed":
            self.conclusion_committed += 1
        elif et == "agent.task_complete":
            self.task_complete += 1

    def attach(self) -> None:
        """订阅全局 EventBus 的所有事件（``*`` 通配）。"""
        from modules.events.bus import EventBus

        self._token = EventBus.get_instance().subscribe("*", self.handle)

    def detach(self) -> None:
        if self._token is None:
            return
        try:
            from modules.events.bus import EventBus

            EventBus.get_instance().unsubscribe(self._token)
        except Exception:  # noqa: BLE001
            pass
        self._token = None

    def reasoning_tool_calls(self) -> dict[str, int]:
        return {
            k: v
            for k, v in self.tool_calls.items()
            if any(h in k for h in _REASONING_TOOL_HINTS)
        }

    def summary(self) -> dict[str, Any]:
        return {
            "event_types": len(self.event_counts),
            "tool_calls_total": sum(self.tool_calls.values()),
            "reasoning_tool_calls": self.reasoning_tool_calls(),
            "cognitive_load_events": len(self.cognitive_load_events),
            "conclusion_committed": self.conclusion_committed,
            "task_complete": self.task_complete,
        }


# ════════════════════════════════════════════════════════════════════════
# 结论判定（关键经验：别只看 success 标志）
# ════════════════════════════════════════════════════════════════════════


def extract_reasoning_outcome(
    result: Any,
    collector: ReasoningEventCollector | None = None,
) -> dict[str, Any]:
    """把引擎结果归一成结论判定。

    判据（System 1 · 零 LLM）：
        ``reasoning_completed`` = 产出非空 ``final_output`` **且**（``success=True``
        或采集到 ``reasoning.conclusion.committed`` 事件）。

    这条经验来自纯 SDK 实测：evidence_chain 这种最复杂的 journey 可能 ``success=
    False`` 却已 commit 完整结论（桌面 / BTQ 路径有 partial 接受层兜底，纯 SDK 没
    有）。只看 ``success`` 会误判"推理失败"。
    """
    success_flag = bool(getattr(result, "success", False))
    final_output = str(getattr(result, "final_output", "") or "")
    concluded = success_flag or (
        collector is not None and collector.conclusion_committed > 0
    )
    reasoning_completed = bool(final_output.strip()) and concluded

    outcome: dict[str, Any] = {
        "success_flag": success_flag,
        "concluded": concluded,
        "reasoning_completed": reasoning_completed,
        "final_output": final_output,
        "final_output_chars": len(final_output),
    }
    if collector is not None:
        outcome["metrics"] = collector.summary()
    return outcome


def persist_reasoning_outcome(
    outcome: dict[str, Any],
    *,
    output_dir: str | Path,
    strategy: str,
    question: str,
    reasoning_id: str,
) -> dict[str, Path]:
    """把结论落盘成 markdown + json（补齐纯 SDK 不自动落盘的缺口）。

    Returns:
        ``{"markdown": Path, "json": Path}``。
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"reasoning_{strategy}.md"
    json_path = out / f"reasoning_{strategy}.json"

    metrics = outcome.get("metrics") or {}
    header = [
        f"# 推理结论 · {strategy}",
        "",
        f"- reasoning_id: `{reasoning_id}`",
        f"- 策略: `{strategy}`",
        f"- 问题: {question}",
        f"- success 标志: {outcome.get('success_flag')}",
        f"- 已 commit 结论: {outcome.get('concluded')}",
        f"- 推理完成判定: {outcome.get('reasoning_completed')}",
        f"- 结论字数: {outcome.get('final_output_chars')}",
    ]
    if metrics:
        header += [
            f"- 工具调用总数: {metrics.get('tool_calls_total')}",
            f"- 推理工具调用: {metrics.get('reasoning_tool_calls')}",
            f"- cognitive.load 事件: {metrics.get('cognitive_load_events')}",
            f"- conclusion.committed 事件: {metrics.get('conclusion_committed')}",
        ]
    header += ["", "---", "", outcome.get("final_output") or "（无结论文本）", ""]
    md_path.write_text("\n".join(header), encoding="utf-8")

    payload = {
        "reasoning_id": reasoning_id,
        "strategy": strategy,
        "question": question,
        "generated_ts": time.time(),
        **{k: v for k, v in outcome.items() if k != "final_output"},
        "final_output": outcome.get("final_output", ""),
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"markdown": md_path, "json": json_path}


# ════════════════════════════════════════════════════════════════════════
# 真正调用引擎（lazy import，smoke 单测不触达）
# ════════════════════════════════════════════════════════════════════════


def run_reasoning(
    *,
    builder: Any,
    strategy: str,
    question: str,
    project_root: str | Path,
    reasoning_id: str | None = None,
    stop_event: Any | None = None,
) -> dict[str, Any]:
    """纯 SDK、无 UI 启动 reasoning 管线并归一结果。

    Args:
        builder: 调用方构造好的 ``AgentBuilder``（已注入 api_key / project_root /
            可选 base_url / model / budget）。把 builder 留给调用方构造，让
            ``--base-url`` 等 cloud endpoint 注入与 install-cli 端协议在 ``main.py``
            一层闭环（详 ``tests/sdk/test_cookbook_main_consistency.py``）。

    Returns:
        ``extract_reasoning_outcome`` 的 dict（附 ``reasoning_id`` / ``strategy``）。
    """
    task_context = build_reasoning_task_context(
        strategy=strategy,
        question=question,
        reasoning_id=reasoning_id,
        project_root=project_root,
    )
    rid = task_context["reasoning_id"]

    agent = builder.build()
    collector = ReasoningEventCollector()
    collector.attach()
    try:
        result = agent.run(
            question,
            task_context=task_context,
            project_id=f"reasoning-analyst-{strategy}",
            stop_event=stop_event,
        )
    finally:
        collector.detach()
        with contextlib.suppress(Exception):
            agent.shutdown()

    outcome = extract_reasoning_outcome(result, collector)
    outcome["reasoning_id"] = rid
    outcome["strategy"] = strategy
    return outcome
