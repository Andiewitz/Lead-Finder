#!/usr/bin/env python3
"""
Andrei's Web Dev Client Acquisition - Automated Lead Outreach

Uses Tavily web search for lead discovery + email extraction,
OpenRouter Nemotron for AI research/writing, Gmail SMTP for sending.
Follows AI_AGENT_BRIEF.md qualification rules.

Database tables:
  leads        - Sent/attempted leads (with indexes for fast lookup)
  blacklist    - Never contact again (exclusion list)
  whitelist    - Qualified leads found but not sent (saved for future runs)
"""

import os
import re
import json
import sqlite3
import time
import imaplib
import email as email_module
import smtplib
import requests
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")
SEARCH_API_URL = os.getenv("SEARCH_API_URL", "https://api.tavily.com/search")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASS = os.getenv("IMAP_PASS")

FROM_NAME = os.getenv("FROM_NAME", "Andrei")
FROM_EMAIL = os.getenv("FROM_EMAIL")
FROM_COMPANY = os.getenv("FROM_COMPANY", "Andrei Freelance Web Development")
VALUE_PROP = os.getenv("VALUE_PROP", "I build custom websites for small businesses")

DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "20"))
DB_PATH = os.getenv("DB_PATH", "leads.db")

assert SMTP_USER and SMTP_PASS, "Set SMTP_USER and SMTP_PASS in .env"
assert SEARCH_API_KEY, "Set SEARCH_API_KEY in .env"

# ── OpenRouter / Nemotron (primary AI writer) ─────────────────────────────
def chat(system_prompt, user_prompt, model="nvidia/nemotron-3.5-super-vl:free", temperature=0.7, max_retries=3):
    for attempt in range(max_retries):
        try:
            resp = requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}], "temperature": temperature},
                timeout=60)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                wait = 2 ** attempt
                print(f"  OpenRouter rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"  OpenRouter error: {e}")
            return None
        except Exception as e:
            print(f"  OpenRouter request failed: {e}")
            return None
    print("  OpenRouter max retries reached, using template fallback")
    return None

# ── Database ───────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Leads table - sent or attempted leads
    c.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_number INTEGER,
            business_name TEXT,
            business_category TEXT,
            city_state TEXT,
            owner_contact_name TEXT,
            public_business_email TEXT,
            email_source_url TEXT,
            business_phone TEXT,
            website_status TEXT,
            website_evidence TEXT,
            google_rating REAL,
            google_review_count INTEGER,
            google_business_profile_url TEXT,
            recent_activity_date TEXT,
            recent_activity_source_url TEXT,
            personalization_fact TEXT,
            personalization_source_url TEXT,
            qualification_status TEXT,
            confidence_level TEXT,
            email_subject TEXT,
            email_body TEXT,
            sending_status TEXT DEFAULT 'draft',
            sent_timestamp TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Blacklist - never contact these again
    c.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            business_name TEXT,
            reason TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Whitelist - qualified leads found but not sent (saved for future)
    c.execute("""
        CREATE TABLE IF NOT EXISTS whitelist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_number INTEGER,
            business_name TEXT,
            business_category TEXT,
            city_state TEXT,
            owner_contact_name TEXT,
            public_business_email TEXT,
            email_source_url TEXT,
            business_phone TEXT,
            website_status TEXT,
            website_evidence TEXT,
            google_rating REAL,
            google_review_count INTEGER,
            google_business_profile_url TEXT,
            recent_activity_date TEXT,
            recent_activity_source_url TEXT,
            personalization_fact TEXT,
            personalization_source_url TEXT,
            qualification_status TEXT,
            confidence_level TEXT,
            email_subject TEXT,
            email_body TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            priority INTEGER DEFAULT 0
        )
    """)

    # Migration: add lead_number to existing whitelist tables
    try:
        c.execute("ALTER TABLE whitelist ADD COLUMN lead_number INTEGER")
    except Exception:
        pass

    # Indexes for fast lookups
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(public_business_email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_name ON leads(business_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(sending_status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_date ON leads(sent_timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_email ON blacklist(email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_whitelist_email ON whitelist(public_business_email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_whitelist_priority ON whitelist(priority DESC)")

    conn.commit()
    conn.close()

def add_lead_record(data, table="leads"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    cols = [
        "lead_number", "business_name", "business_category", "city_state",
        "owner_contact_name", "public_business_email", "email_source_url",
        "business_phone", "website_status", "website_evidence",
        "google_rating", "google_review_count", "google_business_profile_url",
        "recent_activity_date", "recent_activity_source_url",
        "personalization_fact", "personalization_source_url",
        "qualification_status", "confidence_level",
        "email_subject", "email_body",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    col_str = ", ".join(cols)
    values = [data.get(col) for col in cols]
    c.execute(f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})", values)
    conn.commit()
    lid = c.lastrowid
    conn.close()
    return lid

def mark_sent(lead_id, table="leads"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"UPDATE {table} SET sending_status='sent', sent_timestamp=? WHERE id=?",
              (datetime.now(timezone.utc).isoformat(), lead_id))
    conn.commit()
    conn.close()

def get_draft_leads(limit, table="leads"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table} WHERE sending_status='draft' LIMIT ?", (limit,))
    cols = [d[0] for d in c.description]
    rows = c.fetchall()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def email_exists(email_addr, table="leads"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"SELECT id FROM {table} WHERE public_business_email=?", (email_addr,))
    row = c.fetchone()
    # Also check blacklist and whitelist
    c.execute("SELECT id FROM blacklist WHERE email=?", (email_addr,))
    if c.fetchone():
        conn.close()
        return True
    c.execute("SELECT id FROM whitelist WHERE public_business_email=?", (email_addr,))
    if c.fetchone():
        conn.close()
        return True
    conn.close()
    return row is not None

def is_blacklisted(email_addr):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM blacklist WHERE email=?", (email_addr,))
    row = c.fetchone()
    conn.close()
    return row is not None

def add_to_blacklist(email_addr, business_name="", reason=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT OR IGNORE INTO blacklist (email, business_name, reason) VALUES (?, ?, ?)",
                  (email_addr, business_name, reason))
        conn.commit()
    except Exception:
        pass
    conn.close()

def add_to_whitelist(data):
    """Save a qualified lead that wasn't sent (due to quota) for future runs."""
    lid = add_lead_record(data, table="whitelist")
    # Set priority if provided
    if data.get("priority") is not None:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE whitelist SET priority=? WHERE id=?", (data["priority"], lid))
        conn.commit()
        conn.close()
    return lid

def get_whitelist_leads(limit):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM whitelist ORDER BY priority DESC, added_at ASC LIMIT ?", (limit,))
    cols = [d[0] for d in c.description]
    rows = c.fetchall()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def move_whitelist_to_leads(lead_id):
    """Move a whitelisted lead to the leads table for sending."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM whitelist WHERE id=?", (lead_id,))
    cols = [d[0] for d in c.description]
    row = c.fetchone()
    if not row:
        conn.close()
        return None
    data = dict(zip(cols, row))
    # Remove whitelist-specific fields
    data.pop("id", None)
    data.pop("added_at", None)
    data.pop("priority", None)
    data["sending_status"] = "draft"
    new_id = add_lead_record(data, table="leads")
    c.execute("DELETE FROM whitelist WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()
    return new_id

def search_leads(query, table="leads"):
    """Search leads by business name, email, or category."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    like = f"%{query}%"
    c.execute(f"""
        SELECT * FROM {table}
        WHERE business_name LIKE ? OR public_business_email LIKE ? OR business_category LIKE ?
        ORDER BY id DESC
        LIMIT 50
    """, (like, like, like))
    cols = [d[0] for d in c.description]
    rows = c.fetchall()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    stats = {}
    c.execute("SELECT COUNT(*) FROM leads WHERE sending_status='sent'")
    stats["sent"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM leads WHERE sending_status='draft'")
    stats["draft"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM whitelist")
    stats["whitelist"] = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM blacklist")
    stats["blacklist"] = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT public_business_email) FROM leads WHERE sending_status='sent' AND date(sent_timestamp)=?",
              (datetime.now(timezone.utc).date().isoformat(),))
    stats["sent_today"] = c.fetchone()[0]
    conn.close()
    return stats

# ── Email sending ──────────────────────────────────────────────────────────
def send_email(to_email, subject, html_body):
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"  SMTP error: {e}")
        return False

def send_confirmation_email(sent_count, total_processed):
    """Send confirmation email to Andrei after each run."""
    subject = f"Lead Outreach Complete - {sent_count} emails sent"
    body = f"""
    Lead Outreach Run Complete
    ==========================
    Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
    Emails sent this run: {sent_count}
    Daily total processed: {total_processed}
    Daily limit: {DAILY_LIMIT}
    
    Check leads.db for full details.
    
    - Andrei's Outreach Bot
    """
    html_body = f"<p>{body.replace(chr(10), '<br>')}</p>"
    send_email(SMTP_USER, subject, html_body)

# ── Reply tracking (local keyword classifier, no OpenRouter needed) ────────
INTERESTED_KEYWORDS = ["interested", "yes", "please", "tell me more", "learn more",
                       "website", "quote", "meeting", "call", "talk", "schedule",
                       "available", "hear more", "send info", "information"]
NOT_INTERESTED_KEYWORDS = ["not interested", "no thanks", "stop", "unsubscribe",
                           "remove me", "don't email", "do not contact", "spam"]
OOO_KEYWORDS = ["out of office", "ooo", "vacation", "away", "autoreply", "auto-reply",
                "i am out", "i'll be out", "will be out", "returning on"]

def classify_reply(text):
    """Classify email reply using OpenRouter (primary) with keyword fallback."""
    if OPENROUTER_API_KEY:
        ai_result = chat("You classify email replies.",
            f"Classify this reply: Interested, Not interested, Out of office, or Other.\nReply text: {text[:1000]}",
            temperature=0.3)
        if ai_result:
            ai_result = ai_result.strip()
            for kw in ["interested", "not interested", "out of office", "other"]:
                if kw in ai_result.lower():
                    return kw.capitalize() if kw != "out of office" else "Out of office"

    # Keyword-based fallback (when OpenRouter is rate-limited or unavailable)
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

def check_replies():
    if not IMAP_USER or not IMAP_PASS:
        return
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST, timeout=10)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("inbox")
        date_since = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE {date_since})')
        for msg_id in messages[0].split():
            status, data = mail.fetch(msg_id, "(RFC822)")
            msg = email_module.message_from_bytes(data[0][1])
            from_addr = msg.get("From", "")
            subject = msg.get("Subject", "")
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode(errors="ignore")
            full_text = f"{from_addr} {subject} {body}"
            classification = classify_reply(full_text)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT id, business_name FROM leads WHERE sending_status='sent'")
            for lead_id, business_name in c.fetchall():
                if business_name.lower() in (from_addr + subject).lower():
                    c.execute("UPDATE leads SET qualification_status=? WHERE id=?",
                              (classification.lower(), lead_id))
            conn.commit()
            conn.close()
        mail.logout()
    except Exception:
        pass

# ── Email writing ──────────────────────────────────────────────────────────
def write_email(company, personalization_fact, category):
    # Try OpenRouter Nemotron first (primary AI writer)
    if OPENROUTER_API_KEY:
        prompt = f"""
        Write a personalized cold email to {company} ({category} business in Portland, OR).

        Verified detail about them: {personalization_fact}

        From: {FROM_NAME} at {FROM_COMPANY}
        Value proposition: {VALUE_PROP}

        Requirements:
        - 100-170 words
        - Conversational, not salesy
        - Reference the specific verified detail above
        - One or two concrete ways a website could help THIS business
        - Include: "My name is Andrei, and I'm a web developer who builds websites for small businesses."
        - Include portfolio: https://web-dev-portfolio-swart.vercel.app/
        - Include GitHub: https://github.com/Andiewitz
        - End with one low-pressure question
        - Sign off: "Best,\nAndrei"

        Output ONLY the email body. No subject line.
        """
        ai_body = chat("You are a concise B2B copywriter.", prompt, temperature=0.8)
        if ai_body:
            return ai_body.strip()

    # Template-based fallback (when OpenRouter is rate-limited or unavailable)
    category_tips = {
        "cleaning": "Showcase before-and-after photos of cleaned spaces, list your service areas, and make it easy for customers to request a quote online.",
        "landscaping": "Display project galleries, seasonal service offerings, and service area maps so homeowners can see your work and request estimates.",
        "handyman": "Feature a project gallery, list your repair services, and give homeowners a simple way to book a visit or request a quote.",
        "auto detailing": "Showcase detailing packages, before-and-after car photos, and let customers book mobile detailing appointments online.",
        "pet grooming": "List grooming services, pricing, and service areas, plus an easy booking form for pet owners.",
        "pressure washing": "Display before-and-after cleaning photos, service areas, and an easy way for property owners to request a quote.",
        "services": "Showcase your services, service areas, and give potential customers an easy way to learn more and request a quote.",
    }
    tip = category_tips.get(category, category_tips["services"])

    body = f"""Hi {company} team,

I came across {company} while researching local {category} businesses in Portland and noticed you offer {category} services to the community.

A dedicated website could be a useful way to showcase your work and help more local customers find you. It could feature photos of completed projects, explain your service options, and give potential customers an easy way to request a quote. {tip}

My name is Andrei, and I'm a web developer who builds websites for small businesses.

Here's my portfolio:
https://web-dev-portfolio-swart.vercel.app/

You can also check out my projects on GitHub:
https://github.com/Andiewitz

Would you be open to a quick conversation about what a website for {company} could look like?

Best,
Andrei"""
    return body

# ── Email extraction ───────────────────────────────────────────────────────
def extract_emails(text):
    """Extract email addresses from text using regex."""
    if not text:
        return []
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return list(set(re.findall(pattern, text)))

def extract_emails_from_url(url):
    """Fetch a webpage and extract email addresses."""
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            return extract_emails(resp.text)
    except Exception:
        pass
    return []

# ── Lead discovery ─────────────────────────────────────────────────────────
def discover_leads(industry, location, count=10):
    print(f"[1/6] Searching for {industry} in {location}...")
    queries = [
        f"{industry} {location} \"contact us\" email",
        f"{industry} {location} \"get a quote\"",
        f"{industry} {location} \"serving Portland\"",
    ]
    results = []
    for q in queries:
        rs = web_search(q, num_results=count)
        results.extend(rs)
        if len(results) >= count * 3:
            break
    seen = set()
    unique = []
    for r in results:
        key = r["url"] or r["title"]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique[:count]

def web_search(query, num_results=10):
    try:
        resp = requests.post(SEARCH_API_URL, headers={"Content-Type": "application/json"},
                             json={"api_key": SEARCH_API_KEY, "query": query,
                                   "search_depth": "basic", "include_answer": True,
                                   "max_results": num_results}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return [{"title": r.get("title", ""), "url": r.get("url", ""),
                 "content": r.get("content", "")} for r in data.get("results", [])]
    except Exception as e:
        print(f"  Search error: {e}")
        return []

# ── Main pipeline ──────────────────────────────────────────────────────────
def run_once():
    init_db()

    industries = ["pressure washing", "mobile auto detailing", "pet grooming",
                  "handyman", "home repair", "landscaping", "lawn care", "cleaning services"]
    locations = ["Portland, OR", "Beaverton, OR", "Gresham, OR", "Tigard, OR",
                 "Tualatin, OR", "Oregon City, OR", "Lake Oswego, OR", "Happy Valley, OR"]

    # Daily limit check - count unique emails sent today
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT public_business_email) FROM leads WHERE sending_status='sent' AND date(sent_timestamp)=?",
              (datetime.now(timezone.utc).date().isoformat(),))
    sent_today = c.fetchone()[0]
    conn.close()
    remaining = DAILY_LIMIT - sent_today
    if remaining <= 0:
        print(f"Daily limit ({DAILY_LIMIT}) reached. Try again tomorrow.")
        send_confirmation_email(0, 0)
        return

    # Step 1: Pull from whitelist first (previously found but not sent)
    whitelist_leads = get_whitelist_leads(remaining)
    processed = 0
    for wl in whitelist_leads:
        if processed >= remaining:
            break
        email_addr = wl["public_business_email"]
        if email_exists(email_addr) or is_blacklisted(email_addr):
            continue
        # Move from whitelist to leads and send
        new_id = move_whitelist_to_leads(wl["id"])
        if not new_id:
            continue
        html_body = f"<p>{wl['email_body'].replace(chr(10), '<br>')}</p>"
        html_body += f"<p><small>This is a commercial email. To opt out of future messages, reply with STOP.</small></p>"
        success = send_email(email_addr, wl["email_subject"], html_body)
        if success:
            mark_sent(new_id)
            print(f"  Sent (from whitelist): {wl['business_name']}")
        else:
            print(f"  Failed (from whitelist): {wl['business_name']}")
        processed += 1
        time.sleep(3)

    # Step 2: Discover new leads if we still have quota
    if processed < remaining:
        remaining2 = remaining - processed
        all_candidates = []
        max_candidates = remaining2 * 4
        for ind in industries:
            for loc in locations:
                if len(all_candidates) >= max_candidates:
                    break
                rs = discover_leads(ind, loc, count=min(remaining2, 5))
                all_candidates.extend(rs)
                time.sleep(0.5)
            if len(all_candidates) >= max_candidates:
                break

        print(f"\n[2/6] Found {len(all_candidates)} candidates. Processing up to {remaining2}...")

        exclusion_emails = [
            "bussdownscrubdown@gmail.com", "freedomlawncareba@gmail.com",
            "pearldistrictdrycleaners@gmail.com", "honuhomeservices@gmail.com",
            "debonairlawncarepdx@gmail.com", "Sscheans2@gmail.com",
            "waldochristian320@gmail.com", "ismohusic@gmail.com",
            "abiestreecare1@gmail.com", "hoot.n.holler1985@gmail.com",
            "precisemobilepdx@gmail.com", "rachaelsgroomingavenue@gmail.com",
            "chebangv71@gmail.com", "petrarcaseth@gmail.com",
            "allenstreefarm@aol.com", "stellargrade22@gmail.com",
            "marcojoaquin01@gmail.com", "terciadereyes321@gmail.com",
            "thedetailofportland@gmail.com", "pressureon71@gmail.com",
            "thepdxhomepros@gmail.com", "kglandscapemaintenancellc@gmail.com",
            "claffey.massage@gmail.com", "jonesdogs@gmail.com",
        ]

        excluded_names = [
            "buss down scrub down", "freedom lawn care", "pearl district cleaners",
            "barber on barbur", "honu home services", "divine renovation",
            "debonair lawn care", "oregon custom handyman", "cm lawn care",
            "ismo handyman", "abies tree care", "hoot & holler",
            "precise mobile detail", "rachael's grooming avenue",
            "reliable handyman & assembly", "anthony's handywork",
            "allen's tree farm", "stellar grade landscaping",
            "marco joaquin landscaping", "rafael landscaping",
            "the detail of portland", "pressure on power washing",
            "the pdx home pros", "k&g landscape maintenance",
            "portland massage and chiropractic", "oh paws",
            "sparkling palaces", "a & i house cleaning",
            "good green neighbors", "aspen chiropractic",
        ]

        skip_domains = ["yelp.com", "yellowpages.com", "angie.com", "angi.com",
                        "thumbtack.com", "facebook.com", "care.com",
                        "reddit.com", "youtube.com", "npr.org", "wikipedia.org"]

        suspicious_domains = ["oame.org", "thecangroup.co.uk", "mysite.com"]

        for cand in all_candidates:
            if processed >= remaining2:
                break

            business_name = cand.get("title", "Unknown Business")
            snippet = cand.get("content", "")
            url = cand.get("url", "")

            # Skip directories, aggregators, review sites
            if any(d in url for d in skip_domains):
                continue

            # Skip if already excluded by name
            if any(ex in business_name.lower() for ex in excluded_names):
                continue

            # Skip website builder sites
            has_website_indicators = ["wordpress", "wix.com", "squarespace.com",
                                      "shopify.com", "weebly.com", "webflow.com"]
            if any(w in url.lower() for w in has_website_indicators):
                continue

            # Extract emails from snippet
            found_emails = extract_emails(snippet)

            # If no emails in snippet, try fetching the website contact page
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
                        url = cu
                        break

            # Filter out common non-business emails
            found_emails = [e for e in found_emails if not any(
                d in e.lower() for d in ["gmail.com", "yahoo.com", "hotmail.com",
                                         "outlook.com", "aol.com"])]

            if not found_emails:
                continue

            email_addr = found_emails[0]

            # Skip if already in database or blacklisted
            if email_exists(email_addr):
                continue
            if email_addr.lower() in exclusion_emails:
                continue
            if is_blacklisted(email_addr):
                continue

            # Clean business name
            clean_name = business_name
            for suffix in [" | ", " - ", " — "]:
                if suffix in clean_name:
                    clean_name = clean_name.split(suffix)[0].strip()
            for suffix in ["(About)", "Contact Us", "Home", "Services"]:
                clean_name = clean_name.replace(suffix, "").strip()
            business_name = clean_name

            # Filter suspicious emails
            if any(d in email_addr.lower() for d in suspicious_domains):
                continue

            if any(ex in business_name.lower() for ex in excluded_names):
                continue

            # Determine category
            category = "services"
            name_lower = business_name.lower()
            if any(w in name_lower for w in ["clean", "maid", "janitor"]):
                category = "cleaning"
            elif any(w in name_lower for w in ["landscape", "lawn", "yard"]):
                category = "landscaping"
            elif any(w in name_lower for w in ["handyman", "repair", "handy"]):
                category = "handyman"
            elif any(w in name_lower for w in ["detail", "auto", "car"]):
                category = "auto detailing"
            elif any(w in name_lower for w in ["groom", "pet"]):
                category = "pet grooming"
            elif any(w in name_lower for w in ["pressure", "wash"]):
                category = "pressure washing"

            personalization_fact = snippet[:250] if snippet else f"{business_name} is a local {category} business serving Portland, Oregon"
            if len(personalization_fact) < 10:
                personalization_fact = f"{business_name} serves the Portland, Oregon area."

            email_body = write_email(business_name, personalization_fact, category)
            subject = f"A website idea for {business_name}"

            record = {
                "lead_number": processed + 1,
                "business_name": business_name,
                "business_category": category,
                "city_state": locations[0] if locations else "Portland, OR",
                "owner_contact_name": "UNKNOWN",
                "public_business_email": email_addr,
                "email_source_url": url,
                "business_phone": "UNKNOWN",
                "website_status": "NO WEBSITE",
                "website_evidence": "No dedicated website found in search results",
                "google_rating": None,
                "google_review_count": None,
                "google_business_profile_url": "UNKNOWN",
                "recent_activity_date": "UNKNOWN",
                "recent_activity_source_url": "UNKNOWN",
                "personalization_fact": personalization_fact,
                "personalization_source_url": url,
                "qualification_status": "qualified",
                "confidence_level": "medium",
                "email_subject": subject,
                "email_body": email_body,
            }

            # If we have more qualified leads than quota, save extras to whitelist
            if processed >= remaining2:
                add_to_whitelist(record)
                print(f"  Whitelisted (quota full): {business_name} ({email_addr})")
                continue

            lead_id = add_lead_record(record)
            print(f"  Qualified: {business_name} ({email_addr})")

            html_body = f"<p>{email_body.replace(chr(10), '<br>')}</p>"
            html_body += f"<p><small>This is a commercial email. To opt out of future messages, reply with STOP.</small></p>"
            success = send_email(email_addr, subject, html_body)
            if success:
                mark_sent(lead_id)
                print(f"  Sent to {business_name}")
            else:
                print(f"  Failed to send to {business_name}")

            processed += 1
            time.sleep(3)

    print(f"\n[3/6] Processed {processed} leads today.")
    send_confirmation_email(processed, processed)
    print("Done.")

if __name__ == "__main__":
    run_once()
