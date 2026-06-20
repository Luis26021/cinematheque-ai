from justwatch import JustWatch
from typing import List, Dict
import time

# Cache in memoria (semplice)
_cache = {}
CACHE_TTL = 86400  # 24 ore

def get_streaming_availability(film_title: str, tmdb_id: int = None, country: str = "IT") -> List[Dict]:
    """Get where a film is available to stream"""
    
    # Check cache
    cache_key = f"{country}:{film_title}"
    if cache_key in _cache:
        cached_data, timestamp = _cache[cache_key]
        if time.time() - timestamp < CACHE_TTL:
            return cached_data
    
    try:
        jw = JustWatch(country=country)
        results = jw.search_for_item(query=film_title)
        
        if not results.get('items'):
            return []
        
        # Prendi primo match
        film = results['items'][0]
        offers = film.get('offers', [])
        
        # Map provider IDs to names
        provider_map = {
            8: "Netflix",
            9: "Amazon Prime Video",
            337: "Disney+",
            2: "Apple TV+",
            119: "Amazon Prime Video",
            # Aggiungi altri provider italiani
        }
        
        platforms = []
        seen = set()  # Deduplica
        
        for offer in offers:
            provider_id = offer.get('provider_id')
            monetization = offer.get('monetization_type')
            
            # Solo streaming (no rent/buy per ora)
            if monetization != 'flatrate':
                continue
            
            provider_name = provider_map.get(provider_id, f"Provider {provider_id}")
            
            if provider_name not in seen:
                platforms.append({
                    "name": provider_name,
                    "type": "stream",
                    "url": f"https://www.justwatch.com{film.get('full_path', '')}"
                })
                seen.add(provider_name)
        
        # Cache result
        _cache[cache_key] = (platforms, time.time())
        
        return platforms
    
    except Exception as e:
        print(f"Error getting availability: {e}")
        return []