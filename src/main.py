"""
Main orchestrator for Andrei's Web Dev Client Acquisition.

Runs the full pipeline:
1. Load config from environment
2. Initialize database
3. Check daily limit
4. Send from whitelist first (previously found, unsent)
5. Discover new leads via Tavily search
6. Filter, deduplicate, extract emails
7. Write personalized emails (OpenRouter primary, template fallback)
8. Send via Gmail SMTP
9. Send confirmation email
10. Track replies via IMAP
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta

# Ensure src package is importable when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src import db
from src import discovery
from src import writer
from src import sender
from src import classifier

load_dotenv()

from src import db
from src import discovery
from src import writer
from src import sender
from src import classifier

load_dotenv()


# ── Configuration ──────────────────────────────────────────────────────
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


# ── Validation ─────────────────────────────────────────────────────────
def validate_config() -> bool:
    """Check that required config is present."""
    errors = []
    if not SMTP_USER or not SMTP_PASS:
        errors.append("SMTP_USER and SMTP_PASS required")
    if not SEARCH_API_KEY:
        errors.append("SEARCH_API_KEY required")
    if not FROM_EMAIL:
        errors.append("FROM_EMAIL required")

    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        print("See .env.example for required fields.")
        return False
    return True


# ── Exclusion lists ────────────────────────────────────────────────────
EXCLUSION_EMAILS = [
    "bussdownscrubdown@gmail.com",
    "freedomlawncareba@gmail.com",
    "pearldistrictdrycleaners@gmail.com",
    "honuhomeservices@gmail.com",
    "debonairlawncarepdx@gmail.com",
    "Sscheans2@gmail.com",
    "waldochristian320@gmail.com",
    "ismohusic@gmail.com",
    "abiestreecare1@gmail.com",
    "hoot.n.holler1985@gmail.com",
    "precisemobilepdx@gmail.com",
    "rachaelsgroomingavenue@gmail.com",
    "chebangv71@gmail.com",
    "petrarcaseth@gmail.com",
    "allenstreefarm@aol.com",
    "stellargrade22@gmail.com",
    "marcojoaquin01@gmail.com",
    "terciadereyes321@gmail.com",
    "thedetailofportland@gmail.com",
    "pressureon71@gmail.com",
    "thepdxhomepros@gmail.com",
    "kglandscapemaintenancellc@gmail.com",
    "claffey.massage@gmail.com",
    "jonesdogs@gmail.com",
]

EXCLUSION_NAMES = [
    "buss down scrub down",
    "freedom lawn care",
    "pearl district cleaners",
    "barber on barbur",
    "honu home services",
    "divine renovation",
    "debonair lawn care",
    "oregon custom handyman",
    "cm lawn care",
    "ismo handyman",
    "abies tree care",
    "hoot & holler",
    "precise mobile detail",
    "rachael's grooming avenue",
    "reliable handyman & assembly",
    "anthony's handywork",
    "allen's tree farm",
    "stellar grade landscaping",
    "marco joaquin landscaping",
    "rafael landscaping",
    "the detail of portland",
    "pressure on power washing",
    "the pdx home pros",
    "k&g landscape maintenance",
    "portland massage and chiropractic",
    "oh paws",
    "sparkling palaces",
    "a & i house cleaning",
    "good green neighbors",
    "aspen chiropractic",
]

SKIP_DOMAINS = [
    "yelp.com", "yellowpages.com", "angie.com", "angi.com",
    "thumbtack.com", "facebook.com", "care.com",
    "reddit.com", "youtube.com", "npr.org", "wikipedia.org",
    "wikimedia.org",
]

WEBSITE_BUILDER_INDICATORS = [
    "wordpress", "wix.com", "squarespace.com",
    "shopify.com", "weebly.com", "webflow.com",
]

SUSPICIOUS_EMAIL_DOMAINS = [
    "oame.org", "thecangroup.co.uk", "mysite.com",
]

INDUSTRIES = [
    "pressure washing",
    "mobile auto detailing",
    "pet grooming",
    "handyman",
    "home repair",
    "landscaping",
    "lawn care",
    "cleaning services",
]

LOCATIONS = [
    "Portland, OR",
    "Beaverton, OR",
    "Gresham, OR",
    "Tigard, OR",
    "Tualatin, OR",
    "Oregon City, OR",
    "Lake Oswego, OR",
    "Happy Valley, OR",
]


# ── Helpers ────────────────────────────────────────────────────────────
def categorize(business_name: str) -> str:
    """Guess business category from name."""
    name_lower = business_name.lower()
    if any(w in name_lower for w in ["clean", "maid", "janitor"]):
        return "cleaning"
    if any(w in name_lower for w in ["landscap", "lawn", "yard"]):
        return "landscaping"
    if any(w in name_lower for w in ["handyman", "repair", "handy"]):
        return "handyman"
    if any(w in name_lower for w in ["detail", "auto", "car"]):
        return "auto detailing"
    if any(w in name_lower for w in ["groom", "pet"]):
        return "pet grooming"
    if any(w in name_lower for w in ["pressure", "wash"]):
        return "pressure washing"
    return "services"


def clean_business_name(name: str) -> str:
    """Remove title artifacts from business name."""
    clean = name
    for suffix in [" | ", " - ", " — "]:
        if suffix in clean:
            clean = clean.split(suffix)[0].strip()
    for suffix in ["(About)", "Contact Us", "Home", "Services"]:
        clean = clean.replace(suffix, "").strip()
    return clean


def is_excluded_name(name: str) -> bool:
    """Check if business name is in the exclusion list."""
    name_lower = name.lower()
    return any(ex in name_lower for ex in EXCLUSION_NAMES)


def is_suspicious_email(email: str) -> bool:
    """Check if email domain is suspicious."""
    return any(d in email.lower() for d in SUSPICIOUS_EMAIL_DOMAINS)


# ── Main pipeline ──────────────────────────────────────────────────────
def run_once() -> None:
    """Execute one full outreach run."""
    if not validate_config():
        sys.exit(1)

    db.init_db(DB_PATH)

    # Daily limit check
    stats = db.get_stats(DB_PATH)
    remaining = DAILY_LIMIT - stats["sent_today"]
    if remaining <= 0:
        print(f"Daily limit ({DAILY_LIMIT}) reached. Try again tomorrow.")
        sender.send_confirmation_email(
            0, 0, DAILY_LIMIT,
            SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
            FROM_NAME, FROM_EMAIL,
        )
        return

    processed = 0

    # ── Step 1: Send from whitelist first ────────────────────────────
    whitelist_leads = db.get_whitelist_leads(remaining, DB_PATH)
    for wl in whitelist_leads:
        if processed >= remaining:
            break
        email_addr = wl["public_business_email"]
        if db.email_exists(email_addr, "leads", DB_PATH):
            continue
        if db.is_blacklisted(email_addr, DB_PATH):
            continue

        new_id = db.move_whitelist_to_leads(wl["id"], DB_PATH)
        if not new_id:
            continue

        html_body = f"<p>{wl['email_body'].replace(chr(10), '<br>')}</p>"
        html_body += (
            "<p><small>This is a commercial email. "
            "To opt out of future messages, reply with STOP.</small></p>"
        )
        success = sender.send_email(
            email_addr, wl["email_subject"], html_body,
            SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
            FROM_NAME, FROM_EMAIL,
        )
        if success:
            db.mark_sent(new_id, "leads", DB_PATH)
            print(f"  Sent (from whitelist): {wl['business_name']}")
        else:
            print(f"  Failed (from whitelist): {wl['business_name']}")
        processed += 1
        time.sleep(3)

    # ── Step 2: Discover new leads ───────────────────────────────────
    if processed < remaining:
        remaining2 = remaining - processed
        all_candidates: list = []
        max_candidates = remaining2 * 4

        for ind in INDUSTRIES:
            for loc in LOCATIONS:
                if len(all_candidates) >= max_candidates:
                    break
                rs = discovery.discover_leads(
                    ind, loc, SEARCH_API_URL, SEARCH_API_KEY,
                    count=min(remaining2, 5),
                )
                all_candidates.extend(rs)
                time.sleep(0.5)
            if len(all_candidates) >= max_candidates:
                break

        print(
            f"\n[2/6] Found {len(all_candidates)} candidates. "
            f"Processing up to {remaining2}..."
        )

        for cand in all_candidates:
            if processed >= remaining2:
                break

            business_name = cand.get("title", "Unknown Business")
            snippet = cand.get("content", "")
            url = cand.get("url", "")

            # Skip directories/aggregators
            if any(d in url for d in SKIP_DOMAINS):
                continue

            # Skip excluded names
            if is_excluded_name(business_name):
                continue

            # Skip website builder sites
            if any(w in url.lower() for w in WEBSITE_BUILDER_INDICATORS):
                continue

            # Extract emails
            found_emails, source_url = discovery.extract_emails_for_candidate(cand)
            found_emails = discovery.filter_business_emails(found_emails)

            if not found_emails:
                print(f"  Skipping {business_name}: no business email found")
                continue

            email_addr = found_emails[0]

            # Skip if already in DB or blacklisted
            if db.email_exists(email_addr, "leads", DB_PATH):
                print(f"  Skipping {business_name}: email already in database")
                continue
            if email_addr.lower() in [e.lower() for e in EXCLUSION_EMAILS]:
                print(f"  Skipping {business_name}: in exclusion list")
                continue
            if db.is_blacklisted(email_addr, DB_PATH):
                continue

            # Clean business name
            business_name = clean_business_name(business_name)

            # Filter suspicious emails
            if is_suspicious_email(email_addr):
                print(f"  Skipping {business_name}: suspicious email {email_addr}")
                continue

            if is_excluded_name(business_name):
                continue

            # Categorize
            category = categorize(business_name)

            personalization_fact = snippet[:250] if snippet else (
                f"{business_name} is a local {category} business serving Portland, Oregon"
            )
            if len(personalization_fact) < 10:
                personalization_fact = (
                    f"{business_name} serves the Portland, Oregon area."
                )

            email_body = writer.write_email(
                business_name,
                personalization_fact,
                category,
                FROM_NAME,
                FROM_COMPANY,
                VALUE_PROP,
                openrouter_api_key=OPENROUTER_API_KEY,
            )
            subject = writer.make_subject(business_name)

            record = {
                "lead_number": processed + 1,
                "business_name": business_name,
                "business_category": category,
                "city_state": LOCATIONS[0] if LOCATIONS else "Portland, OR",
                "owner_contact_name": "UNKNOWN",
                "public_business_email": email_addr,
                "email_source_url": source_url,
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

            # If quota full, save to whitelist
            if processed >= remaining2:
                db.add_to_whitelist(record, DB_PATH)
                print(f"  Whitelisted (quota full): {business_name} ({email_addr})")
                continue

            lead_id = db.add_lead_record(record, "leads", DB_PATH)
            print(f"  Qualified: {business_name} ({email_addr})")

            html_body = f"<p>{email_body.replace(chr(10), '<br>')}</p>"
            html_body += (
                "<p><small>This is a commercial email. "
                "To opt out of future messages, reply with STOP.</small></p>"
            )
            success = sender.send_email(
                email_addr, subject, html_body,
                SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
                FROM_NAME, FROM_EMAIL,
            )
            if success:
                db.mark_sent(lead_id, "leads", DB_PATH)
                print(f"  Sent to {business_name}")
            else:
                print(f"  Failed to send to {business_name}")

            processed += 1
            time.sleep(3)

    # ── Step 3: Confirmation ─────────────────────────────────────────
    print(f"\n[3/6] Processed {processed} leads today.")
    sender.send_confirmation_email(
        processed, processed, DAILY_LIMIT,
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
        FROM_NAME, FROM_EMAIL,
    )
    print("Done.")


def main() -> None:
    """CLI entry point with subcommand support."""
    db.init_db(DB_PATH)

    parser = argparse.ArgumentParser(
        description='Andrei\'s Web Dev Client Acquisition - Lead Outreach Automation'
    )
    subparsers = parser.add_subparsers(dest='command')

    # run - full pipeline (default)
    subparsers.add_parser('run', help='Run full outreach pipeline (default)')

    # find-leads - discover new leads
    find_parser = subparsers.add_parser('find-leads', help='Discover new leads via Tavily search')
    find_parser.add_argument('--industry', type=str, default='cleaning services', help='Industry to search for')
    find_parser.add_argument('--location', type=str, default='Portland, OR', help='City/area to search in')
    find_parser.add_argument('--count', type=int, default=10, help='Maximum leads to return')

    # send-email - send a single email
    send_parser = subparsers.add_parser('send-email', help='Send a personalized cold email')
    send_parser.add_argument('--email', type=str, required=True, help='Recipient email address')
    send_parser.add_argument('--company', type=str, default='', help='Company name')
    send_parser.add_argument('--personalization', type=str, default='', help='Verified detail about the business')
    send_parser.add_argument('--category', type=str, default='services', help='Business category')

    # check-replies - poll IMAP for replies
    subparsers.add_parser('check-replies', help='Poll IMAP inbox and classify replies')

    # status - view statistics
    subparsers.add_parser('status', help='View campaign statistics')

    # blacklist - add email to blacklist
    bl_parser = subparsers.add_parser('blacklist', help='Add email to permanent do-not-contact list')
    bl_parser.add_argument('--email', type=str, required=True, help='Email to blacklist')
    bl_parser.add_argument('--reason', type=str, default='User requested via MCP', help='Reason for blacklisting')

    # search - search existing leads
    search_parser = subparsers.add_parser('search', help='Search existing lead database')
    search_parser.add_argument('--query', type=str, required=True, help='Search term')

    args = parser.parse_args()

    # Default: run full pipeline
    if args.command is None or args.command == 'run':
        run_once()
    elif args.command == 'find-leads':
        cmd_find_leads(args)
    elif args.command == 'send-email':
        cmd_send_email(args)
    elif args.command == 'check-replies':
        cmd_check_replies()
    elif args.command == 'status':
        cmd_status()
    elif args.command == 'blacklist':
        cmd_blacklist(args)
    elif args.command == 'search':
        cmd_search(args)


def cmd_find_leads(args):
    """Discover leads and print results as JSON."""
    all_candidates = []
    for ind in INDUSTRIES:
        for loc in LOCATIONS:
            rs = discovery.discover_leads(ind, loc, SEARCH_API_URL, SEARCH_API_KEY, count=args.count)
            all_candidates.extend(rs)
            time.sleep(0.5)

    # Filter and extract emails
    results = []
    skip_domains = [
        "yelp.com", "yellowpages.com", "angie.com", "angi.com",
        "thumbtack.com", "facebook.com", "care.com",
        "reddit.com", "youtube.com", "npr.org", "wikipedia.org",
        "wikimedia.org",
    ]
    website_builders = ["wordpress", "wix.com", "squarespace.com", "shopify.com", "weebly.com", "webflow.com"]

    for cand in all_candidates:
        url = cand.get("url", "")
        if any(d in url for d in skip_domains):
            continue
        if any(w in url.lower() for w in website_builders):
            continue

        business_name = cand.get("title", "Unknown Business")
        snippet = cand.get("content", "")
        found_emails, source_url = discovery.extract_emails_for_candidate(cand)
        found_emails = discovery.filter_business_emails(found_emails)

        if not found_emails:
            continue

        email_addr = found_emails[0]
        if db.email_exists(email_addr, "leads", DB_PATH):
            continue
        if db.is_blacklisted(email_addr, DB_PATH):
            continue

        clean_name = business_name
        for suffix in [" | ", " - ", " — "]:
            if suffix in clean_name:
                clean_name = clean_name.split(suffix)[0].strip()
        for suffix in ["(About)", "Contact Us", "Home", "Services"]:
            clean_name = clean_name.replace(suffix, "").strip()

        category = categorize(clean_name)
        personalization_fact = snippet[:250] if snippet else f"{clean_name} is a local {category} business serving Portland, Oregon"

        results.append({
            "business_name": clean_name,
            "category": category,
            "location": loc if 'loc' in dir() else "Portland, OR",
            "email": email_addr,
            "source_url": source_url or url,
            "personalization_fact": personalization_fact,
        })

    print(json.dumps({"leads": results, "count": len(results)}, indent=2))


def cmd_send_email(args):
    """Send a single personalized email."""
    html_body = f"<p>{args.personalization.replace(chr(10), '<br>') if args.personalization else ''}</p>"
    email_body = writer.write_email(
        args.company or args.email.split('@')[0],
        args.personalization or 'Local business',
        args.category,
        FROM_NAME,
        FROM_COMPANY,
        VALUE_PROP,
        openrouter_api_key=OPENROUTER_API_KEY,
    )
    subject = writer.make_subject(args.company or args.email)

    full_html = f"<p>{email_body.replace(chr(10), '<br>')}</p>"
    full_html += "<p><small>This is a commercial email. To opt out of future messages, reply with STOP.</small></p>"

    success = sender.send_email(
        args.email, subject, full_html,
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
        FROM_NAME, FROM_EMAIL,
    )

    if success:
        record = {
            "lead_number": 1,
            "business_name": args.company or args.email.split('@')[0],
            "business_category": args.category,
            "city_state": "Portland, OR",
            "owner_contact_name": "UNKNOWN",
            "public_business_email": args.email,
            "email_source_url": "manual",
            "business_phone": "UNKNOWN",
            "website_status": "NO WEBSITE",
            "website_evidence": "Manual email send",
            "google_rating": None,
            "google_review_count": None,
            "google_business_profile_url": "UNKNOWN",
            "recent_activity_date": "UNKNOWN",
            "recent_activity_source_url": "UNKNOWN",
            "personalization_fact": args.personalization or "Local business",
            "personalization_source_url": "manual",
            "qualification_status": "qualified",
            "confidence_level": "medium",
            "email_subject": subject,
            "email_body": email_body,
        }
        lead_id = db.add_lead_record(record, "leads", DB_PATH)
        db.mark_sent(lead_id, "leads", DB_PATH)
        print(json.dumps({"sent": True, "email": args.email, "lead_id": lead_id}))
    else:
        print(json.dumps({"sent": False, "email": args.email}))
        sys.exit(1)


def cmd_check_replies():
    """Check IMAP for replies."""
    if not IMAP_USER or not IMAP_PASS:
        print(json.dumps({"error": "IMAP not configured"}))
        return

    try:
        import imaplib
        import email as email_module

        mail = imaplib.IMAP4_SSL(IMAP_HOST, timeout=10)
        mail.login(IMAP_USER, IMAP_PASS)
        mail.select("inbox")
        date_since = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE {date_since})')

        replies = []
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
            classification = classifier.classify_reply(full_text, OPENROUTER_API_KEY)

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT id, business_name FROM leads WHERE sending_status='sent'")
            for lead_id, business_name in c.fetchall():
                if business_name.lower() in (from_addr + subject).lower():
                    c.execute("UPDATE leads SET qualification_status=? WHERE id=?",
                              (classification.lower(), lead_id))
            conn.commit()
            conn.close()

            replies.append({
                "from": from_addr,
                "subject": subject,
                "classification": classification,
                "body_preview": body[:200],
            })

        mail.logout()
        print(json.dumps({"replies": replies, "count": len(replies)}, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


def cmd_status():
    """Print campaign statistics."""
    stats = db.get_stats(DB_PATH)
    print(json.dumps(stats, indent=2))


def cmd_blacklist(args):
    """Add email to blacklist."""
    db.add_to_blacklist(args.email, "", args.reason, DB_PATH)
    print(json.dumps({"blacklisted": args.email, "reason": args.reason}))


def cmd_search(args):
    """Search existing leads."""
    results = db.search_leads(args.query, "leads", DB_PATH)
    print(json.dumps({"results": results, "count": len(results)}, indent=2))


if __name__ == "__main__":
    main()
