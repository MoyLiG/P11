# =====================================================================
# Dockerfile - POC RAG Puls-Events
# Base : Python 3.12 slim (Debian bookworm)
# - Compatibilite langchain 0.3 / faiss-cpu / mistralai
# - Utilisateur non-root pour la securite (cf. SECURITY.md)
# - Image finale ~600 Mo (slim + wheels CPU)
# =====================================================================

FROM python:3.12-slim AS base

# Variables Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

# Dependances systeme minimales (libgomp1 requis par faiss-cpu)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Utilisateur non-root (UID/GID stables pour les volumes)
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash app

WORKDIR /app
# WORKDIR cree /app en root ; on transfere a app pour que pytest puisse
# y ecrire son cache et que les volumes data/ soient writables.
RUN chown -R app:app /app

# Copie isolee de requirements pour profiter du cache Docker
COPY --chown=app:app requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copie du code (apres les deps pour optimiser le rebuild)
COPY --chown=app:app . .

# Healthcheck Streamlit (endpoint /_stcore/health)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

USER app

EXPOSE 8501

# Par defaut on lance Streamlit. Pour les autres commandes :
#   docker compose run --rm rag python scripts/pipeline.py
#   docker compose run --rm rag pytest -v
CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
