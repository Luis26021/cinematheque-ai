import os
import json
import re
from groq import Groq
from dotenv import load_dotenv
from services.tmdb import search_films_by_query
from logger_config import get_logger
from base_prompts import get_full_system_prompt, REASONING_AGENT_CONTEXT
from services.json_utils import safe_json_parse

logger = get_logger(__name__)

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def extract_film_title_from_query(query: str, language: str = "it") -> dict:
    """
    Usa LLM per estrarre titolo film pulito da query rumorosa
    
    Returns:
        {
            'original': query originale,
            'clean': titolo film estratto,
            'year': anno estratto (int o None),
            'has_year': bool
        }
    """
    # Extract year with regex (this is fine, objective)
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', query)
    year = int(year_match.group(1)) if year_match else None
    
    # Use LLM to extract clean film title
    system_prompt = get_full_system_prompt(language, REASONING_AGENT_CONTEXT)
    
    prompt = f"""Extract ONLY the film title from this query:

"{query}"

Rules:
- Return ONLY the film title, nothing else
- Remove question words (why, how come, perché, come mai, etc.)
- Remove context (cult, classic, considered, etc.)
- Remove filler words (eh, ah, etc.)
- Keep the core film title

Examples:
- "blade runner eh? come mai è considerato un cult?" → "Blade Runner"
- "how come fight club is a cult classic?" → "Fight Club"
- "parlami del film 2001 odissea nello spazio" → "2001 Odissea nello spazio"
- "sinners horror 2025" → "Sinners"

Return ONLY the title:"""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=50,
            temperature=0.1
        )
        
        clean_title = response.choices[0].message.content.strip().strip('"\'')
        logger.info(f"LLM extraction: '{query}' → '{clean_title}'")
        
        return {
            'original': query,
            'clean': clean_title,
            'year': year,
            'has_year': year is not None
        }
    
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}, falling back to original query")
        # Fallback: return original query
        return {
            'original': query,
            'clean': query,
            'year': year,
            'has_year': year is not None
        }


def filter_relevant_results(results: list, parsed: dict, language: str = "it") -> list:
    """
    Filtra risultati irrilevanti basato su:
    - Year proximity (±2 anni max)
    - Language filtering (evita film in lingue completamente diverse)
    - Popularity threshold
    """
    if not results:
        return []
    
    relevant = []
    
    for film in results:
        # Year proximity check
        if parsed['year'] and film.get('year'):
            try:
                film_year = int(film['year']) if isinstance(film['year'], str) else film['year']
                year_diff = abs(film_year - parsed['year'])
                if year_diff > 2:
                    continue  # Skip film troppo lontani
            except (ValueError, TypeError):
                # Se year non è convertibile, skip questo check
                pass
        
        # Language filtering
        original_lang = film.get('original_language', 'en')
        
        if language == 'it':
            # Per italiani: priorità italiano, inglese, lingue europee
            # Skip film asiatici/altro SE popolarità bassa
            if original_lang not in ['it', 'en', 'es', 'fr', 'de', 'pt']:
                if film.get('popularity', 0) < 20:
                    continue
        
        relevant.append(film)
    
    # Sort by relevance (year proximity + popularity)
    if parsed['year']:
        def year_key(f):
            try:
                film_year = int(f.get('year', 9999)) if f.get('year') else 9999
                return abs(film_year - parsed['year'])
            except (ValueError, TypeError):
                return 9999
        
        relevant.sort(key=lambda f: (
            year_key(f),
            -f.get('popularity', 0)
        ))
    else:
        # No year → sort by popularity only
        relevant.sort(key=lambda f: -f.get('popularity', 0))
    
    return relevant


def is_likely_english(query: str) -> bool:
    """Quick check se query è probabilmente inglese"""
    italian_indicators = [
        'peccatori', 'uccelli', 'notte', 'giorno', 'amore', 'morte',
        'quello', 'questa', 'questo', 'qualcosa', 'qualche'
    ]
    query_lower = query.lower()
    return not any(word in query_lower for word in italian_indicators)


def llm_translate_query(query: str, language: str = "it") -> str:
    """
    LLM translation per query non-inglese → inglese
    Ultimo resort quando systematic variations falliscono
    """
    system_prompt = get_full_system_prompt(language, REASONING_AGENT_CONTEXT)
    
    prompt = f"""The user searched for: "{query}"

This query might be in {language.upper()} or a description.

Your job: translate or convert it to the most likely English film title.

Examples:
- "I peccatori" → "Sinners"
- "Gli uccelli" → "The Birds"
- "quel film con assassini 2025" → "Sinners"

Return ONLY the English title, nothing else."""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=50,
            temperature=0.3
        )
        
        translation = response.choices[0].message.content.strip().strip('"\'')
        logger.info(f"LLM translation: '{query}' → '{translation}'")
        return translation
    
    except Exception as e:
        logger.error(f"LLM translation failed: {e}")
        return query


def extract_conversation_context(history: list, current_query: str, language: str = "it") -> dict:
    """
    Usa LLM per capire se nella history c'è contesto rilevante per la query corrente
    
    Returns:
        {
            'has_context': bool,
            'context_summary': str,
            'referenced_films': list[dict],  # [{'title': ..., 'year': ...}]
            'should_use_context': bool
        }
    """
    if not history or len(history) < 2:
        return {
            'has_context': False,
            'context_summary': None,
            'referenced_films': [],
            'should_use_context': False
        }
    
    # Build conversation history text (last 10 messages)
    recent_history = []
    for msg in history[-10:]:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        if content:
            prefix = "User" if role == "user" else "Assistant"
            recent_history.append(f"{prefix}: {content[:800]}")  # Limit per message
    
    history_text = "\n\n".join(recent_history)
    
    system_prompt = get_full_system_prompt(language, REASONING_AGENT_CONTEXT)
    
    prompt = f"""Analyze this conversation and determine if the user's current query refers to something we already discussed.

CONVERSATION HISTORY:
{history_text}

CURRENT USER QUERY: "{current_query}"

Your task:
1. Look for ANY film titles mentioned in MY (Assistant's) recent responses
2. Check if the user's current query mentions or refers to any of those films
3. If yes, extract the specific film title and year (if mentioned)

IMPORTANT:
- If I showed a list of films, those ARE relevant context
- If I mentioned ANY film by name, that IS relevant context
- User queries like "blade runner?", "tell me about X", "why is X cult?" ARE referring to films from context
- Be generous: if there's any connection, mark has_context=true

Respond in JSON:
{{
    "has_context": true/false,
    "context_summary": "what films did I mention",
    "referenced_films": [{{"title": "Film Title", "year": "1982"}}],
    "should_use_context": true/false
}}

Examples:
- I said "Here are cult films: Blade Runner (1982)...", user says "blade runner?" 
  → {{"has_context": true, "referenced_films": [{{"title": "Blade Runner", "year": "1982"}}], "should_use_context": true}}

- I said "I recommend Fight Club (1999)", user says "fight club?" 
  → {{"has_context": true, "referenced_films": [{{"title": "Fight Club", "year": "1999"}}], "should_use_context": true}}

- No films in my responses, user asks random question
  → {{"has_context": false, "should_use_context": false}}

Respond ONLY with valid JSON."""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.1
        )
        
        result_text = response.choices[0].message.content.strip()
        
        result = safe_json_parse(result_text, {
            'has_context': False,
            'context_summary': None,
            'referenced_films': [],
            'should_use_context': False
        })
        
        logger.info(f"✓ Context extraction: has_context={result.get('has_context', False)}")
        if result.get('referenced_films'):
            logger.info(f"  Referenced films: {result['referenced_films']}")
        
        return {
            'has_context': result.get('has_context', False),
            'context_summary': result.get('context_summary'),
            'referenced_films': result.get('referenced_films', []),
            'should_use_context': result.get('should_use_context', False)
        }
    
    except Exception as e:
        logger.error(f"Context extraction failed: {e}")
        return {
            'has_context': False,
            'context_summary': None,
            'referenced_films': [],
            'should_use_context': False
        }


def resolve_ambiguous_query(user_query: str, max_iterations: int = 3, language: str = "it", history: list = None) -> dict:
    """
    LLM-based resolution per query ambigue
    
    3-TIER STRATEGY:
    1. LLM extraction + direct search
    2. LLM translation (se non inglese)
    3. Give up → request clarification
    
    Args:
        user_query: Query ambigua dell'utente
        max_iterations: Non usato (kept for backwards compatibility)
        language: Lingua risposta (it/en/es/fr/de)
    """
    
    logger.info(f"Starting LLM-based reasoning for query: '{user_query}'")
    
    # ==============================================================
    # TIER 0: CONVERSATION CONTEXT (LLM-based)
    # ==============================================================
    if history:
        context_result = extract_conversation_context(history, user_query, language)
        
        if context_result['should_use_context'] and context_result['referenced_films']:
            # LLM says this query refers to films from conversation
            referenced_films = context_result['referenced_films']
            
            logger.info(f"✓ LLM found conversation context: {context_result['context_summary']}")
            
            if len(referenced_films) == 1:
                # Clear reference to one film
                film_ref = referenced_films[0]
                search_query = f"{film_ref['title']}"
                if film_ref.get('year'):
                    search_query += f" {film_ref['year']}"
                
                logger.info(f"✓ Using context: searching for '{search_query}'")
                
                results = search_films_by_query(search_query, limit=5, language=language)
                
                if results and len(results) > 0:
                    logger.info(f"✓ Context-aware match: {results[0]['title']} ({results[0]['year']})")
                    return {
                        "success": True,
                        "film": results[0],
                        "reasoning": f"Found '{results[0]['title']}' from conversation context",
                        "clarification_needed": None
                    }
            
            elif len(referenced_films) > 1:
                # Multiple films referenced - try each
                for film_ref in referenced_films[:2]:  # Try top 2
                    search_query = f"{film_ref['title']}"
                    if film_ref.get('year'):
                        search_query += f" {film_ref['year']}"
                    
                    results = search_films_by_query(search_query, limit=3, language=language)
                    if results:
                        logger.info(f"✓ Found via context: {results[0]['title']}")
                        return {
                            "success": True,
                            "film": results[0],
                            "reasoning": f"Found '{results[0]['title']}' from conversation context",
                            "clarification_needed": None
                        }
    
    # ==============================================================
    # TIER 1: LLM EXTRACTION + DIRECT SEARCH
    # ==============================================================
    logger.info(f"🔍 Tier 1: LLM extraction + search '{user_query}'")
    
    parsed = extract_film_title_from_query(user_query, language)
    logger.info(f"LLM extracted: clean='{parsed['clean']}', year={parsed['year']}")
    
    # Search with extracted clean title
    clean_title = parsed['clean']
    direct_results = search_films_by_query(clean_title, limit=20, language=language)
    
    if direct_results:
        relevant = filter_relevant_results(direct_results, parsed, language)
        logger.info(f"Direct search: {len(direct_results)} total, {len(relevant)} relevant after filtering")
        
        if len(relevant) == 1:
            logger.info(f"✓ Exact match: {relevant[0]['title']} ({relevant[0]['year']})")
            return {
                "success": True,
                "film": relevant[0],
                "reasoning": f"Found exact match for '{user_query}'",
                "clarification_needed": None
            }
        
        elif len(relevant) >= 2:
            # Multiple matches: show top 5 max
            top_results = relevant[:5]
            logger.info(f"✓ Found {len(relevant)} matches, showing top {len(top_results)}")
            
            film_list = "\n".join([
                f"- **{f['title']}** ({f['year']}) - {f.get('director', 'N/A')} - {f['rating']}/10"
                for f in top_results
            ])
            
            clarification_msg = {
                "it": f"Ho trovato {len(relevant)} film:\n\n{film_list}\n\nQuale ti interessa?",
                "en": f"I found {len(relevant)} films:\n\n{film_list}\n\nWhich one?"
            }.get(language, f"Found {len(relevant)} films")
            
            return {
                "success": False,
                "film": None,
                "reasoning": f"Found multiple relevant matches",
                "clarification_needed": clarification_msg,
                "multiple_matches": top_results
            }
    
    # ==============================================================
    # TIER 2: LLM TRANSLATION (se query non inglese)
    # ==============================================================
    if not is_likely_english(user_query):
        logger.info(f"Query appears non-English, trying LLM translation")
        
        try:
            translated = llm_translate_query(clean_title, language)
            
            if translated and translated.lower() != clean_title.lower():
                logger.info(f"Searching with translation: '{translated}'")
                
                results = search_films_by_query(translated, limit=20, language=language)
                
                if results:
                    relevant = filter_relevant_results(results, parsed, language)
                    logger.info(f"Translation search: {len(results)} total, {len(relevant)} relevant")
                    
                    if len(relevant) == 1:
                        logger.info(f"✓ Found via translation: {relevant[0]['title']}")
                        return {
                            "success": True,
                            "film": relevant[0],
                            "reasoning": f"Found '{relevant[0]['title']}' via translation '{translated}'",
                            "clarification_needed": None
                        }
                    
                    elif len(relevant) >= 2:
                        top_results = relevant[:5]
                        logger.info(f"✓ Found {len(relevant)} matches via translation, showing top {len(top_results)}")
                        
                        film_list = "\n".join([
                            f"- **{f['title']}** ({f['year']}) - {f.get('director', 'N/A')} - {f['rating']}/10"
                            for f in top_results
                        ])
                        
                        clarification_msg = {
                            "it": f"Ho trovato {len(relevant)} film:\n\n{film_list}\n\nQuale ti interessa?",
                            "en": f"I found {len(relevant)} films:\n\n{film_list}\n\nWhich one?"
                        }.get(language, f"Found {len(relevant)} films")
                        
                        return {
                            "success": False,
                            "film": None,
                            "reasoning": f"Found multiple matches via translation",
                            "clarification_needed": clarification_msg,
                            "multiple_matches": top_results
                        }
        
        except Exception as e:
            logger.error(f"LLM translation failed: {e}")
    
    # ==============================================================
    # TIER 3: GIVE UP → REQUEST CLARIFICATION
    # ==============================================================
    logger.warning(f"All strategies failed for query '{user_query}'")
    
    clarification_msg = {
        "it": f"Non sono riuscito a trovare '{user_query}'. Puoi darmi più dettagli? (es. anno, regista, attori)",
        "en": f"I couldn't find '{user_query}'. Can you give me more details? (e.g., year, director, actors)"
    }.get(language, "Could not resolve query")
    
    return {
        "success": False,
        "film": None,
        "reasoning": f"Exhausted all search strategies for '{user_query}'",
        "clarification_needed": clarification_msg
    }


def should_use_reasoning_agent(user_query: str, intent: str) -> bool:
    """
    Decide se usare reasoning agent per questa query
    
    Usa agent quando:
    - Intent è info/review MA query è molto corta/ambigua
    - Query ha nomi strani o anni futuri
    - Query contiene termini vaghi
    """
    
    # Se intent è chat/comparison/recommendation → NO agent
    if intent in ["chat", "comparison", "recommendation"]:
        return False
    
    # Check ambiguità
    query_lower = user_query.lower()
    
    # Trigger 1: Query molto corta (1-2 parole)
    words = user_query.split()
    if len(words) <= 2:
        return True
    
    # Trigger 2: Anno futuro (film non ancora uscito)
    import re
    years = re.findall(r'\b(202[4-9]|203\d)\b', user_query)
    if years:
        return True
    
    # Trigger 3: Nomi strani o acronimi
    if any(word.isupper() and len(word) <= 4 for word in words):
        return True
    
    # Trigger 4: Parole vaghe
    vague_terms = ['cosa', 'qualcosa', 'tipo', 'simile', 'come', 'quello']
    if any(term in query_lower for term in vague_terms):
        return True
    
    return False