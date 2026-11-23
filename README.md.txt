# analyse-candidature

Agent Mistral (Agents SDK, `mistralai-agents`) qui évalue le potentiel d'une candidature :

- **Offre d'emploi** : fournie par URL (lue via l'outil `lire_url`, recherche via `recherche_web`), par PDF joint à la conversation, ou par texte collé.
- **CV** : soit un PDF joint à la conversation, soit le **nom d'un CV de la bibliothèque « Recherche emploi »** (Mistral Studio → Libraries), lu via l'API Libraries (`cv_library`).

Les outils `recherche_web` et `lire_url` passent par l'API Conversations de Mistral (outil serveur `web_search` et lecture de `document_url`), au nom de l'utilisateur de la session.

Sortie : score d'adéquation /100, verdict (postuler / réserves / ne pas postuler), exigences bloquantes couvertes/manquantes, adéquation détaillée offre ↔ CV, points forts, écarts et risques, recommandations concrètes (lettre, mots-clés ATS, entretien).

## Déploiement géré (Mistral Cloud / Studio)

Prérequis : connecteur GitHub connecté sur le compte dans Mistral Studio, projet poussé sur GitHub, et une `MISTRAL_API_KEY` dont l'utilisateur a un rôle avec accès Workflows (Developer / Workspace Contributor).

```bash
cd analyse-candidature
git push -u origin main
export MISTRAL_API_KEY="<clé avec accès Workflows>"
uv run agents deploy
```

Le déploiement construit le `Dockerfile` du dépôt (commit poussé) et héberge l'agent sous le nom `analyse-candidature`.

## Interaction

- **Via Vibe** : lien imprimé par `agents deploy` (`https://chat.mistral.ai/managed-agents/analyse-candidature?...`), ou dans Mistral Studio → Managed Agents ; les sessions apparaissent aussi dans Studio → Managed Agents → Agent sessions.
- **En CLI** : `uv run agents chat analyse-candidature`
- **Par code** : `agents.Agent.load_from(agent_name="analyse-candidature")` puis `agent.run(...)` / `start_session()`.

Exemple de message à envoyer à l'agent :

> Analyse cette offre : https://... (poste X chez Y). Utilise mon CV « CV_PO.pdf » de la bibliothèque « Recherche emploi ». Dois-je postuler ?