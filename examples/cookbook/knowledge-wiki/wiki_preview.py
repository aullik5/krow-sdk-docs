"""Wiki 前端预览生成器（端到端 handoff · 零 LLM · 确定性）.

把编译产出的 ``<project>/.krow/wiki/**/*.md`` 词条渲染成一个**可双击打开**的
静态站点 ``output/wiki_preview/index.html``，复用仓库里的官方前端渲染包
``packages/wiki-render/``（``@krow/wiki-render``，与桌面 WikiView 同源），
演示 SDK 开发者拿到 ``.krow/wiki`` 后如何在 Web 端富渲染（Markdown +
``[[wiki-link]]`` 站内跳转 + mermaid 关系图 + katex + 代码高亮）。

设计要点（与 docs/zeru/wiki_web_handoff 方案 A 对齐）：
- **不重写渲染器**：直接拷贝 ``wiki-render.js`` + ``wiki-theme.css`` 到预览目录，
  浏览器侧 ``createWikiRenderer`` 渲染（SSOT 铁律：渲染逻辑只有一份）。
- **零依赖可离线骨架**：页面数据以 JSON 内联，markdown-it / mermaid / katex /
  highlight.js 从 CDN 按需加载，缺失时优雅降级（与渲染器契约一致）。
- **确定性**：纯 Python 解析 frontmatter + 切正文，不调用任何 LLM。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

# packages/wiki-render 相对本文件的位置：
#   packages/krow-agent-sdk/examples/cookbook/knowledge-wiki/wiki_preview.py
#   packages/wiki-render/
_HERE = Path(__file__).resolve().parent
_WIKI_RENDER_PKG = (
    _HERE.parents[3] / "wiki-render"  # …/packages/wiki-render
)

_CATEGORY_LABEL = {
    "concepts": "概念",
    "entities": "实体",
    "sources": "来源",
    "comparisons": "对比",
    "events": "事件",
    "overview": "总览",
}


def _split_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    """极简 frontmatter 解析（确定性，不引 yaml 依赖）。

    返回 ``(frontmatter_dict, body_markdown)``。只解析渲染器需要的标量 +
    简单 list（``sources``/``tags``/``related``）；解析失败回退为空 fm + 原文。
    """
    t = text.lstrip("\ufeff")
    if not t.startswith("---"):
        return {}, text
    end = t.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = t[3:end].strip("\n")
    body = t[end + 4:].lstrip("\n")
    fm: Dict[str, Any] = {}
    cur_list_key: str | None = None
    for raw in fm_block.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("- ") and cur_list_key:
            fm.setdefault(cur_list_key, []).append(
                line.lstrip()[2:].strip().strip("\"'")
            )
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if not val:
            cur_list_key = key
            fm[key] = []
            continue
        cur_list_key = None
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [
                x.strip().strip("\"'") for x in inner.split(",") if x.strip()
            ] if inner else []
        else:
            fm[key] = val.strip("\"'")
    return fm, body


def _collect_pages(wiki_dir: Path) -> List[Dict[str, Any]]:
    pages: List[Dict[str, Any]] = []
    for md in sorted(wiki_dir.rglob("*.md")):
        name = md.name.lower()
        if name.startswith(("_", ".")) or name in {"schema.md", "readme.md"}:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        fm, body = _split_frontmatter(text)
        # 软删除墓碑跳过
        if str(fm.get("deleted", "")).lower() in {"true", "1", "yes"}:
            continue
        rel = md.relative_to(wiki_dir).as_posix()
        rel_no_ext = rel[:-3] if rel.endswith(".md") else rel
        category = rel.split("/", 1)[0] if "/" in rel else "overview"
        title = (
            str(fm.get("title") or "").strip()
            or md.stem.replace("-", " ").replace("_", " ")
        )
        pages.append(
            {
                "path": rel_no_ext,  # 与 [[wiki-link]] target 对齐（无扩展名）
                "rel": rel,
                "category": category,
                "title": title,
                "tier": str(fm.get("tier") or "").strip(),
                "type": str(fm.get("type") or "").strip(),
                "frontmatter": fm,
                "body": body,
            }
        )
    return pages


def render_wiki_preview(project_dir: Path, output_dir: Path) -> Dict[str, Any]:
    """读 ``project_dir/.krow/wiki`` → 生成 ``output_dir/wiki_preview/index.html``。

    返回 ``{ok, page_count, index_html, summary}``。
    """
    wiki_dir = Path(project_dir) / ".krow" / "wiki"
    if not wiki_dir.exists():
        return {
            "ok": False,
            "page_count": 0,
            "summary": f"未找到 wiki 目录：{wiki_dir}",
        }

    pages = _collect_pages(wiki_dir)
    if not pages:
        return {
            "ok": False,
            "page_count": 0,
            "summary": f"wiki 目录为空（无可渲染词条）：{wiki_dir}",
        }

    preview_dir = Path(output_dir) / "wiki_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    # 1) 拷贝官方渲染器资产（SSOT：不重写）
    assets_ok = True
    for asset in ("wiki-render.js", "wiki-theme.css"):
        src = _WIKI_RENDER_PKG / asset
        if src.exists():
            shutil.copy2(src, preview_dir / asset)
        else:  # 渲染器包缺失时仍出 HTML（内联兜底样式）
            assets_ok = False

    # 2) 生成 index.html（页面数据 JSON 内联）
    page_map = {p["path"]: p for p in pages}
    data_json = json.dumps(
        {"pages": pages, "page_map_keys": list(page_map.keys())},
        ensure_ascii=False,
    )
    index_html = _build_index_html(pages, data_json, assets_ok)
    index_path = preview_dir / "index.html"
    index_path.write_text(index_html, encoding="utf-8")

    by_cat: Dict[str, int] = {}
    n_essay = 0
    for p in pages:
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
        if p["tier"] == "essay":
            n_essay += 1
    cat_str = "，".join(
        f"{_CATEGORY_LABEL.get(c, c)} {n}" for c, n in sorted(by_cat.items())
    )
    return {
        "ok": True,
        "page_count": len(pages),
        "essay_count": n_essay,
        "stub_count": len(pages) - n_essay,
        "index_html": str(index_path),
        "by_category": by_cat,
        "summary": (
            f"前端预览已生成：{len(pages)} 篇词条（{cat_str}；essay {n_essay} / "
            f"stub {len(pages) - n_essay}）→ {index_path}"
        ),
    }


def _build_index_html(
    pages: List[Dict[str, Any]], data_json: str, assets_ok: bool
) -> str:
    """三栏 wiki 浏览器骨架。数据内联，渲染走 ./wiki-render.js（CDN 加载依赖）。"""
    # 侧栏分组（按 category）
    cats: Dict[str, List[Dict[str, Any]]] = {}
    for p in pages:
        cats.setdefault(p["category"], []).append(p)
    nav_items: List[str] = []
    for cat in sorted(cats.keys()):
        label = _CATEGORY_LABEL.get(cat, cat)
        nav_items.append(f'<div class="nav-group">{label}</div>')
        for p in sorted(cats[cat], key=lambda x: x["title"]):
            tier_badge = (
                ' <span class="tier tier-essay">essay</span>'
                if p["tier"] == "essay"
                else ' <span class="tier tier-stub">stub</span>'
            )
            safe_title = (
                p["title"].replace("&", "&amp;").replace("<", "&lt;")
            )
            nav_items.append(
                f'<a class="nav-link" data-path="{p["path"]}" '
                f'href="javascript:void(0)">{safe_title}{tier_badge}</a>'
            )
    nav_html = "\n".join(nav_items)

    theme_link = (
        '<link rel="stylesheet" href="./wiki-theme.css">' if assets_ok else ""
    )
    renderer_import = (
        "import { createWikiRenderer, parseWikiHref } from './wiki-render.js';"
        if assets_ok
        else (
            "const createWikiRenderer = ({MarkdownIt}) => ({"
            "renderPage:(el,md)=>{el.innerHTML=new MarkdownIt().render(md||'');"
            "return [];}}); const parseWikiHref=(h)=>"
            "h&&h.startsWith('wiki:')?{scheme:'wiki',target:"
            "decodeURIComponent(h.slice(5))}:null;"
        )
    )

    return _INDEX_TEMPLATE.format(
        nav_html=nav_html,
        data_json=data_json.replace("</", "<\\/"),
        theme_link=theme_link,
        renderer_import=renderer_import,
        page_count=len(pages),
    )


_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Krow Wiki 预览</title>
{theme_link}
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github.min.css">
<style>
  :root {{ --side: 280px; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: -apple-system, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", sans-serif; color: #1f2328; background: #fff; }}
  .layout {{ display: grid; grid-template-columns: var(--side) 1fr; min-height: 100vh; }}
  aside {{ border-right: 1px solid #e5e7eb; padding: 16px 12px; overflow-y: auto;
    height: 100vh; position: sticky; top: 0; background: #fafbfc; }}
  aside h1 {{ font-size: 15px; margin: 0 0 4px; }}
  aside .meta {{ color: #6b7280; font-size: 12px; margin-bottom: 12px; }}
  .nav-group {{ font-size: 12px; color: #6b7280; text-transform: uppercase;
    letter-spacing: .04em; margin: 14px 0 4px; }}
  .nav-link {{ display: block; padding: 5px 8px; border-radius: 6px;
    color: #1f2328; text-decoration: none; font-size: 14px; }}
  .nav-link:hover {{ background: #eef1f4; }}
  .nav-link.active {{ background: #dbeafe; font-weight: 600; }}
  .tier {{ font-size: 10px; padding: 1px 5px; border-radius: 8px; vertical-align: middle; }}
  .tier-essay {{ background: #dcfce7; color: #166534; }}
  .tier-stub {{ background: #f3f4f6; color: #6b7280; }}
  main {{ padding: 32px 48px; max-width: 900px; }}
  .info-bar {{ color: #6b7280; font-size: 13px; margin-bottom: 16px; }}
  .wiki-link {{ color: #2563eb; text-decoration: none; }}
  .wiki-link:hover {{ text-decoration: underline; }}
  .callout {{ border-left: 4px solid #60a5fa; background: #eff6ff;
    padding: 8px 14px; border-radius: 4px; margin: 12px 0; }}
  .callout-title {{ font-weight: 700; }}
  pre {{ background: #f6f8fa; padding: 12px; border-radius: 6px; overflow-x: auto; }}
  code {{ font-family: "SFMono-Regular", Consolas, monospace; font-size: 13px; }}
  table {{ border-collapse: collapse; }}
  th, td {{ border: 1px solid #d0d7de; padding: 6px 12px; }}
  .empty {{ color: #9ca3af; padding-top: 80px; text-align: center; }}
</style>
</head>
<body>
<div class="layout">
  <aside>
    <h1>📖 Krow Wiki</h1>
    <div class="meta">{page_count} 篇词条 · @krow/wiki-render</div>
    <nav id="nav">{nav_html}</nav>
  </aside>
  <main id="wiki-content"><div class="empty">← 从左侧选择一篇词条</div></main>
</div>

<script id="wiki-data" type="application/json">{data_json}</script>
<!-- markdown-it（必需）；mermaid/katex/highlight 可选，缺失时优雅降级 -->
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
<script type="module">
import MarkdownIt from 'https://esm.sh/markdown-it@14';
{renderer_import}

const DATA = JSON.parse(document.getElementById('wiki-data').textContent);
const PAGES = {{}};
for (const p of DATA.pages) PAGES[p.path] = p;
const renderer = createWikiRenderer({{ MarkdownIt }});
const content = document.getElementById('wiki-content');

function show(path) {{
  const p = PAGES[path];
  if (!p) {{ content.innerHTML = '<div class="empty">页面不存在：' + path + '</div>'; return; }}
  renderer.renderPage(content, p.body, p.frontmatter || {{}});
  document.querySelectorAll('.nav-link').forEach((a) =>
    a.classList.toggle('active', a.dataset.path === path));
  history.replaceState(null, '', '#' + encodeURIComponent(path));
  content.scrollTo(0, 0);
}}

document.getElementById('nav').addEventListener('click', (e) => {{
  const a = e.target.closest('.nav-link');
  if (a) show(a.dataset.path);
}});

// 拦截站内 [[wiki-link]] 跳转（wiki: / wiki-create: scheme）
content.addEventListener('click', (e) => {{
  const a = e.target.closest('a');
  if (!a) return;
  const parsed = parseWikiHref(a.getAttribute('href'));
  if (!parsed) return;
  e.preventDefault();
  let t = parsed.target.replace(/\\.md$/, '');
  if (PAGES[t]) show(t);
  else content.insertAdjacentHTML('afterbegin',
    '<div class="callout callout-WARNING"><div class="callout-title">红链</div>'
    + '<p>目标词条尚未成页：' + t + '</p></div>');
}});

const first = (location.hash ? decodeURIComponent(location.hash.slice(1)) : '')
  || (DATA.pages[0] && DATA.pages[0].path);
if (first) show(first);
</script>
</body>
</html>
"""
