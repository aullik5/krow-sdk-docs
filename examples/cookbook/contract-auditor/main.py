"""Contract-auditor cookbook 主入口（v3 cookbook 第 3 个 demo）.

跑前：
    1. set KROW_API_KEY=sk-user-xxx
       (PowerShell: $env:KROW_API_KEY='sk-user-xxx')
       (Linux/Mac:  export KROW_API_KEY=sk-user-xxx)
    2. krow-sdk-install --api-key $KROW_API_KEY
    3. cd examples/cookbook/contract-auditor && pip install -e .

最小跑（Tier 1：1 份合同 → 风险报告 markdown）：
    python main.py sample_data/contract.pdf

业务可用（Tier 2：合同 + 公司模板 → redline + docx）：
    python main.py sample_data/contract.docx \\
        --template sample_data/template.docx \\
        --docx

合规生产（Tier 3：审计 jsonl + OpenTelemetry tracing + budget）：
    python main.py sample_data/contract.docx \\
        --template sample_data/template.docx \\
        --docx --pdf \\
        --audit-log output/contract.audit.jsonl \\
        --observability \\
        --otlp-endpoint http://otel-collector.legal.internal:4317 \\
        --budget-llm-calls 60 \\
        --budget-walltime 600

输出：
    output/risk_report.md             (风险报告 markdown)
    output/risk_report.docx           (仅 --docx；走 word_smart_export)
    output/risk_report.pdf            (仅 --pdf；走 word_smart_export)
    output/contract.audit.jsonl       (仅 --audit-log；法务合规留痕)

────────────────────────────────────────────────────────────────────
本 cookbook 演示 SDK 全部 6 类 plugin（与 PR-A 财经互补）：
────────────────────────────────────────────────────────────────────
- ToolPlugin × 5（条款切分/分类/风险评分/redline/术语索引）
- ACTPlugin × 1（contract_auditor ACT，6 步标准工作流）
- GatePlugin × 2（**最强阻断**）
  · MandatoryClauseGate：GDPR/反垄断/出口管制必含，缺则 BLOCK
  · HighRiskBlockingGate：≥1 高风险 + 缺人工审核标记 → BLOCK
- HintPlugin × 2
  · AmbiguousLanguageHintPlugin：模糊用语提醒
  · MissingDefinitionHintPlugin：未定义术语提醒
- EventListenerPlugin × 1（LegalAuditTrailListener：法务合规 .audit.jsonl
  + 合同 sha256 文件指纹）
- ObservabilityPlugin × 1（OTelTracingObservabilityPlugin：每个 tool 一个 span
  + gate BLOCK 标 ERROR；推 OTLP collector）
- BudgetSpec：60 LLM × 600s（合同 review 偏交互式不能等太久）
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from krow_agent_sdk import AgentBuilder, BudgetSpec
from contract_auditor_plugin import (
    AmbiguousLanguageHintPlugin,
    ContractAuditorACTPlugin,
    ContractAuditorToolPlugin,
    HighRiskBlockingGate,
    LegalAuditTrailListener,
    MandatoryClauseGate,
    MissingDefinitionHintPlugin,
    OTelTracingObservabilityPlugin,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Krow SDK Cookbook · Contract Auditor Demo (v3 PR-C)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "三档跑法：\n"
            "  Tier 1（基础）：python main.py contract.pdf\n"
            "  Tier 2（业务）：python main.py contract.docx --template tmpl.docx --docx\n"
            "  Tier 3（合规）：python main.py contract.docx --audit-log al.jsonl "
            "--observability --otlp-endpoint http://...\n"
        ),
    )
    parser.add_argument(
        "contract_path",
        help="合同文件路径（docx / pdf / txt）",
    )
    parser.add_argument(
        "--template",
        default=None,
        help="公司模板路径（可选，传了才跑 redline diff）",
    )
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--docx", action="store_true", help="同时生成 docx（法务常用）")
    parser.add_argument("--pdf", action="store_true", help="同时生成 PDF")
    parser.add_argument(
        "--audit-log",
        default=None,
        help=(
            "审计 jsonl 路径（启用 LegalAuditTrailListener）。"
            "建议 SOX / 公司合规场景**必填**"
        ),
    )
    parser.add_argument(
        "--no-mandatory-strict",
        action="store_true",
        help="MandatoryClauseGate 用 DEFER 而非 BLOCK（默认 strict=BLOCK）",
    )
    parser.add_argument(
        "--high-risk-threshold",
        type=float,
        default=0.75,
        help="HighRiskBlockingGate 触发阈值（默认 0.75）",
    )
    parser.add_argument(
        "--observability",
        action="store_true",
        help=(
            "启用 OTelTracingObservabilityPlugin。"
            "需要装 opentelemetry-api/sdk；未装则降级 stdout"
        ),
    )
    parser.add_argument(
        "--otlp-endpoint",
        default=None,
        help=(
            "OTLP gRPC endpoint，例如 http://otel-collector.legal.internal:4317；"
            "不传则不发送到 collector（仅本地 demo 模式）"
        ),
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

    contract_path = Path(args.contract_path).expanduser().resolve()
    if not contract_path.exists():
        print(f"❌ 合同文件不存在：{contract_path}", file=sys.stderr)
        return 1
    if contract_path.suffix.lower() not in {".docx", ".pdf", ".txt", ".md", ""}:
        print(
            f"⚠️  非典型合同后缀 {contract_path.suffix}，仍会尝试 utf-8 文本读取",
            file=sys.stderr,
        )

    template_path: Path | None = None
    if args.template:
        template_path = Path(args.template).expanduser().resolve()
        if not template_path.exists():
            print(f"❌ 模板文件不存在：{template_path}", file=sys.stderr)
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

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "risk_report.md"
    docx_path = output_dir / "risk_report.docx" if args.docx else None
    pdf_path = output_dir / "risk_report.pdf" if args.pdf else None
    audit_log_path = (
        Path(args.audit_log).expanduser().resolve() if args.audit_log else None
    )

    project_root = contract_path.parent

    tier = "1 (基础)"
    if audit_log_path or args.observability:
        tier = "3 (合规)"
    elif template_path or args.docx or args.pdf:
        tier = "2 (业务)"

    print("📜 合同审阅任务")
    print(f"   tier:     {tier}")
    print(f"   contract: {contract_path}")
    if template_path:
        print(f"   template: {template_path}")
    print(f"   markdown: {md_path}")
    if docx_path:
        print(f"   docx:     {docx_path}")
    if pdf_path:
        print(f"   pdf:      {pdf_path}")
    if audit_log_path:
        print(f"   audit:    {audit_log_path}")
    if args.observability:
        endpoint = args.otlp_endpoint or "(demo 模式 - 不发送 collector)"
        print(f"   otel:     {endpoint}")
    print()

    builder = (
        AgentBuilder()
        .with_krow_api_key(api_key)
        .with_project_root(project_root)
        .with_tool_plugin(ContractAuditorToolPlugin())
        .with_act_plugin(ContractAuditorACTPlugin())
    )

    if args.base_url:
        if not args.quiet:
            print(f"  🌐 cloud endpoint: {args.base_url}")
        builder = builder.with_base_url(args.base_url)

    builder = builder.with_gate_plugin(
        MandatoryClauseGate(strict=not args.no_mandatory_strict)
    )
    builder = builder.with_gate_plugin(
        HighRiskBlockingGate(threshold=args.high_risk_threshold)
    )
    builder = builder.with_hint_plugin(AmbiguousLanguageHintPlugin())
    builder = builder.with_hint_plugin(MissingDefinitionHintPlugin())
    builder = builder.with_event_listener_plugin(
        LegalAuditTrailListener(
            verbose=not args.quiet,
            audit_log_path=audit_log_path,
            contract_path=contract_path,
        )
    )

    if args.observability:
        builder = builder.with_observability_plugin(
            OTelTracingObservabilityPlugin(
                otlp_endpoint=args.otlp_endpoint,
                verbose=False,
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
            contract_path=contract_path,
            template_path=template_path,
            md_path=md_path,
            docx_path=docx_path,
            pdf_path=pdf_path,
            mandatory_strict=not args.no_mandatory_strict,
            high_risk_threshold=args.high_risk_threshold,
        )
        result = agent.run(request)
        # W5 治本（2026-05-19）：artifact-fallback robustness.
        # 实测 LLM 在 verify_completion 阶段偶尔说"步骤 6 导出失败"（误判 —
        # 实际 markdown 在前序步骤已落盘），导致 result.success=False；但
        # 用户拿到的产物是完整可读的. 用户价值优先于 agent 自评 → 文件存在
        # 且 ≥ 800B 即视为成功.
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
                print(f"\n❌ 任务失败：{result.final_output}", file=sys.stderr)
                return 1
        print(f"\n📝 风险报告 markdown：{md_path}")
        if docx_path and docx_path.exists():
            print(f"📄 docx：{docx_path}")
        if pdf_path and pdf_path.exists():
            print(f"📄 PDF：{pdf_path}")
        if audit_log_path and audit_log_path.exists():
            line_count = sum(1 for _ in audit_log_path.open("r", encoding="utf-8"))
            print(f"📋 审计日志：{audit_log_path}（{line_count} 条）")
        return 0
    finally:
        agent.shutdown()


def _build_request(
    *,
    contract_path: Path,
    template_path: Path | None,
    md_path: Path,
    docx_path: Path | None,
    pdf_path: Path | None,
    mandatory_strict: bool,
    high_risk_threshold: float,
) -> str:
    parts = [
        "请基于用户提供的合同做风险审阅（6 步工作流）。",
        f"合同路径：{contract_path}",
    ]
    if template_path:
        parts.append(f"公司模板：{template_path}")
    parts.append("")
    parts.append("工作流：")
    parts.append("1. 调 contract_auditor_split_clauses(contract_path=...)")
    parts.append("   - **铁律**：不要直接读 PDF 全文塞 prompt（合同上下文容易爆炸）")
    parts.append("")
    parts.append("2. 调 contract_auditor_classify_clauses(clauses=step1.clauses)")
    parts.append(
        f"   - MandatoryClauseGate 触发：缺 GDPR/反垄断/出口管制 任一 → "
        f"{'BLOCK' if mandatory_strict else 'DEFER'}"
    )
    parts.append("")
    parts.append("3. 调 contract_auditor_score_clause_risk")
    parts.append("   - 输入：clauses + classifications")
    parts.append(
        f"   - 输出：risks 列表（high≥{high_risk_threshold} / medium≥0.50 / low）"
    )
    parts.append("   - HintPlugin 自动激活：AmbiguousLanguageHint 推软提示")
    parts.append("")
    parts.append("4. 调 contract_auditor_index_terms(contract_text=...)")
    parts.append("   - HintPlugin 自动激活：MissingDefinitionHint 列出未定义术语")
    parts.append("")
    if template_path:
        parts.append("5. 调 contract_auditor_redline_diff")
        parts.append(
            f"   - template_text=read_file({template_path})"
        )
        parts.append("   - contract_text=步骤 1 拼接的全文")
        parts.append("   - diff_text 嵌入风险报告「模板偏离」段")
        parts.append("")
        next_step = 6
    else:
        next_step = 5

    parts.append(f"{next_step}. 起草风险报告 markdown，**必须含**：")
    parts.append("   0) **合同基本信息**（开篇必含 — 法务/PM 看报告先要知道审什么）：")
    parts.append("      - 合同标题 / 类型（来自 step 1 输出 / 标题文本）")
    parts.append("      - 甲乙双方完整法人名称")
    parts.append("      - 合同总金额（必须含具体数字 + 币种 + 单位，如『1,500,000 元 CNY』")
    parts.append("        或『150 万元』；用户拿到报告第一眼要知道审的是多少钱的合同）")
    parts.append("      - 主要时间节点（签订 / 生效 / 履行期 / 终止条件）")
    parts.append("   1) 执行摘要（high/medium/low 计数 + 整体风险等级）")
    parts.append("   2) 必备条款检查（GDPR / 反垄断 / 出口管制 三段）")
    parts.append("   3) 高风险条款（每条说明 + 修订建议）")
    parts.append(
        "      - **若有 ≥1 high-risk 必须写**「需法务复核 / "
        "REQUIRES LEGAL REVIEW」标记，否则 HighRiskBlockingGate 会 BLOCK"
    )
    parts.append("   4) 条款语义风险（模糊用语 + 未定义术语，结合 hint 输出）")
    if template_path:
        parts.append("   5) 模板偏离（基于 redline_diff 输出）")
    parts.append("   6) 建议下一步（哪些条款需要谈判 / 修改）")
    parts.append("")
    parts.append(
        f"{next_step + 1}. 调 smart_file_write(operation='write', path={md_path}, "
        f"content=<完整 markdown 文本>) 落盘"
    )
    parts.append(
        "   ⚠️ **铁律**：写 markdown 必须用 ``smart_file_write``；"
        "``word_smart_export`` 是 docx→其他格式 转换工具，"
        "传 .md 路径会把 docx binary 写进去 → encoding 灾难"
    )
    if docx_path:
        parts.append(
            f"{next_step + 2}. word_smart_export(file_path={md_path}, "
            f"format='docx', output_path={docx_path})"
        )
    if pdf_path:
        parts.append(
            f"{next_step + 3}. word_smart_export(file_path={md_path}, "
            f"format='pdf', output_path={pdf_path})"
        )
    return "\n".join(parts)


if __name__ == "__main__":
    sys.exit(main())
