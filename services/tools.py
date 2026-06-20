from typing import List, Dict, Optional
from services.tmdb import get_popular_films, search_films_by_query, find_similar_films
import random

# Tool definitions per Groq
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_films",
            "description": "Search for films by TITLE or GENRE keywords (e.g., 'inception', 'thriller', 'space movies'). Use when user mentions specific film names or genre terms. DO NOT use for platform-only queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (film title, genre, keyword like 'space movies', 'thriller italiano')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of results to return (default 10)",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_popular_films",
            "description": "Get currently popular/trending films. Use for general recommendations, especially with only platform filters (e.g., 'films on Netflix', 'something to watch'). This is the DEFAULT tool for simple requests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of films to return",
                        "default": 10
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_films",
            "description": "Find films similar to a given film. Use when user mentions 'like [film name]' or asks for similar recommendations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "film_title": {
                        "type": "string",
                        "description": "Title of the reference film"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of similar films to return",
                        "default": 5
                    }
                },
                "required": ["film_title"]
            }
        }
    }
]

def execute_tool(tool_name: str, arguments: dict) -> dict:
    """Execute a tool and return results"""

    # Estrai country code e tmdb_language
    country = arguments.get("country", "IT")
    tmdb_language = arguments.get("tmdb_language", "it-IT")
    
    if tool_name == "search_films":
        from services.tmdb import search_films_by_query, search_by_genre_and_year, get_availability_batch
        
        offset = arguments.get("offset", 0)
        limit = arguments.get("limit", 10)
        platform_filter = arguments.get("platform_filter")
        
        # Se c'è filtro piattaforma, fetch MOLTI più film
        fetch_multiplier = 10 if platform_filter else 3
        
        # SE la query contiene genre_ids, usa discover endpoint
        if "genre_ids" in arguments or "year" in arguments or "year_range" in arguments:
            import random
            genre_ids = arguments.get("genre_ids", [])
            year = arguments.get("year")
            year_range = arguments.get("year_range")
            rating_min = arguments.get("rating_min")
            
            # Varia sorting
            if year_range or (year and year >= 2023):
                sort_by = random.choice(["primary_release_date.desc", "popularity.desc", "vote_average.desc"])
            else:
                sort_by = "popularity.desc"
            
            print(f"DEBUG - Using discover with genres={genre_ids}, year={year}, year_range={year_range}, rating_min={rating_min}, sort={sort_by}")
            results = search_by_genre_and_year(genre_ids, year, year_range, rating_min, limit * fetch_multiplier, sort_by, tmdb_language)
            
            # Se multi-genre e 0 risultati, prova solo primo genere
            if len(results) == 0 and genre_ids and len(genre_ids) > 1:
                print(f"DEBUG - No results with all genres, trying first genre only")
                results = search_by_genre_and_year([genre_ids[0]], year, year_range, rating_min, limit * fetch_multiplier, sort_by, tmdb_language)
        else:
            query = arguments.get("query", "")
            
            # Se query vuota E c'è platform_filter, usa get_popular invece
            if not query and platform_filter:
                print(f"DEBUG - Empty query with platform filter, using get_popular_films instead")
                from services.tmdb import get_popular_films
                results = get_popular_films(limit * fetch_multiplier, country, tmdb_language)
            else:
                print(f"DEBUG - Using text search with query={query}")
                results = search_films_by_query(query, limit * fetch_multiplier, tmdb_language)
        
        print(f"DEBUG - After TMDB fetch: {len(results)} films")
        
        # FILTRA: rating >= 5.5 (o rating_min se specificato)
        min_rating = arguments.get("rating_min", 5.5)
        results = [f for f in results if f.get("rating", 0) >= min_rating]
        print(f"DEBUG - After rating filter (>={min_rating}): {len(results)} films")
        
        # Add streaming availability
        if results:
            film_ids = [f["id"] for f in results]
            print(f"DEBUG - Fetching availability for {len(film_ids)} films in country={country}...")
            availability = get_availability_batch(film_ids, country)
            for film in results:
                film["streaming"] = availability.get(film["id"], [])
        
        # FILTRA PER PIATTAFORMA SE RICHIESTA
        if platform_filter:
            print(f"\nDEBUG - Applying platform filter: '{platform_filter}'")
            print(f"DEBUG - Before filter: {len(results)} films")
            
            # Mostra sample
            print(f"\nDEBUG - Sample of films BEFORE platform filter:")
            for i, f in enumerate(results[:5]):
                platforms = [p["name"] for p in f.get("streaming", [])]
                print(f"  {i+1}. {f['title']} ({f['year']}) - Platforms: {platforms if platforms else 'NONE'}")
            
            # Mostra SOLO film disponibili su quella piattaforma
            filtered = [
                f for f in results 
                if any(p["name"] == platform_filter for p in f.get("streaming", []))
            ]
            
            print(f"\nDEBUG - After platform filter '{platform_filter}': {len(filtered)} films")
            if filtered:
                print(f"DEBUG - Films that PASSED filter:")
                for i, f in enumerate(filtered[:5]):
                    platforms = [p["name"] for p in f.get("streaming", [])]
                    print(f"  {i+1}. {f['title']} - {platforms}")
            
            results = filtered
        
        # PRIORITÀ: film con streaming disponibile
        with_streaming = [f for f in results if f.get("streaming")]
        without_streaming = [f for f in results if not f.get("streaming")]
        
        # Se piattaforma richiesta, abbiamo già solo quelli con streaming
        if platform_filter:
            results = with_streaming
        else:
            results = with_streaming + without_streaming
        
        # Randomizza un po' per varietà
        if len(results) > limit * 1.5:
            top = results[:int(limit * 1.5)]
            random.shuffle(top)
            results = top
        
        # ========== APPLY OFFSET (conversation history support) ==========
        print(f"DEBUG - Before offset: {len(results)} films, offset={offset}, limit={limit}")
        results = results[offset:offset + limit]  # Skip primi N, prendi successivi limit
        print(f"DEBUG - After offset: {len(results)} films")
        # ================================================================
        
        print(f"\nDEBUG - Final result count: {len(results)}\n")
        
        return {"films": results, "count": len(results)}
    
    elif tool_name == "get_popular_films":
        from services.tmdb import get_popular_films, get_availability_batch
        
        offset = arguments.get("offset", 0)
        limit = arguments.get("limit", 10)
        platform_filter = arguments.get("platform_filter")
        
        # Fetch molti più film se c'è filtro piattaforma O offset
        fetch_multiplier = 5 if platform_filter else 2
        if offset > 0:
            fetch_multiplier = max(fetch_multiplier, 3)  # Almeno 3x se c'è offset
        
        fetch_limit = limit * fetch_multiplier + offset  # Fetch abbastanza per coprire offset
        
        print(f"\nDEBUG - get_popular_films: limit={limit}, offset={offset}, fetch_limit={fetch_limit}, platform_filter={platform_filter}, country={country}\n")
        
        results = get_popular_films(fetch_limit, country, tmdb_language)
        
        print(f"DEBUG - After get_popular_films: {len(results)} films")
        
        # FILTRA: rating >= 5.5 (o rating_min se specificato)
        min_rating = arguments.get("rating_min", 5.5)
        results = [f for f in results if f.get("rating", 0) >= min_rating]
        
        print(f"DEBUG - After rating filter (>={min_rating}): {len(results)} films")
        
        # Add streaming availability
        if results:
            film_ids = [f["id"] for f in results]
            print(f"DEBUG - Fetching availability for {len(film_ids)} films in country={country}...")
            availability = get_availability_batch(film_ids, country)
            
            films_with_availability = 0
            for film in results:
                avail = availability.get(film["id"], [])
                film["streaming"] = avail
                if avail:
                    films_with_availability += 1
            
            print(f"DEBUG - Films with availability data: {films_with_availability}/{len(results)}")
        
        # FILTRA PER PIATTAFORMA SE RICHIESTA
        if platform_filter:
            print(f"\nDEBUG - Applying platform filter: '{platform_filter}'")
            print(f"DEBUG - Before filter: {len(results)} films")
            
            # Mostra sample
            print(f"\nDEBUG - Sample BEFORE filter:")
            for i, f in enumerate(results[:5]):
                platforms = [p["name"] for p in f.get("streaming", [])]
                print(f"  {i+1}. {f['title']} - {platforms if platforms else 'NONE'}")
            
            filtered = [
                f for f in results 
                if any(p["name"] == platform_filter for p in f.get("streaming", []))
            ]
            
            print(f"\nDEBUG - After filter: {len(filtered)} films")
            if filtered:
                print(f"DEBUG - Films that PASSED:")
                for i, f in enumerate(filtered[:5]):
                    platforms = [p["name"] for p in f.get("streaming", [])]
                    print(f"  {i+1}. {f['title']} - {platforms}")
            
            results = filtered
        
        # PRIORITÀ: streaming disponibile
        with_streaming = [f for f in results if f.get("streaming")]
        without_streaming = [f for f in results if not f.get("streaming")]
        
        if platform_filter:
            results = with_streaming
        else:
            results = with_streaming + without_streaming
        
        # ========== APPLY OFFSET (conversation history support) ==========
        print(f"DEBUG - Before offset: {len(results)} films, offset={offset}, limit={limit}")
        results = results[offset:offset + limit]  # Skip primi N, prendi successivi limit
        print(f"DEBUG - After offset: {len(results)} films")
        # ================================================================
        
        print(f"\nDEBUG - Final: {len(results)} films\n")
        
        return {"films": results, "count": len(results)}
    
    elif tool_name == "find_similar_films":
        from services.tmdb import find_similar_films, get_availability_batch
        
        film_title = arguments.get("film_title", "")
        offset = arguments.get("offset", 0)
        limit = arguments.get("limit", 5)
        platform_filter = arguments.get("platform_filter")
        
        # Fetch più film se c'è filtro piattaforma O offset
        fetch_multiplier = 5 if platform_filter else 2
        if offset > 0:
            fetch_multiplier = max(fetch_multiplier, 3)
        
        results = find_similar_films(film_title, limit * fetch_multiplier + offset, tmdb_language)
        
        # FILTRA: rating >= 5.5
        min_rating = arguments.get("rating_min", 5.5)
        results = [f for f in results if f.get("rating", 0) >= min_rating]
        
        # Add streaming availability
        if results:
            film_ids = [f["id"] for f in results]
            availability = get_availability_batch(film_ids, country)
            for film in results:
                film["streaming"] = availability.get(film["id"], [])
        
        # FILTRA PER PIATTAFORMA SE RICHIESTA
        if platform_filter:
            print(f"DEBUG - Filtering similar films for platform: {platform_filter}")
            filtered = [
                f for f in results 
                if any(p["name"] == platform_filter for p in f.get("streaming", []))
            ]
            print(f"DEBUG - After platform filter: {len(filtered)} films")
            results = filtered
        
        # PRIORITÀ: streaming disponibile
        with_streaming = [f for f in results if f.get("streaming")]
        without_streaming = [f for f in results if not f.get("streaming")]
        
        if platform_filter:
            results = with_streaming
        else:
            results = with_streaming + without_streaming
        
        # ========== APPLY OFFSET (conversation history support) ==========
        print(f"DEBUG - Before offset: {len(results)} films, offset={offset}, limit={limit}")
        results = results[offset:offset + limit]  # Skip primi N, prendi successivi limit
        print(f"DEBUG - After offset: {len(results)} films")
        # ================================================================
        
        return {"films": results, "count": len(results)}
    
    else:
        return {"error": f"Unknown tool: {tool_name}"}
