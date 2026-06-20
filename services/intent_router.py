import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def detect_intent(user_message: str) -> dict:
    """Rileva l'intent della query utente"""
    
    prompt = f"""Analizza questa richiesta e classifica l'intent:

RICHIESTA: "{user_message}"

INTENTS POSSIBILI:
1. "recommendation" - vuole suggerimenti/consigli su cosa guardare
2. "review" - chiede opinione/recensione su un film specifico
3. "comparison" - confronta film o chiede quale scegliere tra opzioni
4. "info" - chiede info su film/attore/regista (plot, cast, anno)
5. "person_filmography" - chiede filmografia di attore/regista (migliori/peggiori/ultimi film)
6. "chat" - conversazione generica, saluti, domande non legate a film

ESEMPI:
"consigliami un thriller" → recommendation
"che ne pensi di Inception?" → review
"meglio Dune o Interstellar?" → comparison
"chi ha diretto Pulp Fiction?" → info
"i 3 migliori film di Scorsese" → person_filmography
"filmografia di Ryan Gosling" → person_filmography
"peggiori film di Adam Sandler" → person_filmography
"ultimi film diretti da Nolan" → person_filmography
"ciao come stai?" → chat

Rispondi SOLO con un JSON:
{{"intent": "...", "entities": ["film1", "film2"]}}

Dove entities contiene titoli di film menzionati (se presenti).
"""
    
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.3
        )
        
        import json
        result_text = response.choices[0].message.content.strip()
        
        # Rimuovi markdown se presente
        if result_text.startswith("```json"):
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        
        result = json.loads(result_text)
        print(f"DEBUG - Intent detected: {result}")
        return result
    
    except Exception as e:
        print(f"Error in intent detection: {e}")
        # Fallback: assume recommendation
        return {"intent": "recommendation", "entities": []}