"""Script CLI : pre-process + vectorisation + indexation FAISS.

Usage :
    python scripts/02_build_index.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pulsevents_rag.config import load_settings  # noqa: E402
from pulsevents_rag.ingestion import load_raw_events  # noqa: E402
from pulsevents_rag.preprocessing import run_preprocessing  # noqa: E402
from pulsevents_rag.vectorstore import build_index  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


def main() -> int:
    settings = load_settings()
    df_raw = load_raw_events(settings)
    logging.info("Donnees chargees : %d lignes", len(df_raw))

    df_clean, documents = run_preprocessing(df_raw, settings)

    # Persistence en parquet pour debug / introspection
    out_path = settings.resolved_path(settings.paths.processed_dir) / "events_clean.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # On retire la colonne datetime locale ajoutee dans filter_recency_and_region
    cols_to_drop = [c for c in ["firstdate_begin_dt"] if c in df_clean.columns]
    df_clean.drop(columns=cols_to_drop).to_parquet(out_path, index=False)
    logging.info("Donnees nettoyees sauvegardees -> %s", out_path)

    if not documents:
        logging.error("Aucun document a indexer - check les filtres et la qualite des descriptions.")
        return 1

    build_index(documents, settings)
    print(f"OK : index FAISS construit sur {len(documents)} documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
