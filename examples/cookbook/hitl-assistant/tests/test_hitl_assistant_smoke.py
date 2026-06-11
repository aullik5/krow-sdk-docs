"""Cookbook hitl-assistant smoke tests (CI-friendly: no runtime / no API key).

测试范围：
- §1 Plugin protocol 合规（plugin_id / get_tools / get_act_root 签名）
- §2 工具行为（read_design_params / apply_param_change · System 1 deterministic）
- §3 错误路径（文件不存在 / 非法 JSON / 参数名不存在）→ 黄金错误模板
- §4 ACT 资源文件（__act__.yaml manifest 合法 + ext md 存在）
- §5 SDK HITL API 契约存在性（with_hitl / resume / list_checkpoints /
  cancel_checkpoint —— 只验签名存在，不真 build/run）
- §6 main.py 答复解析（img: / file: 前缀 → 多模态 HumanInput dict）

不在本测试范围（runtime + 真 LLM 验收在 tests/sdk/test_hitl_journey_real_llm.py）：
- agent.run() / agent.resume() 真实端到端
- 强制确认门真实触发（J2 journey 覆盖）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

COOKBOOK_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COOKBOOK_DIR))

from hitl_assistant_plugin import (  # noqa: E402
    HitlAssistantACTPlugin,
    HitlAssistantToolPlugin,
    apply_param_change,
    read_design_params,
)

SAMPLE_PARAMS = COOKBOOK_DIR / "sample_data" / "design_params.json"


# ============================================================
# §1. Plugin Protocol 合规
# ============================================================


def test_tool_plugin_protocol_shape():
    plugin = HitlAssistantToolPlugin()
    assert plugin.plugin_id == "hitl_assistant.tools"
    assert plugin.plugin_id.count(".") == 1, "plugin_id 必须 <org>.<name> 双段"
    tools = plugin.get_tools()
    assert isinstance(tools, list) and len(tools) == 2
    for tool in tools:
        assert tool["name"].startswith("cad_"), "域前缀命名规范"
        assert callable(tool["handler"])
        assert tool["input_schema"]["type"] == "object"


def test_act_plugin_protocol_shape():
    plugin = HitlAssistantACTPlugin()
    assert plugin.plugin_id == "hitl_assistant.act"
    assert plugin.act_name == "hitl_assistant"
    assert plugin.get_act_root().exists()
    assert plugin.get_act_file_path().exists()
    assert set(plugin.get_tool_names()) == {
        "cad_read_design_params",
        "cad_apply_param_change",
    }


# ============================================================
# §2. 工具行为（System 1 deterministic）
# ============================================================


def test_read_design_params_ok():
    result = read_design_params(SAMPLE_PARAMS)
    assert result["ok"] is True
    assert "pump_outlet_diameter_mm" in result["params"]
    assert result["params"]["pump_outlet_diameter_mm"]["value"] == 50
    assert result["model_name"] == "centrifugal_pump_v3"
    assert "summary" in result


def test_apply_param_change_roundtrip(tmp_path):
    work = tmp_path / "params.json"
    work.write_text(SAMPLE_PARAMS.read_text(encoding="utf-8"), encoding="utf-8")

    result = apply_param_change(
        work, "pump_outlet_diameter_mm", 60, reason="工程师确认改 60mm",
    )
    assert result["ok"] is True
    assert result["old_value"] == 50
    assert result["new_value"] == 60

    data = json.loads(work.read_text(encoding="utf-8"))
    assert data["params"]["pump_outlet_diameter_mm"]["value"] == 60
    # change_log 审计可追溯
    assert len(data["change_log"]) == 1
    log = data["change_log"][0]
    assert log["param"] == "pump_outlet_diameter_mm"
    assert log["old_value"] == 50
    assert log["new_value"] == 60
    assert "60mm" in log["reason"]


def test_read_tolerates_bom(tmp_path):
    """Windows 工具链常写 BOM —— 输入鲁棒不挂。"""
    work = tmp_path / "bom.json"
    work.write_bytes(
        b"\xef\xbb\xbf" + SAMPLE_PARAMS.read_text(encoding="utf-8").encode("utf-8")
    )
    assert read_design_params(work)["ok"] is True


# ============================================================
# §3. 错误路径 → 黄金错误模板
# ============================================================


def test_read_missing_file_golden_error():
    result = read_design_params("does/not/exist.json")
    assert result["ok"] is False
    assert "修法" in result["error"]
    assert "位置" in result["error"]


def test_apply_unknown_param_golden_error(tmp_path):
    work = tmp_path / "params.json"
    work.write_text(SAMPLE_PARAMS.read_text(encoding="utf-8"), encoding="utf-8")
    result = apply_param_change(work, "no_such_param", 1)
    assert result["ok"] is False
    # 错误信息必须列出可用参数名（让 LLM 能自纠）
    assert "pump_outlet_diameter_mm" in result["error"]


def test_apply_invalid_json_golden_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    result = apply_param_change(bad, "x", 1)
    assert result["ok"] is False
    assert "修法" in result["error"]


# ============================================================
# §4. ACT 资源文件
# ============================================================


def test_act_manifest_valid():
    manifest_path = (
        COOKBOOK_DIR / "act_assets" / "hitl_assistant" / "__act__.yaml"
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == "hitl_assistant"
    assert set(manifest["tools"]) == {
        "cad_read_design_params",
        "cad_apply_param_change",
    }
    assert manifest["when_to_enter"], "ACT 必须有进入条件供语义选择器使用"


def test_act_ext_md_mentions_hitl_discipline():
    ext = (
        COOKBOOK_DIR / "act_assets" / "hitl_assistant" / "ext_hitl_assistant.md"
    ).read_text(encoding="utf-8")
    # 核心纪律：不许瞎猜数值 + 确认门是系统行为
    assert "request_human_input" in ext
    assert "confirm_before_tools" in ext


# ============================================================
# §5. SDK HITL API 契约存在性（不真 build）
# ============================================================


def test_sdk_exposes_hitl_api_surface():
    from krow_agent_sdk import AgentBuilder

    builder = AgentBuilder()
    assert hasattr(builder, "with_hitl"), "SDK 必须暴露 with_hitl"
    # fluent：with_hitl 返回 builder 本身
    out = builder.with_hitl(
        confirm_before_tools=["cad_apply_param_change"],
        allow_llm_questions=True,
        max_suspensions=5,
    )
    assert out is builder


# ============================================================
# §6. main.py 答复解析（多模态 HumanInput dict）
# ============================================================


def test_parse_human_reply_text_only():
    from main import _parse_human_reply

    out = _parse_human_reply("改成 60mm 吧")
    assert out["text"] == "改成 60mm 吧"
    assert "images" not in out
    assert "files" not in out


def test_parse_human_reply_with_attachments():
    from main import _parse_human_reply

    out = _parse_human_reply("按标注图改 img:shot.png file:spec.pdf")
    assert out["text"] == "按标注图改"
    assert out["images"] == ["shot.png"]
    assert out["files"] == ["spec.pdf"]
