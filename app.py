"""App Streamlit - demo live du POC RAG Puls-Events.

Lancement :
    streamlit run app.py

Hardening applique (cf. docs/SECURITY.md) :
- Cap longueur question (settings.retrieval.max_question_length).
- Rate-limit par session Streamlit (MAX_QUERIES_PER_SESSION).
- Validation du scheme URL avant rendu markdown.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from pulsevents_rag.config import load_settings  # noqa: E402
from pulsevents_rag.rag import build_rag  # noqa: E402

# Garde-fou contre l'abus de cout / DoS si l'app est exposee au-dela de
# localhost. A combiner avec une auth reverse-proxy en production.
MAX_QUERIES_PER_SESSION = 30

st.set_page_config(
    page_title="Puls-Events Bot",
    page_icon="🎭",
    layout="wide",
)


def _safe_url(url: str | None) -> str | None:
    """Retourne l'URL seulement si le scheme est http/https.

    Defense contre l'injection de scheme malveillant
    (`javascript:`, `data:`...) via les metadonnees Open Agenda
    (cf. security audit M2).
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    return url


@st.cache_resource(show_spinner="Chargement de l'index FAISS et du modele Mistral...")
def get_pipeline():
    settings = load_settings()
    return build_rag(settings), settings


def main() -> None:
    st.title("🎭 Puls-Events Bot")
    st.caption("POC RAG - evenements culturels Open Agenda")

    try:
        pipeline, settings = get_pipeline()
    except FileNotFoundError as exc:
        st.error(
            "Index FAISS introuvable. Lance d'abord :\n\n"
            "`python scripts/01_fetch_data.py`\n"
            "`python scripts/02_build_index.py`\n\n"
            f"Detail : {exc}"
        )
        st.stop()
    except ValueError as exc:
        st.error(f"Configuration invalide : {exc}")
        st.stop()

    with st.sidebar:
        st.header("Parametres")
        st.write(f"**Region :** {settings.filters.region}")
        if settings.filters.department:
            st.write(f"**Departement :** {settings.filters.department}")
        if settings.filters.city:
            st.write(f"**Ville :** {settings.filters.city}")
        st.write(f"**Fenetre temporelle :** {settings.filters.since_days} jours")
        st.write(f"**Modele LLM :** `{settings.models.llm_model}`")
        st.write(f"**Modele embedding :** `{settings.models.embedding_model}`")
        st.write(
            f"**Top-k retriever :** {settings.retrieval.k} "
            f"(MMR sur {settings.retrieval.fetch_k})"
        )
        st.divider()
        if "query_count" in st.session_state:
            remaining = MAX_QUERIES_PER_SESSION - st.session_state.query_count
            st.metric("Questions restantes (session)", remaining)
        st.divider()
        st.markdown(
            "**Exemples de questions :**\n"
            "- Quels concerts a Nantes ce mois-ci ?\n"
            "- Y a-t-il des expositions pour enfants en Loire-Atlantique ?\n"
            "- Que faire ce week-end a Saint-Nazaire ?\n"
            "- Festivals de musique classique cet ete ?"
        )

    if "history" not in st.session_state:
        st.session_state.history = []
    if "query_count" not in st.session_state:
        st.session_state.query_count = 0

    max_len = settings.retrieval.max_question_length
    question = st.chat_input(f"Pose ta question (max {max_len} caracteres)...")

    if question:
        # --- Rate limit session -----------------------------------------
        if st.session_state.query_count >= MAX_QUERIES_PER_SESSION:
            st.error(
                f"Quota de la session atteint ({MAX_QUERIES_PER_SESSION} questions). "
                "Recharge la page pour reinitialiser."
            )
            return

        # --- Cap longueur question --------------------------------------
        if len(question) > max_len:
            st.error(
                f"Question trop longue ({len(question)} caracteres). "
                f"Limite : {max_len}."
            )
            return

        st.session_state.query_count += 1

        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Recherche dans la base..."):
                try:
                    response = pipeline.answer(question)
                except ValueError as exc:
                    st.error(f"Erreur : {exc}")
                    return
            st.markdown(response.answer)
            if response.sources:
                with st.expander(f"📍 Sources ({len(response.sources)})"):
                    for s in response.sources:
                        title = s.get("title") or "?"
                        city = s.get("city") or ""
                        dr = s.get("daterange") or ""
                        url = _safe_url(s.get("url"))  # ⚠ validation scheme
                        line = f"**{title}**"
                        if city:
                            line += f" - {city}"
                        if dr:
                            line += f" - _{dr}_"
                        if url:
                            line += f"\n\n[Voir sur Open Agenda]({url})"
                        st.markdown(line)
                        st.divider()
        st.session_state.history.append({"q": question, "a": response.answer})

    if st.session_state.history:
        with st.expander("Historique"):
            for item in reversed(st.session_state.history[-10:]):
                st.markdown(f"**Q :** {item['q']}")
                st.markdown(f"**R :** {item['a']}")
                st.divider()


if __name__ == "__main__":
    main()
