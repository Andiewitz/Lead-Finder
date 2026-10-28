"""
Email reply classifier module.

Primary: OpenRouter Nemotron for reply classification.
Fallback: Keyword-based classification when OpenRouter is unavailable.
"""

from typing import Optional

import requests

# Keyword lists for fallback classification
INTERESTED_KEYWORDS = [
    "interested",
    "yes",
    "please",
    "tell me more",
    "learn more",
    "website",
    "quote",
    "meeting",
    "call",
    "talk",
    "schedule",
    "available",
    "hear more",
    "send info",
    "information",
]

NOT_INTERESTED_KEYWORDS = [
    "not interested",
    "no thanks",
    "stop",
    "unsubscribe",
    "remove me",
    "don't email",
    "do not contact",
    "spam",
]

OOO_KEYWORDS = [
    "out of office",
    "ooo",
    "vacation",
    "away",
    "autoreply",
    "auto-reply",
    "i am out",
    "i'll be out",
    "will be out",
    "returning on",
]


def classify_reply(
    text: str,
    openrouter_api_key: Optional[str] = None,
) -> str:
    """
    Classify an email reply.

    Tries OpenRouter first, falls back to keyword matching.

    Returns one of: 'Interested', 'Not interested', 'Out of office', 'Other'
    """
    if openrouter_api_key:
        ai_result = _classify_with_ai(text, openrouter_api_key)
        if ai_result:
            return ai_result

    return _classify_with_keywords(text)


def _classify_with_ai(
    text: str,
    openrouter_api_key: str,
) -> Optional[str]:
    """Classify using OpenRouter Nemotron."""
    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openrouter_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "nvidia/nemotron-3.5-super-vl:free",
                "messages": [
                    {
                        "role": "system",
                        "content": "Classify email replies as: Interested, Not interested, Out of office, or Other.",
                    },
                    {
                        "role": "user",
                        "content": f"Reply text: {text[:1000]}",
                    },
                ],
                "temperature": 0.3,
            },
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()["choices"][0]["message"]["content"].strip()
        for kw in ["interested", "not interested", "out of office", "other"]:
            if kw in result.lower():
                if kw == "out of office":
                    return "Out of office"
                return kw.capitalize()
    except Exception:
        pass
    return None


def _classify_with_keywords(text: str) -> str:
    """Classify using keyword matching (fallback)."""
    text_lower = text.lower()

    for kw in OOO_KEYWORDS:
        if kw in text_lower:
            return "Out of office"

    for kw in NOT_INTERESTED_KEYWORDS:
        if kw in text_lower:
            return "Not interested"

    for kw in INTERESTED_KEYWORDS:
        if kw in text_lower:
            return "Interested"

    return "Other"
