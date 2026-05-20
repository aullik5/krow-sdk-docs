"""Financial-analyst cookbook 主入口（v3 cookbook 第 1 个 demo）.

跑前：
    1. set KROW_API_KEY=sk-user-xxx
       (PowerShell: $env:KROW_API_KEY='sk-user-xxx')
       (Linux/Mac:  export KROW_API_KEY=sk-user-xxx)
    2. krow-sdk-install --api-key $KROW_API_KEY  # 装私有 runtime
    3. cd examples/cookbook/financial-analyst && pip install -e .[obs]

最小跑（Tier 1：单文件 KPI 抽取 → 简短 markdown）：
    python main.py sample_data/company_a_2024.pdf --company "公司A"

横向对比跑（Tier 2：3 家公司 + 雷达图 + 行业基线）：
    python main.py sample_data/*.pdf --output-dir output --pdf

全功能跑（Tier 3：合规守门 + 审计 + Prometheus + 估值锚）：
    python main.py sample_data/*.pdf \\
        --pdf \\
        --audit-log output/memo.audit.jsonl \\
        --observability \\
        --budget-llm-calls 80 \\
        --budget-walltime 900 \\
        --target-currency CNY --target-unit 亿

输出：
    output/investment_memo.md
    output/investment_memo.pdf       (仅 --pdf；走 word_smart_export)
    output/radar_chart.svg           (雷达图 SVG)
    output/<basename>.audit.jsonl    (合规审计日志)

────────────────────────────────────────────────────────────────────
本 cookbook 演示 SDK 全部插件类型（与 v2 data-analyst 互补）：
────────────────────────────────────────────────────────────────────
- ToolPlugin × 5（KPI 抽取 / 归一化 / 行业基线 / 雷达图 / 估值锚）
- ACTPlugin × 1（financial_analyst ACT，8 步标准工作流）
- GatePlugin × 2
  · DisclosureCompletenessGate：投资简报必须含 5 段标准披露
  · InsiderInfoGate：禁止简报含"内幕 / 未公开 / MNPI"等关键词
- HintPlugin × 1（AnomalyMetricHint：3σ 偏差 KPI 自动标注亮点 / 风险）
- EventListenerPlugin × 1（InvestmentMemoAuditListener：审计 + Gate BLOCK 留痕）
- ObservabilityPlugin × 1（FinancialMetricsObservabilityPlugin：Prometheus 集成）
- BudgetSpec（5 公司任务推荐 80 LLM × 900s × 2 replan）

PDF 输出策略（SSOT 复用，与 v2 一致）：
- 不引第三方 PDF 库（不用 fpdf2 / reportlab）
- 调 Krow 内置 ``word_smart_export(format="pdf")``
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from financial_analyst_plugin import (
    AnomalyMetricHintPlugin,
    DisclosureCompletenessGate,
    FinancialAnalystACTPlugin,
    FinancialAnalystToolPlugin,
    FinancialMetricsObservabilityPlugin,
    InsiderInfoGate,
    InvestmentMemoAuditListener,
)
from krow_agent_sdk import AgentBuilder, BudgetSpec


def _build_user_request(
    *,
    pdf_paths: list[Path],
    md_path: Path,
    pdf_path: Path | None,
    radar_svg_path: Path,
    target_currency: str,
    target_unit: str,
    company_names: list[str] | None,
    enable_valuation: bool,
) -> str:
    """构造 LLM 任务 prompt（按 ext_financial_analyst.md §推荐工作流 8 步）."""
    pdf_list = "、".join(str(p) for p in pdf_paths)
    names_hint = (
        "用户提供的公司名（按 PDF 顺序）：" + "、".join(company_names) + "\n"
        if company_names else
        "公司名按 PDF 文件名 stem 自动推断。\n"
    )
    parts = [
        "请基于用户提供的 N 家上市公司年报 PDF 做行业横向对比分析 + 写投资简报。",
        f"PDF 列表：{pdf_list}",
        names_hint,
        "请按以下 8 步工作流：",
        "",
        "1. 对**每个**年报 PDF 调 financial_analyst_extract_kpi_from_pdf 抽 KPI",
        "   - 注意 missed 列表（缺哪些 KPI）",
        "   - 抽完后 LLM 看 dict 返回值就够，不要再读 PDF 全文塞 prompt",
        "",
        "2. 调 financial_analyst_normalize_kpi_table 把所有公司 KPI 拉平到同口径",
        f"   - target_currency={target_currency}, target_unit={target_unit}",
        "   - 输入：companies=[{'company':..., 'kpis':...}, ...]（用 step 1 输出）",
        "   - 注意 period_warnings（期数不齐警告）",
        "",
        "3. 调 financial_analyst_industry_baseline 算行业基线",
        "   - 输入：normalized_table=step 2 的 table 字段",
        "   - 完成后 HintPlugin 自动激活，把 ≥2σ 偏差信号推给 LLM",
        "   - LLM 应在简报『财务表现 / 投资建议』段引用这些信号",
        "",
        "4. 调 financial_analyst_radar_chart_svg 生成雷达图",
        "   - kpi_ids 建议选 5-8 个核心维度",
        "     (revenue/net_profit/gross_margin/roe/operating_cash_flow)",
        f"   - 把 svg 字段写到 {radar_svg_path}",
        "",
    ]
    if enable_valuation:
        parts.extend([
            "5. **对每家公司**分别调一次 financial_analyst_valuation_anchor",
            "   - 必须传 market_cap（如年报中市值未披露，用合理估算 + 在简报里标注假设）",
            "   - 必须传 net_profit（来自 step 1）",
            "   - 选传 book_value（total_equity）/ revenue 启用 PB / PS",
            "   - 选传 industry_pe_median / industry_pb_median（来自 step 3 baselines）",
            "",
        ])
    next_step = 6 if enable_valuation else 5
    parts.extend([
        f"{next_step}. 基于 KPI 表 + 行业基线 + 偏差信号 + 雷达图 + 估值锚写中文投资简报：",
        "   **5 段标准披露结构**（DisclosureCompletenessGate 守门）：",
        "   ① 业务概览 ② 财务表现 ③ 行业地位 ④ 风险因素 ⑤ 投资建议",
        "   **铁律**：禁止使用『内幕 / 未公开 / 尚未披露 / MNPI』等关键词",
        "   （InsiderInfoGate 会 BLOCK；只用年报已公开数据）",
        f"   写完 markdown 调 smart_file_write(operation='write', path={md_path}, "
        "content=<完整 markdown 文本>) 落盘",
        "   ⚠️ **铁律**：写 markdown 必须用 ``smart_file_write``；",
        "   ``word_smart_export`` 是 docx→其他格式 转换工具，不是写新 .md 文件",
    ])
    if pdf_path:
        parts.extend([
            f"{next_step + 1}. 把 markdown 渲染为 PDF：",
            f"   word_smart_export(file_path={md_path}, format='pdf', output_path={pdf_path})",
            "   （reportlab 缺失 → markdown-only 降级；继续不阻塞）",
        ])
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Krow SDK Cookbook · Financial Analyst Demo (v3)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "三档跑法（按需启用 SDK 高级能力）：\n"
            "  Tier 1（基础）  ：python main.py company_a.pdf\n"
            "  Tier 2（对比）  ：python main.py *.pdf --pdf\n"
            "  Tier 3（合规）  ：python main.py *.pdf --pdf "
            "--audit-log out/audit.jsonl --observability\n"
        ),
    )
    parser.add_argument(
        "pdf_paths",
        nargs="+",
        help="一个或多个年报 PDF 文件路径（多个时自动横向对比）",
    )
    parser.add_argument("--output-dir", default="output", help="输出目录（默认 ./output）")
    parser.add_argument(
        "--company-names",
        nargs="*",
        help="公司名（数量需与 PDF 数一致；不传则用文件名 stem）",
    )
    parser.add_argument(
        "--target-currency",
        default="CNY",
        choices=["CNY", "USD", "EUR", "HKD", "JPY"],
        help="归一化目标币种（默认 CNY）",
    )
    parser.add_argument(
        "--target-unit",
        default="亿",
        help="归一化目标单位（亿 / 百万 / 万 / 元；默认 亿）",
    )
    parser.add_argument("--pdf", action="store_true", help="同时生成 PDF（走 word_smart_export）")
    parser.add_argument(
        "--no-valuation",
        action="store_true",
        help="跳过估值锚（valuation_anchor 工具）—— 没有 market_cap 数据时启用",
    )
    parser.add_argument(
        "--audit-log",
        default=None,
        help="合规审计日志路径（如 output/memo.audit.jsonl）；启用 InvestmentMemoAuditListener",
    )
    parser.add_argument(
        "--observability",
        action="store_true",
        help=(
            "启用 ObservabilityPlugin（默认走 stdout 模式；"
            "--prometheus-url 启用真实 push gateway）"
        ),
    )
    parser.add_argument(
        "--prometheus-url",
        default=None,
        help="Prometheus push gateway URL（None → stdout demo 模式）",
    )
    parser.add_argument(
        "--no-strict-disclosure",
        action="store_true",
        help="DisclosureCompletenessGate 退化为 warn-only（默认 strict 阻断）",
    )
    # 预算控制
    parser.add_argument(
        "--budget-llm-calls",
        type=int,
        default=None,
        help="agent 整个生命周期最多调 LLM 次数（默认 SDK 内置 120；推荐 80）",
    )
    parser.add_argument(
        "--budget-walltime",
        type=int,
        default=None,
        help="agent 最大墙钟秒数（默认 SDK 内置 1800；推荐 900）",
    )
    parser.add_argument(
        "--budget-replans",
        type=int,
        default=None,
        help="agent 最多 replan 次数（默认 SDK 内置 3；推荐 2）",
    )
    parser.add_argument("--reasoning-model", default=None, help="推理模型 ID")
    parser.add_argument("--chat-model", default=None, help="对话模型 ID")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("KROW_BASE_URL", "").strip() or None,
        help=(
            "自定义 cloud endpoint（仅 staging / 私有部署用；几乎所有用户不要改）。"
            " 默认走 https://api.krow.cn；可由 $KROW_BASE_URL 覆盖。"
            " 例：--base-url https://api-staging.krow.cn"
        ),
    )
    parser.add_argument("--quiet", action="store_true", help="安静模式")
    args = parser.parse_args(argv)

    pdf_paths: list[Path] = []
    for raw in args.pdf_paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print(f"❌ PDF 不存在：{p}", file=sys.stderr)
            return 1
        if p.suffix.lower() != ".pdf":
            print(f"❌ 非 PDF 文件：{p.suffix}", file=sys.stderr)
            return 1
        pdf_paths.append(p)
    if args.company_names and len(args.company_names) != len(pdf_paths):
        print(
            f"❌ --company-names 数量 {len(args.company_names)} 与 PDF 数 {len(pdf_paths)} 不一致",
            file=sys.stderr,
        )
        return 1

    api_key = os.environ.get("KROW_API_KEY", "").strip()
    if not api_key:
        print(
            "❌ 未设 KROW_API_KEY 环境变量。\n"
            "   修法：\n"
            "     1. Windows: $env:KROW_API_KEY='sk-user-xxx'\n"
            "     2. Linux/Mac: export KROW_API_KEY=sk-user-xxx\n"
            "     3. 没 key？登录 krow 客户端 → Settings → API Keys",
            file=sys.stderr,
        )
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "investment_memo.md"
    pdf_path = output_dir / "investment_memo.pdf" if args.pdf else None
    radar_svg_path = output_dir / "radar_chart.svg"
    audit_log_path: Path | None = (
        Path(args.audit_log).expanduser().resolve() if args.audit_log else None
    )

    project_root = Path.cwd()
    if pdf_paths and pdf_paths[0].parent.is_dir():
        project_root = pdf_paths[0].parent
    if output_dir.is_relative_to(Path.cwd()):
        project_root = Path.cwd()

    tier = "1 (基础)"
    if len(pdf_paths) > 1 and args.pdf:
        tier = "2 (对比 + PDF)"
    if audit_log_path or args.observability:
        tier = "3 (合规)"
    print("📊 财经分析任务")
    print(f"   tier:     {tier}")
    print(f"   公司数:   {len(pdf_paths)}")
    print(f"   markdown: {md_path}")
    print(f"   雷达图:   {radar_svg_path}")
    if pdf_path:
        print(f"   pdf:      {pdf_path}")
    if audit_log_path:
        print(f"   audit:    {audit_log_path}")
    if args.observability:
        obs_dest = (
            "push_gateway=" + args.prometheus_url
            if args.prometheus_url else "stdout demo"
        )
        print(f"   obs:      {obs_dest}")
    print()

    builder = (
        AgentBuilder()
        .with_krow_api_key(api_key)
        .with_project_root(project_root)
        .with_tool_plugin(FinancialAnalystToolPlugin())
        .with_act_plugin(FinancialAnalystACTPlugin())
    )

    if args.base_url:
        if not args.quiet:
            print(f"  🌐 cloud endpoint: {args.base_url}")
        builder = builder.with_base_url(args.base_url)

    # GatePlugin × 2：合规硬阻
    builder = builder.with_gate_plugin(
        DisclosureCompletenessGate(strict=not args.no_strict_disclosure)
    )
    builder = builder.with_gate_plugin(InsiderInfoGate())

    # HintPlugin：3σ 偏差软提示
    builder = builder.with_hint_plugin(AnomalyMetricHintPlugin(sigma_threshold=2.0))

    # EventListenerPlugin：合规审计留痕
    if audit_log_path:
        builder = builder.with_event_listener_plugin(
            InvestmentMemoAuditListener(audit_log_path=audit_log_path)
        )

    # ObservabilityPlugin：Prometheus 集成
    if args.observability:
        builder = builder.with_observability_plugin(
            FinancialMetricsObservabilityPlugin(
                push_gateway_url=args.prometheus_url,
                verbose=not args.quiet,
            )
        )

    # BudgetSpec：预算硬约束
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
        user_request = _build_user_request(
            pdf_paths=pdf_paths,
            md_path=md_path,
            pdf_path=pdf_path,
            radar_svg_path=radar_svg_path,
            target_currency=args.target_currency,
            target_unit=args.target_unit,
            company_names=args.company_names,
            enable_valuation=not args.no_valuation,
        )
        result = agent.run(user_request)
        # W5 治本（2026-05-19）：artifact-fallback robustness（与 contract-auditor 对齐）.
        # 实测 LLM 在 verify_completion 阶段偶尔报"工具调用失败"（误判 — 实际
        # markdown 在前序 smart_file_write 步骤已落盘）→ result.success=False；
        # 但用户拿到的产物是完整可读的 → 用户价值优先于 agent 自评.
        # 阈值 800B = expected_card 最低产物 size.
        artifact_ok = md_path.exists() and md_path.stat().st_size >= 800
        if not result.success:
            if artifact_ok:
                print(
                    f"\n⚠️  agent 自评失败但 markdown 已落盘 → 视为成功"
                    f"（{md_path.stat().st_size}B; agent_msg: "
                    f"{(result.final_output or '')[:200]}）",
                    file=sys.stderr,
                )
            else:
                print(f"\n❌ 任务执行失败：{result.final_output}", file=sys.stderr)
                return 1
        print(f"\n📝 投资简报：{md_path}")
        if pdf_path and pdf_path.exists():
            print(f"📄 PDF 报告：{pdf_path}")
        elif pdf_path:
            print("⚠️  PDF 未生成（reportlab 缺失？查 agent log）")
        if radar_svg_path.exists():
            print(f"🎯 雷达图：{radar_svg_path}")
        if audit_log_path and audit_log_path.exists():
            line_count = sum(1 for _ in audit_log_path.open("r", encoding="utf-8"))
            print(f"📋 审计日志：{audit_log_path}（{line_count} 条记录）")
        return 0
    finally:
        agent.shutdown()


if __name__ == "__main__":
    sys.exit(main())
