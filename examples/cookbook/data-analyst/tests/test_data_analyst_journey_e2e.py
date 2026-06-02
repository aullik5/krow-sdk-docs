"""data-analyst cookbook 真实 LLM E2E (本地跑、CI skip).

跑法
====

1. 设 KROW_API_KEY (pilot key 或 prod key 都行)::

      $env:KROW_API_KEY='pk-pilot-xxx'  # PowerShell
      export KROW_API_KEY='pk-pilot-xxx'  # bash

2. 装 cookbook + obs extras::

      cd packages/krow-agent-sdk/examples/cookbook/data-analyst
      pip install -e .[obs,test]

3. 跑::

      pytest tests/test_data_analyst_journey_e2e.py -v -s

CI 行为
=======

CI 上无 ``KROW_API_KEY`` → ``require_real_llm`` 装饰器自动 skip.
nightly (sdk-nightly.yml::cookbook-real-llm-journey matrix) 注入 secret 后真烧 LLM.

预期结果卡
==========

见 ``tests/expected_cards/tier1_minimal.yaml`` (多维断言契约, financial-analyst W5 同源模式).

设计取舍
========

- **复用 sample_data/titanic.csv**: 固定 20 行小 CSV, 含 PII (Name) + 缺失值 (Age) +
  分类列 (Sex / Embarked), 触发 PIIDetectorGate + write_report 6 段披露管线.
- **--audit + --allow-pii**: 启用异常检测 + 相关性 (v2 工具栈), 加 allow-pii
  避免 PIIDetectorGate BLOCK (testing 场景显式放行).
- **--quiet --pdf no**: 缩短跑时间, 只测核心 markdown 流程 (PDF 输出由
  word_smart_export 内置工具单测覆盖, 不在 cookbook journey 范畴).

P2-A follow-up (sdk-nightly.yml 2026-05-15 注释): 本 PR (2026-05-26) 落地, 让
data-analyst 与 contract-auditor / financial-analyst / literature-reviewer 并列
进入 nightly cookbook-real-llm-journey matrix.
"""
from __future__ import annotations

import shutil
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
def test_data_analyst_tier1_journey(tmp_path: Path) -> None:
    """Tier 1 最小跑: 复用 sample_data/titanic.csv + --audit + --allow-pii."""
    titanic_src = _COOKBOOK_ROOT / "data-analyst" / "sample_data" / "titanic.csv"
    assert titanic_src.exists(), (
        f"sample_data/titanic.csv 不存在: {titanic_src} — "
        "cookbook 安装时 hatch wheel include 应已带上, 检查 pyproject.toml."
    )
    titanic = tmp_path / "titanic.csv"
    shutil.copy2(titanic_src, titanic)

    output_dir = tmp_path / "output"
    card = load_expected_card("tier1_minimal.yaml", cookbook_dir="data-analyst")
    # PR #624 (2026-05-27): retry 兜底 LLM 偶发抖动（重复 H2 / numeric_grounding 漂移）
    assert_journey_with_retry(
        cookbook_dir="data-analyst",
        argv=[
            str(titanic),
            "--audit",
            "--allow-pii",
            "--quiet",
            "--output-dir", str(output_dir),
            "--budget-llm-calls", "30",
            "--budget-walltime", "500",
            "--budget-replans", "1",
        ],
        card=card,
        cwd=tmp_path,
        timeout_s=900,
    )
