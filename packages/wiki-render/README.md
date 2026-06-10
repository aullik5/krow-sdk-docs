# @krow/wiki-render — Krow Wiki 渲染套件

> 方案 A 交付物（已收口为可发布共享包，位于仓库 `packages/wiki-render/`）。把桌面 Lite 版
> WikiView **内容区**的视觉与渲染逻辑抽离为框架无关的 Web 资产，让 Cloud Web Wiki 的词条
> 渲染**天然与桌面视觉一致**，且零业务耦合。
> **CSS 单一 SSOT**：`wiki-theme.css` 不是手维护的副本，而是由桌面运行时真源
> `ui/static/wiki/wiki_light_theme.css` 逐字节同步的镜像（`scripts/sync_theme.py`），
> 漂移由 `tests/unit/test_wiki_render_kit_css_ssot.py` 在 CI（unit.yml）fail-loud 守门。

## 这是什么

桌面 WikiView 的"前端"95% 是 PySide6/Qt 外壳（约 3466 行），无法复用到 Web。但其
**内容区**是 `QWebEngineView + 本地 HTML/CSS/JS`，这部分是 Web 可移植的，正是决定
"词条长什么样"的部分。本套件把它抽出来：

| 文件 | 来源 SSOT | 职责 |
| --- | --- | --- |
| `wiki-theme.css` | `ui/static/wiki/wiki_light_theme.css`（逐字节同步，**勿手改**） | 内容区视觉主题（配色 token + typography + callout + 表格 + 图表容器） |
| `wiki-render.js` | `ui/static/wiki/wiki_template.html` | 渲染引擎：Markdown→HTML + callout/mermaid/echarts/katex/highlight 后处理 + TOC 提取 + 链接 scheme 解析 |
| `demo.html` | —（新增） | 可直接双击打开的最小运行样例 |

## 与桌面的唯一架构差异

桌面端 Markdown→HTML 这一步在 **Python 侧**用 `markdown-it-py` 完成；Web 端把它挪回
**浏览器**，用 `markdown-it`（即 `markdown-it-py` 的 JS 原版）以**对齐配置**完成：

```js
new MarkdownIt('commonmark', { html: false, linkify: false, typographer: true })
  .enable(['table', 'strikethrough'])
```

因为是同一个库的两种语言实现 + 同一份配置，渲染结果可做到逐字一致。后处理（callout /
mermaid / echarts / katex / highlight / TOC）则与桌面 `wiki_template.html` 1:1 移植。

## 快速开始

直接看效果：用浏览器打开 `demo.html`（已用 CDN 引入 markdown-it）。

集成到你的前端工程：

```bash
npm i markdown-it
# 可选富内容：npm i mermaid echarts katex highlight.js
```

```js
import { createWikiRenderer, parseWikiHref } from './wiki-render.js';
import MarkdownIt from 'markdown-it';

const renderer = createWikiRenderer({ MarkdownIt });

// container 的 id 必须是 "wiki-content"（TOC 提取依赖此 id）
const headings = renderer.renderPage(containerEl, markdownText, frontmatter);
// headings → [{ level, text, id }]  可用于渲染右侧目录 TOC

// 拦截站内链接（wiki: / wiki-create: / wiki-upgrade: / source-navigate:）
containerEl.addEventListener('click', (e) => {
  const a = e.target.closest('a');
  const parsed = a && parseWikiHref(a.getAttribute('href'));
  if (parsed) { e.preventDefault(); routeTo(parsed.scheme, parsed.target); }
});
```

也别忘了引入主题：`<link rel="stylesheet" href="./wiki-theme.css">`。

## 可选富内容库（缺失时优雅降级，与桌面一致）

| 语法 | 需要的库 | 缺失时行为 |
| --- | --- | --- |
| ` ```mermaid ` | `mermaid` | 保留为普通代码块 |
| ` ```echarts ` | `echarts` | 显示"未加载"提示 + 原始配置 |
| `$...$` / `$$...$$` | `katex`（含 CSS） | 保留原始 LaTeX 文本 |
| 代码高亮 | `highlight.js`（含主题 CSS） | 无高亮的纯代码块 |

> 注：桌面端模板里也写了这些库的加载钩子，但 Python 侧从未真正注入这些库（优雅降级到
> 纯文本/代码块）。Web 端可按需开启，体验比桌面更完整。

## 链接 scheme 契约（与桌面一致）

| href 前缀 | 含义 | Web 端应做什么 |
| --- | --- | --- |
| `wiki:<rel_path>` | 站内跳转到另一篇词条 | 前端路由切到该页 |
| `wiki-create:<rel_path>` | 红链：目标页尚不存在 | 触发"创建此页"流程（可调编译任务） |
| `wiki-upgrade:<rel_path>` | stub 页升级为完整页 | 触发对该 stub 的补全任务 |
| `source-navigate:<source>` | 跳转到原始来源文件 | 打开来源文档预览 |

## SSOT 收口（已落地，避免两份漂移）

> 历史风险：若 Web 与桌面各自维护一份 CSS，半年后视觉必然分叉（违反 DRY/SSOT）。本包已做
> **CSS 单一 SSOT 收口**，无需再担心：

| 维度 | 收口做法 |
| --- | --- |
| **唯一 SSOT** | 桌面运行时真源 `ui/static/wiki/wiki_light_theme.css`（WikiView 实际加载的那份） |
| **包内镜像** | `packages/wiki-render/wiki-theme.css` 由 `scripts/sync_theme.py` 逐字节复制生成 |
| **漂移守门** | `tests/unit/test_wiki_render_kit_css_ssot.py` 断言两者字节一致，不一致即 CI fail-loud（unit.yml） |
| **修改流程** | 改主题只改桌面 SSOT → 跑 `python packages/wiki-render/scripts/sync_theme.py` → 提交（守门验证） |

JS 引擎（`wiki-render.js`）因桌面 Markdown→HTML 在 Python 侧、Web 在浏览器侧（两套运行时），
是**功能对齐的移植**而非逐字共享；后处理逻辑与桌面 `wiki_template.html` 1:1 对齐，升级时人工同步。

> **关于分发**（2026-06-10 起，MIT 许可）：本套件通过两条自助渠道对外分发——
> ① 公开文档仓 `krow-sdk-docs` 的 `packages/wiki-render/` 镜像（直接 vendor）；
> ② SDK wheel 随包资产 `krow_agent_sdk/assets/wiki_render/`（`pip install krow-agent-sdk`
> 后用 `krow_agent_sdk.assets.get_wiki_render_dir()` 定位）。
> `package.json` 的 `private: true` 仅防误发 npm（npm 发布暂缓，等真实需求），
> 不影响 MIT 许可下的 vendoring。


## 作为 npm 包使用（@krow/wiki-render）

本目录已是一个可发布的 npm 包骨架（`package.json`）。结构：

| 文件 | 作用 |
| --- | --- |
| `package.json` | 包元数据；`exports` 暴露 JS 入口与 `./theme.css`；`markdown-it` 为 peerDependency |
| `wiki-render.js` | ESM 源（直接可发布，无需构建——`markdown-it` 由调用方注入，包本身零硬依赖） |
| `wiki-render.d.ts` | TypeScript 类型声明 |
| `wiki-theme.css` | 主题，经 `@krow/wiki-render/theme.css` 导入 |
| `build.mjs` | 可选构建：用 esbuild 产出 `dist/`（CJS + 压缩 ESM），给非打包器消费者 |
| `.gitignore` | 忽略 `node_modules/` 与 `dist/` |

安装与使用（消费方工程）：

```bash
npm i @krow/wiki-render markdown-it
# 可选富内容：npm i mermaid echarts katex highlight.js
```

```js
import { createWikiRenderer, parseWikiHref } from "@krow/wiki-render";
import "@krow/wiki-render/theme.css";
import MarkdownIt from "markdown-it";

const renderer = createWikiRenderer({ MarkdownIt });
const headings = renderer.renderPage(containerEl, markdownText, frontmatter);
```

本地构建可选产物（仅当目标消费者不用打包器时需要）：

```bash
npm i -D esbuild@latest
npm run build      # → dist/wiki-render.cjs + dist/wiki-render.min.js
```

> 设计要点：`markdown-it` 通过 `createWikiRenderer({ MarkdownIt })` **依赖注入**，
> 包内不 `import "markdown-it"`，因此本包**零运行时硬依赖**，构建仅为兼容非 ESM 消费者，
> 多数现代前端工程直接用 `wiki-render.js` ESM 源即可，无需 `npm run build`。

> 注：npm registry 发布暂缓（等真实前端工程需求）；当前推荐直接 vendor 上述两条
> 自助渠道的文件——本包零运行时硬依赖，vendor 成本即 3 个文件。
