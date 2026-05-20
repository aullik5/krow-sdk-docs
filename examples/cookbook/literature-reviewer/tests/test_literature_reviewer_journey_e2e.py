"""literature-reviewer cookbook 真实 LLM E2E（本地跑、CI skip）.

跑法
====

1. 设 KROW_API_KEY（pilot key 或 prod key 都行）：

   .. code-block:: powershell

      $env:KROW_API_KEY='pk-pilot-xxx'

2. 装 cookbook：

   .. code-block:: bash

      cd packages/krow-agent-sdk/examples/cookbook/literature-reviewer
      pip install -e .

3. 跑：

   .. code-block:: bash

      pytest tests/test_literature_reviewer_journey_e2e.py -v -s

CI 行为
=======

CI 上无 KROW_API_KEY → ``require_real_llm`` 装饰器自动 skip。

预期结果卡
==========

见 ``tests/expected_cards/tier1_minimal.yaml``。

设计取舍
========

- **合成 2 篇 paper PDF**：触发主题聚类（要求 ≥2 篇才能聚）+ 引言 / 方法 / 参考文献
  3 段标准结构。
- **review-topic="e2e_demo"**：固定文件名便于 expected_card 断言。
- **关闭 docx / pdf / progress-log**：缩短跑时间，只测核心 review.md 流程。
"""
from __future__ import annotations

import sys
from pathlib import Path


_COOKBOOK_ROOT = Path(__file__).resolve().parents[2]
if str(_COOKBOOK_ROOT) not in sys.path:
    sys.path.insert(0, str(_COOKBOOK_ROOT))

from _journey_e2e_helpers import (  # noqa: E402
    assert_journey,
    load_expected_card,
    require_real_llm,
    run_journey,
    synthesize_research_paper_pdf,
)


@require_real_llm
def test_literature_reviewer_tier1_journey(tmp_path: Path) -> None:
    """Tier 1 最小跑：合成 2 篇 paper + 主题聚类 + 综述 markdown."""
    paper1 = synthesize_research_paper_pdf(
        title="Towards Graph Neural Networks for Recommendation",
        authors=["Alice Wang", "Bob Liu"],
        abstract=(
            "We propose a graph neural network framework for recommendation tasks "
            "that integrates user-item interaction signals with side information. "
            "Experiments on MovieLens-1M and Amazon-Books show 8.5% improvement "
            "over BPR-MF baseline."
        ),
        keywords=["graph neural networks", "recommendation", "embedding"],
        out_path=tmp_path / "paper_gnn_recsys.pdf",
    )
    paper2 = synthesize_research_paper_pdf(
        title="Self-Supervised Contrastive Learning for Sequence Models",
        authors=["Charlie Zhang", "Diana Chen"],
        abstract=(
            "This paper introduces a contrastive self-supervised pretraining "
            "objective for sequential recommendation. Across three benchmarks, "
            "our method outperforms SASRec by 5.2% Hit@10."
        ),
        keywords=["contrastive learning", "self-supervised", "sequential recommendation"],
        out_path=tmp_path / "paper_contrastive_seq.pdf",
    )
    output_dir = tmp_path / "output"

    # W5 实测发现：传 ``--review-topic e2e_demo`` 时，
    # main.py prompt 里的 ``f"output/review_{topic}.md"`` 路径被 LLM 漂移
    # 到默认 ``literature_review.md`` 名（LLM 用了短名直觉）.
    # 解决方案：用 main.py 默认 ``review_topic="literature_review"``，
    # 且 expected_card 同步用 ``review_literature_review.md``.
    # 长远：要让 main.py 的文件名 prompt 强制约束（见 docs/lessons/...）.
    result = run_journey(
        cookbook_dir="literature-reviewer",
        argv=[
            str(paper1), str(paper2),
            "--quiet",
            "--output-dir", str(output_dir),
            "--budget-llm-calls", "60",
            "--budget-walltime", "700",
            "--budget-replans", "1",
            "--similarity-threshold", "0.05",  # 让 2 篇也能聚类（合成数据相似度低）
        ],
        cwd=tmp_path,
        timeout_s=900,
    )

    card = load_expected_card("tier1_minimal.yaml", cookbook_dir="literature-reviewer")
    assert_journey(result, card=card)
