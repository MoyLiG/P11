"""Ingestion des evenements depuis Open Agenda (via Opendatasoft).

L'API Opendatasoft v2.1 expose un endpoint ``/records`` paginee, avec un filtre
ODSQL ``where=`` puissant. On filtre :

- region (obligatoire) ;
- departement / ville (optionnels) ;
- date de debut >= aujourd'hui - N jours.

Les resultats sont sauvegardes en JSON brut dans ``data/raw/`` puis renvoyes
sous forme de DataFrame.

Reference API : https://help.opendatasoft.com/apis/ods-explore-v2/
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

import pandas as pd
import requests
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pulsevents_rag.config import Settings

logger = logging.getLogger(__name__)

# Limite hard de l'endpoint /records (Opendatasoft v2.1) :
# offset + limit <= 10 000. Au-dela on recoit HTTP 400.
# Pour aller plus loin, on bascule sur l'endpoint /exports/json (streaming).
OPENDATASOFT_RECORDS_LIMIT = 10_000


# ---------------------------------------------------------------------------
# Construction de la clause where ODSQL
# ---------------------------------------------------------------------------


def build_where_clause(
    region: str,
    since_days: int,
    department: Optional[str] = None,
    city: Optional[str] = None,
    time_mode: str = "upcoming",
) -> str:
    """Compose la clause ``where=`` ODSQL pour Opendatasoft.

    Args:
        region: nom de la region (ex. "Pays de la Loire").
        since_days: nb de jours de profondeur (utilise en mode historical).
        department: departement optionnel.
        city: ville optionnelle.
        time_mode: "upcoming" (a venir / en cours) ou "historical" (< since_days).

    Returns:
        Chaine ODSQL.

    Examples:
        upcoming :  location_region="Pays de la Loire" AND lastdate_end >= "2026-05-20"
                    AND firstdate_begin <= "2027-05-20"
        historical: location_region="Pays de la Loire" AND firstdate_begin >= "2025-05-20"
    """
    today = datetime.now(timezone.utc).date()
    parts = [f'location_region="{region}"']

    if time_mode == "upcoming":
        # Events qui se terminent aujourd'hui ou plus tard
        # ET qui ne commencent pas dans plus d'un an
        parts.append(f'lastdate_end >= "{today.isoformat()}"')
        upper = (today + timedelta(days=365)).isoformat()
        parts.append(f'firstdate_begin <= "{upper}"')
    elif time_mode == "historical":
        threshold = (today - timedelta(days=since_days)).isoformat()
        parts.append(f'firstdate_begin >= "{threshold}"')
    else:
        raise ValueError(
            f"time_mode invalide : {time_mode!r}. Attendu 'upcoming' ou 'historical'."
        )

    if department:
        parts.append(f'location_department="{department}"')
    if city:
        parts.append(f'location_city="{city}"')
    return " AND ".join(parts)


# ---------------------------------------------------------------------------
# Appel HTTP avec retry
# ---------------------------------------------------------------------------


@retry(
    retry=retry_if_exception_type((requests.RequestException,)),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(4),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _request_page(
    base_url: str,
    where: str,
    limit: int,
    offset: int,
    timeout: int,
) -> dict:
    """Recupere une page de resultats avec retry exponentiel sur erreur reseau."""
    params = {
        "where": where,
        "limit": limit,
        "offset": offset,
        "order_by": "firstdate_begin",
    }
    resp = requests.get(base_url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def _iter_records(settings: Settings) -> Iterator[dict]:
    """Itere sur les records via l'endpoint /records (paginate).

    Plafonne automatiquement a ``OPENDATASOFT_RECORDS_LIMIT`` (10 000).
    Au-dela, utiliser ``_iter_records_export`` (endpoint /exports/json).
    """
    where = build_where_clause(
        region=settings.filters.region,
        since_days=settings.filters.since_days,
        department=settings.filters.department,
        city=settings.filters.city,
        time_mode=settings.filters.time_mode,
    )
    logger.info("Filtre ODSQL : %s", where)

    # Plafonnage : l'API /records refuse offset + limit > 10 000 (HTTP 400).
    requested = settings.filters.max_records
    max_records = min(requested, OPENDATASOFT_RECORDS_LIMIT)
    if max_records < requested:
        logger.warning(
            "max_records=%d plafonne a %d (limite Opendatasoft /records). "
            "Pour aller plus loin, basculer sur fetch_open_agenda(use_export=True).",
            requested, max_records,
        )

    fetched = 0
    offset = 0
    page_size = settings.data_source.page_size

    while fetched < max_records:
        limit = min(page_size, max_records - fetched)
        # Sanity check : on ne demande JAMAIS offset+limit > 10 000.
        if offset + limit > OPENDATASOFT_RECORDS_LIMIT:
            limit = OPENDATASOFT_RECORDS_LIMIT - offset
            if limit <= 0:
                break
        page = _request_page(
            base_url=settings.data_source.base_url,
            where=where,
            limit=limit,
            offset=offset,
            timeout=settings.data_source.request_timeout_s,
        )
        records = page.get("results", [])
        total = page.get("total_count", 0)
        if offset == 0:
            logger.info("Total disponible cote API : %d enregistrements", total)
        if not records:
            break
        for rec in records:
            yield rec
        fetched += len(records)
        offset += len(records)
        time.sleep(0.2)  # courtoisie API
        if len(records) < limit:
            break

    logger.info("Recuperation /records terminee : %d enregistrements", fetched)


def _iter_records_export(settings: Settings) -> Iterator[dict]:
    """Itere via /exports/json - pas de limite d'offset.

    Plus lent (le serveur prepare le dump complet) mais permet de
    recuperer l'integralite des resultats meme au-dela de 10 000.
    """
    where = build_where_clause(
        region=settings.filters.region,
        since_days=settings.filters.since_days,
        department=settings.filters.department,
        city=settings.filters.city,
        time_mode=settings.filters.time_mode,
    )
    logger.info("Filtre ODSQL (export) : %s", where)

    # On derive l'URL d'export depuis l'URL de records.
    export_url = settings.data_source.base_url.replace("/records", "/exports/json")
    params = {
        "where": where,
        "limit": settings.filters.max_records,  # /exports accepte large
        "order_by": "firstdate_begin",
    }
    resp = requests.get(
        export_url, params=params,
        timeout=settings.data_source.request_timeout_s * 4,  # plus tolerant
        stream=False,
    )
    resp.raise_for_status()
    records = resp.json()
    logger.info("Recuperation /exports/json terminee : %d enregistrements",
                len(records))
    for r in records:
        yield r


# ---------------------------------------------------------------------------
# Entree publique
# ---------------------------------------------------------------------------


def fetch_open_agenda(
    settings: Settings,
    save_raw: bool = True,
    use_export: bool | None = None,
) -> pd.DataFrame:
    """Recupere les evenements Open Agenda selon la configuration.

    Args:
        settings: configuration projet chargee.
        save_raw: si True, sauvegarde le JSON brut dans ``data/raw/events.json``.
        use_export: si True, utilise /exports/json (pas de limite offset).
            Si None (defaut), bascule automatiquement sur /exports/json
            quand ``settings.filters.max_records`` > 10 000.

    Returns:
        DataFrame pandas des evenements (un par ligne).

    Raises:
        requests.HTTPError: si l'API renvoie une erreur apres tous les retries.
    """
    if use_export is None:
        use_export = settings.filters.max_records > OPENDATASOFT_RECORDS_LIMIT
    iterator = _iter_records_export if use_export else _iter_records
    if use_export:
        logger.info("Mode export active (max_records=%d > %d).",
                    settings.filters.max_records, OPENDATASOFT_RECORDS_LIMIT)
    records = list(iterator(settings))
    df = pd.DataFrame.from_records(records)

    if save_raw:
        out_dir = settings.resolved_path(settings.paths.raw_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "events.json"
        out_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("JSON brut sauvegarde -> %s", out_path)

    return df


def load_raw_events(settings: Settings) -> pd.DataFrame:
    """Recharge le dump JSON deja telecharge (pour eviter de retaper l'API)."""
    path: Path = settings.resolved_path(settings.paths.raw_dir) / "events.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Aucun dump trouve a {path}. Lance d'abord scripts/01_fetch_data.py"
        )
    records = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame.from_records(records)
