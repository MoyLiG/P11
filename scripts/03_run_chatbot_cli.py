"""Script CLI : chatbot interactif en terminal.

Usage :
    python scripts/03_run_chatbot_cli.py
    > Quels concerts a Nantes en juin ?
    > /quit
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pulsevents_rag.config import load_settings  # noqa: E402
from pulsevents_rag.rag import build_rag  # noqa: E402

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def main() -> int:
    settings = load_settings()
    pipeline = build_rag(settings)
    print("=" * 70)
    print(f" Puls-Events Bot - {settings.filters.region}")
    print(" Tape ta question. '/quit' pour sortir.")
    print("=" * 70)

    while True:
        try:
            question = input("\nTu : ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"/quit", "/exit", ":q"}:
            break

        response = pipeline.answer(question)
        print(f"\nBot : {response.answer}")
        if response.sources:
            print("\nSources :")
            for s in response.sources:
                title = s.get("title") or "?"
                city = s.get("city") or ""
                dr = s.get("daterange") or ""
                url = s.get("url") or ""
                print(f"  - {title} | {city} | {dr}")
                if url:
                    print(f"    {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
