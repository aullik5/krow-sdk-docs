"""Pytest conftest for contract-auditor cookbook tests.

把 cookbook 根目录加到 sys.path，让 ``from contract_auditor_plugin import ...``
能直接 work（cookbook 不是常规 site-packages 安装，只是单文件 plugin）。
"""
from __future__ import annotations

import sys
from pathlib import Path

_COOKBOOK_DIR = Path(__file__).resolve().parent.parent
if str(_COOKBOOK_DIR) not in sys.path:
    sys.path.insert(0, str(_COOKBOOK_DIR))
