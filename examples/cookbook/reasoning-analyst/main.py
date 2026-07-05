"""reasoning-analyst cookbook 主入口（纯 SDK、无 UI 启动推理洞察管线）。

把一份资料 + 一个分析问题，交给 Krow 引擎的 **reasoning 洞察管线**（链式证据 /
竞争假设排除 / 横向对比 / 时间线追踪等策略），输出带证据落点的结论，并自助落盘
成 markdown + json。

跑前：
    1. set KROW_API_KEY=sk-user-xxx
       (PowerShell: $env:KROW_API_KEY='sk-user-xxx')
       (Linux/Mac:  export KROW_API_KEY=sk-user-xxx)
    2. krow-sdk-install --api-key $KROW_API_KEY
    3. cd examples/cookbook/reasoning-analyst && pip install -e .

最小跑（自带病例资料 · 默认 evidence_chain 链式证据核验）：
    python main.py

指定策略 + 自定义问题：
    python main.py hypothesis_test --question "呼吸困难更可能心源性还是肺源性？"

一次跑两个 journey（evidence_chain + hypothesis_test）：
    python main.py --all

输出：
    <output-dir>/reasoning_<strategy>.md     结论报告（含证据落点 + 过程指标）
    <output-dir>/reasoning_<strategy>.json   结构化结论（success/concluded/metrics）
    <output-dir>/summary.json                多 journey 汇总

────────────────────────────────────────────────────────────────────
为什么纯 SDK 也能跑 reasoning 管线（无 UI）
────────────────────────────────────────────────────────────────────
桌面推理工作台提交问题时，用 ``task_context = {"source": "reasoning_panel",
"strategy": ...}`` 激活推理专属行为（工具优先级注入 / 推理前导 / 本体预载）。本
cookbook 在纯 SDK 里复刻这套 task_context，并**显式 pin** ``act_name=
reasoning_pipeline``（该 ACT 无 disclosure_triggers，单靠 strategy 不保证 macro
planner 选中它）。详见 ``reasoning_journeys.build_reasoning_task_context``。

关键经验：``AgentV3Result.success`` vs ``final_output``
    复杂 journey（如 evidence_chain）在纯 SDK 下可能 ``success=False`` 却已 commit
    完整结论（桌面 / 后台任务队列有 partial 接受层兜底，纯 SDK 没有）。所以本
    cookbook 的"推理完成"判据是 ``final_output 非空 且（success 或 conclusion
    committed 事件）``，而非裸 ``success``。详 ``extract_reasoning_outcome``。
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import sys
from pathlib import Path

from real_world_journeys import (
    PRESETS,
    get_preset,
    resolve_journey_sources,
)
from reasoning_journeys import (
    REASONING_EXTRA_STRATEGIES,
    SUPPORTED_STRATEGIES,
    persist_reasoning_outcome,
    run_reasoning,
)

try:  # BudgetSpec 是可选增强
    from krow_agent_sdk import BudgetSpec
except Exception:  # noqa: BLE001
    BudgetSpec = None  # type: ignore[assignment]

def _ensure_utf8_stdio() -> None:
    """把 stdout/stderr 切到 UTF-8，避免 Windows GBK 控制台打印 emoji/中文崩溃。

    背景：Windows 默认控制台
    编码是 GBK（cp936），``print("🔬 ...")`` 直接抛 ``UnicodeEncodeError: 'gbk' codec
    can't encode character '\\U0001f52c'`` —— cookbook 还没进推理就秒崩，真实 Windows
    用户 ``python main.py`` 必撞。System-1 修法：进程启动即把标准流 reconfigure 成
    UTF-8（Python 3.7+ ``TextIOWrapper.reconfigure``），与设 ``PYTHONIOENCODING=utf-8``
    等效但无需用户额外配置。已是 UTF-8 / 不支持 reconfigure 时静默跳过（零副作用）。
    """
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower()
        if "utf-8" in enc or "utf8" in enc:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            # 兜底：极端环境 reconfigure 失败也不阻塞主流程（降级到原编码）。
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8", errors="backslashreplace")


def _warn_if_reasoning_extra_missing(strategies: list[str]) -> None:
    """选了因果/概率策略但缺 ``[reasoning]`` 重型库时给 fail-soft 提示（不阻塞）。

    引擎在缺 dowhy/causal-learn/pgmpy 时会 fail-loud 指引降级到定性路径，cookbook 这里
    只是提前给用户一句可执行的安装建议，避免"为什么因果图没有定量估计"的困惑。
    """
    import importlib.util

    if not any(s in REASONING_EXTRA_STRATEGIES for s in strategies):
        return
    missing = [
        name
        for name, mod in (
            ("dowhy", "dowhy"),
            ("causal-learn", "causallearn"),
            ("pgmpy", "pgmpy"),
        )
        if importlib.util.find_spec(mod) is None
    ]
    if missing:
        print(
            "⚠️  选中的因果/概率策略需要定量统计库，但缺少："
            f"{', '.join(missing)}\n"
            "   定性路径仍可跑（LLM 提因果边 + 定性反驳）；要启用**定量**因果发现/"
            "估计/贝叶斯网推断，请装：\n"
            "     pip install \"krow-agent-sdk[reasoning]\"",
            file=sys.stderr,
        )


_HERE = Path(__file__).resolve().parent
_DEFAULT_SAMPLE = _HERE / "sample_data"

_DEFAULT_QUESTIONS: dict[str, str] = {
    "evidence_chain": (
        "核实论断：本病例支持「下壁急性心肌梗死（STEMI）」诊断。"
        "请基于资料逐级核验证据链，给出每一步证据如何抬升或削弱该论断的后验。"
    ),
    "hypothesis_test": (
        "这名发热 + 咳嗽 + 呼吸困难的患者，呼吸困难更可能是心源性还是肺源性？"
        "请用竞争假设排除法（ACH）逐条权衡证据并给出倾向性结论。"
    ),
    "comparative_analysis": (
        "对比「心源性呼吸困难」与「肺源性呼吸困难」在本资料中的鉴别要点。"
    ),
    "temporal_trace": (
        "按时间顺序追踪本病例从胸痛起病到确诊的关键证据演进。"
    ),
    "causal_discovery": (
        "从本病例资料中挖掘「下壁急性心肌梗死」的因果结构："
        "哪些因素是致病/恶化的因果致因，哪些只是伴随相关？"
        "请走科研闭环（抽取→规律发现→提假设→竞争排除→因果验证→结论），"
        "对每条因果边给出反驳后的可信度。"
    ),
    "bayes_inference": (
        "基于本病例的发热 + 咳嗽 + 呼吸困难证据，用贝叶斯网量化"
        "「心源性呼吸困难」与「肺源性呼吸困难」各自的后验概率，"
        "并说明每条新证据如何更新信念。"
    ),
}


def _run_one(
    *,
    api_key: str,
    strategy: str,
    question: str,
    project_dir: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> dict:
    """跑单个 reasoning journey 并落盘，返回汇总条目。"""
    from krow_agent_sdk import AgentBuilder

    budget = None
    if BudgetSpec is not None and any(
        [args.budget_llm_calls, args.budget_walltime, args.budget_replans]
    ):
        budget_kwargs: dict = {}
        if args.budget_llm_calls is not None:
            budget_kwargs["max_total_llm_calls"] = args.budget_llm_calls
        if args.budget_walltime is not None:
            budget_kwargs["max_walltime_s"] = args.budget_walltime
            budget_kwargs.setdefault(
                "target_walltime_s", max(60, args.budget_walltime - 60)
            )
        if args.budget_replans is not None:
            budget_kwargs["max_replans"] = args.budget_replans
        budget = BudgetSpec(**budget_kwargs)

    # builder 在 main.py 一层闭环：让 --base-url / KROW_BASE_URL 与 install-cli 端
    # 协议同源（W4 staging / 私有部署联调必需）。
    builder = (
        AgentBuilder()
        .with_krow_api_key(api_key)
        .with_project_root(str(project_dir))
    )
    if args.base_url:
        builder = builder.with_base_url(args.base_url)
    if args.chat_model:
        builder = builder.with_chat_model(args.chat_model)
    if args.reasoning_model:
        builder = builder.with_reasoning_model(args.reasoning_model)
    if budget is not None:
        builder = builder.with_budget(budget)

    print(f"\n🧠 推理 journey：strategy={strategy}")
    print(f"   问题：{question}")

    outcome = run_reasoning(
        builder=builder,
        strategy=strategy,
        question=question,
        project_root=project_dir,
    )

    paths = persist_reasoning_outcome(
        outcome,
        output_dir=output_dir,
        strategy=strategy,
        question=question,
        reasoning_id=outcome["reasoning_id"],
    )

    metrics = outcome.get("metrics") or {}
    print(f"   ✅ 推理完成判定：{outcome['reasoning_completed']} "
          f"(success={outcome['success_flag']} / concluded={outcome['concluded']})")
    print(f"   📊 工具调用 {metrics.get('tool_calls_total')} 次 · "
          f"推理工具 {metrics.get('reasoning_tool_calls')}")
    print(f"   🧩 cognitive.load 事件 {metrics.get('cognitive_load_events')} 次")
    print(f"   📝 结论：{paths['markdown']}（{outcome['final_output_chars']} 字）")

    return {
        "strategy": strategy,
        "reasoning_id": outcome["reasoning_id"],
        "reasoning_completed": outcome["reasoning_completed"],
        "success_flag": outcome["success_flag"],
        "concluded": outcome["concluded"],
        "final_output_chars": outcome["final_output_chars"],
        "metrics": metrics,
        "markdown": str(paths["markdown"]),
        "json": str(paths["json"]),
    }


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()  # Windows GBK 控制台 emoji/中文打印守护（须在任何 print 前）
    parser = argparse.ArgumentParser(
        description="Krow SDK Cookbook · Reasoning Analyst（纯 SDK 推理洞察管线）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "跑法：\n"
            "  最小跑（默认 evidence_chain）：python main.py\n"
            "  指定策略：python main.py hypothesis_test\n"
            "  两个 journey：python main.py --all\n"
        ),
    )
    parser.add_argument(
        "strategy",
        nargs="?",
        default="evidence_chain",
        choices=list(SUPPORTED_STRATEGIES),
        help="推理策略（默认 evidence_chain）",
    )
    parser.add_argument("--question", default=None, help="自定义分析问题")
    parser.add_argument(
        "--preset",
        default=None,
        choices=list(PRESETS),
        help=(
            "真实世界 journey 预设（PR-B）：target_discovery（肺癌找靶点）/ "
            "whodunit_x（X 悲剧真凶）/ whodunit_z（Z 悲剧真凶）。缺真数据时"
            "自动用随仓合成微样例跑通（设对应 env 指向真数据即复现完整效果）。"
        ),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="一次跑 evidence_chain + hypothesis_test 两个 journey",
    )
    parser.add_argument(
        "--sources", nargs="*", default=None, help="自定义资料（缺省用 sample_data）"
    )
    parser.add_argument("--project-dir", default="reasoning_project")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--budget-llm-calls", type=int, default=None)
    parser.add_argument("--budget-walltime", type=int, default=None)
    parser.add_argument("--budget-replans", type=int, default=None)
    parser.add_argument("--reasoning-model", default=None)
    parser.add_argument("--chat-model", default=None)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("KROW_BASE_URL", "").strip() or None,
        help="自定义 cloud endpoint（仅 staging / 私有部署用）。默认 https://api.krow.cn。",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    api_key = os.environ.get("KROW_API_KEY", "").strip()
    if not api_key:
        print(
            "❌ 未设 KROW_API_KEY 环境变量。\n"
            "   修法：\n"
            "     1. Windows: $env:KROW_API_KEY='sk-user-xxx'\n"
            "     2. Linux/Mac: export KROW_API_KEY=sk-user-xxx",
            file=sys.stderr,
        )
        return 1

    # ── PR-B 真实世界预设：--preset 覆盖 strategy / question / sources ──
    preset_obj = None
    preset_question = None
    if args.preset:
        preset_obj = get_preset(args.preset)
        override = args.sources[0] if args.sources else None
        try:
            src_path, is_real = resolve_journey_sources(preset_obj, override=override)
        except FileNotFoundError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        args.strategy = preset_obj.strategy
        args.sources = [str(src_path)]
        preset_question = preset_obj.question
        print(
            f"🎯 预设 journey：{preset_obj.name}（策略 {preset_obj.strategy}）\n"
            f"   资料：{src_path} "
            f"（{'真实数据' if is_real else '随仓合成微样例 · smoke'}）"
        )
        if not is_real:
            print(
                f"   ℹ️  用真实数据复现完整效果：设 {preset_obj.data_env} 指向"
                f" {preset_obj.data_hint}",
                file=sys.stderr,
            )

    # ── 项目目录 + 资料准备（把 sample_data 拷进 project_dir 供推理工具读取）──
    project_dir = Path(args.project_dir).expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    raw_sources = args.sources or [str(_DEFAULT_SAMPLE)]
    for raw in raw_sources:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print(f"❌ 资料不存在：{p}", file=sys.stderr)
            return 1
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and ".krow" not in f.parts:
                    dst = project_dir / f.name
                    if not dst.exists():
                        shutil.copy2(f, dst)
        else:
            dst = project_dir / p.name
            if not dst.exists():
                shutil.copy2(p, dst)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    strategies = ["evidence_chain", "hypothesis_test"] if args.all else [args.strategy]
    _warn_if_reasoning_extra_missing(strategies)

    print("🔬 推理分析任务")
    print(f"   project:  {project_dir}")
    print(f"   output:   {output_dir}")
    print(f"   策略:     {', '.join(strategies)}")

    results = []
    for strategy in strategies:
        question = args.question or preset_question or _DEFAULT_QUESTIONS.get(
            strategy, f"请用 {strategy} 策略分析资料。"
        )
        results.append(
            _run_one(
                api_key=api_key,
                strategy=strategy,
                question=question,
                project_dir=project_dir,
                output_dir=output_dir,
                args=args,
            )
        )

    summary = {
        "n_journeys": len(results),
        "n_completed": sum(1 for r in results if r["reasoning_completed"]),
        "journeys": results,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n📦 汇总：{output_dir / 'summary.json'}"
          f"（{summary['n_completed']}/{summary['n_journeys']} 完成）")

    # 退出码：所有 journey 都"推理完成"才算成功（不裸看 success 标志）
    all_completed = summary["n_completed"] == summary["n_journeys"]
    if not all_completed:
        print(
            "\n❌ 存在未完成的推理 journey（final_output 空 / 未 commit 结论）。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
