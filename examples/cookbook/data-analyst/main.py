"""Data-auditor cookbook 主入口（v2 升级：异常检测 + 合规守门 + 预算控制）.

跑前：
    1. set KROW_API_KEY=sk-user-xxx
       (PowerShell: $env:KROW_API_KEY='sk-user-xxx')
       (Linux/Mac:  export KROW_API_KEY=sk-user-xxx)
    2. krow-sdk-install --api-key $KROW_API_KEY  # 装私有 runtime
    3. cd examples/cookbook/data-analyst && pip install -e .

最小跑（Tier 1：基础统计 → markdown 报告）：
    python main.py sample_data/titanic.csv

完整跑（Tier 2：基础统计 + 异常检测 + 相关性 + PDF）：
    python main.py sample_data/titanic.csv --audit --pdf

全功能跑（Tier 3：合规审计；含 PII 守门 + 预算限制 + 审计日志）：
    python main.py sample_data/payments.csv \\
        --audit --pdf \\
        --budget-llm-calls 15 \\
        --budget-walltime 300 \\
        --audit-log output/payments.audit.jsonl

输出：
    output/<csv_basename>_report.md
    output/<csv_basename>_report.pdf       (仅当传 --pdf；走 word_smart_export)
    output/<csv_basename>.audit.jsonl      (仅当传 --audit-log 或 --audit；合规日志)

────────────────────────────────────────────────────────────────────
v2 升级要点（与 v1 data-analyst 对比）：
────────────────────────────────────────────────────────────────────
1. **新增 2 个工具**（Krow 内置无法替代的能力）
   - data_analyst_detect_anomalies（IQR / z-score / IsolationForest）
   - data_analyst_compute_correlation（pearson / spearman + top N）
2. **新增 GatePlugin × 2**（合规硬守门）
   - PIIDetectorGate：column 含手机/身份证 → BLOCK，要求脱敏
   - OutputPathGate：报告路径必须在 project_root 内（防 path traversal）
3. **新增 HintPlugin**（System 2 软提示）
   - 检测时序列 / 高基数 ID 列 / 全 NaN 列时给 LLM 建议
4. **新增 AuditEventListener**（合规审计日志）
   - 每个工具调用 + 结果落 .audit.jsonl
5. **新增 BudgetSpec**（防爆 token）
   - 数据分析容易陷入"每列都跑一次 anomaly_score"循环 → 硬约束

PDF 输出策略（SSOT 复用，详 data_analyst_plugin.py §1.7）：
- cookbook plugin **不**自己写 PDF 渲染工具（避免重复造轮子）
- LLM 在 ACT 流程 step 6 调用 Krow 内置 `word_smart_export(format="pdf")` 工具
- 内置工具 SSOT = `MarkdownDocumentRenderer`（reportlab + 自带 CJK 字体）
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from data_analyst_plugin import (
    AuditEventListener,
    DataAnalystACTPlugin,
    DataAnalystProgressListener,
    DataAnalystToolPlugin,
    DataInsightHintPlugin,
    OutputPathGate,
    PIIDetectorGate,
)
from krow_agent_sdk import AgentBuilder, BudgetSpec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Krow SDK Cookbook · Data Auditor Demo (v2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "三档跑法（按需启用 SDK 高级能力）：\n"
            "  Tier 1（基础）  ：python main.py data.csv\n"
            "  Tier 2（审计）  ：python main.py data.csv --audit --pdf\n"
            "  Tier 3（合规）  ：python main.py data.csv --audit --pdf "
            "--budget-llm-calls 15 --audit-log out/audit.jsonl\n"
        ),
    )
    parser.add_argument("csv_path", help="CSV 文件路径")
    parser.add_argument("--output-dir", default="output", help="输出目录（默认 ./output）")
    parser.add_argument("--pdf", action="store_true", help="同时生成 PDF（走 word_smart_export）")
    parser.add_argument(
        "--audit",
        action="store_true",
        help=(
            "启用审计模式：检测异常 + 算相关性 + 写合规结论"
            "（demo data_analyst_detect_anomalies / compute_correlation 工具）"
        ),
    )
    parser.add_argument(
        "--anomaly-method",
        default="iqr",
        choices=["iqr", "zscore", "isolation_forest"],
        help="异常检测算法（默认 iqr；isolation_forest 需 sklearn）",
    )
    # 合规与守门（v2 新增）
    parser.add_argument(
        "--allow-pii",
        action="store_true",
        help=(
            "显式放行 PII 守门（默认 false；CSV 含手机/身份证等列时 PIIDetectorGate "
            "会 BLOCK conclude，加这个 flag 才跳过守门）"
        ),
    )
    parser.add_argument(
        "--audit-log",
        default=None,
        help=(
            "合规审计日志路径（如 output/audit.jsonl）；"
            "传了就启用 AuditEventListener；--audit 模式下默认 output/<basename>.audit.jsonl"
        ),
    )
    # 预算控制（v2 新增）
    parser.add_argument(
        "--budget-llm-calls",
        type=int,
        default=None,
        help=(
            "agent 整个生命周期最多调 LLM 次数（默认 SDK 内置 120）；"
            "demo 推荐 15-30（数据审计任务不应超 30 次 LLM call）"
        ),
    )
    parser.add_argument(
        "--budget-walltime",
        type=int,
        default=None,
        help="agent 最大墙钟秒数（默认 SDK 内置 1800）；demo 推荐 180-300",
    )
    parser.add_argument(
        "--budget-replans",
        type=int,
        default=None,
        help="agent 最多 replan 次数（默认 SDK 内置 3）",
    )
    parser.add_argument("--reasoning-model", default=None, help="推理模型 ID（找不到自动 fallback）")
    parser.add_argument("--chat-model", default=None, help="对话模型 ID（找不到自动 fallback）")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("KROW_BASE_URL", "").strip() or None,
        help=(
            "自定义 cloud endpoint（仅 staging / 私有部署用；几乎所有用户不要改）。"
            " 默认走 https://api.krow.cn；可由 $KROW_BASE_URL 覆盖。"
        ),
    )
    parser.add_argument("--quiet", action="store_true", help="安静模式")
    args = parser.parse_args(argv)

    csv_path = Path(args.csv_path).expanduser().resolve()
    if not csv_path.exists():
        print(f"❌ CSV 不存在：{csv_path}", file=sys.stderr)
        return 1

    api_key = os.environ.get("KROW_API_KEY", "").strip()
    if not api_key:
        print(
            "❌ 未设 KROW_API_KEY 环境变量。\n"
            "   修法：\n"
            "     1. Windows: $env:KROW_API_KEY='sk-user-xxx'\n"
            "     2. Linux/Mac: export KROW_API_KEY=sk-user-xxx\n"
            "     3. 没 key？登录 krow 客户端 → Settings → API Keys → Generate",
            file=sys.stderr,
        )
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{csv_path.stem}_report.md"
    pdf_path = output_dir / f"{csv_path.stem}_report.pdf"

    audit_log_path: Path | None = None
    if args.audit_log:
        audit_log_path = Path(args.audit_log).expanduser().resolve()
    elif args.audit:
        audit_log_path = output_dir / f"{csv_path.stem}.audit.jsonl"

    project_root = csv_path.parent
    if output_dir.is_relative_to(Path.cwd()):
        project_root = Path.cwd()

    print(f"📊 正在审计 {csv_path}")
    print(f"   tier:     {'3 (合规)' if (args.audit and audit_log_path) else '2 (审计)' if args.audit else '1 (基础)'}")
    print(f"   markdown: {md_path}")
    if args.pdf:
        print(f"   pdf:      {pdf_path}")
    if audit_log_path:
        print(f"   audit:    {audit_log_path}")
    print()

    builder = (
        AgentBuilder()
        .with_krow_api_key(api_key)
        .with_project_root(project_root)
        .with_tool_plugin(DataAnalystToolPlugin())
        .with_act_plugin(DataAnalystACTPlugin())
        .with_event_listener_plugin(
            DataAnalystProgressListener(verbose=not args.quiet)
        )
    )

    if args.base_url:
        if not args.quiet:
            print(f"  🌐 cloud endpoint: {args.base_url}")
        builder = builder.with_base_url(args.base_url)

    # GatePlugin × 2（v2）：硬守门
    builder = builder.with_gate_plugin(PIIDetectorGate(allow_pii=args.allow_pii))
    builder = builder.with_gate_plugin(OutputPathGate(project_root=project_root))

    # HintPlugin（v2）：System 2 软提示
    builder = builder.with_hint_plugin(DataInsightHintPlugin())

    # AuditEventListener（v2）：合规日志
    if audit_log_path:
        builder = builder.with_event_listener_plugin(
            AuditEventListener(audit_log_path=audit_log_path)
        )

    # BudgetSpec（v2）：预算硬约束
    if any([args.budget_llm_calls, args.budget_walltime, args.budget_replans]):
        budget_kwargs: dict = {}
        if args.budget_llm_calls is not None:
            budget_kwargs["max_total_llm_calls"] = args.budget_llm_calls
        if args.budget_walltime is not None:
            budget_kwargs["max_walltime_s"] = args.budget_walltime
            budget_kwargs.setdefault("target_walltime_s", max(60, args.budget_walltime - 60))
        if args.budget_replans is not None:
            budget_kwargs["max_replans"] = args.budget_replans
        budget = BudgetSpec(**budget_kwargs)
        builder = builder.with_budget(budget)
        print(f"  💰 budget: {budget_kwargs}")

    if args.reasoning_model:
        print(f"  ⚙️  reasoning model: {args.reasoning_model}")
        builder = builder.with_reasoning_model(args.reasoning_model)
    if args.chat_model:
        print(f"  ⚙️  chat model:      {args.chat_model}")
        builder = builder.with_chat_model(args.chat_model)
    print()

    agent = builder.build()

    try:
        user_request_parts = [
            f"请读 CSV 文件 {csv_path}，对它做合规数据审计。",
            "步骤：",
            "1. data_analyst_read_csv 拿 metadata（注意 encoding fallback 提示；",
            "   如果 PIIDetectorGate BLOCK 了，告诉用户哪些列含 PII + 修法）",
            "2. data_analyst_compute_stats 算基础统计",
        ]
        if args.audit:
            user_request_parts.extend([
                f"3. data_analyst_detect_anomalies(method='{args.anomaly_method}') 检测异常行",
                "4. data_analyst_compute_correlation(method='pearson', top_n=5) 算相关性矩阵",
                "5. data_analyst_pick_palette 拿配色",
                "6. 基于以上数据 + 异常 + 相关性 + 配色写中文合规审计报告，6 段：",
                "   ① 数据概览 ② 数值统计 ③ 分类统计 ④ 异常审计 ⑤ 相关性洞察 ⑥ 合规建议",
                f"7. data_analyst_write_report 落盘到 {md_path}",
            ])
            next_step = 8
        else:
            user_request_parts.extend([
                "3. data_analyst_pick_palette 拿配色（数值用 sequential，分类用 categorical）",
                "4. 基于数据 + 配色写中文 markdown，5 段：",
                "   数据概览 / 数值列分析 / 分类列分析 / 数据质量 / 初步洞察",
                f"5. data_analyst_write_report 落盘到 {md_path}",
            ])
            next_step = 6
        if args.pdf:
            user_request_parts.append(
                f"{next_step}. word_smart_export(file_path={md_path}, format='pdf', "
                f"output_path={pdf_path}) 把 markdown 转 PDF"
                "（reportlab 缺失则报告 markdown-only 降级）"
            )
        user_request = "\n".join(user_request_parts)

        result = agent.run(user_request)
        if not result.success:
            print(f"\n❌ 任务执行失败：{result.final_output}", file=sys.stderr)
            return 1
        print(f"\n📝 markdown 报告：{md_path}")
        if args.pdf and pdf_path.exists():
            print(f"📄 PDF 报告：{pdf_path}")
        elif args.pdf:
            print("⚠️  PDF 未生成（reportlab 缺失？查 agent log 看降级原因）")
        if audit_log_path and audit_log_path.exists():
            line_count = sum(1 for _ in audit_log_path.open("r", encoding="utf-8"))
            print(f"📋 审计日志：{audit_log_path}（{line_count} 条记录）")
        return 0
    finally:
        agent.shutdown()


if __name__ == "__main__":
    sys.exit(main())
