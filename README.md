# Cinémathèque

An AI-powered film curator with a beautiful editorial interface. Get personalized movie recommendations, film comparisons, and streaming availability across multiple platforms.

## Features

- **AI-Powered Recommendations** — conversational film curation via Groq-hosted LLM inference
- **Multilingual** — full support for Italian, English, Spanish, French, and German
- **Editorial Design** — elegant, newspaper-inspired interface
- **Streaming Availability** — real-time data from TMDB for Netflix, Prime Video, Disney+, and more
- **Smart Search** — by genre, year, platform, rating, mood
- **Film Comparisons** — deep comparative analysis between titles
- **Conversational UI** — natural language interaction with full conversation context

## Tech Stack

**Backend:**
- FastAPI (Python)
- Groq API — LLM inference (`openai/gpt-oss-120b`), chosen for speed and zero-cost MVP development
- TMDB API — film data, metadata, streaming availability

**Frontend:**
- React
- CSS Grid/Flexbox
- Custom editorial design system

> **Note:** the project currently runs entirely on Groq's free tier for LLM inference. This keeps MVP costs at zero but means it inherits Groq's rate limits — a known constraint, not an oversight. Migration to a paid provider (e.g. Anthropic's Claude API) is a possible future step if usage outgrows the free tier.

## License

MIT