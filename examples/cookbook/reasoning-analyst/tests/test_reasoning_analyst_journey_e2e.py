"""reasoning-analyst cookbook 真实 LLM E2E（本地跑、CI skip）.

跑法
====

1. 设 KROW_API_KEY（pilot key 或 prod key 都行）::

      $env:KROW_API_KEY='pk-pilot-xxx'   # PowerShell

2. 装 cookbook::

      cd packages/krow-agent-sdk/examples/cookbook/reasoning-analyst
      pip install -e ".[test]"

3. 跑::

      pytest tests/test_reasoning_analyst_journey_e2e.py -v -s

CI 行为
=======

CI 上无 KROW_API_KEY → ``require_real_llm`` 装饰器自动 skip。

设计取舍
========

- 默认只跑 **evidence_chain**（最复杂的链式证据 journey）做 tier1，控制单 journey
  时长 + LLM 成本。
- **关键经验断言**：纯 SDK 下 evidence_chain 可能 ``success=False``，但只要 commit
  了非空结论即视为"推理完成"。本测试断言 ``summary.json`` 的 ``n_completed >= 1``，
  而非裸看 ``success``——这正是 cookbook 想传达的判定经验。
"""
from __future__ import annotations

import json
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
def test_reasoning_analyst_evidence_chain_journey(tmp_path: Path) -> None:
    """Tier 1：病例资料 → evidence_chain 链式证据核验 → 带证据落点的结论."""
    project_dir = tmp_path / "rp"
    output_dir = tmp_path / "output"

    card = load_expected_card("tier1_minimal.yaml", cookbook_dir="reasoning-analyst")

    assert_journey_with_retry(
        cookbook_dir="reasoning-analyst",
        argv=[
            "evidence_chain",
            "--project-dir", str(project_dir),
            "--output-dir", str(output_dir),
            "--quiet",
        ],
        card=card,
        cwd=tmp_path,
        timeout_s=1800,
    )

    # ── 自定义硬下界：真的产出了结论（card 之外的强证据）──
    summary_path = output_dir / "summary.json"
    assert summary_path.exists(), "缺 summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["n_completed"] >= 1, (
        f"没有任何 journey 推理完成：{summary}"
    )

    journey = summary["journeys"][0]
    assert journey["final_output_chars"] > 50, (
        f"结论文本太短（疑似空结论）：{journey['final_output_chars']} 字"
    )
    # success 标志可能 False（纯 SDK 无 partial 兜底），但 reasoning_completed 必须 True
    assert journey["reasoning_completed"] is True, (
        f"reasoning_completed 应为 True（success={journey['success_flag']} / "
        f"concluded={journey['concluded']}）—— 这正是 cookbook 想传达的判定经验"
    )
