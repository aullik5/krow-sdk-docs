/**
 * Krow Wiki 渲染引擎 — Web 复用版（框架无关 ES module）
 * =====================================================================
 * 来源 SSOT：ui/static/wiki/wiki_template.html（桌面 WikiView 内容区 JS）
 *
 * 与桌面的差异（关键）：
 *   桌面端 Markdown→HTML 在 Python 侧用 markdown-it-py 完成，本模块把这一步
 *   挪回浏览器，用 markdown-it（markdown-it-py 的 JS 原版）以**对齐配置**保证
 *   渲染结果与桌面逐字一致。后处理（callout / mermaid / echarts / katex /
 *   highlight / TOC）逻辑则与桌面 1:1 移植。
 *
 * 依赖（全部可选，缺失时优雅降级，与桌面行为一致）：
 *   - markdown-it            （必需：Markdown→HTML；npm i markdown-it）
 *   - mermaid                （可选：```mermaid 代码块渲染流程图）
 *   - echarts                （可选：```echarts 代码块渲染图表）
 *   - katex                  （可选：$...$ / $$...$$ 数学公式）
 *   - highlight.js (hljs)    （可选：代码高亮）
 *
 * 用法：
 *   import { createWikiRenderer } from './wiki-render.js';
 *   import MarkdownIt from 'markdown-it';
 *   const renderer = createWikiRenderer({ MarkdownIt });
 *   const headings = renderer.renderPage(containerEl, markdownText, frontmatter);
 *   // headings: [{ level, text, id }]  → 可用于生成 TOC 目录
 *
 * 链接 scheme（与桌面契约一致，宿主自行拦截 container 的 click 事件处理）：
 *   wiki:<rel_path>            → 站内跳转到另一篇 wiki 页
 *   wiki-create:<rel_path>     → 红链：目标页不存在，触发"创建此页"
 *   wiki-upgrade:<rel_path>    → stub 页升级为完整页
 *   source-navigate:<source>   → 跳转到原始来源文件
 */

const WIKI_LINK_RE = /\[\[([^\]|]+)(?:\|[^\]]*)?\]\]/g;

function escapeHtml(s) {
  const d = document.createElement('div');
  d.appendChild(document.createTextNode(String(s == null ? '' : s)));
  return d.innerHTML;
}

const hasMermaid = () => typeof window !== 'undefined' && typeof window.mermaid !== 'undefined';
const hasECharts = () => typeof window !== 'undefined' && typeof window.echarts !== 'undefined';
const hasKaTeX = () => typeof window !== 'undefined' && typeof window.katex !== 'undefined';
const hasHljs = () => typeof window !== 'undefined' && typeof window.hljs !== 'undefined';

/**
 * 构造与桌面 markdown-it-py 对齐的 MarkdownIt 实例。
 * 桌面配置（ui/wiki_view.py:_markdown_to_html）：
 *   MarkdownIt("commonmark", { html: <有 sanitizer 时 true>, linkify: false, typographer: true })
 *     .enable(["table", "strikethrough"])
 */
function buildMarkdownIt(MarkdownIt, { allowHtml = false } = {}) {
  const md = new MarkdownIt('commonmark', {
    html: allowHtml,
    linkify: false,
    typographer: true,
  });
  md.enable(['table', 'strikethrough']);
  return md;
}

/** [[wiki-link]] → <a href="wiki:..."> （扩展语法的 |rel:..|weight:.. 元数据用于显示文本剥离） */
function transformWikiLinks(html) {
  return html.replace(WIKI_LINK_RE, (_m, target) => {
    const t = target.trim();
    return `<a href="wiki:${encodeURI(t)}" class="wiki-link">[[${escapeHtml(t)}]]</a>`;
  });
}

function processCallouts(container) {
  container.querySelectorAll('blockquote').forEach((bq) => {
    const firstP = bq.querySelector('p');
    if (!firstP) return;
    const m = firstP.textContent.match(/^\[!(NOTE|TIP|WARNING|IMPORTANT|CAUTION)\]\s*(.*)/);
    if (!m) return;
    const type = m[1];
    const rest = m[2];
    const div = document.createElement('div');
    div.className = 'callout callout-' + type;
    div.innerHTML =
      '<div class="callout-title">' + escapeHtml(type) + '</div>' +
      '<p>' + escapeHtml(rest) + '</p>';
    let sibling = firstP.nextElementSibling;
    while (sibling) {
      div.appendChild(sibling.cloneNode(true));
      sibling = sibling.nextElementSibling;
    }
    bq.parentNode.replaceChild(div, bq);
  });
}

function processMermaid(container) {
  const blocks = container.querySelectorAll('pre code.language-mermaid');
  if (blocks.length === 0) return;
  blocks.forEach((code) => {
    const pre = code.parentElement;
    const div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = code.textContent;
    pre.parentNode.replaceChild(div, pre);
  });
  if (hasMermaid()) {
    try {
      window.mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'strict' });
      window.mermaid.run({ querySelector: '.mermaid' });
    } catch (e) {
      console.warn('Mermaid render error:', e);
    }
  }
}

function processECharts(container) {
  const blocks = container.querySelectorAll('pre code.language-echarts');
  if (blocks.length === 0) return;
  blocks.forEach((code) => {
    const pre = code.parentElement;
    const config = code.textContent;
    const id = 'echart-' + Math.random().toString(36).slice(2, 11);
    const div = document.createElement('div');
    div.id = id;
    div.className = 'echarts-container';
    pre.parentNode.replaceChild(div, pre);

    if (hasECharts()) {
      setTimeout(() => {
        try {
          const chart = window.echarts.init(document.getElementById(id));
          chart.setOption(JSON.parse(config));
        } catch (e) {
          const el = document.getElementById(id);
          if (el) el.innerHTML = '<div class="echarts-error">ECharts 配置无效: ' + escapeHtml(e.message) + '</div>';
        }
      }, 50);
    } else {
      div.innerHTML =
        '<div class="echarts-error">ECharts 库未加载，显示原始配置</div>' +
        '<pre><code>' + config.replace(/</g, '&lt;') + '</code></pre>';
    }
  });
}

function processKaTeX(container) {
  if (!hasKaTeX()) return;
  let html = container.innerHTML;
  html = html.replace(/\$\$([\s\S]+?)\$\$/g, (m, tex) => {
    try { return window.katex.renderToString(tex.trim(), { displayMode: true, throwOnError: false }); }
    catch (e) { return m; }
  });
  html = html.replace(/(?<![\\$])\$([^$\n]+?)\$/g, (m, tex) => {
    try { return window.katex.renderToString(tex.trim(), { displayMode: false, throwOnError: false }); }
    catch (e) { return m; }
  });
  container.innerHTML = html;
}

function processHighlight(container) {
  if (!hasHljs()) return;
  container.querySelectorAll('pre code[class*="language-"]').forEach((code) => {
    if (code.classList.contains('language-mermaid') || code.classList.contains('language-echarts')) return;
    try { window.hljs.highlightElement(code); } catch (e) { /* 语言不支持时静默跳过 */ }
  });
}

function buildInfoBar(frontmatter) {
  const fm = frontmatter || {};
  const confIcon = { high: '\u{1F7E2}', medium: '\u{1F7E1}', low: '\u{1F534}' }[fm.confidence] || '\u26AA';
  const rawSources = fm.sources || [];
  const sourcesHtml = rawSources.length
    ? rawSources.map((s) => `<a href="source-navigate:${encodeURIComponent(s)}" class="source-link">${escapeHtml(s)}</a>`).join(', ')
    : '-';
  return '<div class="info-bar">\u2728 \u81EA\u52A8\u6574\u7406 \u00B7 ' +
    confIcon + escapeHtml(fm.confidence || '') +
    ' \u00B7 \u6765\u6E90: ' + sourcesHtml + '</div>';
}

function extractToc() {
  const headings = [];
  document.querySelectorAll('#wiki-content h1, #wiki-content h2, #wiki-content h3').forEach((h) => {
    const id = h.id || h.textContent.replace(/\s+/g, '-');
    h.id = id;
    headings.push({ level: parseInt(h.tagName[1], 10), text: h.textContent, id });
  });
  return headings;
}

/**
 * 创建一个 wiki 渲染器。
 * @param {object} deps
 * @param {Function} deps.MarkdownIt  markdown-it 构造函数（必需）
 * @param {boolean}  [deps.allowHtml] 是否允许原始 HTML（默认 false；建议配合服务端/DOMPurify 消毒）
 */
export function createWikiRenderer({ MarkdownIt, allowHtml = false } = {}) {
  if (!MarkdownIt) throw new Error('createWikiRenderer 需要传入 MarkdownIt（npm i markdown-it）');
  const md = buildMarkdownIt(MarkdownIt, { allowHtml });

  /** Markdown 字符串 → HTML（含 [[wiki-link]] 转换），不做 DOM 后处理 */
  function markdownToHtml(text) {
    return transformWikiLinks(md.render(text || ''));
  }

  /**
   * 渲染一篇 wiki 页面到容器。
   * @param {HTMLElement} containerEl 必须是 id="wiki-content" 的容器（TOC 提取依赖此 id）
   * @param {string} markdownText     页面 markdown 正文（不含 frontmatter）
   * @param {object} frontmatter      frontmatter 字段（title/type/sources/confidence/...）
   * @returns {Array} headings TOC 数组
   */
  function renderPage(containerEl, markdownText, frontmatter) {
    const bodyHtml = markdownToHtml(markdownText);
    containerEl.innerHTML = buildInfoBar(frontmatter) + bodyHtml;
    // 后处理顺序关键：先 Mermaid/ECharts 替换代码块，再 highlight 其余代码块，最后 KaTeX
    processCallouts(containerEl);
    processMermaid(containerEl);
    processECharts(containerEl);
    processHighlight(containerEl);
    processKaTeX(containerEl);
    return extractToc();
  }

  /** 仅渲染 dashboard / 自定义 HTML（不走 markdown，不加 info-bar） */
  function showHtml(containerEl, html) {
    containerEl.innerHTML = html;
  }

  return { renderPage, showHtml, markdownToHtml };
}

/** 解析 wiki 自定义 scheme 链接（供宿主拦截 click 用）。返回 {scheme, target} 或 null。 */
export function parseWikiHref(href) {
  if (!href) return null;
  for (const scheme of ['wiki-create', 'wiki-upgrade', 'source-navigate', 'wiki']) {
    const prefix = scheme + ':';
    if (href.startsWith(prefix)) {
      return { scheme, target: decodeURIComponent(href.slice(prefix.length)) };
    }
  }
  return null;
}

export default createWikiRenderer;
