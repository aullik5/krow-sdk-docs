# Cookbook · 配置决策脑（litsci-metacog）：看得见 + 动得了手

把你自己垂直功能的**完整度信号**接进 Krow 的元认知**决策脑**（GWT 全局工作站），并让它对这个信号**做针对性的事**。本 demo 以"文献检索下载完整度"为例，是自包含的——不依赖任何真实检索后端，纯 System-1 逻辑，无需 LLM / API key 即可跑通。

两个面，配套交付（缺任一面都是半边墙）：

| 面 | 文件 | 回答 |
|---|---|---|
| **观测面**（三注册表） | `litsci_metacog_demo.py` | 决策脑**看见**"检索有果却零下载" |
| **执行面**（执行器） | `litsci_actuation_demo.py` | 看见之后**改做什么**：不再重试全文，转元数据清单交付 |

只有观测面时，你能做的极限是把信号发出去，然后期待通用决策（`replan` / `converge`）恰好对症——真实体感是传感器天天报"零下载"，而系统只会让 LLM 再 replan 一次同样的检索。

## 为什么需要它

Krow 的 macro 编排不是死循环，而是一个决策脑：平时静默观测，只在"该管"时稀疏唤醒 LLM 做决策，事后结算这次决策有没有用。但它**默认只懂通用信号**（预算、停滞、工具连败…）。如果你做的是文献检索、报告生成、代码审查这类垂直功能，决策脑并不知道"你离交付还差多少"。

典型事故：文献检索到 91 篇候选、却因约束过严"零确认、跳过下载"，多轮规划→执行空转十几分钟——而决策脑毫无察觉。根因就是**领域完整度信号没接进工作站**。三注册表就是解决这个的扩展点。

## 三注册表一句话

| 注册表 | 角色 | 你提供 |
|---|---|---|
| `SituationContributor` | 观测层 | `applicable(exe)->bool` + `__call__(exe)->{"error_vector","signals"}` |
| `WakeTrigger` | 唤醒层 | `(prev,curr,delta,ledger)->str\|None` |
| `DecisionClassifier` | 结算层 | `(action,snap,ledger)->str\|None`（本 demo 复用核心，不自定义） |

- **error_vector**：离验收的距离（0~1）。喂核心"停滞/恶化"判定——**大多数场景你只写这个，连自定义 trigger 都不用**。
- **signals**：观测明细（任意事实）。供你自己的 wake trigger 语义判定 + 事件可观测。

## 跑起来

```bash
# 1. 装 SDK（含 runtime 才能真正注册到决策脑）
pip install "krow-agent-sdk[runtime]>=0.9.0.59"

# 2. 看 demo（无需 API key）
python main.py

# 3. 跑测试
pip install -e ".[test]"
pytest -q
```

`main.py` 会模拟三种态势并打印结果：

- **场景 A**（5 篇候选、0 下载）→ `error_vector.download_gap=1.0`，wake 命中"零下载"；
- **场景 B**（5 篇下 4 篇）→ `download_gap=0.2`，wake 不命中（正常推进）；
- **场景 C**（非文献任务）→ `applicable=False`（收窄门禁，避免"传感器失活"假阳）。

然后跑一遍**执行面**：连续几拍"又试了一轮下载、仍然零成功"，执行器在第 3 拍开火，往计划里追加一步"导出元数据清单"，第 4 拍起因触顶而让位。执行面需要 `[runtime]`（注册表在 runtime 里），缺则自动跳过并打印提示。

## 核心用法（`litsci_metacog_demo.py`）

```python
from krow_agent_sdk.metacognition import (
    register_domain_axis,
    register_situation_contributor,
    register_wake_trigger,
    get_registry_snapshot,
)

register_domain_axis("litsci_download_gap")                     # 领域轴：先登记极性
register_situation_contributor(DownloadCompletenessContributor)  # 传类即可，自动校验可 re-import
register_wake_trigger(wake_zero_download_with_hits)

print(get_registry_snapshot()["counts"])  # 确认注册上了
```

进程启动早期注册一次即可（幂等）。之后 Agent 每个 macro 拍会自动采集你的信号。

### 唤醒声明面：不写这三行，你的触发器会系统性输掉裁决

裁决按 **价值轴权重 × 强度** 排序。域触发器若不声明轴、不自报强度，强度恒 1.0、价值轴落最低档——生产 litsci 曾出现某触发器连续 25 拍命中却一次没赢过。

```python
from krow_agent_sdk.metacognition import VALUE_AXIS_COMPLETENESS, wake_magnitude_from_ratio

wake_zero_download_with_hits.value_axis = VALUE_AXIS_COMPLETENESS  # 争的是完整度不是准确性
wake_zero_download_with_hits.error_axis = "litsci_download_gap"    # 谁的误差
wake_zero_download_with_hits.handled_by = ("replan", "converge")   # 谁来处置（满秩校验查这条）

def wake_zero_download_with_hits(prev, curr, delta, ledger):
    ...
    # 返二元组 = 自报强度。只返字符串 → 强度恒 1.0
    return f"download_gap:{failed}/{requested} 下载失败", wake_magnitude_from_ratio(ratio, 0.5)
```

三条声明的分工：`value_axis` 答"有多重要"，`error_axis` 答"谁的误差"，`handled_by` 答"谁来处置"。缺最后一条会被满秩校验拒——一条轴报了误差却没有决策认领它，就是"传感器齐全但执行器不读"的开环。

声明齐了却还是赢不了裁决时，先查这两格（0.9.1.13+）：

```python
snap = get_registry_snapshot()
snap["axes"]               # 我的 register_domain_axis 生效了吗
snap["magnitude_clamped"]  # {触发器名: 被夹取次数}；非空 = 我自报的强度越界了
```

自报强度越界会被**静默**夹到上界（否则返 `5.0` 就能永久霸占类内第一），症状恰好就是"我明明声明齐了、却总是竞争不过别人"。用 `wake_magnitude_from_ratio` 而不是自己拍数字，就不会撞这一格。

### 零注册的另一条路：信号包络

事件式、一次性的信号不必写 contributor 类：

```python
from krow_agent_sdk.metacognition import publish_signal_envelope

publish_signal_envelope("litsci.download_gap", 0.7, kind="pdf_missing", source="litsci")
```

判据很简单：**每拍都要被询问**的聚合型传感器走注册表（本 demo 的 contributor），**发完就走**的突发信号走包络（`report_download_gap()`）。

### 装上即被看见：entry points 自动发现

`register_*` 有个容易漏的前提——得有人 import 你的模块。包装上了不等于被导入了，靠导入顺序碰运气会时灵时不灵，且失败时静默。把注册项写进 entry points，包管理器替你解决：

```toml
[project.entry-points."krow.metacog.contributors"]
litsci_download = "litsci_metacog_demo:DownloadCompletenessContributor"

[project.entry-points."krow.metacog.wake_triggers"]
litsci_zero_download = "litsci_metacog_demo:wake_zero_download_with_hits"
```

两条路径登记同一个 FQCN 时按字面量去重，只跑一遍。

## 执行面：让决策脑替你动手（`litsci_actuation_demo.py`）

观测面到此为止只解决了"看得见"。真正省钱的是下一步：**下不动就别再下了**。

```python
from krow_agent_sdk.actuation import (
    AUTHORITY_PLAN, append_plan_step, make_actuator_action,
    register_reflex_decision, register_step_actuator, saturation_counter,
)

class MetadataFallbackActuator:          # 必须是模块顶层类（按 FQCN re-import）
    MAX_FIRES = 1

    def __init__(self):                   # 每任务一个新实例，计数器不跨任务
        self._fired = 0
        self._last_attempts = -1
        self._counter = saturation_counter(2, label="litsci_download")

    def __call__(self, exe, plan):
        counts = aggregate_counts(exe)                  # 与观测面读同一份计数
        if counts["requested"] <= 0 or counts["downloaded"] > 0:
            return None                                  # 自判适用性 / 还在出货
        if counts["requested"] <= self._last_attempts:
            return None                                  # 没有新尝试 → 不动 ≠ 饱和
        self._last_attempts = counts["requested"]
        if not self._counter.observe_signature(counts["downloaded"]).saturated:
            return None
        step = append_plan_step(exe, plan, tool="litsci_export_metadata",
                                purpose="…不要再重试下载，改导出元数据清单…")
        if step is None:
            return None
        self._fired += 1
        return make_actuator_action(new_step=step, decision="litsci_metadata_fallback")
```

注册**两半都要**，缺一不可：

```python
register_reflex_decision(
    "litsci_metadata_fallback", authority=AUTHORITY_PLAN,
    actuator="litsci_actuation_demo:MetadataFallbackActuator",
    axis="litsci_download_gap",      # 与观测面同一条轴，否则满秩矩阵上是两个格子
    max_fires=1,
)
register_step_actuator("litsci_actuation_demo:MetadataFallbackActuator")
```

只注册执行器：它照常开火，但 `actuations_total` 不计——报表会说"决策脑从没动手"，而基于这种读数最容易做的决定恰恰是**退化功能**（本仓真实事故）。只登记契约：没有执行器认领，满秩矩阵报"声明了没生效"。

**判据三条纪律**（`tests/test_litsci_actuation_demo.py` 逐条守）：

1. **自判适用性**：非本族任务直接闭嘴，不靠注册顺序抢；
2. **饱和签名读产出、且只在有新尝试时观测**——写成"连续 N 拍没变化"会在 agent 读已下到的 PDF 时假开火，把好路子撤掉；
3. **有界**：`MAX_FIRES` 触顶让位 `converge`，别把计划撑爆。

**换框架的首选姿态不是写 python**：如果你只是"A 路子不行换 B 路子"，在 ACT `__act__.yaml` 里声明 `reframe_frameworks` 即可，由内建通用 provider 消费（内建 19 个 ACT 有 15 个是这么覆盖的）。只有饱和判据要读**领域产物**（本 demo 的"下载成功数"就是）时，写执行器才划算。

## 反模式（都有铁证，别踩）

| 反模式 | 症状 | 解 |
|---|---|---|
| **"注册≠激活"半边墙** | 注册了但 `applicable` 恒 False / 类不可 re-import → 加载期被 silent 跳过 | 用**模块顶层**类/函数（本地类、lambda 不行，facade 注册期会 fail-loud）；写 `register→load→applicable` 单测闭环 |
| **无 ground-truth 的 error_vector** | 把 LLM 自评分/启发式估算当"离验收距离" → 停滞判定假阳假阴 | 只有真值背书的分量进 `error_vector`，其余进 `signals` |
| **唤醒风暴** | 同一条件每拍唤醒 → 淹没真信号 | 每形态每任务只唤醒一次；靠 signals 键天然门禁非本域任务 |
| **传感器失活假阳** | `applicable` 恒真却零产出 | 收窄到"探测到活跃领域信号"才 True |
| **自造账本** | 在 executor 上挂新状态 → 与工具 output SSOT 漂移 | 复用工具返回值 / `_step_results`，不新造 |
| **不登记契约就开火** | 动作真生效，报表 `actuations_total` 恒 0 → 复盘结论反向 | `register_reflex_decision` + 动作带 `decision=` |
| **饱和签名读时间不读产出** | agent 干别的正事时假开火，把好路子撤了 | 签名只读本路子的产出，且只在"有新尝试"时观测 |
| **无界执行器** | 每拍注一步 → 计划膨胀、预算烧光 | `MAX_FIRES` / `max_fires`，触顶让位 `converge` |

## 延伸阅读

- 进阶指南「配置决策脑三注册表」（观测面）+「让决策脑替你动手」（执行面）：完整讲 error_vector 设计、L0/L1/L2 权威阶梯、稀疏唤醒纪律、饱和判据。
- API 参考 `metacognition` / `actuation` 小节：公开函数的签名与契约。
