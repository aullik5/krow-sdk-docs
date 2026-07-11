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

# 本 cookbook 演示的策略集（推理策略 SSOT 在引擎
# ``modules.knowledge.reasoning_strategies.STRATEGIES``）。
#
# 2026-06-29：补齐**因果发现**
# + **概率推理**，让 cookbook 覆盖推理洞察管线的全部范式（此前只演示 4 个定性策略）。
#
# 依赖分层：
#   - 定性策略（前 4 个）：装 ``krow-agent-sdk[ontology]`` 即可跑（networkx 等轻量）。
#   - causal_discovery：定性路径（LLM 提因果边 + domain_prior 定性反驳，无数据集）装
#     ``[ontology]`` 即可；**定量路径**（ingest_dataset + 统计因果发现/估计）需
#     ``krow-agent-sdk[reasoning]``（dowhy/causal-learn）。
#   - bayes_inference：贝叶斯网推断需 ``krow-agent-sdk[reasoning]``（pgmpy）。
# 缺重型库时引擎 fail-loud 指引降级到定性路径（不会静默出错）。
SUPPORTED_STRATEGIES: tuple[str, ...] = (
    "evidence_chain",        # 链式证据逐级抬升后验（单论断核实）
    "hypothesis_test",       # ACH 竞争假设排除分析
    "comparative_analysis",  # 多对象横向对比
    "temporal_trace",        # 时间线追踪
    "causal_discovery",      # 因果发现六阶段科研闭环（定性可跑 / 定量需 [reasoning]）
    "bayes_inference",       # 贝叶斯网概率推理（需 [reasoning] 的 pgmpy）
)

# 需 ``krow-agent-sdk[reasoning]`` 重型依赖才能发挥**完整定量能力**的策略（仅用于
# UX 提示；缺依赖时引擎仍会 fail-loud 降级到定性路径，不阻塞）。
REASONING_EXTRA_STRATEGIES: frozenset[str] = frozenset(
    {"causal_discovery", "bayes_inference"}
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
    depth_mode: bool = False,
) -> dict[str, Any]:
    """构造启动 reasoning 管线的 ``task_context``（纯 System-1，零 LLM）。

    Args:
        strategy: 推理策略 id（必须在 ``SUPPORTED_STRATEGIES`` 内）。
        question: 分析问题（自然语言）。
        reasoning_id: 落盘 / 追踪用 id；缺省自动生成。
        project_root: 可选，供 wiki/graph/seed 数据定位。
        depth_mode: 深度模式（PR-S2 · 2026-07-10）。显式声明"这个任务值得跑满"
            → 引擎把墙钟预算直接抬到策略契约的 max_wallclock（如 hypothesis_test
            7200s），避免长文本 ACH 任务被中途 forced conclude。与桌面推理工作台
            的深挖开关同语义；默认关（普通任务不占长预算）。

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
    if depth_mode:
        ctx["depth_mode"] = True
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
    # PR-S5（2026-07-10 画布冷启动）：会话启动即 seed 问题卡（System-1 确定性）
    intent_seeded: int = 0
    # PR-S7（2026-07-10 Z悲剧 问题4）：胜出假设机制链（conclude 后一次 bounded
    # LLM 调用产出定性因果链，payload 含 edges_created 等指标）
    mechanism_chain_events: list[dict[str, Any]] = field(default_factory=list)
    # PR-S3（2026-07-10 供给层 provider 税）：连续瞬断风暴 / 恢复事件——量化
    # "墙钟去哪了"（基础设施重试 vs 真推理）
    transient_storms: int = 0
    transient_storm_recoveries: int = 0
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
        elif et == "intent.seeded":
            self.intent_seeded += 1
        elif et == "reasoning.mechanism_chain":
            # payload 契约 = causal_tools.elicit_winner_mechanism_chain 返回值
            self.mechanism_chain_events.append(
                {
                    "attempted": payload.get("attempted"),
                    "built": payload.get("built"),
                    "winner_id": payload.get("winner_id"),
                    "reason": payload.get("reason"),
                }
            )
        elif et == "provider.transient_storm":
            self.transient_storms += 1
        elif et == "provider.transient_storm_recovered":
            self.transient_storm_recoveries += 1

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
            "intent_seeded": self.intent_seeded,
            "mechanism_chain_events": list(self.mechanism_chain_events),
            "transient_storms": self.transient_storms,
            "transient_storm_recoveries": self.transient_storm_recoveries,
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


def archive_reasoning_json(
    project_dir: str | Path,
    output_dir: str | Path,
    *,
    max_files: int = 5,
) -> list[Path]:
    """把项目 ``.krow/reasoning/**/*.json`` 归档进 journey output（P2 · 2026-07-11）。

    动机（whodunit_z 走查）：journey 产物只有结论 md/json，事后想核查
    记分卡 / 疑点闭环 / E2 checkpoint 时，桌面写的 reasoning 归档
    （``.krow/reasoning/*.json`` + ``checkpoints/*.json``）不在 artifacts 里，
    复盘只能翻用户机器。本函数把最新 ``max_files`` 份 json 平铺 copy 到
    output_dir（文件名加 ``reasoning_archive_`` 前缀，run_journey 的
    artifacts 收集器只认 output_dir 顶层文件）。

    fail-soft：目录不存在 / copy 失败 → 跳过（归档纯增益，绝不阻断 journey）。
    """
    out = Path(output_dir)
    src_root = Path(project_dir) / ".krow" / "reasoning"
    copied: list[Path] = []
    try:
        if not src_root.is_dir():
            return []
        candidates = sorted(
            (p for p in src_root.rglob("*.json") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:max_files]
        out.mkdir(parents=True, exist_ok=True)
        for p in candidates:
            dst = out / f"reasoning_archive_{p.name}"
            try:
                dst.write_bytes(p.read_bytes())
                copied.append(dst)
            except OSError:
                continue
    except Exception:  # noqa: BLE001 - 归档纯增益
        return copied
    return copied


def persist_reasoning_outcome(
    outcome: dict[str, Any],
    *,
    output_dir: str | Path,
    strategy: str,
    question: str,
    reasoning_id: str,
    project_dir: str | Path | None = None,
) -> dict[str, Path]:
    """把结论落盘成 markdown + json（补齐纯 SDK 不自动落盘的缺口）。

    ``project_dir`` 给定时额外归档项目 ``.krow/reasoning/**/*.json``
    （P2 · 见 ``archive_reasoning_json``）。

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
    if project_dir is not None:
        archive_reasoning_json(project_dir, out)
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
    depth_mode: bool = False,
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
        depth_mode=depth_mode,
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
