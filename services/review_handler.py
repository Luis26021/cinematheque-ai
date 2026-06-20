import os
import re
from groq import Groq
from dotenv import load_dotenv
from services.tmdb import search_films_by_query
from logger_config import get_logger
from base_prompts import get_full_system_prompt, REVIEW_AGENT_CONTEXT

logger = get_logger(__name__)

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def extract_film_from_history(history: list) -> str:
    """Estrae l'ultimo film menzionato dall'assistente nella conversazione"""
    if not history:
        return None
    
    # Cerca nel messaggio più recente dell'assistente
    for msg in reversed(history):
        if msg.get('role') == 'assistant':
            content = msg.get('content', '')
            
            # Cerca pattern **Titolo Film**
            bold_matches = re.findall(r'\*\*([^*]+)\*\*', content)
            if bold_matches:
                # Ritorna il primo film trovato (più recente)
                logger.debug(f"Found film in history: {bold_matches[0]}")
                return bold_matches[0].strip()
            
            # Fallback: cerca titoli con maiuscole (pattern "Titolo Film")
            words = content.split()
            potential_title = []
            for word in words:
                if word and word[0].isupper() and len(word) > 2:
                    potential_title.append(word)
                else:
                    if len(potential_title) >= 2:
                        # Abbiamo una sequenza, potrebbe essere un titolo
                        title = ' '.join(potential_title)
                        logger.debug(f"Found potential title in history: {title}")
                        return title
                    potential_title = []
            
            break  # Usa solo il messaggio più recente
    
    return None

def generate_review(film_title: str = None, film_object: dict = None, history: list = None, language: str = "it") -> dict:
    """Genera recensione/opinione su un film
    
    Args:
        film_title: Titolo del film o query vaga (se film_object non fornito)
        film_object: Film object già trovato (skip search)
        history: Storia conversazione per context-aware extraction
        language: Lingua risposta (it/en/es/fr/de)
    """
    
    # ========== CONTEXT-AWARE FILM EXTRACTION ==========
    # Se film_object già fornito, usa quello
    if film_object:
        logger.info(f"Using provided film object: {film_object['title']}")
        film = film_object
    else:
        # Altrimenti cerca il film
        if not film_title:
            return {
                "text": "Non ho capito quale film vuoi sapere. Puoi essere più specifico?",
                "film": None
            }
        
        # Se query è vaga ("film1", pronomi, domande senza titolo), usa history
        vague_patterns = [
            'film1', 'film2', 'film 1', 'film 2',
            'quello', 'questo', 'quel film', 'questo film',
            'it', 'that', 'the film', 'the movie',
            'come mai', 'perché', 'why', 'how come',
            'che ne pensi', 'what do you think'
        ]
        
        is_vague = any(pattern in film_title.lower() for pattern in vague_patterns)
        
        if is_vague:
            # Query vaga → cerca nell'history
            logger.info(f"Vague query detected: '{film_title}', checking history")
            film_from_history = extract_film_from_history(history)
            
            if film_from_history:
                logger.info(f"Using film from history: {film_from_history}")
                film_title = film_from_history
            else:
                logger.warning("No film found in history, using query as-is")
        # ===================================================
        
        logger.info(f"Generating review for: {film_title}")
        
        # 1. Cerca film su TMDB
        results = search_films_by_query(film_title, limit=1)
        
        if not results:
            return {
                "text": f"Non ho trovato informazioni su '{film_title}'. Puoi essere più specifico con il titolo?",
                "film": None
            }
        
        film = results[0]
    
    # 2. Cast e regista (già fetchati da search_films_by_query)
    cast = film.get("cast", [])
    director = film.get("director")
    
    logger.info(f"Film: {film['title']}, Cast: {cast}, Director: {director}")
    
    # Se per qualche motivo non ci sono, prova a fetchare
    if not cast and not director:
        logger.warning("No credits in film object, attempting to fetch...")
        try:
            from services.tmdb import fetch_movie_credits
            # Map language to TMDB format (it → it-IT)
            tmdb_language = f"{language}-{language.upper()}" if len(language) == 2 else language
            credits = fetch_movie_credits(film["id"], language=tmdb_language)
            cast = credits.get("cast", [])
            director = credits.get("director")
            logger.info(f"Fetched credits: cast={cast}, director={director}")
        except Exception as e:
            logger.error(f"Could not fetch credits: {e}")
    
    # 3. Genera opinione con LLM
    cast_text = ', '.join(cast) if cast else 'Non disponibile'
    director_text = director if director else 'Non disponibile'
    
    # System prompt from base_prompts
    system_prompt = get_full_system_prompt(
        language=language,
        context=REVIEW_AGENT_CONTEXT
    )
    
    # User prompt (only specific review instructions)
    user_prompt = f"""Generate a thoughtful review for this film:

FILM DETAILS:
Title: {film['title']} ({film['year']})
Genres: {', '.join(film['genres'])}
Rating: {film['rating']}/10
Cast: {cast_text}
Director: {director_text}
Plot: {film['overview']}

TASK:
- Write 3-4 paragraphs of critical analysis
- IF cast/director info is available, mention them NATURALLY (don't force if not relevant)
- Comment on plot, direction, acting, themes
- Balance positive and negative aspects
- Be objective but personal
- Conclude with who should watch it

IMPORTANT:
- If rating is low (< 7.0), HONESTLY explain why critics/audience were harsh
- DO NOT invent details you don't know
- Mention cast/director only if available and relevant

FOLLOW-UP QUESTION (MANDATORY):
- At the END of the review, ask a question to continue the conversation
- EXAMPLES:
  * "Have you seen it already? What do you think?"
  * "Do you also like other films by this director/actor?"
  * "Looking for something similar or prefer to explore other genres?"
  * "What made you think of this film in particular?"
- The question must be natural and relevant
"""
    
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=800,
        temperature=0.7
    )
    
    review_text = response.choices[0].message.content
    
    return {
        "text": review_text,
        "film": film
    }