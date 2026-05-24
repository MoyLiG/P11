# Déroulé du projet — POC RAG Puls-Events

> Document narratif et pédagogique. Il raconte **comment** le projet a été
> mené, étape par étape. Sa vocation est servir de référentiel : comprendre
> non seulement *quoi* a été produit, mais *pourquoi* et *dans quel ordre*.

---

## Étape 0 — Lecture du brief et premières interrogations

Le projet arrive sous la forme d'un courriel d'un manager fictif (Jérémy)
demandant un POC RAG. Avant d'écrire la moindre ligne de code, on prend
20 minutes pour :

1. **Lire intégralement la consigne** (mission + étapes + livrables + grille
   de soutenance). Les questions de la grille sont précieuses : elles
   révèlent ce sur quoi l'évaluateur va challenger (ici : pourquoi FAISS,
   pourquoi LangChain, comment garantir la qualité des données, comment
   monitorer en prod).
2. **Lister les contraintes dures** : stack imposée (LangChain + Mistral +
   FAISS), fenêtre temporelle (< 1 an), région libre, livrables précis.
3. **Lister les questions ouvertes** : périmètre géographique optimal,
   source Open Agenda à privilégier, gestion de la clé API.

C'est aussi à ce stade qu'on identifie les pièges potentiels : le filtre
temporel sur quelle date ? quel volume va-t-on charger ? a-t-on une clé
API utilisable ?

## Étape 1 — Cadrage du périmètre

Le brief laisse libre choix sur la région. On évalue trois candidats :

- Paris : très dense, mais cliché, et l'évaluateur va le voir venir.
- Île-de-France : volume max, mais lourd à embedder.
- **Pays de la Loire** : choisi.

La justification tient en trois points :

1. **Volume suffisant** (Nantes, Angers, Le Mans, Saint-Nazaire, La Roche
   sur Yon, festivals d'été, etc.) — entre 3 000 et 6 000 événements
   typiquement, ce qui donne au RAG matière à travailler.
2. **Diversité culturelle** — du classique haut de gamme (La Folle Journée)
   au rock alternatif (Hellfest), en passant par l'art contemporain
   (Voyage à Nantes), le théâtre en plein air (Festival d'Anjou), les
   musiques du monde (Les Escales). Ça fait des démos vivantes.
3. **Originalité** — moins attendu que Paris, ça démontre que le système
   marche partout, pas seulement sur la zone où il y a 10× plus de
   données.

Ce cadrage est paramétré dans `config.yaml` : la région est une variable,
on peut basculer ailleurs en changeant une seule ligne.

## Étape 2 — Exploration de la source

Open Agenda propose deux modes d'accès :

- **API native** — nécessite création de compte et token.
- **Dataset Opendatasoft** `evenements-publics-openagenda` — réplique
  publique avec endpoint REST moderne et filtres ODSQL puissants.

On vérifie manuellement avec un appel `WebFetch` que :

- Le dataset existe (1 116 372 enregistrements au catalogue).
- Les 45 champs disponibles couvrent les besoins : `title_fr`,
  `longdescription_fr`, `daterange_fr`, `firstdate_begin`, `lastdate_end`,
  `location_region`, `location_department`, `location_city`,
  `keywords_fr`, `canonicalurl`, `uid`.
- Le filtre `where=` accepte des clauses du type `location_region="Pays de la Loire" AND firstdate_begin >= "2025-05-08"`.

Décision : on utilise Opendatasoft. C'est plus simple, plus rapide à
démarrer, et la qualité des données est identique.

## Étape 3 — Conception de l'architecture

On dessine l'architecture cible **avant** de coder :

```
ingestion → preprocessing → chunking → embeddings → FAISS
                                                      ↓
question → retriever (MMR) → context → LLM → réponse + sources
```

Choix techniques pris à ce stade :

- **Chunking récursif** (`RecursiveCharacterTextSplitter` LangChain),
  `chunk_size=800` / `overlap=120`. Pourquoi 800 ? Les descriptions
  Open Agenda font typiquement 300 à 2 000 caractères ; 800 capture un
  événement entier dans la majorité des cas, sans dépasser le contexte
  utile.
- **MMR (Maximal Marginal Relevance)** plutôt que similarité simple. Sur
  Open Agenda, plusieurs chunks d'un même événement peuvent dominer le
  top-k. MMR sélectionne 4 chunks parmi 20 en privilégiant la diversité.
- **`mistral-small-latest`** plutôt que `large` pour le POC. Le `large`
  coûte ~6× plus, sans gain qualitatif décisif sur des questions courtes.

## Étape 3bis — Choix d'environnement : Linux-first, Docker en cible

Première erreur d'auto-cohérence : le README initial mettait PowerShell
en premier. L'utilisateur a levé la question à juste titre.

L'écosystème data engineering Python 2026 est **Linux-first** :

- 95 % des tutos LangChain / Mistral / FAISS / HuggingFace sont en bash ;
- déploiement = Docker = Linux ;
- `faiss-cpu` a historiquement des wheels Linux plus stables ;
- les utilitaires Unix (`curl`, `jq`, `grep`, `awk`) sont partout dans les
  pipelines data ;
- la même commande tourne sur la machine du dev, en CI, en prod.

**Décisions** :

1. **README réorganisé** : WSL2/Linux/macOS en path principal, Docker en
   path recommandé pour la démo et la prod, PowerShell en alternatif.
2. **`Dockerfile`** ajouté : `python:3.12-slim`, dépendances système
   minimales (`libgomp1` pour `faiss-cpu`), utilisateur non-root pour la
   sécurité, healthcheck Streamlit.
3. **`docker-compose.yml`** : un service `rag`, volumes pour persister
   `data/raw`, `data/processed`, `data/vectorstore`, `data/embed_cache`
   entre runs, limites de ressources en défense en profondeur.
4. **`.dockerignore`** : réduit le contexte de build de ~95 %.

Bénéfice direct : un évaluateur lance la démo avec
`docker compose run --rm rag python scripts/pipeline.py` puis
`docker compose up rag` — aucune installation Python locale requise.

**Aide-mémoire des commandes Docker** :

| Commande | Rôle |
|---|---|
| `docker compose build` | Construit l'image (après modif de code) |
| `docker compose run --rm rag python scripts/pipeline.py` | fetch + tests + index (jetable) |
| `docker compose run --rm -it rag python scripts/03_run_chatbot_cli.py` | CLI interactif (`-it`) |
| `docker compose run --rm rag python scripts/05_evaluate.py --runs 3` | évaluation multi-run |
| `docker compose up rag` | démo Streamlit (port 8501) |
| `docker compose stop` / `start` | arrête / redémarre (conserve le container) |
| `docker compose down [--rmi local]` | supprime container (+ image) |
| `docker compose ps` | liste les containers |

**Persistance** : `./data/` est un *bind mount* (dossier du disque hôte) —
l'index FAISS et le cache survivent à `stop`/`start`/`down`. Seul l'état
mémoire Streamlit (session, historique) est éphémère ; l'index est
rechargé depuis le disque au redémarrage, sans ré-indexation.

## Étape 4 — Squelette du projet

Plutôt que de jeter tout le code dans un seul script, on adopte une
**structure professionnelle** :

```
src/pulsevents_rag/   (package réutilisable)
  config.py           ingestion.py    preprocessing.py
  vectorstore.py      rag.py          evaluation.py
scripts/              (orchestrateurs CLI numérotés)
tests/                (pytest)
data/                 (raw, processed, vectorstore, eval)
docs/                 (livrables documentaires)
```

Cette structure permet :

- d'**importer** les modules dans Streamlit, dans les tests, dans des
  notebooks d'analyse, sans copier-coller ;
- de **tester** chaque couche indépendamment ;
- de **paramétrer** via un `config.yaml` central plutôt que d'avoir des
  constantes éparpillées.

Le `requirements.txt` épingle toutes les versions (langchain==0.3.7,
faiss-cpu==1.9.0, mistralai==1.2.5, etc.) pour garantir la
reproductibilité.

## Étape 5 — Implémentation du pipeline data

### Ingestion

`src/pulsevents_rag/ingestion.py` expose `fetch_open_agenda(settings)`.
Trois subtilités :

- **Pagination** : l'API limite à 100 enregistrements par requête. On
  paginate via `offset` jusqu'à `max_records` (5 000 par défaut).
- **Retry** : `tenacity` avec backoff exponentiel sur les erreurs réseau.
- **Courtoisie** : 200 ms de pause entre pages pour ne pas se faire
  rate-limiter.

La clause `where=` est composée dynamiquement à partir de la config
(région obligatoire, département/ville optionnels, fenêtre temporelle).

### Preprocessing

`preprocessing.py` enchaîne :

1. **Nettoyage HTML** — BeautifulSoup `get_text()`. Les descriptions
   Open Agenda contiennent souvent des `<p>`, `<br>`, `<a>`. Embedder le
   HTML brut pollue le vecteur sémantique.
2. **Normalisation Unicode** — NFKC + collapse des espaces multiples.
3. **Déduplication** — par `uid`, on garde la première occurrence.
4. **Double filtre métier** — région et fraîcheur, indépendamment du
   filtre déjà fait côté API. C'est ce double filtre qui est testé par
   les tests `pytest`.
5. **Construction des `Document` LangChain** — texte enrichi (titre +
   plage de dates + lieu + ville/département + mots-clés + description)
   et metadata structurée (uid, url, dates pour citation).

### Tests obligatoires

Les consignes demandent explicitement un test « les données respectent
< 1 an et la région choisie ». On le fait en deux fichiers :

- `tests/test_data_freshness.py` — assert sur les dates.
- `tests/test_data_geography.py` — assert sur la région.

Chacun a deux variantes : une sur les fixtures synthétiques (rapide,
toujours exécutée) et une sur le dump réel (skippée si absent). Cette
double approche permet de :

- valider la logique sans dépendre du réseau ;
- valider la prod en exécutant les tests sur le dump réel.

## Étape 6 — Construction de l'index

`vectorstore.py` enchaîne split → embeddings → FAISS → save_local.

Trois points d'attention :

1. **Cle API absente** — on lève une `ValueError` claire avec un message
   qui pointe vers https://console.mistral.ai. Indispensable pour
   l'utilisateur final qui découvre le projet.
2. **Pickle FAISS** — `FAISS.load_local` exige
   `allow_dangerous_deserialization=True` (protection LangChain contre
   les pickles malveillants). On accepte le risque puisque c'est notre
   propre fichier.
3. **Persistence** — l'index est sauvé dans `data/vectorstore/`
   (gitignore). La consigne demande explicitement de pouvoir
   reconstruire la base sur demande : c'est exactement ce que fait
   `02_build_index.py`.

## Étape 7 — Chaîne RAG

`rag.py` assemble :

- un **retriever hybride** : `EnsembleRetriever` qui fusionne via
  Reciprocal Rank Fusion (a) un `BM25Retriever` (lexical, capte les
  noms propres et correspondances factuelles) et (b) le retriever
  dense FAISS+MMR (sémantique, k=6 sur fetch_k=18). Pondération
  40 % BM25 + 60 % dense ;
- un **prompt système** strict en français qui force la citation des
  sources (titre + dates + lieu) et le refus explicite hors-scope ;
- un **LLM** `ChatMistralAI` (mistral-small, T=0.2) ;
- une **chaîne** via `create_retrieval_chain` + `create_stuff_documents_chain`.

Le passage du retriever dense-only au hybride a été motivé par un cas
de test au moment de la mise au point : la question *« concerts à
Nantes »* ne retrouvait pas un événement à La Bottière (quartier de
Nantes) alors que la question *« concerts à proximité de Nantes »*
le retrouvait. Le dense est trop sensible à la formulation ; BM25
résout le problème en captant le mot-clé « Nantes » directement.

La méthode `RagPipeline.answer(question)` retourne un objet
`RagAnswer(question, answer, sources)` où les sources sont dédupliquées
par `uid` (chunks d'un même événement collapsent).

## Étape 8 — Démo

Deux interfaces livrées :

- **CLI** (`scripts/03_run_chatbot_cli.py`) — pratique pour les tests
  rapides, et pour la partie technique de la soutenance si l'évaluateur
  veut voir « les tripes ».
- **Streamlit** (`app.py`) — pratique pour la démo "produit" devant les
  équipes Marketing et Produit. Sidebar avec config courante,
  `st.chat_input` pour la conversation, `st.expander` pour afficher les
  sources cliquables (lien Open Agenda).

## Étape 9 — Évaluation

On construit un jeu de **20 paires Q/R annotées** dans
`data/eval/qa_dataset.json` :

- 5 catégories métier : ville, thématique, date, lieu fin, événement
  spécifique.
- 3 questions hors-scope : Marseille, recette de cuisine, capitale d'Italie.

Les `expected_source_uids` sont laissés vides pour le moment ; ils
seront enrichis manuellement après la première construction de l'index,
quand on connaîtra les `uid` réellement présents.

`evaluation.py` calcule trois métriques :

| Métrique | Calcul |
|---|---|
| `hit_rate@k` | uid attendu présent dans les sources retournées |
| `cosine` | similarité entre embeddings (mistral-embed) de la réponse générée et de la réponse annotée |
| `judge_score` | un appel mistral-small (T=0) note 0-5 la couverture |

Sortie : `data/eval/results.csv` + résumé console. Mode multi-run
(`--runs N`) pour gérer la variance du juge LLM (moyenne ± écart-type).

**Pourquoi pas RAGAS ?** RAGAS est le framework standard d'évaluation
RAG (faithfulness, answer relevancy, context precision/recall). Mais les
consignes demandent de comparer la réponse à l'annotation (même sens +
mêmes informations) — couvert par cosine + juge. Et vérification PyPI
faite : RAGAS dépend de `openai` + `langchain_openai` + `datasets`
HuggingFace, ce qui importerait l'écosystème d'un concurrent dans un POC
100 % Mistral, pour des métriques hors-périmètre. Choix : éval maison au
POC, RAGAS en reco v1. À noter qu'on a réalisé « l'esprit RAGAS »
manuellement (faithfulness ≈ verrou de périmètre, context precision ≈
filtre anti-bruit).

## Étape 10 — Documentation

Quatre documents produits :

- **README.md** — point d'entrée pour qui découvre le projet : install,
  config, usage, tests, FAQ.
- **rapport_technique.docx** — rapport académique de 5-10 pages :
  contexte, architecture, choix justifiés, résultats, limites,
  recommandations.
- **deroule_projet.docx** — *ce document*. Narratif pédagogique pour
  comprendre l'élaboration et la chronologie.
- **journal.md** — journal de bord chronologique avec décisions et
  apprentissages.
- **presentation.pptx** — 12 slides pour la soutenance orale (15 min).

## Étape 11 — Préparation soutenance

La grille mentionne explicitement six questions probables :

1. *Comment FAISS optimise les recherches ?* → IVF, PQ, HNSW.
2. *Limites de FAISS à grande échelle ?* → mémoire, IndexFlat linéaire,
   absence native de mises à jour incrémentales.
3. *Pourquoi LangChain ?* → abstraction multi-fournisseur, chaînes
   prêtes, écosystème.
4. *Qualité des données dans un pipeline ?* → tests unitaires,
   double-filtre, monitoring de schéma, alertes sur taux de nullité.
5. *Détecter les dérives ?* → distribution des questions, pertinence
   du top-1, taux de refus, RAGAS périodique.
6. *KPI prod ?* → CTR sur les sources, satisfaction utilisateur,
   latence p95, coût/requête, taux de hallucination détecté.

Chaque question doit avoir une réponse courte préparée (30 secondes
max), avec une réponse longue en réserve si le challenger insiste.

## Bilan

Le projet a été mené en respectant les principes posés dès J0 :

- **Plan d'abord, code ensuite** — le plan exhaustif a évité les revirs.
- **Tests dès le début** — les contraintes du brief (< 1 an, région) sont
  encodées en tests `pytest` exécutables.
- **Configuration externalisée** — la migration vers une autre région ou
  un autre modèle ne demande aucune modification de code.
- **Documentation au fil de l'eau** — chaque module a ses docstrings,
  chaque décision est tracée dans le journal.
- **Reproductibilité totale** — `requirements.txt` épinglé, pipeline
  end-to-end automatisé, données régénérables.

Le système est prêt pour la soutenance et pour servir de base à une v1
industrielle.
