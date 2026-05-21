# Rapport technique — POC RAG Puls-Events

**Auteur** : Morgan Le Gall
**Date** : mai 2026
**Projet** : OpenClassrooms — Data Engineer — Projet 11
**Stack** : Python 3.12 · LangChain · Mistral · FAISS · Streamlit

---

## 1. Contexte métier et objectif du POC

Puls-Events est une plateforme de découverte d'événements culturels alimentée par Open Agenda. L'entreprise souhaite tester un chatbot capable de fournir des recommandations en langage naturel à ses utilisateurs : « Quels concerts à Nantes ce mois-ci ? », « Y a-t-il des activités pour enfants ce week-end ? ». L'enjeu est de démontrer la faisabilité d'un système RAG (Retrieval-Augmented Generation) avant un éventuel déploiement à grande échelle.

Le POC doit prouver que :

1. Les données Open Agenda peuvent être ingérées, nettoyées et indexées de façon reproductible.
2. Une recherche sémantique sur ces données fournit des résultats pertinents.
3. Un LLM peut composer des réponses naturelles et fiables à partir des chunks récupérés, en citant ses sources.

Le périmètre choisi est la région **Pays de la Loire** restreinte au département **Loire-Atlantique** (44), événements dont la date de début se situe dans les 365 derniers jours, conformément aux consignes. Volume mesuré : **13 272 événements** (Opendatasoft, mesure du 2026-05-08). À titre de comparaison, l'Île-de-France entière en compte 8 036 sur la même fenêtre — la région ligérienne est largement couverte sur Open Agenda.

## 2. Architecture du système

Le système est organisé en quatre couches :

1. **Ingestion** — récupération des événements depuis l'API publique Opendatasoft (`evenements-publics-openagenda`) avec filtres ODSQL (région, fenêtre temporelle, département/ville optionnels).
2. **Preprocessing** — nettoyage HTML, normalisation Unicode, déduplication, double-vérification métier des filtres, et construction de `Document` LangChain enrichis (titre + dates + lieu + mots-clés + description).
3. **Indexation vectorielle** — chunking récursif (`chunk_size=800`, `overlap=120`), embeddings via `mistral-embed`, persistance FAISS locale (`IndexFlatL2`).
4. **Génération RAG** — récupération **hybride** (BM25 lexical + FAISS dense MMR, fusion RRF pondérée 40/60), prompt système contraint, génération via `mistral-small-latest`, retour structuré (`{answer, sources}`).

Le tout est orchestré par cinq scripts numérotés (`01_fetch_data.py` → `05_evaluate.py`) et exposé via un CLI et une app Streamlit. Un `Dockerfile` (Python 3.12-slim, utilisateur non-root, healthcheck) et un `docker-compose.yml` rendent le projet reproductible sur n'importe quel hôte sans installation locale, ce qui est le standard attendu pour une démo en soutenance et pour le déploiement.

```
Open Agenda (Opendatasoft)
        ▼
 ingestion.py  →  data/raw/events.json
        ▼
 preprocessing.py  →  Documents LangChain
        ▼
 vectorstore.py  →  data/vectorstore/{index.faiss, index.pkl}
        ▼
 rag.py  ←—  question utilisateur
   │
   └───►  réponse + sources citées
```

## 3. Choix techniques justifiés

### 3.1 Source de données — Opendatasoft plutôt qu'API Open Agenda directe

L'API Open Agenda native demande un compte et un token. Le dataset Opendatasoft `evenements-publics-openagenda` republie publiquement les mêmes données (1 116 372 enregistrements au catalogue, 45 champs) avec un endpoint moderne `/api/explore/v2.1/catalog/...` et des filtres ODSQL puissants. Pour un POC c'est un gain de temps net sans perte de fonctionnalité.

### 3.1bis Environnement d'exécution — Linux-first, Docker en cible

L'écosystème Python data engineering (LangChain, Mistral SDK, FAISS, Streamlit) est nativement Linux. Trois chemins d'installation sont documentés dans le README : (A) WSL2 / Linux / macOS — recommandé, (B) Docker — recommandé pour la démo et la prod, (C) PowerShell Windows natif — alternatif. Le `Dockerfile` (Python 3.12-slim, ~600 Mo, utilisateur non-root, healthcheck) et le `docker-compose.yml` (volumes persistants pour `data/`, limites de ressources 2 GB / 2 CPU) garantissent qu'un évaluateur peut lancer le projet sans installer Python sur sa machine. C'est aussi la base directement déployable sur ECS, Cloud Run ou Kubernetes pour la version finale.

### 3.2 FAISS comme index vectoriel

FAISS est imposé par les consignes. Le choix de l'algorithme à l'intérieur de FAISS est par contre libre. À l'échelle d'un POC (< 100 000 chunks), `IndexFlatL2` réalise une recherche **exacte** quasi-instantanée (quelques millisecondes par requête). Pour la version finale, sur des centaines de milliers ou millions de chunks, on basculerait sur `IndexIVFFlat` (recherche approximative par cellules de Voronoï, x10 à x100 plus rapide) ou `IndexIVFPQ` (quantification produit, pour réduire l'empreinte mémoire). La discussion détaillée est dans la section 6.

### 3.3 LangChain pour orchestrer

LangChain est imposé. Au-delà de l'imposition, il apporte ici trois bénéfices concrets :

- abstraction unifiée pour Mistral (`langchain-mistralai`) : on bascule vers un autre fournisseur en changeant deux lignes ;
- chaînes prêtes à l'emploi (`create_retrieval_chain`, `create_stuff_documents_chain`) qui codifient les bonnes pratiques RAG ;
- compatibilité native avec FAISS (`langchain-community.vectorstores`).

### 3.4 Modèles Mistral

| Usage | Modèle | Justification |
|---|---|---|
| Embeddings | `mistral-embed` (1024 dim) | imposé ; bonne qualité multilingue, en particulier sur le français |
| Génération RAG | `mistral-small-latest` | très bon rapport qualité / coût pour un POC ; suffisamment rapide pour la démo live |
| Juge d'évaluation | `mistral-small-latest` (T=0) | déterministe pour les notations |

`mistral-large-latest` a été écarté pour le POC à cause du surcoût (~6× plus cher) sans gain qualitatif décisif sur ces requêtes courtes. Il est recommandé pour la version finale (cf. §6).

### 3.5 Récupération MMR plutôt que similarité simple

La recherche par similarité pure tend à retourner plusieurs chunks d'un même événement (par exemple plusieurs paragraphes du Hellfest). Le LLM se retrouve alors avec un contexte redondant et propose une seule recommandation. **MMR (Maximal Marginal Relevance)** pénalise la redondance : on récupère un pool de 18 chunks puis on en sélectionne 6 qui maximisent simultanément la pertinence et la diversité. Sur Open Agenda c'est particulièrement utile car beaucoup d'événements ont des descriptions longues qui produisent plusieurs chunks.

### 3.6 Hybrid search BM25 + dense (Reciprocal Rank Fusion)

Le retriever dense pur (FAISS + embeddings) est sensible à la formulation : deux questions sémantiquement proches mais lexicalement différentes (*« concerts à Nantes »* vs *« concerts à proximité de Nantes »*) renvoient des top-k différents. Surtout faible sur les **correspondances factuelles** : noms propres (Nantes, Hellfest, La Folle Journée), dates, identifiants.

Solution : **`EnsembleRetriever`** LangChain qui combine deux retrievers via Reciprocal Rank Fusion :

- **`BM25Retriever`** (`rank_bm25`, TF-IDF amélioré, lexical exact) — capture les correspondances de mots-clés que la similarité sémantique peut rater. Index reconstruit en mémoire au démarrage à partir du parquet `data/processed/events_clean.parquet` (~1 s pour 2 000 docs, aucun appel API).
- **Le retriever dense FAISS+MMR** — robustesse sémantique sur les requêtes thématiques larges.

Pondération `bm25_weight=0.4` (60 % dense + 40 % BM25). Configurable via `config.yaml`. Mesurable via `hit_rate@k` du jeu d'évaluation : gain typique attendu +5 à +15 points sur les questions à entités nommées.

### 3.6 Prompt système contraint en français

Le prompt force trois comportements clés :

1. **citation des sources** (titre + dates + lieu) — sans cela le LLM tend à paraphraser sans tracer ;
2. **refus explicite hors-scope** (« Je n'ai pas trouvé d'événement correspondant ») — sans cela le LLM hallucine sur les questions hors région ou hors thème ;
3. **concision** (« max 6 phrases ») — pour la démo live, une réponse courte est plus convaincante.

## 4. Pipeline data — détails

### 4.1 Filtre temporel

Sémantique retenue : `firstdate_begin >= today - 365j`. Les consignes parlent d'« événements récents de moins d'un an » sans préciser sur quelle date. J'ai choisi la **date de début** plutôt que la date de fin pour respecter la lecture stricte (« événement créé/lancé il y a moins d'un an »). Une variante `lastdate_end >= today - 365j` est discutée en limites.

### 4.2 Nettoyage HTML

Le champ `longdescription_fr` contient parfois des balises `<p>`, `<br>`, `<a>`, voire des emojis encodés. BeautifulSoup `get_text(separator=" ", strip=True)` suffit ; on évite de pousser le HTML brut dans l'embedding (le bruit syntaxique réduit la qualité du vecteur sémantique).

### 4.3 Déduplication

Open Agenda peut renvoyer deux fois le même événement (ré-import, mise à jour). Dédupliqué sur `uid` (clé stable du framework), on conserve la première occurrence (l'ordre est `order_by=firstdate_begin` ASC, donc la plus ancienne).

### 4.4 Construction des Documents

Le texte indexé n'est pas la simple description : c'est un **texte enrichi** contenant titre, plage de dates, lieu, ville, département, mots-clés et description. Cette construction améliore la pertinence du retrieval — une question comme « concerts à Nantes en juin » matchera mieux un texte qui contient explicitement « Nantes » et la date dans son préambule.

## 5. Résultats du POC

> Les valeurs ci-dessous seront mises à jour après exécution end-to-end avec la clé API utilisateur. La méthodologie d'évaluation est en place ; les chiffres présentés sont des valeurs cibles attendues.

### 5.1 Volumes (mesures réelles)

- Total Open Agenda (catalogue) : 1 116 372 enregistrements.
- Loire-Atlantique (44), filtre `upcoming` (à venir / en cours) : ~2 500 événements.
- Après dédup + filtre métier : ~2 124 événements.
- Après **filtre anti-bruit** (retrait emploi/formation/admin) : **1 849 documents** (−275, soit −13 % de bruit retiré).
- Chunks FAISS (chunking 1200/80) : ~2 150 chunks.
- Note : le mode `historical` (365 derniers jours) donnait ~13 272 events bruts → ~9 948 documents → ~12 834 chunks. Le mode `upcoming` réduit fortement le volume en ne gardant que les événements pertinents pour un chatbot de découverte.

### 5.2 Performance technique

- Construction de l'index : ~5 minutes pour 2 468 chunks sur le tier gratuit Mistral (rate limit 1,1 s/requête, batch 24). Quasi-instantané sur tier payant.
- Latence requête utilisateur : ~1,5 s (retriever hybride ~50 ms + LLM ~1,4 s).
- Empreinte disque : ~15 Mo (`index.faiss` + `index.pkl`).
- Coût d'une indexation complète : environ **0,15 €** (mistral-embed à 0,10 €/M tokens × ~1,5 M tokens). Rebuilds quasi gratuits grâce au `CacheBackedEmbeddings`.

### 5.3 Qualité — sur le jeu de 20 Q/R (mesures réelles)

Résultats du run d'évaluation (`scripts/05_evaluate.py`) sur l'index `upcoming` (2 127 documents) :

| Métrique | Mesuré | Lecture |
|---|---|---|
| `hit_rate@k` (14 questions annotées + 5 hors-scope) | **100 %** | la source attendue est dans le top-k (ou refus correct) |
| `cosine` réponse générée vs annotée | **0,890** | excellente couverture sémantique |
| `judge_score` (mistral-small, 0-5) | **4,15 / 5** | bonne qualité globale (après filtre anti-bruit) |
| Taux de refus correct sur hors-scope | **100 %** (5/5) | aucune hallucination sur Angers, Vendée, Italie, recette, Marseille |

Ces chiffres sont le résultat d'un cycle de tuning itératif documenté (cf. journal J14-J16) : (1) un premier run a révélé une fuite de connaissance paramétrique (le bot répondait « Rome » à « capitale de l'Italie »), (2) un verrou de périmètre l'a corrigée mais a introduit des faux refus sur des questions thématiques, (3) un verrou chirurgical a équilibré les deux. Enseignement clé : **les métriques agrégées masquent les régressions ; seule l'analyse fine par question les révèle** (le `hit_rate@k` mesure le retriever, le `judge_score` la génération).

> **Limite méthodologique** : les `expected_source_uids` sont annotés à partir des candidats du retriever (pas de ground truth exhaustif sur 2 127 events). Le `hit_rate@k` mesure donc la *cohérence* du top-k plutôt qu'un *recall* absolu. Le cosine et le juge, eux, sont non circulaires.

**Imperfections identifiées** (juge < 5) : sur-interprétation temporelle occasionnelle (le LLM ajoute « ce week-end » quand la question ne le demande pas) et pertinence thématique parfois approximative (un débat classé comme « humour »). Pistes : affiner le prompt, re-ranker (cf. §6.2).

**Finding qualité de données + correctif** : Open Agenda Loire-Atlantique agrège des contributeurs hétérogènes ; ~30-50 % des candidats sur certaines requêtes étaient des événements **emploi/formation/administratif** (France Travail « job dating », ateliers LinkedIn, « comment choisir ma mutuelle »...) qui polluaient le retrieval. Un filtre `filter_noise()` a été ajouté à l'ingestion : exclusion par mots-clés de titre et par contributeur d'origine (`originagenda_title`), listes configurables dans `config.yaml`. Ce nettoyage améliore la pertinence du contexte fourni au LLM (cf. journal J17 pour l'avant/après mesuré).

## 6. Limites du POC et recommandations pour la version finale

### 6.1 Limites identifiées

| Limite | Impact | Mitigation |
|---|---|---|
| Filtre `firstdate_begin` only | un événement long démarré il y a > 1 an mais en cours est exclu | basculer sur `lastdate_end >= today - 365j` |
| `IndexFlatL2` ne scale pas | latence linéaire en N | passer à IVFFlat / IVFPQ au-delà de 100k chunks |
| Pas de re-ranking | top-k parfois bruyant | ajouter un re-ranker (BGE, Cohere) entre retriever et LLM |
| Pas de monitoring | dérive non détectée | LangSmith ou Phoenix (Arize) en production |
| Coût LLM linéaire en requêtes | risque de scale-up | cache sémantique (GPTCache), fallback FAQ |
| Données Open Agenda incomplètes (tarif, accessibilité) | réponses imprécises | enrichir avec d'autres sources (sites lieux) |

### 6.2 Recommandations chiffrées pour la v1

0. **Historique de conversation (trade-off POC assumé)** — la chaîne actuelle est volontairement stateless, conformément à l'énoncé du brief. L'extension est prête : `create_history_aware_retriever` LangChain + `RunnableWithMessageHistory` (backend `RedisChatMessageHistory` ou `SQLChatMessageHistory`) ajoutent l'historique avec ~30 lignes de code. Impact chiffré : ×1,7 sur les tokens input (8 paires de turns), ×2 sur les appels LLM par requête (reformulation + génération), latence p50 ~1,5 s → ~2,8 s, coût ~0,001 € → ~0,002-0,003 € par requête. Effort ~1-2 h. Activable derrière un flag de configuration sans toucher au comportement POC actuel.
2. **Re-ranker dédié** — un modèle léger comme `bge-reranker-v2-m3` après le retriever réduit fortement le bruit. Latence +200 ms, qualité +10 à +20 % sur le judge_score.
3. **Modèle plus large pour la génération** — `mistral-large-latest` ou `mistral-medium`. Surcoût ~6×, mais meilleure formulation et capacité de raisonnement.
4. **Indexation incrémentale** — Open Agenda met à jour quotidiennement. Stocker le `updatedat` de chaque événement, ne ré-embedder que les nouveaux et modifiés.
5. **Évaluation automatisée RAGAS** — faithfulness, answer relevance, context precision/recall. Intégrable dans une CI nocturne pour détecter les régressions.
6. **Monitoring de drift** — surveiller la distribution des questions reçues et la pertinence du top-1 source. Alerte si le pourcentage de « pas trouvé » dépasse un seuil.
7. **KPI produit** — taux de clic sur les sources affichées (le user clique-t-il sur l'événement recommandé ?), temps moyen avant refus utilisateur, satisfaction (thumbs up/down).

## 7. Conclusion

Le POC démontre :

1. Que la stack imposée (LangChain + Mistral + FAISS) est parfaitement adaptée au cas d'usage Puls-Events.
2. Que le pipeline est entièrement reproductible (un script reconstruit l'index à la demande, conformément aux consignes).
3. Que la qualité des réponses est suffisante pour justifier un investissement en v1, sous réserve d'ajouter re-ranking, hybrid search et observabilité.
4. Que les coûts opérationnels sont maîtrisables (~0,30 € par construction d'index, ~1 centime par requête utilisateur).

Les recommandations §6 dessinent une roadmap cohérente sur 6 à 12 semaines pour passer du POC à une v1 industrielle.

---

**Annexes**

- Fichiers de code : `src/pulsevents_rag/*.py`, `app.py`, `scripts/*.py`.
- Tests unitaires : `tests/test_data_*.py`, `tests/test_preprocessing.py`, `tests/test_vectorstore.py`.
- Jeu Q/R annoté : `data/eval/qa_dataset.json` (20 paires).
- Configuration : `config.yaml` (paramètres centralisés).
