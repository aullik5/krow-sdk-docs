"""target-nominator cookbook 真实 LLM E2E（本地/nightly 跑、CI smoke skip）.

跑法
====

1. 设 KROW_API_KEY（pilot key 或 prod key 都行）：

   .. code-block:: powershell

      $env:KROW_API_KEY='pk-pilot-xxx'

2. 装 cookbook：

   .. code-block:: bash

      cd packages/krow-agent-sdk/examples/cookbook/target-nominator
      pip install -e .

3. 跑：

   .. code-block:: bash

      pytest tests/test_target_nominator_journey_e2e.py -v -s

CI 行为
=======

CI 上无 KROW_API_KEY → ``require_real_llm`` 装饰器自动 skip（绝不假绿）。
本 journey 真取 HPA + Open Targets 数据（需出网 443）→ LLM 多维打分提名。

预期结果卡
==========

见 ``tests/expected_cards/tier1_minimal.yaml``。

设计取舍
========

- **GPNMB journey**：黑色素瘤 6 候选（含 GPNMB），验证"经真 HPA/Open Targets 取数
  的多维打分提名"——即 litsci §13.7 的 cookbook 硬验收门。
- **真取数**：候选表达/关联/可药性全部由 cookbook 工具在线取，不预填任何数值
  （反"凭记忆编造"）。
"""
from __future__ import annotations

import sys
from pathlib import Path

_COOKBOOK_ROOT = Path(__file__).resolve().parents[2]
if str(_COOKBOOK_ROOT) not in sys.path:
    sys.path.insert(0, str(_COOKBOOK_ROOT))

from _journey_e2e_helpers import (  # noqa: E402
    assert_journey_with_retry,
    load_expected_card,
    require_real_llm,
)


@require_real_llm
def test_target_nominator_gpnmb_journey(tmp_path: Path) -> None:
    """GPNMB journey：黑色素瘤候选 → 真取数 → 多维打分 → 提名报告.

    tier1_minimal 用 4 候选（GPNMB + TYRP1 + MLANA + MCAM）——足够体现"横向竞争排序"
    且含谱系基准 GPNMB，又把逐候选多库取数（每候选 2 库真网 + 多轮 LLM）的墙钟控在
    可靠区间。6+ 候选的完整跑法见 README / sample_data（用户可 --candidates 扩展）。

    墙钟余量（实测教训 · 2026-07-11）：单次自然完成 ~500-750s，但 LLM 偶发多轮 replan /
    重写文件会把墙钟拉到 ~1000s+。故 subprocess timeout 给 1500s、预算墙钟 1200s、
    卡阈 serial 1400s，确保 LLM 抖动不撞硬超时（准确性 > 速度）。
    """
    output_dir = tmp_path / "output"
    card = load_expected_card("tier1_minimal.yaml", cookbook_dir="target-nominator")
    assert_journey_with_retry(
        cookbook_dir="target-nominator",
        argv=[
            "--cancer-type", "melanoma",
            "--candidates", "GPNMB", "TYRP1", "MLANA", "MCAM",
            "--quiet",
            "--output-dir", str(output_dir),
            "--budget-llm-calls", "150",
            "--budget-walltime", "1200",
            "--budget-replans", "1",
        ],
        card=card,
        cwd=tmp_path,
        timeout_s=1500,
    )
