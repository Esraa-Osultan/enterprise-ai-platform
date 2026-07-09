"""
The two features that turn this from "chat with a PDF" into an
engineering platform: executive summaries and requirements/action-item
extraction. Both work with or without an LLM key, same fallback
philosophy as the chat pipeline.
"""

import logging
import re

from app.core.config import get_settings

logger = logging.getLogger(__name__)

REQUIREMENT_KEYWORDS = ("shall", "must", "should", "required to", "needs to", "action item")


def summarize_document(full_text: str) -> str:
    settings = get_settings()
    if settings.openai_api_key:
        try:
            return _summarize_with_llm(full_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM summarization failed (%s), using extractive summary", exc)

    return _summarize_extractive(full_text)


def extract_requirements(full_text: str) -> list[str]:
    settings = get_settings()
    if settings.openai_api_key:
        try:
            return _extract_requirements_with_llm(full_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM requirement extraction failed (%s), using keyword match", exc)

    return _extract_requirements_keyword(full_text)


# --- LLM-backed implementations ---


def _summarize_with_llm(full_text: str) -> str:
    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.llm_model_name,
        messages=[
            {
                "role": "user",
                "content": f"Write a concise executive summary (5-8 sentences) of:\n\n{full_text[:12000]}",
            }
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def _extract_requirements_with_llm(full_text: str) -> list[str]:
    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    prompt = (
        "Extract every requirement or action item from the text below as a "
        "bullet list, one per line, no extra commentary:\n\n" + full_text[:12000]
    )
    response = client.chat.completions.create(
        model=settings.llm_model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    return [line.strip("-• ").strip() for line in raw.splitlines() if line.strip()]


# --- Offline fallback implementations ---


def _summarize_extractive(full_text: str) -> str:
    """Take the first sentence of each paragraph as a cheap-but-honest
    stand-in for a real abstractive summary."""
    paragraphs = [p.strip() for p in full_text.split("\n") if p.strip()]
    sentences = []
    for paragraph in paragraphs:
        match = re.split(r"(?<=[.!?])\s", paragraph, maxsplit=1)
        if match and match[0]:
            sentences.append(match[0])
        if len(sentences) >= 8:
            break
    return " ".join(sentences) if sentences else "Document is empty."


def _extract_requirements_keyword(full_text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", full_text)
    return [
        s.strip()
        for s in sentences
        if s.strip() and any(kw in s.lower() for kw in REQUIREMENT_KEYWORDS)
    ]
