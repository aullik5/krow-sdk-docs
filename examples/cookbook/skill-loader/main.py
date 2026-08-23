"""Krow SDK Cookbook · 用 markdown 扩展 agent，不写 Python。

这个 demo 装载 ``skills/`` 下的两个 ``SKILL.md``，打印它们被翻译成了什么，
然后（可选）跑一次真实任务。

装载入口只有一个：``with_skill_directory(path)``。没有 env 开关 —— **写下这行调用
就是同意**，不写就一个 skill 都不会被装（与 ``with_act_plugin`` 同一口径）。

运行：

    export KROW_API_KEY=sk-user-xxx
    python main.py --dry-run              # 只看翻译结果，不建 agent
    python main.py                        # 建 agent（需要 runtime）
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SKILLS_DIR = HERE / "skills"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="外部 SKILL.md 装载 demo")
    parser.add_argument(
        "--skills-dir",
        default=str(DEFAULT_SKILLS_DIR),
        help="含 SKILL.md 子目录的父目录（默认：本 demo 自带的 skills/）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只翻译并打印报告，不构建 agent（不需要 runtime / API key）",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("KROW_BASE_URL", "").strip() or None,
        help="自定义 cloud endpoint（仅 staging / 私有部署用）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from krow_agent_sdk import AgentBuilder, SkillLoadError

    builder = AgentBuilder()
    if args.base_url:
        builder = builder.with_base_url(args.base_url)

    try:
        builder = builder.with_skill_directory(args.skills_dir)
    except SkillLoadError as exc:
        # fail-loud：skill 写错了要当场知道，而不是安静地少装一个。
        print(f"skill 装载失败：{exc}", file=sys.stderr)
        return 1

    reports = builder.get_skill_reports()
    print(f"已装载 {len(reports)} 个 skill\n" + "=" * 68)
    for report in reports:
        print(report.describe())
        print("-" * 68)

    print(
        "\n翻译产物是可以直接打开看的 —— 上面每条的『已物化到』就是路径，"
        "\n里面的 __act__.yaml 就是你的 frontmatter 被翻译成的样子。"
    )

    if args.dry_run:
        return 0

    api_key = os.environ.get("KROW_API_KEY", "").strip()
    if not api_key:
        print("\n未设 KROW_API_KEY，跳过 agent 构建（--dry-run 可完整演示翻译部分）。")
        return 0

    agent = (
        builder
        .with_krow_api_key(api_key)
        .with_project_root(str(HERE))
        .build()
    )
    print("\nagent 已构建；上面这些 skill 现在会作为扩展 ACT 出现在 planner 菜单里。")
    agent.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
