"""Knowledge-wiki cookbook 主入口（v3.5 第 1 个"知识管理"demo）.

把一批领域资料编译成结构化知识库（本体 Ontology）+ 可浏览互链的百科词条（wiki）。

跑前：
    1. set KROW_API_KEY=sk-user-xxx
       (PowerShell: $env:KROW_API_KEY='sk-user-xxx')
       (Linux/Mac:  export KROW_API_KEY=sk-user-xxx)
    2. krow-sdk-install --api-key $KROW_API_KEY
    3. cd examples/cookbook/knowledge-wiki && pip install -e .

最小跑（用自带 sample_data 的 3 篇光伏资料）：
    python main.py

指定自己的资料 + 项目目录：
    python main.py path/to/docs --project-dir ./my_kb

输出：
    <project-dir>/.krow/ontology/global.db   (本体 SSOT：概念/实体/关系/chunk)
    <project-dir>/.krow/wiki/**/*.md         (百科词条：每个核心节点一篇)
    output/compile_report.md                 (编译验收报告：覆盖率 + 词条清单)
    output/ontology_snapshot.json            (本体计数快照)
    output/<basename>.progress.jsonl         (可选：三阶段编译进度日志)

────────────────────────────────────────────────────────────────────
编译流水线（System 1 编排 + System 2 单发，TURBO 哲学）
────────────────────────────────────────────────────────────────────
不靠"巨型 macro-ReACT 一把跑完"（易在 step 解析 / 重规划上空转），而是用确定性
代码把引擎里**已验证可靠的单发能力**串起来：

    0. 规划：knowledge_wiki_scan_sources    （System 1 · 零 LLM）
    1. 抽取：knowledge_wiki_extract_ontology （System 2 · 每文件一次 LLM 调用）
    2. 关联：knowledge_wiki_link_relations   （System 2 · 一次 LLM 调用提关系）
    3. 物化：knowledge_wiki_materialize      （System 1 · 零 LLM · 红链物化）
    4. 验收：knowledge_wiki_coverage_report  （System 1 · 零 LLM · 覆盖核对）

抽取 / 物化都复用引擎内置实现（``extractive_tools`` / ``ontology_stub_compiler``），
cookbook **不重写**这些轮子（SSOT 铁律）。SDK 场景关键点：桌面端 wiki 物化由
``KnowledgeLifecycleManager`` 自动触发，SDK 端**必须显式调 materialize**，否则
本体抽完但 wiki 不丰富（正是真实用户反馈的痛点）。

演示 SDK plugin（按需省略 Hint / Observability，详 design §3）：
- ToolPlugin（scan / extract / relate / materialize / coverage 五件套）
- ACTPlugin × 1（knowledge_wiki_studio，供 agent.run 走 knowledge_compile 时选用）
- GatePlugin × 1（WikiCoverageGate：防"假编译"——本体抽完但词条没写）
- EventListenerPlugin × 1（CompileProgressListener：三阶段进度）
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from knowledge_wiki_plugin import (
    CompileProgressListener,
    KnowledgeWikiACTPlugin,
    KnowledgeWikiToolPlugin,
    WikiCoverageGate,
    extract_ontology_from_sources,
    link_ontology_relations,
    materialize_wiki_pages,
    report_wiki_coverage,
    scan_knowledge_sources,
)
from krow_agent_sdk import AgentBuilder, BudgetSpec

_HERE = Path(__file__).resolve().parent
_DEFAULT_SAMPLE = _HERE / "sample_data"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Krow SDK Cookbook · Knowledge & Wiki Studio Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "跑法：\n"
            "  最小跑（自带光伏 sample_data）：python main.py\n"
            "  自定义资料：python main.py path/to/docs --project-dir ./my_kb\n"
        ),
    )
    parser.add_argument(
        "sources",
        nargs="*",
        help="资料文件或目录（缺省用自带 sample_data/）",
    )
    parser.add_argument(
        "--project-dir",
        default="knowledge_project",
        help="项目目录（本体 + wiki 落盘在此 .krow/；默认 ./knowledge_project）",
    )
    parser.add_argument("--output-dir", default="output", help="编译报告输出目录")
    parser.add_argument(
        "--progress-log",
        default=None,
        help="三阶段编译进度日志路径（.progress.jsonl）",
    )
    parser.add_argument(
        "--min-wiki-pages",
        type=int,
        default=3,
        help="WikiCoverageGate 最少 wiki 页数（默认 3）",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=15,
        help="每个源文件最多抽取本体对象数（1-20，默认 15）",
    )
    parser.add_argument(
        "--max-relations",
        type=int,
        default=20,
        help="关系推断阶段最多落库关系数（默认 20）",
    )
    parser.add_argument(
        "--min-signal",
        type=int,
        default=1,
        help="wiki 物化质量门：关系+出处数 ≥ 此值才成页（默认 1）",
    )
    parser.add_argument(
        "--skip-relations",
        action="store_true",
        help="跳过关系推断阶段（只抽本体 + 物化 wiki，更快）",
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

    # ── 项目目录 + docs 准备 ─────────────────────────────────────────
    project_dir = Path(args.project_dir).expanduser().resolve()
    docs_dir = project_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # 收集源文件：未指定则用自带 sample_data
    raw_sources = args.sources or [str(_DEFAULT_SAMPLE)]
    copied = 0
    for raw in raw_sources:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print(f"❌ 资料不存在：{p}", file=sys.stderr)
            return 1
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                # 跳过 .krow 产出物 + README（资料目录的说明文档，不是知识源）
                if not f.is_file() or ".krow" in f.parts:
                    continue
                if f.name.lower() in {"readme.md", "readme.txt"}:
                    continue
                dst = docs_dir / f.name
                if not dst.exists():
                    shutil.copy2(f, dst)
                    copied += 1
        else:
            dst = docs_dir / p.name
            if not dst.exists():
                shutil.copy2(p, dst)
                copied += 1

    doc_files = sorted(f for f in docs_dir.iterdir() if f.is_file())
    if not doc_files:
        print(f"❌ docs 目录为空：{docs_dir}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "compile_report.md"
    snapshot_path = output_dir / "ontology_snapshot.json"
    progress_log_path: Path | None = (
        Path(args.progress_log).expanduser().resolve() if args.progress_log else None
    )

    print("📚 知识编译任务")
    print(f"   project:  {project_dir}")
    print(f"   docs:     {len(doc_files)} 份资料（{docs_dir}）")
    print(f"   wiki out: {project_dir / '.krow' / 'wiki'}")
    print(f"   report:   {report_path}")
    print()

    # ── 构建 Agent ───────────────────────────────────────────────────
    builder = (
        AgentBuilder()
        .with_krow_api_key(api_key)
        .with_project_root(project_dir)
        .with_tool_plugin(KnowledgeWikiToolPlugin())
        .with_act_plugin(KnowledgeWikiACTPlugin())
        .with_gate_plugin(WikiCoverageGate(min_wiki_pages=args.min_wiki_pages))
        .with_event_listener_plugin(
            CompileProgressListener(
                verbose=not args.quiet,
                progress_log_path=progress_log_path,
            )
        )
    )

    if args.base_url:
        if not args.quiet:
            print(f"  🌐 cloud endpoint: {args.base_url}")
        builder = builder.with_base_url(args.base_url)

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
    # build() 已 bootstrap 引擎运行时（LLM provider + 工具栈 + ontology store）。
    # 把 project_root 写进 SSOT，供编译三段工具内的本体定位（对齐 seed 脚本）。
    try:
        from modules.utils.project_context import set_project_root

        set_project_root(str(project_dir))
    except Exception:  # noqa: BLE001
        pass

    try:
        # ── 知识编译流水线（System 1 编排 + System 2 单发，TURBO 哲学）──────
        # 不依赖 macro-ReACT 一把跑完（易空转），而是确定性串起引擎已验证的单发
        # 能力：扫描 → 逐文件抽取 → 关系推断 → wiki 物化 → 覆盖验收。
        quiet = args.quiet

        print("【0/4】规划：扫描可编译源清单")
        scan = scan_knowledge_sources(docs_dir)
        if not scan.get("ok"):
            print(f"\n{scan.get('error')}", file=sys.stderr)
            return 1
        sources = [s["path"] for s in scan.get("sources", [])]
        print(f"   {scan.get('summary')}")

        print("\n【1/4】抽取阶段：逐文件抽概念/实体/事件入本体（real LLM）")
        ext = extract_ontology_from_sources(
            project_dir, sources, max_items=args.max_items
        )
        if not quiet:
            for pf in ext.get("per_file", []):
                print(f"   🔍 {pf['file']} → +{pf.get('new_objects', 0)} 对象")
        print(f"   {ext.get('summary')}")
        if not ext.get("ok"):
            print(
                "\n❌ 抽取阶段未产出本体对象（可能 LLM 凭证/网络异常）",
                file=sys.stderr,
            )
            return 1

        if not args.skip_relations:
            print("\n【2/4】关联阶段：LLM 推断领域关系并落库（real LLM）")
            rel = link_ontology_relations(project_dir, max_relations=args.max_relations)
            print(f"   🔗 {rel.get('summary')}")
        else:
            print("\n【2/4】关联阶段：--skip-relations 跳过")

        print("\n【3/4】发布阶段：本体 → wiki 词条确定性物化（零 LLM）")
        mat = materialize_wiki_pages(project_dir, min_signal=args.min_signal)
        print(f"   📝 {mat.get('summary')}")

        print("\n【4/4】验收阶段：本体↔wiki 覆盖核对")
        coverage = report_wiki_coverage(project_dir)
        print(f"   ✅ {coverage.get('summary')}")

        _write_compile_report(
            report_path, coverage, doc_files=doc_files, project_dir=project_dir
        )
        _write_snapshot(snapshot_path, coverage)

        wiki_pages = coverage.get("wiki_page_count", 0) if coverage.get("ok") else 0
        artifact_ok = wiki_pages >= 1 and coverage.get("key_node_count", 0) >= 1
        if not artifact_ok:
            print(
                f"\n❌ 编译未产出有效知识库（wiki 页={wiki_pages}，"
                f"核心节点={coverage.get('key_node_count', 0)}）",
                file=sys.stderr,
            )
            return 1
        if coverage.get("under_populated"):
            print(
                f"\n⚠️  覆盖偏低（wiki 页={wiki_pages} / 核心节点="
                f"{coverage.get('key_node_count', 0)}）；考虑提高 --max-items。",
                file=sys.stderr,
            )

        print(f"\n📝 编译报告：{report_path}")
        print(f"📊 本体快照：{snapshot_path}")
        print(f"📖 wiki 词条：{project_dir / '.krow' / 'wiki'}（{wiki_pages} 篇）")
        if progress_log_path and progress_log_path.exists():
            n = sum(1 for _ in progress_log_path.open("r", encoding="utf-8"))
            print(f"📋 进度日志：{progress_log_path}（{n} 条）")
        return 0
    finally:
        agent.shutdown()


def _collect_wiki_titles(project_dir: Path) -> list[str]:
    """从 .krow/wiki/**/*.md 读每篇词条的 frontmatter title / 首个 H1（确定性）。"""
    wiki_dir = project_dir / ".krow" / "wiki"
    titles: list[str] = []
    if not wiki_dir.exists():
        return titles
    for md in sorted(wiki_dir.rglob("*.md")):
        name = md.name.lower()
        if name.startswith(("_", ".")) or name in {"index.md", "readme.md"}:
            continue
        title = ""
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("title:"):
                title = s.split(":", 1)[1].strip().strip("\"'")
                break
            if s.startswith("# "):
                title = s[2:].strip()
                break
        rel = md.relative_to(wiki_dir).as_posix()
        titles.append(f"{title or md.stem}（{rel}）")
    return titles


def _write_compile_report(
    path: Path, coverage: dict, *, doc_files: list[Path], project_dir: Path
) -> None:
    """写确定性编译验收报告（markdown）。内容来自 coverage 核对，非 LLM 生成。"""
    counts = coverage.get("ontology_counts", {}) if coverage.get("ok") else {}
    by_cat = coverage.get("wiki_by_category", {}) if coverage.get("ok") else {}
    wiki_titles = _collect_wiki_titles(project_dir)
    lines = [
        "# 知识编译验收报告",
        "",
        "## 概要",
        "",
        coverage.get("summary", "（覆盖核对失败）"),
        "",
        "## 本体统计（GlobalOntology）",
        "",
        f"- 概念（concept）：{counts.get('concept', 0)}",
        f"- 实体（entity）：{counts.get('entity', 0)}",
        f"- 关系（relation）：{counts.get('relation', 0)}",
        f"- 文档片段（document_chunk）：{counts.get('document_chunk', 0)}",
        f"- 事件（event）：{counts.get('event', 0)}",
        "",
        "## wiki 词条覆盖",
        "",
        f"- wiki 页总数：{coverage.get('wiki_page_count', 0)}",
        f"- 核心节点（概念+实体）：{coverage.get('key_node_count', 0)}",
        f"- 覆盖率：{coverage.get('coverage_ratio', 0):.0%}",
    ]
    for cat, n in by_cat.items():
        if n:
            lines.append(f"- 分类 `{cat}`：{n} 篇")
    lines += [
        "",
        "## 已生成词条",
        "",
    ]
    lines += [f"- {t}" for t in wiki_titles] or ["（无）"]
    lines += [
        "",
        "## 已编译资料",
        "",
    ]
    lines += [f"- {f.name}" for f in doc_files]
    lines += ["", "---", "", "_本报告由 knowledge_wiki_coverage_report 确定性生成（零 LLM）。_"]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_snapshot(path: Path, coverage: dict) -> None:
    payload = {
        "ok": coverage.get("ok", False),
        "ontology_counts": coverage.get("ontology_counts", {}),
        "wiki_page_count": coverage.get("wiki_page_count", 0),
        "wiki_by_category": coverage.get("wiki_by_category", {}),
        "key_node_count": coverage.get("key_node_count", 0),
        "coverage_ratio": coverage.get("coverage_ratio", 0.0),
        "under_populated": coverage.get("under_populated", True),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main())
