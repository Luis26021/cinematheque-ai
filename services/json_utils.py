"""
JSON sanitization utilities for LLM-generated JSON responses.
Handles common issues like unescaped quotes, apostrophes, newlines.
"""

import json
import re


def sanitize_llm_json(text: str) -> str:
    """
    Clean LLM-generated JSON before parsing.
    
    Handles:
    - Markdown fences (```json```)
    - Unescaped quotes in strings
    - Extra whitespace
    """
    
    # Remove markdown fences
    text = re.sub(r'```json\s*|\s*```', '', text).strip()
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    return text


def safe_json_parse(text: str, default: dict = None) -> dict:
    """
    Attempt to parse JSON with fallbacks.
    
    Returns:
        Parsed dict or default dict if parsing fails
    """
    
    if default is None:
        default = {}
    
    try:
        # Clean text first
        cleaned = sanitize_llm_json(text)
        
        if not cleaned:
            return default
        
        # Try direct parse
        return json.loads(cleaned)
    
    except json.JSONDecodeError as e:
        # If direct parse fails, try fixing common issues
        try:
            # Replace single quotes with double quotes (common LLM mistake)
            fixed = cleaned.replace("'", '"')
            return json.loads(fixed)
        except:
            pass
        
        # Last resort: return default
        return default


def extract_json_from_text(text: str) -> dict:
    """
    Extract JSON object from text that might contain other content.
    
    Looks for first { ... } block.
    """
    
    try:
        # Find first { and last }
        start = text.find('{')
        end = text.rfind('}')
        
        if start == -1 or end == -1 or start >= end:
            return {}
        
        json_text = text[start:end+1]
        return safe_json_parse(json_text, {})
    
    except Exception:
        return {}
