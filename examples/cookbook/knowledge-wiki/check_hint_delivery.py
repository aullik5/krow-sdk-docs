"""自检：我写在 __act__.yaml 里的 hint，到 macro planner 手上了吗？

背景：`__act__.yaml` 里写的 hint **不等于** LLM 看到的 hint。中间三道收口都会丢内容
（详见 advanced-development-guide.md §4.8）：

  1. 加载期单字段硬上限 —— planner_hint 2000 字符 / decision_hint 800 字符，超出部分
     在解析 yaml 那一刻就丢弃，不进内存，后面任何通道都救不回来；
  2. macro 聚合预算 —— 没被 pin 时所有 ACT 共享 4000 字符，按 priority 装填，装不下的
     降为一行指针甚至整个丢掉；
  3. 全文披露区硬顶 —— pin + baseline 全文合计超过 24000 字符时靠后的被降级。

这三道历史上前两道完全静默：内置 pptx_studio 的作者写了 12524 字符的 planner_hint、
planner 实际只看到 2000，中间没有任何日志或报错。所以「写完就以为送到了」是本 SDK 最
容易踩的坑之一。

用法：

    python check_hint_delivery.py                 # 检查本 cookbook 自带的 ACT
    python check_hint_delivery.py path/to/act_dir # 检查你自己的 ACT 目录

脚本分两段，第二段需要装好 runtime；只写 yaml 阶段跑第一段就够：

  [静态] 只读 yaml，比对已公开的字段上限 —— 不需要 runtime，随写随查；
  [实跑] 调 ACTHierarchyLoader 做送达体检 —— 需要 runtime，看真实通道与送达字数。
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# advanced-development-guide.md §4.8 表格的 SSOT 侧镜像。
# 权威定义在 runtime 的 ACTHierarchyLoader；这里重复一份是为了「没装 runtime 也能查」，
# 数值若与 §4.8 不一致，以 §4.8 与 runtime 为准。
FIELD_CAPS = {
    "planner_hint": 2000,
    "decision_hint": 800,
    "verify_fix_hint": 2500,
    "verify_fix_hint_pisma": 2500,
}

# 建议值（留出余量，别贴着硬上限写）。本 cookbook 自带的 ACT 是刻意贴着建议值上沿写的
# 参考标定：planner_hint 1282 / decision_hint 569，承载三阶段工具链 + 两档词条模型 +
# 路径强约束仍在预算内。你的 ACT 大概率不需要比它更长。
FIELD_BUDGETS = {
    "planner_hint": 1500,
    "decision_hint": 600,
}

DEFAULT_ACT_DIR = Path(__file__).parent / "act_assets" / "knowledge_wiki_studio"


def check_static(act_dir: Path) -> int:
    """只读 yaml：作者写了多少，会不会在加载期就被截掉。"""
    yaml_path = act_dir / "__act__.yaml"
    if not yaml_path.exists():
        print(f"[静态] 找不到 {yaml_path}")
        return 1

    doc = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    act_name = doc.get("name", act_dir.name)
    print(f"[静态] {act_name}  ({yaml_path})")

    over = []
    for field, cap in FIELD_CAPS.items():
        raw = doc.get(field) or ""
        if not raw:
            continue
        n = len(raw)
        budget = FIELD_BUDGETS.get(field)
        if n > cap:
            # 实际保留量比 cap 略少：截断按行边界切并挂显式标记，回退找边界最多
            # 让出 10%。所以这里报的是"至少丢多少"，不是精确值。
            verdict = f"超硬上限，加载期至少丢 {n - cap} 字符（按行边界切，实际略多）"
            over.append(field)
        elif budget and n > budget:
            verdict = f"未超上限，但已超建议值 {budget}，建议下沉"
        else:
            verdict = "ok"
        print(f"        {field:22} {n:>6} / 上限 {cap:<6} {verdict}")

    # 第二道收口的前置条件：没有 disclosure_triggers 的 ACT，默认聚合路径下很可能一个字
    # 都送不到。纯意图场景只写 path_suffixes 是已知陷阱（用户说「做个财务对标」时手上
    # 没有任何文件路径，触发器必然 miss）。
    triggers = doc.get("disclosure_triggers") or {}
    if not triggers:
        print("        ⚠ 未声明 disclosure_triggers：不被 pin 时 planner_hint 可能送达 0 字符")
    elif not triggers.get("keywords"):
        print("        ⚠ disclosure_triggers 没有 keywords：纯意图输入（无文件路径）触发不了披露")

    if over:
        print(f"[静态] 不通过：{', '.join(over)} 超硬上限")
        return 1
    print("[静态] 通过")
    return 0


def check_live(act_name: str) -> int:
    """实跑：问 runtime「这个 ACT 的 hint 走哪条通道、送到几个字」。"""
    try:
        from modules.agent.act.act_hierarchy import get_hierarchy_loader
    except ImportError:
        print("[实跑] 跳过：未安装 runtime（krow-sdk-install --api-key ...）")
        return 0

    loader = get_hierarchy_loader()

    caps = [r for r in loader.load_time_cap_report if r.act_name == act_name]
    for rec in caps:
        print(f"[实跑] 加载期截断 {rec.field}: {rec.original_chars} → {rec.cap}"
              f"（丢 {rec.lost_chars}）")

    audit = loader.audit_hint_delivery()
    rec = audit.per_act.get(act_name)
    if rec is None:
        # 插件 ACT 只在 agent 构建时经 with_act_plugin 注册，裸跑本脚本时看不到它。
        # 这不是 hint 的问题，所以不判失败 —— 要跑这一段，把本函数搬进你的 test 里，
        # 在 AgentBuilder().with_act_plugin(...).build() 之后调用。
        print(f"[实跑] 跳过：{act_name} 未注册进当前 loader"
              f"（插件 ACT 需在 with_act_plugin(...).build() 之后才可见）")
        return 0

    print(f"[实跑] 默认聚合路径：channel={rec.channel} "
          f"作者写 {rec.authored_chars} → 送达 {rec.delivered_chars}")

    pinned = loader.audit_hint_delivery(pinned_act_names=[act_name])
    prec = pinned.per_act[act_name]
    print(f"[实跑] 被 pin 时：    channel={prec.channel} 送达 {prec.delivered_chars}")
    if pinned.demand_over_ceiling_by:
        print(f"[实跑] ⚠ 全文披露区需求超硬顶 {pinned.demand_over_ceiling_by} 字符，"
              f"这一刀会削掉靠后的 ACT")

    # 判据：pin 之后必须全文送达。做不到说明 hint 太厚，该往 extended.md 下沉了。
    if prec.channel != "pinned_full":
        print(f"[实跑] 不通过：pin 后仍未全文送达（channel={prec.channel}）")
        return 1
    print("[实跑] 通过")
    return 0


def main() -> int:
    act_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ACT_DIR
    rc = check_static(act_dir)
    doc = yaml.safe_load((act_dir / "__act__.yaml").read_text(encoding="utf-8")) or {}
    return rc | check_live(doc.get("name", act_dir.name))


if __name__ == "__main__":
    raise SystemExit(main())
