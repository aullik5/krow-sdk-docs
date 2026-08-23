---
name: word-format
description: 用户要求"按 X 的格式排版 Y"/"照着模板统一版式"时用；以一份已排版 .docx 为模板，把纸张、页边距、分栏与样式表搬到目标文档，内容一个字不改。
when_to_use:
  - 用户给了一份"参考文件"和一份"待排版文件"
  - 需要保留文档里 MathType / OLE 公式不被破坏的排版任务
  - 用户说"严格按 X 的排版规范重排 Y"
allowed-tools:
  - word_extract_style_spec
  - word_apply_style_spec
  - word_analyze_state
---

# 按模板统一 Word 版式

## 先确认两份文件分别是什么

用户至少要给出两份 `.docx`：

- **模板**：已经排好版的那份，只读，不改
- **目标**：需要被重排的那份

如果只给了一份，先问清楚另一份在哪，不要自己猜一个"通用美化"方案顶上。

## 步骤

1. 用 `word_extract_style_spec` 读模板，向用户复述读到的版式（纸张、页边距、栏数、栏间距）。
   这一步是给人看的确认，不是给自己看的。

2. 用 `word_apply_style_spec(file_path=目标, template_path=模板)` 一步套用。

   **不要**先把模板的字号字体读出来、再逐项填给 `word_smart_beautify`。
   完整版式规格序列化后上万字符，远超参数截断阈值，转述必然丢东西且丢得无声无息。

3. 读返回值里的 `verified`。

   - `verified=true` → 向用户报告改了哪些（`section_changes` 里有改前改后）
   - `verified=false` → **不要报成功**，把 `verification_mismatches` 逐条讲给用户

## 边界：公式的字号不归这里管

含 MathType 公式的文档（数学教辅等），公式所在的 run 会被自动跳过 —— 公式的字号和间距由它自己的内嵌二进制决定，改 Word 的样式表对它没有作用。

用户如果要求"公式也要 12 磅"，如实说明这需要用 MathType 自己的 `.eqp` 配置来处理，本流程不承接。**不要**假装做到了。
