"""Script CLI : telecharge les evenements Open Agenda et les sauvegarde en JSON.

Usage :
    python scripts/01_fetch_data.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Permet d'executer le script depuis la racine sans installer le package
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pulsevents_rag.config import load_settings  # noqa: E402
from pulsevents_rag.ingestion import fetch_open_agenda  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def main() -> int:
    settings = load_settings()
    logging.info(
        "Filtres : region=%s, dept=%s, ville=%s, since=%dj, max=%d",
        settings.filters.region,
        settings.filters.department,
        settings.filters.city,
        settings.filters.since_days,
        settings.filters.max_records,
    )
    df = fetch_open_agenda(settings, save_raw=True)
    logging.info("DataFrame brute : %d lignes, %d colonnes", *df.shape)
    if df.empty:
        logging.warning("Aucun evenement recupere - elargis les filtres ?")
        return 1
    print(f"OK : {len(df)} evenements telecharges.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
