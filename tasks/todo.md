# Plan de travail - POC RAG Puls-Events

## Phase 1 - Squelette et configuration
- [x] Arborescence du projet
- [x] requirements.txt avec versions pinnees
- [x] .env.example + .gitignore
- [x] config.yaml (parametres centralises)
- [x] tasks/todo.md + tasks/lessons.md
- [x] README.md (squelette, complete en Phase 6)

## Phase 2 - Pipeline data
- [x] src/pulsevents_rag/config.py (chargement config)
- [x] src/pulsevents_rag/ingestion.py (Open Agenda fetch)
- [x] src/pulsevents_rag/preprocessing.py (clean + dedupe)
- [x] scripts/01_fetch_data.py
- [x] tests/conftest.py + fixtures
- [x] tests/test_data_freshness.py
- [x] tests/test_data_geography.py
- [x] tests/test_preprocessing.py

## Phase 3 - RAG
- [x] src/pulsevents_rag/vectorstore.py (FAISS + Mistral embed)
- [x] src/pulsevents_rag/rag.py (chaine LangChain)
- [x] scripts/02_build_index.py
- [x] scripts/03_run_chatbot_cli.py
- [x] tests/test_vectorstore.py

## Phase 4 - Demo Streamlit
- [x] app.py (UI Streamlit)
- [x] scripts/04_run_streamlit.py

## Phase 5 - Evaluation
- [x] data/eval/qa_dataset.json (15-20 paires Q/R)
- [x] src/pulsevents_rag/evaluation.py
- [x] scripts/05_evaluate.py

## Phase 6 - Documentation finale
- [x] README.md (version finale complete)
- [x] docs/journal.md (journal de bord)
- [x] docs/rapport_technique.docx (5-10 pages)
- [x] docs/deroule_projet.docx (narratif pedagogique)
- [x] docs/presentation.pptx (10-15 slides)

## Phase 7 - Verification finale
- [x] Compilation py_compile sur tous les modules : OK
- [x] Tests pytest offline (9 passed, 2 skipped legitimement) : OK
- [x] Generation .docx + .pptx : OK
- [x] Section "Review" complete (ci-dessous)
- [ ] [USER] Execution end-to-end avec cle Mistral
- [ ] [USER] Mise a jour rapport.docx avec metriques reelles
- [ ] [USER] Annotation de qa_dataset.json avec uids reels apres premier index

## Review

### Etat de livraison

**Tous les livrables OC sont presents :**

| # | Livrable | Fichier | Statut |
|---|---|---|---|
| L1 | Readme + dependances | `README.md` + `requirements.txt` + `.env.example` + `config.yaml` | OK |
| L2 | Pre-processing + tests | `src/pulsevents_rag/{ingestion,preprocessing,vectorstore}.py` + `scripts/01,02_*.py` + `tests/*.py` | OK |
| L3 | Rapport + code RAG | `docs/rapport_technique.docx` + `src/pulsevents_rag/rag.py` + `app.py` + `scripts/03,04_*.py` | OK |
| Bonus | Jeu test annote | `data/eval/qa_dataset.json` (20 paires) + `scripts/05_evaluate.py` | OK |
| Bonus | Presentation | `docs/presentation.pptx` (13 slides) | OK |
| User | Deroule pedagogique | `docs/deroule_projet.docx` | OK |
| User | Journal de bord | `docs/journal.md` | OK |

### Verifications effectuees

- `python -m py_compile` sur tous les fichiers .py : RC=0.
- `pytest tests/test_data_*.py tests/test_preprocessing.py -v` : 9 passed, 2 skipped (skip legitime : pas de dump reel encore).
- Structure de projet conforme au plan.

### Ce qu'il reste a faire (pour l'utilisateur)

1. Recuperer une cle API sur https://console.mistral.ai (Le Chat Pro != API).
2. Lancer la pipeline : `python scripts/pipeline.py`.
3. Lancer la demo : `streamlit run app.py`.
4. Lancer l'evaluation : `python scripts/05_evaluate.py`.
5. Optionnel : enrichir `qa_dataset.json` avec les `expected_source_uids` reels apres premier indexage.
6. Optionnel : mettre a jour les chiffres dans le rapport (cf. section 5 du rapport_technique.docx).
