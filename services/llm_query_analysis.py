# LLM-Based Query Analysis - Replace Regex Hell

import json
from services.groq_client import call_groq, GroqRateLimitError
from logger_config import get_logger

logger = get_logger(__name__)


def analyze_query_with_llm(user_message: str, response_language: str = "it", history: list = None):
    """
    Estrae parametri di ricerca usando LLM invece di regex

    Vantaggi:
    - Robusto a variazioni linguistiche
    - Multi-lingua automatico
    - No false positive
    - Meno codice
    """

    tmdb_language_map = {
        "it": "it-IT", "en": "en-US", "es": "es-ES",
        "fr": "fr-FR", "de": "de-DE"
    }

    # Conversation context
    is_repeat_request = False
    previous_platform = None

    if history and len(history) > 0:
        # Pattern repeat
        repeat_patterns = ['altri', 'ancora', 'more', 'another', 'diversi', 'dammene']
        if any(p in user_message.lower() for p in repeat_patterns):
            is_repeat_request = True

            # Estrai platform dall'ultimo messaggio
            for msg in reversed(history):
                if msg.get('role') == 'assistant':
                    content = msg.get('content', '').lower()
                    platforms = ['netflix', 'prime', 'disney', 'hbo']
                    for p in platforms:
                        if p in content:
                            previous_platform = p
                            break
                    break

    # LLM Extraction Prompt
    extraction_prompt = f"""Extract search parameters from this film request. Return ONLY valid JSON.

USER REQUEST: "{user_message}"

Extract these parameters (use null if not mentioned):

{{
  "platform": "Netflix" | "Amazon Prime Video" | "Disney Plus" | "HBO Max" | "Apple TV Plus" | null,
  "genres": ["action", "comedy", "drama", "horror", "romance", "sci-fi", "thriller"] | [],
  "year": 2023 | null,
  "year_range": [2020, 2023] | null,
  "rating_min": 8.0 | null,
  "mood": "tonight" | "now" | "urgent" | null
}}

RULES:
- platform: exact platform name if mentioned (Netflix, Prime Video, etc.)
- genres: list of genres mentioned (action, comedy, etc.)
- year: single year if mentioned (2023, 2020, etc.)
- year_range: [start, end] if range mentioned ("from 2020 to 2023", "dal 2020 al 2023")
- rating_min: minimum rating as float if mentioned ("above 8", "superiore all'8" → 8.0)
- mood: "urgent" if user says "tonight", "now", "stasera", "adesso"

EXAMPLES:

Input: "film romantico su netflix superiore all'8"
Output: {{"platform": "Netflix", "genres": ["romance"], "rating_min": 8.0, "year": null, "year_range": null, "mood": null}}

Input: "thriller psicologico del 2023 su prime video"
Output: {{"platform": "Amazon Prime Video", "genres": ["thriller"], "year": 2023, "rating_min": null, "year_range": null, "mood": null}}

Input: "film d'azione dal 2020 in poi"
Output: {{"platform": null, "genres": ["action"], "year": null, "year_range": [2020, 2026], "rating_min": null, "mood": null}}

Input: "qualcosa di leggero per stasera"
Output: {{"platform": null, "genres": ["comedy"], "year": null, "year_range": null, "rating_min": null, "mood": "urgent"}}

Input: "film con valutazione alta"
Output: {{"platform": null, "genres": [], "year": null, "year_range": null, "rating_min": 7.5, "mood": null}}

CRITICAL:
- Return ONLY the JSON object, no markdown, no explanation
- If a parameter is not mentioned, use null or []
- Be precise with platform names (exact match from list)
- "valutazione alta" = rating 7.5+, NOT a genre

Now extract from: "{user_message}"
"""

    try:
        response = call_groq(
            messages=[{"role": "user", "content": extraction_prompt}],
            max_tokens=200,
            temperature=0.1
        )

        result_text = response.choices[0].message.content.strip()

        # Remove markdown fences if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        # Parse JSON
        params = json.loads(result_text)

        print(f"DEBUG - LLM extracted params: {params}")

        # Map to TMDB format
        country_code = "IT"
        tmdb_language = tmdb_language_map.get(response_language, "it-IT")

        # Genre mapping
        genre_map = {
            "action": [28],
            "adventure": [12],
            "animation": [16],
            "comedy": [35],
            "crime": [80],
            "drama": [18],
            "fantasy": [14],
            "horror": [27],
            "romance": [10749],
            "sci-fi": [878],
            "thriller": [53],
            "documentary": [99],
            "mystery": [9648]
        }

        # Build args
        args = {
            "limit": 10,
            "country": country_code,
            "tmdb_language": tmdb_language
        }

        # Platform
        if params.get("platform"):
            args["platform_filter"] = params["platform"]
        elif is_repeat_request and previous_platform:
            args["platform_filter"] = previous_platform.title()

        # Genres
        if params.get("genres"):
            genre_ids = []
            for g in params["genres"]:
                genre_ids.extend(genre_map.get(g, []))
            if genre_ids:
                args["genre_ids"] = list(set(genre_ids))

        # Year
        if params.get("year"):
            args["year"] = params["year"]

        # Year range
        if params.get("year_range"):
            args["year_range"] = params["year_range"]

        # Rating
        if params.get("rating_min"):
            args["rating_min"] = params["rating_min"]

        # Mood → urgency → recent years
        if params.get("mood") == "urgent":
            args["year_range"] = [2020, 2026]

        # Repeat request offset
        if is_repeat_request:
            import random
            args["offset"] = random.randint(5, 20)
            print(f"DEBUG - Repeat request: offset={args['offset']}")

        # Decide tool
        if "genre_ids" in args or "year" in args or "year_range" in args:
            tool = "search_films"
        elif args.get("platform_filter") or args.get("rating_min"):
            tool = "search_films"
        else:
            tool = "get_popular_films"

        return {"tool": tool, "args": args}

    except GroqRateLimitError:
        logger.warning("Rate limited during query analysis, defaulting to get_popular_films")
        return {
            "tool": "get_popular_films",
            "args": {
                "limit": 10,
                "country": "IT",
                "tmdb_language": tmdb_language_map.get(response_language, "it-IT")
            }
        }

    except Exception as e:
        print(f"ERROR in LLM extraction: {e}")
        import traceback
        traceback.print_exc()

        # Fallback to safe defaults
        return {
            "tool": "get_popular_films",
            "args": {
                "limit": 10,
                "country": "IT",
                "tmdb_language": tmdb_language_map.get(response_language, "it-IT")
            }
        }


# ============================================
# HOW TO USE
# ============================================

"""
In streaming_agent.py, SOSTITUISCI:

# PRIMA:
tool_decision = analyze_query(user_message, response_language, history)

# DOPO:
tool_decision = analyze_query_with_llm(user_message, response_language, history)

Questo ELIMINA:
- Tutti i rating_patterns regex
- Tutto il platform_map
- Tutto il genre_id_map matching con word boundaries
- Pattern matching per year/year_range

E li SOSTITUISCE con una singola chiamata LLM robusta.
"""
