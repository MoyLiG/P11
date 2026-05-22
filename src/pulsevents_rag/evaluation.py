"""Evaluation du systeme RAG sur un jeu de questions / reponses annote.

Trois metriques :
- **hit_rate@k** : la source attendue (uid) est-elle dans les sources retournees ?
- **cosine_similarity** : similarite cosinus (via mistral-embed) entre la
  reponse generee et la reponse annotee.
- **llm_judge** : un appel LLM separe juge si la reponse generee couvre
  l'information de la reponse annotee (score 0 a 5).

Sortie : DataFrame + CSV + resume console.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
import pandas as pd
from langchain_core.prompts import ChatPromptTemplate
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pulsevents_rag.config import Settings

# Imports lourds (langchain LLM) charges paresseusement dans evaluate() :
# permet de tester summarize() sans installer toute la stack.
if TYPE_CHECKING:
    from pulsevents_rag.rag import RagPipeline

logger = logging.getLogger(__name__)

# Pause entre questions pour rester sous le rate limit Mistral (tier gratuit ~1 req/s).
EVAL_PAUSE_S = 1.5


@retry(
    retry=retry_if_not_exception_type((ValueError, KeyboardInterrupt)),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _retry_call(fn, *args, **kwargs):
    """Appel avec retry exponentiel sur les 429 / erreurs transientes Mistral.

    Ne retry PAS les ValueError (question trop longue, etc.).
    """
    return fn(*args, **kwargs)


JUDGE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Tu es un juge impartial. Compare la REPONSE_GENEREE a la REPONSE_ATTENDUE.\n"
            "Note de 0 a 5 la couverture des informations attendues :\n"
            "  0 = totalement faux ou hors-sujet ;\n"
            "  3 = capture l'essentiel ;\n"
            "  5 = couvre tout, exact, bien formule.\n"
            "Reponds UNIQUEMENT par un entier (0 a 5).",
        ),
        (
            "human",
            "QUESTION : {question}\n\nREPONSE_ATTENDUE : {expected}\n\nREPONSE_GENEREE : {generated}",
        ),
    ]
)


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if not np.any(va) or not np.any(vb):
        return 0.0
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))


def _safe_int(text: str) -> Optional[int]:
    text = text.strip().split()[0] if text else ""
    try:
        return max(0, min(5, int(text)))
    except ValueError:
        return None


def _strip_accents(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


# Formules de refus du bot (normalisees sans accent, en minuscules).
_REFUSAL_MARKERS = [
    "pas trouve",          # "Je n'ai pas trouve..."
    "n'ai pas",
    "aucun evenement",
    "cette periode",       # "...pour cette periode dans ma base"
    "correspondant dans ma base",
    "ne propose",
]


def _is_refusal(generated: str) -> bool:
    """Detecte si la reponse est un refus (robuste aux accents)."""
    norm = _strip_accents(generated.lower())
    return any(marker in norm for marker in _REFUSAL_MARKERS)


def load_qa_dataset(path: Path) -> list[dict]:
    """Charge le jeu de Q/R annote (JSON)."""
    if not path.exists():
        raise FileNotFoundError(f"Jeu d'evaluation introuvable : {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(
    pipeline: "RagPipeline",
    settings: Settings,
    qa_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Lance l'evaluation et retourne un DataFrame de resultats.

    Le DataFrame contient une ligne par question avec : reponse generee,
    sources, hit_rate, cosine, score_juge.
    """
    from langchain_mistralai import ChatMistralAI  # import paresseux (stack lourde)

    from pulsevents_rag.vectorstore import get_embeddings

    qa_path = qa_path or settings.resolved_path(settings.paths.eval_dataset)
    dataset = load_qa_dataset(qa_path)

    embeddings = get_embeddings(settings)
    judge_llm = ChatMistralAI(
        model=settings.models.llm_model,
        temperature=0.0,
        api_key=settings.mistral_api_key,
    )

    rows = []
    for i, item in enumerate(dataset, 1):
        question = item["question"]
        expected = item.get("expected_answer", "")
        expected_uids = set(item.get("expected_source_uids", []) or [])
        is_out_of_scope = bool(item.get("out_of_scope", False))

        logger.info("[%d/%d] %s", i, len(dataset), question)
        if i > 1:
            time.sleep(EVAL_PAUSE_S)  # espacement anti-429
        result = _retry_call(pipeline.answer, question)
        generated = result.answer
        retrieved_uids = {s.get("uid") for s in result.sources if s.get("uid")}

        # Hit rate
        if is_out_of_scope:
            # Pour les hors-sujet, "hit" = la reponse est un refus correct
            hit = int(_is_refusal(generated))
        elif expected_uids:
            hit = int(bool(expected_uids & retrieved_uids))
        else:
            hit = None  # pas mesurable (uids non annotes)

        # Cosine similarity
        try:
            v_gen = embeddings.embed_query(generated)
            v_exp = embeddings.embed_query(expected) if expected else None
            cos = _cosine(v_gen, v_exp) if v_exp else None
        except Exception as exc:  # pragma: no cover
            logger.warning("Erreur embedding : %s", exc)
            cos = None

        # LLM judge
        if expected:
            try:
                judge_chain = JUDGE_PROMPT | judge_llm
                judge_msg = _retry_call(
                    judge_chain.invoke,
                    {"question": question, "expected": expected, "generated": generated},
                )
                judge_score = _safe_int(judge_msg.content)
            except Exception as exc:  # pragma: no cover
                logger.warning("Erreur juge : %s", exc)
                judge_score = None
        else:
            judge_score = None

        rows.append(
            {
                "id": item.get("id", i),
                "question": question,
                "expected": expected,
                "generated": generated,
                "expected_uids": ", ".join(sorted(expected_uids)),
                "retrieved_uids": ", ".join(sorted(u for u in retrieved_uids if u)),
                "hit": hit,
                "cosine": cos,
                "judge_score": judge_score,
                "out_of_scope": is_out_of_scope,
            }
        )

    df = pd.DataFrame(rows)

    out_path = settings.resolved_path(settings.paths.eval_results)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8")
    logger.info("Resultats sauvegardes -> %s", out_path)

    logger.info("Resume : %s", summarize(df))
    return df


def summarize(df: pd.DataFrame) -> dict:
    """Agrege les 3 metriques d'un DataFrame de resultats (un run)."""
    return {
        "n_questions": len(df),
        "hit_rate": df["hit"].dropna().mean() if df["hit"].notna().any() else None,
        "cosine": df["cosine"].dropna().mean() if df["cosine"].notna().any() else None,
        "judge": df["judge_score"].dropna().mean() if df["judge_score"].notna().any() else None,
    }


def evaluate_multi(
    pipeline: "RagPipeline",
    settings: Settings,
    n_runs: int = 3,
    qa_path: Optional[Path] = None,
) -> dict:
    """Lance l'evaluation ``n_runs`` fois et agrege moyenne + ecart-type.

    Utile car le juge LLM (et la generation a T>0) ne sont pas
    deterministes : un run unique n'est pas representatif. On reporte
    moyenne ± ecart-type sur plusieurs runs.

    Returns:
        dict avec, par metrique, mean / std / values.
    """
    per_run: list[dict] = []
    dfs: list[pd.DataFrame] = []
    for r in range(1, n_runs + 1):
        logger.info("===== Run %d / %d =====", r, n_runs)
        df = evaluate(pipeline, settings, qa_path)
        per_run.append(summarize(df))
        dfs.append(df)

    # Agregat GLOBAL (moyenne +/- ecart-type sur les runs)
    agg: dict = {"n_runs": n_runs, "per_run": per_run, "metrics": {}}
    for key in ("hit_rate", "cosine", "judge"):
        vals = [run[key] for run in per_run if run[key] is not None]
        if vals:
            agg["metrics"][key] = {
                "mean": float(np.mean(vals)),
                "std": float(np.std(vals)),
                "min": float(np.min(vals)),
                "max": float(np.max(vals)),
                "values": [round(v, 4) for v in vals],
            }

    # Agregat PAR QUESTION (moyenne + ecart-type du juge sur les runs)
    allruns = pd.concat(dfs, ignore_index=True)
    per_q = (
        allruns.groupby("id")
        .agg(
            question=("question", "first"),
            out_of_scope=("out_of_scope", "first"),
            hit=("hit", "mean"),
            cosine=("cosine", "mean"),
            judge_mean=("judge_score", "mean"),
            judge_std=("judge_score", "std"),
        )
        .reset_index()
    )
    agg["per_question"] = per_q

    logger.info("Resume multi-run : %s", agg["metrics"])
    return agg
