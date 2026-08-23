# skill-loader · 用 markdown 扩展 agent，不写 Python

本目录演示 Krow SDK 的**外部 `SKILL.md` 装载**：把一份用 markdown 写的指令手册接进 agent，让它像内置能力一样出现在 planner 的菜单里。

不需要写 Python，不需要打包，不需要注册 entry point。

## 它演示了什么

| SDK 能力 | 本 demo 的用法 |
|---|---|
| `with_skill_directory(path)` | 装载 `skills/` 下的两个 `SKILL.md` |
| `get_skill_reports()` | 打印每个 skill "被怎么处理了" |
| `SkillLoadError` | skill 写错时 fail-loud，不安静地少装一个 |

## 快速开始

```bash
pip install -e ".[test]"

python main.py --dry-run        # 只看翻译结果，不需要 API key / runtime
```

输出会告诉你每个 skill 被翻译成了什么，以及三件在你背后发生的事（见下）。

```bash
python main.py                  # 构建真实 agent（需 KROW_API_KEY + runtime）
```

## `SKILL.md` 长什么样

```markdown
---
name: word-format
description: 用户要求"按 X 的格式排版 Y"时用；以一份已排版 .docx 为模板统一版式
when_to_use:
  - 用户给了一份"参考文件"和一份"待排版文件"
allowed-tools:
  - word_apply_style_spec
---

（正文是完整的 markdown 指令手册，会被 verbatim 送给 LLM）
```

只有 `name` 和 `description` 是必须的。

> **`description` 要写清"何时用"，不是"是什么"。** 它是 planner 菜单里唯一常驻的那一行；省略 `when_to_use` 时它还会兼任 `planner_hint`。写成"Word 排版工具"，planner 就没有选用它的依据。

## 三件会在你背后发生的事

skill 是**你写的**，但装载链上有三处会被自动处理。`get_skill_reports()` 就是把它们问出来的地方 —— 跑一次 `--dry-run` 就能看到：

| 发生什么 | 为什么 | 报告字段 |
|---|---|---|
| `word-format` → `word_format` | ACT 名只收小写字母、数字、下划线 | `renamed` / `act_name` |
| `allowed-tools` 里有的名字被忽略 | 那个工具在当前环境不存在，**不做猜测映射** | `unknown_tools` |
| 正文被注入过滤改写了一段 | 该过滤对所有扩展 ACT 无条件生效 | `injection_detections` |

第三条尤其值得看一眼：过滤是**生效的**，但如果只写进日志，你的手册被改了一段而你不会知道。所以这里把它报出来。

## 翻译产物是可以打开看的

装载时 skill 会被物化成一个标准扩展 ACT：

```
.krow/skills/word_format/
├── __act__.yaml      ← 你的 frontmatter 被翻译成的样子
└── ext_word_format.md ← 你的正文，逐字
```

想确认"我的 skill 到底被理解成了什么"，直接读 `__act__.yaml`。报告里的**已物化到**就是这个路径。

> 你的 `skills/` 目录**全程只读** —— 它可以放在只读挂载上。

## 什么时候该改用 Python

`SKILL.md` 覆盖的是"一份指令手册 + 几个已有工具"。以下情况请改写 ACTPlugin：

| 需求 | 选 |
|---|---|
| 注册**新工具**（Python 函数） | ToolPlugin + ACTPlugin |
| 需要 `on_load` / `on_unload` 生命周期钩子 | ACTPlugin |
| 运行时按条件动态改 ACT 内容 | ACTPlugin |
| 只想让不写代码的同事也能改 | `SKILL.md` |

## 边界

- **不执行** skill 里的脚本（不 `exec` / 不 `subprocess` / 不导入其中的 python）。从别的生态搬来的 skill 若带 `scripts/*.py`，脚本需由 LLM 走终端工具调用。
- 不做隐式目录发现 —— 路径必须显式给出。默认 OFF 的形式就是"你没写 `with_skill_directory` 那行"，没有 env 开关。
- skill 只能**引用**已存在的工具，不注册新工具；因此工具名**不加**前缀。
- skill 名冲突会报错，不静默覆盖。

## fork 成自己的

1. 把 `skills/` 换成你自己的 `SKILL.md`
2. `description` 按"何时用"来写
3. `allowed-tools` 填你环境里**真实存在**的工具名（跑 `--dry-run` 看哪些没命中）
4. `python main.py --dry-run` 确认翻译结果符合预期

## 测试

```bash
pytest tests/ -v
```
