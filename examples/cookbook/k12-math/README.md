# K12 数学知识编译 · SDK Cookbook

把 K12（初中/高中）数学教材、讲义、知识点总结编译成**教育知识图谱**：
知识目录、知识点、定义、定理、公式、原子知识、原子技能、解题方法，以及目录层级
（`part_of`）、内容挂载（`has_*`）、知识/技能依赖（`requires_knowledge` /
`requires_skill`）、学习前置（`prerequisite_of`）等学习路径骨架关系。

> 这是面向 **SDK 开发者二次开发** 的范例。K12 数学领域包 `k12_math` 已随
> runtime 内置（声明式 manifest），开发者**无需重写抽取/物化轮子**——一行
> `.with_domain_pack("k12_math")` 即可让知识编译走 K12 本体；要做校本/题库特化，
> 用 `.with_domain_pack_manifest(...)` 继承 `k12_math` 再追加即可。

## 这个 cookbook 演示什么

1. **激活内置 K12 包**：`AgentBuilder().with_domain_pack("k12_math")`
   —— entity/relation kinds + few-shot + planner hints + WikiSpec + 学习路径 gate
   一次性生效。
2. **内置题库层包**：`.with_domain_pack("k12_question_bank")`
   —— 在 `k12_math` 之上叠加题目（`question`）/解答（`solution`）/解题步骤
   （`step`）/错误模式（`error_pattern`）实体，及 `tests`（考查）/`practices`
   （训练）/`has_solution` / `has_step` / `next_step_of` / `uses_knowledge` /
   `uses_skill` / `uses_method` / `may_trigger_error` / `variant_of` 等关系。
   自带 mock 题库数据 `mock_question_bank/`（真实 K12 资料多缺题库，先用 mock
   提前覆盖与验证）。
3. **校本二次开发**：`.with_domain_pack_manifest("k12_school_pack.yaml")`
   —— 继承 `k12_math`，追加自有题库实体（`question`）/关系（`tests`）。
4. **System 1 评分工具**（零 LLM、可单测）：前置 DAG 环检测、TESTS 权重归一化、
   难度/前置多维聚合（`modules.knowledge.k12_scoring`）。
5. **学习路径 gate**：`prerequisite_of` 成环时 conclude 被 fail-loud 阻断；
   题库层激活时同一题所有 `tests` 边考查权重和偏离 1 也被阻断
   （`GateK12LearningPath`，编译期自动生效）。

## 跑前

```bash
# 1. 设 API key
export KROW_API_KEY=sk-user-xxx      # PowerShell: $env:KROW_API_KEY='sk-user-xxx'
# 2. 安装 runtime
krow-sdk-install --api-key $KROW_API_KEY
# 3. 装本 cookbook
cd examples/cookbook/k12-math && pip install -e .
```

## 跑法

```bash
# 最小跑（自带导数/概率/立体几何 3 份知识点资料）
python main.py

# 用自己的 K12 资料 + 自定义校本包
python main.py path/to/k12_docs --project-dir ./my_k12_kb --school-pack k12_school_pack.yaml

# 题库层：用自带 mock 题库数据 + 叠加内置 k12_question_bank 包
python main.py mock_question_bank --question-bank --project-dir ./my_k12_qb
```

## 输出

```
<project-dir>/.krow/ontology/global.db   # 本体 SSOT（知识点/定理/公式/关系）
<project-dir>/.krow/wiki/**/*.md         # 知识点百科词条
output/k12_compile_report.md             # 编译验收 + 学习路径校验报告
```

## 关键 API（二次开发速查）

```python
from krow_agent_sdk import AgentBuilder

agent = (
    AgentBuilder()
    .with_krow_api_key(api_key)
    .with_project_root(project_dir)
    .with_domain_pack("k12_math")                       # 激活内置 K12 包
    .with_domain_pack_manifest("k12_school_pack.yaml")  # 可选：校本/题库特化
    .build()
)
report = agent.run(
    "把 docs/ 下的 K12 数学资料编译成知识百科",
    task_context={"strategy": "knowledge_compile"},
)
```

System 1 评分工具（独立可用，不依赖 LLM）：

```python
from modules.knowledge.k12_scoring import (
    detect_prerequisite_cycles,   # 前置 DAG 环检测（学习路径必须无环）
    normalize_weights,            # TESTS 权重归一化（和=1）
    aggregate_dimensions,         # 难度/前置多维加权聚合
)
report = detect_prerequisite_cycles([("求导", "判断单调性"), ("判断单调性", "求极值")])
assert report.is_dag
```

### 数学公式 LaTeX 增强（图片公式 → LaTeX）

K12 讲义（如立体几何/概率）的公式大量以 WMF/EMF 图片存储，纯文本抽取拿不到 →
`Formula` 节点 `latex` 恒空。`modules.knowledge.formula_latex` 复用既有基础设施
（`metafile_image` 栅格化 + 视觉 LLM `chat_vision` + `coerce_attributes` 归一）
补公式 LaTeX，fail-soft 不编造：

```python
from modules.knowledge.formula_latex import (
    extract_docx_formula_images, recognize_formula_latex,
)
for fi in extract_docx_formula_images("讲义.docx"):
    res = recognize_formula_latex(fi.png_bytes, context_text=fi.context_text)
    if res.ok:
        print(res.latex)     # 识别失败 → latex 留空待补，不编造
```
