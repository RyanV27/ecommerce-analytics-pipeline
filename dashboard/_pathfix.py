"""
Adds src/ (the repo root) to sys.path so page scripts can `from dashboard.bq
import ...` / `from ab_testing.ab_test import ...` regardless of invocation
directory or whether PYTHONPATH was set.

Importable without any prior path setup: Streamlit's multipage router runs
every page script with the main script's directory (dashboard/) on
sys.path[0], not the page script's own directory — so this module lives
directly in dashboard/, not dashboard/pages/. (A copy inside pages/ is
auto-discovered as a phantom nav entry and is unreachable via `import
_pathfix` from a page script, since dashboard/pages/ is never added to
sys.path.)
"""
import pathlib
import sys

_SRC_ROOT = str(pathlib.Path(__file__).parent.parent)
if _SRC_ROOT not in sys.path:
    sys.path.insert(0, _SRC_ROOT)
