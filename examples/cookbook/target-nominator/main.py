"""Target-nominator cookbook 主入口（借鉴 Cell GPNMB CAR-T 靶点发现）.

跑前：
    1. set KROW_API_KEY=sk-user-xxx
       (PowerShell: $env:KROW_API_KEY='sk-user-xxx')
       (Linux/Mac:  export KROW_API_KEY=sk-user-xxx)
    2. krow-sdk-install --api-key $KROW_API_KEY
    3. cd examples/cookbook/target-nominator && pip install -e .

最小跑（GPNMB journey：黑色素瘤候选清单 → 提名报告）：
    python main.py --cancer-type melanoma \\
        --candidates GPNMB MLANA PMEL TYRP1 MCAM CSPG4

从候选文件跑（sample_data 微样例）：
    python main.py --candidates-file sample_data/melanoma_candidates.md \\
        --cancer-type melanoma

长任务档（多候选 × 多库取数 + 打分，8h 预算天花板 · 呼应 litsci depth_mode）：
    python main.py --candidates GPNMB MLANA PMEL TYRP1 MCAM CSPG4 \\
        --cancer-type melanoma --depth-mode \\
        --budget-llm-calls 200 --budget-walltime 3600

输出：
    output/target_nomination.md   （提名报告：候选表 + 四维打分 + 最佳靶点 + 溯源）
    output/target_scores.json     （打分工具的 ranking / matrix / weights / issues）
    output/summary.json           （本次运行摘要：候选数 / 产物 / 预算）

────────────────────────────────────────────────────────────────────
本 cookbook 演示 SDK plugin 组合（对齐 litsci worker §13 增补设计）：
────────────────────────────────────────────────────────────────────
- ToolPlugin × 3（HPA 取数 / Open Targets 取数 / 多维加权打分）
- ACTPlugin × 1（target_nominator ACT，提名工作流）
- GatePlugin × 1（TargetNominationIntegrityGate：无真取数 / 全 ungrounded → BLOCK）
- BudgetSpec（长任务弹性：--depth-mode 抬高墙钟上限，逐候选多库取数不被误 kill）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from krow_agent_sdk import AgentBuilder, BudgetSpec
from target_nominator_plugin import (
    TargetNominationIntegrityGate,
    TargetNominatorACTPlugin,
    TargetNominatorToolPlugin,
    build_data_sources_markdown,
    collect_data_sources,
    get_last_score_result,
    reset_capture,
)


def _parse_candidates_file(path: Path) -> list[str]:
    """从候选文件抽基因符号（每行一个 / markdown 列表项 / 逗号分隔）."""
    text = path.read_text(encoding="utf-8")
    genes: list[str] = []
    for raw in re.split(r"[\n,]", text):
        line = raw.strip().lstrip("-*").strip()
        if not line or line.startswith("#"):
            continue
        # 取行首的基因符号 token（字母数字 + 常见符号）
        m = re.match(r"[A-Za-z0-9][A-Za-z0-9\-]{1,15}", line)
        if m:
            genes.append(m.group(0))
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for g in genes:
        if g.upper() not in seen:
            seen.add(g.upper())
            out.append(g)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Krow SDK Cookbook · Target Nominator Demo（借鉴 Cell GPNMB CAR-T）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--candidates", nargs="*", default=None,
        help="候选基因符号列表（如 GPNMB MLANA PMEL）",
    )
    parser.add_argument(
        "--candidates-file", default=None,
        help="候选清单文件（每行/列表项/逗号分隔基因符号）",
    )
    parser.add_argument("--cancer-type", default="melanoma", help="癌种（如 melanoma）")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument(
        "--weights", default=None,
        help='各维权重 JSON（如 \'{"safety":2,"efficacy":1,"druggability":1,"breadth":1}\'）',
    )
    parser.add_argument(
        "--depth-mode", action="store_true",
        help="长任务档：抬高墙钟上限（逐候选多库取数偏重，避免被兜底提前 kill）",
    )
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

    candidates: list[str] = []
    if args.candidates_file:
        cf = Path(args.candidates_file).expanduser().resolve()
        if not cf.exists():
            print(f"❌ 候选文件不存在：{cf}", file=sys.stderr)
            return 1
        candidates = _parse_candidates_file(cf)
    if args.candidates:
        for g in args.candidates:
            if g.upper() not in {c.upper() for c in candidates}:
                candidates.append(g)
    if len(candidates) < 2:
        print(
            f"❌ 候选靶点不足（当前 {len(candidates)}）——提名需 ≥2 候选竞争排序。\n"
            "   传 --candidates GPNMB MLANA ... 或 --candidates-file <path>",
            file=sys.stderr,
        )
        return 1

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

    weights: dict | None = None
    if args.weights:
        try:
            weights = json.loads(args.weights)
        except json.JSONDecodeError as e:
            print(f"❌ --weights 不是合法 JSON：{e}", file=sys.stderr)
            return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "target_nomination.md"
    scores_path = output_dir / "target_scores.json"
    summary_path = output_dir / "summary.json"
    # 幂等清场（journey retry 复用同一 output-dir · 2026-07-11 教训）：残留旧产物会让
    # agent 内 smart_file_write 撞"文件已存在" → retry 空跑。跑前先删本次会写的产物。
    for stale in (md_path, scores_path, summary_path):
        if stale.exists():
            stale.unlink()

    project_root = Path.cwd()

    print("🎯 靶点提名任务")
    print(f"   癌种：     {args.cancer_type}")
    print(f"   候选：     {len(candidates)} 个 —— {', '.join(candidates)}")
    print(f"   报告：     {md_path}")
    print(f"   打分矩阵： {scores_path}")
    if args.depth_mode:
        print("   模式：     depth-mode（长任务档，抬高墙钟上限）")
    print()

    builder = (
        AgentBuilder()
        .with_krow_api_key(api_key)
        .with_project_root(project_root)
        .with_tool_plugin(TargetNominatorToolPlugin())
        .with_act_plugin(TargetNominatorACTPlugin())
        .with_gate_plugin(TargetNominationIntegrityGate())
    )
    if args.base_url:
        if not args.quiet:
            print(f"  🌐 cloud endpoint: {args.base_url}")
        builder = builder.with_base_url(args.base_url)

    # 预算：depth-mode 给足墙钟（逐候选多库取数偏重）；显式 flag 覆盖默认。
    budget_kwargs: dict = {}
    if args.depth_mode:
        budget_kwargs["max_walltime_s"] = args.budget_walltime or 3600
        budget_kwargs["max_total_llm_calls"] = args.budget_llm_calls or 200
    if args.budget_llm_calls is not None:
        budget_kwargs["max_total_llm_calls"] = args.budget_llm_calls
    if args.budget_walltime is not None:
        budget_kwargs["max_walltime_s"] = args.budget_walltime
    if args.budget_replans is not None:
        budget_kwargs["max_replans"] = args.budget_replans
    if "max_walltime_s" in budget_kwargs:
        budget_kwargs.setdefault(
            "target_walltime_s", max(60, budget_kwargs["max_walltime_s"] - 120)
        )
    if budget_kwargs:
        builder = builder.with_budget(BudgetSpec(**budget_kwargs))
        print(f"  💰 budget: {budget_kwargs}")

    if args.reasoning_model:
        builder = builder.with_reasoning_model(args.reasoning_model)
    if args.chat_model:
        builder = builder.with_chat_model(args.chat_model)
    print()

    agent = builder.build()
    # 启用工具取数捕获：让 main.py 跑完后能确定性收口结构化产物（打分矩阵 JSON +
    # 数据来源 url），不依赖 LLM 手抄（TURBO"数据注入≠数据采用"教训，见 plugin §-1）。
    reset_capture()
    try:
        request = _build_request(
            candidates=candidates,
            cancer_type=args.cancer_type,
            md_path=md_path,
            scores_path=scores_path,
            weights=weights,
        )
        result = agent.run(request)
        artifact_ok = md_path.exists() and md_path.stat().st_size >= 800
        if not result.success and not artifact_ok:
            print(f"\n❌ 任务失败：{result.final_output}", file=sys.stderr)
            return 1
        if not result.success and artifact_ok:
            print(
                f"\n⚠️  agent 自评失败但提名报告已落盘 → 视为成功"
                f"（{md_path.stat().st_size}B）",
                file=sys.stderr,
            )

        # ── System 1 确定性收口（TURBO：语法交系统 · 见 plugin §-1）──────────
        # LLM 稳定真取数（报告有真 Ensembl id / OT 分）却不采用打分工具的结构化输出：
        # 自己重算 ranking、手写残缺 target_scores.json、用名字而非 url 溯源。用捕获的
        # **工具自产产物**确定性收口，LLM 只留叙事（提名理由）。
        _finalize_artifacts(md_path=md_path, scores_path=scores_path)

        summary = {
            "cancer_type": args.cancer_type,
            "candidates": candidates,
            "n_candidates": len(candidates),
            "depth_mode": bool(args.depth_mode),
            "budget": budget_kwargs,
            "artifacts": {
                "target_nomination_md": md_path.name if md_path.exists() else None,
                "target_scores_json": scores_path.name if scores_path.exists() else None,
            },
            "agent_success": bool(result.success),
        }
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        print(f"\n📝 提名报告：{md_path}")
        if scores_path.exists():
            print(f"📊 打分矩阵：{scores_path}")
        print(f"🧾 运行摘要：{summary_path}")
        return 0
    finally:
        agent.shutdown()


def _finalize_artifacts(*, md_path: Path, scores_path: Path) -> None:
    """跑后 System 1 收口：确定性落打分矩阵 JSON + 兜底报告数据来源 url.

    两件事都用**工具自产的结构化产物**（打分工具返回 / 取数捕获），不改 LLM 的语义
    决策（提名理由 / 各维有利度判断），只补"语法级"确定性产物——对齐 TURBO 边界：
    ranking/matrix/溯源 url = 语法（系统保证），提名论证 = 语义（LLM 保留）。
    所有动作 fail-soft + 打印可见，绝不吞异常导致主流程崩。
    """
    score_res = get_last_score_result()

    # (1) 打分矩阵 JSON：用打分工具返回原样落盘（保证 ranking/aggregate/grounded/matrix
    #     结构完整），覆盖 LLM 可能写残缺的版本。仅当本次真打过分才覆盖。
    if isinstance(score_res, dict) and score_res.get("ranking"):
        payload = {
            "ranking": score_res.get("ranking"),
            "matrix": score_res.get("matrix"),
            "weights": score_res.get("weights"),
            "issues": score_res.get("issues"),
            "data_sources": score_res.get("data_sources"),
        }
        try:
            scores_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"  🧮 打分矩阵已由工具产出确定性收口 → {scores_path.name}", file=sys.stderr)
        except OSError as e:
            print(f"  ⚠️ 打分矩阵收口写盘失败（不阻塞）：{e}", file=sys.stderr)

    # (2) 报告数据来源 url：LLM 常把 url 换成"Human Protein Atlas"名字导致无法溯源。
    #     若报告里一个来源 url 都没有，则从捕获的取数结果确定性追加"## 数据来源"章节。
    #     这是溯源元数据（确定性），不改 LLM 的提名语义。
    if md_path.exists():
        try:
            report = md_path.read_text(encoding="utf-8")
        except OSError:
            report = ""
        urls = collect_data_sources()
        if urls and not any(u in report for u in urls):
            block = build_data_sources_markdown()
            if block:
                sep = "" if report.endswith("\n") else "\n"
                md_path.write_text(report + sep + "\n" + block + "\n", encoding="utf-8")
                print(
                    f"  🔗 报告缺来源 url → 已从取数捕获确定性追加"
                    f"「## 数据来源」（{len(urls)} 条）",
                    file=sys.stderr,
                )


def _build_request(
    *,
    candidates: list[str],
    cancer_type: str,
    md_path: Path,
    scores_path: Path,
    weights: dict | None,
) -> str:
    cand_str = ", ".join(candidates)
    weights_hint = (
        f"\n   - 用户指定权重：{json.dumps(weights, ensure_ascii=False)}"
        if weights else ""
    )
    return "\n".join([
        f"请为 **{cancer_type}** 做 CAR-T / ADC 表面靶点提名（借鉴 Cell GPNMB 方法论）。",
        f"候选靶点（共 {len(candidates)} 个）：{cand_str}",
        "",
        "工作流（**每个候选都要真取数，禁止凭记忆填分**）：",
        "1. 逐候选调 target_nominator_fetch_expression(gene=<symbol>)",
        "   - 拿 HPA 的 normal（安全维）/ tumor（有效维）/ single-cell 表达 + source url",
        "2. 逐候选调 target_nominator_fetch_associations(gene=<symbol>)",
        "   - 拿 Open Targets 的 tractability（可药维）+ associatedDiseases 分（广谱维）+ source url",
        "3. 把每候选每维的**有利度**（0-1，越大越好）+ 对应工具 source 组织成打分条目：",
        "   - 安全维：健康组织表达越低 → value 越高",
        "   - 有效维：肿瘤表达越高 → value 越高",
        "   - 可药维：antibody_tractable=true → value 高",
        "   - 广谱维：max_association_score / 关联疾病数越大 → value 越高",
        "4. 调 target_nominator_score_candidates(candidates=..., scores=..., weights=...)"
        + weights_hint,
        "   - 若返回 issues 非空（缺维 / ungrounded）→ 回工具补数据再打分",
        "5. 读 ranking + matrix 提名综合有利度最高的**单一**最佳靶点，一句话理由 +"
        " 引用各维 source url。未能取到的维必须显式标 ungrounded（不许猜）。",
        "",
        f"6. 用 smart_file_write 写提名报告到 {md_path}（markdown）：",
        "   - 标题含癌种 + 最佳靶点名",
        "   - 候选四维打分表（安全/有效/可药/广谱 + 综合分）",
        "   - 每维数值旁标 source url（HPA / Open Targets 词条链接）",
        "   - **铁律**：不许出现无 source 的表达/关联数值",
        f"7. 用 smart_file_write 写打分矩阵到 {scores_path}"
        "（把 score_candidates 返回的 ranking/matrix/weights/issues 存成 JSON）",
    ])


if __name__ == "__main__":
    sys.exit(main())
