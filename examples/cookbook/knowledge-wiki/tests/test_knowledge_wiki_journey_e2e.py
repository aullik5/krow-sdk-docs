"""knowledge-wiki cookbook 真实 LLM E2E（本地跑、CI skip）.

跑法
====

1. 设 KROW_API_KEY（pilot key 或 prod key 都行）：

   .. code-block:: powershell

      $env:KROW_API_KEY='pk-pilot-xxx'

2. 装 cookbook：

   .. code-block:: bash

      cd packages/krow-agent-sdk/examples/cookbook/knowledge-wiki
      pip install -e ".[test]"

3. 跑：

   .. code-block:: bash

      pytest tests/test_knowledge_wiki_journey_e2e.py -v -s

CI 行为
=======

CI 上无 KROW_API_KEY → ``require_real_llm`` 装饰器自动 skip。

设计取舍
========

- **用自带 3 篇光伏 sample_data**：概念 / 实体 / 关系交织，足以抽出 ≥6 个核心
  本体节点 + 生成 ≥3 篇互链 wiki 词条。
- **本体 + wiki 落在 project_dir/.krow**（非 output_dir）：``assert_journey`` 只看
  output_dir 的 compile_report.md / ontology_snapshot.json；本体 + wiki 的**硬下界**
  由本文件自定义断言（读 ontology_snapshot.json + 扫 .krow/wiki）。
- **复用 _journey_e2e_helpers**：与其他 4 个 cookbook 共享 retry + cloud env-error skip。
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

_THIS_COOKBOOK = Path(__file__).resolve().parents[1]
_SAMPLE_DATA = _THIS_COOKBOOK / "sample_data"


@require_real_llm
def test_knowledge_wiki_tier1_journey(tmp_path: Path) -> None:
    """Tier 1 最小跑：3 篇光伏资料 → 本体 + wiki 词条."""
    project_dir = tmp_path / "kb"
    output_dir = tmp_path / "output"

    card = load_expected_card("tier1_minimal.yaml", cookbook_dir="knowledge-wiki")

    # 走通用 journey runner + retry（覆盖 LLM 偶发抖动 + cloud env-error skip）
    assert_journey_with_retry(
        cookbook_dir="knowledge-wiki",
        argv=[
            str(_SAMPLE_DATA),
            "--project-dir", str(project_dir),
            "--output-dir", str(output_dir),
            "--quiet",
        ],
        card=card,
        cwd=tmp_path,
        timeout_s=2600,
    )

    # ── 自定义硬下界断言：真的产出了 ontology + wiki（card 之外的强证据）──
    snapshot_path = output_dir / "ontology_snapshot.json"
    assert snapshot_path.exists(), "缺 ontology_snapshot.json"
    snap = json.loads(snapshot_path.read_text(encoding="utf-8"))

    key_nodes = int(snap.get("key_node_count", 0))
    wiki_pages = int(snap.get("wiki_page_count", 0))
    assert key_nodes >= 3, (
        f"本体核心节点（概念+实体）太少：{key_nodes} < 3；"
        f"ontology_counts={snap.get('ontology_counts')}"
    )
    assert wiki_pages >= 3, (
        f"wiki 词条太少：{wiki_pages} < 3（假编译信号）；"
        f"wiki_by_category={snap.get('wiki_by_category')}"
    )

    # 真实 wiki 页落盘在 project_dir/.krow/wiki
    wiki_dir = project_dir / ".krow" / "wiki"
    md_pages = [
        p for p in wiki_dir.rglob("*.md")
        if p.is_file() and not p.name.lower().startswith(("_", "."))
        and p.name.lower() not in {"index.md", "readme.md"}
    ]
    assert len(md_pages) >= 3, f"磁盘上 wiki 词条 < 3：{[p.name for p in md_pages]}"

    # 至少一篇词条有 YAML frontmatter（不是空壳 / 纯 JSON dump）
    has_frontmatter = 0
    for p in md_pages:
        txt = p.read_text(encoding="utf-8")
        if txt.lstrip().startswith("---") and "title" in txt[:300]:
            has_frontmatter += 1
    assert has_frontmatter >= 1, (
        f"没有任何 wiki 词条含 YAML frontmatter（疑似 JSON dump / 空壳）；"
        f"pages={[p.name for p in md_pages]}"
    )
