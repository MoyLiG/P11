"""Construction et chargement de l'index vectoriel FAISS.

On utilise :
- ``RecursiveCharacterTextSplitter`` (LangChain) pour decouper les
  documents longs en chunks gerables ;
- ``MistralAIEmbeddings`` pour la vectorisation (modele ``mistral-embed``,
  dimension 1024) ;
- ``FAISS`` (CPU) pour l'index local persiste (``IndexFlatL2`` par defaut).

Persistance via ``FAISS.save_local()`` qui ecrit ``index.faiss`` (vecteurs)
et ``index.pkl`` (mapping doc -> metadata).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from langchain.embeddings import CacheBackedEmbeddings
from langchain.storage import LocalFileStore
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_mistralai import MistralAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pulsevents_rag.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wrapper anti rate-limit autour de MistralAIEmbeddings
# ---------------------------------------------------------------------------


class RateLimitedMistralEmbeddings(Embeddings):
    """Decorateur qui rate-limit + retry les appels a MistralAIEmbeddings.

    Mistral La Plateforme limite ~1 req/s sur le tier gratuit. Sans rate
    limit cote client, on prend des HTTP 429. Pire, langchain-mistralai
    0.2.x a un bug : il parse ``response.json()["data"]`` meme sur 429,
    ce qui crash en ``KeyError: 'data'`` au lieu d'un retry propre.

    Ce wrapper :
    - garantit un intervalle minimum entre appels (defaut 1.1 s) ;
    - batch les documents par paquets (defaut 24 chunks ; reste sous la
      limite Mistral de tokens/batch) ;
    - retry exponentiel sur quasiment toutes exceptions (incl. KeyError
      qui signe un 429 mal gere).
    """

    def __init__(
        self,
        base: MistralAIEmbeddings,
        min_interval_s: float = 1.1,
        batch_size: int = 24,
    ):
        self._base = base
        self._min_interval = min_interval_s
        self._batch_size = batch_size
        self._last_ts = 0.0

    # tenacity n'aime pas les methodes ; on passe par un wrapper.
    @retry(
        retry=retry_if_not_exception_type((ValueError, TypeError, NotImplementedError)),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _safe_call(self, fn, *args, **kwargs):
        elapsed = time.time() - self._last_ts
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        try:
            result = fn(*args, **kwargs)
        finally:
            self._last_ts = time.time()
        return result

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        total = len(texts)
        for start in range(0, total, self._batch_size):
            chunk = texts[start:start + self._batch_size]
            vectors = self._safe_call(self._base.embed_documents, chunk)
            out.extend(vectors)
            done = start + len(chunk)
            if done % (self._batch_size * 10) == 0 or done == total:
                logger.info("Embeddings : %d / %d documents (%.0f%%)",
                            done, total, 100 * done / max(total, 1))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._safe_call(self._base.embed_query, text)


# ---------------------------------------------------------------------------
# Decoupage en chunks
# ---------------------------------------------------------------------------


def split_documents(documents: list[Document], settings: Settings) -> list[Document]:
    """Decoupe les documents en chunks adaptes a l'embedding.

    Les separateurs respectent la structure FR (paragraphes, phrases).
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunking.chunk_size,
        chunk_overlap=settings.chunking.chunk_overlap,
        separators=["\n\n", "\n", ". ", "? ", "! ", ", ", " ", ""],
        length_function=len,
    )
    chunks = splitter.split_documents(documents)
    logger.info("Decoupage : %d documents -> %d chunks", len(documents), len(chunks))
    return chunks


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


def get_embeddings(settings: Settings, use_cache: bool = True) -> Embeddings:
    """Instancie le modele d'embeddings Mistral, eventuellement cache.

    Le cache (``CacheBackedEmbeddings`` + ``LocalFileStore``) evite de
    re-embedder les textes deja vus lors d'un rebuild de l'index. Gain
    typique : 95 % sur les rebuilds qui ne touchent que quelques events
    nouveaux (cf. audit cost-reducer).

    Args:
        settings: configuration projet.
        use_cache: si True (defaut), wrap l'embedder dans un cache disque
            persiste a ``data/embed_cache/``. Mettre a False pour le test
            unitaire.

    Raises:
        ValueError: si la cle API n'est pas renseignee.
    """
    if not settings.mistral_api_key:
        raise ValueError(
            "MISTRAL_API_KEY absente. Renseigne-la dans .env "
            "(voir https://console.mistral.ai pour obtenir une cle)."
        )
    base = MistralAIEmbeddings(
        model=settings.models.embedding_model,
        api_key=settings.mistral_api_key,
    )
    # Toujours wrapper en rate-limited : evite les 429 et le bug
    # KeyError 'data' de langchain-mistralai 0.2.x. L'intervalle vient
    # de la config (1.1s tier gratuit, 0.3s tier Pro).
    rate_limited = RateLimitedMistralEmbeddings(
        base,
        min_interval_s=settings.models.embedding_min_interval_s,
        batch_size=settings.models.embedding_batch_size,
    )
    if not use_cache:
        return rate_limited
    cache_dir = settings.project_root / "data" / "embed_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    store = LocalFileStore(str(cache_dir))
    return CacheBackedEmbeddings.from_bytes_store(
        rate_limited, store, namespace=settings.models.embedding_model
    )


# ---------------------------------------------------------------------------
# Build / load FAISS
# ---------------------------------------------------------------------------


def build_index(documents: list[Document], settings: Settings) -> FAISS:
    """Construit l'index FAISS et le persiste sur disque.

    Args:
        documents: documents LangChain deja pre-processes.
        settings: configuration projet.

    Returns:
        L'objet ``FAISS`` charge en memoire (egalement sauvegarde sur disque).
    """
    chunks = split_documents(documents, settings)
    embeddings = get_embeddings(settings)
    logger.info(
        "Construction de l'index FAISS sur %d chunks (modele=%s)...",
        len(chunks),
        settings.models.embedding_model,
    )
    vectorstore = FAISS.from_documents(chunks, embeddings)

    persist_dir: Path = settings.resolved_path(settings.paths.vectorstore_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(persist_dir))
    logger.info("Index FAISS sauvegarde -> %s", persist_dir)
    return vectorstore


def load_index(settings: Settings) -> FAISS:
    """Recharge un index FAISS deja persiste.

    Raises:
        FileNotFoundError: si l'index n'existe pas.
    """
    persist_dir: Path = settings.resolved_path(settings.paths.vectorstore_dir)
    if not (persist_dir / "index.faiss").exists():
        raise FileNotFoundError(
            f"Aucun index FAISS dans {persist_dir}. Lance scripts/02_build_index.py"
        )
    embeddings = get_embeddings(settings)
    return FAISS.load_local(
        str(persist_dir),
        embeddings,
        allow_dangerous_deserialization=True,
    )


def load_documents_for_bm25(settings: Settings) -> list[Document]:
    """Recharge les Documents pre-processes pour alimenter BM25Retriever.

    BM25 est un index lexical (pas d'embedding). On le reconstruit en
    memoire au demarrage a partir du parquet ``events_clean.parquet``.
    C'est rapide (< 1 s sur quelques milliers de docs) et evite la
    duplication d'un second index sur disque.

    Raises:
        FileNotFoundError: si le parquet n'existe pas.
    """
    import pandas as pd

    from pulsevents_rag.preprocessing import to_documents

    parquet = settings.resolved_path(settings.paths.processed_dir) / "events_clean.parquet"
    if not parquet.exists():
        raise FileNotFoundError(
            f"Parquet introuvable : {parquet}. Lance scripts/02_build_index.py."
        )
    df = pd.read_parquet(parquet)
    docs = to_documents(df, settings.preprocessing.min_description_length)
    logger.info("BM25 : %d Documents reconstruits depuis %s", len(docs), parquet.name)
    return docs
