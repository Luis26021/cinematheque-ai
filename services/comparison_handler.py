import os
from services.groq_client import call_groq, GroqRateLimitError
from services.tmdb import search_films_by_query
from services.i18n import t
from base_prompts import get_full_system_prompt, COMPARISON_AGENT_CONTEXT
from logger_config import get_logger

logger = get_logger(__name__)


def compare_films(film_titles: list, language: str = "it") -> dict:
    """Confronta due o più film

    Args:
        film_titles: Lista titoli film da confrontare
        language: Lingua risposta (it/en/es/fr/de)
    """

    # Cerca tutti i film
    films = []
    for title in film_titles:
        results = search_films_by_query(title, limit=1)
        if results:
            films.append(results[0])

    if len(films) < 2:
        return {
            "text": "Non ho trovato abbastanza film per fare un confronto. Dammi almeno due titoli.",
            "films": []
        }

    # Genera confronto
    films_info = "\n\n".join([
        f"FILM {i+1}: {f['title']} ({f['year']})\n"
        f"Genres: {', '.join(f['genres'])}\n"
        f"Rating: {f['rating']}/10\n"
        f"Plot: {f['overview']}\n"
        f"Cast: {', '.join(f['cast']) if f.get('cast') else 'N/A'}\n"
        f"Director: {f.get('director', 'N/A')}"
        for i, f in enumerate(films)
    ])

    system_prompt = get_full_system_prompt(
        language=language,
        context=COMPARISON_AGENT_CONTEXT
    )

    user_prompt = f"""Compare these films and help the user choose:

{films_info}

TASK:
- Compare films on: genre, tone, quality, target audience
- Highlight key differences
- Suggest which to choose based on mood/preferences
- If similar, explain the nuances
- Format: conversational, NOT bullet points

FOLLOW-UP QUESTION (MANDATORY):
- At the END, ask a question to continue the conversation
- EXAMPLES:
  * "What's your mood tonight - more reflective or more adrenaline?"
  * "Have you seen one of them already? How did it seem to you?"
  * "Is there any particular theme you're interested in exploring?"
  * "Do you prefer open endings or definitive conclusions?"
- The question should help the user decide or explore further
"""

    try:
        response = call_groq(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=600,
            temperature=0.7
        )

        return {
            "text": response.choices[0].message.content,
            "films": films
        }

    except GroqRateLimitError:
        logger.warning("Rate limited in compare_films")
        return {"text": t("rate_limited", language), "films": films}
