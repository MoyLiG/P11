"""Script CLI : lance l'evaluation du RAG sur le jeu de Q/R annote.

Usage :
    python scripts/05_evaluate.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pulsevents_rag.config import load_settings  # noqa: E402
from pulsevents_rag.evaluation import evaluate  # noqa: E402
from pulsevents_rag.rag import build_rag  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def main() -> int:
    settings = load_settings()
    pipeline = build_rag(settings)
    df = evaluate(pipeline, settings)

    # Affichage console
    print("\n=== Resultats par question ===")
    for _, row in df.iterrows():
        marker = "[hit]" if row["hit"] == 1 else ("[miss]" if row["hit"] == 0 else "[--]")
        cos = f"{row['cosine']:.2f}" if row["cosine"] is not None else "--"
        judge = f"{row['judge_score']}/5" if row["judge_score"] is not None else "--"
        print(f"  {marker} cos={cos} judge={judge} | Q{row['id']}: {row['question'][:60]}")

    print("\n=== Resume global ===")
    if df["hit"].notna().any():
        print(f"  hit_rate@k     : {df['hit'].dropna().mean() * 100:.1f}%")
    if df["cosine"].notna().any():
        print(f"  cosine moyenne : {df['cosine'].dropna().mean():.3f}")
    if df["judge_score"].notna().any():
        print(f"  juge moyen     : {df['judge_score'].dropna().mean():.2f} / 5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
