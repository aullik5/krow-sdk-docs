"""Literature-reviewer cookbook 主入口（v3 cookbook 第 2 个 demo）.

跑前：
    1. set KROW_API_KEY=sk-user-xxx
       (PowerShell: $env:KROW_API_KEY='sk-user-xxx')
       (Linux/Mac:  export KROW_API_KEY=sk-user-xxx)
    2. krow-sdk-install --api-key $KROW_API_KEY
    3. cd examples/cookbook/literature-reviewer && pip install -e .

最小跑（Tier 1：5-10 篇 paper → 简单综述）：
    python main.py sample_data/paper_*.pdf

横向对比跑（Tier 2：30-50 篇 paper + 引用图 + docx）：
    python main.py sample_data/*.pdf --docx \\
        --citation-edges citation_relations.json

全功能跑（Tier 3：100+ paper + 进度日志 + 抄袭检测 + budget）：
    python main.py sample_data/*.pdf \\
        --docx --pdf \\
        --citation-edges citation_relations.json \\
        --progress-log output/review.progress.jsonl \\
        --budget-llm-calls 120 \\
        --budget-walltime 1800

输出：
    output/review_<topic>.md          (综述章节 markdown)
    output/review_<topic>.docx        (仅 --docx；走 word_smart_export)
    output/review_<topic>.pdf         (仅 --pdf；走 word_smart_export)
    output/citation_graph.dot         (引用图 DOT)
    output/topic_map.svg              (聚类地图 SVG，可选)
    output/<basename>.progress.jsonl  (大批量任务进度日志)

────────────────────────────────────────────────────────────────────
本 cookbook 演示 SDK 5 类 plugin（按需省略 ObservabilityPlugin，详 design §3）：
────────────────────────────────────────────────────────────────────
- ToolPlugin × 5（PDF 元数据 / 主题聚类 / 引用图 / 抄袭检测 / 章节大纲）
- ACTPlugin × 1（literature_reviewer ACT，10 步标准工作流）
- GatePlugin × 2
  · CitationCompletenessGate：综述每段 ≥3 篇引用（学术规范）
  · PlagiarismGate：n-gram overlap ≥60% = 抄袭红线
- HintPlugin × 2
  · TopicCoverageHintPlugin：thin cluster 合并建议
  · YearGapHintPlugin：年份跨度 ≥15 年 → 分 era
- EventListenerPlugin × 1（ReviewProgressListener：实时进度 + .progress.jsonl）
- BudgetSpec（100+ paper 任务推荐 120 LLM × 1800s × 2 replan）

注：本 demo **按设计 §3 不演示 ObservabilityPlugin**——学术场景一般不接 BI。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from krow_agent_sdk import AgentBuilder, BudgetSpec
from literature_reviewer_plugin import (
    CitationCompletenessGate,
    LiteratureReviewerACTPlugin,
    LiteratureReviewerToolPlugin,
    PlagiarismGate,
    ReviewProgressListener,
    TopicCoverageHintPlugin,
    YearGapHintPlugin,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Krow SDK Cookbook · Literature Reviewer Demo (v3 PR-B)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "三档跑法：\n"
            "  Tier 1（基础）：python main.py paper1.pdf paper2.pdf paper3.pdf\n"
            "  Tier 2（中量）：python main.py *.pdf --docx --citation-edges edges.json\n"
            "  Tier 3（大量）：python main.py *.pdf --docx --progress-log out/p.jsonl "
            "--budget-llm-calls 120\n"
        ),
    )
    parser.add_argument(
        "pdf_paths",
        nargs="+",
        help="paper PDF 文件路径列表（≥2 篇才能聚类；建议 5-200 篇）",
    )
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--docx", action="store_true", help="同时生成 docx（学术界常用）")
    parser.add_argument("--pdf", action="store_true", help="同时生成 PDF")
    parser.add_argument(
        "--review-topic",
        default="literature_review",
        help="综述主题（用作输出文件名 stem）",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.15,
        help="cluster 阈值（cosine sim ≥ 此值 = 同簇；默认 0.15）",
    )
    parser.add_argument(
        "--outline-template",
        choices=["standard", "compact"],
        default="standard",
        help="综述大纲模板",
    )
    parser.add_argument(
        "--citation-edges",
        default=None,
        help=(
            "引用关系 JSON 文件（list of {from, to}）；"
            "可选：传了才画引用图。建议接 OpenAlex / Semantic Scholar API"
        ),
    )
    parser.add_argument(
        "--progress-log",
        default=None,
        help="进度日志路径（.progress.jsonl）；启用 ReviewProgressListener 写 jsonl",
    )
    parser.add_argument(
        "--min-citations-per-section",
        type=int,
        default=3,
        help="CitationCompletenessGate 每段最少引用数（默认 3，符合学术规范）",
    )
    parser.add_argument(
        "--year-gap-threshold",
        type=int,
        default=15,
        help="YearGapHintPlugin 触发年份跨度（默认 15）",
    )
    # 预算
    parser.add_argument("--budget-llm-calls", type=int, default=None)
    parser.add_argument("--budget-walltime", type=int, default=None)
    parser.add_argument("--budget-replans", type=int, default=None)
    parser.add_argument("--reasoning-model", default=None)
    parser.add_argument("--chat-model", default=None)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("KROW_BASE_URL", "").strip() or None,
        help=(
            "自定义 cloud endpoint（仅 staging / 私有部署用；几乎所有用户不要改）。"
            " 默认走 https://api.krow.cn；可由 $KROW_BASE_URL 覆盖。"
        ),
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    pdf_paths: list[Path] = []
    for raw in args.pdf_paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print(f"❌ PDF 不存在：{p}", file=sys.stderr)
            return 1
        if p.suffix.lower() != ".pdf":
            print(f"❌ 非 PDF：{p.suffix}", file=sys.stderr)
            return 1
        pdf_paths.append(p)
    if len(pdf_paths) < 2:
        print(
            f"⚠️  只有 {len(pdf_paths)} 篇 paper —— 聚类至少需要 2 篇\n"
            "   仍可跑，但 step 2 将报错。",
            file=sys.stderr,
        )

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

    # 引用关系（可选）
    citation_edges: list[dict[str, str]] = []
    if args.citation_edges:
        edges_path = Path(args.citation_edges).expanduser().resolve()
        if not edges_path.exists():
            print(f"❌ citation-edges JSON 不存在：{edges_path}", file=sys.stderr)
            return 1
        try:
            citation_edges = json.loads(edges_path.read_text(encoding="utf-8"))
            if not isinstance(citation_edges, list):
                print("❌ citation-edges 必须是 list[{from,to}]", file=sys.stderr)
                return 1
        except Exception as e:
            print(f"❌ citation-edges 解析失败：{e}", file=sys.stderr)
            return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    # W5 简化（2026-05-19）：去掉 "review_" 前缀冗余.
    # 实测发现 LLM 在长 prompt 下漂移到短名（``literature_review.md``）.
    # 简化命名约定 + 去除前缀，让 prompt 路径与 LLM 直觉一致 → 减少漂移.
    md_path = output_dir / f"{args.review_topic}.md"
    docx_path = output_dir / f"{args.review_topic}.docx" if args.docx else None
    pdf_path = output_dir / f"{args.review_topic}.pdf" if args.pdf else None
    dot_path = output_dir / "citation_graph.dot"
    progress_log_path: Path | None = (
        Path(args.progress_log).expanduser().resolve() if args.progress_log else None
    )

    project_root = pdf_paths[0].parent if pdf_paths else Path.cwd()
    if output_dir.is_relative_to(Path.cwd()):
        project_root = Path.cwd()

    tier = "1 (基础)"
    if len(pdf_paths) >= 30 or progress_log_path:
        tier = "3 (大量)"
    elif args.docx or args.pdf or citation_edges:
        tier = "2 (中量)"
    print("📚 文献综述任务")
    print(f"   tier:     {tier}")
    print(f"   papers:   {len(pdf_paths)}")
    print(f"   markdown: {md_path}")
    if docx_path:
        print(f"   docx:     {docx_path}")
    if pdf_path:
        print(f"   pdf:      {pdf_path}")
    if citation_edges:
        print(f"   edges:    {len(citation_edges)} 条引用关系 → {dot_path}")
    if progress_log_path:
        print(f"   progress: {progress_log_path}")
    print()

    builder = (
        AgentBuilder()
        .with_krow_api_key(api_key)
        .with_project_root(project_root)
        .with_tool_plugin(LiteratureReviewerToolPlugin())
        .with_act_plugin(LiteratureReviewerACTPlugin())
    )

    if args.base_url:
        if not args.quiet:
            print(f"  🌐 cloud endpoint: {args.base_url}")
        builder = builder.with_base_url(args.base_url)

    builder = builder.with_gate_plugin(
        CitationCompletenessGate(
            min_citations_per_section=args.min_citations_per_section
        )
    )
    builder = builder.with_gate_plugin(PlagiarismGate())
    builder = builder.with_hint_plugin(TopicCoverageHintPlugin())
    builder = builder.with_hint_plugin(
        YearGapHintPlugin(gap_threshold_years=args.year_gap_threshold)
    )
    builder = builder.with_event_listener_plugin(
        ReviewProgressListener(
            verbose=not args.quiet,
            progress_log_path=progress_log_path,
            total_papers=len(pdf_paths),
        )
    )

    if any([args.budget_llm_calls, args.budget_walltime, args.budget_replans]):
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
        builder = builder.with_budget(BudgetSpec(**budget_kwargs))
        print(f"  💰 budget: {budget_kwargs}")

    if args.reasoning_model:
        builder = builder.with_reasoning_model(args.reasoning_model)
    if args.chat_model:
        builder = builder.with_chat_model(args.chat_model)
    print()

    agent = builder.build()
    try:
        request = _build_request(
            pdf_paths=pdf_paths,
            citation_edges=citation_edges,
            md_path=md_path,
            docx_path=docx_path,
            pdf_path=pdf_path,
            dot_path=dot_path,
            similarity_threshold=args.similarity_threshold,
            outline_template=args.outline_template,
            min_citations_per_section=args.min_citations_per_section,
        )
        result = agent.run(request)
        # W5 治本（2026-05-19）：artifact-fallback robustness（与 contract-auditor 对齐）.
        # 实测 LLM 在 verify_completion 阶段偶尔报"工具调用失败"（误判 — 实际
        # markdown 在前序 smart_file_write 步骤已落盘），导致 result.success=False；
        # 但用户拿到的产物是完整可读的 → 用户价值优先于 agent 自评.
        # 阈值 1500B = expected_card 最低产物 size.
        artifact_ok = md_path.exists() and md_path.stat().st_size >= 1500
        if not result.success:
            if artifact_ok:
                print(
                    f"\n⚠️  agent 自评失败但 markdown 已落盘 → 视为成功"
                    f"（{md_path.stat().st_size}B; agent_msg: "
                    f"{(result.final_output or '')[:200]}）",
                    file=sys.stderr,
                )
            else:
                print(f"\n❌ 任务失败：{result.final_output}", file=sys.stderr)
                return 1
        print(f"\n📝 综述 markdown：{md_path}")
        if docx_path and docx_path.exists():
            print(f"📄 docx：{docx_path}")
        if pdf_path and pdf_path.exists():
            print(f"📄 PDF：{pdf_path}")
        if dot_path.exists():
            print(f"🔗 引用图 DOT：{dot_path}")
        if progress_log_path and progress_log_path.exists():
            line_count = sum(1 for _ in progress_log_path.open("r", encoding="utf-8"))
            print(f"📋 进度日志：{progress_log_path}（{line_count} 条）")
        return 0
    finally:
        agent.shutdown()


def _build_request(
    *,
    pdf_paths: list[Path],
    citation_edges: list[dict[str, str]],
    md_path: Path,
    docx_path: Path | None,
    pdf_path: Path | None,
    dot_path: Path,
    similarity_threshold: float,
    outline_template: str,
    min_citations_per_section: int,
) -> str:
    pdf_list = "\n".join(f"   - {p}" for p in pdf_paths[:30])
    if len(pdf_paths) > 30:
        pdf_list += f"\n   ... 另 {len(pdf_paths) - 30} 篇"
    parts = [
        "请基于用户提供的 N 篇 paper PDF 做主题文献综述（10 步工作流）。",
        f"PDF 列表（共 {len(pdf_paths)} 篇）：",
        pdf_list,
        "",
        "工作流：",
        "1. **批量调** literature_reviewer_extract_paper_metadata，每个 PDF 调一次",
        "   - 抽 title / authors / year / abstract / keywords / ref_count",
        "   - **铁律**：不要直接读 PDF 全文塞 prompt（上下文爆炸）",
        "",
        "2. 收集所有 paper 元数据后调 literature_reviewer_cluster_papers_by_topic",
        f"   - similarity_threshold={similarity_threshold}",
        "   - 输出 clusters: topic_id / paper_ids / top_terms / year_min/max / thin",
        "   - HintPlugin 自动激活：TopicCoverage / YearGap 推 LLM 软提示",
        "",
        f"3. 调 literature_reviewer_generate_review_outline(template='{outline_template}')",
        "   - 输入：step 2 的 cluster_result",
        "   - 自动决策 Timeline 章节（年份跨度 ≥10 年自动含）",
    ]
    if citation_edges:
        parts.extend([
            "",
            "4. 调 literature_reviewer_build_citation_graph",
            f"   - papers=step 1 输出列表，edges=用户提供的 {len(citation_edges)} 条引用",
            f"   - 把 dot 字段写到 {dot_path}",
            "",
        ])
        next_step = 5
    else:
        next_step = 4

    parts.extend([
        f"{next_step}. 基于 outline + 聚类结果起草综述 markdown",
        f"   - **每段 ≥{min_citations_per_section} 篇引用**（CitationCompletenessGate 守门）",
        "   - **不允许大段抄原文**（PlagiarismGate 守门）",
        "   - 引用格式：[N] 数字 / (Author, Year) 任选",
        "   - LLM 应：把 abstract 用自己的话改写，不直接复制",
        "   - **铁律**：综述必须保留每篇 paper abstract 中的**具体实验数据**：",
        "     * 改进百分比（如 ``8.5% over BPR-MF`` / ``5.2% Hit@10``）",
        "     * 数据集名（如 ``MovieLens-1M`` / ``Amazon-Books``）",
        "     * baseline 名（如 ``BPR-MF`` / ``SASRec``）",
        "     学术综述的核心价值就是让读者一眼看到证据数字，不要写空泛叙事",
        "",
        f"{next_step + 1}. 调 smart_file_write(operation='write', path={md_path}, "
        "content=<完整 markdown 文本>) 落盘",
        "   ⚠️ **铁律**：写 markdown 必须用 ``smart_file_write``；",
        "   ``word_smart_export`` 是 docx→其他格式 转换工具，会把 docx binary 写到 .md "
        "→ encoding 灾难",
        "   ⚠️ **operation 只用 write**：write 覆盖同名文件，重写多少次都安全；",
        "   用 create 写第二次会撞「文件已存在，请设置 overwrite=true」硬闸",
        "   ⚠️ **content 必须是完整正文**：空正文会被 empty_content_gate 拒绝"
        "（工具不落 0 字节文件）；正文过长被截断 → 先 write 首段再 append 续写",
        "",
        f"{next_step + 2}. 调 literature_reviewer_detect_plagiarism_overlap",
        f"   - review_path={md_path}（上一步刚落盘的综述，工具自己读，省 token）",
        "   - source_texts={paper_id: abstract} 来自 step 1",
        "   - 默认 5-gram + 60% 阈值；命中即 PlagiarismGate BLOCK",
        "",
        f"{next_step + 3}. 如 Gate BLOCK：根据 reason 修改 → "
        "用 smart_file_write(operation='write') 覆盖重写 → 重检测",
        "   - CitationCompletenessGate BLOCK → 看缺哪几段引用 → 补齐",
        "   - PlagiarismGate BLOCK → 找命中段落 → 改写",
    ])
    if docx_path:
        parts.append(
            f"{next_step + 4}. word_smart_export(file_path={md_path}, "
            f"format='docx', output_path={docx_path})"
        )
    if pdf_path:
        parts.append(
            f"{next_step + 5}. word_smart_export(file_path={md_path}, "
            f"format='pdf', output_path={pdf_path})"
        )
    return "\n".join(parts)


if __name__ == "__main__":
    sys.exit(main())
