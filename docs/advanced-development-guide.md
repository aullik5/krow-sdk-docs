# Krow Agent SDK — 进阶开发最佳实践

> 给"已读完 [`quickstart.md`](./quickstart.md)、写过第一个 plugin"的外部开发者。
> 本文档解释**为什么 Krow Agent 这样设计**，让你写的 plugin 能与 SDK 主路径协同得当（不撞规则、不翻车、不踩坑）。
>
> 阅读节奏：约 60 分钟通读 + 写 plugin 时按需回查。
>
> 本文档与 SDK 主仓内部使用的 [`AGENTS.md`](https://pypi.org/project/krow-agent-sdk/) 元规则同源（提炼对外公开级内容）。

---

## 目录

| 章节 | 主题 | 何时读 |
|---|---|---|
| §0 | 价值观（准确性 > 完整性 > 速度 > 成本） | 写代码前 |
| §1 | TURBO 哲学（System 1 fast/syntax + System 2 slow/semantic） | 设计任何决策前 |
| §2 | Plugin 设计 5 大原则（SSOT / OCP / SRP / DRY / 复用） | 写 plugin 前 |
| §3 | ToolPlugin 设计哲学（功能强大 + Agent 友好接口） | 写 ToolPlugin |
| §4 | ACTPlugin / extended.md 编写最佳实践 | 写 ACTPlugin |
| §5 | HintPlugin / GatePlugin / EventListener 边界 | 写其它 plugin |
| §6 | 关键基础设施速查（公开 SDK 暴露的接口） | 写代码时按需 |
| §7 | 测试方法论（Plugin 单测 + record/replay + 真实 LLM 验证） | 验收前 |
| §8 | 反模式黑名单（铁证支撑） | 写完前 review |

---

## §0 价值观（**最上位约束**）

### 0.1 排序

> **准确性 > 完整性 > 速度 > 成本**

| 价值 | 含义 | 你写 plugin 时的体现 |
|---|---|---|
| **准确性** | 输出结果正确 / 不胡编 / 不撒谎 | 错就 fail-loud；宁可少做、不可做错 |
| **完整性** | 该交付的产物完整、不缺页、不缺字段 | 一次任务的所有产物全交付 + 自我验收 |
| **速度** | 用户可感知的延迟与吞吐 | 在准确 + 完整的前提下优化；不为速度牺牲前两项 |
| **成本** | LLM token / 计算 / 存储 | 在前三项已达标后才优化；不为省 token 砍准确性 |

### 0.2 判定冲突

| 冲突 | 选哪个 |
|---|---|
| 速度 vs 准确性 | **永远选准确**（错的快没意义） |
| 成本 vs 完整性 | **永远选完整**（少交付一半价值丢失 50%+） |
| 完整性 vs 准确性 | **选准确**（部分正确比全部错的好） |

### 0.3 反模式（铁证）

| 反模式 | 为什么错 |
|---|---|
| 为了"看起来快" 上 cache 跳过 LLM | 牺牲准确性换速度 → 业务价值倒挂 |
| 用启发式 / regex 替代语义判断 | 同上；语义问题应交给 LLM（详 §1） |
| 不确定时 try/except 吞错继续 | 用户拿到错误结果也不知道；应 fail-loud |
| 跑到一半超 token / 网络抖动就吐部分结果说"差不多了" | 完整性破坏；应重试或明确告知不完整 |

> **核心铁律**：你的 plugin 失败了不丢人，**默默给错的结果**才是大事故。任何不确定的状况优先 fail-loud。

---

## §1 TURBO 哲学（**Krow Agent 的灵魂**）

### 1.1 一句话总结

> **"语义交给 LLM、语法交给系统。"**

### 1.2 双系统架构

| 维度 | System 1（系统 / fast / syntax） | System 2（LLM / slow / semantic） |
|---|---|---|
| **职责** | 机械校验、错误信号结构化、协议守门、确定性查表、精确数值 / 几何计算 | 理解、生成、决策、风格、叙事、创意 |
| **特征** | 可被 unit test 100% 覆盖、零成本、毫秒级、行为可重放 | 需要 prompt 工程、有不确定性、按 token 计费、秒级～分钟级 |
| **范例** | 几何计算 / 颜色对查表 / 工具优先级排序 / Gate 8 闸门 | 写 SVG / ReACT 推理循环 / brief 解析 |
| **绝不混做** | System 1 工具内**禁止调 LLM**（性能 + 可重放性死线） | System 2 hint 不要让 LLM 做 cos/sin / 颜色对比度查表（出工具） |

### 1.3 写 plugin 时的判定 3 步

写**任何** plugin 代码 / hint / prompt 之前，先答这 3 个问题：

1. **能不能让系统侧 fail-loud 闸住？**
   - 能 → 写闸门（GatePlugin / 工具入参校验），**不准**用 hint 提醒 LLM
2. **能不能封装成 System 1 确定性工具让 LLM 调？**
   - 能 → 写 ToolPlugin，hint 里只列工具名 + 调用时机
3. **是不是真的"语义/决策/创意"问题？**
   - 是 → 才允许写 hint / prompt，且必须带"铁证"

### 1.4 反模式（铁证级）

#### 反模式 A："PNG 旁路反模式"（System 1 没闸住，靠 hint 教 LLM）

**场景**：发现 LLM 把某个工具的 `use_compat_mode=True` 当逃生口，结果不准。

| ❌ 错误 | ✅ 正确 |
|---|---|
| 把"严禁翻参数"写在 hint 里反复警告 | 物理移除该参数（System 1 闸住）/ 工具入口归一化掉 |

**铁律**：能让代码闸住的，就**不要**写在 hint 里教 LLM。LLM 会忘 / 误读 / 优先 short-cut。

#### 反模式 B：让 LLM 凭感觉算几何 / 配色

| ❌ 错误 | ✅ 正确 |
|---|---|
| hint 里写"请仔细配色避免撞色" | 写一个 `pick_color_pair(palette, conflict_set) -> (fg, bg)` 工具 |
| hint 里写"请让两个图形对齐" | 写一个 `align_horizontal(elements) -> coords` 工具 |
| LLM 算 `cos(45°) * 100` | 工具内做 `math.cos(math.radians(45)) * 100`，输出给 LLM 用 |

#### 反模式 C：System 1 工具内调 LLM

ToolPlugin 内部**绝不能** `import openai` / `import httpx` 调 LLM。这违反 TURBO 边界，破坏 unit test 100% 覆盖能力。

如果工具确实需要 LLM 输出，**让 ToolManager 之外的 ACT 调度逻辑**处理（即由主 agent 调用一个 LLM-driven 路径替代该工具）。

### 1.5 实战决策树

写一行新代码前，问自己：

```
这件事是确定性的（输入 → 唯一输出）吗？
├─ 是 → System 1（写工具 / 闸门 / 入口归一化）
│        测试用 unit test 覆盖；零成本
└─ 否（涉及理解 / 生成 / 决策） → System 2
        让 LLM 来做；测试用 record/replay
```

**举例 1**：判断"用户输入是否含敏感词" → 关键词列表查表 → System 1
**举例 2**：判断"用户输入语义上是否在抱怨产品" → 需要理解 → System 2
**举例 3**：把 markdown 转 HTML → 确定性映射 → System 1（用 markdown 库）
**举例 4**：写一个段落总结 → 创意生成 → System 2

---

## §2 Plugin 设计 5 大原则

### 2.1 SSOT (Single Source of Truth)

**定义**：任何元数据 / 配置 / 协议**只能有一份权威定义**。

| 维度 | 应放在哪 |
|---|---|
| Plugin 暴露的工具列表 | `ToolPlugin` 类内的 `get_tools()` 方法 |
| Plugin 配置 schema | `PluginConfig` dataclass 里 |
| 错误码与 message | 集中常量类（不要散在多处 raise） |
| Plugin 元数据（name / version / author） | `entry_points` group `krow.plugin` 内 |

**禁止**：

- ❌ 在 `__init__.py` 写一遍 tool 列表，然后在另一个 yaml 又写一遍 → 早晚漂移
- ❌ Plugin A 内写一份 ACT 配置，Plugin B 又复刻一份 → 两边走错路

### 2.2 OCP (Open-Closed Principle)

**定义**：对扩展开放、对修改关闭——加新能力**不应**改老代码。

| 准则 | 推荐 | 反例 |
|---|---|---|
| 新增功能加参数（带 default） | `read_file(path, start_line=None, encoding="utf-8")` | 加新工具 `read_file_v2` |
| 行为分流用 enum 字符串 | `mode="strict" / "lenient"` | `_strict_internal=True` 私参 |
| 复杂参数用 dict | `options={"compact": True}` | 10 个独立参数 |
| 不破坏旧调用 | 加新参数必须有 default；改 default 走灰度协议 | 直接改 default 让所有旧调用失效 |

**Plugin 视角的 OCP**：

- 你的 ToolPlugin 升级 v1 → v2 → v3 时，**老用户调用方式不变**（参数加 default）
- 加新工具 → 加新 `Tool` 子类，不改老 `Tool`
- 改 ACT 行为 → 加新 ACT 配置 enum，不改老 ACT yaml

### 2.3 SRP (Single Responsibility Principle)

**定义**：每个模块 / 函数 / 类只做一件事。

| Plugin 类 | 职责 |
|---|---|
| `ToolPlugin` | 提供工具集，每个工具单一动作 |
| `HintPlugin` | 提供软提示，**不**做参数校验 / 防御逻辑（那是 GatePlugin / 工具入口的事） |
| `GatePlugin` | 提供 fail-loud 守门，**不**做内容生成（那是 LLM 的事） |
| `EventListenerPlugin` | 监听事件 + 落审计，**不**改 agent 状态 |
| `ObservabilityPlugin` | metric / trace 输出，**不**做错误处理（那是 plugin 自己的事） |

### 2.4 DRY (Don't Repeat Yourself)

**定义**：同一段逻辑 / 文案 / schema 不准在多处出现。

**反模式**：

| 反例 | 修法 |
|---|---|
| 3 个工具内各自实现"路径转绝对路径"逻辑 | 抽 `_to_absolute(path) -> Path` 共享 |
| Hint 文本里同一句话写 3 遍（不同位置） | 抽常量；动态拼接 |
| 多个 plugin 各自校验"API key 格式" | 用 SDK 提供的 `validate_api_key()` 公共函数 |

### 2.5 复用 > 重造（**最关键**）

**写代码前的"造轮子检查"4 步**：

1. **Grep SDK 内现有 API** — 用主题关键词搜，命中 → 优先复用
2. **看 §6 基础设施清单** — 是不是已有现成 API（EventBus / ToolManager / etc.）
3. **看 SDK 文档** — quickstart.md / 本文 §6 是不是已有相关引导
4. **真没有再造轮子** — 但要在 GitHub Discussions 提一下"是不是 SDK 缺这个能力"

**反模式**（高频踩坑）：

- ❌ 在你的 plugin 内写一个新 EventBus → SDK 已有 `from krow_agent_sdk import EventBus`
- ❌ 在你的 plugin 内写一个 LLM client → SDK 已有 `from krow_agent_sdk.replay import LLMReplayStore`
- ❌ 在你的 plugin 内写文件 watch / 路径解析 → SDK 已有 helpers

---

## §3 ToolPlugin 设计哲学（**LLM 视角，不是程序员视角**）

### 3.1 基本原则

> 工具是给 **LLM** 用的，不是给程序员用的。所有设计按"LLM 视角"做 trade-off。

| 维度 | 原则 | 反例 → 推荐 |
|---|---|---|
| **数量** | 少而灵活：> 5 个工具共享同一动词 = 应合并 + 参数分流 | `pptx_create_freeform/grid/chart/table/...` 8 个 → `pptx_render_page_svg(page_kind=...)` 1 个 |
| **命名** | 动词在前 + 明确宾语 + 下划线小写 + 不带版本号 + 域前缀 | `file_reader_v2` → `read_file` |
| **输入鲁棒** | 接受多种格式（路径/enum 大小写/单值或 list/JSON 字符串或 dict）+ 自然语言 + 空值容错 | strict 类型 → 入口 `_normalize_input()` 归一 |
| **输出格式** | 自然语言/markdown > 平铺 JSON > 嵌套 JSON > 二进制；关键字段在首尾 | `{matches:[{file:{path,meta},loc:{line}}]}` 嵌套 → `{ok, summary, file, line, snippet}` 平铺 |
| **错误信息** | 黄金模板：一句话 + 原因 + 位置 + 1-3 个修法 + 相关链接 | `Error: invalid input` → `❌ 参数 page_kind 必须是 freeform/grid/chart/table 之一，你传了 'free'。修法：1) 改成 'freeform'；2) 调 pptx_list_page_kinds 看完整列表` |

### 3.2 命名规范（强约束）

**好命名**：

```
read_file
search_files
write_file
pptx_render_page_svg     ← 域前缀 pptx_ + 动词 render + 宾语 page_svg
excel_compute_formula
web_search
save_note
```

**坏命名**：

```
FileReader               ← PascalCase（Python 不爱）
read_file_v2             ← 带版本（OCP 反例）
pptx_create_v3_full      ← 同上
get_data                 ← 太泛；不知道做啥
helper_util              ← 不是动词宾语结构
```

### 3.3 入参鲁棒（LLM 经常输错）

LLM 给你的入参**100% 不可信**。要在工具入口做归一化：

```python
def my_tool(
    paths: Union[str, List[str], None],     # LLM 可能传单 str / list / None
    mode: str = "strict",                    # LLM 可能写 "Strict" / "STRICT" / "strict"
    options: Union[dict, str, None] = None,  # LLM 可能传 JSON 字符串
):
    # 入口归一
    if paths is None or paths == "" or paths == []:
        return _empty_result("paths 不能为空")
    if isinstance(paths, str):
        paths = [paths]
    paths = [_to_absolute(p) for p in paths]

    mode = mode.lower().strip()
    if mode not in {"strict", "lenient"}:
        return _error(f"mode 必须是 strict/lenient，你传了 '{mode}'")

    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            return _error("options 不是合法 JSON")
    options = options or {}

    # ... 真实逻辑
```

### 3.4 输出格式（LLM 视角）

**优先级**：自然语言 / markdown > 平铺 JSON > 嵌套 JSON > 二进制。

**好输出**：

```python
return {
    "ok": True,
    "summary": "找到 3 个匹配文件",
    "files": [
        {"path": "/a.py", "line": 10, "snippet": "def foo():"},
        {"path": "/b.py", "line": 25, "snippet": "foo()"},
    ],
}
```

**坏输出**：

```python
return {
    "result": {
        "data": {
            "items": [
                {"file": {"meta": {"path": ..., "size": ...}}, "loc": {"start": ..., "end": ...}}
            ]
        },
        "metadata": {"timestamp": ..., "version": ...}
    }
}  # 嵌套 4 层；LLM 取数据要 result.data.items[0].file.meta.path
```

### 3.5 错误信息黄金模板（**强制**）

```
❌ <一句话发生了什么>。
   原因：<根因>
   位置：<出错的具体参数 / 路径 / 行>
   修法：
     1. <最常见的修法>
     2. <备选修法>
     3. （可选）<更多上下文>
   相关：<相关工具 / 文档链接>
```

**好错误**：

```
❌ 参数 path 不存在该文件。
   位置：path = "./missing.py"
   修法：
     1. 检查路径拼写
     2. 调 search_files(name="missing.py") 看是否换了名
     3. 是新文件 → 先调 write_file 创建
   相关：read_file / write_file / search_files
```

**坏错误**：

```
Error: invalid argument
```

### 3.6 OCP 扩展性

| 准则 | 推荐 | 反例 |
|---|---|---|
| 新功能加参数（带 default） | `read_file(path, start_line=None, encoding="utf-8")` | 加新工具 `read_file_v2` |
| 行为分流用 enum 字符串 | `mode="strict" / "lenient"` | `_strict_internal=True` 私参 |
| 复杂参数用 dict | `options={"compact": True}` | 10 个独立参数 |
| 加新输出字段 | 始终 ok 返回 + 新字段直接加（不破老调用方） | 改返回结构搞 v2 |

### 3.7 红线

- ❌ ToolPlugin 内调 LLM（System 1 工具禁止 — TURBO 边界）
- ❌ 加 hint 教 LLM "别用某工具" → 物理移除工具 / `with_disabled_tools()` 闸住
- ❌ 工具数 > 5 共享同一动词 → 合并 + 参数分流
- ❌ 输出嵌套 3 层以上 JSON → 平铺
- ❌ 错误信息只说 "failed" → 黄金模板（含可执行修法）

### 3.8 实战 checklist（写完 ToolPlugin 后过一遍）

- [ ] 工具数 ≤ 5？或合理分类？
- [ ] 命名都是动词在前？
- [ ] 入参支持 LLM 常见输入变形（str/list/None/JSON 字符串）？
- [ ] 输出 ≤ 2 层嵌套？关键字段在顶层？
- [ ] 错误都用黄金模板？
- [ ] 加新功能的接口能向后兼容吗？
- [ ] unit test 100% 覆盖（System 1 应该可以做到）？

---

## §4 ACTPlugin 编写最佳实践

### 4.1 ACT 是什么

ACT (Activity / Capability Tier) = **一组工具 + 一份 hint 模板 + 一个语义意图**的捆绑。

LLM 不直接看完整工具列表（太长 → 注意力分散），而是按"当前任务意图"匹配出 1-3 个最相关的 ACT，每个 ACT 内的工具与 hint 才被注入到 prompt。

**简单类比**：ACT = 一个"工种"，里面有该工种的工具箱（tools）+ 工种说明书（hint）+ 招呼语（intent description）。

### 4.2 ACT 文件结构

```
my_plugin/
  acts/
    __act__.yaml              # ACT 元数据（必）
    extended.md               # 详细 hint（可选；按需加载）
    summary.md                # 简短摘要（必；hot path 注入 prompt）
```

### 4.3 `__act__.yaml` 写法

```yaml
name: my_research_agent
display_name: 科研论文助手
intent_description: |
  帮用户读论文、写综述、做 BibTeX 引用。
  适用：用户提到 "论文" / "paper" / "arxiv" / "综述" / "literature review" 等关键词。
tools:
  - search_arxiv
  - read_pdf
  - extract_bibtex
  - summarize_paper
hint_files:
  summary: summary.md
  extended: extended.md     # 可选；只在 LLM 主动 call when_extended_needed 时才加载
require_acts: []              # 可选；本 ACT 依赖的其他 ACT
exclude_acts: []              # 可选；与本 ACT 互斥的 ACT
```

### 4.4 写 `intent_description` 的黄金法则

**目标**：让 LLM 在意图匹配时一眼能判断"该不该选我"。

| 准则 | 示例 |
|---|---|
| 用**用户关键词**触发，不用"专业术语" | `"用户提到 论文/paper/arxiv"` 而不是 `"学术文献检索"` |
| 列**典型场景**（不是抽象功能） | `"读 PDF + 抽 BibTeX"` 而不是 `"信息抽取"` |
| **明确不适用场景** | `"不适用：纯算法问题、代码题、数学题"` |
| 控制在 100-200 字 | 太长 LLM 不读完 |

**好范例**：

```yaml
intent_description: |
  帮用户读论文、写综述、做 BibTeX 引用。
  适用：用户提到 "论文" / "paper" / "arxiv" / "综述" / "literature review"
        / "参考文献" / "BibTeX" 等关键词。
  典型场景：读 PDF 抽 BibTeX、对比多篇论文、生成综述大纲、转引用格式。
  不适用：写代码题、数学推理、纯网页搜索（用 web_search ACT）。
```

**坏范例**：

```yaml
intent_description: 学术文献处理工具集。   # 太抽象，LLM 不知道用户问啥时该选我
```

### 4.5 写 `summary.md`（hot path）

**目标**：50-200 字让 LLM 知道"现在我手上有什么工具、什么时候该用"。

```markdown
# 📚 科研论文助手

| 工具 | 用途 |
|---|---|
| `search_arxiv(query)` | arxiv 检索（关键词或 arxiv ID） |
| `read_pdf(path_or_url)` | 读 PDF 文本（自动 OCR 兜底） |
| `extract_bibtex(text)` | 从论文文本抽 BibTeX |
| `summarize_paper(text, length=500)` | 论文摘要 |

**典型流**：
1. `search_arxiv` 找论文
2. `read_pdf` 拉全文
3. `extract_bibtex` + `summarize_paper` 二选一
```

**铁律**：

- 不要在 summary.md 里写长篇逻辑 → 写到 `extended.md`
- 不要把每个工具的全部参数列出来 → ToolManager 会自动注入工具签名
- 用 markdown 表格让 LLM 一眼扫到

### 4.6 写 `extended.md`（按需加载）

**目标**：当 LLM 在某个具体任务上需要详细 know-how 时按需读。

```markdown
# 📚 科研论文助手 — 详细规则

## 何时调 `read_pdf`

- 用户给了 arxiv URL → `read_pdf(url)` 直接读
- 用户给了本地路径 → `read_pdf(path)`
- PDF 含大量公式 → 加 `mode="ocr_with_math"`

## BibTeX 抽取最佳实践

1. 优先用 `extract_bibtex` 自动抽
2. 如果文章是 preprint 没 DOI → 手填 `arxiv_id` 字段
3. ...
```

**何时该写 extended.md**：当 summary.md 已经塞不下、但 LLM 又确实需要这些细节时。

**何时不写**：

- 信息太杂 → 拆多个 ACT
- 信息只有 1-2 条 → 直接加到 summary.md

### 4.7 ACT hint 反模式

#### 反模式 A：在 hint 里写"严禁 / 不要"

| ❌ 错误 | ✅ 正确 |
|---|---|
| hint："严禁直接调 `os.system`" | 不暴露 `os.system` 工具（System 1 闸住） |
| hint："不要在用户没确认前删文件" | 在 `delete_file` 工具入口加确认 prompt（System 1 闸住） |

**铁律**：能让 System 1 物理闸住的，就**不要**写在 hint 里教 LLM。

#### 反模式 B：hint 与工具签名重复

ToolManager 自动注入每个工具的签名（参数 + docstring）。如果你在 hint 里又把签名写一遍 → DRY 违反 + 早晚漂移。

**正确**：hint 里只写"何时调用、串用顺序、典型组合"，**不**写参数细节。

#### 反模式 C：让 hint 长篇大论

LLM context 是稀缺资源。一个 ACT 的 hint 加起来 > 2K token → 反模式。

**修法**：

- 把详细规则拆到 extended.md（按需加载）
- 把多余规则下沉到工具入口归一化（System 1）
- 把铁律下沉到 GatePlugin（System 1）

---

## §5 其它 Plugin 类型边界（HintPlugin / GatePlugin / EventListener / Observability）

### 5.1 HintPlugin（**软**提示）

| 适用 | 不适用 |
|---|---|
| ✅ "如果用户问 X，建议先用 Y 工具" | ❌ "禁止用户做 X"（软提示不强制 → 用 GatePlugin） |
| ✅ "回答前先确认 Z" | ❌ "Z 必须 ≥ 10 字"（用 GatePlugin） |
| ✅ 给 LLM 注入领域知识（"金融数据习惯用 Q-Q 图"） | ❌ 业务校验逻辑 |

**关键约束**：HintPlugin 输出是**给 LLM 看的**，**不能**直接控制 agent 行为。如果你要"强制不让某事发生" → GatePlugin。

### 5.2 GatePlugin（**硬**守门）

`Gate` = 在 agent 行为之前插入的"检查闸"，不通过就**fail-loud**。

**典型用例**：

| 用例 | 实现 |
|---|---|
| 不允许 agent 在生产路径写文件 | Gate 检查 `path` 参数是否在白名单 |
| 不允许 agent 在工作时间外触发邮件 | Gate 检查当前时间 |
| Agent 调某 API 单次超过 1000 元成本上限 | Gate 检查累计 token 消耗 |
| Agent 准备 conclude 但还没完成必要步骤 | ConcludeGuard Gate 链 |

**铁律**：

- Gate 失败 = **agent 任务失败**，不是 retry。
- Gate 不应做"软警告"那是 HintPlugin 的事。
- Gate 应给清晰错误信息（黄金模板）让用户知道为什么挂掉。

```python
class MyGate(GatePlugin):
    name = "production_path_gate"

    def check(self, ctx: GateContext) -> GateDecision:
        write_path = ctx.tool_args.get("path", "")
        if "/production/" in write_path:
            return GateDecision(
                pass_=False,
                reason=(
                    "❌ 不允许在生产路径写文件。\n"
                    f"   位置：path = {write_path}\n"
                    f"   修法：1) 改写路径到 ./workspace/；"
                    f"2) 联系 ops 申请生产权限。"
                ),
            )
        return GateDecision(pass_=True)
```

### 5.3 EventListenerPlugin（审计 / metric）

适合**只读 / 旁路**的场景：

| 用例 | 实现 |
|---|---|
| 把 agent 每步行为落到 ELK | 监听 `executor.step.finished` → 写 Kafka |
| 统计每个 LLM 调用的 token | 监听 `llm.call.finished` → 累加到 Prometheus |
| 发现长任务 > 30min 自动通知用户 | 监听 `task.elapsed` → 触发钉钉 |

**关键约束**：

- 监听器**不应抛异常**（除非 fatal）
- 监听器**不应改 agent 状态**（只读）
- 监听器**不应做长 IO**（用异步队列）

### 5.4 ObservabilityPlugin（trace / metric）

与 EventListener 的区别：

| 维度 | EventListener | Observability |
|---|---|---|
| 触发 | 按事件订阅 | 全链路注入（span context） |
| 用途 | 落审计 / 通知 | 性能 trace / metrics 输出 |
| 输出 | 自由（Kafka / DB / log） | 标准化（OpenTelemetry / Prometheus） |

**典型用例**：

```python
class PrometheusObservability(ObservabilityPlugin):
    name = "prometheus_metrics"

    def on_span_start(self, span: Span):
        SPAN_START_COUNTER.labels(span.name).inc()

    def on_span_end(self, span: Span):
        SPAN_DURATION_HIST.labels(span.name).observe(span.duration_ms)
```

---

## §6 关键基础设施速查（公开 SDK 暴露的接口）

> 本节只列**公开 SDK 暴露给外部 plugin 用的 API**。私有 runtime 实现细节不在本文档范围。
> 完整 API 手册（带签名 + 例子）见 [`api-reference.md`](./api-reference.md)。

### 6.1 Agent 入口

```python
from krow_agent_sdk import (
    AgentBuilder,           # 链式 builder 构造 Agent
    Agent,                  # 主入口（不直接 new；通过 .build() 拿到）
    BudgetSpec,             # 预算配置 dataclass
    BuilderConfig,          # builder 内部状态 dataclass
    HttpGatewaySpec,        # HTTP gateway 配置（opt-in）
    StreamItem,             # run_stream() 返回的 envelope
    StreamItemKind,         # Literal["event", "result", "error"]
    EventBusReader,         # 给 plugin 看的只读 EventBus 视图
)
# AgentV3Result 不在 SDK 顶层 export；通过 result = agent.run(...) 拿到
```

| API | 用途 |
|---|---|
| `AgentBuilder()` | 启动构造链 |
| `.with_krow_api_key(key)` | 配 Krow API key |
| `.with_project_root(path)` | 指定 agent 工作根目录 |
| `.with_chat_model(name)` | 选 chat 模型（如 `"qwen3.6-plus"`） |
| `.with_reasoning_model(name)` | 选 reasoning 模型（如 `"deepseek-reasoner"`） |
| `.with_vision_model(name)` | 选视觉理解模型 |
| `.with_image_gen_model(name)` | 选图像生成模型 |
| `.with_image_edit_model(name)` | 选图像编辑模型 |
| `.with_text_encoder_model(name)` | 选 embedding 模型 |
| `.with_tool_plugin(plugin)` | 注册 ToolPlugin |
| `.with_act_plugin(plugin)` | 注册 ACTPlugin |
| `.with_hint_plugin(plugin)` | 注册 HintPlugin |
| `.with_gate_plugin(plugin)` | 注册 GatePlugin |
| `.with_event_listener_plugin(plugin)` | 注册 EventListenerPlugin |
| `.with_observability_plugin(plugin)` | 注册 ObservabilityPlugin |
| `.with_mcp_server_plugin(plugin)` | 注册 MCPServerPlugin（experimental，需 `KROW_ENABLE_MCP_SERVER_PLUGIN=1`）|
| `.with_security_plugin(plugin)` | 注册 SecurityPlugin（experimental）|
| `.with_domain_pack_plugin(plugin)` | 注册 DomainPackPlugin（experimental）|
| `.with_visual_adapter(ext, cls)` | 注册 VisualAdapter（按文件扩展名）|
| `.with_visual_adapter_plugin(plugin)` | 注册 VisualAdapterPlugin（批量）|
| `.with_default_pptx_adapter()` | 一行打开 PPTX 视觉质检 |
| `.with_replay_store(store)` | 走 record/replay 测试模式 |
| `.with_budget(BudgetSpec(...))` | 自定义预算 |
| `.with_http_gateway(HttpGatewaySpec(...))` | opt-in HTTP gateway |
| `.with_*_plugins_from_entry_points()` | opt-in 扫 entry_points 自动注册（需 `KROW_ENABLE_PLUGIN_ENTRY_POINTS=1`） |
| `.build(validate_connection=True)` | 构造 Agent（自动凭证注入 + cloud 模型 fallback） |

```python
# 阻塞式（返回 AgentV3Result，不是 RunResult）
result = agent.run(user_input)
# result.success / result.solution / result.execution_result / result.final_output

# 流式（用户可中断；详 quickstart §2 流式输出）
for item in agent.run_stream(user_input):
    if item.kind == "event":
        # event 是 modules.events.bus_core.Event dataclass
        print(item.event.type, item.event.payload)
    elif item.kind == "result":
        print("Done:", item.result.final_output)
    elif item.kind == "error":
        raise item.error  # 后台异常
```

### 6.2 LLM helper（在 LLM-driven Tool 中按需用，注意 §1.4 反模式 C）

```python
from krow_agent_sdk.llm import build_chat_message, build_chat_messages
# build_chat_message(role, content) -> dict
# build_chat_messages(system, user) -> list[dict]
```

> ⚠️ **TURBO 边界**：System 1 工具内**禁止**调 LLM。LLM-driven 工具的合理形态是把工具上层"ACT-内 ReACT 循环"作为驱动方，工具本身仍是 deterministic helper。详 §1.4 反模式 C。

### 6.3 EventBus（只读视图）

`EventBusReader` 是 SDK 给 plugin 提供的只读视图（不能 publish），通过 `agent.event_bus` 访问：

```python
from krow_agent_sdk import EventBusReader

reader: EventBusReader = agent.event_bus  # 只读 EventBusReader（不是 EventBus）

def on_step(event):
    # event 是 modules.events.bus_core.Event dataclass：type / payload / trace_id / timestamp
    print(event.type, event.payload)

token = reader.subscribe("progressive.step_completed", on_step, track_recent=True)
# ...
reader.unsubscribe(token)

# 也支持 ring buffer 回看（仅 track_recent=True 的 topic）：
for ev in reader.iter_recent("progressive.step_completed", n=10):
    print(ev.type, ev.payload)
```

> Plugin 想"发"事件 → 走 P5 EventListenerPlugin 的 listener 副作用 / P6 ObservabilityPlugin 自己的 sink，**不**通过 SDK 反向 publish（保单向 pub-sub）。

### 6.4 Replay Store（测试一等公民）

```python
from krow_agent_sdk.replay import LLMReplayStore

# 推荐：从环境变量决定 mode（CI replay / 本地 record / auto）
store = LLMReplayStore.from_env(
    "tests/fixtures/my_test.json",      # fixture 路径
    mode_env="KROW_LLM_REPLAY_MODE",    # 默认值
    default="replay",
)

# 或显式指定
from pathlib import Path
store = LLMReplayStore(Path("fixtures/x.json"), mode="replay")

agent = (
    AgentBuilder()
    .with_replay_store(store)            # SDK 自动 wrap 所有 LLM provider
    .build()
)
```

**特点**：

- 0 token 成本（replay 模式）
- 完全确定性可重放（key = request hash）
- CI 可跑（`KROW_LLM_REPLAY_MODE=replay`，cache miss 抛 `LLMReplayMiss`）
- mode：`record` / `replay`（默认）/ `auto`

### 6.5 Plugin 接口（**实例属性 / 协议方法**，不是 ctx 注入）

> SDK 走 **Protocol**（duck typing） + 实例属性的扁平形态，**没有** PluginContext / ToolContext 注入。`plugin_id` 是 property / class attr，工具 handler 直接是 `Callable`。

```python
from krow_agent_sdk.protocols import ToolPlugin, ACTPlugin

# ToolPlugin: plugin_id (property) + get_tools() -> list[ToolSpec]
class MyToolPlugin:
    plugin_id = "acme.search"   # 双段 "<org>.<plugin_name>"

    def get_tools(self) -> list[dict]:
        return [{
            "name": "acme_search",
            "description": "搜某个数据库",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            "handler": _do_search,    # Callable[..., Any]
        }]

def _do_search(query: str) -> dict:
    if not query.strip():
        return {"ok": False, "error": "❌ query 不能为空。"}
    return {"ok": True, "results": [...]}


# ACTPlugin: plugin_id + act_name (property) + get_act_root() + get_act_file_path() + get_tool_names()
# 详 quickstart.md §3 + api-reference.md §5.1
```

### 6.6 Lifecycle hooks（可选）

```python
from krow_agent_sdk import BasePluginLifecycle, SDKContext

class MyPlugin(BasePluginLifecycle):
    plugin_id = "acme.example"

    def on_load(self, ctx: SDKContext) -> None:
        # ctx.api_key  : str
        # ctx.workspace: Path
        # ctx.event_bus: EventBusReader  (只读，不能 publish)
        ...

    def on_unload(self) -> None:
        ...
```

`BasePluginLifecycle` 是**可选** mixin —— Protocol 本身不要求 lifecycle 方法。`on_load` 异常 → fail-loud；`on_unload` 异常 → log warning 不阻塞。

### 6.7 Plugin entry_points（**opt-in**，默认关）

在你的 `pyproject.toml` 内（一个 plugin 一个 group）：

```toml
[project.entry-points."krow.act_plugin"]
my_research = "my_pkg.plugin:get_act_plugin"

[project.entry-points."krow.tool_plugin"]
my_cad = "my_pkg.cad:CADQueryPlugin"
```

主进程**默认不**自动扫描；用户必须 opt-in：

```python
import os
os.environ["KROW_ENABLE_PLUGIN_ENTRY_POINTS"] = "1"

agent = (
    AgentBuilder()
    .with_krow_api_key(key)
    .with_all_plugins_from_entry_points()  # 扫 9 个 group
    .build()
)
```

或按类型粒度扫：

```python
.with_act_plugins_from_entry_points()
.with_tool_plugins_from_entry_points()
.with_hint_plugins_from_entry_points()
.with_gate_plugins_from_entry_points()
.with_event_listener_plugins_from_entry_points()
.with_observability_plugins_from_entry_points()
.with_domain_pack_plugins_from_entry_points()
.with_visual_adapter_plugins_from_entry_points()
```

> **安全**：默认关闭防 supply-chain（恶意 wheel install 自动注入 plugin）。打开 entry_points 自动扫描 = 信任 PyPI 上所有装的 wheel；生产建议保持显式 `.with_<type>_plugin(...)`。

---

## §7 测试方法论

### 7.1 三层测试金字塔

```
        ▲
        │  E2E 真实 LLM 测试（少而精）
        │  - 跑 1-2 个完整 user journey
        │  - 用真实 LLM 验证 prompt 与模型对齐
        │  - nightly 跑（成本高）
        │
        │  Replay 测试（覆盖核心路径）
        │  - 用 LLMReplayStore 跑录制好的 LLM 对话
        │  - 0 token 成本 + 完全确定性
        │  - 每次 PR / push 都跑（CI 主力）
        │
        │  Unit 测试（覆盖 System 1）
        │  - 测工具入参归一、错误模板、Gate 守门
        │  - 100% 覆盖（System 1 应该可以做到）
```

### 7.2 写 Unit 测试（System 1）

System 1 工具应该**100% 可被 unit test 覆盖**：

```python
def test_my_tool_empty_query():
    tool = MyTool()
    result = tool.execute(ctx=mock_ctx(), query="")
    assert result["ok"] is False
    assert "不能为空" in result["error"]


def test_my_tool_normalizes_path_list():
    tool = MyTool()
    # 单 str → 自动包装为 list
    result = tool.execute(ctx=mock_ctx(), paths="/a")
    assert result["normalized_paths"] == ["/a"]
    # list → 保持
    result = tool.execute(ctx=mock_ctx(), paths=["/a", "/b"])
    assert result["normalized_paths"] == ["/a", "/b"]
```

### 7.3 写 Replay 测试

> **真实 API**：`LLMReplayStore` 的 mode 由 `KROW_LLM_REPLAY_MODE` env 或构造参数决定；`record` 模式下每次 LLM 调用自动 `put` 到 fixture，无需手动 `save()`。

**录制阶段**（本地一次性，跑前 `set KROW_LLM_REPLAY_MODE=record`）：

```python
import os
from pathlib import Path
from krow_agent_sdk import AgentBuilder
from krow_agent_sdk.replay import LLMReplayStore

os.environ["KROW_LLM_REPLAY_MODE"] = "record"  # 本地 record；CI 默认 replay
store = LLMReplayStore.from_env("./fixtures/my_test.json")
agent = (
    AgentBuilder()
    .with_krow_api_key(os.environ["KROW_API_KEY"])
    .with_project_root("./workspace")
    .with_replay_store(store)            # SDK 自动 wrap LLM provider
    .build()
)
try:
    result = agent.run("我的测试 user input")
    assert result.success
finally:
    agent.shutdown()  # 自动 uninstall replay swap，并 persist fixture
```

**回放阶段**（CI 每次跑）：

```python
import pytest
from krow_agent_sdk import AgentBuilder
from krow_agent_sdk.replay import LLMReplayStore


def test_my_journey_replay():
    # CI 默认 replay；fixture 必须已被 record 阶段提交到仓
    store = LLMReplayStore.from_env(
        "./fixtures/my_test.json",
        default="replay",
    )
    agent = (
        AgentBuilder()
        .with_krow_api_key("sk-user-fake-for-replay-mode-only")
        .with_project_root("./workspace")
        .with_replay_store(store)
        .build()
    )
    try:
        result = agent.run("我的测试 user input")
        assert result.success
        assert "expected_output_substring" in result.final_output
    finally:
        agent.shutdown()
```

**cache miss 行为**：默认 `on_miss="raise"` → 撞 cache miss 抛 `LLMReplayMiss`，提示需要重 record，避免悄悄烧钱。

### 7.4 写 E2E 真实 LLM 测试

**关键问题**：LLM 不确定性 → 用什么作为 PASS/FAIL 判据？

**答**：**预期结果卡 + 多维断言 + 容差**。

预期结果卡示例（`fixtures/expected_my_journey.yaml`）：

```yaml
expected_actions:
  macro_steps_min: 3
  macro_steps_max: 8
  required_tools_called:
    - search_arxiv
    - read_pdf
expected_artifacts:
  output_file: "./output/summary.md"
  output_size_kb_min: 1
  output_size_kb_max: 50
expected_quality:
  must_contain:
    - "BibTeX"
  must_not_contain:
    - "TODO"
    - "lorem ipsum"
expected_fail_signals:
  no_replan_more_than: 2
  no_budget_exhausted: true
  llm_calls_max: 80
expected_perf:
  wall_clock_max_seconds: 600
```

测试代码：

```python
def test_my_journey_real_llm(real_llm_available):
    if not real_llm_available:
        pytest.skip("nightly only")
    expected = yaml.safe_load(open("./fixtures/expected_my_journey.yaml"))

    agent = AgentBuilder().with_krow_api_key(KEY).build()
    result = agent.run("写一篇 transformer 综述")

    # 多维断言
    assert result.success
    assert expected["expected_actions"]["macro_steps_min"] <= result.macro_steps_count
    assert all(t in result.tools_called for t in expected["expected_actions"]["required_tools_called"])
    assert Path(expected["expected_artifacts"]["output_file"]).exists()
    # ... 其它维度
```

### 7.5 测试反模式

| ❌ 错误 | ✅ 正确 |
|---|---|
| `mock.patch('httpx...')` 模拟 LLM | 用 `LLMReplayStore` |
| 测试内 `time.sleep(N)` 死等 | 用 `wait_until(predicate)` |
| 测试用一个完美 LLM 输出做绝对断言 | 用预期结果卡 + 多维容差 |
| 不写 unit test，只写 e2e | unit test 是 System 1 的护栏，必须有 |
| record 完后 LLM 改了 → 测试还过 | 定期跑真实 LLM 验证 prompt 与模型对齐 |

---

## §8 反模式黑名单（带铁证）

> 凡违反这一节的设计，**99% 概率会出 bug**。请逐条核对。

### 8.1 TURBO 边界违反

| 反模式 | 铁证 | 修法 |
|---|---|---|
| ToolPlugin 内 `import openai` 调 LLM | 失去 unit test 100% 覆盖；性能可重放性破坏 | 把 LLM 驱动逻辑抽到上层 ACT；ToolPlugin 只做 System 1 |
| HintPlugin 内做参数校验 | LLM 经常忽略软提示 → 校验形同虚设 | 用 GatePlugin（System 1 fail-loud） |
| 让 LLM 算 `cos / sin / 颜色对比度` | LLM 算数不可靠（已知数学题翻车率 5-10%） | 写 System 1 工具查表 / 计算 |
| 用 regex 抽语义信息（"是不是抱怨"） | 自然语言无穷变化；regex 一定漏 | 用 LLM (System 2) |

### 8.2 SSOT / DRY 违反

| 反模式 | 铁证 | 修法 |
|---|---|---|
| 在 plugin yaml 写一遍工具列表，又在 `__init__.py` 注册一遍 | 早晚漂移 → bug | yaml 是 SSOT，code 自动读 yaml |
| 错误信息散在 5 个 `raise ValueError(...)` | 改文案要找 5 处 | 集中常量类 |
| `summary.md` 重复 ToolManager 自动注入的工具签名 | LLM 看 2 遍浪费 token | summary.md 只写"何时调"，不写参数 |

### 8.3 OCP 违反

| 反模式 | 铁证 | 修法 |
|---|---|---|
| `read_file_v2` / `read_file_v3` | LLM 不知道选哪个；老代码全失效 | 加新参数 `read_file(path, mode="...")` |
| 改 `read_file()` default 让所有旧调用变行为 | 静默改变行为 → 历史 hint 全错 | 加新参数；旧 default 不变 |

### 8.4 错误处理反模式

| 反模式 | 铁证 | 修法 |
|---|---|---|
| `try: ... except: pass` 吞错继续 | 用户拿到错误结果不知情 | 至少 log + raise；最好 fail-loud 给清晰信息 |
| 错误信息只说 "failed" | LLM 不知道怎么修 | 用 §3.5 黄金模板 |
| LLM 失败 1 次直接返回 "我做不到" | 应有 1-3 次 retry + 不同策略 | SDK 的 ProgressiveExecutor 自带；plugin 不要自己 short-circuit |

### 8.5 测试反模式

| 反模式 | 铁证 | 修法 |
|---|---|---|
| `mock.patch('httpx.post')` 模拟 LLM | 重造 `LLMReplayStore` 轮子；LLM 协议变就漂 | 用 `LLMReplayStore` |
| 测试内 `time.sleep(5)` 死等 agent | 慢 + 容易 flaky | 用 `wait_until` / event 监听 |
| 只写 e2e 不写 unit | System 1 没护栏 | 先写 unit 100% 覆盖工具入口归一 |
| 依赖一次 LLM 输出做绝对断言 | LLM 不确定性 → 偶发 fail | 用预期结果卡 + 多维容差 |

### 8.6 信息披露反模式（**Plugin 作者关心**）

| 反模式 | 铁证 | 修法 |
|---|---|---|
| 把 KROW_API_KEY 透传给第三方 API | 凭证泄漏风险 | 只在 SDK <-> Krow Cloud 链路上用 |
| 把用户业务数据 log 到 stdout | 可能被 ELK 截到 | 脱敏 / log 前过滤 |
| 把 Plugin 内部 stack trace 全文返回给 agent | LLM 可能在用户输出里复述 | 错误黄金模板内只露用户能修的 hint |

---

## 进一步阅读

- [`quickstart.md`](./quickstart.md)：5 分钟入门 + 5 类 plugin 范例
- [`external-developer-onboarding.md`](./external-developer-onboarding.md)：第 1 周节奏 + 3 种领域适配
- [`runtime-install.md`](./runtime-install.md)：runtime wheel 装机指南
- [`roadmap.md`](./roadmap.md)：SDK 进度 + milestone

---

> 文档版本：跟随 `krow-agent-sdk` PyPI 主版本同步发布；当前与最新 patch 对齐
> （当前 PyPI: <https://pypi.org/project/krow-agent-sdk/>）。本文档持续吸纳社区反馈 —
> 欢迎到 [GitHub Discussions](https://github.com/aullik5/krow-sdk-docs/discussions) 提建议。
