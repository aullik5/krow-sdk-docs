"""contract-auditor cookbook 真实 LLM E2E（本地跑、CI skip）.

跑法
====

1. 设 KROW_API_KEY：

   .. code-block:: powershell

      $env:KROW_API_KEY='pk-pilot-xxx'

2. 装 cookbook：

   .. code-block:: bash

      cd packages/krow-agent-sdk/examples/cookbook/contract-auditor
      pip install -e .

3. 跑：

   .. code-block:: bash

      pytest tests/test_contract_auditor_journey_e2e.py -v -s

CI 行为
=======

CI 上无 KROW_API_KEY → ``require_real_llm`` 装饰器自动 skip。

设计取舍
========

- **合成商业合同 PDF**：含"甲方免责"风险条款，对应 HighRiskBlockingGate 在
  warn-only 模式下触发但不阻断。
- **--no-mandatory-strict**：合成合同没有 GDPR / 反垄断 / 出口管制条款，
  避免 MandatoryClauseGate 真 BLOCK。
- **关闭 --docx / --observability**：缩短跑时间。Tier 3 路径见 nightly。
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
    synthesize_contract_pdf,
)


@require_real_llm
def test_contract_auditor_tier1_journey(tmp_path: Path) -> None:
    """Tier 1 最小跑：合成商业合同 PDF + 风险报告 markdown."""
    pdf = synthesize_contract_pdf(
        title="软件开发服务合同",
        parties=("北京某某科技有限公司", "上海某某软件开发有限公司"),
        contract_value_cny=1_500_000,
        out_path=tmp_path / "service_contract.pdf",
        include_unbalanced_liability=True,
        include_no_termination_clause=False,
    )
    output_dir = tmp_path / "output"
    card = load_expected_card("tier1_minimal.yaml", cookbook_dir="contract-auditor")
    # PR #624 (2026-05-27): retry 兜底 LLM 偶发抖动
    assert_journey_with_retry(
        cookbook_dir="contract-auditor",
        argv=[
            str(pdf),
            "--quiet",
            "--output-dir", str(output_dir),
            "--no-mandatory-strict",
            "--budget-llm-calls", "40",
            "--budget-walltime", "600",
            "--budget-replans", "1",
        ],
        card=card,
        cwd=tmp_path,
        timeout_s=900,
    )
