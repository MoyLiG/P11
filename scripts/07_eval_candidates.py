"""Aide a l'annotation : affiche les candidats du retriever par question.

Pour chaque question in-scope de data/eval/qa_dataset.json, lance le
retriever hybride et liste les events candidats (uid, titre, ville, date).
La sortie sert a remplir manuellement les "expected_source_uids".

Usage :
    python scripts/07_eval_candidates.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pulsevents_rag.config import load_settings  # noqa: E402
from pulsevents_rag.rag import build_rag  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(message)s")


def main() -> int:
    settings = load_settings()
    pipeline = build_rag(settings)
    qa_path = settings.resolved_path(settings.paths.eval_dataset)
    dataset = json.loads(qa_path.read_text(encoding="utf-8"))

    for item in dataset:
        if item.get("out_of_scope"):
            continue
        q = item["question"]
        print("=" * 78)
        print(f"  Q{item['id']} : {q}")
        print("=" * 78)
        # On reutilise le retriever du pipeline (hybride)
        docs = pipeline.retriever.invoke(q)
        seen = set()
        for d in docs:
            uid = d.metadata.get("uid")
            if uid in seen:
                continue
            seen.add(uid)
            title = d.metadata.get("title") or "?"
            city = d.metadata.get("city") or "?"
            dr = d.metadata.get("daterange") or d.metadata.get("firstdate_begin") or "?"
            print(f'    {uid}  |  {title[:55]}  |  {city}  |  {dr}')
        print()

    print("\n>>> Copie cette sortie et transmets-la pour annotation des expected_source_uids.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
