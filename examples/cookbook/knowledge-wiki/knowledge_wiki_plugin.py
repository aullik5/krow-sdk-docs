"""Knowledge-wiki cookbook plugin SSOT.

> Cookbook v3.5 第 1 个"知识管理"demo（设计依据：``COOKBOOK_DESIGN.md`` §2.4）。

业务场景：知识工作者 / 研究团队 / 企业知识库管理员，手上有一批领域资料
（markdown / txt / PDF / Office），想把它们**编译成结构化知识库**——抽出本体
（Ontology：概念 / 实体 / 关系），并为每个核心节点生成一篇可浏览、可互链的
**百科词条（wiki）**。LLM 介入前要人工梳理 1-2 天；用本 cookbook 预期 20-40 分钟。

与前 4 个 cookbook 的本质差异（**这是关键设计点**）：

- financial / literature / contract / data-analyst：核心工作由 cookbook **自带的
  领域工具**（KPI 抽取 / 聚类 / 条款分类）完成，LLM 调它们。
- knowledge-wiki：核心工作（抽本体 + 写 wiki）由 **Krow 引擎内置工具** 完成
  （``extract_entities_from_text`` / ``add_relation`` / ``wiki_info`` /
  ``smart_file_write`` / ``summarize_ontology``），通过 ``with_project_root()``
  在 ``sdk_runtime`` 工具栈自动注册，再由 ``task_context={"strategy":
  "knowledge_compile"}`` 三阶段契约驱动。**cookbook 不重复造这些轮子**（SSOT 铁律）。

那么本 cookbook 的 plugin 演示什么"按需而生"的价值（设计原则 §1.2 ②）？

1. **ToolPlugin × 2（差异化 + 必要性，不与内置工具重复）**：
   - ``knowledge_wiki_scan_sources``：确定性扫描资料目录 → 产出可编译源清单
     （path / ext / size / 估算 chunk 数）。内置工具没有"我该编入哪些文件"的
     规划器；这个 System 1 工具给 LLM 一份确定性的 ingest 清单，避免漏编 / 重编。
   - ``knowledge_wiki_coverage_report``：确定性交叉核对 **本体节点数 vs wiki 页数**
     → 给出覆盖率 + 缺页清单。内置 ``summarize_ontology`` 只总览本体、
     ``wiki_info(validate)`` 只 lint wiki，**都不做"本体↔wiki 覆盖"交叉核对**。
     这个工具正是"编译后词条到底有没有变丰富"的确定性度量（直接回应真实用户反馈）。

2. **GatePlugin × 1（WikiCoverageGate）**：fail-loud 守门，防"假编译"——
   本体抽完但 wiki 页几乎没写（用户原始痛点：编译完没感觉词条变丰富）。
   读 ``knowledge_wiki_coverage_report`` 结果，覆盖不足则 BLOCK conclude。

3. **EventListenerPlugin × 1（CompileProgressListener）**：三阶段（抽取 / 关联 /
   发布）实时进度 + 审计 jsonl，让用户看到编译在推进而非卡死。

4. **HintPlugin / ObservabilityPlugin 按需省略**（设计 §3 铁律：不为凑齐硬塞）：
   - Hint：编译流程由 ``knowledge_compile`` 契约 + ACT 引导，软提示价值低。
   - Observability：个人 / 团队知识库一般不接 BI dashboard。

参考：
- 内置编译 E2E 金标准：``tests/fixtures/expected_cards/journey_wiki_compile_medical_v2.yaml``
- 编译策略 SSOT：``modules/knowledge/reasoning_strategies.py::Strategy(id="knowledge_compile")``
- 设计 SSOT：``COOKBOOK_DESIGN.md`` §2.4 / §3
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# §0. 通用工具（黄金错误模板 + 路径归一化 + wiki 页扫描）
# ============================================================

# 编入百科的源文件支持的后缀（与 lifecycle_triggers 的 ingest 后缀对齐）
_INGESTIBLE_EXTS = {".md", ".txt", ".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".html"}

# wiki 页四大分类目录（与 WikiCompiler 落盘约定一致）
_WIKI_CATEGORIES = ("concepts", "entities", "sources", "comparisons")


def _normalize_path(p: str | Path) -> Path:
    if isinstance(p, str):
        p = Path(p)
    return p.expanduser().resolve()


def _golden_error(
    msg: str, *, where: str, fixes: Iterable[str], related: Iterable[str] = ()
) -> dict[str, Any]:
    parts = [f"❌ {msg}", f"   位置：{where}", "   修法："]
    for i, fix in enumerate(fixes, 1):
        parts.append(f"     {i}. {fix}")
    if related:
        parts.append(f"   相关：{' / '.join(related)}")
    return {"ok": False, "error": "\n".join(parts)}


def _resolve_project_root(project_root: str | Path | None) -> Path | None:
    """归一化 project_root；None 时尝试从 project_context 读（与内置工具同源）."""
    if project_root:
        return _normalize_path(project_root)
    try:
        from modules.utils.project_context import get_project_root

        pr = get_project_root()
        return _normalize_path(pr) if pr else None
    except Exception:  # noqa: BLE001
        return None


def _wiki_dir_of(project_root: Path) -> Path:
    return project_root / ".krow" / "wiki"


def _scan_wiki_pages(wiki_dir: Path) -> dict[str, list[Path]]:
    """扫描 .krow/wiki 下的 *.md，按分类目录归组（不含 index / _* 文件）."""
    by_cat: dict[str, list[Path]] = {c: [] for c in _WIKI_CATEGORIES}
    by_cat["other"] = []
    if not wiki_dir.exists():
        return by_cat
    for md in wiki_dir.rglob("*.md"):
        if not md.is_file():
            continue
        name = md.name.lower()
        # 跳过索引 / 隐藏 / 模板 / 脚手架文件（index/log/schema 非词条）
        if name.startswith(("_", ".")) or name in {
            "index.md", "readme.md", "log.md", "schema.md",
        }:
            continue
        # 归类：看相对 wiki_dir 的第一段目录
        try:
            rel_parts = md.relative_to(wiki_dir).parts
        except ValueError:
            rel_parts = (md.name,)
        cat = rel_parts[0] if len(rel_parts) > 1 and rel_parts[0] in by_cat else "other"
        by_cat[cat].append(md)
    return by_cat


# ============================================================
# §1. 源清单扫描（System 1 确定性 ingest 规划）
# ============================================================
#
# 业务理由：
#   编译知识库第一步 = 确定"哪些文件要编入"。让 LLM 自己 ls 目录再决定，会
#   漏文件 / 把 .krow/wiki 自己产出的页又编一遍（自激环）。System 1 工具按
#   确定性规则扫描，给 LLM 一份干净的 ingest 清单。


def scan_knowledge_sources(
    docs_dir: str | Path,
    *,
    min_bytes: int = 200,
    max_sources: int = 200,
) -> dict[str, Any]:
    """扫描资料目录，产出可编译的源文件清单（确定性，零 LLM）.

    Args:
        docs_dir: 资料目录（递归扫描）
        min_bytes: 过滤过小文件（< 此字节视为占位 / 空文件，跳过）
        max_sources: 清单上限（防 prompt 膨胀）

    Returns:
        dict 含 ok/summary/sources（list of {path, ext, size_bytes, est_chunks}）/
        n_sources/total_bytes/skipped_small
    """
    d = _normalize_path(docs_dir)
    if not d.exists() or not d.is_dir():
        return _golden_error(
            f"资料目录不存在或不是目录：{d}",
            where=f"docs_dir={docs_dir}",
            fixes=[
                "检查路径拼写",
                "传入包含 .md / .txt / .pdf / .docx 资料的目录",
            ],
            related=["scan_knowledge_sources"],
        )

    sources: list[dict[str, Any]] = []
    total_bytes = 0
    skipped_small = 0
    for f in sorted(d.rglob("*")):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext not in _INGESTIBLE_EXTS:
            continue
        # 跳过 .krow（引擎产出物，不能反向编入 → 自激环）
        if ".krow" in f.parts:
            continue
        size = f.stat().st_size
        if size < min_bytes:
            skipped_small += 1
            continue
        # 文本类按 ~1200 字节估算 chunk 数；二进制类粗估
        est_chunks = max(1, size // 1200)
        sources.append({
            "path": str(f),
            "ext": ext,
            "size_bytes": size,
            "est_chunks": est_chunks,
        })
        total_bytes += size
        if len(sources) >= max_sources:
            break

    if not sources:
        return _golden_error(
            f"目录下没有可编译的源文件（支持 {sorted(_INGESTIBLE_EXTS)}）",
            where=f"docs_dir={d}",
            fixes=[
                f"放入至少 1 份 ≥{min_bytes}B 的 .md / .txt / .pdf / .docx",
                f"跳过了 {skipped_small} 个过小文件（< {min_bytes}B）",
            ],
        )

    return {
        "ok": True,
        "summary": (
            f"扫描完成：{len(sources)} 个可编译源文件，"
            f"共 {total_bytes} 字节，估算 ~{sum(s['est_chunks'] for s in sources)} 个 chunk"
            f"{f'（跳过 {skipped_small} 个过小文件）' if skipped_small else ''}"
        ),
        "sources": sources,
        "n_sources": len(sources),
        "total_bytes": total_bytes,
        "skipped_small": skipped_small,
    }


# ============================================================
# §2. 本体↔wiki 覆盖率核对（System 1 确定性后置验收）
# ============================================================
#
# 业务理由（直接回应真实用户反馈）：
#   "编译完后没感觉到词条丰富了" —— 因为本体抽取了一堆节点，但只写了 1-2 篇
#   wiki 页，绝大多数节点没有对应词条。内置 summarize_ontology 只看本体、
#   wiki_info(validate) 只 lint wiki，没人做"本体节点 vs wiki 页"的覆盖核对。
#   这个工具给出确定性覆盖率，是编译质量的"验收单"。


def report_wiki_coverage(
    project_root: str | Path | None = None,
    *,
    wiki_dir: str | Path | None = None,
) -> dict[str, Any]:
    """交叉核对本体节点数与 wiki 页数，给出覆盖率 + 验收结论（确定性，零 LLM）.

    Args:
        project_root: 项目根（None 时从 project_context 读）
        wiki_dir: wiki 目录（None 时取 project_root/.krow/wiki）

    Returns:
        dict 含 ok/summary/ontology_counts/wiki_page_count/wiki_by_category/
        coverage_ratio/key_node_count/under_populated
    """
    pr = _resolve_project_root(project_root)
    if pr is None:
        return _golden_error(
            "未能解析 project_root（未传且 project_context 未设）",
            where="report_wiki_coverage",
            fixes=[
                "显式传 project_root=<项目根目录>",
                "或确保 Agent 已 with_project_root(...) 构建",
            ],
        )

    # 读 GlobalOntology 6 类对象 count（走 SDK 公开 data API）
    ontology_counts: dict[str, int] = {}
    try:
        from krow_agent_sdk.data import get_global_ontology_snapshot

        snap = get_global_ontology_snapshot(pr)
        ontology_counts = dict(snap.get("counts") or {})
    except Exception as e:  # noqa: BLE001
        logger.warning("读 ontology snapshot 失败：%s", e)
        ontology_counts = {}

    wd = _normalize_path(wiki_dir) if wiki_dir else _wiki_dir_of(pr)
    by_cat = _scan_wiki_pages(wd)
    wiki_by_category = {c: len(v) for c, v in by_cat.items()}
    wiki_page_count = sum(wiki_by_category.values())

    # "核心节点" = 概念 + 实体（这两类是应当有 wiki 词条的对象；
    #  chunk / relation / action / event 不要求逐个建页）
    key_node_count = int(ontology_counts.get("concept", 0)) + int(
        ontology_counts.get("entity", 0)
    )
    coverage_ratio = (
        round(wiki_page_count / key_node_count, 3) if key_node_count > 0 else 0.0
    )
    # 验收：本体有核心节点但 wiki 页严重偏少 → under_populated（假编译信号）
    under_populated = key_node_count >= 3 and wiki_page_count < 3

    cat_str = ", ".join(
        f"{c}={n}" for c, n in wiki_by_category.items() if n > 0
    ) or "（无）"
    return {
        "ok": True,
        "summary": (
            f"覆盖核对：本体核心节点 {key_node_count}（概念 "
            f"{ontology_counts.get('concept', 0)} + 实体 "
            f"{ontology_counts.get('entity', 0)}），wiki 页 {wiki_page_count} "
            f"[{cat_str}]，覆盖率 {coverage_ratio:.0%}"
            + ("，⚠️ 词条偏少（疑似假编译）" if under_populated else "，✅ 覆盖正常")
        ),
        "project_root": str(pr),
        "ontology_counts": ontology_counts,
        "wiki_page_count": wiki_page_count,
        "wiki_by_category": wiki_by_category,
        "key_node_count": key_node_count,
        "coverage_ratio": coverage_ratio,
        "under_populated": under_populated,
    }


# ============================================================
# §2.5 知识编译三段（抽取 / 关联 / 物化）—— 复用引擎内置 System 1/2 能力
# ============================================================
#
# 设计哲学（AGENTS.md §0.1 TURBO + SSOT）：
#   这三个工具**不重写**抽取 / 关系 / 物化逻辑，而是把引擎里**已验证可靠**的
#   单发能力封成"可被 agent 调、也可被 main.py 确定性编排"的工具：
#     - 抽取（System 2）：``extractive_tools.tool_extract_entities_from_text``
#       —— 每文件一次 LLM 调用，直接写 GlobalOntologyStore（可靠、可重放）。
#     - 关联（System 2）：``call_llm`` 提关系候选 + ``tool_add_relation`` 落库
#       （复用 ``scripts/build_e2e_seed_ontology.py`` 同款 SSOT 模式）。
#     - 物化（System 1 · 零 LLM）：``ontology_stub_compiler.compile_ontology_to_stubs``
#       —— 把本体节点确定性派生为可点击 wiki stub 词条（红链物化，公理 D）。
#   为什么不直接让 macro-ReACT 一把跑完：单发工具比"巨型 ReACT 循环"可靠得多
#   （后者易在 step 解析/重规划上空转）。main.py 用 System 1 编排串起单发 System 2，
#   正是 TURBO 哲学的落地。所有内置依赖**惰性 import**（保 plugin standalone 可导入）。


def _resolve_store(project_root: Path) -> Any:
    """取 project_root 对应的 GlobalOntologyStore 单例（惰性 import 内置）."""
    from modules.knowledge.global_ontology_store import get_global_ontology_store

    return get_global_ontology_store(project_root)


def extract_ontology_from_sources(
    project_root: str | Path | None,
    sources: list[str] | str,
    *,
    max_items: int = 15,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """对每个源文件单发抽取 Concept/Entity/Event 入 GlobalOntology（System 2）.

    复用引擎内置 ``tool_extract_entities_from_text``（每文件一次 LLM 调用，
    可靠落库）。返回逐文件计数 + 本体总计数。

    **重试**：默认 chat model 可能是 thinking 模型，偶发返回 ``<think>`` 前导
    占满 token 预算 → JSON 截断 → 该文件抽到 0 个对象。这是随机现象（重试常成功），
    故对"抽到 0 且文件非空"的文件最多重试 ``max_attempts`` 次（System 1 鲁棒包装）。
    """
    pr = _resolve_project_root(project_root)
    if pr is None:
        return _golden_error(
            "未能解析 project_root",
            where="extract_ontology_from_sources",
            fixes=["显式传 project_root", "或先 with_project_root(...) 构建 Agent"],
        )
    if isinstance(sources, str):
        sources = [sources]
    if not sources:
        return _golden_error(
            "sources 为空",
            where="extract_ontology_from_sources",
            fixes=["先调 knowledge_wiki_scan_sources 拿源清单再传入"],
        )
    try:
        from modules.agent.react_templates.extractive_tools import (
            tool_extract_entities_from_text,
        )
    except Exception as e:  # noqa: BLE001
        return _golden_error(
            f"内置抽取工具不可用：{e}",
            where="extract_ontology_from_sources",
            fixes=["确认安装 krow-agent-sdk[ontology]", "确认在 krow 引擎运行时内"],
        )

    store = _resolve_store(pr)
    if store is None:
        return _golden_error(
            "GlobalOntologyStore 未就绪",
            where="extract_ontology_from_sources",
            fixes=["确认 project_root 下 .krow 可写", "确认 with_project_root 已生效"],
        )

    ctx = {"project_root": str(pr), "task_context": {"project_root": str(pr)}}
    attempts = max(1, int(max_attempts))
    per_file: list[dict[str, Any]] = []

    def _obj_total() -> int:
        return store.count("concept") + store.count("entity") + store.count("event")

    for src in sources:
        sp = Path(src)
        # 归一为相对 project_root（内置工具按 root 解析；绝对路径也支持）
        file_arg = src
        with suppress(Exception):
            if sp.is_absolute() and pr in sp.resolve().parents:
                file_arg = sp.resolve().relative_to(pr).as_posix()
        before = _obj_total()
        last_head: list[str] = []
        err: str | None = None
        used = 0
        for used in range(1, attempts + 1):
            try:
                md = tool_extract_entities_from_text(
                    {
                        "file_path": file_arg,
                        "kinds": ["person", "org", "product", "symbol", "place"],
                        "max_items": max_items,
                    },
                    ctx,
                    store=store,
                )
                last_head = (md or "").splitlines()[:1]
            except Exception as e:  # noqa: BLE001
                err = str(e)
                logger.warning("extract failed for %s (try %d): %s", file_arg, used, e)
            if _obj_total() > before:
                break
        new_objects = max(0, _obj_total() - before)
        rec: dict[str, Any] = {
            "file": file_arg,
            "new_objects": new_objects,
            "attempts": used,
            "head": last_head,
        }
        if err and new_objects == 0:
            rec["error"] = err
        per_file.append(rec)

    counts = {
        k: store.count(k)
        for k in ("concept", "entity", "event", "relation", "document_chunk")
    }
    total_new = sum(int(x.get("new_objects", 0)) for x in per_file)
    return {
        "ok": total_new > 0,
        "summary": (
            f"抽取完成：{len(sources)} 个源文件 → 本体新增 {total_new} 个对象"
            f"（当前 concept={counts['concept']} entity={counts['entity']} "
            f"event={counts['event']} relation={counts['relation']}）"
        ),
        "project_root": str(pr),
        "per_file": per_file,
        "ontology_counts": counts,
        "total_new_objects": total_new,
    }


def link_ontology_relations(
    project_root: str | Path | None,
    *,
    max_relations: int = 20,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """LLM 对已抽本体提领域关系候选 + 落库（System 2，复用 seed 同款 SSOT 模式）.

    与抽取同理，thinking 模型偶发 ``<think>`` 截断导致 0 候选 → 最多重试
    ``max_attempts`` 次（System 1 鲁棒包装）。
    """
    pr = _resolve_project_root(project_root)
    if pr is None:
        return _golden_error(
            "未能解析 project_root",
            where="link_ontology_relations",
            fixes=["显式传 project_root"],
        )
    store = _resolve_store(pr)
    if store is None:
        return _golden_error(
            "GlobalOntologyStore 未就绪",
            where="link_ontology_relations",
            fixes=["先调 extract_ontology_from_sources 抽本体"],
        )
    try:
        from modules.agent.react_templates.extractive_tools import tool_add_relation
        from modules.agent.react_templates.llm_call import call_llm
    except Exception as e:  # noqa: BLE001
        return _golden_error(
            f"内置关系工具不可用：{e}",
            where="link_ontology_relations",
            fixes=["确认在 krow 引擎运行时内"],
        )

    concepts = list(store.iter("concept"))
    entities = list(store.iter("entity"))
    events = list(store.iter("event"))
    if len(concepts) + len(entities) + len(events) < 2:
        return {
            "ok": True,
            "summary": "本体对象不足 2 个，跳过关系推断",
            "added": 0,
        }

    def _brief(obj: Any) -> str:
        label = getattr(obj, "label", "?")
        defn = (getattr(obj, "definition", "") or "")[:70]
        return f"{obj.id} | {label} | {defn}" if defn else f"{obj.id} | {label}"

    roster = "\n".join(
        ["# Concepts"] + [_brief(o) for o in concepts]
        + ["", "# Entities"] + [_brief(o) for o in entities]
        + ["", "# Events"] + [_brief(o) for o in events]
    )
    system = (
        "你是领域本体工程师。基于给定的 Concept/Entity/Event 清单，找出**明确**的"
        "领域关系。只输出 JSON 数组。每项字段：source_id（必须来自清单），"
        "target_id（必须来自清单），kind ∈ is_a/part_of/causes/participates/"
        "precedes/related，weight_label ∈ strong/medium/weak。"
        "避免自环 / 重复 / 模糊联想；不确定就不输出。"
    )
    user = (
        f"请基于下列 Ontology 对象清单，给出 {min(max_relations, 20)} 条以内的关系。\n\n"
        f"---\n{roster}\n---"
    )
    import re

    candidates: list[dict[str, Any]] = []
    for _ in range(max(1, int(max_attempts))):
        raw = call_llm(system=system, user=user, temperature=0.15, max_tokens=1800)
        if raw:
            m = re.search(r"(\[\s*\{.*?\}\s*\])", raw, re.DOTALL)
            if m:
                with suppress(Exception):
                    data = json.loads(m.group(1))
                    if isinstance(data, list):
                        candidates = [x for x in data if isinstance(x, dict)]
        if candidates:
            break

    added = 0
    for c in candidates[:max_relations]:
        sid = str(c.get("source_id") or "").strip()
        tid = str(c.get("target_id") or "").strip()
        kind = str(c.get("kind") or "related").strip()
        weight = str(c.get("weight_label") or "medium").strip()
        if not sid or not tid or sid == tid:
            continue
        out = tool_add_relation(
            {"source_id": sid, "target_id": tid, "kind": kind, "weight_label": weight},
            {},
            store=store,
        )
        if out and not str(out).startswith("❌"):
            added += 1

    return {
        "ok": True,
        "summary": f"关系推断完成：候选 {len(candidates)} 条 → 落库 {added} 条",
        "project_root": str(pr),
        "candidates": len(candidates),
        "added": added,
        "relation_count": store.count("relation"),
    }


def materialize_wiki_pages(
    project_root: str | Path | None,
    *,
    min_signal: int = 1,
) -> dict[str, Any]:
    """把本体节点确定性派生为 wiki stub 词条（System 1 · 零 LLM · 公理 D 红链物化）.

    复用引擎内置 ``compile_ontology_to_stubs``。这是 SDK 场景下"编译完词条变丰富"
    的关键一步——桌面端由 ``KnowledgeLifecycleManager`` 自动触发，SDK 端需显式调用。
    """
    pr = _resolve_project_root(project_root)
    if pr is None:
        return _golden_error(
            "未能解析 project_root",
            where="materialize_wiki_pages",
            fixes=["显式传 project_root"],
        )
    try:
        from modules.knowledge.wiki_compiler.ontology_stub_compiler import (
            compile_ontology_to_stubs,
        )
    except Exception as e:  # noqa: BLE001
        return _golden_error(
            f"内置物化器不可用：{e}",
            where="materialize_wiki_pages",
            fixes=["确认安装 krow-agent-sdk[ontology]"],
        )
    try:
        result = compile_ontology_to_stubs(pr, min_signal=int(min_signal))
    except Exception as e:  # noqa: BLE001
        return _golden_error(
            f"物化失败：{e}",
            where="materialize_wiki_pages",
            fixes=["先 extract_ontology_from_sources 抽本体再物化"],
        )
    stats = result.as_dict()
    return {
        "ok": stats["created_count"] + stats["updated_count"] > 0,
        "summary": (
            f"wiki 物化完成：新建 {stats['created_count']} 篇 + 刷新 "
            f"{stats['updated_count']} 篇（遍历 {stats['total_nodes']} 节点，"
            f"跳过低信号 {stats['skipped_low_signal']}）"
        ),
        "project_root": str(pr),
        **stats,
    }


# ============================================================
# §3. ToolPlugin（注册差异化 System 1 工具 + 编译三段封装）
# ============================================================


class KnowledgeWikiToolPlugin:
    """实现 ``krow_agent_sdk.protocols.ToolPlugin`` Protocol。

    注册的工具分两类：
    - 差异化 System 1 工具（scan_sources / coverage_report）：内置工具没有的能力。
    - 编译三段封装（extract / relate / materialize）：把引擎已验证的单发能力封成
      可被 agent 调、也可被 main.py 确定性编排的工具（不重写逻辑，SSOT 复用）。
    """

    plugin_id = "knowledge_wiki.tools"

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "knowledge_wiki_scan_sources",
                "description": (
                    "确定性扫描资料目录，产出可编译的源文件清单"
                    "（path/ext/size/est_chunks）。编译知识库前先调本工具拿 ingest 清单，"
                    "避免漏编 / 把 .krow/wiki 引擎产出物反向编入（自激环）。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "docs_dir": {
                            "type": "string",
                            "description": "资料目录（递归扫描）",
                        },
                        "min_bytes": {
                            "type": "integer",
                            "default": 200,
                            "description": "过滤过小文件阈值",
                        },
                        "max_sources": {"type": "integer", "default": 200},
                    },
                    "required": ["docs_dir"],
                },
                "handler": scan_knowledge_sources,
            },
            {
                "name": "knowledge_wiki_extract_ontology",
                "description": (
                    "对源文件逐个单发抽取概念/实体/事件入本体（每文件一次 LLM 调用，"
                    "可靠落库 GlobalOntology）。是知识编译第一阶段；比让 ReACT 自己"
                    "循环抽取更可靠。传 knowledge_wiki_scan_sources 给出的 path 列表。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "project_root": {"type": "string"},
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "源文件路径列表（绝对或相对 project_root）",
                        },
                        "max_items": {"type": "integer", "default": 15},
                    },
                    "required": ["sources"],
                },
                "handler": extract_ontology_from_sources,
            },
            {
                "name": "knowledge_wiki_link_relations",
                "description": (
                    "对已抽本体用 LLM 提领域关系（is_a/part_of/causes/...）并落库。"
                    "知识编译第二阶段；让词条之间形成可导航的关系网络。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "project_root": {"type": "string"},
                        "max_relations": {"type": "integer", "default": 20},
                    },
                    "required": [],
                },
                "handler": link_ontology_relations,
            },
            {
                "name": "knowledge_wiki_materialize",
                "description": (
                    "把本体节点确定性派生为可点击 wiki stub 词条（零 LLM）。"
                    "知识编译第三阶段；SDK 场景必调（桌面端由生命周期自动触发）。"
                    "这是'编译完词条变丰富'的关键步骤。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "project_root": {"type": "string"},
                        "min_signal": {
                            "type": "integer",
                            "default": 1,
                            "description": "质量门：关系+出处数 ≥ 此值才成页",
                        },
                    },
                    "required": [],
                },
                "handler": materialize_wiki_pages,
            },
            {
                "name": "knowledge_wiki_coverage_report",
                "description": (
                    "确定性交叉核对本体节点数 vs wiki 页数，给出覆盖率 + 验收结论。"
                    "编译收尾时调本工具验收——内置 summarize_ontology 只看本体、"
                    "wiki_info(validate) 只 lint wiki，本工具专做'本体↔wiki 覆盖'核对，"
                    "是'词条到底有没有变丰富'的确定性度量。under_populated=true 即假编译信号。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "project_root": {
                            "type": "string",
                            "description": "项目根（缺省从运行时 project_context 读）",
                        },
                        "wiki_dir": {"type": "string"},
                    },
                    "required": [],
                },
                "handler": report_wiki_coverage,
            },
        ]


# ============================================================
# §4. ACTPlugin（让 LLM 自动选 knowledge_wiki_studio ACT）
# ============================================================


class KnowledgeWikiACTPlugin:
    """实现 ``krow_agent_sdk.protocols.ACTPlugin`` Protocol。

    本 ACT 把"知识编译 + wiki 编译"的三阶段工作流（抽取 / 关联 / 发布）
    与 cookbook 自带的扫描 / 覆盖核对工具打包，bundling 内置编译工具栈。
    """

    plugin_id = "knowledge_wiki.act"
    act_name = "knowledge_wiki_studio"

    def get_act_root(self) -> Path:
        return Path(__file__).parent / "act_assets" / "knowledge_wiki_studio"

    def get_act_file_path(self) -> Path:
        return self.get_act_root() / "ext_knowledge_wiki_studio.md"

    def get_tool_names(self) -> list[str]:
        # cookbook 自带 2 工具 + Krow 内置知识编译工具栈（由 with_project_root
        # 在 sdk_runtime 注册；knowledge_compile 策略也会注入这批白名单）
        return [
            "knowledge_wiki_scan_sources",
            "knowledge_wiki_extract_ontology",
            "knowledge_wiki_link_relations",
            "knowledge_wiki_materialize",
            "knowledge_wiki_coverage_report",
            "smart_read_document",
            "read_file",
            "summarize_ontology",
            "wiki_info",
            "smart_file_write",
            "save_note",
        ]


# ============================================================
# §5. GatePlugin（WikiCoverageGate · 防"假编译"硬阻断）
# ============================================================
#
# 设计依据（真实用户反馈驱动）：
#   "编译完后没感觉到词条丰富了" = 本体抽了一堆节点但 wiki 页几乎没写。
#   hint 提醒 LLM "记得写 wiki" 在压缩任务时会被跳过；必须 System 1 闸住：
#   conclude 前若覆盖核对显示 under_populated → BLOCK，逼 LLM 补写 wiki 页。


class WikiCoverageGate:
    """编译质量守门：本体有核心节点但 wiki 页严重偏少 → BLOCK conclude.

    实现 ``krow_agent_sdk.protocols.GatePlugin`` Protocol。

    工作机制：扫描 ``recent_tool_results`` 里 ``knowledge_wiki_coverage_report``
    的输出，若 ``under_populated`` 为 true 或 wiki 页数 < ``min_wiki_pages`` 则 BLOCK。
    没调过覆盖核对工具 → DEFER（不强制必调，但 ACT prompt 引导收尾必调）。
    """

    plugin_id = "knowledge_wiki.coverage_gate"
    phase = "macro"

    def __init__(
        self,
        *,
        min_wiki_pages: int = 3,
        min_key_nodes: int = 3,
    ) -> None:
        self._min_pages = int(min_wiki_pages)
        self._min_nodes = int(min_key_nodes)

    def get_gate(self) -> Any:
        from krow_agent_sdk.protocols import (
            GateDecision,
            GateVerdict,
            make_simple_gate,
        )

        min_pages = self._min_pages
        min_nodes = self._min_nodes

        def evaluate(parsed: dict, context: dict) -> Any:
            tool_results = context.get("recent_tool_results", []) or []
            for tr in reversed(tool_results):
                if not isinstance(tr, dict):
                    continue
                if tr.get("tool_name") != "knowledge_wiki_coverage_report":
                    continue
                result = tr.get("result", {}) or {}
                if not result.get("ok"):
                    continue
                key_nodes = int(result.get("key_node_count", 0))
                wiki_pages = int(result.get("wiki_page_count", 0))
                under = bool(result.get("under_populated"))
                # 本体几乎没抽到东西 → 不归 coverage gate 管（DEFER，留给编译契约）
                if key_nodes < min_nodes:
                    return GateDecision(
                        verdict=GateVerdict.DEFER,
                        gate_name="wiki_coverage",
                    )
                if under or wiki_pages < min_pages:
                    return GateDecision(
                        verdict=GateVerdict.BLOCK,
                        reason=(
                            f"❌ 知识编译覆盖不足：本体有 {key_nodes} 个核心节点"
                            f"（概念+实体），但只写了 {wiki_pages} 篇 wiki 页"
                            f"（要求 ≥{min_pages}）\n"
                            "   位置：knowledge_wiki_coverage_report 输出 under_populated\n"
                            "   修法（两档词条模型 · 架构公理 D）：\n"
                            "     1. stub 红链词条由 knowledge_wiki_materialize（零 LLM）"
                            "自动物化——若还没调，先调它把本体节点确定性派生为词条\n"
                            "     2. 对 top-K 重要节点用 smart_file_write 写 tier: essay "
                            "精写页（人话论述，不是 JSON 转储；frontmatter 含 "
                            "title/type/tags/sources/status/tier）\n"
                            "     3. 写完重调 knowledge_wiki_coverage_report 复核\n"
                            "   规范依据：知识库的价值在于可浏览的词条网络；"
                            "stub 由系统物化，essay 由你精写——**不要**为覆盖每个节点"
                            "而批量手写 stub（撞 wiki_gate 空转）"
                        ),
                        gate_name="wiki_coverage",
                    )
                return GateDecision(
                    verdict=GateVerdict.ALLOW,
                    reason=(
                        f"✅ 编译覆盖达标：{key_nodes} 核心节点 / "
                        f"{wiki_pages} wiki 页（覆盖率 "
                        f"{result.get('coverage_ratio', 0):.0%}）"
                    ),
                    gate_name="wiki_coverage",
                )
            # 没调过覆盖核对工具 → DEFER
            return GateDecision(verdict=GateVerdict.DEFER, gate_name="wiki_coverage")

        return make_simple_gate(
            name="wiki_coverage", priority=82, evaluator=evaluate
        )


# ============================================================
# §6. EventListenerPlugin（三阶段编译进度 + 审计 jsonl）
# ============================================================
#
# 业务理由：
#   知识编译是长任务（多文件抽本体 + 写多页 wiki）；用户看不到进度容易以为
#   卡死。listener 按工具调用分类计数（抽取 / 关联 / 发布），实时报进度。


class CompileProgressListener:
    """知识编译三阶段实时进度 + 审计 jsonl.

    实现 ``krow_agent_sdk.protocols.EventListenerPlugin`` Protocol。

    三阶段计数（按工具名归类，对齐 knowledge_compile 契约）：
    - extract：extract_entities_from_text
    - relate：add_relation
    - publish：smart_file_write（写 .krow/wiki）
    """

    plugin_id = "knowledge_wiki.progress_listener"

    # 工具名 → 阶段映射（兼容内置工具名 + cookbook 三段封装名）
    _PHASE_TOOLS = {
        "extract_entities_from_text": "extract",
        "knowledge_wiki_extract_ontology": "extract",
        "add_relation": "relate",
        "knowledge_wiki_link_relations": "relate",
        "smart_file_write": "publish",
        "knowledge_wiki_materialize": "publish",
    }

    def __init__(
        self,
        *,
        verbose: bool = True,
        progress_log_path: str | Path | None = None,
    ) -> None:
        self._verbose = bool(verbose)
        self._step_count = 0
        self._phase_counts: dict[str, int] = {"extract": 0, "relate": 0, "publish": 0}
        self._gate_blocks = 0
        self._path: Path | None = (
            _normalize_path(progress_log_path) if progress_log_path else None
        )
        if self._path:
            with suppress(OSError):
                self._path.parent.mkdir(parents=True, exist_ok=True)

    def get_subscriptions(self) -> list[dict[str, Any]]:
        return [
            {"topic": "tool.call_completed", "handler": self._on_tool_done},
            {"topic": "progressive.step_start", "handler": self._on_step_start},
            {"topic": "progressive.step_completed", "handler": self._on_step_done},
            {"topic": "gate.blocked", "handler": self._on_gate_blocked},
            {"topic": "agent.task_complete", "handler": self._on_task_done},
            {"topic": "agent.task_failed", "handler": self._on_task_failed},
        ]

    def _append(self, record: dict[str, Any]) -> None:
        if not self._path:
            return
        with suppress(Exception):
            record.setdefault("timestamp", time.time())
            record.setdefault("timestamp_iso", time.strftime("%Y-%m-%dT%H:%M:%S"))
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _on_tool_done(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        tool_name = payload.get("tool_name", "")
        phase = self._PHASE_TOOLS.get(tool_name)
        if phase:
            self._phase_counts[phase] += 1
            if self._verbose:
                label = {
                    "extract": "🔍 抽取本体",
                    "relate": "🔗 补关系",
                    "publish": "📝 写 wiki 词条",
                }[phase]
                print(f"  {label} #{self._phase_counts[phase]}（{tool_name}）")
            self._append({
                "kind": "phase_progress",
                "phase": phase,
                "tool_name": tool_name,
                "count": self._phase_counts[phase],
            })

    def _on_step_start(self, event: Any) -> None:
        self._step_count += 1
        payload = getattr(event, "payload", {}) or {}
        if self._verbose:
            print(f"  [step {self._step_count}] {payload.get('description', '...')}")

    def _on_step_done(self, event: Any) -> None:
        if self._verbose:
            payload = getattr(event, "payload", {}) or {}
            elapsed = payload.get("elapsed_seconds", 0)
            print(f"  [step {self._step_count}] ✓ done ({elapsed:.1f}s)")

    def _on_gate_blocked(self, event: Any) -> None:
        self._gate_blocks += 1
        payload = getattr(event, "payload", {}) or {}
        if self._verbose:
            print(
                f"  ⛔ gate BLOCK: {payload.get('gate_name')} — "
                f"{(payload.get('reason') or '')[:80]}..."
            )
        self._append({
            "kind": "gate_blocked",
            "gate_name": payload.get("gate_name"),
            "reason_excerpt": (payload.get("reason") or "")[:200],
        })

    def _on_task_done(self, event: Any) -> None:
        if self._verbose:
            print(
                f"\n✅ 知识编译完成：{self._step_count} 步 / "
                f"抽取 {self._phase_counts['extract']} / "
                f"关系 {self._phase_counts['relate']} / "
                f"wiki {self._phase_counts['publish']} / "
                f"{self._gate_blocks} 次 gate block"
            )
        self._append({
            "kind": "task_complete",
            "step_count": self._step_count,
            "phase_counts": dict(self._phase_counts),
            "gate_blocks": self._gate_blocks,
        })

    def _on_task_failed(self, event: Any) -> None:
        payload = getattr(event, "payload", {}) or {}
        if self._verbose:
            print(f"\n❌ 编译失败：{payload.get('reason', 'unknown')}")
        self._append({"kind": "task_failed", "reason": payload.get("reason")})


__all__ = [
    "scan_knowledge_sources",
    "report_wiki_coverage",
    "extract_ontology_from_sources",
    "link_ontology_relations",
    "materialize_wiki_pages",
    "KnowledgeWikiToolPlugin",
    "KnowledgeWikiACTPlugin",
    "WikiCoverageGate",
    "CompileProgressListener",
]
