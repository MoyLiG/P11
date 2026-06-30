"""Tests geographiques - consigne du projet : region selectionnee uniquement.

Verifie que :
- les events hors-region sont filtres ;
- en cas de dump reel, 100 % des lignes ont la region attendue.
"""

from __future__ import annotations

from pulsevents_rag.preprocessing import filter_recency_and_region


def test_out_of_region_events_are_filtered(sample_events, settings):
    """Les events de region != settings.filters.region doivent disparaitre."""
    out = filter_recency_and_region(sample_events, settings)
    assert (out["location_region"] == settings.filters.region).all(), (
        "Au moins un evenement hors-region a passe le filtre."
    )
    assert "evt-005" not in set(out["uid"]), (
        "L'evenement Lyon (Auvergne-Rhone-Alpes) n'aurait pas du passer."
    )


def test_real_dump_is_in_region(raw_events_if_exists, settings):
    """Sur le dump reel : tous les evenements doivent etre dans la region cible."""
    df = filter_recency_and_region(raw_events_if_exists, settings)
    if df.empty:
        return
    bad = df[df["location_region"] != settings.filters.region]
    assert bad.empty, (
        f"{len(bad)} evenements hors region '{settings.filters.region}' detectes : "
        f"{bad['location_region'].unique().tolist()}"
    )


def test_optional_department_filter(sample_events, settings, monkeypatch):
    """Si department est specifie, le filtrage est plus strict."""
    # On copie les filtres et force department=Loire-Atlantique
    new_filters = settings.filters.model_copy(update={"department": "Loire-Atlantique"})
    new_settings = settings.model_copy(update={"filters": new_filters})

    out = filter_recency_and_region(sample_events, new_settings)
    assert (out["location_department"] == "Loire-Atlantique").all()
    # Le festival d'Anjou (Maine-et-Loire) doit disparaitre
    assert "evt-004" not in set(out["uid"])
