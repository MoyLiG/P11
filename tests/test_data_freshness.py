"""Tests de fraicheur des donnees.

Verifie selon le ``time_mode`` configure :
- ``upcoming`` : tous les events doivent etre a venir ou en cours
  (``lastdate_end >= today``) ET commencer dans l'annee (`firstdate_begin <= today+365j`).
- ``historical`` : tous les events doivent etre < ``since_days`` jours
  (``firstdate_begin >= today - since_days``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from pulsevents_rag.preprocessing import filter_recency_and_region


def _check_time_filter(df: pd.DataFrame, settings) -> None:
    """Verifie que la dataframe respecte le filtre temporel courant."""
    if df.empty:
        return
    df = df.copy()
    df["first_dt"] = pd.to_datetime(df["firstdate_begin"], errors="coerce", utc=True)
    df["last_dt"] = pd.to_datetime(df["lastdate_end"], errors="coerce", utc=True)
    now = datetime.now(timezone.utc)
    mode = settings.filters.time_mode
    if mode == "upcoming":
        upper = now + timedelta(days=365)
        bad = df[(df["last_dt"] < now) | (df["first_dt"] > upper)]
        assert bad.empty, (
            f"[upcoming] {len(bad)} events ne sont pas dans la fenetre "
            f"(lastdate_end >= today AND firstdate_begin <= today+365j) : "
            f"{bad['uid'].head(3).tolist()}"
        )
    elif mode == "historical":
        threshold = now - timedelta(days=settings.filters.since_days)
        bad = df[df["first_dt"] < threshold]
        assert bad.empty, (
            f"[historical] {len(bad)} events plus vieux que "
            f"{settings.filters.since_days} jours : {bad['uid'].head(3).tolist()}"
        )
    else:
        raise AssertionError(f"time_mode inattendu : {mode}")


def test_old_events_are_filtered(sample_events, settings):
    """Le filtrage doit retirer tout event hors fenetre temporelle."""
    out = filter_recency_and_region(sample_events, settings)
    _check_time_filter(out, settings)


def test_freshness_in_real_dump(raw_events_if_exists, settings):
    """Sur le dump reel : tous les events doivent respecter le mode courant."""
    df = filter_recency_and_region(raw_events_if_exists, settings)
    _check_time_filter(df, settings)
