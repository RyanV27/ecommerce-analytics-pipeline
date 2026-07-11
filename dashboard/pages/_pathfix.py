"""
Adds src/ (the repo root) to sys.path so page scripts can `from dashboard.bq
import ...` / `from ab_testing.ab_test import ...` regardless of invocation
directory or whether PYTHONPATH was set.

Importable without any prior path setup: Streamlit executes each page script
with its own directory (dashboard/pages/) already on sys.path, the same way
`python dashboard/pages/1_Overview.py` would put that directory on sys.path[0].
"""
import pathlib
import sys

_SRC_ROOT = str(pathlib.Path(__file__).parent.parent.parent)
if _SRC_ROOT not in sys.path:
    sys.path.insert(0, _SRC_ROOT)
