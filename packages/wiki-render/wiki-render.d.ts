// 类型声明 — @krow/wiki-render
export interface WikiFrontmatter {
  title?: string;
  type?: string;
  sources?: string[];
  related?: string[];
  confidence?: "high" | "medium" | "low";
  [key: string]: unknown;
}

export interface TocHeading {
  level: number;
  text: string;
  id: string;
}

export interface WikiRenderer {
  /** 渲染一篇 wiki 页面到容器（container.id 必须为 "wiki-content"）。返回 TOC headings。 */
  renderPage(container: HTMLElement, markdownText: string, frontmatter?: WikiFrontmatter): TocHeading[];
  /** 渲染自定义 HTML（dashboard 等，不走 markdown，不加 info-bar）。 */
  showHtml(container: HTMLElement, html: string): void;
  /** 仅做 Markdown→HTML（含 [[wiki-link]] 转换），不做 DOM 后处理。 */
  markdownToHtml(text: string): string;
}

export interface CreateWikiRendererOptions {
  /** markdown-it 构造函数（必需，由调用方注入：import MarkdownIt from "markdown-it"）。 */
  MarkdownIt: unknown;
  /** 是否允许原始 HTML（默认 false；建议配合服务端/DOMPurify 消毒）。 */
  allowHtml?: boolean;
}

export function createWikiRenderer(opts: CreateWikiRendererOptions): WikiRenderer;

export type WikiScheme = "wiki" | "wiki-create" | "wiki-upgrade" | "source-navigate";

export interface ParsedWikiHref {
  scheme: WikiScheme;
  target: string;
}

/** 解析 wiki 自定义 scheme 链接（供宿主拦截 click 用）。 */
export function parseWikiHref(href: string): ParsedWikiHref | null;

declare const _default: typeof createWikiRenderer;
export default _default;
