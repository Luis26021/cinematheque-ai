from services.groq_client import call_groq, GroqRateLimitError
from logger_config import get_logger

logger = get_logger(__name__)


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
        response = call_groq(
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

    except GroqRateLimitError:
        logger.warning("Rate limited during intent detection, defaulting to recommendation")
        return {"intent": "recommendation", "entities": []}

    except Exception as e:
        print(f"Error in intent detection: {e}")
        return {"intent": "recommendation", "entities": []}
