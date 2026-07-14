"""datasheet-batch cookbook 主入口（模拟 KAD 生产场景 · 并发批量 datasheet 解析）。

演示两条路径：

1. **确定性演示（--demo，零 LLM）**：直接调 datasheet_batch_parse 并发解析随仓样例，
   打印 per-item 归属 + 覆盖报告。用于快速验证 N1–N5 无需 API key。

2. **Agent 路径（默认，需 KROW_API_KEY）**：把「批量解析这批 datasheet」交给 Krow
   agent（datasheet_batch ACT），由 Macro/Micro ReACT 选中并发工具、读覆盖报告、
   在覆盖率守门下收尾。这才是 KAD 的真实生产形态（认知回路内并发 + per-item 记账）。

跑前（Agent 路径）：
    export KROW_API_KEY=sk-user-xxx
    krow-sdk-install --api-key $KROW_API_KEY
    cd examples/cookbook/datasheet-batch && pip install -e .

最小跑：
    python main.py --demo                 # 零 LLM 确定性演示
    python main.py                        # Agent 路径（需 key）
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

import datasheet_batch_plugin as db

_HERE = Path(__file__).resolve().parent
_DEFAULT_SAMPLE = _HERE / "sample_data"


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = (getattr(stream, "encoding", "") or "").lower()
        if "utf-8" in enc or "utf8" in enc:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            with contextlib.suppress(Exception):
                reconfigure(encoding="utf-8", errors="backslashreplace")


def _discover_items(sample_dir: Path) -> list[dict[str, str]]:
    """从样例目录发现 datasheet 清单 [{model, path}]（model = 文件名去后缀）。"""
    items: list[dict[str, str]] = []
    for p in sorted(sample_dir.glob("*.txt")):
        items.append({"model": p.stem, "path": str(p)})
    return items


def _run_demo(items: list[dict[str, str]], project_root: Path, max_workers: int) -> int:
    """零 LLM 确定性演示：直接调编排工具，打印覆盖报告。"""
    print("🔧 确定性演示（零 LLM）：并发批量解析 datasheet")
    print(f"   清单：{len(items)} 份 · 并发度 {max_workers}")
    res = db.datasheet_batch_parse(
        items, project_root=str(project_root), max_workers=max_workers
    )
    if not res.get("ok"):
        print(f"❌ {res.get('error')}", file=sys.stderr)
        return 1
    print(f"\n📊 {res['summary']}")
    print(f"   completed={res['completed']} failed={res['failed']} "
          f"degraded={res['degraded']} coverage={res['coverage']}")
    print("\n   per-item 归属：")
    for r in res["results"]:
        tag = {"completed": "✅", "failed": "❌", "degraded": "⚠️"}.get(r["status"], "·")
        detail = r.get("part_number") or (r.get("error", "").splitlines() or [""])[0]
        print(f"     {tag} {r['model']}: {detail}")

    out = project_root / "datasheet_results.json"
    with contextlib.suppress(Exception):
        out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n📦 结果落盘：{out}")
    # 演示视角：只要有成功份且覆盖率>0 即演示成功（失败份是 N3 隔离的刻意样例）。
    return 0 if res["completed"] > 0 else 1


def _stage_items_into_project(items: list[dict[str, str]], project_root: Path) -> list[dict[str, str]]:
    """把样例 datasheet 落入 project_root/upload/（SDK 沙箱允许的输入目录）。

    SDK 路径安全校验只放行 project_root 内的路径，样例默认在 sample_dir（沙箱外）。
    真实生产里用户上传的 datasheet 也落在 upload/，此处贴合该形态：复制后给 agent
    传项目内相对路径 upload/<file>，agent 才能真正读到并解析。
    """
    import shutil

    upload = project_root / "upload"
    upload.mkdir(parents=True, exist_ok=True)
    staged: list[dict[str, str]] = []
    for it in items:
        src = Path(it["path"])
        dst = upload / src.name
        with contextlib.suppress(Exception):
            shutil.copyfile(src, dst)
        staged.append({"model": it["model"], "path": f"upload/{src.name}"})
    return staged


def _run_agent(items: list[dict[str, str]], project_root: Path, output_dir: Path,
               api_key: str, args: argparse.Namespace) -> int:
    """Agent 路径：交给 Krow agent 用 datasheet_batch ACT 并发处理。"""
    from krow_agent_sdk import AgentBuilder

    # 把样例落入 project_root/upload/ 并改写为项目内相对路径（沙箱约定）。
    items = _stage_items_into_project(items, project_root)

    builder = (
        AgentBuilder()
        .with_krow_api_key(api_key)
        .with_project_root(str(project_root))
        .with_tool_plugin(db.DatasheetBatchToolPlugin())
        .with_gate_plugin(db.DatasheetBatchCoverageGate())
        .with_act_plugin(db.DatasheetBatchACTPlugin())
    )
    if args.base_url:
        builder = builder.with_base_url(args.base_url)
    if args.chat_model:
        builder = builder.with_chat_model(args.chat_model)

    agent = builder.build()
    manifest = json.dumps(items, ensure_ascii=False)
    task = (
        "批量并发解析下方 datasheet 清单（清单已直接给出，**无需搜索文件系统**）。\n"
        "第一步动作就调 datasheet_batch_parse：\n"
        f"  datasheet_batch_parse(items={manifest}, "
        f"project_root=\"{project_root}\", max_workers=8)\n"
        "然后读返回的 completed/failed/degraded/coverage/remaining/should_continue，"
        "若 should_continue=true 用相同 items 续跑至 remaining=0；"
        "最后把 per-item 结果写 output/datasheet_results.json、"
        "覆盖报告写 output/datasheet_batch_report.md。"
    )
    print("🤖 Agent 路径：交给 Krow agent（datasheet_batch ACT）并发处理…")
    result = agent.run(task, task_context={"act_name": "datasheet_batch"})

    final = getattr(result, "final_output", "") or ""
    success = bool(getattr(result, "success", False))
    print(f"   success={success} · final_output {len(final)} 字")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "agent_output.md").write_text(final, encoding="utf-8")
    with contextlib.suppress(Exception):
        agent.shutdown()
    return 0 if (success or final.strip()) else 1


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Krow SDK Cookbook · Datasheet 批量并发解析（模拟 KAD 场景）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--demo", action="store_true", help="零 LLM 确定性演示（不需 API key）")
    parser.add_argument("--sample-dir", default=str(_DEFAULT_SAMPLE))
    parser.add_argument("--project-dir", default="datasheet_project")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--base-url", default=os.environ.get("KROW_BASE_URL", "").strip() or None)
    parser.add_argument("--chat-model", default=None)
    args = parser.parse_args(argv)

    sample_dir = Path(args.sample_dir).expanduser().resolve()
    if not sample_dir.is_dir():
        print(f"❌ 样例目录不存在：{sample_dir}", file=sys.stderr)
        return 1
    items = _discover_items(sample_dir)
    if not items:
        print(f"❌ 样例目录无 .txt datasheet：{sample_dir}", file=sys.stderr)
        return 1

    project_root = Path(args.project_dir).expanduser().resolve()
    project_root.mkdir(parents=True, exist_ok=True)

    if args.demo:
        return _run_demo(items, project_root, args.max_workers)

    api_key = os.environ.get("KROW_API_KEY", "").strip()
    if not api_key:
        print(
            "❌ 未设 KROW_API_KEY（Agent 路径需要）。\n"
            "   快速体验可跑零 LLM 确定性演示：python main.py --demo\n"
            "   Agent 路径：export KROW_API_KEY=sk-user-xxx",
            file=sys.stderr,
        )
        return 1
    output_dir = Path(args.output_dir).expanduser().resolve()
    return _run_agent(items, project_root, output_dir, api_key, args)


if __name__ == "__main__":
    sys.exit(main())
