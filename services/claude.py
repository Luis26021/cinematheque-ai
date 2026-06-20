import os
import json
from groq import Groq
from dotenv import load_dotenv
from services.tools import TOOLS, execute_tool

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_film_suggestion(user_message: str, history: list) -> dict:
    """Chiama Groq con function calling per suggerimento film"""
    
    system_prompt = """Sei un esperto consigliere di film. Aiuti le persone a scegliere cosa guardare.

HAI ACCESSO A QUESTI TOOLS:
- search_films: cerca film per titolo, genere, o parole chiave
- get_popular_films: ottieni film popolari/trending DEFAULT per richieste semplici come "dammi [tot] film leggeri" oppure "consigliami film recenti" oppure "dammi [tot] film su [piattaforma]"
- find_similar_films: trova film simili a uno specifico

CRITERI DI QUALITÀ (già applicati automaticamente):
- Tutti i film hanno rating >= 6.0/10
- Film disponibili in streaming hanno priorità

REGOLE:
- Suggerisci principalmente film disponibili in streaming (Netflix, Prime, Disney+, etc.)
- Se un film non ha streaming, menzionalo solo se molto rilevante
- Dopo aver ricevuto risultati, suggerisci 1-3 film con spiegazione
- Menziona sempre dove guardare il film (es: "Disponibile su Netflix")
- Sii conversazionale e amichevole

ESEMPI:
User: "Voglio qualcosa di leggero"
→ Usa get_popular_films, suggerisci commedie con streaming

User: "Qualcosa come Inception"
→ Usa find_similar_films("Inception"), dai priorità a quelli con streaming

User: "Film di fantascienza recenti"
→ Usa search_films("sci-fi 2024")
"""

    # Build messages
    messages = [
        {"role": "system", "content": system_prompt},
        *[{"role": m["role"], "content": m["content"]} for m in history],
        {"role": "user", "content": user_message}
    ]
    
    try:
        # Initial call to Groq with tools
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=2048,
            temperature=0.7
        )
        
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        
        # If no tool calls, return direct response
        if not tool_calls:
            return {
                "text": response_message.content or "Non ho trovato nulla di rilevante.",
                "films": []
            }
        
        # Execute tool calls
        messages.append(response_message)
        
        all_films = []
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            print(f"Calling tool: {function_name} with args: {function_args}")
            
            # Execute tool
            tool_result = execute_tool(function_name, function_args)
            all_films.extend(tool_result.get("films", []))
            
            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": json.dumps(tool_result)
            })
        
        # CAMBIA SYSTEM PROMPT per seconda chiamata
        # Rimuovi il vecchio system prompt
        messages_for_final = [m for m in messages if m.get("role") != "system"]
        
        # Aggiungi nuovo system prompt senza tools
        final_system_prompt = """Sei un esperto consigliere di film. 

Hai appena ricevuto una lista di film di qualità (rating >= 6.0).

REGOLE:
- PRIORITÀ ASSOLUTA: suggerisci film disponibili in streaming
- Per ogni film suggerito, menziona dove guardarlo (Netflix, Prime, etc.)
- Se un film non ha streaming, suggeriscilo SOLO se molto rilevante alla richiesta
- Spiega brevemente perché consigli ogni film (max 2-3 frasi)
- Menziona i titoli esatti
- Formato: "Ti consiglio **[Titolo]** disponibile su [Piattaforma]"
"""

        messages_for_final.insert(0, {"role": "system", "content": final_system_prompt})
        
        # Second call WITHOUT tools
        second_response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=messages_for_final,
            max_tokens=1024,
            temperature=0.7
        )
        
        assistant_text = second_response.choices[0].message.content
        
        # Extract mentioned films
        mentioned_films = []
        for film in all_films:
            if film["title"].lower() in assistant_text.lower():
                mentioned_films.append(film)
        
        # If no films mentioned but we have results, include top 3
        if not mentioned_films and all_films:
            mentioned_films = all_films[:3]
        
        return {
            "text": assistant_text,
            "films": mentioned_films[:3]
        }
    
    except Exception as e:
        print(f"Error in get_film_suggestion: {e}")
        import traceback
        traceback.print_exc()
        return {
            "text": "Scusa, ho avuto un problema tecnico. Riprova.",
            "films": []
        }