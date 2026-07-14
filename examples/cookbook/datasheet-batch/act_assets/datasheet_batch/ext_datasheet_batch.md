# Datasheet 批量并发解析（Datasheet Batch）· ACT 扩展指令

> 场景：批量解析元器件 datasheet PDF（电阻/电容/芯片建库）。**并行吞吐 + per-item
> 正确性**同时成立：每份结果确定性归属其型号（A 引脚绝不串到 B），单份失败被单独
> 记账、不拖垮整批，「N 中完成 M / 失败 K」对收尾可判定。

## 核心原则（铁律）

1. **批量首选并发工具**：一批多份 datasheet **必须**用 `datasheet_batch_parse` 一次并发
   解析，**禁止**逐份串行调 `datasheet_parse_one`（那会退回串行、失去吞吐与统一记账）。
2. **per-item 身份确定性**（N2）：每份的 `model`（型号）是确定性身份，结果据此归属。
   传入 `items=[{model, path}]` 时务必让 model 唯一且准确——解析结果的字段绝不靠你
   在一次输出里"记住谁是谁"，而由编排器按 model 绑定。
3. **失败隔离 + 覆盖可判定**（N3/N4）：单份失败/降级由编排器单独记账，其余照常完成。
   读 `datasheet_batch_parse` 返回的 `completed/failed/degraded/coverage`——覆盖率过低或
   全失败会被 `DatasheetBatchCoverageGate` 拦住 conclude，须先修复失败份或显式说明。
4. **大批量续跑**（N5）：若返回 `should_continue=true`（`remaining>0`），说明本批只处理了
   一部分（受 batch_size / 软预算限），**用相同 items 再调一次** `datasheet_batch_parse`
   续跑下一批（账本自动跳过已处理份，幂等）。直到 `remaining=0`。
5. **分工（TURBO）**：并发编排 / 身份归属 / 覆盖记账 = 工具（System 1）；如何组织清单、
   如何判定覆盖率是否达标、失败份如何处置 = 你（LLM）决策。

## 标准工作流

1. **组织清单**：清单通常**已在任务输入里以 JSON manifest 直接给出**（形如
   `[{"model","path"}]`）——**直接使用它**，不要去文件系统 `search_files` / `list_dir`
   找 datasheet（样例已随任务下发，搜索只会白跑）。仅当任务未给清单、只给目录时，
   才需列目录组织清单。
2. **并发解析（第一步动作）**：拿到清单**立即**调
   `datasheet_batch_parse(items=[...], project_root=<项目根>, max_workers=8)`
   → 拿 `completed/failed/degraded/coverage/remaining/should_continue/results`。
   路径用任务给的原样（通常是项目内相对路径，如 `upload/xxx.txt`）。
3. **续跑（如需）**：`should_continue=true` → 用相同 items 再调 `datasheet_batch_parse`，
   直到 `remaining=0`。
4. **判定 + 处置**：覆盖率达标（gate ALLOW）→ 进入收尾；否则看 `results[].error`
   定位失败份，修复或说明。
5. **落盘**：用 `smart_file_write` 写 `datasheet_batch_report.md`（覆盖汇总 + per-item 表）
   + `datasheet_results.json`（结构化 results 留档）。

## 反模式（会被 gate 拦 / 判低效）

- ❌ 逐份串行调 `datasheet_parse_one`（失去并发吞吐 + 统一记账）
- ❌ 忽略 `should_continue=true` 不续跑（大批量漏处理）
- ❌ 全失败 / 覆盖率过低却报成功 conclude（DatasheetBatchCoverageGate BLOCK）
- ❌ 靠"自己记住"把字段归属到型号（应信编排器按 model 的确定性绑定）
