"""Pipeline end-to-end : ingestion -> tests -> indexation.

Usage :
    python scripts/pipeline.py
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path


def _run(label: str, cmd: list[str]) -> int:
    print(f"\n>>> {label}")
    rc = subprocess.call(cmd)
    if rc != 0:
        print(f"!!! Echec : {label} (code {rc})")
    return rc


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    root = Path(__file__).resolve().parents[1]
    py = sys.executable

    rc = _run("01 Telechargement Open Agenda", [py, str(root / "scripts" / "01_fetch_data.py")])
    if rc != 0:
        return rc

    rc = _run("Tests qualite des donnees", [py, "-m", "pytest", str(root / "tests" / "test_data_freshness.py"), str(root / "tests" / "test_data_geography.py"), "-v"])
    if rc != 0:
        return rc

    rc = _run("02 Construction de l'index FAISS", [py, str(root / "scripts" / "02_build_index.py")])
    if rc != 0:
        return rc

    print("\nPipeline terminee.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
