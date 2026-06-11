"""HITL-assistant cookbook 主入口：CAD 参数变更助手（human-in-the-loop demo）.

跑前：
    1. set KROW_API_KEY=sk-user-xxx
       (PowerShell: $env:KROW_API_KEY='sk-user-xxx')
       (Linux/Mac:  export KROW_API_KEY=sk-user-xxx)
    2. krow-sdk-install --api-key $KROW_API_KEY  # 装私有 runtime
    3. cd examples/cookbook/hitl-assistant && pip install -e .

交互式跑（agent 挂起时在终端里答复，支持附图）：
    python main.py "把泵的出口直径改大一点"

跨进程续跑（demo durable checkpoint：挂起后 Ctrl+C 杀掉进程，再）：
    python main.py --resume <resume_token> "按工程师的答复继续"

查 / 取消断点：
    python main.py --list-checkpoints
    python main.py --cancel <resume_token>

答复语法（挂起后的 stdin 提示符里）：
    直接打字                  → 纯文本答复
    任意文本 img:截图.png     → 文本 + 附图（可多个 img:）
    任意文本 file:规格书.pdf  → 文本 + 附文件

教学点（对照 docs/sdk/api-reference.md §3.5）：
    1. ``with_hitl(confirm_before_tools=[...])`` —— System 1 强制确认门：
       LLM 在计划步骤里要调 ``cad_apply_param_change`` 之前框架必停，
       不依赖 LLM 自觉（参数改错 = 数小时仿真白跑）。
    2. ``allow_llm_questions=True`` —— LLM 信息不足时自主调
       ``request_human_input`` 发问（如"出口直径改到多少？"）。
    3. ``result.suspended / result.suspension["resume_token"]`` —— 挂起语义。
    4. ``agent.resume(token, {"text":..., "images":[...]})`` —— 多模态续跑；
       checkpoint 落 SQLite，进程重启后凭 token 依然能续。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from hitl_assistant_plugin import (
    HitlAssistantACTPlugin,
    HitlAssistantToolPlugin,
)
from krow_agent_sdk import AgentBuilder

COOKBOOK_DIR = Path(__file__).resolve().parent
DEFAULT_PARAMS = COOKBOOK_DIR / "sample_data" / "design_params.json"


def _parse_human_reply(raw: str) -> dict:
    """终端答复 → HumanInput dict（``img:`` / ``file:`` 前缀抽附件）."""
    words = raw.strip().split()
    images = [w[4:] for w in words if w.startswith("img:")]
    files = [w[5:] for w in words if w.startswith("file:")]
    text = " ".join(
        w for w in words if not w.startswith(("img:", "file:"))
    )
    out: dict = {"text": text or raw.strip()}
    if images:
        out["images"] = images
    if files:
        out["files"] = files
    return out


def _build_agent(params_file: Path, base_url: str | None = None):
    builder = (
        AgentBuilder()
        .with_workspace(str(COOKBOOK_DIR / "output"))
        .with_plugin(HitlAssistantToolPlugin())
        .with_plugin(HitlAssistantACTPlugin())
        # HITL 三件套：LLM 自主发问 + 高代价工具强制确认门 + 防滥用护栏
        .with_hitl(
            confirm_before_tools=["cad_apply_param_change"],
            allow_llm_questions=True,
            max_suspensions=5,
        )
    )
    if base_url:
        builder = builder.with_base_url(base_url)
    return builder.build()


def _interactive_loop(agent, result) -> int:
    """挂起 → 终端问答 → resume，循环到任务完结。"""
    rounds = 0
    while getattr(result, "suspended", False):
        rounds += 1
        susp = result.suspension or {}
        print("\n" + "=" * 60)
        print(f"⏸  Agent 第 {rounds} 次挂起，等你答复")
        print(f"   问题：{susp.get('question', '(无问题文本)')}")
        print(f"   resume_token：{susp.get('resume_token')}")
        print("   （此刻 Ctrl+C 退出也不丢：之后可用 --resume <token> 续跑）")
        print("=" * 60)
        try:
            raw = input("你的答复（可带 img:xx.png / file:xx.pdf）> ")
        except (EOFError, KeyboardInterrupt):
            print("\n已退出；断点仍在，可用 --resume 续跑。")
            return 0
        result = agent.resume(
            susp.get("resume_token"), _parse_human_reply(raw),
        )

    print("\n" + "=" * 60)
    if getattr(result, "success", False):
        print(f"✅ 任务完成（人机往返 {rounds} 轮）")
    else:
        print("⚠️ 任务结束但未标记 success，请检查输出")
    print(f"   {getattr(result, 'final_output', '')[:500]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Krow SDK Cookbook · HITL CAD 参数变更助手",
    )
    parser.add_argument("goal", nargs="?", help="给 agent 的任务（自然语言）")
    parser.add_argument(
        "--params-file", default=str(DEFAULT_PARAMS),
        help="设计参数表 JSON（默认 sample_data/design_params.json）",
    )
    parser.add_argument(
        "--resume", default=None, metavar="TOKEN",
        help="跨进程续跑：传上次挂起的 resume_token（goal 作为答复文本）",
    )
    parser.add_argument(
        "--list-checkpoints", action="store_true", help="列出现存断点",
    )
    parser.add_argument(
        "--cancel", default=None, metavar="TOKEN", help="取消一个断点",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("KROW_BASE_URL", "").strip() or None,
        help=(
            "Krow Cloud endpoint（私有化部署 / 海外网关时传）；"
            "默认走 https://api.krow.cn；可由 $KROW_BASE_URL 覆盖。"
        ),
    )
    args = parser.parse_args(argv)

    if not os.environ.get("KROW_API_KEY"):
        print("⚠️ 未设 KROW_API_KEY；真实跑 agent 需要先登录 / 设 key")

    agent = _build_agent(Path(args.params_file), base_url=args.base_url)
    try:
        if args.list_checkpoints:
            cps = agent.list_checkpoints(session_id="")
            print(f"现存断点 {len(cps)} 个：")
            for cp in cps:
                print(f"  - {cp}")
            return 0
        if args.cancel:
            agent.cancel_checkpoint(args.cancel)
            print(f"已取消断点：{args.cancel}")
            return 0

        if args.resume:
            if not args.goal:
                print("❌ --resume 需要把答复文本作为 goal 参数传入")
                return 2
            result = agent.resume(args.resume, _parse_human_reply(args.goal))
            return _interactive_loop(agent, result)

        if not args.goal:
            parser.print_help()
            return 2

        goal = (
            f"{args.goal}\n\n"
            f"设计参数表：{Path(args.params_file).resolve()}\n"
            "约束：改参数前必须先读参数表确认参数名与当前值；"
            "信息不足（比如不知道改到多少）就先问工程师，不要瞎猜。"
        )
        print(f"▶ 启动任务：{args.goal}")
        result = agent.run(goal)
        return _interactive_loop(agent, result)
    finally:
        agent.shutdown()


if __name__ == "__main__":
    sys.exit(main())
