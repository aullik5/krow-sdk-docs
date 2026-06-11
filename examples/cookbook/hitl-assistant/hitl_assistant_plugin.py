"""HITL-assistant cookbook plugin SSOT.

场景（来自工业设计软件集成方的真实需求）：用 Krow Agent 驱动 CAD /
仿真软件（SimLab / CATIA 等）做设计参数变更。**参数改错的代价极高**
（重新仿真数小时起步），所以 Agent 必须：

1. 信息不足时**停下来问工程师**（`request_human_input`，LLM 自主发问）；
2. 真正写参数之前**必须经人确认**（`confirm_before_tools` 强制确认门，
   System 1 必停，不依赖 LLM 自觉）；
3. 工程师答复可以带**截图 / 标注图 / 规格书**（多模态 resume）；
4. 进程重启后凭 `resume_token` **断点续跑**（durable checkpoint）。

本 cookbook 教学点 = SDK 的 HITL 全 API：
``with_hitl`` / ``result.suspended`` / ``agent.resume`` /
``agent.list_checkpoints`` / ``agent.cancel_checkpoint``。

2 类 plugin 实现：
- HitlAssistantToolPlugin: 2 个 System 1 工具
  - cad_read_design_params：读设计参数 JSON（deterministic）
  - cad_apply_param_change：写参数变更（**高代价副作用 → 配合强制确认门**）
- HitlAssistantACTPlugin: 自定义 "hitl_assistant" ACT

设计原则（与 advanced-development-guide.md / AGENTS.md §0.2 对齐）：
- TURBO 边界：工具是 System 1（不调 LLM；deterministic；unit-test 100% 覆盖）
- 错误信息：黄金模板（原因 + 位置 + 修法）
- 强制确认门是 **System 1 闸门**：哪怕 LLM 忘了问，框架也会在
  ``cad_apply_param_change`` 执行前必停（详 api-reference §3.5）
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 真实业务里这里是 SimLab / CATIA 的 COM / gRPC 接口；
# cookbook 用 JSON 文件模拟"设计软件当前参数表"。


def _normalize_path(p: str | Path) -> Path:
    if isinstance(p, str):
        p = Path(p)
    return p.expanduser().resolve()


def _golden_error(
    msg: str, *, where: str, fixes: Iterable[str],
) -> dict[str, Any]:
    parts = [f"❌ {msg}", f"   位置：{where}", "   修法："]
    for i, fix in enumerate(fixes, 1):
        parts.append(f"     {i}. {fix}")
    return {"ok": False, "error": "\n".join(parts)}


def read_design_params(params_file: str | Path) -> dict[str, Any]:
    """读设计参数表 JSON（System 1 deterministic，模拟查询 CAD 软件状态）。

    Returns:
        dict 含 ok / summary / params（{name: {value, unit, description}}）
    """
    p = _normalize_path(params_file)
    if not p.exists():
        return _golden_error(
            f"参数表不存在：{p}",
            where=f"params_file={params_file}",
            fixes=[
                "检查路径拼写（绝对路径更稳）",
                "确认 sample_data/design_params.json 是否在",
            ],
        )
    try:
        # utf-8-sig: 容忍 Windows 工具链写出的 BOM（输入鲁棒）
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as e:
        return _golden_error(
            f"参数表解析失败：{e}",
            where=f"params_file={p}",
            fixes=["确认是合法 JSON", "确认文件未被设计软件锁定"],
        )
    params = data.get("params") or {}
    return {
        "ok": True,
        "summary": (
            f"读到 {len(params)} 个设计参数："
            + "、".join(list(params)[:6])
            + ("..." if len(params) > 6 else "")
        ),
        "params_file": str(p),
        "model_name": data.get("model_name", ""),
        "params": params,
    }


def apply_param_change(
    params_file: str | Path,
    param_name: str,
    new_value: float | int | str,
    reason: str = "",
) -> dict[str, Any]:
    """对设计参数表应用一次变更（**高代价副作用工具**）。

    真实业务里这一步会驱动 CAD 软件改模型 + 触发重新仿真（数小时），
    所以 demo 在 main.py 用 ``confirm_before_tools=["cad_apply_param_change"]``
    强制确认门拦住它——**框架在执行前必停**，工程师 approve 后才真改。

    变更历史追加到 JSON 的 ``change_log``（审计可追溯）。
    """
    p = _normalize_path(params_file)
    if not p.exists():
        return _golden_error(
            f"参数表不存在：{p}",
            where=f"params_file={params_file}",
            fixes=["先调 cad_read_design_params 验证路径"],
        )
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as e:
        return _golden_error(
            f"参数表解析失败：{e}",
            where=f"params_file={p}",
            fixes=["确认是合法 JSON"],
        )

    params = data.get("params") or {}
    name = str(param_name or "").strip()
    if name not in params:
        return _golden_error(
            f"参数 {name!r} 不存在",
            where=f"apply_param_change(param_name={param_name!r})",
            fixes=[
                "先调 cad_read_design_params 看可用参数名",
                f"现有参数：{', '.join(list(params)[:8])}",
            ],
        )

    old_value = params[name].get("value")
    params[name]["value"] = new_value
    data.setdefault("change_log", []).append({
        "param": name,
        "old_value": old_value,
        "new_value": new_value,
        "reason": str(reason or "")[:300],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    try:
        p.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    except OSError as e:
        return _golden_error(
            f"写参数表失败：{e}",
            where=f"params_file={p}",
            fixes=["检查写权限 / 磁盘空间", "确认文件未被设计软件锁定"],
        )

    return {
        "ok": True,
        "summary": (
            f"参数已变更：{name} = {old_value} → {new_value}"
            f"（unit={params[name].get('unit', '?')}；已记 change_log）"
        ),
        "param": name,
        "old_value": old_value,
        "new_value": new_value,
        "params_file": str(p),
    }


# ============================================================
# ToolPlugin / ACTPlugin
# ============================================================


class HitlAssistantToolPlugin:
    """实现 ``krow_agent_sdk.protocols.ToolPlugin`` Protocol。"""

    plugin_id = "hitl_assistant.tools"

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "cad_read_design_params",
                "description": (
                    "读设计参数表 JSON（模拟查询 CAD/仿真软件当前参数）。"
                    "改参数之前必须先读，确认参数名与当前值。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "params_file": {
                            "type": "string",
                            "description": "参数表 JSON 路径（绝对或相对）",
                        },
                    },
                    "required": ["params_file"],
                },
                "handler": read_design_params,
            },
            {
                "name": "cad_apply_param_change",
                "description": (
                    "对设计参数表应用一次变更（高代价副作用：真实场景会触发"
                    "CAD 改模 + 重新仿真）。变更自动记 change_log。"
                    "注意：本工具通常被强制确认门（confirm_before_tools）守护，"
                    "执行前框架会暂停等工程师 approve。"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "params_file": {"type": "string"},
                        "param_name": {
                            "type": "string",
                            "description": "要改的参数名（必须先 read 确认存在）",
                        },
                        "new_value": {
                            "description": "新值（数值或字符串）",
                        },
                        "reason": {
                            "type": "string",
                            "description": "变更原因（进 change_log 审计）",
                        },
                    },
                    "required": ["params_file", "param_name", "new_value"],
                },
                "handler": apply_param_change,
            },
        ]


class HitlAssistantACTPlugin:
    """实现 ``krow_agent_sdk.protocols.ACTPlugin`` Protocol。"""

    plugin_id = "hitl_assistant.act"
    act_name = "hitl_assistant"

    def get_act_root(self) -> Path:
        return Path(__file__).parent / "act_assets" / "hitl_assistant"

    def get_act_file_path(self) -> Path:
        return self.get_act_root() / "ext_hitl_assistant.md"

    def get_tool_names(self) -> list[str]:
        return [
            "cad_read_design_params",
            "cad_apply_param_change",
        ]


__all__ = [
    "read_design_params",
    "apply_param_change",
    "HitlAssistantToolPlugin",
    "HitlAssistantACTPlugin",
]
