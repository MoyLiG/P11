# Journal de bord — POC RAG Puls-Events

> Journal chronologique du déroulé du projet. Chaque entrée capture les
> décisions prises, les obstacles rencontrés et les apprentissages.

---

## J0 — Réception du brief (8 mai 2026)

**Source** : courriel de Jérémy (responsable technique fictif).

**Lecture critique des consignes** :

- Stack imposée : **LangChain + Mistral + FAISS**. Pas le choix.
- Périmètre géographique **libre**. Bonne nouvelle, ça permet d'optimiser
  le rapport volume/pertinence.
- Filtre temporel **strict** : événements de moins d'un an.
- Livrables : Readme + scripts + tests + rapport (5-10 p) + présentation
  (10-15 slides) + jeu Q/R annoté + démo live.
- La soutenance comporte une partie démo live → l'UI doit fonctionner.

**Première liste de questions** :

1. Source Open Agenda : API officielle (token requis) ou dataset
   Opendatasoft public ? → à vérifier.
2. Mistral : abonnement Le Chat ≠ accès API ? → à clarifier.
3. Quel volume attendre ? → à mesurer avant de fixer la région.

---

## J1 — Cadrage et exploration de la source

### Décision initiale : région **Pays de la Loire**, puis resserrement sur **Loire-Atlantique**

Volumes mesurés directement sur l'API Opendatasoft (filtre `firstdate_begin >= today - 365j`, mesure du 2026-05-08) :

| Périmètre | Évènements < 1 an |
|---|---|
| Pays de la Loire | **19 927** |
| Loire-Atlantique seule | 13 272 |
| Nantes (ville) | 8 892 |
| Île-de-France (comparaison) | 8 036 |
| Saint-Nazaire | 284 |

Surprise : Pays de la Loire pèse **2,5× l'Île-de-France** sur Open Agenda. Beaucoup d'agendas territoriaux ligériens (Voyage à Nantes, offices de tourisme, médiathèques...) sont connectés à la plateforme.

**Décision finale** : `region: "Pays de la Loire"` + `department: "Loire-Atlantique"`. Justification :

1. **Volume parfait pour un POC** : 13 272 événements, c'est exhaustif sans être ingérable (coût d'embedding ~0,80 €).
2. **Cohérence narrative** : la démo orale (Nantes / Saint-Nazaire / presqu'île guérandaise) reste centrée sur un département identifiable.
3. **Filtre escamotable** : si on veut élargir, `department: null` ramène les 19 927 events sans changer le code.

Trois candidats étaient initialement sur la table :

| Option | Volume estimé | Pour | Contre |
|---|---|---|---|
| Paris | très élevé | dense, démo facile | biais parisien attendu, pas distinctif |
| Île-de-France | très élevé | volume max | lourdeur de l'index |
| **Pays de la Loire** | moyen-élevé | diversité (Nantes, Angers, Saint-Nazaire, Vendée), originalité, festivals emblématiques | volume un peu plus faible |

J'ai retenu **Pays de la Loire** : volume suffisant pour que le RAG ait
quelque chose à se mettre sous la dent, sans tomber dans le réflexe Paris.
Festivals identifiables (La Folle Journée, Hellfest, Les Escales,
Voyage à Nantes) qui faciliteront la présentation orale.

### Décision : source = **dataset Opendatasoft**

L'API officielle Open Agenda nécessite un compte et un token. Le dataset
[`evenements-publics-openagenda`](https://public.opendatasoft.com/explore/dataset/evenements-publics-openagenda/)
republié par OPDF expose **45 champs** et **1,1 M+ enregistrements** sans
authentification, avec un endpoint moderne `/api/explore/v2.1/catalog/...`
et des filtres ODSQL puissants. Choix évident pour un POC.

Vérifié manuellement que les champs nécessaires sont présents :
`title_fr`, `longdescription_fr`, `daterange_fr`, `firstdate_begin`,
`location_region`, `location_department`, `location_city`, `keywords_fr`,
`canonicalurl`, `uid`. ✅

### Décision : démo = **Streamlit + CLI**

CLI pour les tests rapides (et la soutenance technique si besoin),
Streamlit pour la démo "produit" qui parle aux équipes Marketing et
Produit présentes en réunion.

---

## J2 — Architecture et squelette

### Architecture retenue

```
Open Agenda → ingestion → preprocessing → chunking → mistral-embed
                                                         ↓
                                                       FAISS
                                                         ↓
question → retriever (MMR k=4) → context → mistral-small → réponse + sources
```

### Choix techniques argumentés

- **Chunking** : `RecursiveCharacterTextSplitter` (LangChain) avec
  `chunk_size=800` / `overlap=120`. Les descriptions Open Agenda sont
  courtes-moyennes (300 à 2 000 caractères) ; 800 capture un événement
  entier sans le couper et reste sous les limites de contexte.
- **Embeddings** : `mistral-embed`, 1024 dim. Imposé.
- **FAISS** : `IndexFlatL2` (recherche exacte). Pour < 100 k chunks la
  vitesse est suffisante. À l'échelle, IVF ou IVF-PQ. Documenté dans le
  rapport.
- **Retrieval** : `mmr` plutôt que `similarity` pour éviter que 4 chunks
  consécutifs d'un même festival saturent le contexte.
- **LLM** : `mistral-small-latest`, température 0.2. Compromis
  qualité/coût pour un POC. `mistral-large` discuté en recommandations.
- **Prompt** : système strict en français, force la citation des sources
  (titre + dates + lieu) et le refus explicite hors-scope.

### Structure du repo

Organisation classique en package `src/pulsevents_rag/` (réutilisable),
scripts numérotés `01..05` pour le pipeline, tests dans `tests/`,
config externalisée en YAML.

---

## J3 — Implémentation du pipeline data

**Modules livrés** :

- `config.py` : chargement YAML + `.env`, validation pydantic.
- `ingestion.py` : pagination 100/req, retry exponentiel `tenacity` sur
  erreurs réseau, courtoisie 0,2 s entre pages.
- `preprocessing.py` : nettoyage HTML (BeautifulSoup), normalisation
  Unicode NFKC, déduplication par `uid`, double filtre métier
  (région + fraîcheur), construction des `Document` LangChain avec
  texte enrichi (titre + dates + lieu + mots-clés + description).

**Point de vigilance identifié** : un événement multi-mois peut avoir
commencé il y a > 365 j et durer encore. Décision retenue (justifiée
dans le rapport) : on filtre sur `firstdate_begin`, conformément au
texte « événements de moins d'un an » lu littéralement. Une variante
`lastdate_end >= today - 365j` est documentée comme amélioration future.

---

## J4 — Construction de l'index et chaîne RAG

**Modules livrés** :

- `vectorstore.py` : split + `FAISS.from_documents` + `save_local`.
- `rag.py` : `ChatPromptTemplate`, `create_stuff_documents_chain`,
  `create_retrieval_chain`. Helpers `RagPipeline.answer` qui retourne
  un objet structuré avec sources dédupliquées.

**Anecdote** : j'ai d'abord oublié `allow_dangerous_deserialization=True`
sur `FAISS.load_local`. LangChain refuse de charger un pickle non
explicitement marqué comme sûr (protection contre les pickles
malveillants). Comme c'est notre propre fichier, on accepte le risque.
Ajouté dans `vectorstore.load_index`.

---

## J5 — Démo et tests

**App Streamlit** : `app.py`. Sidebar qui affiche la config courante
(région, modèle, top-k), `st.chat_input` pour la saisie, `st.expander`
pour les sources cliquables (lien Open Agenda).

**Tests pytest** : 4 fichiers, focus sur les contraintes du projet
(fraîcheur, région). Les tests qui examinent le dump réel sont marqués
*skip* automatiquement si `data/raw/events.json` n'existe pas → bonne
pratique pour la CI.

---

## J6 — Évaluation

### Construction du jeu Q/R annoté

20 paires Q/R réparties en :

- **5 catégories métier** : ville, thématique, date, lieu fin, événement
  spécifique.
- **3 questions hors-scope** (Marseille, recette de cuisine, géographie
  d'Italie) pour tester la robustesse du *garde-fou* du prompt.

Les `expected_source_uids` sont laissés vides volontairement : ils
seront enrichis manuellement après une première construction d'index,
quand on connaîtra les `uid` réels présents dans la base. Le jeu
permettra alors un **hit_rate@k** précis.

### Métriques implémentées

- `hit_rate@k` (uid attendu dans les sources retournées) ;
- similarité cosinus (mistral-embed) entre réponse générée et réponse
  annotée ;
- juge LLM (mistral-small, température 0) qui note 0 à 5 la couverture
  de la réponse attendue.

Sortie : CSV `data/eval/results.csv` + résumé console.

---

## J7 — Documentation finale

- README détaillé (table des matières, install Win/Linux, tests, FAQ).
- Rapport technique 5-10 pages (architecture, choix justifiés,
  résultats, limites, recommandations).
- Document « déroulé du projet » (narratif pédagogique demandé par
  l'utilisateur).
- Présentation 10-15 slides pour la soutenance.

---

## J7-Audit — Audit coût + sécurité et hardening

### Audit coût (skill `cost-reducer`)

Mesure des coûts réels du projet :

| Opération | Coût |
|---|---|
| 1 indexation complète (~16k chunks) | ~0,96 € |
| 1 requête utilisateur | ~0,001 € |
| 1 run d'évaluation (20 Q/R × 3 métriques) | ~0,03 € |

Projection prod (500 users × 5 req/jour) : ~47 €/mois, ~30 € avec cache sémantique.

### Audit sécurité (skill `security`)

7 dépendances avec CVE identifiées (toutes Medium/Low, fixées en upgrade) ; 3 findings High (prompt injection indirecte, absence de rate limit Streamlit, pickle FAISS), 5 Medium, 3 Low. Aucun secret hardcodé, .gitignore correct.

### Modifications appliquées

| # | Type | Fichier | Changement |
|---|---|---|---|
| 1 | Cost | `config.yaml` | `chunk_size: 800→1200`, `chunk_overlap: 120→80`, `fetch_k: 20→12` (-30 % coût d'indexation) |
| 2 | Cost+Sec | `src/pulsevents_rag/rag.py` | Prompt compressé (~250→~140 tokens) + balisage `<events>` anti-prompt-injection + log tronqué (anti-PII) |
| 3 | Cost+Sec | `src/pulsevents_rag/rag.py` | `max_tokens=400` sur `ChatMistralAI` (anti-runaway) |
| 4 | Sec | `src/pulsevents_rag/rag.py` | `RagPipeline.answer` lève `ValueError` si question > 500 chars |
| 5 | Cost | `src/pulsevents_rag/vectorstore.py` | `CacheBackedEmbeddings` + `LocalFileStore` → -95 % sur les rebuilds incrémentaux |
| 6 | Sec | `app.py` | `MAX_QUERIES_PER_SESSION=30`, cap longueur question, `_safe_url` qui filtre `javascript:`/`data:` |
| 7 | Sec | `requirements.txt` | `python-dotenv 1.0.1 → 1.2.2` (CVE-2026-28684) |
| 8 | Sec | `SECURITY.md` (nouveau) | Modèle de menace, mesures appliquées, checklist pré-prod |

Tests post-modifs : `9 passed, 2 skipped` — pas de régression.

## J8 — Standardisation environnement : WSL2 / Docker

### Constat

Première itération du README : commandes en PowerShell en premier. Erreur d'auto-cohérence : `CLAUDE.md` du projet précisait « Bash préféré pour Unix-style ». Question levée par l'utilisateur : *« PowerShell ou WSL2 ? Quelle est la norme ? »*.

### Décision

L'écosystème data engineering Python 2026 est **Linux-first** :

- 95 % des tutos LangChain / Mistral / FAISS / HuggingFace sont en bash ;
- déploiement = Docker = Linux ;
- `faiss-cpu` a historiquement des wheels Linux plus stables ;
- `curl`, `jq`, `grep`, scripts Makefile partout en bash ;
- Streamlit Cloud, HuggingFace Spaces, EC2 = Linux ;
- reproductibilité : un script bash tourne identique partout.

### Modifications appliquées

1. **README** réorganisé : Option A (WSL2/Linux/macOS) en path principal, Option B (Docker) recommandée pour la démo et la prod, Option C (PowerShell natif) en alternatif.
2. **Dockerfile** ajouté : `python:3.12-slim`, utilisateur non-root (UID 1000), `libgomp1` pour `faiss-cpu`, healthcheck Streamlit, image ~600 Mo.
3. **docker-compose.yml** : un service `rag`, env_file `.env`, volumes pour persister `data/raw`, `data/processed`, `data/vectorstore`, `data/embed_cache` entre runs ; limites de ressources (2 GB / 2 CPU) en défense en profondeur.
4. **.dockerignore** : exclut `.venv`, caches Python, `.git`, données locales, `.env` → contexte de build réduit de ~95 %.
5. **Toutes les commandes** des sections « Utilisation » et « Tests » du README passées en bash.

### Bénéfices

- Démo en soutenance reproductible : un évaluateur lance `docker compose up rag` et c'est fini.
- Élimine la question « ça marche chez moi pas chez toi » entre Windows et Linux.
- Prépare la roadmap v1 : l'image Docker est directement déployable sur ECS, Cloud Run, ou Kubernetes.

## J9 — Premier run end-to-end : bug API Opendatasoft

### Symptome

`docker compose run --rm rag python scripts/pipeline.py` : build OK (270s
la premiere fois, normal), ingestion demarre sur 13 308 events Loire-Atlantique,
recupere ~10 000 events puis `HTTPError: 400 Client Error` a `offset=10000`,
trois retries qui echouent identiquement, pipeline en echec.

### Diagnostic

L'endpoint `/records` v2.1 d'Opendatasoft a une limitation hard :
**offset + limit <= 10 000**. Documentee mais cachee dans la doc API.
Au-dela, c'est HTTP 400 systematique (donc le retry exponentiel ne sert
a rien — c'est une erreur deterministe, pas un soucis reseau).

Le total disponible (13 308) etait correctement remonte par l'API, mais
on ne peut tout simplement pas le paginer via /records.

### Fix applique

1. **Constante explicite** dans [ingestion.py](src/pulsevents_rag/ingestion.py) :
   `OPENDATASOFT_RECORDS_LIMIT = 10_000`.
2. **Plafonnage automatique** dans `_iter_records` : si l'utilisateur configure
   `max_records > 10 000`, on log un warning et on cape a 10 000.
3. **Sanity check par requete** : `offset + limit > 10000` declenche un break
   propre, jamais d'appel HTTP voue a echouer.
4. **Route alternative** : nouvelle fonction `_iter_records_export` qui appelle
   `/exports/json` (pas de limite offset, retourne tout le dataset filtre en un
   coup, plus lent mais exhaustif).
5. **Bascule automatique** dans `fetch_open_agenda(use_export=None)` : si
   `max_records > 10 000`, bascule sur l'export.
6. **Config par defaut** : `max_records: 10000` dans `config.yaml` (suffit
   largement pour un POC RAG, ~75 % de la Loire-Atlantique).

### Impact mesures

Volumes attendus revus :
- Avant (config 15k) : ~13 272 events ingerables -> ECHEC.
- Apres (config 10k) : ~10 000 events ingeres en propre, ~7 500 documents
  apres dedup/filtre qualite, ~12 000 chunks FAISS, ~0,75 EUR d'indexation.

C'est largement assez pour le POC. Si la prod veut tout, basculer sur
`use_export=True`.

## J10 — Run end-to-end : rate limit Mistral + bug langchain-mistralai

### Symptomes (apres fix J9)

L'ingestion passe (`10 000 / 10 000`), les tests pytest passent (`5 passed`),
le decoupage en chunks fonctionne (`9 948 docs -> 12 834 chunks`). Mais
l'indexation FAISS crash apres ~150 secondes d'embedding :

```
HTTP Request: POST .../v1/embeddings "HTTP/1.1 429 Too Many Requests"
ERROR | langchain_mistralai.embeddings | An error occurred with MistralAI: 'data'
KeyError: 'data'
```

Plus deux warnings cosmetiques (pytest cache et BeautifulSoup).

### Diagnostic

1. **Rate limit Mistral La Plateforme** : ~1 req/s sur le tier gratuit, un
   peu plus sur paye. LangChain envoie les batches sans rate limit natif
   → on saute la limite → HTTP 429.
2. **Bug langchain-mistralai 0.2.x** : parse `response.json()["data"]`
   meme quand le status est 429 → KeyError au lieu d'un retry propre.
3. **Permissions Docker** : `WORKDIR /app` cree le dossier en root (mode
   755), l'utilisateur `app` (UID 1000) ne peut pas y ecrire son cache
   pytest.
4. **Warning BeautifulSoup** : faux positif sur les descriptions courtes
   qui ressemblent a des URLs/paths.

### Fix applique

1. **`RateLimitedMistralEmbeddings`** dans
   [src/pulsevents_rag/vectorstore.py](src/pulsevents_rag/vectorstore.py) :
   wrapper Embeddings qui (a) garantit un intervalle minimum 1,1 s entre
   appels, (b) batch par paquets de 24 docs, (c) retry exponentiel
   tenacity (6 tentatives, backoff 2-60 s) sur quasi toutes exceptions
   y compris KeyError. Toujours actif, en dessous du
   `CacheBackedEmbeddings`.
2. **`embedding_batch_size: 50 -> 24`** dans
   [config.yaml](config.yaml) : reste sous la limite tokens/batch Mistral.
3. **`RUN chown -R app:app /app`** dans le
   [Dockerfile](Dockerfile) apres `WORKDIR /app`.
4. **`warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)`**
   dans
   [src/pulsevents_rag/preprocessing.py](src/pulsevents_rag/preprocessing.py).

### Impact attendu sur le run

- Plus de crash 429.
- Embedding sequentiel rate-limite : ~12 834 chunks / 24 par batch =
  ~535 batches × 1,1 s = ~10 min de pauses cumulees. Plus ~2-3 min
  d'API reelle. Total ~13 min pour l'indexation complete.
- A partir du 2e build (apres modif minime), le `CacheBackedEmbeddings`
  evite 95 % des appels Mistral -> ~30 s seulement.
- Plus de warnings parasites dans la sortie.

## J11 — Découverte UX : événements passés retournés

### Symptôme

Run end-to-end OK, index FAISS construit. Première démo Streamlit :
question *« Que faire ce week-end à Saint-Nazaire ? »* (date du jour :
20 mai 2026) → le bot répond avec des événements de **septembre 2025**,
**juin 2025**, **novembre 2025**. Tous passés.

### Cause

Le filtre temporel d'origine `firstdate_begin >= today - 365j` est
l'interprétation **rétrospective** de la consigne « moins d'un an ».
Pour un chatbot de découverte, l'interprétation **prospective** fait
sens : *événements à venir ou en cours dans l'année*. Cette ambiguïté
était documentée dans le rapport (§6.1 limite, §6.2 reco) mais l'option
historical était active par défaut.

### Fix

1. **Filtre `time_mode` paramétrable** dans
   [config.yaml](config.yaml) avec deux valeurs :
   - `upcoming` (nouveau défaut) : `lastdate_end >= today AND
     firstdate_begin <= today + 365j` → events à venir ou en cours.
   - `historical` : `firstdate_begin >= today - since_days` → ancien
     comportement, utile pour des analyses retrospectives.
2. **Cohérence côté Python** dans
   [src/pulsevents_rag/preprocessing.py](src/pulsevents_rag/preprocessing.py)
   `filter_recency_and_region` qui implémente le double check selon le
   mode.
3. **Tests pytest mis à jour** : `test_old_events_are_filtered` et
   `test_freshness_in_real_dump` vérifient le mode courant. 11/11 PASSED.
4. **Date du jour injectée dans le prompt système** : le LLM peut
   interpréter "ce week-end", "cet été", etc. (utilise la date du
   build, gelée par session).
5. **Prompt amélioré** : "privilégie les events à venir, signale les
   passés explicitement".

### Action utilisateur

Re-télécharger avec le nouveau filtre + ré-indexer. Le cache d'embeddings
limitera le coût aux nouveaux events (probablement ~30 % de nouveau).

## J12 — Hybrid search BM25 + dense

### Symptôme

Sur la même intention, deux formulations légèrement différentes
donnent des résultats différents :

| Question | Top-6 retourné | Pertinent dans top-6 |
|---|---|---|
| *« concerts à Nantes ce mois-ci »* | 4 chunks dont 1 pertinent (Sylvain Chauveau) | 1/4 |
| *« concerts à proximité de Nantes »* | 4 chunks dont 2 pertinents (+ L'Opéra à la Bottière) | 2/4 |

L'Opéra à la Bottière (Nantes 44300) **devrait** apparaître sur les deux
formulations. Il chute hors top-6 sur la 1ère.

### Cause

Le retriever dense (FAISS + embeddings Mistral) classe les chunks selon
la similarité **sémantique**. Pour le mot « Nantes » dans une requête
courte, l'embedding capture le **contexte** (mots autour) plutôt que le
**token exact**. Deux formulations sémantiquement proches mais
lexicalement différentes peuvent donner des top-k différents.

C'est le défaut classique du dense-only : sensible à la formulation,
faible sur les correspondances factuelles (noms propres, dates, IDs).

### Fix : Hybrid Search (BM25 + dense + RRF)

Implémentation :

1. **`rank_bm25==0.2.2`** ajouté à [requirements.txt](requirements.txt).
2. **`load_documents_for_bm25`** dans
   [src/pulsevents_rag/vectorstore.py](src/pulsevents_rag/vectorstore.py) :
   recharge les `Document` LangChain depuis le parquet
   `data/processed/events_clean.parquet`. BM25 est un index lexical
   reconstruit en mémoire au démarrage (< 1 s sur quelques milliers
   de docs, pas d'API call).
3. **`_build_retriever`** dans
   [src/pulsevents_rag/rag.py](src/pulsevents_rag/rag.py) :
   `EnsembleRetriever([BM25Retriever, dense_retriever], weights=[0.4, 0.6])`
   avec Reciprocal Rank Fusion native LangChain.
4. **Config exposée** dans
   [config.yaml](config.yaml) : `retrieval.use_hybrid: true`,
   `retrieval.bm25_weight: 0.4`. Désactivable pour comparer.
5. **Tests offline** dans
   [tests/test_retriever.py](tests/test_retriever.py) : 3 tests sur
   BM25 (correspondance exacte, classement par TF-IDF, validation
   config). 14/14 PASSED.

### Compromis et pondération

- `bm25_weight = 0.4` : on donne 60 % de poids au dense car il est
  meilleur sur les questions thématiques larges (*« festivals de musique
  classique »*, *« expositions pour enfants »*), 40 % au BM25 pour
  capter les correspondances factuelles fortes.
- Réajustable selon le profil de requêtes utilisateur observé en prod.
- Mesurable via `scripts/05_evaluate.py` (hit_rate@k devrait monter).

### Impact attendu

- Robustesse forte sur les noms propres : *Hellfest*, *La Folle Journée*,
  *Voyage à Nantes*, noms de communes.
- Latence inchangée : BM25 est natif Python pur, ~5 ms par requête.
- Coût inchangé : pas d'embedding supplémentaire.
- Retire la limitation §6.1 du rapport et l'intègre dans les
  choix techniques §3.

## J13 — Bug ndarray : keywords_fr depuis parquet

### Symptôme

Apres l'ajout du hybrid search, Streamlit affiche :
*"Configuration invalide : The truth value of an array with more than
one element is ambiguous. Use a.any() or a.all()"*.

### Cause

`load_documents_for_bm25` relit `data/processed/events_clean.parquet`.
Or pyarrow/pandas convertit les colonnes de listes (`keywords_fr`) en
`numpy.ndarray`. Le code historique de `build_document_text` faisait :

```python
keywords = row.get("keywords_fr") or []   # ndarray or [] -> ValueError
```

`ndarray or []` force l'evaluation booleenne de l'array → erreur numpy.
Le pipeline d'indexation ne plantait pas car il lit le JSON brut (liste
Python). C'est le rechargement parquet (nouveau, pour BM25) qui declenche.

### Fix

Helper `_as_list()` dans
[src/pulsevents_rag/preprocessing.py](src/pulsevents_rag/preprocessing.py)
qui coerce proprement list / ndarray / None / NaN / scalaire en liste
Python, en traitant l'ndarray AVANT tout test booleen. Test de regression
ajoute dans
[tests/test_preprocessing.py](tests/test_preprocessing.py)
(`test_build_document_text_handles_numpy_keywords`). 15/15 PASSED.

### Lecon

Toujours se mefier du type des cellules pandas selon la source
(JSON vs parquet vs CSV). Ne jamais faire `valeur or defaut` sur une
cellule susceptible de contenir un array. Tester le pipeline avec la
VRAIE source de rechargement, pas seulement le chemin d'ecriture.

## J14 — Évaluation chiffrée + finding qualité de données

### Premier run d'évaluation

Sur le jeu de 20 Q/R (avant annotation des uids) :
- **cosine moyenne : 0,846** (excellent — réponses sémantiquement justes)
- **juge LLM : 3,35 / 5** (correct, tiré vers le bas par des réponses
  attendues citant des events saisonniers absents en mode upcoming)
- **hit_rate : 33,3 %** (non significatif : uids non annotés, mesuré
  seulement sur les hors-scope)

### Améliorations du jeu d'évaluation

1. Détection de refus robuste (insensible aux accents) via `_is_refusal()`.
2. Réponses attendues rendues génériques (retrait de La Folle Journée,
   Les Escales, Hellfest — events hors base upcoming).
3. Annotation des `expected_source_uids` via `scripts/07_eval_candidates.py`
   (affiche les candidats du retriever par question → annotation manuelle).
4. Angers et Vendée reclassés `out_of_scope` : hors du département filtré
   (Loire-Atlantique), le bot doit légitimement refuser.

> **Limite méthodologique assumée** : les uids sont annotés à partir des
> candidats remontés par le retriever, faute de ground truth exhaustif
> (parcourir 2 127 events à la main). Le `hit_rate@k` mesure donc la
> *cohérence* du top-k (contient-il au moins un event pertinent) plutôt
> qu'un *recall* absolu. Le cosine et le juge restent les métriques de
> qualité non circulaires.

### FINDING IMPORTANT — bruit emploi/formation dans Open Agenda

En annotant, observation nette : Open Agenda Loire-Atlantique contient
beaucoup d'« événements » **non culturels** qui polluent le retrieval :

- France Travail : « Job dating - Métiers du soin » (×6 sur une requête
  Saint-Nazaire !), « Alternance Dating », « Cap emploi »...
- Formations : « Maîtriser LinkedIn », « Devenez Digital Learning Manager »...
- Administratif : « Comment choisir ma mutuelle ? », « Atelier indemnisation
  fin de droits », « Eau potable : à votre santé ! »...

Ces events sont indexés au même titre que les concerts et expos, et
remontent dans le top-k, réduisant la précision.

**Cause** : l'agenda Open Agenda agrège des contributeurs hétérogènes
(`originagenda_title` = "francetravail", etc.) sans distinction de nature.

**Reco v1 (filtre à l'ingestion)** : exclure par `originagenda_title`
(France Travail, Pôle Emploi) ou par `category` Open Agenda, ou par
liste de mots-clés titre. Gain attendu sur la précision@k : fort.
C'est exactement le type de nettoyage attendu sur la compétence
"garantir la qualité des données dans un pipeline".

## J15 — Fuite de connaissance paramétrique (OWASP LLM09)

### Symptôme

Analyse fine par question de l'éval : un seul vrai échec, Q15
*« Quelle est la capitale de l'Italie ? »* → hit=miss, juge 0/5.
Le bot a répondu « Rome » au lieu de refuser.

Les autres hors-scope sont bien refusés :
- Q17 « events à Marseille » → refus correct (5/5)
- Q16 « recette galettes » → refus (3/5)

### Cause

Sur une **question factuelle simple**, le LLM (mistral-small) puise dans
sa **connaissance paramétrique** plutôt que de rester confiné au contexte.
Le prompt disait « réponds depuis le contexte » sans **interdire
explicitement** l'usage des connaissances générales. C'est de l'OWASP
LLM09 (overreliance / scope creep).

Différence avec Q16/Q17 : « Marseille » et « recette » n'ont pas de
réponse factuelle évidente à fournir → le bot refuse naturellement.
« Capitale de l'Italie » a une réponse triviale que le LLM connaît →
il la donne.

### Fix

Verrou de périmètre dans le prompt système
([src/pulsevents_rag/rag.py](src/pulsevents_rag/rag.py)) :
« Tu réponds EXCLUSIVEMENT à des questions sur des événements culturels.
Pour toute question de culture générale [...] réponds la formule de refus.
N'utilise JAMAIS tes connaissances générales hors du bloc <events>. »

Impact attendu : Q15 passe de 0/5 à 5/5 → juge moyen ~3,55 → ~3,8.

### Lecon

Un RAG ne confine pas automatiquement le LLM à sa base. Sur les
questions factuelles, il faut un **verrou de périmètre explicite** dans
le prompt, sinon le modèle « fuit » sa connaissance paramétrique. À
tester systématiquement avec des questions de culture générale dans le
jeu d'évaluation.

## J16 — Régression du verrou de périmètre (sur-refus)

### Symptôme

Après le fix J15 (verrou anti-fuite), nouveau run :
- hit_rate 100 %, cosine 0,868, juge **4,10** (en hausse).
- MAIS l'analyse fine révèle 6 **faux refus** : Q4 (musique classique),
  Q5 (expos), Q6 (théâtre enfants), Q10 (juillet), Q11 (presqu'île),
  Q18 (conférences) répondent « Je n'ai pas trouvé » alors que le
  retriever a remonté les bons events.

### Cause

Le verrou J15 était trop agressif : « réponds EXCLUSIVEMENT aux events
culturels [...] N'utilise JAMAIS tes connaissances générales » a rendu
le LLM paranoïaque. Il interprétait « musique classique » comme de la
connaissance générale et refusait.

### Point méthodologique clé

**Les agrégats ont masqué la régression** :
- hit_rate 100 % mesure le *retriever* (parfait), pas la *génération*.
- juge 4,10 monte car les 5 hors-scope parfaits compensent les 6 faux refus.

Seule l'**analyse fine par question** a révélé le problème. Leçon :
ne jamais juger une régression sur les seuls agrégats.

### Re-fix (verrou chirurgical)

Distinguer explicitement dans le prompt :
- question événementielle (concert, expo, thème large) → chercher dans <events> ;
- question SANS AUCUN RAPPORT (capitale, recette, météo) → refus.

Suppression de l'interdiction trop large « N'utilise JAMAIS tes
connaissances générales » (remplacée par une interdiction ciblée sur
les questions hors-événementiel uniquement).

### Lecon

Le tuning de prompt est itératif et à double tranchant : durcir le refus
augmente les faux refus. Toujours re-mesurer sur l'ensemble du jeu après
un changement de prompt, et lire le détail par question.

## J17 — Filtre anti-bruit (qualité de données)

### Objectif

Suite au finding J14 (events emploi/formation/admin polluent le retrieval),
implémenter un filtre à l'ingestion et mesurer l'avant/après.

### Implémentation

`filter_noise()` dans
[src/pulsevents_rag/preprocessing.py](src/pulsevents_rag/preprocessing.py)
exclut les events dont :
- le titre contient un mot-clé emploi/formation/admin
  (`exclude_title_keywords` : "job dating", "forum emploi", "indemnisation",
  "comment choisir ma mutuelle", "maitriser linkedin"...) ;
- le contributeur d'origine (`originagenda_title`) est dans `exclude_agendas`
  ("france travail", "pole emploi").

Comparaison insensible aux accents/casse (`strip_accents_lower`).
Listes configurables dans [config.yaml](config.yaml).
Intégré dans `run_preprocessing` après le filtre métier.
Tests : 3 ajoutes (18/18 PASSED).

### Avant / après (mesuré)

| Métrique | Avant filtre | Après filtre |
|---|---|---|
| Documents indexés | 2 124 | **1 849** (−275, soit −13 %) |
| hit_rate@k | 100 % | 100 % |
| cosine moyenne | 0,885 | **0,890** |
| juge moyen | 4,10 / 5 | **4,15 / 5** |

**275 événements emploi/formation/administratif retirés (13 % du corpus !)** —
volume de bruit bien plus élevé qu'attendu. Gains nets par question :
Q5 expositions (3→4), Q20 rock (3→5).

### Analyse : pourquoi l'impact est modeste mais utile

L'amélioration est faible (+0,05 juge) car le LLM **filtrait déjà
implicitement** le bruit : il ne citait pas les « job dating » même
présents dans le top-k. Le filtre apporte donc surtout :
1. une meilleure **précision du retrieval** (le top-k ne gaspille plus
   de places sur du bruit) ;
2. de la **robustesse sur les requêtes où le bruit domine** (sur
   Saint-Nazaire, 6/12 candidats étaient des job dating avant filtre) ;
3. une **réduction du coût** (contexte plus dense en info utile).

Enseignement : nettoyer à la source est une bonne pratique même quand le
gain agrégé est faible, car cela réduit le risque sur les cas limites et
améliore la précision sans dépendre de la robustesse du LLM.

## Bilan d'apprentissage

1. **La distinction Le Chat / API Mistral n'est pas évidente** pour un
   utilisateur final — à toujours documenter clairement.
2. **La sémantique du filtre temporel** mérite d'être explicite : sur
   `firstdate_begin` ou `lastdate_end` ? On choisit, on documente, on
   teste.
3. **MMR > similarity simple** dès qu'il existe des doublons sémantiques
   dans la base (ce qui est typiquement le cas sur Open Agenda où un
   événement génère plusieurs chunks).
4. **Le prompt système est aussi important que le retriever** : sans
   instruction explicite de refuser, le LLM hallucine sur les questions
   hors-scope. Le test `id=15` (capitale d'Italie) le valide.
5. **FAISS suffit largement à cette échelle** ; passer à un service
   managé serait du gold-plating.

---

## À faire post-soutenance (hors POC)

- Indexation incrémentale (mises à jour quotidiennes Open Agenda).
- Re-ranking (cohere ou bge-reranker) après le retriever.
- Hybrid search (BM25 + dense) pour les queries factuelles précises.
- Observabilité : LangSmith ou Phoenix (Arize) pour tracer les
  appels LLM et détecter les régressions.
- Métriques RAGAS (faithfulness, answer relevance, context precision).
