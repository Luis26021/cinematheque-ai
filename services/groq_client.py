import os
import time
import logging
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_client = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


class GroqRateLimitError(Exception):
    """Raised when Groq rate limit persists after all retries"""
    pass


def call_groq(
    messages: list,
    model: str = "openai/gpt-oss-120b",
    max_tokens: int = 1024,
    temperature: float = 0.7,
    **kwargs
):
    """
    Centralized Groq API call with automatic retry on rate limit (429).

    Retries up to 3 times with exponential back-off.
    Raises GroqRateLimitError if rate limit persists after all retries.
    Returns the full response object unchanged.
    """
    client = _get_client()
    max_retries = 3
    retry_delays = [5, 15, 30]

    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs
            )

        except Exception as e:
            error_str = str(e).lower()
            is_rate_limit = (
                "429" in str(e)
                or "rate_limit" in error_str
                or "rate limit" in error_str
                or "too many requests" in error_str
            )

            if is_rate_limit and attempt < max_retries - 1:
                delay = retry_delays[attempt]
                logger.warning(
                    f"Groq rate limit hit (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {delay}s..."
                )
                time.sleep(delay)
                continue

            if is_rate_limit:
                raise GroqRateLimitError(
                    f"Groq rate limit persists after {max_retries} attempts"
                ) from e

            raise
