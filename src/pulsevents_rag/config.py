"""Chargement centralise de la configuration du projet.

La configuration vient de deux sources :
- ``config.yaml`` (parametres metier, modeles, chemins)
- ``.env`` (secrets, en particulier MISTRAL_API_KEY)

Usage :
    >>> from pulsevents_rag.config import load_settings
    >>> settings = load_settings()
    >>> settings.filters.region
    'Pays de la Loire'
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Schemas de configuration
# ---------------------------------------------------------------------------


class DataSourceConfig(BaseModel):
    base_url: str
    page_size: int = Field(default=100, ge=1, le=100)
    request_timeout_s: int = 30
    retry_attempts: int = 4
    retry_initial_wait_s: int = 1


class FiltersConfig(BaseModel):
    region: str
    department: Optional[str] = None
    city: Optional[str] = None
    since_days: int = Field(default=365, ge=1)
    max_records: int = Field(default=5000, ge=1)
    time_mode: str = "upcoming"  # "upcoming" (a venir + en cours) | "historical" (< since_days)


class PreprocessingConfig(BaseModel):
    min_description_length: int = 30
    exclude_title_keywords: list[str] = []  # events exclus si le titre contient un de ces termes
    exclude_agendas: list[str] = []         # exclus si originagenda_title contient un de ces termes


class ChunkingConfig(BaseModel):
    chunk_size: int = 800
    chunk_overlap: int = 120


class ModelsConfig(BaseModel):
    embedding_model: str = "mistral-embed"
    llm_model: str = "mistral-small-latest"
    llm_temperature: float = 0.2
    embedding_batch_size: int = 24
    embedding_min_interval_s: float = 1.1  # tier gratuit ; 0.3 pour Pro


class RetrievalConfig(BaseModel):
    search_type: str = "mmr"
    k: int = 6
    fetch_k: int = 18
    max_question_length: int = 500
    max_answer_tokens: int = 400
    use_hybrid: bool = True        # active EnsembleRetriever BM25 + dense
    bm25_weight: float = Field(default=0.4, ge=0.0, le=1.0)


class PathsConfig(BaseModel):
    raw_dir: str = "data/raw"
    processed_dir: str = "data/processed"
    vectorstore_dir: str = "data/vectorstore"
    eval_dataset: str = "data/eval/qa_dataset.json"
    eval_results: str = "data/eval/results.csv"


class Settings(BaseModel):
    data_source: DataSourceConfig
    filters: FiltersConfig
    preprocessing: PreprocessingConfig
    chunking: ChunkingConfig
    models: ModelsConfig
    retrieval: RetrievalConfig
    paths: PathsConfig
    mistral_api_key: Optional[str] = None
    project_root: Path

    def resolved_path(self, relative: str) -> Path:
        """Resout un chemin relatif depuis la racine du projet."""
        return (self.project_root / relative).resolve()


# ---------------------------------------------------------------------------
# Chargement
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    """Racine du projet = parent du dossier ``src``."""
    return Path(__file__).resolve().parents[2]


def load_settings(config_path: Optional[Path] = None) -> Settings:
    """Charge ``config.yaml`` et merge la cle API depuis l'environnement.

    Args:
        config_path: chemin optionnel vers un YAML ; defaut = ``config.yaml``
            a la racine du projet.

    Returns:
        Instance ``Settings`` validee par pydantic.

    Raises:
        FileNotFoundError: si le YAML n'existe pas.
        pydantic.ValidationError: si le YAML est mal forme.
    """
    root = _project_root()
    load_dotenv(root / ".env", override=False)

    cfg_path = (
        Path(config_path)
        if config_path
        else Path(os.environ.get("PULSEVENTS_CONFIG", root / "config.yaml"))
    )
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path

    if not cfg_path.exists():
        raise FileNotFoundError(f"Fichier de configuration introuvable : {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    raw["project_root"] = root
    raw["mistral_api_key"] = os.environ.get("MISTRAL_API_KEY")
    return Settings.model_validate(raw)
