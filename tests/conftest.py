"""Fixtures pytest pour le POC RAG.

On expose deux datasets :
- ``sample_events`` : 5 evenements synthetiques (test reproductible, sans I/O).
- ``raw_events`` : le dump JSON reel s'il existe, sinon skip.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

# Ajoute src/ au path pour pouvoir importer pulsevents_rag sans installer le package
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pulsevents_rag.config import load_settings  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    """Configuration projet chargee depuis config.yaml."""
    return load_settings()


@pytest.fixture
def sample_events() -> pd.DataFrame:
    """Echantillon synthetique : 4 events valides + 1 hors-region.

    Les dates sont calculees relativement a maintenant pour que le test
    reste valide dans le temps.
    """
    now = datetime.now(timezone.utc)
    rows = [
        {
            "uid": "evt-001",
            "title_fr": "La Folle Journee de Nantes",
            "longdescription_fr": "<p>Festival de musique classique a la Cite des Congres.</p>",
            "daterange_fr": "Du 30 janvier au 2 fevrier 2026",
            "firstdate_begin": (now - timedelta(days=10)).isoformat(),
            "lastdate_end": (now + timedelta(days=5)).isoformat(),
            "location_name": "Cite des Congres",
            "location_city": "Nantes",
            "location_department": "Loire-Atlantique",
            "location_region": "Pays de la Loire",
            "keywords_fr": ["musique", "classique", "festival"],
            "canonicalurl": "https://openagenda.com/folle-journee",
        },
        {
            "uid": "evt-002",
            "title_fr": "Voyage a Nantes",
            "longdescription_fr": "Parcours d'art contemporain en ville.",
            "daterange_fr": "Du 1 juillet au 31 aout",
            "firstdate_begin": (now - timedelta(days=200)).isoformat(),
            "lastdate_end": (now - timedelta(days=120)).isoformat(),
            "location_name": "Centre-ville",
            "location_city": "Nantes",
            "location_department": "Loire-Atlantique",
            "location_region": "Pays de la Loire",
            "keywords_fr": ["art", "contemporain"],
            "canonicalurl": "https://openagenda.com/vaan",
        },
        {
            "uid": "evt-003",
            "title_fr": "Festival Les Escales",
            "longdescription_fr": "Musiques du monde a Saint-Nazaire.",
            "daterange_fr": "Du 1 au 3 aout",
            "firstdate_begin": (now - timedelta(days=300)).isoformat(),
            "lastdate_end": (now - timedelta(days=297)).isoformat(),
            "location_name": "Port",
            "location_city": "Saint-Nazaire",
            "location_department": "Loire-Atlantique",
            "location_region": "Pays de la Loire",
            "keywords_fr": ["musique", "monde"],
            "canonicalurl": "https://openagenda.com/escales",
        },
        {
            "uid": "evt-004",
            "title_fr": "Festival d'Anjou",
            "longdescription_fr": "Theatre en plein air dans des chateaux du Maine-et-Loire.",
            "daterange_fr": "Juin / juillet",
            "firstdate_begin": (now - timedelta(days=20)).isoformat(),
            "lastdate_end": (now + timedelta(days=10)).isoformat(),
            "location_name": "Divers chateaux",
            "location_city": "Angers",
            "location_department": "Maine-et-Loire",
            "location_region": "Pays de la Loire",
            "keywords_fr": ["theatre", "festival"],
            "canonicalurl": "https://openagenda.com/anjou",
        },
        {
            "uid": "evt-005",
            "title_fr": "Concert hors region",
            "longdescription_fr": "Devrait etre filtre car region != Pays de la Loire.",
            "daterange_fr": "Mai",
            "firstdate_begin": (now - timedelta(days=5)).isoformat(),
            "lastdate_end": (now - timedelta(days=4)).isoformat(),
            "location_name": "Salle X",
            "location_city": "Lyon",
            "location_department": "Rhone",
            "location_region": "Auvergne-Rhone-Alpes",
            "keywords_fr": ["musique"],
            "canonicalurl": "https://openagenda.com/lyon",
        },
        {
            "uid": "evt-006",
            "title_fr": "Vieil evenement Pays de la Loire",
            "longdescription_fr": "Devrait etre filtre car > 1 an.",
            "daterange_fr": "Janvier 2024",
            "firstdate_begin": (now - timedelta(days=500)).isoformat(),
            "lastdate_end": (now - timedelta(days=499)).isoformat(),
            "location_name": "Theatre",
            "location_city": "Le Mans",
            "location_department": "Sarthe",
            "location_region": "Pays de la Loire",
            "keywords_fr": ["theatre"],
            "canonicalurl": "https://openagenda.com/old",
        },
    ]
    return pd.DataFrame.from_records(rows)


@pytest.fixture
def raw_events_if_exists(settings) -> pd.DataFrame:
    """Charge le dump reel s'il existe ; skip sinon."""
    path = settings.resolved_path(settings.paths.raw_dir) / "events.json"
    if not path.exists():
        pytest.skip(f"Pas de dump reel ({path}) - lance scripts/01_fetch_data.py d'abord.")
    return pd.DataFrame.from_records(json.loads(path.read_text(encoding="utf-8")))
