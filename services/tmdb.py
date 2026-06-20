import requests
import os
from typing import List, Dict, cast
from dotenv import load_dotenv
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from logger_config import get_logger

load_dotenv()
logger = get_logger(__name__)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"

# Configure session with retry logic
session = requests.Session()
retry_strategy = Retry(
    total=3,                      # 3 retry attempts
    backoff_factor=0.5,           # wait 0.5s, 1s, 2s between retries
    status_forcelist=[500, 502, 503, 504, 429],  # retry on these HTTP codes
    allowed_methods=["GET"]       # only retry GET requests
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)

# Genre mapping
GENRE_MAP = {
    28: "Azione", 12: "Avventura", 16: "Animazione",
    35: "Commedia", 80: "Crime", 18: "Dramma",
    14: "Fantasy", 27: "Horror", 878: "Fantascienza",
    53: "Thriller", 10749: "Romantico", 10751: "Famiglia",
    36: "Storia", 37: "Western", 10752: "Guerra",
    99: "Documentario", 9648: "Mistero", 10770: "TV Movie"
}

def safe_tmdb_request(url: str, params: dict, timeout: int = 10) -> dict:
    """
    Make a safe TMDB API request with error handling
    
    Returns:
        Response JSON or empty dict on error
    """
    try:
        logger.debug(f"TMDB request: {url} with params: {params}")
        response = session.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    
    except requests.Timeout:
        logger.error(f"TMDB timeout after {timeout}s: {url}")
        return {}
    
    except requests.HTTPError as e:
        if e.response.status_code == 401:
            logger.critical("TMDB API key invalid or missing!")
        elif e.response.status_code == 429:
            logger.warning("TMDB rate limit exceeded")
        else:
            logger.error(f"TMDB HTTP error {e.response.status_code}: {url}")
        return {}
    
    except requests.RequestException as e:
        logger.error(f"TMDB request failed: {e}")
        return {}
    
    except Exception as e:
        logger.error(f"Unexpected error in TMDB request: {e}", exc_info=True)
        return {}


def get_popular_films(limit: int = 30, country: str = "IT", language: str = "it-IT") -> List[Dict]:
    """Fetch popular films with robust error handling"""
    
    logger.info(f"Fetching popular films: limit={limit}, country={country}, lang={language}")
    
    url = f"{BASE_URL}/movie/popular"
    params = {
        "api_key": TMDB_API_KEY,
        "language": language,
        "region": country,
        "page": 1
    }
    
    data = safe_tmdb_request(url, params)
    if not data:
        logger.warning("No data from TMDB popular endpoint")
        return []
    
    films = []
    for movie in data.get("results", [])[:limit]:
        # Validate required fields
        if not all([movie.get("id"), movie.get("title"), movie.get("poster_path")]):
            continue
        
        overview = movie.get("overview", "").strip()
        if not overview or len(overview) < 50:
            continue
        
        if movie.get("vote_count", 0) < 10:
            continue
        
        try:
            film_obj = {
                "id": movie["id"],
                "title": movie["title"],
                "year": movie.get("release_date", "")[:4] if movie.get("release_date") else "N/A",
                "overview": overview[:200],
                "genres": [GENRE_MAP.get(gid, "Altro") for gid in movie.get("genre_ids", [])],
                "rating": round(movie.get("vote_average", 0), 1),
                "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}",
                "link": f"https://www.themoviedb.org/movie/{movie['id']}"
            }
            films.append(film_obj)
        except Exception as e:
            logger.warning(f"Error processing film {movie.get('id')}: {e}")
            continue
    
    logger.info(f"Returning {len(films)} popular films")
    return films

def fetch_movie_credits(movie_id: int, language: str = "it-IT") -> dict:
    """Fetch cast e crew per un film specifico con logging dettagliato"""
    
    logger.info(f"Fetching credits for movie_id={movie_id}")
    
    try:
        url = f"{BASE_URL}/movie/{movie_id}/credits"
        params = {
            "api_key": TMDB_API_KEY,
            "language": language
        }
        
        logger.debug(f"Credits URL: {url}")
        logger.debug(f"Credits params: {params}")
        
        response = requests.get(url, params=params, timeout=10)
        
        # Check response status
        if response.status_code != 200:
            logger.error(f"Credits API returned status {response.status_code}")
            logger.error(f"Response body: {response.text[:200]}")
            return {"cast": [], "director": None}
        
        response.raise_for_status()
        data = response.json()
        
        # Debug: vedi cosa ritorna API
        logger.debug(f"Credits response keys: {data.keys()}")
        logger.debug(f"Cast count: {len(data.get('cast', []))}")
        logger.debug(f"Crew count: {len(data.get('crew', []))}")
        
        # Top 5 attori principali
        cast_list = data.get("cast", [])
        cast = [actor["name"] for actor in cast_list[:5]]
        
        # Regista
        director = None
        crew_list = data.get("crew", [])
        for crew in crew_list:
            if crew.get("job") == "Director":
                director = crew["name"]
                logger.debug(f"Found director: {director}")
                break
        
        if not director:
            logger.warning(f"No director found in {len(crew_list)} crew members")
        
        logger.info(f"✓ Credits fetched: {len(cast)} actors, director={director}")
        
        return {
            "cast": cast,
            "director": director
        }
    
    except requests.Timeout:
        logger.error(f"TIMEOUT fetching credits for movie {movie_id}")
        return {"cast": [], "director": None}
    
    except requests.RequestException as e:
        logger.error(f"REQUEST ERROR fetching credits: {e}")
        return {"cast": [], "director": None}
    
    except KeyError as e:
        logger.error(f"KEY ERROR parsing credits response: {e}")
        logger.error(f"Response data: {data}")
        return {"cast": [], "director": None}
    
    except Exception as e:
        logger.error(f"UNEXPECTED ERROR fetching credits: {e}", exc_info=True)
        return {"cast": [], "director": None}

def search_films_by_query(query: str, limit: int = 10, language: str = "it-IT") -> List[Dict]:
    """Search films with error handling"""
    
    logger.info(f"Searching films: query='{query}', lang={language}")
    
    url = f"{BASE_URL}/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "language": language,
        "query": query,
        "page": 1
    }
    
    data = safe_tmdb_request(url, params, timeout=5)
    if not data:
        return []
    
    films = []
    for movie in data.get("results", [])[:limit]:
        if not movie.get("poster_path"):
            continue

        credits = fetch_movie_credits(movie["id"], language)
        
        try:
            films.append({
                "id": movie["id"],
                "title": movie["title"],
                "year": movie.get("release_date", "")[:4] if movie.get("release_date") else "N/A",
                "overview": movie.get("overview", "Nessuna descrizione disponibile")[:200],
                "genres": [GENRE_MAP.get(gid, "Altro") for gid in movie.get("genre_ids", [])],
                "rating": round(movie.get("vote_average", 0), 1),
                "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}",
                "cast": credits["cast"],
                "director": credits["director"]
            })
        except Exception as e:
            logger.warning(f"Error processing search result: {e}")
            continue
    
    logger.info(f"Found {len(films)} films for query '{query}'")
    return films


def find_similar_films(film_title: str, limit: int = 5, language: str = "it-IT") -> List[Dict]:
    """Find similar films with error handling"""
    
    logger.info(f"Finding similar films to '{film_title}'")
    
    # First, search for the film
    search_url = f"{BASE_URL}/search/movie"
    search_params = {
        "api_key": TMDB_API_KEY,
        "language": language,
        "query": film_title,
        "page": 1
    }
    
    search_data = safe_tmdb_request(search_url, search_params, timeout=5)
    if not search_data or not search_data.get("results"):
        logger.warning(f"Film not found: '{film_title}'")
        return []
    
    film_id = search_data["results"][0]["id"]
    logger.debug(f"Found film ID: {film_id}")
    
    # Get similar films
    similar_url = f"{BASE_URL}/movie/{film_id}/similar"
    similar_params = {
        "api_key": TMDB_API_KEY,
        "language": language,
        "page": 1
    }
    
    similar_data = safe_tmdb_request(similar_url, similar_params, timeout=5)
    if not similar_data:
        return []
    
    films = []
    for movie in similar_data.get("results", [])[:limit]:
        if not movie.get("poster_path"):
            continue
        credits = fetch_movie_credits(movie["id"], language)
        try:
            films.append({
                "id": movie["id"],
                "title": movie["title"],
                "year": movie.get("release_date", "")[:4] if movie.get("release_date") else "N/A",
                "overview": movie.get("overview", "Nessuna descrizione disponibile")[:200],
                "genres": [GENRE_MAP.get(gid, "Altro") for gid in movie.get("genre_ids", [])],
                "rating": round(movie.get("vote_average", 0), 1),
                "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}",
                "cast": credits["cast"],
                "director": credits["director"]
            })
        except Exception as e:
            logger.warning(f"Error processing similar film: {e}")
            continue
    
    logger.info(f"Found {len(films)} similar films")
    return films


def get_streaming_availability(film_id: int, country: str = "IT") -> List[Dict]:
    """Get streaming availability with error handling"""
    
    url = f"{BASE_URL}/movie/{film_id}/watch/providers"
    params = {"api_key": TMDB_API_KEY}
    
    data = safe_tmdb_request(url, params, timeout=5)
    if not data:
        return []
    
    country_data = data.get("results", {}).get(country, {})
    if not country_data:
        # Fallback to US if no data for requested country
        country_data = data.get("results", {}).get("US", {})
    
    platforms = []
    try:
        for provider in country_data.get("flatrate", []):
            platforms.append({
                "name": provider["provider_name"],
                "type": "stream",
                "logo": f"https://image.tmdb.org/t/p/original{provider['logo_path']}",
                "link": country_data.get("link", "")
            })
    except Exception as e:
        logger.warning(f"Error parsing availability data for film {film_id}: {e}")
    
    return platforms


def get_availability_batch(film_ids: List[int], country: str = "IT") -> Dict[int, List[Dict]]:
    """Get availability for multiple films with rate limiting"""
    
    results = {}
    total_with_streaming = 0
    
    for i, film_id in enumerate(film_ids):
        availability = get_streaming_availability(film_id, country)
        results[film_id] = availability
        
        if availability:
            total_with_streaming += 1
        
        # Rate limiting: small delay between requests
        if i < len(film_ids) - 1:  # Don't sleep after last request
            time.sleep(0.15)
    
    logger.info(f"Availability check: {total_with_streaming}/{len(film_ids)} films have streaming")
    return results


def search_by_genre_and_year(genre_ids: list, year: int = None, year_range: list = None, 
                             rating_min: float = None, limit: int = 10, 
                             sort_by: str = "popularity.desc", language: str = "it-IT"):
    """Search with filters using discover endpoint"""
    
    logger.info(f"Discover search: genres={genre_ids}, year={year}, range={year_range}, rating_min={rating_min}")
    
    url = f"{BASE_URL}/discover/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "language": language,
        "sort_by": sort_by,
        "vote_count.gte": 20
    }
    
    if rating_min:
        params["vote_average.gte"] = rating_min
    
    if genre_ids:
        params["with_genres"] = ",".join(map(str, genre_ids))
    
    if year_range:
        params["primary_release_date.gte"] = f"{min(year_range)}-01-01"
        params["primary_release_date.lte"] = f"{max(year_range)}-12-31"
    elif year:
        params["primary_release_year"] = year
    
    data = safe_tmdb_request(url, params)
    if not data:
        return []
    
    results = []
    for movie in data.get("results", [])[:limit * 2]:
        if not movie.get("poster_path"):
            continue
        
        overview = movie.get("overview", "").strip()
        if not overview or len(overview) < 50:
            continue
        
        if movie.get("vote_count", 0) < 10:
            continue
        
        if genre_ids:
            movie_genres = movie.get("genre_ids", [])
            if not any(gid in movie_genres for gid in genre_ids):
                continue
        
        try:
            film = {
                "id": movie["id"],
                "title": movie["title"],
                "year": movie.get("release_date", "")[:4] if movie.get("release_date") else "N/A",
                "overview": overview,
                "genres": [GENRE_MAP.get(gid, "Altro") for gid in movie.get("genre_ids", [])],
                "rating": round(movie.get("vote_average", 0), 1),
                "poster": f"https://image.tmdb.org/t/p/w500{movie['poster_path']}",
                "link": f"https://www.themoviedb.org/movie/{movie['id']}"
            }
            results.append(film)
        except Exception as e:
            logger.warning(f"Error processing discover result: {e}")
            continue
    
    logger.info(f"Discover returned {len(results)} films")
    return results


def search_person(name: str, language: str = "it-IT") -> List[Dict]:
    """
    Search for a person (actor/director) by name
    
    Args:
        name: Person's name to search
        language: Language for results
        
    Returns:
        List of person objects with:
        - id: TMDB person ID
        - name: Person's name
        - known_for_department: 'Acting' or 'Directing'
        - profile_path: Profile image URL
        - known_for: List of notable films
    """
    logger.info(f"Searching person: name='{name}', lang={language}")
    
    url = f"{BASE_URL}/search/person"
    params = {
        "api_key": TMDB_API_KEY,
        "query": name,
        "language": language,
        "include_adult": False
    }
    
    data = safe_tmdb_request(url, params)
    
    if not data or "results" not in data:
        logger.warning(f"Person search failed for '{name}'")
        return []
    
    results = []
    for person in data["results"][:5]:  # Top 5 matches
        try:
            person_obj = {
                "id": person["id"],
                "name": person["name"],
                "known_for_department": person.get("known_for_department", "Unknown"),
                "profile_path": f"https://image.tmdb.org/t/p/w500{person['profile_path']}" if person.get("profile_path") else None,
                "known_for": [film.get("title", film.get("name", "Unknown")) for film in person.get("known_for", [])][:3]
            }
            results.append(person_obj)
        except Exception as e:
            logger.warning(f"Error processing person result: {e}")
            continue
    
    # Smart filtering: se primo risultato matcha esattamente, scarta altri
    if results and results[0]["name"].lower() == name.lower():
        logger.info(f"Exact match found: '{results[0]['name']}', discarding other fuzzy matches")
        results = [results[0]]
    
    logger.info(f"Found {len(results)} people for '{name}'")
    return results


def get_person_filmography(person_id: int, role: str = "all", language: str = "it-IT") -> List[Dict]:
    """
    Get filmography for a person
    
    Args:
        person_id: TMDB person ID
        role: Filter by role - 'director', 'actor', or 'all'
        language: Language for results
        
    Returns:
        List of films with full details including credits
    """
    logger.info(f"Fetching filmography: person_id={person_id}, role={role}")
    
    url = f"{BASE_URL}/person/{person_id}/movie_credits"
    params = {
        "api_key": TMDB_API_KEY,
        "language": language
    }
    
    data = safe_tmdb_request(url, params)
    
    if not data:
        logger.warning(f"Filmography fetch failed for person_id={person_id}")
        return []
    
    films = []
    
    # Collect based on role
    if role in ["director", "all"]:
        for movie in data.get("crew", []):
            if movie.get("job") == "Director":
                films.append(("director", movie))
    
    if role in ["actor", "all"]:
        for movie in data.get("cast", []):
            films.append(("actor", movie))
    
    # Process and deduplicate
    seen_ids = set()
    results = []
    
    for role_type, movie in films:
        if movie["id"] in seen_ids:
            continue
        seen_ids.add(movie["id"])
        
        try:
            # Fetch full details with credits
            full_movie = get_film_details(movie["id"], language=language)
            
            if full_movie:
                full_movie["role_in_film"] = role_type  # Tag with role
                results.append(full_movie)
        
        except Exception as e:
            logger.warning(f"Error processing filmography entry: {e}")
            continue
    
    # ========================================================
    # SMART FILTERING: Canonical films only
    # ========================================================
    canonical_films = []
    
    for film in results:
        # Filter 1: Runtime > 70 mins (no shorts/documentaries)
        if film.get("runtime", 0) < 70:
            continue
        
        # Filter 2: Vote count > 500 (real consensus, no obscure films)
        if film.get("vote_count", 0) < 500:
            continue
        
        # Filter 3: Exclude documentaries (usually not what user wants)
        genres = [g.lower() for g in film.get("genres", [])]
        if "documentario" in genres or "documentary" in genres:
            continue
        
        canonical_films.append(film)
    
    logger.info(f"Filtered to {len(canonical_films)} canonical films (from {len(results)} total)")
    
    # ========================================================
    # WEIGHTED SCORING: rating × log(vote_count + popularity)
    # ========================================================
    import math
    
    for film in canonical_films:
        rating = film.get("rating", 0)
        vote_count = film.get("vote_count", 0)
        popularity = film.get("popularity", 0)
        
        # Weighted score favors films with both high rating AND high consensus
        weighted_score = rating * math.log(vote_count + popularity + 1)
        film["weighted_score"] = round(weighted_score, 2)
    
    # Sort by weighted score (best curation)
    canonical_films.sort(key=lambda x: -x.get("weighted_score", 0))
    
    logger.info(f"Filmography returned {len(canonical_films)} canonical films")
    return canonical_films


def get_film_details(movie_id: int, language: str = "it-IT") -> Dict:
    """
    Get full film details including credits
    Used by filmography to get complete film info
    """
    url = f"{BASE_URL}/movie/{movie_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": language
    }
    
    data = safe_tmdb_request(url, params)
    
    if not data:
        return {}
    
    # Fetch credits
    credits = fetch_movie_credits(movie_id)
    
    # Build film object
    film = {
        "id": data["id"],
        "title": data.get("title", "Unknown"),
        "year": data.get("release_date", "")[:4] if data.get("release_date") else "N/A",
        "overview": data.get("overview", ""),
        "genres": [g["name"] for g in data.get("genres", [])],
        "rating": round(data.get("vote_average", 0), 1),
        "popularity": data.get("popularity", 0),
        "runtime": data.get("runtime", 0),  # Added for filtering
        "vote_count": data.get("vote_count", 0),  # Added for weighted scoring
        "poster": f"https://image.tmdb.org/t/p/w500{data['poster_path']}" if data.get("poster_path") else None,
        "link": f"https://www.themoviedb.org/movie/{data['id']}",
        "cast": credits.get("cast", []),
        "director": credits.get("director", "Unknown")
    }
    
    return film