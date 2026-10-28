"""
Lead discovery module.

Uses Tavily web search to find Portland-area small businesses and extracts
contact email addresses from search result snippets and website contact pages.
"""

import re
from typing import Any, Dict, List, Optional

import requests


# Directories and aggregators that don't represent real businesses
SKIP_DOMAINS = [
    "yelp.com",
    "yellowpages.com",
    "angie.com",
    "angi.com",
    "thumbtack.com",
    "facebook.com",
    "care.com",
    "reddit.com",
    "youtube.com",
    "npr.org",
    "wikipedia.org",
    "wikimedia.org",
]

# Website builder platforms that indicate an existing website
WEBSITE_BUILDER_INDICATORS = [
    "wordpress",
    "wix.com",
    "squarespace.com",
    "shopify.com",
    "weebly.com",
    "webflow.com",
]

# Common non-business email domains to filter out
NON_BUSINESS_DOMAINS = [
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "aol.com",
    "icloud.com",
]


def extract_emails(text: str) -> List[str]:
    """Extract email addresses from text using regex."""
    if not text:
        return []
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    return list(set(re.findall(pattern, text)))


def extract_emails_from_url(url: str, timeout: int = 8) -> List[str]:
    """Fetch a webpage and extract email addresses from its HTML."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            return extract_emails(resp.text)
    except requests.RequestException:
        pass
    return []


def web_search(
    query: str,
    search_api_url: str,
    search_api_key: str,
    num_results: int = 10,
) -> List[Dict[str, str]]:
    """Search the web using Tavily API."""
    try:
        resp = requests.post(
            search_api_url,
            headers={"Content-Type": "application/json"},
            json={
                "api_key": search_api_key,
                "query": query,
                "search_depth": "basic",
                "include_answer": True,
                "max_results": num_results,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
            }
            for r in data.get("results", [])
        ]
    except requests.RequestException as e:
        print(f"  Search error: {e}")
        return []


def is_directory_site(url: str) -> bool:
    """Check if a URL is from a directory/aggregator site."""
    return any(domain in url for domain in SKIP_DOMAINS)


def has_website_builder(url: str) -> bool:
    """Check if a URL indicates an existing website builder site."""
    return any(indicator in url.lower() for indicator in WEBSITE_BUILDER_INDICATORS)


def filter_business_emails(emails: List[str]) -> List[str]:
    """Filter out common non-business email domains."""
    return [e for e in emails if not any(d in e.lower() for d in NON_BUSINESS_DOMAINS)]


def discover_leads(
    industry: str,
    location: str,
    search_api_url: str,
    search_api_key: str,
    count: int = 10,
) -> List[Dict[str, str]]:
    """
    Search for businesses in a given industry and location.

    Returns a list of candidate dicts with title, url, and content fields.
    """
    print(f"[1/6] Searching for {industry} in {location}...")
    queries = [
        f"{industry} {location} \"contact us\" email",
        f"{industry} {location} \"get a quote\"",
        f"{industry} {location} \"serving Portland\"",
    ]
    results: List[Dict[str, str]] = []
    for q in queries:
        rs = web_search(q, search_api_url, search_api_key, num_results=count)
        results.extend(rs)
        if len(results) >= count * 3:
            break

    # Deduplicate by URL or title
    seen: set = set()
    unique: List[Dict[str, str]] = []
    for r in results:
        key = r["url"] or r["title"]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique[:count]


def extract_emails_for_candidate(
    candidate: Dict[str, str],
) -> List[str]:
    """
    Extract business emails from a candidate search result.

    First checks the snippet content, then tries fetching contact pages
    from the candidate URL if no emails found.
    """
    snippet = candidate.get("content", "")
    url = candidate.get("url", "")

    found_emails = extract_emails(snippet)

    # If no emails in snippet, try fetching contact pages
    if not found_emails and url:
        domain = url.replace("http://", "").replace("https://", "").split("/")[0]
        contact_urls = [
            f"{url}contact",
            f"{url}contact-us",
            f"{url}about",
            f"https://{domain}/contact",
            f"https://{domain}/contact-us",
            f"https://{domain}/about",
        ]
        for cu in contact_urls:
            found_emails = extract_emails_from_url(cu)
            if found_emails:
                return found_emails, cu  # Return updated source URL

    return found_emails, url
