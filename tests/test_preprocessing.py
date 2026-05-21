"""Tests unitaires des fonctions de pre-processing."""

from __future__ import annotations

import pandas as pd

from pulsevents_rag.preprocessing import (
    build_document_text,
    clean_html,
    dedupe,
    filter_noise,
    normalize_text,
    strip_accents_lower,
    to_documents,
)


def test_clean_html_strips_tags():
    assert clean_html("<p>Bonjour <b>Nantes</b> !</p>") == "Bonjour Nantes !"


def test_clean_html_handles_none_and_empty():
    assert clean_html(None) == ""
    assert clean_html("") == ""


def test_normalize_text_collapses_spaces():
    assert normalize_text("  hello\n\n  world  ") == "hello world"


def test_dedupe_keeps_first_occurrence():
    df = pd.DataFrame(
        [
            {"uid": "a", "title_fr": "T1"},
            {"uid": "a", "title_fr": "T1-bis"},
            {"uid": "b", "title_fr": "T2"},
        ]
    )
    out = dedupe(df)
    assert len(out) == 2
    assert set(out["uid"]) == {"a", "b"}
    assert out.iloc[0]["title_fr"] == "T1"


def test_build_document_text_includes_main_fields(sample_events):
    row = sample_events.iloc[0]
    text = build_document_text(row)
    assert "La Folle Journee" in text
    assert "Nantes" in text
    assert "Description" in text
    # Pas de balises HTML residuelles
    assert "<p>" not in text


def test_strip_accents_lower():
    assert strip_accents_lower("Évènement Théâtre") == "evenement theatre"
    assert strip_accents_lower(None) == ""


def test_filter_noise_removes_employment_events(settings):
    """Le filtre anti-bruit retire les events emploi/formation/admin."""
    df = pd.DataFrame(
        [
            {"uid": "1", "title_fr": "Concert Bouskidou Symphonique", "originagenda_title": "Ville de Saint-Nazaire"},
            {"uid": "2", "title_fr": "Job dating - Metiers du soin", "originagenda_title": "France Travail"},
            {"uid": "3", "title_fr": "Comment choisir ma mutuelle ?", "originagenda_title": "Nantes Metropole"},
            {"uid": "4", "title_fr": "Exposition d'art contemporain", "originagenda_title": "FRAC"},
            {"uid": "5", "title_fr": "Forum emploi industrie", "originagenda_title": "France Travail"},
        ]
    )
    out = filter_noise(df, settings)
    kept = set(out["uid"])
    assert kept == {"1", "4"}, f"Attendu {{1,4}} (events culturels), recu {kept}"


def test_filter_noise_is_accent_insensitive(settings):
    """Le filtre matche meme avec accents/casse differents."""
    df = pd.DataFrame(
        [
            {"uid": "a", "title_fr": "JOB DATING special alternance", "originagenda_title": ""},
            {"uid": "b", "title_fr": "Récital d'orgue", "originagenda_title": ""},
        ]
    )
    out = filter_noise(df, settings)
    assert set(out["uid"]) == {"b"}


def test_build_document_text_handles_numpy_keywords():
    """Regression : keywords_fr en numpy.ndarray (cas parquet) ne doit pas crasher.

    Bug historique : `ndarray or []` levait
    "truth value of an array with more than one element is ambiguous".
    """
    import numpy as np

    row = pd.Series(
        {
            "title_fr": "Concert",
            "longdescription_fr": "Description suffisamment longue pour le test.",
            "keywords_fr": np.array(["musique", "concert", "live"]),
            "location_city": "Nantes",
        }
    )
    text = build_document_text(row)  # ne doit pas lever
    assert "musique, concert, live" in text


def test_to_documents_skips_short_descriptions(sample_events):
    # On force une description tres courte sur le 1er event
    df = sample_events.copy()
    df.loc[df.index[0], "longdescription_fr"] = "ok"
    df.loc[df.index[0], "description_fr"] = "ok"
    docs = to_documents(df, min_description_length=30)
    # 6 lignes initiales, mais celle a "ok" doit etre filtree
    titles = [d.metadata["title"] for d in docs]
    assert "La Folle Journee de Nantes" not in titles
