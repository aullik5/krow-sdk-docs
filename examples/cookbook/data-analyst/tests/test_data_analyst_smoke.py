"""Cookbook data-analyst (v2 auditor scope) smoke tests (CI-friendly: no runtime / no API key needed).

测试范围（v2 升级版）：
- §1 Plugin protocol 合规（实例化 + plugin_id / get_tools 等签名）
- §2 ToolPlugin 注册的 6 个工具行为
  - read_csv / compute_stats / detect_anomalies / compute_correlation /
    pick_palette / write_report
- §3 错误路径（不存在的 CSV / 编码错 / 写入失败）— 黄金错误模板覆盖
- §4 ACT 资源文件存在性 + frontmatter 合法 + 引用了 word_smart_export 内置工具
- §5 pick_palette 查表配色（System 1 deterministic）
- §6 错误降级演示（encoding fallback）
- §7 v2 新增：detect_anomalies / compute_correlation 工具
- §8 v2 新增：GatePlugin × 2（PIIDetectorGate / OutputPathGate）
- §9 v2 新增：HintPlugin（DataInsightHintPlugin）
- §10 v2 新增：AuditEventListener

不在本测试范围（留给后续 LLM replay PR）：
- agent.run() 真实端到端（需要 runtime + KROW_API_KEY）
- LLM ACT 选中行为
- word_smart_export 真实 PDF 渲染（属于 Krow 主应用 unit test 范围）
"""
from __future__ import annotations

import json
from pathlib import Path

from data_analyst_plugin import (
    AuditEventListener,
    DataAnalystACTPlugin,
    DataAnalystProgressListener,
    DataAnalystToolPlugin,
    DataInsightHintPlugin,
    OutputPathGate,
    PIIDetectorGate,
    _scan_pii_columns,
    compute_correlation,
    compute_stats,
    detect_anomalies,
    pick_palette,
    read_csv,
    write_report,
)

COOKBOOK_DIR = Path(__file__).resolve().parent.parent
SAMPLE_CSV = COOKBOOK_DIR / "sample_data" / "titanic.csv"


# ============================================================
# §1. Plugin Protocol 合规
# ============================================================


def test_tool_plugin_protocol_shape():
    plugin = DataAnalystToolPlugin()
    assert plugin.plugin_id == "data_analyst.tools"
    assert plugin.plugin_id.count(".") == 1, "plugin_id 必须 <org>.<name> 双段"
    tools = plugin.get_tools()
    assert isinstance(tools, list) and len(tools) == 6, (
        f"v2 升级版应注册 6 个工具，实际 {len(tools)}（read_csv / compute_stats / "
        "detect_anomalies / compute_correlation / pick_palette / write_report）— "
        "PDF 输出复用 Krow 内置 word_smart_export"
    )
    for spec in tools:
        assert {"name", "description", "input_schema", "handler"}.issubset(spec.keys())
        assert spec["name"].startswith("data_analyst_"), (
            "工具命名必须含 plugin_name 段前缀（advanced-development-guide §3.2）"
        )
        assert callable(spec["handler"])


def test_act_plugin_protocol_shape():
    plugin = DataAnalystACTPlugin()
    assert plugin.plugin_id == "data_analyst.act"
    assert plugin.act_name == "data_analyst"
    assert plugin.get_act_root().exists(), "ACT root 目录必须存在"
    assert plugin.get_act_file_path().exists(), "ACT extended.md 必须存在"
    tool_names = plugin.get_tool_names()
    assert tool_names == [
        "data_analyst_read_csv",
        "data_analyst_compute_stats",
        "data_analyst_detect_anomalies",
        "data_analyst_compute_correlation",
        "data_analyst_pick_palette",
        "data_analyst_write_report",
    ]


def test_event_listener_protocol_shape():
    listener = DataAnalystProgressListener(verbose=False)
    assert listener.plugin_id == "data_analyst.progress_listener"
    subs = listener.get_subscriptions()
    assert isinstance(subs, list) and len(subs) >= 1
    for sub in subs:
        assert "topic" in sub and "handler" in sub
        assert callable(sub["handler"])
    topics = {s["topic"] for s in subs}
    assert topics & {"agent.task_complete", "agent.task_failed", "agent.task_cancelled"}


# ============================================================
# §2. 工具行为（happy path）
# ============================================================


def test_read_csv_happy_path():
    result = read_csv(SAMPLE_CSV)
    assert result["ok"] is True
    assert result["row_count"] == 20
    assert "PassengerId" in result["columns"]
    assert "Sex" in result["columns"]
    assert len(result["preview_rows"]) <= 10


def test_compute_stats_happy_path():
    result = compute_stats(SAMPLE_CSV)
    assert result["ok"] is True
    assert result["row_count"] == 20
    assert "Age" in result["numeric_stats"]
    age_stats = result["numeric_stats"]["Age"]
    assert age_stats["count"] >= 15
    assert age_stats["min"] >= 0 and age_stats["max"] <= 100
    assert age_stats["missing_count"] >= 1
    assert "Sex" in result["categorical_stats"]
    sex_stats = result["categorical_stats"]["Sex"]
    assert sex_stats["unique_count"] == 2
    assert "male" in sex_stats["top5"]


def test_write_report_happy_path(tmp_path):
    out = tmp_path / "report.md"
    result = write_report(out, title="Test Report", content="第 1 段。\n\n第 2 段。")
    assert result["ok"] is True
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert body.startswith("# Test Report\n\n")
    assert "第 1 段" in body and "第 2 段" in body


# ============================================================
# §3. 错误路径 — 黄金模板覆盖
# ============================================================


def test_read_csv_missing_file():
    result = read_csv("/nonexistent/path/foo.csv")
    assert result["ok"] is False
    assert "❌" in result["error"]
    assert "位置：" in result["error"]
    assert "修法：" in result["error"]


def test_compute_stats_missing_file():
    result = compute_stats("/nonexistent/path/bar.csv")
    assert result["ok"] is False
    assert "❌" in result["error"]
    assert "修法：" in result["error"]


def test_write_report_invalid_dir(tmp_path):
    bad_path = tmp_path / "exists_as_file"
    bad_path.write_text("blocker")
    target = bad_path / "subdir" / "report.md"
    result = write_report(target, title="x", content="y")
    assert result["ok"] is False
    assert "❌" in result["error"]


def test_read_csv_str_path_normalization():
    result_str = read_csv(str(SAMPLE_CSV))
    result_path = read_csv(SAMPLE_CSV)
    assert result_str["ok"] and result_path["ok"]
    assert result_str["row_count"] == result_path["row_count"]


def test_read_csv_encoding_case_normalization():
    result_lower = read_csv(SAMPLE_CSV, encoding="utf-8")
    result_upper = read_csv(SAMPLE_CSV, encoding="UTF-8")
    result_spaced = read_csv(SAMPLE_CSV, encoding="  utf-8  ")
    assert result_lower["ok"] and result_upper["ok"] and result_spaced["ok"]


# ============================================================
# §4. ACT 资源文件 frontmatter 合法
# ============================================================


def test_act_extended_md_has_yaml_frontmatter():
    plugin = DataAnalystACTPlugin()
    body = plugin.get_act_file_path().read_text(encoding="utf-8")
    assert body.startswith("---\n"), "extended.md 必须以 YAML frontmatter 起头"
    end_marker = body.find("\n---\n", 4)
    assert end_marker > 0, "frontmatter 必须有结束标记 ---"
    fm = body[4:end_marker]
    for required_key in ("name:", "display_name:", "description:", "tools:"):
        assert required_key in fm, f"frontmatter 必须含 {required_key}"
    # v2 升级版必须含 6 个 cookbook 工具 + 1 个 Krow 内置工具（PDF 输出复用）
    for tool_name in (
        "data_analyst_read_csv",
        "data_analyst_compute_stats",
        "data_analyst_detect_anomalies",
        "data_analyst_compute_correlation",
        "data_analyst_pick_palette",
        "data_analyst_write_report",
        "word_smart_export",
    ):
        assert tool_name in fm, f"frontmatter tools 列表必须含 {tool_name}"


def test_act_extended_md_teaches_ssot_reuse():
    plugin = DataAnalystACTPlugin()
    body = plugin.get_act_file_path().read_text(encoding="utf-8")
    assert "word_smart_export" in body
    assert "SSOT" in body
    assert "render_pdf" not in body or "不要" in body


def test_act_extended_md_teaches_v2_advanced_features():
    """v2 ACT 必须教用户 GatePlugin / HintPlugin / BudgetSpec 的真实业务价值."""
    plugin = DataAnalystACTPlugin()
    body = plugin.get_act_file_path().read_text(encoding="utf-8")
    for keyword in (
        "GatePlugin", "PIIDetectorGate", "OutputPathGate",
        "HintPlugin", "BudgetSpec", "AuditEventListener",
        "异常检测", "相关性",
    ):
        assert keyword in body, f"v2 ACT extended.md 必须教 {keyword}"


# ============================================================
# §5. pick_palette 工具（System 1 deterministic 查表）
# ============================================================


def test_pick_palette_categorical_default():
    result = pick_palette()
    assert result["ok"] is True
    assert result["palette_kind"] == "categorical"
    assert result["n"] == 10
    assert len(result["colors"]) == 10
    assert all(c.startswith("#") and len(c) == 7 for c in result["colors"])


def test_pick_palette_sequential_truncates():
    result = pick_palette(palette_kind="sequential", n=5)
    assert result["ok"] is True
    assert len(result["colors"]) == 5
    assert result["palette_kind"] == "sequential"


def test_pick_palette_categorical_cycles():
    result = pick_palette(palette_kind="categorical", n=15)
    assert result["ok"] is True
    assert len(result["colors"]) == 15
    assert result["colors"][10] == result["colors"][0]


def test_pick_palette_unknown_kind_returns_golden_error():
    result = pick_palette(palette_kind="rainbow")
    assert result["ok"] is False
    assert "❌" in result["error"]
    assert "categorical" in result["error"]
    assert "sequential" in result["error"]
    assert "diverging" in result["error"]


def test_pick_palette_invalid_n_returns_golden_error():
    result = pick_palette(palette_kind="categorical", n=0)
    assert result["ok"] is False
    assert "❌" in result["error"]


def test_pick_palette_case_insensitive():
    r1 = pick_palette(palette_kind="CATEGORICAL")
    r2 = pick_palette(palette_kind="  categorical  ")
    assert r1["ok"] and r2["ok"]
    assert r1["colors"] == r2["colors"]


# ============================================================
# §6. 错误降级：encoding fallback
# ============================================================


def test_read_csv_encoding_fallback_gbk(tmp_path):
    csv = tmp_path / "gbk_data.csv"
    csv.write_bytes("name,age\n张三,30\n李四,25\n".encode("gbk"))

    result = read_csv(csv, encoding="utf-8")
    assert result["ok"] is True
    assert result["encoding_fallback_triggered"] is True
    assert result["encoding_used"] == "gbk"
    assert "encoding 降级" in result["summary"]
    assert result["row_count"] == 2


def test_read_csv_encoding_no_fallback_when_utf8_works():
    result = read_csv(SAMPLE_CSV, encoding="utf-8")
    assert result["ok"] is True
    assert result["encoding_fallback_triggered"] is False
    assert result["encoding_used"] == "utf-8"


# ============================================================
# §7. v2 新增：detect_anomalies / compute_correlation
# ============================================================


def _make_anomaly_csv(tmp_path: Path) -> Path:
    """造一个含明显 outlier 的 CSV."""
    csv = tmp_path / "anomaly_data.csv"
    rows = ["x,y,z"] + [f"{i},{i*2},{i*0.5}" for i in range(1, 21)]
    rows.append("9999,9999,9999")  # outlier
    rows.append("-9999,-9999,-9999")  # outlier
    csv.write_text("\n".join(rows), encoding="utf-8")
    return csv


def test_detect_anomalies_iqr_finds_outliers(tmp_path):
    csv = _make_anomaly_csv(tmp_path)
    result = detect_anomalies(csv, method="iqr")
    assert result["ok"] is True
    assert result["method"] == "iqr"
    assert result["total_rows"] == 22
    assert result["anomaly_count"] >= 2  # 至少 2 个 outlier
    assert result["anomaly_rate"] > 0
    assert isinstance(result["anomaly_indices"], list)


def test_detect_anomalies_zscore(tmp_path):
    csv = _make_anomaly_csv(tmp_path)
    result = detect_anomalies(csv, method="zscore")
    assert result["ok"] is True
    assert result["method"] == "zscore"
    assert result["anomaly_count"] >= 1


def test_detect_anomalies_invalid_method(tmp_path):
    csv = _make_anomaly_csv(tmp_path)
    result = detect_anomalies(csv, method="auto")
    assert result["ok"] is False
    assert "❌" in result["error"]
    assert "iqr" in result["error"] and "zscore" in result["error"]


def test_detect_anomalies_invalid_contamination(tmp_path):
    csv = _make_anomaly_csv(tmp_path)
    result = detect_anomalies(csv, method="iqr", contamination=2.5)
    assert result["ok"] is False
    assert "contamination" in result["error"]


def test_detect_anomalies_no_numeric_cols(tmp_path):
    csv = tmp_path / "all_strings.csv"
    csv.write_text("a,b\nfoo,bar\nbaz,qux\n", encoding="utf-8")
    result = detect_anomalies(csv, method="iqr")
    assert result["ok"] is False
    assert "无数值列" in result["error"]


def test_compute_correlation_pearson(tmp_path):
    csv = tmp_path / "corr_data.csv"
    rows = ["a,b,c"] + [f"{i},{i*2},{i + 100}" for i in range(1, 51)]
    csv.write_text("\n".join(rows), encoding="utf-8")
    result = compute_correlation(csv, method="pearson", top_n=3)
    assert result["ok"] is True
    assert result["method"] == "pearson"
    assert result["n_columns"] == 3
    assert "matrix" in result and "top_pairs" in result
    assert len(result["top_pairs"]) == 3
    # a 和 b 应强相关（b = a*2）
    top_ab = next((p for p in result["top_pairs"]
                   if {p["col_a"], p["col_b"]} == {"a", "b"}), None)
    assert top_ab is not None
    assert abs(top_ab["r"] - 1.0) < 0.001  # 完美线性


def test_compute_correlation_spearman(tmp_path):
    csv = tmp_path / "corr_spear.csv"
    rows = ["a,b"] + [f"{i},{i**2}" for i in range(1, 21)]
    csv.write_text("\n".join(rows), encoding="utf-8")
    result = compute_correlation(csv, method="spearman", top_n=1)
    assert result["ok"] is True
    # spearman 对单调非线性应给 r=1.0
    assert abs(result["top_pairs"][0]["r"] - 1.0) < 0.001


def test_compute_correlation_too_few_cols(tmp_path):
    csv = tmp_path / "single_num.csv"
    csv.write_text("a,b\n1,foo\n2,bar\n", encoding="utf-8")
    result = compute_correlation(csv, method="pearson")
    assert result["ok"] is False
    assert "至少需 2 个数值列" in result["error"]


def test_compute_correlation_invalid_method(tmp_path):
    csv = tmp_path / "trivial.csv"
    csv.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    result = compute_correlation(csv, method="kendall")
    assert result["ok"] is False
    assert "pearson" in result["error"] and "spearman" in result["error"]


# ============================================================
# §8. v2 新增：GatePlugin × 2
# ============================================================


def test_pii_keyword_scan_helper():
    """PII column 检测 helper 是否能命中典型字段名."""
    assert _scan_pii_columns(["phone", "name"]) == ["phone"]
    assert _scan_pii_columns(["手机号", "性别"]) == ["手机号"]
    assert _scan_pii_columns(["id_card", "age"]) == ["id_card"]
    assert _scan_pii_columns(["email", "mobile"]) == ["email", "mobile"]
    assert _scan_pii_columns(["x", "y", "z"]) == []
    assert _scan_pii_columns([]) == []


def test_pii_detector_gate_protocol_shape():
    gate_plugin = PIIDetectorGate()
    assert gate_plugin.plugin_id == "data_analyst.pii_gate"
    assert gate_plugin.phase == "macro"
    gate = gate_plugin.get_gate()
    assert hasattr(gate, "name") and hasattr(gate, "priority")
    assert hasattr(gate, "evaluate") and callable(gate.evaluate)


def test_pii_detector_gate_blocks_when_pii_present():
    gate_plugin = PIIDetectorGate()
    gate = gate_plugin.get_gate()
    context = {
        "recent_tool_results": [
            {
                "tool_name": "data_analyst_read_csv",
                "result": {"columns": ["name", "phone", "score"]},
            }
        ]
    }
    decision = gate.evaluate(parsed={}, context=context)
    assert decision.is_blocking()
    assert "PII" in decision.reason or "敏感字段" in decision.reason
    assert "phone" in decision.reason


def test_pii_detector_gate_defers_when_no_pii():
    gate_plugin = PIIDetectorGate()
    gate = gate_plugin.get_gate()
    context = {
        "recent_tool_results": [
            {
                "tool_name": "data_analyst_read_csv",
                "result": {"columns": ["age", "score", "category"]},
            }
        ]
    }
    decision = gate.evaluate(parsed={}, context=context)
    assert not decision.is_blocking()


def test_pii_detector_gate_allows_when_explicit_flag():
    gate_plugin = PIIDetectorGate(allow_pii=True)
    gate = gate_plugin.get_gate()
    context = {
        "recent_tool_results": [
            {
                "tool_name": "data_analyst_read_csv",
                "result": {"columns": ["phone", "id_card"]},
            }
        ]
    }
    decision = gate.evaluate(parsed={}, context=context)
    assert decision.is_allowing()


def test_output_path_gate_protocol_shape(tmp_path):
    gate_plugin = OutputPathGate(project_root=tmp_path)
    assert gate_plugin.plugin_id == "data_analyst.path_gate"
    assert gate_plugin.phase == "macro"
    gate = gate_plugin.get_gate()
    assert hasattr(gate, "evaluate")


def test_output_path_gate_blocks_traversal(tmp_path):
    gate_plugin = OutputPathGate(project_root=tmp_path)
    gate = gate_plugin.get_gate()
    context = {
        "recent_tool_results": [
            {
                "tool_name": "data_analyst_write_report",
                "args": {"output_path": "/tmp/foo/report.md"},
            }
        ]
    }
    decision = gate.evaluate(parsed={}, context=context)
    assert decision.is_blocking()
    assert "project_root" in decision.reason


def test_output_path_gate_defers_when_in_root(tmp_path):
    gate_plugin = OutputPathGate(project_root=tmp_path)
    gate = gate_plugin.get_gate()
    in_root = tmp_path / "out" / "report.md"
    context = {
        "recent_tool_results": [
            {
                "tool_name": "data_analyst_write_report",
                "args": {"output_path": str(in_root)},
            }
        ]
    }
    decision = gate.evaluate(parsed={}, context=context)
    assert not decision.is_blocking()


# ============================================================
# §9. v2 新增：HintPlugin
# ============================================================


def test_hint_plugin_protocol_shape():
    hint = DataInsightHintPlugin()
    assert hint.plugin_id == "data_analyst.insight_hint"
    assert "data_analyst" in hint.applicable_acts


def test_hint_for_returns_none_when_no_csv_yet():
    hint = DataInsightHintPlugin()
    result = hint.hint_for(context={"recent_tool_results": []})
    assert result is None


def test_hint_for_detects_time_column():
    hint = DataInsightHintPlugin()
    context = {
        "recent_tool_results": [
            {
                "tool_name": "data_analyst_read_csv",
                "result": {
                    "columns": ["date", "amount"],
                    "dtypes": {"date": "object", "amount": "float64"},
                    "row_count": 100,
                    "preview_rows": [
                        {"date": "2024-01-01", "amount": 100.0},
                    ],
                },
            }
        ]
    }
    result = hint.hint_for(context)
    assert result is not None
    assert "时间列" in result or "时序" in result


def test_hint_for_detects_id_column():
    hint = DataInsightHintPlugin()
    context = {
        "recent_tool_results": [
            {
                "tool_name": "data_analyst_read_csv",
                "result": {
                    "columns": ["uuid", "score"],
                    "dtypes": {"uuid": "object", "score": "float64"},
                    "row_count": 1000,
                    "preview_rows": [
                        {"uuid": f"u{i}", "score": 0.5} for i in range(10)
                    ],
                },
            }
        ]
    }
    result = hint.hint_for(context)
    assert result is not None
    assert "ID 列" in result or "uuid" in result


def test_hint_for_detects_large_dataset():
    hint = DataInsightHintPlugin()
    context = {
        "recent_tool_results": [
            {
                "tool_name": "data_analyst_read_csv",
                "result": {
                    "columns": ["x"],
                    "dtypes": {"x": "float64"},
                    "row_count": 200_000,
                    "preview_rows": [{"x": 1.0}],
                },
            }
        ]
    }
    result = hint.hint_for(context)
    assert result is not None
    assert "数据规模" in result or "100" in result


# ============================================================
# §10. v2 新增：AuditEventListener
# ============================================================


def test_audit_listener_protocol_shape(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    listener = AuditEventListener(audit_log_path=audit_path)
    assert listener.plugin_id == "data_analyst.audit_listener"
    subs = listener.get_subscriptions()
    topics = {s["topic"] for s in subs}
    assert "tool.call_started" in topics
    assert "tool.call_completed" in topics
    assert topics & {"agent.task_complete", "agent.task_failed"}


def test_audit_listener_writes_jsonl(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    listener = AuditEventListener(audit_log_path=audit_path)

    class _Event:
        def __init__(self, payload):
            self.payload = payload

    listener._on_tool_call_started(_Event({
        "tool_name": "data_analyst_read_csv",
        "args": {"path": "data.csv"},
    }))
    listener._on_tool_call_completed(_Event({
        "tool_name": "data_analyst_read_csv",
        "ok": True,
        "elapsed_ms": 12.3,
        "result": {"ok": True, "summary": "读到 20 行 × 5 列"},
    }))
    listener._on_task_complete(_Event({"summary": "done", "step_count": 6}))

    assert audit_path.exists()
    lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["kind"] == "tool_call_started"
    assert parsed[0]["tool_name"] == "data_analyst_read_csv"
    assert parsed[1]["kind"] == "tool_call_completed"
    assert parsed[1]["result_summary"]["summary"] == "读到 20 行 × 5 列"
    assert parsed[2]["kind"] == "task_complete"
    for record in parsed:
        assert "timestamp" in record and "timestamp_iso" in record


def test_audit_listener_handles_missing_payload(tmp_path):
    """listener 不应因事件 payload 缺字段而抛异常（容错）."""
    audit_path = tmp_path / "audit.jsonl"
    listener = AuditEventListener(audit_log_path=audit_path)

    class _Event:
        payload = {}

    listener._on_tool_call_started(_Event())
    listener._on_tool_call_completed(_Event())
    listener._on_task_complete(_Event())
    listener._on_task_failed(_Event())
    assert audit_path.exists()
    lines = audit_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 4
