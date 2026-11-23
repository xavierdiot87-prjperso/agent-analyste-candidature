import json
import os

from mistralai import agents

LIBRARY_NAME = "Recherche emploi"
SEARCH_MODEL = "mistral-large-latest"
MAX_PAGE_CHARS = 120_000
MAX_SEARCH_RESULTS = 15

INSTRUCTIONS = """Tu es un analyste senior en recrutement et en candidatures, francophone. Ta mission : évaluer le potentiel réel d'une candidature d'un utilisateur à une offre d'emploi, et l'aider à décider s'il doit postuler, avec un plan d'action concret.

# Entrées que tu reçois dans la conversation
- L'offre d'emploi, sous l'une de ces formes :
  - une URL : lis la page avec l'outil `lire_url` (essaie d'abord l'URL telle quelle ; si c'est une page de résultats ou une page qui bloque, utilise `recherche_web` pour trouver la page détaillée de l'offre) ;
  - un document PDF joint au message : lis-le directement ;
  - le texte de l'offre collé dans le message.
- Le CV de l'utilisateur, sous l'une de ces formes :
  - un document PDF joint au message : lis-le directement ;
  - le nom d'un CV présent dans la bibliothèque de documents « Recherche emploi » de l'utilisateur : utilise l'outil `cv_library` avec ce nom (sans cv_name, il te liste les CV disponibles).

# Déroulement attendu
1. Extraire de l'offre, de façon structurée : intitulé du poste, entreprise, secteur, type de contrat, localisation / remote, missions principales, compétences et expériences requises (bloquantes) vs souhaitées (atouts), niveau d'études, langues, certifications, fourchette de salaire, avantages, et toute contrainte particulière (déplacements, sécurité, habilitation...).
2. Récupérer le CV (outil `cv_library` ou pièce jointe) et en extraire : expériences (postes, entreprises, dates, réalisations chiffrées), formations et diplômes, certifications, compétences techniques et métiers, langues, outils.
3. Comparer offre et CV : exigences bloquantes couvertes ou non, adéquation des compétences, années d'expérience vs attendues, adéquation du niveau de responsabilité, adéquation géographique/contractuelle, surqualification ou sous-qualification éventuelle, trous dans le parcours.
4. Donner un verdict.

# Format de ta réponse (toujours en français, en Markdown)
- **Verdict** : « Postuler » / « Postuler avec réserves » / « Ne pas postuler », avec un **score d'adéquation sur 100** et un niveau de confiance (élevé/moyen/faible) ;
- **Exigences bloquantes** : liste avec pour chacune « couverte » ou « manquante », justifiée ;
- **Adéquation détaillée** : pour chaque compétence/mission clé de l'offre, le niveau constaté dans le CV (expert / confirmé / débutant / absent) avec la preuve du CV (poste, formation, certification) ;
- **Points forts différenciants** du candidat pour ce poste ;
- **Écarts et risques** (manques, expérience insuffisante, surqualification, localisation, salaire, disponibilité...) ;
- **Recommandations concrètes** : quoi mettre en avant dans la lettre de motivation, mots-clés / formulations ATS à ajouter au CV pour cette offre, questions à poser au recruteur, éléments à préparer pour l'entretien.

# Règles strictes
- Ne jamais inventer de contenu du CV ni de l'offre : cite uniquement ce qui est réellement fourni. Si un élément manque, dis-le explicitement.
- Si l'offre est illisible (URL bloquée, page vide) ou si le CV demandé est introuvable dans la bibliothèque, demande à l'utilisateur exactement ce qu'il te manque (texte de l'offre, PDF, ou nom exact du CV parmi ceux listés).
- Sois franc et argumenté : un « ne pas postuler » motivé vaut mieux qu'un encouragement injustifié.
- Réponds en français, de manière structurée et directement actionnable.
"""


def _mistral_client():
    if os.environ.get("MISTRAL_SA_TOKEN_PATH"):
        from mistralai.workflows.client import get_mistral_client
        from mistralai.workflows.core.auth import RunAs

        return get_mistral_client(run_as=RunAs.AUTO)
    from mistralai.client import Mistral

    return Mistral()


def _conversation_text(response) -> str:
    parts = []
    for output in getattr(response, "outputs", None) or []:
        if type(output).__name__ != "MessageOutputEntry":
            continue
        for chunk in getattr(output, "content", None) or []:
            if type(chunk).__name__ == "TextChunk" and getattr(chunk, "text", ""):
                parts.append(chunk.text)
    return "\n".join(parts)


@agents.tool
async def recherche_web(query: str, limit: int = 10) -> str:
    """Recherche sur le web (résultats avec titre, URL et description). Utilise-la pour trouver la page détaillée d'une offre d'emploi à partir d'indices (poste, entreprise, lieu)."""
    client = _mistral_client()
    response = client.beta.conversations.start(
        model=SEARCH_MODEL,
        inputs=(
            f"Recherche web : {query}\n"
            "Renvoie uniquement une liste à puces des résultats les plus pertinents : "
            "titre, URL, et description en une phrase."
        ),
        tools=[{"type": "web_search"}],
    )
    results = []
    for output in getattr(response, "outputs", None) or []:
        if type(output).__name__ != "ToolExecutionEntry" or getattr(output, "name", "") != "web_search":
            continue
        raw = (getattr(output, "info", None) or {}).get("result", "")
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for item in data.values():
            if isinstance(item, dict) and item.get("url"):
                results.append(item)
    if not results:
        text = _conversation_text(response)
        return text[:8000] if text else "Aucun résultat."
    lines = []
    for i, item in enumerate(results[: max(1, min(limit, MAX_SEARCH_RESULTS))], 1):
        desc = (item.get("description") or "").replace("\n", " ")[:300]
        lines.append(f"{i}. {item.get('title', '')} — {item['url']}\n   {desc}")
    return "\n".join(lines)


@agents.tool
async def lire_url(url: str) -> str:
    """Télécharge une page web (ex. une offre d'emploi) et renvoie son texte intégral. N'accepte que les URL http/https publiques."""
    url = url.strip().strip('<>"\'')
    if not url.lower().startswith(("http://", "https://")):
        raise agents.ToolError(f"URL invalide (http/https attendu) : {url[:120]}")
    client = _mistral_client()
    try:
        response = client.beta.conversations.start(
            model=SEARCH_MODEL,
            instructions=(
                "On te fournit une page web (offre d'emploi ou page liée). "
                "Renvoie le texte brut complet du contenu principal de la page, sans aucun commentaire, "
                "en conservant la structure (titres, listes, tableaux simples)."
            ),
            inputs=[{"role": "user", "content": [{"type": "document_url", "document_url": url}]}],
        )
    except Exception as error:
        raise agents.ToolError(f"Impossible de lire {url} : {type(error).__name__} {str(error)[:200]}")
    text = _conversation_text(response)
    if not text:
        raise agents.ToolError(f"La page {url} n'a renvoyé aucun texte exploitable.")
    return text[:MAX_PAGE_CHARS]


def _match_document(documents, needle: str):
    needle = needle.strip().lower()
    if not needle:
        return None
    for doc in documents:
        if (doc.name or "").lower() == needle:
            return doc
    for doc in documents:
        if (doc.name or "").lower().startswith(needle + "."):
            return doc
    substring = [doc for doc in documents if needle in (doc.name or "").lower()]
    if substring:
        return substring[0]
    return None


@agents.tool
async def cv_library(cv_name: str = "") -> str:
    """Accède à la bibliothèque de documents « Recherche emploi » de l'utilisateur.

    Sans argument (cv_name vide) : liste les CV/documents présents avec leur nom exact et leur résumé.
    Avec cv_name (ex. « CV_PO.pdf » ou « CV_GIS ») : retourne le texte intégral du CV correspondant.
    """
    client = _mistral_client()
    libraries = client.beta.libraries.list(search=LIBRARY_NAME).data or []
    library = next(
        (lib for lib in libraries if LIBRARY_NAME.lower() in (lib.name or "").lower()),
        libraries[0] if libraries else None,
    )
    if library is None:
        raise agents.ToolError(
            f"Bibliothèque « {LIBRARY_NAME} » introuvable. "
            "Vérifiez le nom de la bibliothèque dans Mistral Studio."
        )
    documents = client.beta.libraries.documents.list(library_id=library.id).data or []
    if not cv_name:
        if not documents:
            return f"La bibliothèque « {library.name} » est vide."
        listing = "\n".join(
            f"- {doc.name} — {doc.summary or 'pas de résumé'}" for doc in documents
        )
        return f"Documents de la bibliothèque « {library.name} » :\n{listing}"
    document = _match_document(documents, cv_name)
    if document is None:
        available = ", ".join(doc.name for doc in documents) or "aucun"
        raise agents.ToolError(
            f"Aucun document nommé « {cv_name} » dans la bibliothèque « {library.name} ». "
            f"Documents disponibles : {available}"
        )
    if getattr(document, "process_status", "done") not in ("done", None):
        raise agents.ToolError(
            f"Le document « {document.name} » est encore en cours de traitement "
            f"(statut : {document.process_status}). Réessaie dans quelques instants."
        )
    text = client.beta.libraries.documents.text_content(
        library_id=library.id, document_id=document.id
    ).text
    return f"=== CV « {document.name} » (bibliothèque « {library.name} ») ===\n{text}"


agent = agents.Agent(
    model=SEARCH_MODEL,
    name="analyse-candidature",
    description=(
        "Analyse le potentiel d'une candidature à une offre d'emploi : compare l'offre "
        "(lien, PDF ou texte) au CV de l'utilisateur (PDF joint ou CV nommé dans la "
        "bibliothèque « Recherche emploi »), donne un score d'adéquation, un verdict "
        "postuler / ne pas postuler, et des recommandations concrètes."
    ),
    instructions=INSTRUCTIONS,
    tools=[cv_library, recherche_web, lire_url],
    connectors=[agents.connector("web_search")],
    max_iterations=30,
)