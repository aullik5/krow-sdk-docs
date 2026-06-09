# 方案 B · Wiki 前端信息架构与交互契约规范

> 把桌面 WikiView（约 3466 行 Qt 代码）里**藏在代码中的产品设计**提炼成框架无关的规范，
> 供你用现代 Web 框架（React/Vue）重做外壳 shell 时直接照搬，不必逆向桌面 Qt 代码。
> 配合方案 A 的渲染套件，可在保证视觉一致的同时快速搭出 Web Wiki。

本文不含 Qt 代码细节，只描述"产品长什么样、各部分数据从哪来、交互怎么走"。

---

## 1. 整体布局（三栏 + 顶栏）

桌面 WikiView 采用经典百科布局，建议 Web 沿用：

```
┌──────────────────────────────────────────────────────────────┐
│  顶栏 NavBar：← → 🏠 | 面包屑 Breadcrumb | 🔍 搜索 | ⚙️ | 编译状态  │
├────────────┬─────────────────────────────────────────────────┤
│            │                                                  │
│  左栏       │   主内容区（方案 A 渲染套件 #wiki-content）         │
│  侧边树     │   info-bar · 正文 · related-pages · infobox       │
│  Sidebar   │                                                  │
│  (页面树)   │                                                  │
│            │                                                  │
└────────────┴─────────────────────────────────────────────────┘
```

| 区域 | 桌面实现 | Web 数据来源（见方案 C BFF） |
| --- | --- | --- |
| 顶栏导航 | NavBar widget | 前端状态（history 栈）+ 编译状态 SSE |
| 左栏侧边树 | Sidebar tree | `GET /wiki/pages`（按 subdir / type 分组） |
| 主内容区 | QWebEngineView | `GET /wiki/page?path=...` → 方案 A `renderPage()` |
| 编译状态条 | mini-bar | `GET /agent/stream/{task_id}` SSE |

---

## 2. 页面类型（Page Type）元数据 SSOT

桌面 `_WIKI_TYPE_META` 定义了 wiki 的核心信息分类。**Web 必须照搬这套枚举**（侧边树分组、
图标、frontmatter `type` 字段全依赖它）：

| type | 图标 | 标签 | 物理子目录 |
| --- | --- | --- | --- |
| `concept` | 💡 | 知识主题 | `concepts/` |
| `entity` | 🏢 | 人物与组织 | `entities/` |
| `event` | 📅 | 事件 | `events/` |
| `source-summary` | 📄 | 文档摘要 | `sources/` |
| `comparison` | ⚖️ | 对比分析 | `comparisons/` |
| `overview` | 📖 | 概览 | （根目录） |
| `unknown` | 📝 | 其他 | （根目录） |

> 物理目录 = 语义分类。`.krow/wiki/concepts/react.md` 的 `type` 一定是 `concept`。
> 侧边树即按这 5 个子目录（+ 根目录 overview）分组。

---

## 3. 页面数据模型（frontmatter 契约）

每篇词条 = `YAML frontmatter + Markdown 正文 + [[wiki-link]] 内链`。frontmatter 契约：

```yaml
---
title: 页面标题（简洁准确）
type: concept | entity | event | source-summary | comparison | overview
sources:                 # 引用的原始文件名列表
  - quarterly-report-2026-Q1.pdf
related:                 # 显式关联页（相对路径）
  - concepts/related-topic.md
created: YYYY-MM-DD
updated: YYYY-MM-DD
confidence: high | medium | low   # 渲染 info-bar 的 🟢🟡🔴 信号
human_edited: false      # 人工编辑过 → 系统不自动覆盖
archived: false
schema_version: "1.2"
---
```

**关键约束（防 SSOT 漂移，Web 端务必遵守）**：
- frontmatter **只放表达层信息**，不要内嵌实体/关系结构化数据。
- 实体/关系由 GlobalOntology（`.krow/ontology/global.db`）单一持有。
- 页内关系通过**扩展 wiki-link 语法**表达：`[[entities/foo|rel:causes|weight:strong|role:agent]]`，
  系统自动从 link 解析出 ontology 边。Web 渲染时只显示 `foo`，元数据部分剥离（方案 A 已处理）。

---

## 4. 链接 scheme 语义（站内导航契约）

桌面用自定义 URL scheme 驱动站内交互，方案 A 的 `parseWikiHref()` 已能解析。Web 宿主需
对每种 scheme 实现对应动作：

| scheme | 触发场景 | Web 端动作 |
| --- | --- | --- |
| `wiki:<rel_path>` | 点击 `[[wiki-link]]` 或相关页 | 前端路由跳到该词条（`GET /wiki/page`） |
| `wiki-create:<rel_path>` | 目标页不存在（红链） | 弹"创建此页" → 提交编译任务（`POST /wiki/compile`，限定 target） |
| `wiki-upgrade:<rel_path>` | stub 页（仅占位）想补全 | 提交"补全该页"任务 |
| `source-navigate:<source>` | 点击 info-bar 来源 | 打开原始来源文件预览（`GET /files/read`） |

**红链（dangling link）**：指向尚未生成的页面。桌面会渲染成可点击的"创建此页"。Web 应保留
这一 UX——它是知识库"自生长"的关键入口。

---

## 5. 主内容区的三个组成部分

桌面主内容区由上到下依次为：

### 5.1 info-bar（信息栏）
显示 `✨ 自动整理 · {置信度图标}{confidence} · 来源: {可点击来源链接}`。
方案 A `renderPage()` 已根据 frontmatter 自动生成。

### 5.2 正文（body）
Markdown 渲染产物。方案 A 负责。

### 5.3 related-pages（相关页面）+ infobox
- **related-pages**：三类关联——
  - `related` frontmatter 显式关联
  - **反向链接 backlinks**（哪些页引用了本页）
  - **图社区 See also**（GlobalOntology 社区检测的同簇节点）
- **infobox**（仅 entity / 有 `ontology_id` 的页）：从 ontology 拉结构化字段（类似维基百科右侧信息框）。

> 这两块数据来自后端（BFF 需提供 `neighbors` / ontology 查询）。Web 可一期先做 related，
> 二期再做 infobox。

---

## 6. 侧边树（Sidebar）组织规则

- **默认模式**：按 `_WIKI_TYPE_META` 的 5 个子目录分组（💡知识主题 / 🏢人物与组织 / 📄文档摘要 / …），
  组内按 title 排序。
- **可选 taxonomy 模式**：按 ontology 分类层级组织（桌面有此开关，Web 可二期再做）。
- 每个节点显示 `{type 图标} {title}`，点击 → `wiki:` 跳转。

---

## 7. 搜索（Search）

- 入口：顶栏搜索框。
- 后端：全文检索（桌面走 SQLite FTS BM25）。
- 降级：FTS 不可用时回退到文件内容 grep。
- Web 对接：`GET /wiki/search?q=...`（见方案 C）。结果项含 `path / title / type / 摘要片段`。

---

## 8. 编译状态可视化（Compile Status）

桌面在顶栏有"编译状态 mini-bar"，反映三阶段编译进度。Web 应订阅 SSE 展示：

| 阶段 | 含义 | 事件信号 |
| --- | --- | --- |
| Phase 1 抽取 | 从源文档抽概念/实体入 ontology | `agent.step.update` + 工具 `extract_entities_from_text` |
| Phase 2 关联 | LLM 推断关系落库 | 工具 `add_relation` |
| Phase 3 发布 | 写 `.krow/wiki/*.md` 词条 | 工具 `smart_file_write` / `materialize` |

桌面订阅的事件（Web 通过 SSE 等价获得）：
`wiki.page_written` / `wiki.compile.started` / `wiki.compile.finished` /
`background_task.started|completed|failed`。

---

## 9. 不要复用 / 需重写的部分（明确边界）

| 桌面部分 | 为什么不复用 | Web 替代 |
| --- | --- | --- |
| 全部 Qt chrome（toolbar/sidebar/对话框/Toast/齿轮菜单/前进后退栈） | 是 PySide6 widget + QSS + paintEvent，约 3000+ 行 | 用 React/Vue 按本规范重写，配色照搬方案 A 的 `:root` token |
| dashboard 内联样式 | 在 Python 字符串里 | 用方案 A 的 CSS 变量重写 dashboard 卡片 |
| 进程内事件总线订阅 | 桌面进程内事件总线 | 改为 SSE（方案 C `GET /agent/stream`） |
| 进程内 `KnowledgeAPI` / `WikiCompiler` 直接 Python 调用 | 桌面进程内 API | 改为 BFF REST（方案 C） |
| 桌面后台任务队列投递 | 桌面后台任务队列 | 改为 `POST /agent/execute`（方案 C） |

---

## 10. Web 实现建议的最小信息架构（落地清单）

一期 MVP 建议实现：

1. 三栏布局 + 顶栏（配色用方案 A token）
2. 侧边树（按 5 类分组，数据来自 `GET /wiki/pages`）
3. 词条页（方案 A `renderPage()` + info-bar + related-pages）
4. 搜索（`GET /wiki/search`）
5. 站内 4 种 scheme 链接路由（`parseWikiHref()`）
6. 编译任务触发 + SSE 进度条（`POST /wiki/compile` + `GET /agent/stream`）

二期增强：infobox（ontology 结构化）、taxonomy 侧边树、知识图谱视图、红链/stub 补全工作流。
