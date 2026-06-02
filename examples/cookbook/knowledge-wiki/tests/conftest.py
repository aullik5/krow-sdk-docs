"""Pytest fixtures for knowledge-wiki cookbook tests."""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_COOKBOOK_ROOT = _HERE.parent

if str(_COOKBOOK_ROOT) not in sys.path:
    sys.path.insert(0, str(_COOKBOOK_ROOT))
