from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import os
import json
from dotenv import load_dotenv
from services.streaming_agent import stream_film_suggestion
from logger_config import setup_logging, get_logger

# Load environment variables
load_dotenv()

# Setup logging (opzionale: aggiungi log_file="app.log" per salvare su file)
log_file = os.getenv("LOG_FILE")  # Set LOG_FILE=app.log in .env per file logging
setup_logging(log_file=log_file)
logger = get_logger(__name__)

# Initialize FastAPI
app = FastAPI(title="Cinémathèque API")

# CORS configuration
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
logger.info(f"Allowed CORS origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Log application startup"""
    logger.info("=" * 60)
    logger.info("🎬 Cinémathèque API Starting")
    logger.info("=" * 60)
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    logger.info(f"TMDB API: {'✓ configured' if os.getenv('TMDB_API_KEY') else '✗ missing'}")
    logger.info(f"Groq API: {'✓ configured' if os.getenv('GROQ_API_KEY') else '✗ missing'}")
    logger.info(f"Anthropic API: {'✓ configured' if os.getenv('ANTHROPIC_API_KEY') else '✗ missing'}")
    logger.info("=" * 60)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Cinémathèque API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }

@app.post("/api/chat/stream")
async def chat_stream(request: Request):
    """
    Streaming chat endpoint for film recommendations
    
    Expects JSON body:
    {
        "message": str,
        "conversation_history": list,
        "language": str (optional, default: "it")
    }
    """
    try:
        data = await request.json()
        user_message = data.get("message", "")
        history = data.get("conversation_history", [])
        user_language = data.get("language", "it")

        
        # Log request
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"[{client_ip}] Chat request: lang={user_language}, message_len={len(user_message)} history_len={len(history)}")
        
        # Validate input
        if not user_message or len(user_message.strip()) == 0:
            logger.warning(f"[{client_ip}] Empty message received")
            return {"error": "Message cannot be empty"}
        
        if len(user_message) > 1000:
            logger.warning(f"[{client_ip}] Message too long: {len(user_message)} chars")
            return {"error": "Message too long (max 1000 characters)"}
        
        if user_language not in ['it', 'en', 'es', 'fr', 'de']:
            logger.warning(f"[{client_ip}] Invalid language: {user_language}, defaulting to 'it'")
            user_language = 'it'
        
        # Wrapper to convert dict to SSE format
        async def generate_sse():
            """Convert generator dict yields to SSE format strings"""
            try:
                for chunk in stream_film_suggestion(user_message, history, user_language):
                    # Serialize dict to JSON and format as SSE
                    yield f"data: {json.dumps(chunk)}\n\n"
            except Exception as e:
                logger.error(f"Stream generation error: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'message': 'Stream error'})}\n\n"
        
        # Stream response
        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            }
        )
        
    except Exception as e:
        logger.error(f"Error in chat_stream: {e}", exc_info=True)
        return {"error": "Internal server error"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
