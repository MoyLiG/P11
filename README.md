# POC RAG Puls-Events

> Proof of Concept d'un chatbot RAG (Retrieval-Augmented Generation) sur les
> événements culturels publics d'**Open Agenda**, restreints à la région
> **Pays de la Loire** et aux **événements de moins d'un an**.
> Stack imposée : **LangChain + Mistral + FAISS**.

---

## Table des matières

1. [Contexte](#contexte)
2. [Architecture](#architecture)
3. [Arborescence](#arborescence)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Utilisation](#utilisation)
7. [Tests](#tests)
8. [Évaluation](#évaluation)
9. [Livrables](#livrables-projet-oc)
10. [FAQ technique](#faq-technique)

---

## Contexte

L'entreprise **Puls-Events** propose une plateforme de découverte d'événements
culturels. Elle souhaite tester un chatbot capable de répondre en langage
naturel à des questions du type *« Quels concerts à Nantes ce mois-ci ? »* en
s'appuyant sur les données Open Agenda.

Le POC démontre la faisabilité avec :

- **Source** : dataset Opendatasoft `evenements-publics-openagenda` (1,1 M+
  enregistrements au catalogue, accès ouvert sans clé).
- **Périmètre** : région Pays de la Loire, événements dont la date de début
  est dans les 365 derniers jours.
- **Embeddings** : `mistral-embed` (1024 dimensions).
- **LLM** : `mistral-small-latest` (température 0.2).
- **Vector store** : FAISS local (`IndexFlatL2`).
- **Orchestration** : LangChain (`create_retrieval_chain` + MMR retriever).
- **Démo** : CLI Python + app Streamlit.

---

## Architecture

```
                           ┌────────────────────────┐
   Open Agenda             │  Opendatasoft API v2.1 │
   (Opendatasoft)          └───────────┬────────────┘
                                       │ filtres ODSQL
                                       ▼
                         ┌──────────────────────────┐
                         │   ingestion.py           │
                         │  pagination + retry      │
                         └───────────┬──────────────┘
                                     │ data/raw/events.json
                                     ▼
                         ┌──────────────────────────┐
                         │ preprocessing.py         │
                         │  - clean HTML            │
                         │  - dedupe (uid)          │
                         │  - filtre region+date    │
                         │  - build Documents       │
                         └───────────┬──────────────┘
                                     │ List[Document]
                                     ▼
                         ┌──────────────────────────┐
                         │ vectorstore.py           │
                         │  RecursiveSplitter       │
                         │  → MistralAIEmbeddings   │
                         │  → FAISS.from_documents  │
                         │  → save_local            │
                         └───────────┬──────────────┘
                                     │ data/vectorstore/{index.faiss,index.pkl}
                                     ▼
   Question utilisateur   ┌──────────────────────────┐
   ───────────────────►   │ rag.py (RagPipeline)     │
                         │  - retriever MMR k=4     │
                         │  - prompt système FR     │
                         │  - ChatMistralAI         │
                         └───────────┬──────────────┘
                                     │ {answer, sources}
                                     ▼
                         ┌──────────────────────────┐
                         │ CLI / Streamlit          │
                         └──────────────────────────┘
```

---

## Arborescence

```
P11/
├── README.md                         ← ce fichier (livrable 1)
├── SECURITY.md                       ← modèle de menace + checklist pré-prod
├── requirements.txt                  ← dépendances pinnées
├── Dockerfile                        ← image reproductible (Python 3.12-slim)
├── docker-compose.yml                ← orchestration + volumes data persistants
├── .dockerignore
├── .env.example                      ← gabarit MISTRAL_API_KEY
├── .gitignore
├── config.yaml                       ← région, dates, modèles, hyperparamètres
│
├── src/pulsevents_rag/
│   ├── config.py                     ← chargement config + .env (pydantic)
│   ├── ingestion.py                  ← Open Agenda fetch + pagination + retry
│   ├── preprocessing.py              ← clean HTML, dedupe, filtre, build Documents
│   ├── vectorstore.py                ← FAISS + MistralAIEmbeddings
│   ├── rag.py                        ← chaîne LangChain + prompt + LLM
│   └── evaluation.py                 ← métriques (hit_rate, cosine, LLM-as-judge)
│
├── scripts/
│   ├── 01_fetch_data.py              ← télécharge → data/raw/events.json
│   ├── 02_build_index.py             ← preprocess + index FAISS → data/vectorstore/
│   ├── 03_run_chatbot_cli.py         ← CLI interactif
│   ├── 04_run_streamlit.py           ← lance l'app Streamlit
│   ├── 05_evaluate.py                ← évalue sur qa_dataset.json (--runs N)
│   ├── 06_debug_query.py             ← inspecte le retriever (debug)
│   ├── 07_eval_candidates.py         ← aide à l'annotation du jeu Q/R
│   └── pipeline.py                   ← orchestration end-to-end (fetch → tests → index)
│
├── app.py                            ← démo Streamlit
│
├── tests/
│   ├── conftest.py                   ← fixtures
│   ├── test_data_freshness.py        ← OBLIGATOIRE : events < 1 an
│   ├── test_data_geography.py        ← OBLIGATOIRE : région = Pays de la Loire
│   ├── test_preprocessing.py
│   ├── test_retriever.py
│   └── test_vectorstore.py
│
├── data/
│   ├── raw/                          ← dump JSON brut (gitignore)
│   ├── processed/                    ← parquet nettoyé (gitignore)
│   ├── vectorstore/                  ← FAISS index (gitignore)
│   └── eval/qa_dataset.json          ← 20 paires Q/R annotées (commitées)
│
└── docs/
    └── rapport_technique.docx        ← rapport technique (livrable 3)
```

> La présentation de soutenance est réalisée séparément et n'est pas versionnée dans ce dépôt.

---

## Installation

### Prérequis

- **Python 3.11 ou 3.12** (recommandé). Python 3.13/3.14 émet des avertissements
  de compatibilité avec Pydantic V1 utilisé en interne par LangChain.
- Une clé API Mistral. **`Le Chat Pro` ne donne PAS accès à l'API** : il faut
  créer un workspace gratuit sur [console.mistral.ai](https://console.mistral.ai)
  (plateforme « La Plateforme »), puis générer une clé.

> **Choix de l'environnement** — l'écosystème data engineering (LangChain,
> FAISS, Mistral SDK, déploiement Docker) est **Linux-first**. Sur Windows,
> la voie standard est WSL2 (Ubuntu). PowerShell fonctionne mais demande
> quelques aménagements. Docker rend la question caduque.

### Option A — WSL2 / Linux / macOS (recommandé)

```bash
# 1. Se placer dans le dossier (depuis WSL : /mnt/c/Users/moymo/OC/P11)
cd ~/projects/P11   # ou un mount adapte

# 2. Environnement virtuel
python3 -m venv .venv
source .venv/bin/activate

# 3. Dépendances
pip install --upgrade pip
pip install -r requirements.txt

# 4. Configuration de la clé API
cp .env.example .env
${EDITOR:-nano} .env   # renseigner MISTRAL_API_KEY
```

### Option B — Docker (zero install hors Docker Desktop)

C'est l'option la plus reproductible : tout le monde lance la même chose,
peu importe l'OS hôte. Recommandée pour la démo en soutenance et la prod.

```bash
# 1. Préparer la clé API
cp .env.example .env && ${EDITOR:-nano} .env

# 2. Build de l'image (premier run : ~3 min)
docker compose build

# 3. Construire l'index (one-shot, demande la clé Mistral)
docker compose run --rm rag python scripts/pipeline.py

# 4. Lancer la démo Streamlit
docker compose up rag
# → ouvrir http://localhost:8501
```

Tests dans le conteneur :

```bash
docker compose run --rm rag pytest tests/test_data_freshness.py \
                                   tests/test_data_geography.py \
                                   tests/test_preprocessing.py -v
```

#### Commandes Docker — aide-mémoire

| Commande | Rôle |
|---|---|
| `docker compose build` | Construit l'image (après modification du code) |
| `docker compose build --no-cache` | Rebuild complet (ignore le cache de couches) |
| `docker compose run --rm rag python scripts/pipeline.py` | Tâche ponctuelle : fetch + tests + index (container jetable) |
| `docker compose run --rm -it rag python scripts/03_run_chatbot_cli.py` | CLI interactif (`-it` requis) |
| `docker compose run --rm rag python scripts/05_evaluate.py --runs 3` | Évaluation multi-run |
| `docker compose up rag` | Démarre Streamlit (service, port 8501) |
| `docker compose stop` / `start` | Arrête / redémarre le container (le conserve) |
| `docker compose down` | Arrête **et supprime** container + réseau |
| `docker compose down --rmi local` | + supprime aussi l'image |
| `docker compose ps` | Liste les containers du projet |

#### Persistance : qu'est-ce qui survit aux arrêts ?

| Élément | `stop`→`start` | `down` | `down --rmi` |
|---|---|---|---|
| `./data/` (index FAISS, cache, dump, résultats) | ✅ | ✅ | ✅ |
| Filesystem interne du container | ✅ | ❌ | ❌ |
| État mémoire (session Streamlit, historique, compteur) | ❌ | ❌ | ❌ |
| Image `pulsevents-rag:latest` | ✅ | ✅ | ❌ |

**Pourquoi `./data/` survit à tout** : c'est un **bind mount** (dossier du
disque hôte branché dans le container, cf. `docker-compose.yml`). L'index
FAISS et le cache d'embeddings vivent sur ta machine, pas dans Docker —
donc même `docker compose down` ne les supprime pas. Au redémarrage,
Streamlit recharge l'index depuis `./data/vectorstore` (instantané, pas de
ré-indexation). Le seul état réellement perdu à chaque arrêt est la session
Streamlit en mémoire (historique de chat affiché, compteur de requêtes) —
ce qui est attendu, le POC étant volontairement stateless.

### Option C — Windows / PowerShell natif

Fonctionne mais demande quelques précautions (wheels `faiss-cpu`
disponibles uniquement pour Python 3.11/3.12 sous Windows ; activation
de venv différente).

```powershell
# 1. Cloner / se placer dans le dossier
cd C:\Users\moymo\OC\P11

# 2. Environnement virtuel (Python 3.11 ou 3.12 OBLIGATOIRE)
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Dépendances
pip install --upgrade pip
pip install -r requirements.txt

# 4. Configuration de la clé API
Copy-Item .env.example .env
notepad .env   # remplir MISTRAL_API_KEY=...
```

---

## Configuration

Tout est dans **`config.yaml`** à la racine. Les paramètres principaux :

| Section | Clé | Valeur par défaut | Rôle |
|---|---|---|---|
| `filters` | `region` | `Pays de la Loire` | Filtre géographique principal |
| `filters` | `department` | `null` | Optionnel — `Loire-Atlantique`, `Vendée`, etc. |
| `filters` | `city` | `null` | Optionnel — ex. `Nantes` |
| `filters` | `since_days` | `365` | **Consigne projet : événements de moins d'un an** |
| `filters` | `max_records` | `5000` | Garde-fou coût API |
| `chunking` | `chunk_size` | `800` | Taille d'un chunk |
| `chunking` | `chunk_overlap` | `120` | Recouvrement entre chunks |
| `models` | `embedding_model` | `mistral-embed` | Imposé |
| `models` | `llm_model` | `mistral-small-latest` | Bon rapport qualité / coût |
| `retrieval` | `search_type` | `mmr` | Diversité dans les chunks retournés |
| `retrieval` | `k` / `fetch_k` | `4` / `20` | Top-k final / pool MMR |

Modifier ces valeurs ne nécessite pas de toucher au code Python.

---

## Utilisation

### Pipeline complet (recommandé)

```bash
python scripts/pipeline.py
```

Cette commande enchaîne : téléchargement → tests qualité → indexation FAISS.

### Étape par étape

```bash
# 1. Téléchargement Open Agenda → data/raw/events.json
python scripts/01_fetch_data.py

# 2. Preprocessing + vectorisation → data/vectorstore/{index.faiss,index.pkl}
python scripts/02_build_index.py

# 3a. Démo CLI
python scripts/03_run_chatbot_cli.py
# > Quels concerts à Nantes ?
# > /quit

# 3b. Démo Streamlit
streamlit run app.py
# ou : python scripts/04_run_streamlit.py

# 4. Évaluation sur le jeu Q/R annoté
python scripts/05_evaluate.py            # 1 run (détail par question)
python scripts/05_evaluate.py --runs 3   # 3 runs, moyenne ± écart-type (recommandé)
```

### Reconstruction de la base vectorielle

La consigne projet impose que la base soit reconstructible « sur demande ».
C'est exactement ce que fait `scripts/02_build_index.py` à partir du dump JSON
brut, sans appel réseau supplémentaire à Open Agenda. Le cache local
(`data/embed_cache/`) évite de re-payer les embeddings déjà calculés.

```bash
python scripts/02_build_index.py
```

---

## Tests

Les tests `pytest` couvrent à la fois la logique de preprocessing et les
contraintes **obligatoires** du projet (fraîcheur < 1 an, région correcte).

```bash
# Tous les tests
pytest -v

# Uniquement les tests qualité de données (rapides, sans appel API)
pytest tests/test_data_freshness.py tests/test_data_geography.py -v

# Tests qui examinent le dump réel (sont skip si data/raw/events.json n'existe pas)
pytest tests/test_data_freshness.py::test_no_event_more_than_one_year_old_in_real_dump -v

# Sous Docker
docker compose run --rm rag pytest -v
```

**Détail des tests** :

- `test_data_freshness.py` — vérifie `firstdate_begin >= today - since_days`.
- `test_data_geography.py` — vérifie `location_region == settings.filters.region`,
  et le filtrage optionnel par département.
- `test_preprocessing.py` — `clean_html`, `normalize_text`, `dedupe`,
  `build_document_text`, filtrage des descriptions courtes.
- `test_vectorstore.py` — split en chunks, validation absence de clé API.

---

## Évaluation

Le jeu de données annoté `data/eval/qa_dataset.json` contient **20 paires
Q/R** couvrant 5 catégories (ville, thématique, date, lieu fin, événement
spécifique) + 3 questions hors-scope.

`src/pulsevents_rag/evaluation.py` calcule trois métriques :

| Métrique | Calcul | Lecture |
|---|---|---|
| **hit_rate@k** | la source attendue (uid) est-elle dans les chunks récupérés | qualité du retriever |
| **cosine** | similarité cosinus entre embeddings de la réponse générée et de la réponse annotée | qualité sémantique de la génération |
| **judge_score** | un appel `mistral-small` sépare juge la couverture (0 à 5) | qualité humanly-perceived de la réponse |

Le rapport CSV est sauvegardé dans `data/eval/results.csv`.

---

## Livrables projet OC

| Livrable demandé | Fichier(s) |
|---|---|
| **L1** README + gestion des dépendances | `README.md`, `requirements.txt`, `.env.example`, `config.yaml` |
| **L2** Scripts pré-processing + vectorisation + tests unitaires | `src/pulsevents_rag/{ingestion,preprocessing,vectorstore}.py`, `scripts/01_*.py`, `scripts/02_*.py`, `tests/*.py` |
| **L3** Rapport technique + code RAG | `docs/rapport_technique.docx`, `src/pulsevents_rag/rag.py`, `app.py`, `scripts/03_*.py`, `scripts/04_*.py` |
| Bonus jeu test annoté + script éval | `data/eval/qa_dataset.json`, `scripts/05_evaluate.py` |
| Présentation soutenance | réalisée séparément (non versionnée) |

---

## FAQ technique

**Pourquoi FAISS et pas Chroma / pgvector / Pinecone ?**
FAISS est imposé par les consignes. Pour un POC < 100 k chunks, `IndexFlatL2`
fait une recherche exacte rapide. Pour la version finale, on passerait à
`IndexIVFFlat` ou `IndexIVFPQ` (cf. rapport technique).

**Pourquoi MMR au lieu de la similarité simple ?**
MMR (Maximal Marginal Relevance) pénalise les chunks redondants. Sur Open
Agenda, plusieurs chunks d'un même festival peuvent dominer le top-k :
MMR force de la diversité, ce qui aide le LLM à proposer plusieurs
recommandations.

**Pourquoi un retriever hybride BM25 + dense ?**
Le retriever dense (FAISS sur embeddings Mistral) est sensible à la
formulation : *« concerts à Nantes »* et *« concerts à proximité de Nantes »*
peuvent renvoyer des chunks différents. BM25 (TF-IDF amélioré) attrape les
correspondances **lexicales exactes** que la similarité sémantique peut
rater (noms propres : *Nantes*, *Hellfest*, *Folle Journée*). La fusion via
`EnsembleRetriever` (Reciprocal Rank Fusion, pondérée 40/60 par défaut)
combine la précision factuelle du BM25 avec la robustesse sémantique du
dense. Configurable via `retrieval.use_hybrid` et `retrieval.bm25_weight`
dans `config.yaml`.

**Comment vérifie-t-on que les données respectent la consigne « < 1 an » ?**
Double filtre : (a) clause `where=` envoyée à l'API Opendatasoft, (b)
re-filtrage Python dans `preprocessing.py`, (c) tests `pytest` qui assertent
sur le dump réel. Voir `tests/test_data_freshness.py`.

**Combien coûte une indexation ?**
~5 000 chunks × ~600 tokens moyens = 3 M tokens d'embedding. Au tarif Mistral
embed (≈ 0,10 €/M tokens), environ **0,30 €** par construction d'index.
Les requêtes RAG (LLM small) sont de l'ordre du centime chacune.

**L'historique de conversation est-il géré ?**
Non. La consigne précise explicitement que l'historique n'est pas requis
pour le POC. La chaîne est volontairement stateless.

**Pourquoi pas RAGAS pour l'évaluation ?**
Les consignes demandent de mesurer la qualité « par rapport aux réponses
annotées » (même sens + mêmes informations) — exactement ce que couvrent
les métriques maison cosine + LLM-as-judge. Vérifié sur PyPI (ragas
0.4.3) : RAGAS dépend directement de `openai` et `langchain_openai`, plus
`datasets` HuggingFace (~150-200 Mo) ; importer l'écosystème OpenAI dans
un POC 100 % Mistral serait incohérent, pour des métriques (faithfulness,
context precision) hors du périmètre demandé. RAGAS est gardé en
recommandation v1 pour industrialiser l'évaluation en CI.

---

## Auteur

**Morgan Le Gall** — moy.morgan@gmail.com
Formation Data Engineer, OpenClassrooms — mai 2026.
