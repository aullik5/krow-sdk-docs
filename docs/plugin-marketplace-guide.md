# Krowwork 市场插件包（`plugin.json`）· 插件开发与上架指南

> 面向第三方开发者。适用插件格式：`krow-plugin/1`。本文讲的是**Krowwork 市场插件包**——打成 `tar.gz`、上架到 Krowwork 插件市场、由主人装给**平台组员**的能力包；它与 Krow Agent SDK 的 **SDK Plugin Protocol**（Python 协议类，`AgentBuilder.with_*_plugin`，见 [`api-reference.md`](./api-reference.md) §5）**不是同一套东西**，不要混用。
> 本指南按 2026-10-23 的平台实现与 Krow Agent SDK `0.9.5.27` 核对；凡写「以平台公告为准」的事项，表示本指南不作承诺，请以插件市场页面与平台公告为准。
> **范围与状态**：第 1–4 节（概念与运行模式、插件格式、开发规范、本地自测）按已验证的代码与 SDK 行为写成，可直接照做；第 5–6 节的**生产侧「提交 → 审核 → 分发安装」三段属于规划 / 实验阶段，以平台公告为准**，本指南不把它们表述为已上线或已验证，也不构成任何生产操作授权（详见第 8 节）。
> 网页里「插件市场 › 开发者 › 开发文档」也有一份简版。两者有出入时以本指南与平台实际检查结果为准。

---

## 目录

1. 概览
2. 快速开始
3. 开发规范
4. 本地自测
5. 上架流程
6. 开发者接口参考
7. 常见问题
8. 范围与状态说明（规划 / 实验）

---

## 1. 概览

### 1.1 插件是什么

插件是 KrowWork 的**能力售卖单位**，装在**组员**身上（不是装给整个小组）。一个插件可以带三类组件，**至少要有一类**：

| 组件 | 包内位置 | 是什么 | 组员拿到后 |
|---|---|---|---|
| 技能 | `skills/<技能名>/SKILL.md` | 一份或多份技能说明：什么时候用、一步步怎么做 | 落到组员的技能目录；平台组员由模型按 `description` 在 `krow skill list` 里挑选后读取，外部工作台组员由各自 CLI 的技能机制触发。`description` 写得准，技能才会被想起 |
| 工具 | `tools/<python 包>/` | 一个纯 Python 包，对外暴露若干可调用工具 | 注册到平台组员的工具表，模型用 `` ```tool `` 块或 `krow tool run <工具名> --arg k=v`（长文本参数用 `--arg-file k=<文件>`）调用，用 `krow tool list / help` 发现与查参数；外部工作台组员**不接工具** |
| 连接 | `mcp.json` | MCP 服务器声明：stdio（本地进程）或 url（远程） | stdio 由组员工作台拉起；url 型会成为该组员的连接器，需要授权的由主人到连接器页授权 |

另外可以带一份 `README.md`，作为市场详情页的正文。

### 1.2 能力边界（当前实现）

- **运行模式：只面向 klik，不支持 Turbo**。本指南描述的是组员在 klik 运行模式（SDK 0.9.5 起的缺省模式，也是平台组员的缺省模式）下技能与工具的加载和调用面；Turbo 仅为回退模式、平台计划退役（治理决定，非代码现状），本指南不支持 Turbo 模式，也不提供兼容路径。运行模式由平台按角色配置，插件不能选择也不需要适配（工具组件在两种模式下都只经同一套宿主工具表注册，但 Turbo 下的行为本指南不描述、不承诺）。
- **社区层不分发可执行代码**：社区层插件的 `tools/` 整棵剥离，技能里的 `scripts/` 也会剥离。社区层插件实际能用的是「技能 + 连接」。分发工具代码要走**合作伙伴层**（需与平台签约开通）。
- **平台不会替插件安装 Python 依赖**：组员端只把 `tools/` 加进 `sys.path` 再 import，`pyproject.toml` 里的依赖不会生效；带 C 扩展的包不支持。
- **插件里不能带任何密钥**：url 型 MCP 的 OAuth 只能写公开客户端配置，`client_secret`、访问令牌由主人在连接器页填写。
- **外部工作台（BYO）组员**：可以装插件，但只拿到**技能**——平台把 `skills/` 投影到三个 CLI 技能目录（**同时写入** Claude Code `.claude/skills`、Cursor `.cursor/skills`、Codex `.codex/skills`；Codex 设了 `CODEX_HOME` 时写 `$CODEX_HOME/skills`），由 CLI 自身机制触发；**工具与连接（`tools/`、`mcp.json`）在 BYO 组员上不生效**。面向 BYO 组员的插件请把关键能力写进技能。
- `requires` / `permissions` / `scope` 目前**只校验格式、原样存档，不执行**；审核员会对照它们检查（见 5.5 审核清单第 4 条）。
- 插件安装目前**免费**；定价、云端软件（`components.compute`）等能力在设计中，格式未开放，请勿使用。

---

## 2. 快速开始

### 2.1 最小可用插件（只含一个技能，适合社区层）

```text
hello-notes/                    # 根目录名必须等于 plugin.json 的 name
├── plugin.json
├── README.md                   # 可选，强烈建议写（审核第 8、9 条要看）
└── skills/
    └── hello-notes/
        └── SKILL.md
```

`plugin.json`：

```json
{
  "schema": "krow-plugin/1",
  "name": "hello-notes",
  "version": "1.0.0",
  "display_name": "会议纪要整理",
  "description": "把零散的会议记录整理成结构化纪要：议题、结论、待办与负责人。",
  "license": "MIT",
  "author": "你的名字或组织",
  "components": {
    "skills": ["hello-notes"],
    "tools": null,
    "mcp_servers": []
  }
}
```

`skills/hello-notes/SKILL.md`：

```markdown
---
name: hello-notes
description: 会议纪要整理。当任务是「整理会议记录 / 写纪要 / 提取待办」时使用：按议题归类，列出结论与待办（含负责人和截止时间），输出 Markdown。
---

# 会议纪要整理

## 何时用
## 工作流
## 输出模板
## 不适用 / 出错时怎么办
```

打包（在 `hello-notes` 的**上一级目录**执行）：

```bash
# macOS 请加 COPYFILE_DISABLE=1，避免打进 ._xxx 隐藏文件（见第 7 节）
COPYFILE_DISABLE=1 tar czf hello-notes-1.0.0.tar.gz hello-notes
```

然后到「插件市场 › 开发者 › 提交新版本」上传，选「社区」，先点「**先检查一遍**」，全部没有「不通过」后点「**提交审核**」。

### 2.2 完整示例（技能 + 工具 + 连接）

```text
paper-search/
├── plugin.json
├── README.md
├── skills/
│   └── paper-search/
│       └── SKILL.md
├── tools/
│   ├── pyproject.toml                # 可选，仅供本地开发；平台不据此装依赖
│   └── krow_plugin_paper_search/
│       └── __init__.py
└── mcp.json
```

```json
{
  "schema": "krow-plugin/1",
  "name": "paper-search",
  "version": "1.0.0",
  "display_name": "文献检索",
  "description": "OpenAlex 搜论文、取摘要与引用数，落成 Markdown 文献表。",
  "license": "MIT",
  "author": "你的名字或组织",
  "components": {
    "skills": ["paper-search"],
    "tools": {
      "entry": "krow_plugin_paper_search:PaperSearchTools",
      "tool_names": ["paper_search.search", "paper_search.fetch"]
    },
    "mcp_servers": ["arxiv"]
  },
  "requires": { "krow_sdk": ">=0.9.5.2", "python": ">=3.11" },
  "permissions": ["network"],
  "scope": "teammate"
}
```

`mcp.json`：

```json
{
  "mcpServers": {
    "arxiv": { "command": "uvx", "args": ["arxiv-mcp-server"], "env": {} }
  }
}
```

> 注意：这个示例带了 `tools/`。提交到**社区层**时 `tools/` 会被剥离（清单里 `components.tools` 被改写为 `null`），只剩技能和连接；要保留工具需要合作伙伴层。

### 2.3 plugin.json 逐字段说明

清单未列出的字段会被忽略（前向兼容），原文整份存档。

| 字段 | 必需 | 类型 | 规则（以平台检查为准） |
|---|---|---|---|
| `schema` | 是 | 字符串 | 固定为 `"krow-plugin/1"`，其他值一律拒绝 |
| `name` | 是 | 字符串 | 1–64 字符；只能用小写字母、数字、连字符；不能以 `-` 开头或结尾，不能有连续 `--`；**必须等于归档根目录名** |
| `version` | 是 | 字符串 | 严格 semver 2.0：`MAJOR.MINOR.PATCH[-预发布][+构建]`；数字段不能有前导零；总长 ≤32 字符（详见 3.2） |
| `description` | 是 | 字符串 | 去掉首尾空白后非空，≤1024 字符；长介绍写进 README.md |
| `display_name` | 否 | 字符串 | ≤200 字符；市场展示名，不填或为空时显示 `name`。审核要求有中文展示名 |
| `license` | 否 | 字符串 | 写了就不能是空串；原样展示 |
| `author` | 否 | 字符串 | 原样存档。注意：市场上显示的作者是你的**开发者展示名** |
| `components.skills` | 否* | 字符串数组 | 每项是合法技能名（规则同 `name`），不能重复；必须与 `skills/` 下的子目录**一一对应** |
| `components.tools` | 否* | 对象或 `null` | `{ "entry": "...", "tool_names": [...] }`，规则见 3.4；不带工具时写 `null` 或省略 |
| `components.mcp_servers` | 否* | 字符串数组 | 非空字符串、不能重复；必须与 `mcp.json` 里的服务器名集合**完全相同** |
| `tool_prefix` | 否 | 字符串 | 工具名前缀；写了就不能为空。缺省为 `name` 把 `-` 换成 `_` 再加 `.`（`paper-search` → `paper_search.`） |
| `requires` | 否 | 对象 | 写了必须是 JSON 对象，如 `{"python": ">=3.11"}`。只存档、不执行；可用键以平台公告为准 |
| `permissions` | 否 | 字符串数组 | 可为空数组；有项时不能是空串、不能重复。只存档、不执行；合法取值清单以平台公告为准（示例用 `network`） |
| `scope` | 否 | 字符串 | 写了就不能是空串。只存档、不执行；示例为 `teammate`，其他取值以平台公告为准 |

\* `skills`、`tools`、`mcp_servers` 三者至少一个非空。

---

## 3. 开发规范

### 3.1 命名

| 对象 | 规则 |
|---|---|
| 开发者命名空间 | 3–32 字符；小写字母开头；只能用小写字母、数字、连字符；不能以连字符结尾，不能有连续连字符；**认领后不可修改**；不能与已有命名空间重复 |
| 保留命名空间（不能认领） | `admin` `api` `community` `internal` `krow` `krowwork` `latest` `official` `oss` `partner` `platform` `root` `system` `test` |
| 插件名 `name` | 1–64 字符，小写字母 / 数字 / 单个连字符，不以连字符开头或结尾；= 根目录名 |
| 插件全名 | `命名空间/插件名`，例如 `zhangsan/kicad-check`。组员安装与钉版本都用这个全名 |
| 技能名 | 同插件名规则；`SKILL.md` frontmatter 的 `name` = 技能目录名 = `components.skills` 里的声明 |
| 工具名 | 必须以 `tool_prefix` 开头，且前缀后面还要有内容（不能只有前缀）；不能重复 |
| 工具入口 `entry` | `顶层包.模块:类名`，各段都是 Python 标识符（`[A-Za-z_][A-Za-z0-9_]*`），`tools/<顶层包>/` 必须存在 |
| MCP 服务器名 | 非空、不重复，与 `mcp.json` 一致 |

### 3.2 版本号

- 格式：严格 semver 2.0（`1.2.0`、`1.2.0-beta.1`、`1.2.0+build.5`），数字段不能有前导零（`01.0.0` 不行），纯数字的预发布段也不能有前导零；总长 ≤32 字符。
- 先后比较按 semver 2.0 优先级：构建元数据（`+...`）不参与比较；同核心版本时不带预发布段的更高（`1.0.0-beta` < `1.0.0`）；预发布段逐段比较，纯数字按数值、数字段低于字母段、段数多者更高。
- 提交规则（自动检查「版本号」）：
  - 与已上架版本**相同** → 不通过（已上架版本不能覆盖）。
  - **不高于**已上架的最高版本 → 不通过。
  - 同一版本号此前被驳回、已撤回或仍在审核中 → 允许，用原版本号重新提交会**替换**之前那次提交（检查结果会提示「会替换之前提交的同版本」），并重新进入审核。
- 改了任何文件都要升 `version`（如有 `tools/pyproject.toml` 也同步升）。市场按版本缓存，不升版本订阅方拉到的还是旧包。

### 3.3 包结构与大小限制

| 限制 | 值 |
|---|---|
| 包格式 | `tar.gz`，归档里**恰好一个**含 `plugin.json` 的顶层目录；`plugin.json` 不能平铺在归档根；一个归档只能放一个插件 |
| 上传包大小（压缩后） | **≤ 8 MB**（组员工作台拉插件整包的上限） |
| 解压后总大小 | ≤ 64 MB |
| 单个文件 | ≤ 8 MB |
| 文件数 | ≤ 2000 |
| `plugin.json` | ≤ 256 KB，必须是 JSON 对象 |
| `mcp.json` | ≤ 256 KB |
| `README.md` | ≤ 512 KB，UTF-8 |
| 每个 `SKILL.md` | ≤ 512 KB，UTF-8 |
| 文件类型 | 只允许普通文件和目录；**符号链接、硬链接、设备文件一律拒绝** |
| 路径 | 不能是绝对路径，不能含 `..` |
| 根目录以外的杂物 | 例如 `__MACOSX/`，直接丢弃，不报错 |
| 根目录以内的杂物 | `__pycache__/`、`*.pyc`、`.DS_Store`、`._xxx` **不会被过滤**，会原样入包并分发（社区层随 `tools/`、`scripts/` 一起被剥离的除外）。打包前自己排除（见第 4 节） |

声明与实物必须**双向一致**：

- `skills/` 下的每个子目录都必须在 `components.skills` 中声明；声明的每个技能都必须有 `skills/<名>/SKILL.md`；`skills/` 下**不能直接放文件**。
- 声明了 `components.tools` 就必须有 `tools/` 目录且 `tools/<顶层包>/` 存在；没声明（`null`）就不能有 `tools/`。
- 声明了 `components.mcp_servers` 就必须有 `mcp.json`；有 `mcp.json` 就必须声明；两边服务器名集合完全相同。

### 3.4 技能 `SKILL.md`

- 必须以 YAML frontmatter 开头（`---` 包起来）。
- 必填：`name`（等于目录名）、`description`（非空，≤1024 字符）。
- 选填：`license`、`compatibility`、`allowed-tools`（空格分隔）、`metadata`（嵌套内容会被忽略）；其他未知键忽略。
- frontmatter 只支持简单写法：普通标量（裸写 / 单引号 / 双引号）、块标量（`|`、`>`、`|-`、`>-`）、多行折叠标量。**不支持**锚点 / 别名 / 标签（`&` `*` `!`）、流式集合（`[...]` `{...}`）用作字段值；双引号里只支持 `\" \\ \n \r \t \/` 转义。
- `description` 决定组员什么时候想起用它：写清触发场景和要调用的工具名，别写成「任何任务都用我」（审核第 2 条）。
- 技能里的 `scripts/` 在**社区层会被剥离**，关键步骤不要只靠脚本。

### 3.5 工具 `tools/`

```python
class PaperSearchTools:
    plugin_id = "paper_search"

    def on_load(self, ctx):            # 可选：加载时调用一次。ctx 字段：plugin_id / project_root / logger / event_bus（只读订阅）/ sdk_version（宿主路径为真实版本，`krow tool` 自测路径里是占位值，不要据此做分支）/ config（当前为空 dict）；可选 on_unload(self) 在插件被卸载时调用
        pass

    def get_tools(self):
        return [{
            "name": "paper_search.search",             # 以 tool_prefix 开头，并列在 tool_names 里
            "description": "按关键词与年份搜论文……",    # 给模型看，写清入参含义
            "input_schema": {                          # JSON Schema
                "type": "object",
                "properties": {"query": {"type": "string", "description": "关键词"},
                               "limit": {"type": "integer", "description": "最多返回几条，缺省 10"}},   # 每个字段写 description，krow tool help 会显示
                "required": ["query"],
            },
            "handler": self._search,                   # 以关键字参数接收模型传入的字段
        }]

    def _search(self, query: str, limit: int = 10, **_):
        try:
            ...
            return {"items": [...], "count": 3}
        except Exception as e:
            return {"error": f"数据源暂不可用：{e}"}    # 约定：出错返回 {"error"}，不要抛异常
```

要求：

0. 工具是**确定性器件**：不在工具里调模型、不做需要判断的事（判断留给组员的模型），同样的入参给同样的结果；只往自己的返回值里写结果，不写组员工作盘上的其他位置。
1. `components.tools.tool_names` 至少一项，且与 `get_tools()` 返回的 `name` 一一对应。
2. 只用标准库，或把**纯 Python** 依赖放进 `tools/` 一起打包（注意许可证）；带 C 扩展的包不支持。
3. handler 自己设超时（建议 ≤15 秒），长任务拆成「提交 / 查询」两个工具；出错返回 `{"error": "原因"}`，不抛异常、不无限等待（审核第 3 条）。返回 `{"error"}` 在组员端会被记为**调用失败**（模型看到你写的原因；`krow tool run` 返回码 1），所以把原因写清楚。
4. 社区层 `tools/` 整棵剥离；需要分发工具请申请合作伙伴层。
5. 组员只能加载主人批准安装的插件：工作台按授权令牌（`KW_ENTITLEMENT`）过滤，未授权的工具插件会被拒装并上报，不会出现在 `krow tool list` 里（原因看不带 `--prefix` 的 `krow tool list` 末尾的「插件未装」行，或 `krow -v tool list`）。本地开发自测时去掉这个环境变量（见第 4 节）。

### 3.6 连接 `mcp.json`

```json
{
  "mcpServers": {
    "arxiv":  { "command": "uvx", "args": ["arxiv-mcp-server"], "env": {} },
    "notion": { "url": "https://mcp.notion.com/mcp", "transport": "http",
                "auth_kind": "oauth2", "authorize_url": "https://<授权服务>/oauth/authorize", "token_url": "https://<授权服务>/oauth/token",
                "client_id": "...", "scopes": ["read"], "use_pkce": true }
  }
}
```

- 根对象必须有非空对象 `mcpServers`；每个服务器是对象，并且**只能二选一**：字符串 `command`（stdio，跑在组员工作台里）或字符串 `url`（远程）。
- url 型会成为该组员的连接器（来源显示为插件）。组员工作台从服务器条目读取并上报下列字段，其余键忽略：
  - `url` → 连接地址（必填）。
  - `transport`：`sse` 按 sse；`streamable` / `streamable-http` / `http` / 不填 都按 streamable。
  - `auth_kind`（也认 `auth`）：`none` / `bearer` / `oauth2`，缺省 `none`。`none` 装上即可用；`bearer` / `oauth2` 需要主人到连接器页授权。
  - `display_name`：连接器显示名，可选。
  - oauth2 **公开**客户端配置：`authorize_url`、`token_url`、`client_id`、`scopes`（字符串数组或空格分隔字符串）、`use_pkce`（布尔）、`auth_extra_params`（授权网址附加参数字符串，形如 `&k=v`）。可平铺在服务器条目里，也可收在 `oauth: {...}` 子对象里；两处都写时平铺优先。
  - **不要写 `client_secret`、`bearer_token`、`token`、`access_token`、`api_key`、`secret`**：组员工作台在上报前会把这六个键剔除并告警（所以写了也不生效）；其中带引号长值的 `client_secret` / `api_key` / `access_token` 等还会被 3.8 的密钥扫描直接判 `fail`（`bearer_token`、`token`、`secret` 不在扫描规则内，不要指望被拦）。
- stdio 服务器的 `env` 里不要写真值。整串 `${变量名}` 形式会用组员工作台的进程环境展开，取不到时为空串；目前没有面向开发者的注入入口（是否提供以平台公告为准），所以 stdio 服务器应能在没有密钥的情况下工作，需要鉴权的服务请改用 url 型 + 连接器授权。

### 3.7 安全与权限要求

- 不放密钥、令牌、私钥、个人数据（密钥扫描见 3.8）。
- 网络访问与 `permissions` 声明一致，访问的域名和插件用途相关。
- 不越权：不读写工作区之外的路径，不读其他组员的数据，不绕过确认对外发送消息，不尝试规避平台安全限制。
- 如实描述，不冒用他人品牌；许可证清楚，随包依赖的许可证兼容。
- 以上同时是《插件开发者协议》（版本 2026-10-16）的条款，也是人工审核清单的内容（见 5.5）。

### 3.8 自动检查会拦什么（逐条）

每次「先检查一遍」和「提交审核」都跑同一套检查。每条结果有 `key`、`title`、`level`（`pass` 通过 / `warn` 提醒 / `fail` 不通过）和 `detail`。**有任何一条 `fail` 就不会入库**；`warn` 不阻止提交。

| 顺序 | key | 标题 | 判定 |
|---|---|---|---|
| ① | `package` | 包结构与清单 | 按 2.3、3.1–3.6 的全部规则解包校验。**不通过时只返回这一条**，后面的检查不再执行。通过时给出「命名空间/名称 版本：技能 N 个、工具 N 个、连接 N 个」 |
| ② | `ownership` | 插件归属 | 同一命名空间下这个插件名已存在、但不属于你 → `fail`「这个插件名已被平台占用，换一个 name」。正常情况下不会出现 |
| ③ | `version` | 版本号 | 见 3.2：等于已上架版本或不高于已上架最高版本 → `fail`；否则 `pass`（首次上架 / 高于已上架的 x.y.z；重提同版本时提示会替换） |
| ④ | `secrets` | 密钥扫描 | 见下表，命中即 `fail`。结果只给「文件:行号（规则名）」，最多列 5 处，**不回显密钥本身** |
| ⑤ | `tools` | 工具 / 工具依赖 | 社区层带了 `tools/` → `warn`「已被剥离」；合作伙伴层：`tools/` 里 import 了既非标准库、也非随包带的顶层模块 → `warn`，否则 `pass`。没有工具则无此条 |
| ⑥ | `scripts` | 技能脚本 | 社区层且有技能的 `scripts/` 被剥离 → `warn` |

**密钥扫描规则**（扫描的是**剥离后实际分发的文件**，逐行扫描所有 UTF-8 文本文件，包括 README 和 SKILL.md；二进制文件跳过）：

| 规则名 | 命中条件 |
|---|---|
| 私钥 | 同一行出现 PEM 私钥头（五个短横 + BEGIN … PRIVATE KEY + 五个短横） |
| AWS 访问密钥 | AWS Access Key ID 的固定前缀 + ≥16 个令牌字符 |
| 火山引擎访问密钥 | 火山引擎 AccessKey 的固定前缀 + ≥20 个令牌字符 |
| GitHub 令牌 | GitHub 个人 / OAuth / 应用令牌的固定前缀 + ≥20 个令牌字符 |
| Slack 令牌 | Slack bot / user / app 令牌的固定前缀 + ≥10 个令牌字符 |
| 模型 API Key | OpenAI 风格 API Key 的固定前缀 + ≥20 个令牌字符 |
| Krow 连接器令牌 | Krow 连接器令牌的固定前缀 + ≥16 个令牌字符 |
| client_secret | 键名含 `client_secret` / `client-secret` / `clientsecret`（不分大小写），用冒号或等号赋一个**带引号**的值，值 ≥8 字符 |
| API Key / Token 赋值 | 键名含 `api_key` / `api-key` / `apikey` / `access_token` / `secret_key` / `auth_token`（不分大小写），用冒号或等号赋一个带引号的值，值 ≥16 字符 |

说明：

- 「令牌字符」= 字母、数字、`_`、`-`。前缀左侧必须是词边界（前缀只是长串的一部分时不算）。
- 键名是**子串匹配**，形如「某某_API_KEY 等于一个带引号的长值」也会命中。
- 赋值形态里，值以 `$`、`{`、`<` 开头的占位（如美元符变量、双花括号模板、尖括号占位）不算；值里含空白也不算。
- 文档、示例里也会被扫描：示例里请用占位符，不要贴形似真值的长串。

**工具依赖检查细节**（仅合作伙伴层等保留 `tools/` 时）：只看 `tools/` 下 `.py` 文件里的 `import a, b` / `from a.b import x` 行；相对导入忽略；`tools/` 下自带的顶层目录或 `.py` 文件视为随包模块；标准库按 Python 3.11–3.13 的标准库模块名单判断。

**包结构错误的提示是英文**（来自同一套入库校验），常见几条对照：

| 提示（节选） | 含义与改法 |
|---|---|
| `plugin.json must live under a single top-level directory named after the plugin` | `plugin.json` 平铺在归档根了；用 `tar czf x.tar.gz <插件目录>` 打包 |
| `plugin.json not found in a top-level directory of the archive` | 找不到清单，或多套了一层目录 |
| `Archive contains multiple plugins` | 一个归档里有多个带 `plugin.json` 的顶层目录 |
| `plugin.json name '...' does not match the archive root directory '...'` | 根目录名 ≠ `name` |
| `plugin.json 'version' must be semver ...` | 版本号格式不对 |
| `skills/x/ is present in the archive but not declared ...` | `skills/` 下多了一个没在 `components.skills` 声明的子目录 |
| `files under skills/ must live in a skill sub-directory` | `skills/` 下直接放了文件（常见于 `.DS_Store`、`._xxx` 等隐藏文件） |
| `... frontmatter name '...' does not match its directory name` | SKILL.md 的 `name` ≠ 目录名 |
| `tools/ is present in the archive but plugin.json components.tools is null` | 有 `tools/` 但没声明 |
| `tool_names entry '...' must start with tool_prefix '...'` | 工具名前缀不对 |
| `mcp.json server '...' must have exactly one of string 'command' (stdio) or 'url' (remote)` | 服务器配置要在 `command` 和 `url` 里二选一 |
| `Tar archive contains a non-regular file (symlink/hardlink/device)` | 包里有符号链接等 |
| `File '...' exceeds the 8388608 byte per-file limit` | 单文件超过 8 MB |
| `mcp.json must contain an object 'mcpServers'` | 根键写错（例如写成 `servers`）或缺失 |
| `plugin.json must declare at least one component (skills, tools or mcp_servers)` | 三类组件全空 |
| `Tar entry escapes the archive root: ...` | 路径含 `..` |
| `plugin.json 'license' must be non-empty when present` | `license` 写了空串（`scope`、`tool_prefix` 同理） |
| `plugin.json 'description' exceeds 1024 characters; put long text in README.md` | 描述超长 |

---

## 4. 本地自测

平台目前**没有**提供离线校验工具；最权威的自测是网页上的「**先检查一遍**」（或接口 `dry_run: true`）：用与正式入库同一套规则检查，逐条给结果，**不会入库**。在此之前建议先做本地检查：

```bash
# 1) 工具冒烟（如有 tools/）：能 import、能列出工具、出错不抛异常
cd my-plugin/tools
python -c "from my_plugin_tools import MyTools as T; t=T(); print([x['name'] for x in t.get_tools()])"

# 2) 清单是合法 JSON
python -m json.tool ../plugin.json > /dev/null && echo plugin.json OK

# 3) 打包：在插件目录的上一级执行，根目录名 = plugin.json 的 name
cd ../..
COPYFILE_DISABLE=1 tar --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' --exclude='._*' -czf my-plugin-1.0.0.tar.gz my-plugin

# 4) 看一眼包内容：只有一个顶层目录、没有隐藏杂物、没有符号链接
tar tzvf my-plugin-1.0.0.tar.gz
ls -l my-plugin-1.0.0.tar.gz      # 压缩后 ≤ 8 MB
```

**有 Krow Agent SDK 的开发者可以让工具真正跑一遍**（与平台组员 `krow tool run` 用的是同一条加载路径）。需要 `krow` 命令及其运行时：公开包 `krow-agent-sdk`（本指南实测版本 0.9.5.27）提供 `krow` 入口，运行时模块的获取方式以 SDK 文档（[`runtime-install.md`](./runtime-install.md)）为准。只装了公开 wheel 没装运行时时，`krow tool list` 会以返回码 3 退出并提示「krow 运行时不可用 … 请安装 krow-agent-sdk-runtime 或在仓库根运行」——这是缺运行时，不是插件写错：

```bash
pip install krow-agent-sdk            # 公开包；运行时模块的安装方式以 SDK 文档为准
mkdir -p .krow
# 一行一个插件：<tools 目录绝对路径>::<顶层包.模块>:<类名>
echo "$PWD/my-plugin/tools::my_plugin_tools:MyTools" > .krow/cli_plugins.txt
unset KW_ENTITLEMENT                  # 组员工位上有这个变量时会按授权拒装，本地自测先去掉
krow tool list --prefix my_plugin.    # 应列出 tool_names 里的每一个，带 [plugin]
krow tool help my_plugin.search       # 看字段 description 是否齐全
krow tool run my_plugin.search --arg query=测试 --json
# 再走一次会返回 {"error"} 的分支（例如数据源不可用）：期望返回码 1、stderr 是你写的原因（--json 时 stdout 为空，错误只在 stderr）
```

自查清单：

- [ ] 根目录名 = `name`；`version` 是 semver，且高于已上架的最高版本
- [ ] `skills/` 每个子目录都已声明，SKILL.md 的 `name` 等于目录名，`description` 非空
- [ ] `tool_names` 每项以前缀开头，并且和 `get_tools()` 返回的一一对应
- [ ] `mcp.json` 的服务器名和 `components.mcp_servers` 完全相同，每个服务器只有 `command` 或 `url` 之一
- [ ] 没有符号链接；压缩包 ≤8 MB、解压 ≤64 MB、单文件 ≤8 MB、文件 ≤2000 个
- [ ] 没有密钥、令牌、个人数据（包括 README 里的示例）
- [ ] 有中文展示名、中文描述，README 写了用法和一个可复现的示例任务
- [ ] 包里没有 `__pycache__`、`.pyc`、`.DS_Store`、`._xxx`（`tar tzvf` 看一遍）
- [ ] 每个工具字段都有 `description`，`krow tool help` 看得到

---

## 5. 上架流程

> **状态：规划 / 实验 · 以平台公告为准。** 本节描述的提交、审核、分发安装三段是平台侧的设计流程；在你的部署里是否已开放、审核时效、合作伙伴层如何开通，以插件市场页面与平台公告为准。本节不表示这三段已对所有开发者上线或经过验证。

全部在网页「插件市场 › 开发者」完成（页面地址形如 `/workspace/<小组ID>/plugins/developer`，`?tab=mine|submit|docs` 可直达「我的插件 / 提交新版本 / 开发文档」）。开发者身份**按账号**算，与小组无关：在哪个小组打开开发者页看到的都是同一份。

```
注册开发者 ──► 提交新版本 ──► 自动检查 ──► 人工审核 ──► 上架
   (一次)        (每个版本)     (先检查一遍)    (审核中)      (已上架)
                                   │fail           ├─ 驳回 → 修改后重提
                                   └─ 修改后重传    └─ 审核中可撤回
```

### 5.1 注册成为开发者

第一次打开开发者页时填写：

| 项 | 说明 |
|---|---|
| 命名空间 | 你所有插件的前缀（规则见 3.1）。**认领后不能改** |
| 展示名 | 市场上显示的开发者名字（同时作为插件的作者名），非空，≤200 字符 |
| 类型 | 个人（`individual`，缺省）或组织（`organization`） |
| 联系邮箱 | 可选；不填默认用登录邮箱 |

并阅读、同意《插件开发者协议》（当前版本 `2026-10-16`）。协议更新后，页面会提示「开发者协议有更新，重新同意后才能提交新版本」，重新同意前不能提交。

注册后可以再修改展示名、类型、联系邮箱，命名空间不能改。

### 5.2 选择上架层

| 层 | `tools/` | 技能里的 `scripts/` | 谁能选 |
|---|---|---|---|
| 社区 `community` | 自动剥离 | 自动剥离 | 所有开发者 |
| 合作伙伴 `partner` | 保留 | 保留 | 与平台签约、由平台开通合作伙伴身份后可选 |
| 官方 / 开源 | — | — | 只由平台发布，开发者不能提交 |

合作伙伴的申请方式与联系渠道以平台公告为准。

### 5.3 提交新版本

1. 打包成 `tar.gz`（≤8 MB）。
2. 在「提交新版本」上传，选上架层，写「这次改了什么」（≤2000 字符；审核员和装了插件的主人都会看到）。
3. 点「**先检查一遍**」查看逐条结果（不入库）。
4. 全部没有「不通过」后点「**提交审核**」。

入库时平台会对**剥离后的内容**做确定性重打包并由平台签名，组员拿到的是这份产物。

### 5.4 自动检查

规则见 3.8。不通过的修改方法：

| 检查 | 怎么改 |
|---|---|
| 包结构与清单 | 按第 2、3 节修改 |
| 版本号 | 升版本号。被驳回或已撤回的版本可以用原版本号重新提交 |
| 密钥扫描 | 删掉密钥。oauth2 只写公开客户端配置，其余改成让用户在连接器里授权 |
| 工具依赖（提醒） | 改用标准库，或把纯 Python 依赖随包带上 |
| 剥离提醒（提醒） | 这部分不会分发；需要的话申请合作伙伴层 |

### 5.5 人工审核

提交后版本进入审核队列，状态为「审核中」。审核员能看到自动检查结果、清单、README，并可下载你的包；会给测试组员装上、跑一遍 README 里的示例任务。审核清单：

| # | 审核项 |
|---|---|
| 1 | 名称和描述如实，不冒用别家品牌 |
| 2 | 技能的 `description` 触发范围合理，不写成「任何任务都用我」 |
| 3 | 工具出错返回 `{"error"}`、有超时，不抛异常、不无限等待 |
| 4 | 网络访问与 `permissions` 一致，访问的域名和插件用途相关 |
| 5 | 没有密钥、令牌、个人数据 |
| 6 | 不越权：不读写工作区外的路径，不读其他组员的数据，不绕过确认发外部消息 |
| 7 | 许可证清楚，随包依赖的许可证兼容 |
| 8 | 按 README 的示例真实可用 |
| 9 | 有中文展示名、中文描述，README 写了用法 |

审核时效以平台公告为准。

### 5.6 状态含义

**版本状态**（每个版本独立审核）：

| 状态 | 页面显示 | 含义 | 你能做什么 |
|---|---|---|---|
| `pending` | 审核中 | 等待审核 | 撤回；或用同版本号重新提交（替换本次提交） |
| `approved` | 已上架 | 已出现在市场，可被安装 | 不能覆盖、不能撤回；改动请升版本号 |
| `rejected` | 已驳回 | 未通过，附驳回原因 | 修改后用原版本号或新版本号重新提交 |
| `withdrawn` | 已撤回 | 你主动撤回 | 可用原版本号或新版本号重新提交 |

**插件状态**（由各版本状态自动推导）：

| 状态 | 条件 |
|---|---|
| `approved` | 至少有一个已上架版本；市场「最新版本」= 已上架版本中 semver 最高的那个 |
| `pending` | 没有已上架版本，但有审核中的版本 |
| `rejected` | 既没有已上架版本，也没有审核中的版本（**仅有已撤回版本时也显示为此状态**） |

插件的展示名、描述、上架层取自「最新已上架版本」的清单与所选层。「我的插件」列表的当前状态按**最近一次提交的版本**显示，所以新版本待审时会显示「审核中」。

### 5.7 发新版本：旧版本照常分发

- 已上架插件提交新版本时，**新版本审核期间，旧版本照常在市场上供安装**，已安装的组员也不受影响。
- 新版本被驳回不影响已上架的旧版本。
- 新版本通过后成为最新版本。**安装 / 卸载**在该组员的下次任务生效（空闲组员立即换环境，忙碌组员当前任务不受影响）。**版本跟随**：没被钉版本的组员在之后的轮次拉到新版文件（技能、`krow tool run` 可用的工具随之更新）；平台组员已加载进工具表的旧版工具会在环境重建后换新。主人也可以把某位组员钉在某个版本。进行中的任务不会中途换版本。
- 已上架的版本不能覆盖，改动一律升版本号。

### 5.8 被驳回怎么改

1. 在「我的插件」里展开对应版本，查看驳回原因。原因形如「审核第 N 条（条目内容）：补充说明」，命中多条时用「；」连接；也可能只有条目、或只有补充说明。N 对应 5.5 的审核清单。
2. 按原因修改，必要时同时调整 README / 描述。
3. 用**原版本号**或**新版本号**重新提交（先检查一遍 → 提交审核）。

---

## 6. 开发者接口参考

> **状态：实验 · 以平台公告为准。** 接口形状按 2026-10-23 的实现写出；对外主机名、是否开放给脚本 / CI 长期调用、各部署是否已开通，以平台公告为准。

网页开发者页背后就是下面这组接口，也可以直接调用。

- **地址**：与 KrowWork 网页同源（网页以相对路径调用）。对外推荐的接口主机名以平台公告为准，下文用 `$KROW_API` 表示。
- **鉴权**：`Authorization` 头以持有者令牌（Bearer）方式携带登录令牌，即 KrowWork 登录态的 JWT。目前**没有**单独的开发者 API Key；在脚本 / CI 里长期使用登录令牌是否被支持，以平台公告为准。
- **身份**：以令牌里的用户为开发者，与小组无关。
- **成功响应**：HTTP 200，直接返回数据对象（下文各端点的「返回」）。
- **失败响应**：`{"error": {"code": "...", "message": "..."}}`，`message` 是给开发者看的中文原因（包结构类为英文，见 3.8）。

| HTTP 状态 | code | 含义 |
|---|---|---|
| 400 | `INVALID_REQUEST` | 参数不合法（命名空间、展示名、邮箱、更新说明超长、未同意当前协议、base64 不合法、包超过 8 MB 等）。平台网关自身校验的部分 body 为 `{"error": "..."}` 字符串形式 |
| 401 | — | 未登录或令牌无效 |
| 403 | `FORBIDDEN` | 开发者身份已暂停；协议有更新未重新同意；无权选择该上架层 |
| 404 | `NOT_FOUND` | 还没有开发者身份；没有可撤回的待审版本 |
| 409 | `CONFLICT` | 命名空间已被占用 / 试图修改命名空间 / 版本已上架不能覆盖 |
| 502 | `MARKETPLACE_UNREACHABLE` 等 | 插件市场暂时连不上或内部错误，请稍后再试 |
| 503 | `DEVELOPER_DISABLED` | 本部署还没有开放插件开发者上架（是否开放以平台公告为准，见第 8 节） |

请求超时：平台转发到市场的单次调用超时为 30 秒。

### 6.1 `GET /v1/plugin-developer` — 查看开发者身份

无参数。

返回：

```json
{
  "developer": { /* Developer 对象，未注册时为 null */ },
  "agreement_version": "2026-10-16"
}
```

`Developer` 对象：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 开发者 ID |
| `owner_ref` | string | 你的用户 ID |
| `namespace` | string | 命名空间 |
| `display_name` | string | 展示名 |
| `kind` | string | `individual` / `organization` |
| `contact_email` | string \| null | 联系邮箱 |
| `partner` | bool | 是否已开通合作伙伴 |
| `status` | string | `active` / `suspended` |
| `agreement_version` | string | 你同意过的协议版本 |
| `agreement_current` | bool | 是否已同意当前版本协议 |
| `agreed_at` / `created_at` | string（RFC 3339） | 同意时间 / 注册时间 |
| `allowed_tiers` | string[] | 可选上架层：`["community"]` 或 `["community","partner"]` |

### 6.2 `PUT /v1/plugin-developer` — 注册 / 更新资料

请求体：

| 字段 | 必需 | 说明 |
|---|---|---|
| `namespace` | 是 | 首次 = 认领；之后必须与已认领的一致，否则 409 |
| `display_name` | 是 | 非空，≤200 字符 |
| `kind` | 否 | `individual`（缺省）/ `organization` |
| `contact_email` | 否 | 须含 `@`，≤200 字符；不填用登录邮箱 |
| `agreement_version` | 是 | 必须等于当前协议版本（从 6.1 的 `agreement_version` 取），表示你已阅读并同意 |

返回：`{ "developer": Developer, "created": true|false }`（`true` = 本次为首次注册）。

重新同意协议也是调用本接口（带上原命名空间和当前 `agreement_version`）。

### 6.3 `GET /v1/plugin-developer/plugins` — 我的插件

无参数。未注册返回 404，身份暂停返回 403。

返回：

```json
{
  "developer": { /* Developer */ },
  "items": [
    {
      "namespace": "zhangsan",
      "name": "kicad-check",
      "display_name": "…",
      "description": "…",
      "tier": "community",
      "status": "approved",
      "latest_version": "1.1.0",
      "install_count": 12,
      "updated_at": "2026-10-20T08:00:00+00:00",
      "versions": [
        {
          "id": "…",
          "version": "1.2.0",
          "review_status": "pending",
          "review_note": null,
          "requested_tier": "community",
          "release_notes": "…",
          "checks": [ { "key": "package", "title": "包结构与清单", "level": "pass", "detail": "…" } ],
          "tools_stripped": false,
          "components": { "skills": ["…"], "tools": ["…"], "mcp_servers": ["…"] },
          "submitted_at": "…",
          "reviewed_at": null
        }
      ]
    }
  ]
}
```

插件按更新时间倒序；`versions` 按 semver 从高到低。`review_note` 是驳回原因（或审核备注）。

### 6.4 `POST /v1/plugin-developer/submissions` — 先检查 / 正式提交

请求体：

| 字段 | 必需 | 说明 |
|---|---|---|
| `tarball_b64` | 是 | 插件 `tar.gz` 的标准 base64（不带 `data:` 前缀）；解码后 ≤8 MB |
| `tier` | 是 | `community` 或 `partner`（后者需已开通） |
| `dry_run` | 否 | `true` = 只检查不入库（「先检查一遍」） |
| `release_notes` | 否 | 这次改了什么，≤2000 字符 |
| `category` | 否 | 分类，缺省 `agents`；可选值清单以平台公告为准（不做枚举校验，长度上限 50） |
| `tags` | 否 | 字符串数组 |
| `homepage_url` | 否 | 主页链接 |

注意：`category` / `tags` / `homepage_url` 目前网页上没有输入项，只能通过接口传；并且**只在插件第一次建档时写入**，之后的提交不会更新它们（开发者接口目前没有修改入口）。插件图标目前开发者接口不转发，不能设置。

返回（**检查不通过也是 HTTP 200**，以 `ok` 判断）：

```json
// 检查不通过：什么都不入库
{ "ok": false, "checks": [ ... ], "submission": null }

// dry_run 且全部通过
{ "ok": true, "checks": [ ... ], "submission": null, "dry_run": true }

// 正式提交成功
{
  "ok": true,
  "checks": [ ... ],
  "submission": {
    "version_id": "…",
    "namespace": "zhangsan",
    "name": "kicad-check",
    "version": "1.2.0",
    "tier": "community",
    "review_status": "pending",
    "sha256": "…",
    "tools_stripped": false,
    "scripts_stripped": false
  }
}
```

`review_status` 一般为 `pending`；若平台开启了社区层自动上架（是否开启以平台公告为准），社区层提交通过检查后直接为 `approved`。`sha256` 是平台重打包后产物的摘要。

示例：

```bash
B64=$(base64 -w0 my-plugin-1.0.0.tar.gz)        # macOS: base64 -i my-plugin-1.0.0.tar.gz
# KROW_AUTH_HEADER = 完整的 Authorization 请求头（持有者令牌方式，值为你的登录令牌）
curl -sS -X POST "$KROW_API/v1/plugin-developer/submissions" \
  -H "$KROW_AUTH_HEADER" -H "Content-Type: application/json" \
  -d "{\"tarball_b64\":\"$B64\",\"tier\":\"community\",\"dry_run\":true}"
```

（包较大时请把 JSON 写进文件再用 `-d @body.json`，避免命令行过长。）

### 6.5 `POST /v1/plugin-developer/plugins/{name}/versions/{version}/withdraw` — 撤回待审版本

- 路径参数：`name` 插件名、`version` 版本号；只允许字母、数字和 `- . + _`，≤64 字符。
- 无请求体。
- 只能撤回**审核中**的版本，否则 404「没有这个待审版本（只能撤回审核中的版本）」。

返回：`{ "name": "...", "version": "...", "review_status": "withdrawn" }`

> 开发者接口目前只有以上 5 个端点；**没有**下架已上架版本、删除插件、修改命名空间的接口。已上架版本如需下架，请联系平台（渠道以平台公告为准）。

---

## 7. 常见问题

**能改命名空间吗？**
不能。认领后不可更改（组员安装、钉版本用的是 `命名空间/插件名`）。一定要换只能用新账号注册新命名空间重新上架，并在旧插件说明里引导迁移。

**检查提示 `files under skills/ must live in a skill sub-directory`？**
macOS 会在目录里生成 `.DS_Store` 和 `._xxx`（AppleDouble）隐藏文件；它们落在 `skills/` 下时会被这条拦住。注意**只有这一处会被拦**：落在技能目录里（`skills/x/._SKILL.md`）或插件根目录下（`._plugin.json`、`.DS_Store`）的隐藏文件不会报错，会原样进包、随插件分发。所以打包前要删除这些文件，并用 `COPYFILE_DISABLE=1` 加 `--exclude` 打包（见第 4 节）。根目录以外的 `__MACOSX/` 会被自动丢弃。

**本地 `krow tool list` 看不到我的工具，日志说「插件拒装 … not_entitled / no_ref」？**
你所在的环境带着组员授权令牌 `KW_ENTITLEMENT`，工作台按它过滤市场插件。本地开发自测先 `unset KW_ENTITLEMENT`；上架后组员端由主人批准安装来授权。

**我的插件需要第三方 Python 包怎么办？**
平台不会替组员安装依赖。用标准库，或把纯 Python 依赖放进 `tools/` 一起打包（注意许可证）；带 C 扩展的不支持。另外社区层不分发 `tools/`。

**社区层提交了带 `tools/` 的包，会失败吗？**
不会失败，会给「工具」提醒并剥离 `tools/`（清单里的 `components.tools` 同步改为 `null`）。如果插件离开工具就不能用，请改走合作伙伴层，或改成「技能 + 连接」的形态。

**README 里写了示例配置，被密钥扫描拦了？**
扫描覆盖所有文本文件，包括 README。示例值请用 `${VAR}`、`{{var}}`、`<填你的>` 这类占位，或使用明显不是令牌的短值。

**同一个版本号能反复提交吗？**
只要这个版本还没上架就可以（审核中 / 被驳回 / 已撤回），新提交会替换旧的并重新进入审核。已上架的版本号不能再用。

**被驳回了看不懂原因？**
原因前的「审核第 N 条」对应 5.5 审核清单。仍有疑问请联系平台（渠道以平台公告为准）。

**新版本在审核，用户还能装吗？**
能。旧的已上架版本照常分发，新版本通过后才成为最新版本。

**合作伙伴层怎么申请？**
需要与平台签约，由平台为你的开发者身份开通。申请渠道以平台公告为准。

**收费吗？**
目前插件上架与安装都免费。以后开放付费插件时，平台会另行公布规则并征得你同意。

**开发者身份被暂停了怎么办？**
暂停后所有提交、查看「我的插件」、撤回都会返回 403「开发者身份已被暂停，请联系平台」。申诉流程以平台公告为准。

---

## 8. 范围与状态说明（规划 / 实验）

本指南把内容分成两类，请按类对待：

| 类别 | 章节 | 依据 | 你可以怎么用 |
|---|---|---|---|
| **已验证** | 第 1–4 节：插件结构、`plugin.json` 字段、命名 / 版本 / 包限制、技能与工具规范、`mcp.json`、自动检查规则、本地自测 | 按 2026-10-23 的平台入库校验与 Krow Agent SDK `0.9.5.27` 的 `krow tool list / help / run` 加载路径核对，并实跑过本地自测段 | 直接照做；平台实际检查结果与本指南有出入时以平台为准 |
| **规划 / 实验 · 以平台公告为准** | 第 5–6 节：**提交新版本 → 自动检查 + 人工审核 → 上架与分发安装**三段，以及开发者接口的对外开放范围 | 平台侧设计流程，接口形状按当前实现写出；是否已在你的部署开放、审核时效、合作伙伴层开通方式、社区层是否自动上架、脚本 / CI 长期调用是否支持，均以平台公告为准 | 作为准备材料：先把包做成第 1–4 节要求的样子并本地自测；在开发者页看到「本部署还没有开放插件开发者上架」时，表示该部署尚未开通，不是你的包有问题 |

补充说明：

1. 本指南不构成任何生产操作授权；上架、审核、分发由平台流程决定。
2. 计划中、尚未开放的格式能力：`components.compute`（云端软件）、`pricing`（定价）、`requires` / `permissions` 的安装前执行。请勿在包里使用。
3. 当前开发者协议版本：`2026-10-16`；协议更新后需重新同意才能提交。
4. 本指南随 Krow Agent SDK 公开文档一起维护（公开文档仓 `aullik5/krow-sdk-docs`）；错误或遗漏请到公开文档仓提 issue。
