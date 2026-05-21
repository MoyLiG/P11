"""Debug : interroge directement l'index FAISS et affiche les chunks.

Permet de distinguer un probleme de retrieval (chunks hors-sujet)
d'un probleme de generation (LLM trop conservateur).

Usage :
    python scripts/06_debug_query.py "Quels concerts a Nantes ?"
    python scripts/06_debug_query.py    # questions par defaut
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pulsevents_rag.config import load_settings  # noqa: E402
from pulsevents_rag.vectorstore import load_index  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")

DEFAULT_QUESTIONS = [
    "Quels concerts a Nantes ?",
    "Festival de musique classique",
    "Expositions pour enfants",
    "Que faire ce week-end a Saint-Nazaire ?",
    "Theatre",
    "Concert rock",
]


def _truncate(text: str, n: int = 200) -> str:
    text = text.replace("\n", " ").strip()
    return text[:n] + ("..." if len(text) > n else "")


def main() -> int:
    settings = load_settings()
    print(f"\nChargement de l'index FAISS depuis {settings.paths.vectorstore_dir}...")
    vs = load_index(settings)
    print(f"Index charge.\n")

    queries = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_QUESTIONS

    for q in queries:
        print("=" * 80)
        print(f"  QUESTION : {q}")
        print("=" * 80)

        # 1) Similarity search avec scores (pas de MMR)
        print("\n--- Top 4 par similarite cosinus (scores - plus c'est petit, plus c'est proche) ---")
        results = vs.similarity_search_with_score(q, k=4)
        for i, (doc, score) in enumerate(results, 1):
            print(f"\n  [{i}]  score={score:.3f}  uid={doc.metadata.get('uid')}")
            print(f"       titre  : {doc.metadata.get('title')}")
            print(f"       ville  : {doc.metadata.get('city')}  |  dates : {doc.metadata.get('daterange')}")
            print(f"       contenu: {_truncate(doc.page_content, 180)}")

        # 2) MMR (ce que le bot utilise vraiment)
        print("\n--- Top 4 via MMR (configuration runtime) ---")
        mmr_results = vs.max_marginal_relevance_search(
            q,
            k=settings.retrieval.k,
            fetch_k=settings.retrieval.fetch_k,
        )
        for i, doc in enumerate(mmr_results, 1):
            print(f"  [{i}]  uid={doc.metadata.get('uid')}  |  {doc.metadata.get('title')}  |  {doc.metadata.get('city')}")

        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
