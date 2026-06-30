"""Helper : lance Streamlit sur app.py.

Usage :
    python scripts/04_run_streamlit.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    app = root / "app.py"
    return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app)])


if __name__ == "__main__":
    raise SystemExit(main())
