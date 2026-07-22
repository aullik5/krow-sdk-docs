"""可跑 demo：注册决策脑三注册表 + 模拟三种态势看信号/唤醒结果。

无需真实 LLM / API key —— 本 demo 只演示"观测层 + 唤醒层"如何把领域完整度
信号接进决策脑。真实任务里这些信号会在 Agent 运行的每个 macro 拍自动被采集。

运行：
    python main.py
"""
from __future__ import annotations

from types import SimpleNamespace

from litsci_metacog_demo import (
    DownloadCompletenessContributor,
    register,
    wake_zero_download_with_hits,
)


def _fake_executor(**step_results) -> SimpleNamespace:
    """构造与 Krow ProgressiveExecutor 同形的最小执行器（暴露 _step_results）。"""
    return SimpleNamespace(_step_results=step_results)


def _sr(tool: str, output: dict) -> SimpleNamespace:
    return SimpleNamespace(tool=tool, output=output)


def _snapshot(contributor, executor):
    """模拟决策脑单拍：调 contributor 得 signals/error_vector，包成 snapshot。"""
    data = contributor(executor)
    return SimpleNamespace(
        signals=data.get("signals", {}),
        error_vector=data.get("error_vector", {}),
    )


def main() -> None:
    # 1) 注册（幂等）。strict=False 便于无 SDK 环境时也能读到提示。
    fqcns = register(strict=False)
    if not fqcns:
        print("[!] 未检测到 krow-agent-sdk[runtime]，跳过真实注册（仅演示逻辑）。\n")
    else:
        print(f"[ok] 已注册：{fqcns}\n")

    contributor = DownloadCompletenessContributor()

    # 场景 A：检索到 5 篇却零下载（F1 空转前兆）→ 应唤醒。
    exe_a = _fake_executor(
        s1=_sr("paper_search", {"papers": [{"id": i} for i in range(5)]}),
        s2=_sr("download_pdf", {"counts": {"requested": 5, "downloaded": 0, "failed": 5}}),
    )
    snap_a = _snapshot(contributor, exe_a)
    print("场景 A（5 篇候选，0 下载）：")
    print(f"  applicable = {contributor.applicable(exe_a)}")
    print(f"  error_vector = {snap_a.error_vector}")
    print(f"  wake = {wake_zero_download_with_hits(None, snap_a, {}, None)}\n")

    # 场景 B：5 篇里下 4 篇（失败率 0.2 < 0.5）→ 不唤醒（正常推进）。
    exe_b = _fake_executor(
        s1=_sr("paper_search", {"papers": [{"id": i} for i in range(5)]}),
        s2=_sr("download_pdf", {"counts": {"requested": 5, "downloaded": 4, "failed": 1}}),
    )
    snap_b = _snapshot(contributor, exe_b)
    print("场景 B（5 篇候选，下 4 篇）：")
    print(f"  error_vector = {snap_b.error_vector}")
    print(f"  wake = {wake_zero_download_with_hits(None, snap_b, {}, None)}\n")

    # 场景 C：非文献任务（无 paper_search / download_pdf）→ 不适用（天然门禁）。
    exe_c = _fake_executor(s1=_sr("write_output", {"path": "report.md"}))
    print("场景 C（非文献任务）：")
    print(f"  applicable = {contributor.applicable(exe_c)}  ← 收窄，避免'传感器失活'假阳")


if __name__ == "__main__":
    main()
