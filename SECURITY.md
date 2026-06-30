# Security Policy

## Statut

Ce projet est un **POC académique** (OpenClassrooms, formation Data Engineer).
Il n'est pas destiné à un déploiement en production en l'état. Un audit
complet a été réalisé et les mesures de durcissement minimales ont été appliquées.

## Modèle de menace retenu

| Surface | Acteur | Risque |
|---|---|---|
| Données ingérées (Open Agenda) | Publisher malveillant | **Prompt injection indirecte** |
| Interface Streamlit | Utilisateur public (si exposé) | DoS, abus de coût API |
| Fichier `index.pkl` FAISS | Attaquant filesystem local | RCE via désérialisation |
| Clé API Mistral (`.env`) | Tout porteur du fichier | Abus de quota |
| Logs (questions utilisateur) | Tiers ayant accès aux logs | Fuite de PII éventuelle |

## Mesures appliquées

1. **Prompt système renforcé** ([src/pulsevents_rag/rag.py](src/pulsevents_rag/rag.py)) :
   contexte balisé `<events>...</events>` et instruction explicite d'ignorer
   toute meta-commande qui apparaîtrait dans la donnée.
2. **Cap longueur question** : `max_question_length=500` côté CLI et Streamlit.
3. **Cap output LLM** : `max_tokens=400` sur `ChatMistralAI` (anti-runaway).
4. **Rate limit session Streamlit** : `MAX_QUERIES_PER_SESSION=30`.
5. **Validation scheme URL** : seuls `http://` et `https://` sont rendus dans
   les sources Streamlit ([app.py:_safe_url](app.py)).
6. **Logs tronqués** : `logger.info` ne loggue que les 60 premiers caractères
   de la question.
7. **`.env` gitignored** : aucune clé ne peut être commitée.
8. **Dépendances scannées** : `pip-audit` sur `requirements.txt`,
   `python-dotenv` upgrade à 1.2.2 (CVE-2026-28684).

## Risques résiduels acceptés (POC)

| ID | Risque | Justification de l'acceptation |
|---|---|---|
| H3 | `allow_dangerous_deserialization=True` sur FAISS | POC local, attaquant filesystem a déjà tout. Mitigé en prod par hash SHA-256 + migration vers Chroma/Qdrant. |
| M4 | Données envoyées à Mistral (privacy) | Inhérent au POC ; mention explicite dans README + politique privacy en prod. |
| LOW | Pas de CSP / HSTS sur Streamlit | OK pour localhost. Mettre un reverse proxy en prod. |

## Avant un déploiement public

- [ ] Authentification (streamlit-authenticator ou reverse proxy)
- [ ] Reverse proxy (nginx / Caddy) avec headers CSP, HSTS, X-Frame-Options, Referrer-Policy
- [ ] Rate limit global (par IP, pas seulement par session)
- [ ] Budget alert sur console.mistral.ai (< 5 €/jour par défaut)
- [ ] Politique de confidentialité visible (mention envoi à Mistral)
- [ ] CI : `pip-audit` à chaque push
- [ ] Tests adversariaux dans `qa_dataset.json` (prompt injection)
- [ ] Hash SHA-256 sur l'index FAISS (`index.sha256`) vérifié au chargement
- [ ] Migration FAISS → Chroma/Qdrant (pas de pickle)

## Reporting

Toute découverte de vulnérabilité peut être signalée à :
**moy.morgan@gmail.com** (sujet : `[SECURITY] POC RAG Puls-Events`).
