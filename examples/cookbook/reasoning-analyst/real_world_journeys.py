"""三个真实世界 reasoning journey 预设（PR-B · 2026-07-06 三议题辩论 议题 3）。

用户诉求：SDK cookbook 升级为覆盖三个真实场景的完整 journey，**除 UI 外等价于
桌面版效果**：

  1. ``target_discovery`` —— 肺癌论文找靶点（因果发现 causal_discovery，科研闭环）
  2. ``whodunit_x`` —— X 的悲剧推理真凶（竞争假设排除 hypothesis_test，长文本 whodunit）
  3. ``whodunit_z`` —— Z 的悲剧推理真凶（同 hypothesis_test，另一部长篇）

版权合规（辩论 §三 SDK-ENG 红线）
================================
三个真实数据集**都不能进公开仓**（期刊 PDF = 出版商版权；X/Z = 小说译本版权）。
所以本模块只做三件事：

  (a) **预设定义**（策略 + 默认问题 + 真数据 env / 路径约定），零版权内容；
  (b) **微型合成样例**（本仓自撰、零版权的仿写侦探短篇 + 合成文献摘要，几 KB），
      够 smoke 跑通管线；
  (c) **真数据路径参数化**——用户把真数据放到约定路径 / 传 env，即复现完整 journey。

这是纯 System-1 模块（零 LLM、可单测）；``main.py --preset <name>`` 消费它。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SYNTH_DIR = _HERE / "sample_data" / "real_world_synthetic"


@dataclass(frozen=True)
class JourneyPreset:
    """一个真实世界 journey 的确定性定义（零 LLM）。"""

    name: str
    strategy: str
    question: str
    #: 真数据路径的环境变量名（用户 export 后即用真数据跑）
    data_env: str
    #: 真数据缺省路径提示（写进 README / 报错，非硬编码依赖）
    data_hint: str
    #: 合成微样例子目录名（smoke 跑用，随仓发布，零版权）
    synthetic_subdir: str
    #: 结果导向验收关键词（桌面对应 journey 卡的结果子集，去 UI 断言）
    expected_card: str


PRESETS: dict[str, JourneyPreset] = {
    "target_discovery": JourneyPreset(
        name="target_discovery",
        strategy="causal_discovery",
        question=(
            "从提供的肺癌研究文献中挖掘潜在的药物靶点：哪些基因/通路是肺癌"
            "发生发展的因果致因（而非仅相关）？请走科研闭环（抽取→规律发现→"
            "提候选靶点假设→竞争排除→因果验证→结论），对每个候选靶点给出"
            "支持证据、反驳后的可信度，以及可成药性判断。"
        ),
        data_env="KROW_JOURNEY_LUNG_CANCER_PAPERS",
        data_hint=r"D:\krow\projects\肺癌科研智能体\papers（期刊 PDF 目录）",
        synthetic_subdir="lung_cancer_abstracts",
        expected_card="tier3_target_discovery.yaml",
    ),
    "whodunit_x": JourneyPreset(
        name="whodunit_x",
        strategy="hypothesis_test",
        question=(
            "根据提供的侦探小说全文，推理谁是真凶。请用竞争假设排除法（ACH）："
            "为每个嫌疑人建立假设，逐条核验证据（尤其强证据）是否吻合，任何一条"
            "不吻合即为疑点（矛盾），顺着疑点深挖直到证明或证伪该假设。只有当某个"
            "假设解释了所有高置信疑点、且其余假设都被证伪时，才给出真凶结论。"
        ),
        data_env="KROW_JOURNEY_TRAGEDY_X",
        data_hint=r"D:\krow\projects\侦探小说\X的悲剧-隐藏结尾版本.txt（约 509KB 全文）",
        synthetic_subdir="mini_whodunit",
        expected_card="tier3_whodunit.yaml",
    ),
    "whodunit_z": JourneyPreset(
        name="whodunit_z",
        strategy="hypothesis_test",
        question=(
            "根据提供的侦探小说全文，推理谁是真凶。请用竞争假设排除法（ACH）"
            "逐条权衡证据，死抓每一个疑点递归深挖，把不成立的假设一一证伪，"
            "直到只剩一个能解释全部高置信疑点的假设，再给出真凶结论并说明"
            "关键推理链。"
        ),
        data_env="KROW_JOURNEY_TRAGEDY_Z",
        data_hint=(
            r"D:\krow\projects\Z的悲剧-分析推理\output\Z的悲剧-隐藏结局版本.md"
            "（约 366KB 全文）"
        ),
        synthetic_subdir="mini_whodunit",
        expected_card="tier3_whodunit.yaml",
    ),
}


class UnknownPresetError(ValueError):
    """preset 名不存在时 fail-loud（黄金错误模板）。"""


def get_preset(name: str) -> JourneyPreset:
    """按名取预设；不存在 fail-loud 列出可选项。"""
    key = (name or "").strip()
    preset = PRESETS.get(key)
    if preset is None:
        raise UnknownPresetError(
            f"未知的 journey 预设 {name!r}。\n"
            f"  可选：{', '.join(PRESETS)}\n"
            f"  用法：python main.py --preset target_discovery"
        )
    return preset


def resolve_journey_sources(
    preset: JourneyPreset,
    *,
    override: str | None = None,
) -> tuple[Path, bool]:
    """解析该 preset 的资料目录/文件，返回 ``(path, is_real)``。

    优先级：显式 ``override`` > env(``preset.data_env``) > 合成微样例。
    ``is_real=True`` 表示用了真实（版权）数据；``False`` 表示用随仓合成样例。

    Raises:
        FileNotFoundError: override / env 指定了路径但不存在（fail-loud）。
    """
    if override:
        p = Path(override).expanduser()
        if not p.exists():
            raise FileNotFoundError(
                f"--sources 指定的资料不存在：{p}"
            )
        return p, True
    env_val = os.environ.get(preset.data_env, "").strip()
    if env_val:
        p = Path(env_val).expanduser()
        if not p.exists():
            raise FileNotFoundError(
                f"环境变量 {preset.data_env} 指向的资料不存在：{p}\n"
                f"  期望：{preset.data_hint}"
            )
        return p, True
    synth = _SYNTH_DIR / preset.synthetic_subdir
    return synth, False


def synthetic_dir(preset: JourneyPreset) -> Path:
    """该 preset 的合成微样例目录（随仓发布，零版权）。"""
    return _SYNTH_DIR / preset.synthetic_subdir
