"""Tests unitaires du module vectorstore (sans appel reseau Mistral).

On ne teste PAS la creation reelle de l'index (ca couterait des tokens
Mistral). On teste :
- le decoupage en chunks (offline, deterministe) ;
- le comportement de ``get_embeddings`` quand la cle API est absente.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from pulsevents_rag.vectorstore import get_embeddings, split_documents


def test_split_documents_creates_chunks(settings):
    long_text = ("Phrase. " * 200).strip()
    docs = [Document(page_content=long_text, metadata={"uid": "x"})]
    chunks = split_documents(docs, settings)
    assert len(chunks) > 1, "Un document long doit etre decoupe en plusieurs chunks."
    # Tous les chunks doivent porter les metadonnees d'origine
    assert all(c.metadata.get("uid") == "x" for c in chunks)
    # Aucun chunk ne doit depasser la limite + une marge raisonnable
    assert all(len(c.page_content) <= settings.chunking.chunk_size + 50 for c in chunks)


def test_get_embeddings_requires_api_key(settings):
    no_key = settings.model_copy(update={"mistral_api_key": None})
    with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
        get_embeddings(no_key, use_cache=False)
