# hitl-assistant — CAD 参数变更助手（Human-in-the-Loop demo）

> 演示 Krow SDK 的 **HITL 挂起/续跑/多模态** 全 API（`krow-agent-sdk >= 0.9.0.5`）。
> 场景原型：用 Krow Agent 驱动工业设计软件（SimLab / CATIA 等）改设计参数——
> 改错的代价极高，Agent 必须会"停下来问工程师"。

## 它演示了什么

| HITL 能力 | 本 demo 对应 | SDK API |
|---|---|---|
| LLM 自主发问 | 用户说"改大一点"→ Agent 停下来问"改到多少？" | `with_hitl(allow_llm_questions=True)` |
| 强制确认门（System 1） | 真正写参数前框架**必停**，不依赖 LLM 自觉 | `with_hitl(confirm_before_tools=["cad_apply_param_change"])` |
| 多模态答复 | 工程师答复可带截图/标注图/规格书 | `agent.resume(token, {"text":..., "images":[...], "files":[...]})` |
| 跨进程续跑 | 挂起后 Ctrl+C 杀进程，重启后凭 token 续跑 | durable checkpoint（SQLite）+ `--resume <token>` |
| 断点管理 | 列出/取消断点 | `agent.list_checkpoints` / `agent.cancel_checkpoint` |

## 快速跑

```bash
pip install -e .
krow-sdk-install --api-key sk-user-xxx     # 装私有 runtime（一次性）
export KROW_API_KEY=sk-user-xxx

# 交互式：指令故意含糊 → agent 会挂起来问你
python main.py "把泵的出口直径改大一点"
```

挂起时终端会显示问题 + `resume_token`，直接打字答复即可；带附件用前缀：

```text
你的答复> 按标注图改到 60mm img:annotated_shot.png
```

### 跨进程续跑（durable checkpoint）

挂起时直接 Ctrl+C 杀掉进程，然后：

```bash
python main.py --resume <resume_token> "改到 60mm，确认执行"
```

### 断点管理

```bash
python main.py --list-checkpoints
python main.py --cancel <resume_token>
```

## 关键设计（对照 `docs/sdk/api-reference.md` §3.5）

1. **确认门是 System 1 闸门**：`cad_apply_param_change` 是高代价副作用工具
   （真实场景 = 改模 + 重新仿真数小时）。哪怕 LLM 忘了请示，框架也会在
   计划步骤调用它之前挂起等 approve——这是"语法交给系统"的 TURBO 哲学落地。
2. **LLM 发问是 System 2 语义判断**：什么时候信息不足、问什么问题，
   由 LLM 决定（`request_human_input` 工具）；ACT 扩展指南里立了
   "禁止瞎猜数值"的纪律。
3. **答复多模态双通道**：图片既作为视觉输入直接给 LLM，又注册文件缓存
   供后续步骤的工具引用（真实 id/路径，防 LLM 臆造缓存 ID）。

## 测试

```bash
pip install -e ".[test]"
pytest tests/ -v        # smoke：无需 runtime / API key
```

真实 LLM 端到端验收（J1-J4 journey）在主仓 `tests/sdk/test_hitl_journey_real_llm.py`。
