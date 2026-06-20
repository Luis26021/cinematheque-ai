import os
import json
import re
import random
from groq import Groq
from dotenv import load_dotenv
from services.llm_query_analysis import analyze_query_with_llm
from services.tools import TOOLS, execute_tool
from services.i18n import t
from logger_config import get_logger
from base_prompts import get_full_system_prompt, RECOMMENDATION_AGENT_CONTEXT, CULT_FILMS_GENERATOR_CONTEXT

logger = get_logger(__name__)

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def handle_cult_films_query(user_message: str, language: str = "it", country: str = "IT"):
    """
    Handle cult films queries with LLM-generated search strategy.
    
    Returns:
        dict with 'films' list or None if generation fails
    """
    # Import qui per evitare circular imports
    from services.tmdb import search_films_by_query, get_streaming_availability
    
    try:
        logger.info(f"Handling cult films query: {user_message}")
        
        # STEP 1: Generate cult film titles via LLM
        system_prompt = get_full_system_prompt(
            language=language,
            context=CULT_FILMS_GENERATOR_CONTEXT
        )
        
        user_prompt = f"""User request: "{user_message}"

Generate 5-8 cult film titles that match this request.
Remember: films must be from 2016 or earlier.
Return ONLY the JSON array, nothing else."""

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        # Parse LLM response
        llm_output = response.choices[0].message.content.strip()
        logger.debug(f"LLM generated titles: {llm_output}")
        
        # Extract JSON (might have markdown fences)
        json_str = llm_output
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        
        # Parse titles
        try:
            cult_titles = json.loads(json_str)
            if not isinstance(cult_titles, list):
                raise ValueError("Expected list of titles")
        except:
            logger.error(f"Failed to parse LLM output as JSON: {llm_output}")
            return None
        
        logger.info(f"Generated {len(cult_titles)} cult film titles")
        
        # SANITY CHECK: skippa titoli con anni recenti visibili
        recent_years = ["2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"]
        clean_titles = []
        for title in cult_titles:
            if any(year in str(title) for year in recent_years):
                logger.warning(f"⚠️ LLM generated title with recent year: {title} - SKIPPING")
                continue
            clean_titles.append(title)
        
        logger.info(f"After year sanity check: {len(clean_titles)} titles")
        
        # STEP 2: Search for each title
        all_films = []
        for title in clean_titles[:8]:  # Max 8 searches
            results = search_films_by_query(query=title, limit=1, language=language)
            if results:
                all_films.extend(results)
        
        logger.info(f"Found {len(all_films)} films from searches")
        
        # STEP 3: Filter results
        current_year = 2026
        filtered_films = []
        
        for film in all_films:
            title = film.get("title", "Unknown")
            
            # Extract year - it's already in film object as string
            year_str = film.get("year", "")
            
            if not year_str or year_str == "N/A":
                logger.warning(f"Skipping {title}: no valid year")
                continue
                
            try:
                year = int(year_str)
            except:
                logger.warning(f"Skipping {title}: invalid year format ({year_str})")
                continue
            
            # Apply filters:
            # 1. Min 10 years old (2016 or earlier)
            if year > current_year - 10:
                logger.info(f"❌ FILTERED OUT: {title} ({year}) - too recent (need ≤2016)")
                continue
            
            # 2. Min rating 6.0
            rating = film.get("rating", 0)
            if rating < 6.0:
                logger.info(f"❌ FILTERED OUT: {title} ({year}) - low rating ({rating})")
                continue
            
            logger.info(f"✅ PASSED: {title} ({year}, rating {rating})")
            filtered_films.append(film)
        
        logger.info(f"After filtering: {len(filtered_films)} cult films")
        
        # Deduplicate by ID
        seen_ids = set()
        unique_films = []
        for film in filtered_films:
            if film["id"] not in seen_ids:
                seen_ids.add(film["id"])
                unique_films.append(film)
        
        # Get streaming availability
        for film in unique_films:
            if "streaming" not in film:
                film["streaming"] = get_streaming_availability(film["id"], country)
        
        return {"films": unique_films[:10]}  # Max 10 results
        
    except Exception as e:
        logger.error(f"Cult films handler error: {e}", exc_info=True)
        return None


def detect_message_language(user_message: str) -> str:
    """Detect language of user message for response matching"""
    
    try:
        prompt = f"""Detect the language of this message. Return ONLY a 2-letter code.

Message: "{user_message}"

Rules:
- Italian → it
- English → en
- Spanish → es
- French → fr
- German → de
- Other → en

Return ONLY the 2-letter code, nothing else."""

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0
        )
        
        language = response.choices[0].message.content.strip().lower()
        
        # Validate
        if language in ['it', 'en', 'es', 'fr', 'de']:
            logger.debug(f"Detected response language: {language}")
            return language
        else:
            logger.warning(f"Invalid language '{language}', defaulting to en")
            return 'en'
    
    except Exception as e:
        logger.error(f"Language detection error: {e}, defaulting to en")
        return 'en'

def stream_film_suggestion(user_message: str, history: list, user_country: str = "IT", user_language: str = "it"):
    """Generator che gestisce tutti i tipi di richieste film
    
    Args:
        user_message: Il messaggio dell'utente
        history: Storico conversazione
        user_country: Paese dell'utente (IT/US/ES/FR/DE)
        user_language: Lingua preferita dell'utente (it/en/es/fr/de)
    """
    
    try:
        # Usa la lingua dell'utente per response (invece di auto-detect)
        response_language = user_language
        
        yield {"type": "status", "message": t("analyzing", response_language)}
        
        # ========== MEMORY SYSTEM (ALWAYS FIRST) ==========
        from services.conversation_memory import (
            initialize_memory,
            extract_memory_from_turn,
            update_memory,
            get_memory_summary,
            should_respond_conversationally
        )
        
        # Load or initialize memory
        conversation_memory = initialize_memory()
        
        # Extract memory from recent history
        if history and len(history) >= 2:
            logger.info("📚 Loading conversation memory from history...")
            
            # Process last turns to build memory
            for i in range(0, len(history) - 1, 2):
                if i + 1 < len(history):
                    user_msg = history[i].get('content', '')
                    assistant_msg = history[i + 1].get('content', '')
                    
                    if user_msg and assistant_msg:
                        extracted = extract_memory_from_turn(
                            user_msg,
                            assistant_msg,
                            conversation_memory,
                            response_language
                        )
                        conversation_memory = update_memory(conversation_memory, extracted)
            
            memory_summary = get_memory_summary(conversation_memory, response_language)
            logger.info(f"✓ Memory loaded: {memory_summary[:200]}")
        
        # ========================================================
        
        # ========== CHECK IF CONVERSATIONAL RESPONSE ==========
        # Decide if we can respond conversationally or need search
        conversational_check = should_respond_conversationally(
            user_message,
            conversation_memory,
            response_language
        )
        
        if conversational_check.get('conversational'):
            logger.info(f"💬 Conversational response: {conversational_check.get('reasoning')}")
            
            # Generate conversational response with memory
            from base_prompts import get_full_system_prompt, RECOMMENDATION_AGENT_CONTEXT
            
            system_prompt = get_full_system_prompt(response_language, RECOMMENDATION_AGENT_CONTEXT)
            memory_summary = get_memory_summary(conversation_memory, response_language)
            
            conversational_prompt = f"""You are having a natural conversation about cinema.

CONVERSATION MEMORY:
{memory_summary}

USER: "{user_message}"

Respond naturally as a knowledgeable film curator. Use examples from our conversation memory.
Be conversational, insightful, and engaging. This is a discussion, not a search result.

NO need to search for films - use what we've already discussed."""

            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": conversational_prompt}
                ],
                max_tokens=800,
                temperature=0.8
            )
            
            assistant_text = response.choices[0].message.content
            
            # Update memory with this turn
            extracted = extract_memory_from_turn(
                user_message,
                assistant_text,
                conversation_memory,
                response_language
            )
            conversation_memory = update_memory(conversation_memory, extracted)
            
            yield {
                "type": "complete",
                "text": assistant_text,
                "films": []  # No specific films to show
            }
            return
        
        # Otherwise, proceed with normal search flow
        logger.info(f"🔍 Search-based response: {conversational_check.get('reasoning')}")
        # ========================================================
        
        # ========== TIER 0: CONVERSATION CONTEXT (ALWAYS) ==========
        # Check if user is referring to something from conversation history
        conversation_context = None
        if history and len(history) >= 2:
            from services.reasoning_agent import extract_conversation_context
            
            logger.info("🔍 Checking conversation context...")
            conversation_context = extract_conversation_context(history, user_message, response_language)
            
            if conversation_context.get('should_use_context'):
                logger.info(f"✓ Found conversation context: {conversation_context.get('context_summary')}")
            else:
                logger.info("✗ No relevant conversation context found")
        
        # ========================================================
        
        # INTENT DETECTION
        from services.intent_router import detect_intent
        intent_result = detect_intent(user_message)
        intent = intent_result.get("intent", "recommendation")
        entities = intent_result.get("entities", [])
        
        logger.debug(f"Intent: {intent}, Entities: {entities}")
        
        # ========== SANITY CHECK INTENT ==========
        # Fix: "si però" non è comparison se non ci sono titoli film
        if intent == "comparison":
            # Check se ci sono almeno 2 titoli di film (parole con maiuscola)
            capitalized_words = [w for w in user_message.split() 
                                if w and w[0].isupper() and len(w) > 2]
            
            if len(capitalized_words) < 2:
                logger.warning(f"Intent 'comparison' but only {len(capitalized_words)} film titles, fallback to recommendation")
                intent = "recommendation"
                entities = []
        # =========================================
        
        # ========== REASONING AGENT per query ambigue ==========
        # Usa agent solo per info/review con query ambigue
        # EXCEPT: se conversation context ha già identificato il film → skippa reasoning
        if intent in ["info", "review"]:
            from services.reasoning_agent import should_use_reasoning_agent, resolve_ambiguous_query
            
            # Check if context already resolved the film
            if (conversation_context and 
                conversation_context.get('should_use_context') and 
                conversation_context.get('referenced_films') and
                len(conversation_context['referenced_films']) == 1):
                
                # Context identified exact film - use it directly
                film_ref = conversation_context['referenced_films'][0]
                search_query = f"{film_ref['title']}"
                if film_ref.get('year'):
                    search_query += f" {film_ref['year']}"
                
                logger.info(f"✓ Using film from context: '{search_query}' (skipping reasoning agent)")
                
                from services.tmdb import search_films_by_query
                results = search_films_by_query(search_query, limit=1, language=response_language)
                
                if results and len(results) > 0:
                    film = results[0]
                    logger.info(f"✓ Context-resolved film: {film['title']} ({film['year']})")
                    
                    # Route to review handler with this film
                    from services.review_handler import generate_review
                    result = generate_review(
                        film_object=film,
                        history=history,
                        language=response_language
                    )
                    
                    yield {"type": "complete", "text": result["text"], "films": [result["film"]]}
                    return
            
            # Otherwise, use reasoning agent if query is ambiguous
            film_query = user_message
            
            if should_use_reasoning_agent(film_query, intent):
                logger.info(f"🧠 Ambiguous query detected, using reasoning agent: '{film_query}'")
                
                yield {"type": "status", "message": "Sto cercando di capire a cosa ti riferisci..."}
                
                # Run reasoning loop with conversation history
                agent_result = resolve_ambiguous_query(
                    film_query, 
                    max_iterations=3,
                    language=response_language,
                    history=history  # PASS HISTORY for context-aware disambiguation
                )
                
                if agent_result["success"]:
                    # Agent ha trovato il film!
                    logger.info(f"✓ Agent found film: {agent_result['film']['title']}")
                    
                    film = agent_result["film"]
                    
                    # Usa review_handler invece di duplicare
                    from services.review_handler import generate_review
                    
                    result = generate_review(
                        film_title=film["title"],
                        history=history,
                        language=response_language
                    )
                    
                    yield {
                        "type": "complete",
                        "text": result["text"],
                        "films": [result["film"]] if result["film"] else []
                    }
                    return
                
                else:
                    # Agent non ha capito → chiede chiarimenti
                    logger.info("✗ Agent couldn't resolve query, asking for clarification")
                    
                    clarification = agent_result["clarification_needed"]
                    
                    yield {
                        "type": "complete",
                        "text": clarification,
                        "films": []
                    }
                    return
        # ========================================================
        
        # ========== ROUTE BASATO SU INTENT (flow normale se agent non usato) ==========
        
        if intent == "review":
            # Opinione su film specifico
            from services.review_handler import generate_review
            
            film_title = entities[0] if entities else user_message
            yield {"type": "status", "message": t("searching_info", response_language, title=film_title)}
            
            # PASS HISTORY per context-aware extraction
            result = generate_review(film_title, history=history, language=response_language)
            
            yield {
                "type": "complete",
                "text": result["text"],
                "films": [result["film"]] if result["film"] else []
            }
            return
        
        elif intent == "comparison":
            # Confronto tra film
            from services.comparison_handler import compare_films
            
            yield {"type": "status", "message": t("comparing", response_language)}
            
            result = compare_films(entities if entities else [])
            
            yield {
                "type": "complete",
                "text": result["text"],
                "films": result["films"]
            }
            return
        
        elif intent == "info":
            # Info film → stesso handling di review
            from services.review_handler import generate_review
            
            film_title = entities[0] if entities else user_message
            yield {"type": "status", "message": t("searching_info", response_language, title=film_title)}
            
            result = generate_review(film_title, history=history, language=response_language)
            
            yield {
                "type": "complete",
                "text": result["text"],
                "films": [result["film"]] if result["film"] else []
            }
            return
        
        elif intent == "chat":
            # Conversazione generica
            yield {
                "type": "complete",
                "text": "Ciao! Questo è Cinémathèque. Sono un curatore specializzato in film. Posso consigliarti cosa guardare, darti la mia opinione su film specifici, o confrontare titoli. Qual è il tuo genere preferito? O c'è un film che ti è piaciuto molto ultimamente? Parliamone!",
                "films": []
            }
            return
        
        # ========== RECOMMENDATION FLOW (default) ==========
        
        # CULT FILMS SPECIAL HANDLING
        # Check for cult/classic patterns OR if context suggests cult films
        cult_patterns = ["cult", "classic", "classico", "classici", "culto", "vedere almeno una volta"]
        query_lower = user_message.lower()
        
        is_cult_query = any(pattern in query_lower for pattern in cult_patterns)
        
        # CONTEXT-AWARE: If we just discussed cult films and user asks for more
        if (not is_cult_query and 
            conversation_context and 
            conversation_context.get('should_use_context')):
            
            context_summary = conversation_context.get('context_summary', '').lower()
            # Check if context mentions cult films
            if any(word in context_summary for word in ['cult', 'classic', 'classico', 'imprescindibil']):
                # User is asking for more cult films
                follow_up_patterns = ['altri', 'ancora', 'more', 'dammene', 'suggeriscimi', 'altro']
                if any(pattern in query_lower for pattern in follow_up_patterns):
                    logger.info("✓ Context suggests continuing cult films discussion")
                    is_cult_query = True
        
        if is_cult_query:
            logger.info("Detected cult films query, using special handler")
            yield {"type": "status", "message": "Generando lista cult films..."}
            
            cult_result = handle_cult_films_query(
                user_message=user_message,
                language=response_language,
                country=user_country
            )
            
            if cult_result and cult_result.get("films"):
                all_films = cult_result["films"]
                
                yield {
                    "type": "tool_result",
                    "tool": "cult_films_search",
                    "message": f"Trovati {len(all_films)} cult films",
                    "count": len(all_films)
                }
                
                # Generate final response with cult films context
                yield {"type": "status", "message": "Generando suggerimenti personalizzati..."}
                
                # Build conversation summary
                conversation_summary = ""
                if history and len(history) > 0:
                    recent = history[-4:] if len(history) >= 4 else history
                    for msg in recent:
                        role = "User" if msg.get("role") == "user" else "You"
                        content = msg.get("content", "")[:200]
                        conversation_summary += f"{role}: {content}\n"
                else:
                    conversation_summary = "This is the start of the conversation."

                from base_prompts import get_full_system_prompt, RECOMMENDATION_AGENT_CONTEXT
                
                # Build system prompt
                system_prompt = get_full_system_prompt(
                    language=response_language,
                    context=RECOMMENDATION_AGENT_CONTEXT
                )
                
                films_summary = json.dumps({
                    "films": [
                        {
                            "title": f["title"],
                            "year": f["year"],
                            "genres": f["genres"],
                            "rating": f["rating"],
                            "overview": f["overview"],
                            "streaming": [p["name"] for p in f.get("streaming", [])]
                        }
                        for f in all_films
                    ]
                }, ensure_ascii=False, indent=2)
                
                # Extract requested quantity if present
                import re
                quantity_match = re.search(r'(\d+)\s*film', user_message.lower())
                requested_count = int(quantity_match.group(1)) if quantity_match else 5
                
                # Cap at available films
                suggested_count = min(requested_count, len(all_films))
                
                user_prompt = f"""User request: "{user_message}"

Conversation context:
{conversation_summary}

I FOUND these cult classic films that match the request:
{films_summary}

CRITICAL INSTRUCTIONS:
- The films above are SEARCH RESULTS I found, NOT films the user mentioned
- The user asked for {requested_count} films specifically
- These are CULT CLASSIC films (minimum 10+ years old)
- Explain WHY each film is considered cult (influential, ahead of its time, passionate following, etc.)
- Suggest {suggested_count} films with thoughtful explanations from the list above
- Mention streaming platforms when available
- End with a question to continue the conversation
- NEVER suggest these films are recent or new
- NEVER say "films you mentioned" - the user didn't mention any films"""

                # Generate response
                response = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=1000
                )
                
                final_text = response.choices[0].message.content
                
                # Extract mentioned films from text (same logic as normal flow)
                mentioned_films = []
                
                # Search for **Title** pattern
                bold_matches = re.findall(r'\*\*([^*]+)\*\*', final_text)
                
                for potential in bold_matches:
                    for film in all_films:
                        clean_potential = potential.lower().strip()
                        clean_title = film["title"].lower()
                        
                        if clean_potential in clean_title or clean_title in clean_potential:
                            if film not in mentioned_films:
                                mentioned_films.append(film)
                                break
                
                # Fallback: match in text
                if not mentioned_films:
                    for film in all_films:
                        if film["title"].lower() in final_text.lower():
                            mentioned_films.append(film)
                
                # Last resort: return requested count
                if not mentioned_films:
                    mentioned_films = all_films[:suggested_count]
                
                logger.debug(f"Mentioned {len(mentioned_films)} films in cult response")
                
                yield {
                    "type": "complete",
                    "text": final_text,
                    "films": mentioned_films
                }
                return
            else:
                # Fallback to normal flow if cult handler fails
                logger.warning("Cult handler failed, falling back to normal flow")
        
        # PRE-PROCESSING: decidi quale tool usare (ORA CON HISTORY!)
        tool_decision = analyze_query_with_llm(user_message, response_language, history)
        tool_name = tool_decision["tool"]
        tool_args = tool_decision["args"]
        
        logger.info(f"Query: {user_message}")
        logger.info(f"Tool decision: {tool_name}({tool_args})")
        
        # Definisci tool_descriptions con i18n
        tool_descriptions = {
            "get_popular_films": t("fetching_popular", response_language),
            "find_similar_films": t("fetching_similar", response_language, title=tool_args.get('film_title', ''))
        }
        
        # Migliora messaggio per search_films
        if tool_name == "search_films":
            msg_parts = []
            
            if "genre_ids" in tool_args and tool_args["genre_ids"]:
                genre_names = {
                    18: "drammatici", 35: "comici", 28: "d'azione", 27: "horror", 
                    53: "thriller", 10749: "romantici", 878: "fantascienza", 16: "animati"
                }
                
                genres = tool_args["genre_ids"]
                if len(genres) == 1:
                    genre_desc = genre_names.get(genres[0], "film")
                    msg_parts.append(f"film {genre_desc}")
                else:
                    genre_labels = [genre_names.get(g, "?") for g in genres[:2]]
                    msg_parts.append(f"film {' + '.join(genre_labels)}")
            else:
                msg_parts.append("film")
            
            if "year_range" in tool_args:
                years = tool_args["year_range"]
                msg_parts.append(f"{min(years)}-{max(years)}")
            elif "year" in tool_args:
                msg_parts.append(str(tool_args["year"]))
            
            if "rating_min" in tool_args:
                msg_parts.append(f"rating ≥{tool_args['rating_min']}")

            if "platform_filter" in tool_args:
                platform = tool_args["platform_filter"]
                msg_parts.insert(0, f"su {platform}")
            
            tool_descriptions["search_films"] = f"Cercando {' '.join(msg_parts)}"
        
        yield {
            "type": "tool_call",
            "tool": tool_name,
            "message": tool_descriptions.get(tool_name, f"Chiamando {tool_name}"),
            "args": tool_args
        }
        
        # ESEGUI il tool
        tool_result = execute_tool(tool_name, tool_args)
        all_films = tool_result.get("films", [])
        
        yield {
            "type": "tool_result",
            "tool": tool_name,
            "message": f"Trovati {len(all_films)} film",
            "count": len(all_films)
        }
        
        # Fallback se 0 risultati
        if len(all_films) == 0:
            platform_filter = tool_args.get("platform_filter")
            
            if platform_filter:
                # Specifico per piattaforma
                yield {"type": "status", "message": f"Nessun film trovato su {platform_filter}, espando ricerca..."}
                
                # Riprova senza filtro piattaforma
                fallback_args = {k: v for k, v in tool_args.items() if k != "platform_filter"}
                fallback_result = execute_tool(tool_name, fallback_args)
                all_films = fallback_result.get("films", [])
                
                # Riapplica filtro manualmente
                all_films = [
                    f for f in all_films
                    if any(p["name"] == platform_filter for p in f.get("streaming", []))
                ][:10]
                
                if len(all_films) == 0:
                    # IMPORTANTE: passa anche country e platform_filter al fallback
                    fallback_result = execute_tool("get_popular_films", {
                        "limit": 10, 
                        "platform_filter": platform_filter,
                        "country": tool_args.get("country", "IT")
                    })
                    all_films = fallback_result.get("films", [])
            else:
                # Fallback normale
                yield {"type": "status", "message": "Nessun risultato, cerco film popolari..."}
                fallback_result = execute_tool("get_popular_films", {
                    "limit": 10,
                    "country": tool_args.get("country", "IT")
                })
                all_films = fallback_result.get("films", [])
            
            yield {
                "type": "tool_result",
                "tool": "get_popular_films",
                "message": f"Trovati {len(all_films)} film",
                "count": len(all_films)
            }
        
        # SECONDA CHIAMATA - Genera risposta
        yield {"type": "status", "message": "Generando suggerimenti personalizzati..."}
        
        # ========== BUILD CONVERSATION SUMMARY ==========
        conversation_summary = ""
        if history and len(history) > 0:
            # Get last 2 exchanges (4 messages: user, assistant, user, assistant)
            recent = history[-4:] if len(history) >= 4 else history
            
            for msg in recent:
                role = "User" if msg.get("role") == "user" else "You"
                content = msg.get("content", "")[:200]  # Truncate if too long
                conversation_summary += f"{role}: {content}\n"
        else:
            conversation_summary = "This is the start of the conversation."
        # ================================================
        from base_prompts import get_full_system_prompt, RECOMMENDATION_AGENT_CONTEXT
        # Build system prompt from base_prompts
        system_prompt = get_full_system_prompt(
            language=response_language,
            context=RECOMMENDATION_AGENT_CONTEXT
        )
        
        films_summary = json.dumps({
            "films": [
                {
                    "title": f["title"],
                    "year": f["year"],
                    "genres": f["genres"],
                    "rating": f["rating"],
                    "overview": f["overview"],
                    "streaming": [p["name"] for p in f.get("streaming", [])]
                }
                for f in all_films[:10]
            ],
            "user_request": user_message
        }, ensure_ascii=False)
        
        # User prompt with conversation-specific instructions
        user_prompt = f"""USER'S LATEST MESSAGE: "{user_message}"

CONVERSATION CONTEXT:
{conversation_summary}

I found these {len(all_films)} films that match:
{films_summary}

YOUR ROLE:
You are NOT a robotic recommendation engine. You are a knowledgeable, passionate cinephile having a real conversation.

CRITICAL GUIDELINES:

1. **RESPOND TO THE USER'S ACTUAL MESSAGE**
   - If they comment on previous suggestions ("a me non è piaciuto", "not bad", "meh") → RESPOND to that comment FIRST
   - If they share an opinion → ENGAGE with it, agree/disagree, add insight
   - If they ask a question → ANSWER it naturally
   - If they make a request ("li voglio del 2025") → Acknowledge and suggest accordingly
   - NEVER ignore what they just said to mechanically list films

2. **BE CONVERSATIONAL, NOT TRANSACTIONAL**
   - Don't just list films like a database
   - Share WHY a film is interesting (director, themes, style, trivia)
   - Mention connections to other films they might know
   - Share insider knowledge or fun facts
   - Build on what they've said in the conversation

3. **PLATFORM MENTIONS (CRITICAL)**
   - Look at the "streaming" field for each film
   - IF "streaming" has platforms → mention them naturally ("it's on Netflix")
   - IF "streaming" is empty [] → say "in theaters" or "not on streaming yet"
   - NEVER invent platforms not in the streaming field
   - Films have ALREADY been filtered for requested platform

4. **SUGGEST THOUGHTFULLY**
   - Quality over quantity - better 1 perfect film than 3 mediocre ones
   - Use the "overview" to verify the film actually fits their request
   - Skip films with poor/missing descriptions
   - If nothing fits well, say so honestly and suggest alternatives

5. **KEEP THE CONVERSATION FLOWING**
   - Ask interesting questions about their taste, mood, preferences
   - Suggest related directors, actors, or themes worth exploring
   - Be curious about what they're really looking for
   - Reference previous parts of the conversation naturally

6. **FILM INSIGHTS & CONNECTIONS**
   - Compare to other films when relevant
   - Mention if a director has other notable work
   - Point out thematic or stylistic connections
   - Share context that enriches understanding
   - When relevant, explain what makes a film special

EXAMPLES OF GOOD VS BAD RESPONSES:

❌ Bad (robotic): "I recommend **Film X**. It's a thriller from 2023. Available on Netflix. The plot is about..."

✅ Good (conversational): "Oh, if you want something from 2025 specifically, **Film X** just dropped on Netflix and it's getting real buzz. The director previously did [other film], so if you liked that vibe, this could work. What kind of mood are you in tonight - something intense or more atmospheric?"

❌ Bad (ignores user comment): 
User: "a me non è piaciuto, sembrava fatto solo per soldi"
Bot: "Here are 3 recommendations: **Film A**, **Film B**..." [lists films mechanically]

✅ Good (engages with comment):
User: "a me non è piaciuto, sembrava fatto solo per soldi"
Bot: "I totally get that - you're right it felt rushed to capitalize on the franchise. Happens a lot with late sequels pushed by studios. If you want something that feels more authentic in that genre, **Film Y** is the opposite - real passion project, director spent years developing it. Have you seen their earlier work?"

❌ Bad (when user says "belli, ma..."): 
Bot: [compares Film 1 vs Film 2 as if they were mentioned]

✅ Good (when user says "belli, ma..."): 
Bot: "Glad you liked them! So for 2025 releases specifically, **Film Z** just came out..."

Remember: RESPOND to what they said, THEN suggest films naturally as part of the conversation.

Now respond naturally to: "{user_message}"
"""
        
        final_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=final_messages,
            max_tokens=1024,
            temperature=0.7
        )
        
        assistant_text = response.choices[0].message.content
        
        # EXTRACTION
        mentioned_films = []

        import re
        
        # Cerca **Titolo**
        bold_matches = re.findall(r'\*\*([^*]+)\*\*', assistant_text)
        
        for potential in bold_matches:
            for film in all_films:
                clean_potential = potential.lower().strip()
                clean_title = film["title"].lower()
                
                if clean_potential in clean_title or clean_title in clean_potential:
                    if film not in mentioned_films:
                        mentioned_films.append(film)
                        break
        
        # Fallback: match nel testo
        if not mentioned_films:
            for film in all_films:
                if film["title"].lower() in assistant_text.lower():
                    mentioned_films.append(film)
        
        # Ultimo resort: top 3 per rating
        if not mentioned_films and all_films:
            sorted_films = sorted(all_films, key=lambda x: x.get("rating", 0), reverse=True)
            mentioned_films = sorted_films[:3]
        
        logger.debug(f"Mentioned films: {[f['title'] for f in mentioned_films[:3]]}")
        
        yield {
            "type": "complete",
            "text": assistant_text,
            "films": mentioned_films[:3]
        }
    
    except Exception as e:
        logger.error(f"Stream error: {e}", exc_info=True)
        yield {
            "type": "error",
            "message": f"Errore: {str(e)}"
        }