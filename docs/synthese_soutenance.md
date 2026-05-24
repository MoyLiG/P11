# Synthèse soutenance — POC RAG Puls-Events

> Antisèche personnelle. Reprend les éléments **à jour** du projet
> (chiffres et choix finaux). Organisée par thème + formulations prêtes
> à dire + réponses aux questions de la grille.

---

## 0. Pitch d'ouverture (30 secondes)

« J'ai réalisé un POC de chatbot RAG pour Puls-Events : il répond en
langage naturel à des questions sur les événements culturels d'Open
Agenda, sur la Loire-Atlantique. La stack imposée — LangChain, Mistral,
FAISS — est orchestrée en un pipeline reproductible sous Docker.
Le système est évalué sur un jeu de questions/réponses annoté :
100 % de hit_rate retriever, 0,89 de similarité, 4,15/5 au jugement LLM,
et 100 % de refus correct sur les questions hors-domaine. »

---

## 1. Contexte & cadrage

- **Besoin métier** : chatbot de recommandation d'événements culturels,
  augmenté par les données Open Agenda (RAG).
- **Périmètre géographique** : région Pays de la Loire, resserrée sur le
  département Loire-Atlantique. Justification : volume riche + diversité
  culturelle (Nantes, Saint-Nazaire, presqu'île guérandaise) + éviter le
  biais parisien attendu.
- **Volumes mesurés sur l'API** (à dire si on challenge le choix géo) :
  Pays de la Loire 19 927 events à venir, Loire-Atlantique 13 272,
  Nantes 8 892 — à comparer à l'Île-de-France entière : 8 036. La région
  ligérienne est très bien couverte sur Open Agenda.
- **Source** : dataset Opendatasoft `evenements-publics-openagenda`
  (1,1 M enregistrements au catalogue, 45 champs, accès public sans
  token). Choisi plutôt que l'API Open Agenda native (qui demande un
  compte) pour la simplicité, sans perte fonctionnelle.
- **Filtre temporel** : mode « upcoming » = événements à venir ou en
  cours (`lastdate_end >= aujourd'hui` ET `firstdate_begin <= aujourd'hui
  + 365 j`). C'est un **choix produit** : pour un chatbot de découverte,
  on veut ce qui arrive, pas l'historique. Le mode « historical » reste
  disponible en configuration.

**À savoir** : `Le Chat` (interface chat Mistral) et `La Plateforme`
(console.mistral.ai, l'API) sont deux produits distincts. L'accès API
ne vient pas de l'abonnement Le Chat.

---

## 2. Architecture

Deux temps :

1. **Batch (reconstruction de l'index sur demande)** :
   Opendatasoft → ingestion → preprocessing (nettoyage + filtres) →
   chunking → embeddings Mistral → index FAISS persisté.
2. **Runtime (réponse à une question)** :
   question → retriever hybride → contexte balisé → LLM Mistral →
   réponse + sources citées.

Orchestration : LangChain. Exposition : CLI + app Streamlit.
Reproductibilité : Docker (image `python:3.12-slim`, utilisateur
non-root, volumes pour les données).

---

## 3. Choix techniques justifiés

| Couche | Choix | Justification (à dire) |
|---|---|---|
| Index vectoriel | FAISS `IndexFlatL2` | recherche exacte, suffisant pour notre échelle (< 100k chunks) |
| Embeddings | `mistral-embed` (1024 dim) | imposé ; bonne qualité sur le français |
| LLM | `mistral-small-latest`, T=0.2 | rapport qualité/coût optimal pour un POC |
| Chunking | Recursive 1200 / 80 | adapté aux descriptions Open Agenda (souvent courtes) |
| Retriever | **Hybride BM25 + dense MMR**, fusion RRF (0,4 / 0,6) | corrige la sensibilité du dense à la formulation ; BM25 capte les noms propres (villes, festivals) |
| Cache | `CacheBackedEmbeddings` | rebuilds quasi gratuits (−95 % d'appels embedding) |

**Phrase clé sur le retriever hybride** : « Le retriever dense seul est
sensible à la formulation : "concerts à Nantes" et "concerts près de
Nantes" ne renvoyaient pas les mêmes résultats. J'ai ajouté un BM25
lexical fusionné par Reciprocal Rank Fusion — il capte les
correspondances exactes de mots-clés que la similarité sémantique peut
rater. C'est le standard de l'industrie. »

**Prompt système — trois rôles** :
1. **Sécurité** : le contexte est balisé `<events>` et le LLM ignore
   toute instruction qui s'y trouverait (anti prompt-injection).
2. **Périmètre** : refus des questions sans rapport avec un événement
   (anti fuite de connaissance paramétrique).
3. **Temporel** : la date du jour + les bornes « ce week-end » / « ce
   mois-ci » sont injectées, et chaque chunk porte les dates ISO pour
   que le LLM compare rigoureusement.

---

## 4. Qualité des données (point fort)

- **Double filtre région + fraîcheur** : appliqué côté API (clause
  ODSQL) ET re-vérifié côté Python, et **testé** par pytest.
- **Filtre anti-bruit** : Open Agenda agrège des contributeurs
  hétérogènes. **275 « événements » emploi/formation/administratif
  (13 % du corpus !)** étaient en réalité du France Travail (job
  dating), des ateliers LinkedIn, « comment choisir ma mutuelle ». Je
  les ai mesurés et filtrés à la source (mots-clés titre +
  contributeur d'origine).
- **19 tests pytest** : fraîcheur, région, preprocessing, BM25, gestion
  des types (bug ndarray vs liste selon JSON/parquet).
- **Corpus final** : 1 849 documents culturels, ~2 150 chunks.

**Phrase clé** : « 13 % de mon corpus était du bruit non culturel. Je
l'ai filtré à la source plutôt que de compenser en aval. L'impact sur le
score moyen est modeste car le LLM est robuste, mais la précision du
retrieval et la fiabilité sur les cas limites s'améliorent. »

---

## 5. Évaluation & résultats

- **Jeu annoté** : 20 paires Q/R (14 in-scope avec sources annotées,
  5 hors-scope, 1 sur les dates).
- **3 métriques complémentaires** :
  - `hit_rate@k` : la source attendue est-elle dans le top-k → mesure le
    **retriever**.
  - `cosine` : similarité réponse générée vs annotée → mesure la
    **génération** (sémantique).
  - `LLM-as-judge` : note 0-5 de couverture → qualité **perçue**.
- **Résultats (moyenne sur plusieurs runs)** :
  - hit_rate@k : **100 %**
  - cosine : **0,893 ± 0,003**
  - juge : **4,15 ± 0,18 / 5**
  - refus correct hors-scope : **100 %** (Angers, Vendée, capitale
    Italie, recette, Marseille)

**Variance des métriques (à dire absolument)** : « Le juge LLM n'est pas
déterministe, même à température 0 — à cause du batching serveur et de
l'arithmétique flottante GPU. Je reporte donc une moyenne ± écart-type
sur plusieurs runs, pas un chiffre unique. Le cosine est plus stable
(±0,003) que le juge (±0,18) ; hit_rate est déterministe. »

**Limite méthodologique assumée** : les sources attendues sont annotées
à partir des candidats du retriever (pas de ground truth exhaustif sur
1 849 events). Le hit_rate mesure donc la cohérence du top-k plutôt
qu'un recall absolu.

**Décomposer retriever vs générateur (cas Q4)** : une seule question
sous-performe de façon stable — « concerts de musique classique ». En
lisant le CSV de résultats, j'ai vu que le retriever fournit les 5 bons
événements (hit=1) mais que `mistral-small` refuse à tort (« pas
trouvé »). C'est donc une **faute du générateur, pas du retriever** :
le petit modèle est parfois trop conservateur sur les requêtes
thématiques pointues. Levier v1 : `mistral-large` ou re-ranker. À dire :
« le CSV permet de savoir si c'est l'index ou le modèle qui a failli —
ici l'index est parfait, c'est le modèle. »

---

## 5 bis. RAGAS — pourquoi je ne l'ai pas utilisé

Si on me demande « pourquoi pas RAGAS ? » (vu en cours) :

- **Les consignes** demandent de mesurer la qualité « par rapport aux
  réponses annotées » (même sens + mêmes informations). Mes métriques
  maison cosine + juge couvrent exactement ce critère. RAGAS n'est pas
  demandé.
- **Vérifié sur PyPI** (ragas 0.4.3) : il dépend directement de `openai`
  et `langchain_openai`, plus `datasets` HuggingFace (~150-200 Mo).
  Importer l'écosystème d'un concurrent (OpenAI) dans un POC 100 %
  Mistral serait incohérent, pour des métriques hors-périmètre.
- **J'ai fait l'esprit de RAGAS à la main** : la *faithfulness*
  (anti-hallucination) = mon verrou de périmètre (cas « capitale de
  l'Italie ») ; la *context precision* = mon filtre anti-bruit (13 % de
  bruit retiré). RAGAS aurait chiffré automatiquement ces deux choses.
- **Gardé en reco v1** : pour industrialiser l'éval en CI nocturne, en le
  branchant explicitement sur Mistral.

À dire : « Je connais RAGAS, je sais ce qu'il apporterait — faithfulness
et context precision — et je l'ai mis en reco v1. Au POC, j'ai mesuré ce
que demande la consigne, sans importer l'écosystème OpenAI. »

## 6. Le récit du tuning (storytelling fort)

À raconter pour montrer une vraie démarche d'ingénierie :

1. Premier run d'éval → **fuite de connaissance paramétrique** : le bot
   répondait « Rome » à « capitale de l'Italie » au lieu de refuser.
2. J'ajoute un **verrou de périmètre** dans le prompt → corrige la fuite,
   mais **introduit une régression** : faux refus sur des questions
   thématiques légitimes (« concerts classiques »).
3. Les **métriques agrégées masquaient la régression** (hit_rate restait
   à 100 % car il mesure le retriever, pas la génération). Seule
   l'**analyse fine par question** l'a révélée.
4. **Re-fix chirurgical** : distinguer « question événementielle » de
   « question sans rapport ». Équilibre trouvé.

**Phrase clé** : « Évaluer un LLM, ce n'est pas regarder une moyenne.
Un fix peut corriger un cas et en casser un autre — et l'agrégat ne le
montre pas. Seule l'analyse par question le révèle. »

---

## 7. Robustesse & production

- **Rate limit Mistral** : le tier gratuit limite à ~1 req/s. J'ai
  rencontré des HTTP 429 et les ai traités par **retry exponentiel sur
  les 4 chemins** qui touchent l'API (embeddings indexation, embeddings
  éval, chat éval, chat runtime). Dette assumée : en v1, un client
  Mistral centralisé plutôt que 4 protections.
- **Coûts maîtrisés** : indexation ~0,13 €, requête ~0,001 €, projection
  prod (500 users × 5 req/j) ~47 €/mois (~30 € avec cache sémantique).
- **Audits réalisés** : coût (cost-reducer) et sécurité (OWASP LLM
  Top 10 — prompt injection, DoS/rate-limit, supply chain, scope creep).

---

## 8. Réponses aux 6 questions de la grille

**1. Comment FAISS optimise les recherches ?**
FAISS indexe des vecteurs et accélère la recherche du plus proche
voisin. `IndexFlatL2` = exact (comparaison à tous, rapide jusqu'à ~100k).
À l'échelle : `IVFFlat` (partition en cellules de Voronoï, on ne fouille
que les cellules proches), `IVFPQ` (quantification produit, compresse les
vecteurs pour réduire la RAM), `HNSW` (graphe navigable, très rapide).

**2. Limites de FAISS pour une grande quantité de données ?**
Tout est en RAM (coûteux à grande échelle) ; `IndexFlat` est linéaire en
N ; pas de mise à jour incrémentale native (reconstruction) ; pas de
recherche hybride lexicale native (d'où mon EnsembleRetriever) ; pas de
filtrage par métadonnées performant. Solutions : IVF/PQ, ou un vector
store managé (Qdrant, pgvector) pour le scale.

**3. Pourquoi LangChain ?**
Abstraction unifiée multi-fournisseurs (changer de LLM = 2 lignes),
chaînes prêtes codifiant les bonnes pratiques RAG
(`create_retrieval_chain`), `EnsembleRetriever` pour l'hybride en
10 lignes, intégration native FAISS. Inconvénient : couche
d'abstraction parfois opaque (versions qui bougent).

**4. Garantir la qualité des données dans un pipeline automatisé ?**
Double filtre (API + Python) testé ; filtre anti-bruit (13 % retiré) ;
19 tests pytest exécutables en CI ; gestion robuste des types (ndarray
vs liste) ; nettoyage HTML ; déduplication par identifiant stable.
Principe : nettoyer à la source, tester chaque contrainte.

**5. Détecter les dérives de performance d'un modèle déployé ?**
D'abord distinguer une **vraie dérive** d'une **variance de mesure**
(mesurer la variance avant de fixer des seuils, sinon fausses alertes).
Outils : éval périodique multi-run (moyenne ± écart-type), analyse fine
par question (pas que l'agrégat), suivi du taux de « pas trouvé »,
distribution des questions, RAGAS en CI, observabilité (LangSmith /
Phoenix).

**6. Quels KPI pour suivre un modèle en production ?**
Qualité : hit_rate@k, cosine, juge, taux de refus correct.
Produit : CTR sur les sources affichées, satisfaction (pouce
haut/bas), taux de « pas trouvé ». Technique : latence p95, coût par
requête, taux d'erreur API.

---

## 9. Recommandations pour la v1

- Re-ranking (`bge-reranker-v2-m3`) entre retriever et LLM.
- Historique de conversation (`RunnableWithMessageHistory`) — chiffré :
  ×2 appels LLM, ~1-2 h de dev, activable par flag.
- Indexation incrémentale (champ `updatedat`).
- Modèle plus large (`mistral-large`) pour la génération.
- Observabilité + RAGAS en CI nocturne.
- Déploiement Docker → ECS / Cloud Run / Kubernetes.
- Sécurité prod : authentification, hash SHA-256 sur l'index FAISS,
  monitoring de drift.

---

## 9 bis. Commandes Docker (démo live)

| Commande | Rôle |
|---|---|
| `docker compose build` | Construit l'image (après modif de code) |
| `docker compose run --rm rag python scripts/pipeline.py` | fetch + tests + index (jetable) |
| `docker compose run --rm -it rag python scripts/03_run_chatbot_cli.py` | CLI interactif (`-it` requis) |
| `docker compose run --rm rag python scripts/05_evaluate.py --runs 3` | évaluation multi-run |
| `docker compose up rag` | démo Streamlit (port 8501) |
| `docker compose stop` / `start` | arrêt / redémarrage (conserve le container) |
| `docker compose down [--rmi local]` | supprime container (+ image) |
| `docker compose ps` | liste les containers |

**Persistance** : `./data/` (index FAISS, cache, dump, résultats) est un
**bind mount** = dossier du disque hôte → survit à `stop`, `start`, `down`.
Seul l'état mémoire Streamlit (historique affiché, compteur) est perdu à
l'arrêt. Au redémarrage, l'index est rechargé depuis le disque (instantané).

À dire si on me demande la démo : « Je lance `docker compose up rag`,
l'index est déjà construit et persisté sur disque, donc le bot répond
immédiatement. »

## 10. Chiffres clés à retenir

| Indicateur | Valeur |
|---|---|
| Catalogue Open Agenda | 1 116 372 events |
| Corpus indexé (Loire-Atlantique, à venir, filtré) | 1 849 documents |
| Bruit emploi/formation retiré | 275 events (13 %) |
| Chunks FAISS | ~2 150 |
| hit_rate@k | 100 % |
| cosine | 0,893 ± 0,003 |
| juge LLM | 4,15 ± 0,18 / 5 |
| Refus hors-scope | 100 % |
| Coût indexation | ~0,13 € |
| Coût par requête | ~0,001 € |
| Tests pytest | 19 |
| Latence requête | ~1,5 s |
