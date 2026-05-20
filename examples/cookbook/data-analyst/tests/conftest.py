"""Cookbook data-analyst smoke conftest — make plugin module importable from tests/."""
from __future__ import annotations

import sys
from pathlib import Path

# Add cookbook directory (parent of tests/) to sys.path so `import data_analyst_plugin` works
COOKBOOK_DIR = Path(__file__).resolve().parent.parent
if str(COOKBOOK_DIR) not in sys.path:
    sys.path.insert(0, str(COOKBOOK_DIR))
