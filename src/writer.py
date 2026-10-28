"""
Email writer module.

Primary: OpenRouter Nemotron 3.5 Super VL for personalized cold emails.
Fallback: Template-based emails when OpenRouter is rate-limited or unavailable.
"""

from typing import Optional

import requests


# Category-specific tips for template emails
CATEGORY_TIPS = {
    "cleaning": "Showcase before-and-after photos of cleaned spaces, list your service areas, and make it easy for customers to request a quote online.",
    "landscaping": "Display project galleries, seasonal service offerings, and service area maps so homeowners can see your work and request estimates.",
    "handyman": "Feature a project gallery, list your repair services, and give homeowners a simple way to book a visit or request a quote.",
    "auto detailing": "Showcase detailing packages, before-and-after car photos, and let customers book mobile detailing appointments online.",
    "pet grooming": "List grooming services, pricing, and service areas, plus an easy booking form for pet owners.",
    "pressure washing": "Display before-and-after cleaning photos, service areas, and an easy way for property owners to request a quote.",
    "services": "Showcase your services, service areas, and give potential customers an easy way to learn more and request a quote.",
}

# Email footer for CAN-SPAM compliance
OPT_OUT_FOOTER = (
    "\n---\n"
    "This is a commercial email. To opt out of future messages, reply with STOP."
)


def chat(
    system_prompt: str,
    user_prompt: str,
    openrouter_api_key: str,
    model: str = "nvidia/nemotron-3.5-super-vl:free",
    temperature: float = 0.7,
    max_retries: int = 3,
) -> Optional[str]:
    """
    Call OpenRouter API with retry logic for rate limits.

    Returns the assistant message content, or None if all retries fail.
    """
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                wait = 2 ** attempt
                print(f"  OpenRouter rate limited, waiting {wait}s...")
                import time
                time.sleep(wait)
                continue
            print(f"  OpenRouter error: {e}")
            return None
        except Exception as e:
            print(f"  OpenRouter request failed: {e}")
            return None
    print("  OpenRouter max retries reached, using template fallback")
    return None


def write_email(
    company: str,
    personalization_fact: str,
    category: str,
    from_name: str,
    from_company: str,
    value_prop: str,
    portfolio_url: str = "https://web-dev-portfolio-swart.vercel.app/",
    github_url: str = "https://github.com/Andiewitz",
    openrouter_api_key: Optional[str] = None,
) -> str:
    """
    Write a personalized cold email.

    Tries OpenRouter Nemotron first. Falls back to template if API is
    rate-limited or unavailable.
    """
    # Try AI writer first
    if openrouter_api_key:
        prompt = f"""
        Write a personalized cold email to {company} ({category} business in Portland, OR).

        Verified detail about them: {personalization_fact}

        From: {from_name} at {from_company}
        Value proposition: {value_prop}

        Requirements:
        - 100-170 words
        - Conversational, not salesy
        - Reference the specific verified detail above
        - One or two concrete ways a website could help THIS business
        - Include: "My name is {from_name}, and I'm a web developer who builds websites for small businesses."
        - Include portfolio: {portfolio_url}
        - Include GitHub: {github_url}
        - End with one low-pressure question
        - Sign off: "Best,\n{from_name}"

        Output ONLY the email body. No subject line.
        """
        ai_body = chat(
            "You are a concise B2B copywriter.",
            prompt,
            openrouter_api_key,
            temperature=0.8,
        )
        if ai_body:
            return ai_body.strip()

    # Template-based fallback
    tip = CATEGORY_TIPS.get(category, CATEGORY_TIPS["services"])

    body = f"""Hi {company} team,

I came across {company} while researching local {category} businesses in Portland and noticed you offer {category} services to the community.

A dedicated website could be a useful way to showcase your work and help more local customers find you. It could feature photos of completed projects, explain your service options, and give potential customers an easy way to request a quote. {tip}

My name is {from_name}, and I'm a web developer who builds websites for small businesses.

Here's my portfolio:
{portfolio_url}

You can also check out my projects on GitHub:
{github_url}

Would you be open to a quick conversation about what a website for {company} could look like?

Best,
{from_name}{OPT_OUT_FOOTER}"""
    return body


def make_subject(company: str) -> str:
    """Generate a non-deceptive subject line."""
    return f"A website idea for {company}"
