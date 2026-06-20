import os
import json
from groq import Groq
from dotenv import load_dotenv
from services.tmdb import search_person, get_person_filmography
from logger_config import get_logger
from base_prompts import get_full_system_prompt, FILMOGRAPHY_AGENT_CONTEXT

logger = get_logger(__name__)

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def analyze_filmography_query(user_query: str, language: str = "it") -> dict:
    """
    Usa LLM per analizzare query su filmografia e estrarre:
    - person_name: nome attore/regista
    - role: 'director' | 'actor' | 'all'
    - sort_by: 'rating_desc' | 'rating_asc' | 'recent' | 'old' | 'popular'
    - limit: numero film da ritornare (default 3)
    
    Examples:
    - "i 3 migliori film di Scorsese" → {name: "Martin Scorsese", role: "director", sort_by: "rating_desc", limit: 3}
    - "peggiori film di Adam Sandler" → {name: "Adam Sandler", role: "actor", sort_by: "rating_asc", limit: 3}
    - "ultimi 5 film diretti da Nolan" → {name: "Christopher Nolan", role: "director", sort_by: "recent", limit: 5}
    """
    
    logger.info(f"Analyzing filmography query: '{user_query}'")
    
    system_prompt = get_full_system_prompt(language, FILMOGRAPHY_AGENT_CONTEXT)
    
    analysis_prompt = f"""Analyze this user query about films/filmography: "{user_query}"

Extract the following information:

1. **person_name**: Full name of the actor or director (e.g., "Martin Scorsese", "Ryan Gosling")
2. **role**: Whether they want films as director or actor
   - "director" if query says: "diretti da", "regista", "directed by", "films of [director name]"
   - "actor" if query says: "con", "recitati da", "starring", "acted by", "films with [actor name]"
   - "all" if unclear or both
3. **sort_by**: How to sort the results
   - "rating_desc" for: migliori, best, top-rated, più belli
   - "rating_asc" for: peggiori, worst, meno riusciti
   - "recent" for: ultimi, recenti, latest, recent
   - "old" for: primi, vecchi, oldest, first
   - "popular" for: famosi, popolari, most popular
4. **limit**: Number of films requested (default 3)

OUTPUT FORMAT (JSON only, no explanation):
{{
  "person_name": "Full name",
  "role": "director" | "actor" | "all",
  "sort_by": "rating_desc" | "rating_asc" | "recent" | "old" | "popular",
  "limit": number
}}

Return ONLY valid JSON."""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": analysis_prompt}
            ],
            max_tokens=200,
            temperature=0.3
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parse JSON
        if result_text.startswith("```json"):
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif result_text.startswith("```"):
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        analysis = json.loads(result_text)
        
        logger.info(f"Query analysis: {analysis}")
        return analysis
    
    except Exception as e:
        logger.error(f"Error analyzing filmography query: {e}", exc_info=True)
        # Fallback
        return {
            "person_name": user_query,
            "role": "all",
            "sort_by": "rating_desc",
            "limit": 3
        }


def generate_filmography_response(
    user_query: str,
    history: list = None,
    language: str = "it"
) -> dict:
    """
    Main handler per filmography queries
    
    Flow:
    1. Analizza query con LLM (person_name, role, sort_by, limit)
    2. Search person su TMDB
    3. Se multiple matches → ritorna lista per chiarimento
    4. Fetch filmography
    5. Sort + filter
    6. Generate response con LLM synthesis
    """
    
    logger.info(f"Processing filmography query: '{user_query}'")
    
    # STEP 1: Analyze query
    analysis = analyze_filmography_query(user_query, language)
    person_name = analysis["person_name"]
    role = analysis["role"]
    sort_by = analysis["sort_by"]
    limit = analysis.get("limit", 3)
    
    # STEP 2: Search person
    people = search_person(person_name, language=f"{language}-IT")
    
    if not people:
        logger.warning(f"No person found for '{person_name}'")
        return {
            "success": False,
            "error": "person_not_found",
            "message": {
                "it": f"Non ho trovato nessun attore o regista chiamato '{person_name}'.",
                "en": f"I couldn't find any actor or director named '{person_name}'."
            }.get(language, f"Person '{person_name}' not found")
        }
    
    # STEP 3: Handle multiple matches
    if len(people) > 1:
        logger.info(f"Multiple people found for '{person_name}', asking for clarification")
        
        people_list = "\n".join([
            f"- **{p['name']}** ({p['known_for_department']}) - Known for: {', '.join(p['known_for'][:2])}"
            for p in people
        ])
        
        clarification_msg = {
            "it": f"Ho trovato più persone con questo nome:\n\n{people_list}\n\nA chi ti riferisci?",
            "en": f"I found multiple people with this name:\n\n{people_list}\n\nWhich one do you mean?"
        }.get(language, "Multiple people found")
        
        return {
            "success": False,
            "error": "multiple_matches",
            "message": clarification_msg,
            "people": people
        }
    
    # STEP 4: Get filmography
    person = people[0]
    person_id = person["id"]
    
    logger.info(f"Fetching filmography for {person['name']} (id={person_id})")
    
    # Auto-detect role if "all"
    if role == "all":
        role = "director" if person["known_for_department"] == "Directing" else "actor"
        logger.info(f"Auto-detected role: {role}")
    
    films = get_person_filmography(person_id, role=role, language=f"{language}-IT")
    
    if not films:
        logger.warning(f"No filmography found for {person['name']}")
        return {
            "success": False,
            "error": "no_filmography",
            "message": {
                "it": f"Non ho trovato film per {person['name']}.",
                "en": f"I couldn't find any films for {person['name']}."
            }.get(language, "No films found")
        }
    
    # STEP 5: Sort + limit
    films_sorted = sort_films(films, sort_by)
    films_final = films_sorted[:limit]
    
    logger.info(f"Selected {len(films_final)} films (sort_by={sort_by})")
    
    # STEP 6: Generate response with LLM
    system_prompt = get_full_system_prompt(language, FILMOGRAPHY_AGENT_CONTEXT)
    
    films_data = "\n\n".join([
        f"**{f['title']}** ({f['year']})\n"
        f"- Rating: {f['rating']}/10\n"
        f"- Director: {f['director']}\n"
        f"- Cast: {', '.join(f['cast'][:3])}\n"
        f"- Overview: {f['overview'][:200]}..."
        for f in films_final
    ])
    
    # Craft prompt based on sort_by
    sort_context = {
        "rating_desc": "best/top-rated films",
        "rating_asc": "worst/lowest-rated films",
        "recent": "most recent films",
        "old": "earliest/oldest films",
        "popular": "most popular films"
    }.get(sort_by, "films")
    
    synthesis_prompt = f"""The user asked: "{user_query}"

You are discussing the {sort_context} of **{person['name']}** ({person['known_for_department']}).

Here are the {len(films_final)} films with data:

{films_data}

YOUR TASK:
Write a natural, flowing response about these films. This should read like a conversation with a knowledgeable friend, NOT a numbered list of reviews.

CRITICAL RULES:
1. **NO FORMULAS**: Never repeat "Questo film è..." or "La sua regia è..." across multiple films. Each film gets unique phrasing.
2. **SPECIFIC, NOT GENERIC**: Don't say "magistrale" or "semplicemente fantastico" - explain WHAT makes it good (specific scenes, choices, performances).
3. **CREATE FLOW**: Connect films to each other. Show evolution, recurring themes, or contrasts between them. Don't treat as isolated blocks.
4. **CONVERSATIONAL**: Write like you're talking, not writing a formal review. Use natural transitions.
5. **CONCRETE OPINIONS**: "The diner scene's paranoia is palpable" not "creates atmosphere of suspense"

STRUCTURE:
- Brief intro (1-2 sentences setting up the selection)
- Discuss films naturally, weaving between them
- For each film: title (year) - rating, then WHY it matters in their career
- Vary your sentence structure and length
- End with a connecting thought or question

TONE: Informal (tu), passionate but not reverential, opinionated but fair.

Example of BAD writing (avoid this):
"Questo film è un capolavoro. La sua regia è magistrale. Il cast è fantastico."

Example of GOOD writing (do this):
"Goodfellas (1990) - 8.5/10 è dove Scorsese perfeziona il suo stile frenetico: quel lungo piano sequenza nel Copacabana non è solo tecnica, è cinema puro che ti fa sentire l'adrenalina di Henry Hill."

Write naturally. Vary your style. Connect the dots."""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": synthesis_prompt}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        
        final_text = response.choices[0].message.content.strip()
        
        logger.info(f"Generated filmography response ({len(final_text)} chars)")
        
        return {
            "success": True,
            "text": final_text,
            "person": person,
            "films": films_final
        }
    
    except Exception as e:
        logger.error(f"Error generating filmography response: {e}", exc_info=True)
        
        # Fallback: simple list
        fallback_text = f"Ecco i {len(films_final)} film di {person['name']}:\n\n"
        fallback_text += "\n".join([
            f"{i+1}. **{f['title']}** ({f['year']}) - {f['rating']}/10"
            for i, f in enumerate(films_final)
        ])
        
        return {
            "success": True,
            "text": fallback_text,
            "person": person,
            "films": films_final
        }


def sort_films(films: list, sort_by: str) -> list:
    """Sort films based on criteria"""
    
    if sort_by == "rating_desc":
        # Use weighted_score for better curation (already computed in get_person_filmography)
        return sorted(films, key=lambda f: -f.get("weighted_score", 0))
    
    elif sort_by == "rating_asc":
        # Use weighted_score (ascending for "worst")
        return sorted(films, key=lambda f: f.get("weighted_score", 0))
    
    elif sort_by == "recent":
        return sorted(films, key=lambda f: -int(f.get("year", 0)) if f.get("year", "0").isdigit() else 0)
    
    elif sort_by == "old":
        return sorted(films, key=lambda f: int(f.get("year", 9999)) if f.get("year", "9999").isdigit() else 9999)
    
    elif sort_by == "popular":
        return sorted(films, key=lambda f: -f.get("popularity", 0))
    
    else:
        # Default: weighted score
        return sorted(films, key=lambda f: -f.get("weighted_score", 0))