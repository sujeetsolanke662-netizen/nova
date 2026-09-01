import sys
from pathlib import Path

# Make `backend` importable as a top-level package regardless of where
# pytest is invoked from. backend.app uses relative imports internally
# (e.g. `from . import audit_log`), which only resolve correctly when the
# module is imported through its real package path (backend.app.*), not
# as a bare top-level `app`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
