"""skill-loader cookbook smoke。

判据围绕一件事：**这两个 SKILL.md 真的被翻译对了吗**。
只断言"装载没报错"是不够的 —— 裸 SKILL.md 本来就能装载，
丢的是 frontmatter（description / priority / hint），而那正是 skill 有没有用的分水岭。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import krow_agent_sdk
from krow_agent_sdk import SkillLoadError, skill_adapter

# ⚠️ 走属性访问拿子模块，**不要**写 ``from krow_agent_sdk.skill_adapter import ...``：
# 在 monorepo 里 ``krow_agent_sdk`` 顶层被 runtime_guard 解析到 ``modules.agent.sdk``，
# 而显式的点路径 import 会沿 packages/ 的符号链接**另载一份**同名模块 —— 于是
# ``SkillLoadError`` 有两个互不相等的类对象，``pytest.raises`` 抓不住实际抛出的那个。
# 纯 PyPI 安装下不存在这个二义性；这是仓内测试才会踩到的坑。
load_skills_from_directory = skill_adapter.load_skills_from_directory
materialize_skill = skill_adapter.materialize_skill
parse_skill_md = skill_adapter.parse_skill_md

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
EXPECTED = {"word_format", "release_notes"}


def test_bundled_skills_parse():
    """自带的两个 SKILL.md 必须都能解析（缺字段会 fail-loud）。"""
    found = {parse_skill_md(p / "SKILL.md").name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    assert found == {"word-format", "release-notes"}


def test_skills_load_into_act_plugins(tmp_path):
    plugins = load_skills_from_directory(SKILLS_DIR, tmp_path / "cache")
    assert {p.act_name for p in plugins} == EXPECTED


def test_frontmatter_survives(tmp_path):
    """L4 的全部缺口就是这三项 —— description / priority / planner_hint。"""
    manifest = parse_skill_md(SKILLS_DIR / "word-format" / "SKILL.md")
    _, report = materialize_skill(manifest, tmp_path / "cache")

    act = yaml.safe_load(
        (tmp_path / "cache" / report.act_name / "__act__.yaml").read_text("utf-8")
    )
    assert act["description"] == manifest.description
    assert not act["description"].startswith("#"), "description 退化成了正文首行"
    assert act["priority"] > 3, "priority 是『没读到元数据』的回落值"
    assert act["planner_hint"], "planner_hint 为空 = 该 skill 永远不会被选中"


def test_kebab_rename_is_visible(tmp_path):
    """`word-format` → `word_format`，改了名就要说出来。"""
    plugins = load_skills_from_directory(SKILLS_DIR, tmp_path / "cache")
    word = next(p for p in plugins if p.act_name == "word_format")

    assert word.load_report.renamed is True
    assert "word-format" in word.load_report.describe()


def test_declared_tools_are_reported_against_reality(tmp_path):
    """word-format 声明了 3 个工具；未命中的要逐条报出，不猜测映射。"""
    plugins = load_skills_from_directory(
        SKILLS_DIR, tmp_path / "cache", known_tools={"word_apply_style_spec"}
    )
    report = next(p for p in plugins if p.act_name == "word_format").load_report

    assert report.resolved_tools == ["word_apply_style_spec"]
    assert set(report.unknown_tools) == {"word_extract_style_spec", "word_analyze_state"}


def test_pure_instruction_skill_binds_no_tools(tmp_path):
    """release-notes 没有 allowed-tools —— 纯指令型 skill 是合法形态。"""
    plugins = load_skills_from_directory(SKILLS_DIR, tmp_path / "cache")
    report = next(p for p in plugins if p.act_name == "release_notes").load_report

    assert report.declared_tools == []
    assert report.resolved_tools == []


def test_source_skills_are_never_written(tmp_path):
    """适配器纯读 —— 用户的 skill 目录可能只读，改它是越权。"""
    before = {p.name: p.read_bytes() for p in SKILLS_DIR.rglob("SKILL.md")}
    load_skills_from_directory(SKILLS_DIR, tmp_path / "cache")
    after = {p.name: p.read_bytes() for p in SKILLS_DIR.rglob("SKILL.md")}
    assert after == before


def test_bad_skill_fails_loud(tmp_path):
    """缺 description 要当场报错，而不是安静地少装一个。"""
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "SKILL.md").write_text("---\nname: no-desc\n---\n正文", encoding="utf-8")
    with pytest.raises(SkillLoadError, match="description"):
        load_skills_from_directory(bad, tmp_path / "cache")


def test_main_runs_dry(capsys, tmp_path, monkeypatch):
    """`python main.py --dry-run` 必须能在没有 API key / runtime 的情况下跑通。"""
    import main as demo

    # 打在 demo 真正会用到的那个类对象上（理由同文件头的模块二义性注释）——
    # 打错对象的话物化会落进真实项目目录，而测试照样绿。
    monkeypatch.setattr(
        krow_agent_sdk.AgentBuilder,
        "_skill_cache_root",
        lambda self: tmp_path / "cache",
    )
    monkeypatch.setattr("sys.argv", ["main.py", "--dry-run"])

    assert demo.main() == 0
    out = capsys.readouterr().out
    assert "已装载 2 个 skill" in out
    assert "word_format" in out
