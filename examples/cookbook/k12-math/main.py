"""K12 数学知识编译 cookbook 主入口（SDK 二次开发范例）。

把 K12 数学教材/讲义/知识点总结编译成教育知识图谱（知识点/定理/公式/原子知识/
原子技能 + part_of / has_* / requires_* / prerequisite_of 学习路径骨架），
并做 System 1 学习路径校验（前置 DAG 环检测）。

核心演示（开发者二次开发路径）：
    AgentBuilder()
        .with_domain_pack("k12_math")                       # 激活内置 K12 包
        .with_domain_pack_manifest("k12_school_pack.yaml")  # 可选：校本/题库特化
        .build()
    agent.run(task, task_context={"strategy": "knowledge_compile"})

跑前：
    1. set KROW_API_KEY=sk-user-xxx
    2. krow-sdk-install --api-key $KROW_API_KEY
    3. cd examples/cookbook/k12-math && pip install -e .

最小跑（自带导数/概率/立体几何 3 份资料）：
    python main.py

自定义资料 + 校本包：
    python main.py path/to/k12_docs --project-dir ./my_k12_kb \\
        --school-pack k12_school_pack.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEFAULT_SAMPLE = _HERE / "sample_data"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Krow SDK Cookbook · K12 数学知识编译 Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("sources", nargs="*", help="资料文件或目录（缺省用自带 sample_data/）")
    parser.add_argument("--project-dir", default="k12_project",
                        help="项目目录（本体+wiki 落盘在此 .krow/）")
    parser.add_argument("--output-dir", default="output", help="编译报告输出目录")
    parser.add_argument("--school-pack", default=None,
                        help="校本/题库特化领域包 manifest（yaml 路径，继承 k12_math）")
    parser.add_argument("--question-bank", action="store_true",
                        help="叠加激活内置题库层包 k12_question_bank（题目/解答/步骤/错因 + TESTS/USES_*）")
    parser.add_argument("--base-url",
                        default=os.environ.get("KROW_BASE_URL", "").strip() or None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    api_key = os.environ.get("KROW_API_KEY", "").strip()
    if not api_key:
        print("❌ 未设 KROW_API_KEY 环境变量。\n"
              "   Windows: $env:KROW_API_KEY='sk-user-xxx'\n"
              "   Linux/Mac: export KROW_API_KEY=sk-user-xxx", file=sys.stderr)
        return 1

    # ── 项目目录 + docs 准备 ───────────────────────────────────────────
    project_dir = Path(args.project_dir).expanduser().resolve()
    docs_dir = project_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    raw_sources = args.sources or [str(_DEFAULT_SAMPLE)]
    for raw in raw_sources:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print(f"❌ 资料不存在：{p}", file=sys.stderr)
            return 1
        files = sorted(p.rglob("*")) if p.is_dir() else [p]
        for f in files:
            if not f.is_file() or ".krow" in f.parts:
                continue
            if f.name.lower() in {"readme.md", "readme.txt"}:
                continue
            dst = docs_dir / f.name
            if not dst.exists():
                shutil.copy2(f, dst)

    doc_files = sorted(f for f in docs_dir.iterdir() if f.is_file())
    if not doc_files:
        print(f"❌ docs 目录为空：{docs_dir}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("📐 K12 数学知识编译任务")
    print(f"   project: {project_dir}")
    print(f"   docs:    {len(doc_files)} 份资料")
    _domain_extra = ""
    if args.question_bank:
        _domain_extra += " + k12_question_bank"
    if args.school_pack:
        _domain_extra += f" + {args.school_pack}"
    print(f"   domain:  k12_math{_domain_extra}")
    print()

    from krow_agent_sdk import AgentBuilder

    # ── 构建 Agent：激活 K12 领域包（核心二次开发 API）──────────────────
    builder = (
        AgentBuilder()
        .with_krow_api_key(api_key)
        .with_project_root(project_dir)
        .with_domain_pack("k12_math")
    )
    if args.question_bank:
        builder = builder.with_domain_pack("k12_question_bank")
    if args.school_pack:
        pack_path = Path(args.school_pack)
        if not pack_path.is_absolute():
            pack_path = (_HERE / pack_path).resolve()
        if not pack_path.exists():
            print(f"❌ 校本包不存在：{pack_path}", file=sys.stderr)
            return 1
        builder = builder.with_domain_pack_manifest(str(pack_path))
    if args.base_url:
        builder = builder.with_base_url(args.base_url)

    agent = builder.build()
    try:
        from modules.utils.project_context import set_project_root
        set_project_root(str(project_dir))
    except Exception:  # noqa: BLE001
        pass

    try:
        print("【1/2】知识编译（real LLM · strategy=knowledge_compile）")
        report = agent.run(
            f"把 {docs_dir} 下的 K12 数学资料编译成结构化知识库与百科词条，"
            "区分知识点/定义/定理/公式/原子知识/原子技能，"
            "并标注 part_of 目录层级、requires_knowledge/requires_skill 依赖、"
            "prerequisite_of 学习前置关系。",
            task_context={"strategy": "knowledge_compile"},
        )
        if not args.quiet:
            print(f"   {getattr(report, 'summary', '') or report}")

        print("\n【2/2】学习路径校验（System 1 · 前置 DAG 环检测）")
        cycle_report = _validate_learning_path(project_dir)
        print(f"   {'✅' if cycle_report['is_dag'] else '❌'} {cycle_report['detail']}")

        _write_report(output_dir / "k12_compile_report.md", project_dir,
                      doc_files, cycle_report)
        print(f"\n📝 编译报告：{output_dir / 'k12_compile_report.md'}")
        print(f"📖 wiki 词条：{project_dir / '.krow' / 'wiki'}")
        return 0 if cycle_report["is_dag"] else 2
    finally:
        agent.shutdown()


def _validate_learning_path(project_dir: Path) -> dict:
    """从本体取 prerequisite_of 边，跑 System 1 环检测（学习路径必须是 DAG）。"""
    try:
        from modules.knowledge.global_ontology_metrics import iter_relation_pairs
        from modules.knowledge.k12_scoring import detect_prerequisite_cycles
        edges = list(iter_relation_pairs("prerequisite_of"))
        rep = detect_prerequisite_cycles(edges)
        return {"is_dag": rep.is_dag, "detail": rep.detail,
                "cycles": rep.cycles, "edge_count": rep.edge_count}
    except Exception as exc:  # noqa: BLE001
        return {"is_dag": True, "detail": f"（跳过环检测：{exc}）",
                "cycles": [], "edge_count": 0}


def _write_report(path: Path, project_dir: Path, doc_files: list[Path],
                  cycle_report: dict) -> None:
    lines = [
        "# K12 数学知识编译报告", "",
        "## 学习路径校验（prerequisite_of）", "",
        f"- DAG（无环）：{'是 ✅' if cycle_report['is_dag'] else '否 ❌'}",
        f"- 前置边数：{cycle_report.get('edge_count', 0)}",
        f"- 详情：{cycle_report.get('detail', '')}", "",
        "## 已编译资料", "",
    ]
    lines += [f"- {f.name}" for f in doc_files]
    lines += ["", "---", "",
              "_本报告由 k12-math cookbook 确定性生成（学习路径校验零 LLM）。_"]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
