"""
Conversation Memory System for Cinémathèque

Maintains persistent, cumulative memory of film discussions.
Not just film titles - full conversational context.
"""

import os
import json
from groq import Groq
from dotenv import load_dotenv
from logger_config import get_logger
from services.json_utils import safe_json_parse, sanitize_llm_json

logger = get_logger(__name__)
load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def extract_memory_from_turn(
    user_message: str,
    assistant_response: str,
    current_memory: dict,
    language: str = "it"
) -> dict:
    """
    LLM extracts salient information from this conversation turn.
    
    Returns updated memory with:
    - Films discussed (with context)
    - Directors/actors mentioned
    - Themes explored
    - User preferences revealed
    - Key moments
    """
    
    prompt = f"""You are analyzing a conversation about films to extract salient information.

CURRENT MEMORY:
{json.dumps(current_memory, indent=2, ensure_ascii=False)}

THIS TURN:
User: "{user_message}"
Assistant: "{assistant_response[:1000]}"

Your task: Extract what's NEW and IMPORTANT from this turn.

Look for:
1. **Films mentioned** - title, year, director, context (why mentioned)
2. **Directors/actors** - names, what was said about them
3. **Themes** - topics discussed (genre, style, era, movements)
4. **User preferences** - what they like/dislike, their taste
5. **Key moments** - important insights or discussion points

Rules:
- Only add NEW information (don't repeat what's in current memory)
- Be concise but specific
- Capture WHY things were mentioned, not just WHAT
- Focus on conversation flow, not just data extraction

Respond in JSON:
{{
    "films_discussed": [
        {{"title": "Film Title", "year": 1994, "director": "Director", "context": "why it came up"}}
    ],
    "directors_mentioned": ["Director Name"],
    "actors_mentioned": ["Actor Name"],
    "themes": ["theme or topic"],
    "user_preferences": {{
        "likes": ["what they like"],
        "dislikes": ["what they don't like"],
        "favorite_genres": ["genre"]
    }},
    "key_moments": ["important insight from this turn"],
    "current_topic": "what we're discussing right now"
}}

Examples:

Turn: User asks "why is Pulp Fiction cult?", Assistant explains nonlinear narrative
→ films_discussed: [{{"title": "Pulp Fiction", "year": 1994, "director": "Tarantino", "context": "user asked why it's cult - discussed nonlinear structure"}}]
   themes: ["cult films", "nonlinear storytelling"]
   key_moments: ["Explained how Pulp Fiction's structure broke conventions"]
   current_topic: "cult film aesthetics"

Turn: User says "I love dark comedies", Assistant suggests films
→ user_preferences: {{"likes": ["dark comedies"], "favorite_genres": ["comedy"]}}
   current_topic: "dark comedy recommendations"

Respond ONLY with valid JSON."""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.3
        )
        
        result_text = response.choices[0].message.content.strip()
        
        extracted = safe_json_parse(result_text, {
            "films_discussed": [],
            "directors_mentioned": [],
            "actors_mentioned": [],
            "themes": [],
            "user_preferences": {"likes": [], "dislikes": [], "favorite_genres": []},
            "key_moments": [],
            "current_topic": None
        })
        
        logger.info(f"✓ Memory extracted: {len(extracted.get('films_discussed', []))} films, {len(extracted.get('key_moments', []))} moments")
        
        return extracted
    
    except Exception as e:
        logger.error(f"Memory extraction failed: {e}")
        return {
            "films_discussed": [],
            "directors_mentioned": [],
            "actors_mentioned": [],
            "themes": [],
            "user_preferences": {"likes": [], "dislikes": [], "favorite_genres": []},
            "key_moments": [],
            "current_topic": None
        }


def update_memory(current_memory: dict, extracted_info: dict) -> dict:
    """
    Merge new information into existing memory.
    Deduplicate and keep memory concise.
    """
    
    updated = current_memory.copy()
    
    # Merge films (deduplicate by title+year)
    existing_films = {(f['title'].lower(), f.get('year')): f for f in updated.get('films_discussed', [])}
    for film in extracted_info.get('films_discussed', []):
        key = (film['title'].lower(), film.get('year'))
        if key not in existing_films:
            existing_films[key] = film
        else:
            # Update context if new info
            if film.get('context'):
                existing_films[key]['context'] = film['context']
    
    updated['films_discussed'] = list(existing_films.values())
    
    # Merge directors (deduplicate)
    directors = set(updated.get('directors_mentioned', []))
    directors.update(extracted_info.get('directors_mentioned', []))
    updated['directors_mentioned'] = list(directors)
    
    # Merge actors (deduplicate)
    actors = set(updated.get('actors_mentioned', []))
    actors.update(extracted_info.get('actors_mentioned', []))
    updated['actors_mentioned'] = list(actors)
    
    # Merge themes (deduplicate)
    themes = set(updated.get('themes', []))
    themes.update(extracted_info.get('themes', []))
    updated['themes'] = list(themes)
    
    # Merge preferences
    if 'user_preferences' not in updated:
        updated['user_preferences'] = {"likes": [], "dislikes": [], "favorite_genres": []}
    
    for key in ['likes', 'dislikes', 'favorite_genres']:
        existing = set(updated['user_preferences'].get(key, []))
        new_items = set(extracted_info.get('user_preferences', {}).get(key, []))
        updated['user_preferences'][key] = list(existing | new_items)
    
    # Add key moments (keep last 10)
    moments = updated.get('key_moments', [])
    moments.extend(extracted_info.get('key_moments', []))
    updated['key_moments'] = moments[-10:]  # Keep last 10 only
    
    # Update current topic
    if extracted_info.get('current_topic'):
        updated['current_topic'] = extracted_info['current_topic']
    
    logger.info(f"✓ Memory updated: {len(updated['films_discussed'])} films total, {len(updated['themes'])} themes")
    
    return updated


def get_memory_summary(memory: dict, language: str = "it") -> str:
    """
    Format memory for LLM context (concise summary).
    """
    
    if not memory or not any(memory.values()):
        return "This is the start of our conversation."
    
    summary_parts = []
    
    # Current topic
    if memory.get('current_topic'):
        summary_parts.append(f"Current discussion: {memory['current_topic']}")
    
    # Films discussed
    if memory.get('films_discussed'):
        films_text = ", ".join([
            f"{f['title']} ({f.get('year', '?')})"
            for f in memory['films_discussed'][:5]  # Top 5
        ])
        summary_parts.append(f"Films discussed: {films_text}")
    
    # Directors mentioned
    if memory.get('directors_mentioned'):
        directors_text = ", ".join(memory['directors_mentioned'][:5])
        summary_parts.append(f"Directors mentioned: {directors_text}")
    
    # Themes
    if memory.get('themes'):
        themes_text = ", ".join(memory['themes'][:5])
        summary_parts.append(f"Themes explored: {themes_text}")
    
    # User preferences
    prefs = memory.get('user_preferences', {})
    if prefs.get('likes'):
        likes_text = ", ".join(prefs['likes'][:3])
        summary_parts.append(f"User likes: {likes_text}")
    
    # Key moments (last 3)
    if memory.get('key_moments'):
        recent_moments = memory['key_moments'][-3:]
        moments_text = "; ".join(recent_moments)
        summary_parts.append(f"Key moments: {moments_text}")
    
    return "\n".join(summary_parts)


def initialize_memory() -> dict:
    """
    Create empty memory structure.
    """
    return {
        "films_discussed": [],
        "directors_mentioned": [],
        "actors_mentioned": [],
        "themes": [],
        "user_preferences": {
            "likes": [],
            "dislikes": [],
            "favorite_genres": []
        },
        "key_moments": [],
        "current_topic": None
    }


def should_respond_conversationally(user_message: str, memory: dict, language: str = "it") -> dict:
    """
    Determine if this query needs TMDB search or can be answered conversationally.
    
    Returns:
        {
            "conversational": bool,
            "reasoning": str,
            "suggested_approach": str
        }
    """
    
    memory_summary = get_memory_summary(memory, language)
    
    prompt = f"""Given this conversation memory and user query, determine if we need to search for films or can respond conversationally.

MEMORY:
{memory_summary}

USER QUERY: "{user_message}"

Decision criteria:
- **Search needed**: User asks for specific film details, wants recommendations, mentions unknown film
- **Conversational**: Discussing directors/actors we know, exploring themes from memory, asking opinions, follow-up questions

Examples:

Query: "why is Tarantino considered great?" + Memory has Pulp Fiction
→ Conversational (we can discuss using Pulp Fiction as example)

Query: "recommend me a thriller"
→ Search needed (need to find films)

Query: "tell me about Inception"
→ Search needed (specific film details)

Query: "what do you think of his dialogue style?" + Memory has Tarantino
→ Conversational (we know who "his" is from memory)

Respond in JSON:
{{
    "conversational": true/false,
    "reasoning": "why this decision",
    "suggested_approach": "how to respond"
}}

Respond ONLY with valid JSON."""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.2
        )
        
        result_text = response.choices[0].message.content.strip()
        
        result = safe_json_parse(result_text, {
            "conversational": False,
            "reasoning": "Error in check, defaulting to search",
            "suggested_approach": "search"
        })
        
        logger.info(f"✓ Conversational check: {result.get('conversational')} - {result.get('reasoning')}")
        
        return result
    
    except Exception as e:
        logger.error(f"Conversational check failed: {e}")
        # Default to search on error
        return {
            "conversational": False,
            "reasoning": "Error in check, defaulting to search",
            "suggested_approach": "search"
        }