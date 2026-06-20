import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def detect_language_and_country(user_message: str) -> str:
    """Detect user language and return appropriate TMDB country code"""
    
    # Quick pattern matching per casi comuni (fast path)
    italian_keywords = ['film', 'guardare', 'stasera', 'disponibile', 'consiglia', 'qualcosa', 'vedere']
    english_keywords = ['movie', 'watch', 'tonight', 'recommend', 'something', 'available']
    spanish_keywords = ['película', 'ver', 'esta noche', 'recomienda', 'disponible']
    french_keywords = ['regarder', 'ce soir', 'recommande', 'disponible']
    german_keywords = ['schauen', 'heute abend', 'empfehlen', 'verfügbar']
    
    msg_lower = user_message.lower()
    
    # Conta match per lingua
    it_score = sum(1 for kw in italian_keywords if kw in msg_lower)
    en_score = sum(1 for kw in english_keywords if kw in msg_lower)
    es_score = sum(1 for kw in spanish_keywords if kw in msg_lower)
    fr_score = sum(1 for kw in french_keywords if kw in msg_lower)
    de_score = sum(1 for kw in german_keywords if kw in msg_lower)
    
    # Se match chiaro, ritorna subito
    scores = {'IT': it_score, 'US': en_score, 'ES': es_score, 'FR': fr_score, 'DE': de_score}
    max_score = max(scores.values())
    
    if max_score >= 2:  # Almeno 2 keyword match
        country = max(scores, key=scores.get)
        print(f"DEBUG - Fast language detection: {country} (score: {max_score})")
        return country
    
    # Fallback: LLM detection per casi ambigui
    try:
        prompt = f"""Detect the language of this user message and return the appropriate country code for movie streaming availability.

User message: "{user_message}"

Language → Country mapping:
- Italian → IT
- English (any region) → US
- Spanish → ES
- French → FR
- German → DE
- Portuguese → BR
- Other European → GB
- Other → US

Rules:
- Return ONLY the 2-letter country code in uppercase
- No explanation, just the code
- If mixed languages, pick the dominant one
- If uncertain, return US

Country code:"""

        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0
        )
        
        country = response.choices[0].message.content.strip().upper()
        
        # Validate
        valid_countries = ['IT', 'US', 'ES', 'FR', 'DE', 'GB', 'BR', 'CA', 'AU', 'MX', 'AR']
        if country in valid_countries:
            print(f"DEBUG - LLM language detection: {country}")
            return country
        else:
            print(f"DEBUG - Invalid LLM response '{country}', defaulting to US")
            return 'US'
    
    except Exception as e:
        print(f"ERROR in language detection: {e}, defaulting to US")
        return 'US'