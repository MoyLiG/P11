"""Tests du retriever hybride - lexical (BM25) + dense.

BM25 ne fait pas d'appel API, on peut tester offline.
La partie dense (FAISS + Mistral) est testee separement.
"""

from __future__ import annotations

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document


def test_bm25_finds_exact_keyword(sample_events, settings):
    """BM25 doit retrouver un Document contenant le mot exact recherche.

    C'est le cas d'usage central qui justifie l'hybrid search :
    la recherche dense est sensible a la formulation, BM25 capte le
    mot-cle precis.
    """
    docs = [
        Document(
            page_content="Concert de musique classique a Nantes a la Cite des Congres.",
            metadata={"uid": "evt-1", "city": "Nantes"},
        ),
        Document(
            page_content="Exposition d'art contemporain au musee d'arts de Paris.",
            metadata={"uid": "evt-2", "city": "Paris"},
        ),
        Document(
            page_content="Festival de cinema independant a Saint-Nazaire en juin.",
            metadata={"uid": "evt-3", "city": "Saint-Nazaire"},
        ),
    ]
    bm25 = BM25Retriever.from_documents(docs)
    bm25.k = 1
    results = bm25.invoke("Nantes Cite des Congres")
    assert results, "BM25 doit retourner au moins un Document"
    assert results[0].metadata["uid"] == "evt-1"


def test_bm25_ranks_relevant_first(sample_events, settings):
    """BM25 doit prioriser un Document avec plusieurs occurrences du terme."""
    docs = [
        Document(page_content="Concert Concert Concert a Nantes", metadata={"uid": "a"}),
        Document(page_content="Marche aux fleurs a Nantes", metadata={"uid": "b"}),
        Document(page_content="Vente aux encheres a Paris", metadata={"uid": "c"}),
    ]
    bm25 = BM25Retriever.from_documents(docs)
    bm25.k = 3
    results = bm25.invoke("Concert Nantes")
    uids = [r.metadata["uid"] for r in results]
    assert uids[0] == "a", f"Ordre attendu a,b,c (decroissant TF-IDF) ; recu {uids}"


def test_hybrid_config_round_trip(settings):
    """La config charge bien use_hybrid et bm25_weight."""
    assert hasattr(settings.retrieval, "use_hybrid")
    assert isinstance(settings.retrieval.use_hybrid, bool)
    assert hasattr(settings.retrieval, "bm25_weight")
    assert 0.0 <= settings.retrieval.bm25_weight <= 1.0


def test_summarize_aggregates_metrics():
    """summarize() calcule hit_rate, cosine, judge depuis un DataFrame."""
    import pandas as pd

    from pulsevents_rag.evaluation import summarize

    df = pd.DataFrame(
        {
            "hit": [1, 0, 1, None],
            "cosine": [0.9, 0.8, 0.85, 0.7],
            "judge_score": [5, 3, 4, None],
        }
    )
    s = summarize(df)
    assert s["n_questions"] == 4
    assert abs(s["hit_rate"] - (2 / 3)) < 1e-6  # 2 hits sur 3 mesurables
    assert abs(s["cosine"] - 0.8125) < 1e-6
    assert abs(s["judge"] - 4.0) < 1e-6
