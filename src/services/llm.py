"""Compatibility import for code that used the former LangChain helper."""

from src.investigation.llm import GeminiService, get_gemini_service


def get_llm() -> GeminiService:
    return get_gemini_service()
