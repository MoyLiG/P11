"""Pre-processing des evenements Open Agenda.

Etapes :
    1. Nettoyage HTML (BeautifulSoup ``get_text``).
    2. Normalisation Unicode (NFKC) + collapse des espaces.
    3. Deduplication par ``uid``.
    4. Verification metier (region, fraicheur).
    5. Construction du texte enrichi pour embedding + metadonnees.
"""

from __future__ import annotations

import logging
import re
import unicodedata
import warnings
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from langchain_core.documents import Document

from pulsevents_rag.config import Settings

logger = logging.getLogger(__name__)

# BeautifulSoup warn quand une description courte ressemble a un chemin/URL
# (faux positif sur les descriptions Open Agenda de type "Voir https://...").
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)


# ---------------------------------------------------------------------------
# Nettoyage texte
# ---------------------------------------------------------------------------


def clean_html(text: Optional[str]) -> str:
    """Retire balises HTML et entites, en preservant le texte lisible.

    Args:
        text: contenu potentiellement HTML.

    Returns:
        Texte nettoye (chaine vide si input ``None`` ou vide).

    Examples:
        >>> clean_html("<p>Bonjour <b>Nantes</b> !</p>")
        'Bonjour Nantes !'
    """
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def normalize_text(text: str) -> str:
    """Normalise Unicode (NFKC) + collapse les espaces multiples."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def strip_accents_lower(text: Optional[str]) -> str:
    """Minuscule sans accents, pour des comparaisons robustes de mots-cles."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _as_list(value) -> list:
    """Coerce une valeur en liste Python.

    Robuste aux types renvoyes selon la source :
    - JSON brut -> list Python ;
    - parquet (pyarrow) -> numpy.ndarray ;
    - cellule vide -> None ou NaN (float).

    Evite le piege ``ndarray or []`` qui leve
    "truth value of an array with more than one element is ambiguous".
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if hasattr(value, "tolist"):  # numpy.ndarray
        return list(value.tolist())
    try:
        if pd.isna(value):  # scalaire NaN uniquement (les arrays sont deja traites)
            return []
    except (TypeError, ValueError):
        pass
    return [value]


# ---------------------------------------------------------------------------
# Filtrage metier
# ---------------------------------------------------------------------------


def filter_recency_and_region(df: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Conserve les evenements correspondant aux filtres metier.

    Double-check cote Python pour ne PAS dependre uniquement du filtre API.
    Ce filtre est verifie par les tests unitaires.

    Args:
        df: DataFrame brute d'Open Agenda.
        settings: configuration (region, time_mode, since_days, dept, city).

    Returns:
        DataFrame filtree.
    """
    if df.empty:
        return df

    df = df.copy()
    df["firstdate_begin_dt"] = pd.to_datetime(df["firstdate_begin"], errors="coerce", utc=True)
    df["lastdate_end_dt"] = pd.to_datetime(df["lastdate_end"], errors="coerce", utc=True)

    now = datetime.now(timezone.utc)
    mode = settings.filters.time_mode

    if mode == "upcoming":
        upper = now + timedelta(days=365)
        time_mask = (df["lastdate_end_dt"] >= now) & (df["firstdate_begin_dt"] <= upper)
    elif mode == "historical":
        threshold = now - timedelta(days=settings.filters.since_days)
        time_mask = df["firstdate_begin_dt"] >= threshold
    else:
        raise ValueError(f"time_mode invalide : {mode!r}")

    mask = (df["location_region"] == settings.filters.region) & time_mask
    if settings.filters.department:
        mask &= df["location_department"] == settings.filters.department
    if settings.filters.city:
        mask &= df["location_city"] == settings.filters.city

    filtered = df[mask].copy()
    logger.info(
        "Filtrage metier (%s) : %d -> %d evenements (region=%s)",
        mode, len(df), len(filtered), settings.filters.region,
    )
    return filtered


def filter_noise(df: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Retire les events non culturels (emploi, formation, administratif).

    Open Agenda agrege des contributeurs heterogenes : France Travail
    (job dating, forum emploi), formations (LinkedIn, Digital Learning),
    administratif (mutuelle, indemnisation). Ces "evenements" polluent le
    retrieval. On les exclut via :
    - mots-cles dans le titre (``exclude_title_keywords``) ;
    - contributeur d'origine (``exclude_agendas`` sur ``originagenda_title``).

    Comparaison insensible aux accents et a la casse.
    """
    kws = [strip_accents_lower(k) for k in settings.preprocessing.exclude_title_keywords]
    agendas = [strip_accents_lower(a) for a in settings.preprocessing.exclude_agendas]
    if df.empty or (not kws and not agendas):
        return df

    df = df.copy()
    title_norm = df["title_fr"].map(strip_accents_lower)
    agenda_col = df["originagenda_title"] if "originagenda_title" in df.columns else None
    agenda_norm = agenda_col.map(strip_accents_lower) if agenda_col is not None else None

    def _kw_hit(t: str) -> bool:
        return any(k in t for k in kws)

    mask_noise = title_norm.map(_kw_hit)
    if agenda_norm is not None and agendas:
        mask_noise = mask_noise | agenda_norm.map(lambda a: any(x in a for x in agendas))

    kept = df[~mask_noise].copy()
    logger.info(
        "Filtre anti-bruit : %d -> %d evenements (%d events emploi/formation/admin retires)",
        len(df), len(kept), int(mask_noise.sum()),
    )
    return kept


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplique par ``uid`` (clef stable Open Agenda)."""
    if "uid" not in df.columns or df.empty:
        return df
    before = len(df)
    df = df.drop_duplicates(subset="uid", keep="first").copy()
    logger.info("Deduplication : %d -> %d", before, len(df))
    return df


# ---------------------------------------------------------------------------
# Construction des Documents LangChain
# ---------------------------------------------------------------------------


def build_document_text(row: pd.Series) -> str:
    """Concatene les champs utiles d'un evenement en un texte enrichi.

    Inclut titre, plage de dates (humaine + ISO), lieu, ville, departement,
    mots-cles et description longue. Les dates ISO permettent au LLM de
    comparer rigoureusement avec la date du jour ("ce week-end", etc.).
    """
    title = normalize_text(row.get("title_fr") or "")
    description = normalize_text(clean_html(row.get("longdescription_fr") or row.get("description_fr") or ""))
    daterange = normalize_text(row.get("daterange_fr") or "")
    fdb = str(row.get("firstdate_begin") or "")[:10]  # YYYY-MM-DD
    lde = str(row.get("lastdate_end") or "")[:10]
    place = normalize_text(row.get("location_name") or "")
    city = normalize_text(row.get("location_city") or "")
    dept = normalize_text(row.get("location_department") or "")
    keywords = _as_list(row.get("keywords_fr"))
    keywords_str = ", ".join(normalize_text(str(k)) for k in keywords if k)

    parts = [
        f"Titre : {title}",
        f"Quand : {daterange}" if daterange else "",
        f"Date debut (ISO) : {fdb}" if fdb else "",
        f"Date fin (ISO) : {lde}" if lde else "",
        f"Lieu : {place}" + (f" ({city}, {dept})" if city or dept else ""),
        f"Mots-cles : {keywords_str}" if keywords_str else "",
        "Description :",
        description,
    ]
    return "\n".join(p for p in parts if p)


def build_metadata(row: pd.Series) -> dict:
    """Metadonnees attachees au document (servent a citer la source)."""
    return {
        "uid": row.get("uid"),
        "title": normalize_text(row.get("title_fr") or ""),
        "city": normalize_text(row.get("location_city") or ""),
        "department": normalize_text(row.get("location_department") or ""),
        "region": normalize_text(row.get("location_region") or ""),
        "firstdate_begin": str(row.get("firstdate_begin") or ""),
        "lastdate_end": str(row.get("lastdate_end") or ""),
        "url": row.get("canonicalurl") or "",
        "daterange": normalize_text(row.get("daterange_fr") or ""),
    }


def to_documents(df: pd.DataFrame, min_description_length: int = 30) -> list[Document]:
    """Convertit la DataFrame nettoyee en liste de ``Document`` LangChain.

    Filtre les evenements dont la description nettoyee est trop courte
    (sinon l'embedding est pauvre).
    """
    documents: list[Document] = []
    skipped = 0
    for _, row in df.iterrows():
        text = build_document_text(row)
        # On verifie la qualite via la description seule, pas via le texte complet
        desc_only = normalize_text(clean_html(row.get("longdescription_fr") or row.get("description_fr") or ""))
        if len(desc_only) < min_description_length:
            skipped += 1
            continue
        documents.append(Document(page_content=text, metadata=build_metadata(row)))
    logger.info("Construction documents : %d retenus, %d ignores (description trop courte)", len(documents), skipped)
    return documents


# ---------------------------------------------------------------------------
# Pipeline complet
# ---------------------------------------------------------------------------


def run_preprocessing(df: pd.DataFrame, settings: Settings) -> tuple[pd.DataFrame, list[Document]]:
    """Enchaine deduplication -> filtrage metier -> filtre bruit -> Documents.

    Returns:
        Tuple ``(dataframe_clean, documents)``.
    """
    df = dedupe(df)
    df = filter_recency_and_region(df, settings)
    df = filter_noise(df, settings)
    docs = to_documents(df, settings.preprocessing.min_description_length)
    return df, docs
