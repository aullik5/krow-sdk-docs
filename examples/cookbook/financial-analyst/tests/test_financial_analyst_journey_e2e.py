"""financial-analyst cookbook 真实 LLM E2E（本地跑、CI skip）.

跑法
====

1. 设 KROW_API_KEY（pilot key 或 prod key 都行）：

   .. code-block:: powershell

      $env:KROW_API_KEY='pk-pilot-xxx'

2. 装 cookbook + obs extras：

   .. code-block:: bash

      cd packages/krow-agent-sdk/examples/cookbook/financial-analyst
      pip install -e .[obs]

3. 跑：

   .. code-block:: bash

      pytest tests/test_financial_analyst_journey_e2e.py -v -s

CI 行为
=======

CI 上无 KROW_API_KEY → ``require_real_llm`` 装饰器自动 skip。

预期结果卡
==========

见 ``tests/expected_cards/tier1_minimal.yaml``（多维断言契约）。

设计取舍
========

- **合成 PDF**：不依赖外部年报数据，``synthesize_annual_report_pdf`` 5 KB 内即可触发
  KPI 抽取工具识别（关键词：营业收入 / 净利润 / 毛利率 / ROE / 资产负债率）。
- **--no-valuation**：跳过 valuation_anchor 工具（合成 PDF 无市值数据），
  避免 LLM 反复 replan 找市值；纯走 KPI + 行业基线 + 雷达图 + 简报。
- **多维断言**：5 段披露标题 / InsiderInfoGate 禁词 / 简报最小字节，覆盖
  GatePlugin × 2 + ToolPlugin × 5 中的 4 个核心工具。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 把 cookbook root 加进 sys.path 以便 import _journey_e2e_helpers
_COOKBOOK_ROOT = Path(__file__).resolve().parents[2]
if str(_COOKBOOK_ROOT) not in sys.path:
    sys.path.insert(0, str(_COOKBOOK_ROOT))

from _journey_e2e_helpers import (  # noqa: E402
    assert_journey,
    load_expected_card,
    assert_journey_with_retry,
    require_real_llm,
    run_journey,
    synthesize_annual_report_pdf,
)


@require_real_llm
def test_financial_analyst_tier1_journey(tmp_path: Path) -> None:
    """Tier 1 最小跑：合成单 PDF + --no-valuation + --quiet."""
    pdf = synthesize_annual_report_pdf(
        company="Skyline Tech Corp",
        revenue_yi=128.6,
        net_profit_yi=15.3,
        gross_margin_pct=42.5,
        roe_pct=18.1,
        debt_to_equity=0.32,
        out_path=tmp_path / "skyline_2024.pdf",
    )
    output_dir = tmp_path / "output"

    # PR #624 (2026-05-27): 改用 assert_journey_with_retry 覆盖 fail mode A+B
    # (LLM 偶发抖动 50%+ 实测; opus-4.6 long-form 场景 numeric_grounding 偶尔
    # 漏抽 KPI / smart_file_write 偶尔没真调). retry 不降低测试严格性.
    card = load_expected_card("tier1_minimal.yaml", cookbook_dir="financial-analyst")
    assert_journey_with_retry(
        cookbook_dir="financial-analyst",
        argv=[
            str(pdf),
            "--no-valuation",
            "--quiet",
            "--output-dir", str(output_dir),
            "--budget-llm-calls", "40",
            "--budget-walltime", "600",
            "--budget-replans", "1",
        ],
        card=card,
        cwd=tmp_path,
        timeout_s=900,
    )


@pytest.mark.skip(reason="Tier 3 需要多 PDF + Prometheus 集成，nightly 跑")
def test_financial_analyst_tier3_journey() -> None:
    """Tier 3：合规守门 + Prometheus + 多公司横向对比（占位）."""
