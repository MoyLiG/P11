"""Script CLI : lance l'evaluation du RAG sur le jeu de Q/R annote.

Usage :
    python scripts/05_evaluate.py             # 1 run (detail par question)
    python scripts/05_evaluate.py --runs 3    # 3 runs, moyenne +/- ecart-type

Le mode multi-run est recommande : le juge LLM n'est pas deterministe,
un run unique n'est pas representatif (cf. journal J19).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pulsevents_rag.config import load_settings  # noqa: E402
from pulsevents_rag.evaluation import evaluate, evaluate_multi  # noqa: E402
from pulsevents_rag.rag import build_rag  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def _run_single(pipeline, settings) -> int:
    df = evaluate(pipeline, settings)
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


def _run_multi(pipeline, settings, n_runs: int) -> int:
    import pandas as pd

    agg = evaluate_multi(pipeline, settings, n_runs=n_runs)

    # Detail par question (moyenne sur les runs + variance du juge)
    print(f"\n=== Detail par question (moyenne sur {n_runs} runs) ===")
    per_q = agg["per_question"].sort_values("id")
    for _, row in per_q.iterrows():
        hit = row["hit"]
        if pd.isna(hit):
            marker = "[--]  "
        elif hit == 1:
            marker = "[hit] "
        elif hit == 0:
            marker = "[miss]"
        else:
            marker = "[part]"  # hit varie entre runs (rare : retriever deterministe)
        cos = f"{row['cosine']:.2f}" if pd.notna(row["cosine"]) else "--"
        jm = f"{row['judge_mean']:.1f}" if pd.notna(row["judge_mean"]) else "--"
        js = f"+/-{row['judge_std']:.1f}" if pd.notna(row["judge_std"]) else ""
        print(f"  {marker} cos={cos} judge={jm}{js}/5 | Q{int(row['id'])}: {row['question'][:52]}")

    print(f"\n=== Resume sur {n_runs} runs (moyenne +/- ecart-type) ===")
    labels = {"hit_rate": "hit_rate@k   ", "cosine": "cosine moyenne", "judge": "juge moyen   "}
    for key, label in labels.items():
        m = agg["metrics"].get(key)
        if not m:
            continue
        if key == "hit_rate":
            print(f"  {label} : {m['mean']*100:.1f}% +/- {m['std']*100:.1f}  "
                  f"(min {m['min']*100:.0f}% / max {m['max']*100:.0f}%)")
        elif key == "cosine":
            print(f"  {label} : {m['mean']:.3f} +/- {m['std']:.3f}  "
                  f"(min {m['min']:.3f} / max {m['max']:.3f})")
        else:
            print(f"  {label} : {m['mean']:.2f} +/- {m['std']:.2f} / 5  "
                  f"(min {m['min']:.2f} / max {m['max']:.2f})  valeurs={m['values']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluation du RAG Puls-Events")
    parser.add_argument("--runs", type=int, default=1,
                        help="Nombre de runs (>1 => moyenne +/- ecart-type)")
    args = parser.parse_args()

    settings = load_settings()
    pipeline = build_rag(settings)

    if args.runs > 1:
        return _run_multi(pipeline, settings, args.runs)
    return _run_single(pipeline, settings)


if __name__ == "__main__":
    raise SystemExit(main())
