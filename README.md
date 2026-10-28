# Lead Outreach Automation (Python, zero OAuth, $0)

Runs locally. No n8n, no OAuth browser flows, no domain needed, no paid services.

Uses **Enrich MCP/API** for lead discovery + email verification, **OpenRouter Nemotron** for AI research/writing, and **Gmail SMTP** for sending.

## 1. Install
```bash
cd ~/Desktop/email-sender
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Configure
```bash
cp .env.example .env
# Edit .env and fill in:
#   OPENROUTER_API_KEY  - from openrouter.ai/keys
#   ENRICH_API_KEY      - from enrich.so (configured in Kilo MCP too)
#   SMTP_USER           - your Gmail address
#   SMTP_PASS           - Gmail App Password (from myaccount.google.com/apppasswords)
#   FROM_EMAIL          - same as SMTP_USER
```

### Gmail App Password setup:
1. Go to your Google Account → Security → 2-Step Verification (turn it ON)
2. Go to Security → App passwords → select "Mail" → generate password
3. Use that 16-character password as `SMTP_PASS` in `.env`

**Never share your .env file.**

## 3. Run once (finds leads, verifies emails, sends up to 20)
```bash
python main.py
```

## 4. Run tests
```bash
python -m unittest test_main -v
```

## 5. Send a test email
```bash
python test_send_email.py
```

## 6. Automate daily (cron — already configured)
Cron runs weekdays at 14:00 UTC (9AM EST / 3PM CET — peak US+EU business overlap).
Logs go to `~/Desktop/email-sender/logs.txt`.

## How it works

1. **Discover** — Enrich Lead Finder searches 300M+ leads for Portland-area small businesses in target industries
2. **Find email** — Enrich Email Finder locates the owner's professional email
3. **Validate** — Enrich Email Validation confirms the email is deliverable before sending
4. **Research** — Nemotron researches each company for personalization
5. **Write** — Nemotron writes a personalized cold email following the brief format
6. **Send** — Gmail SMTP sends it (free, no domain needed)
7. **Track** — IMAP checks inbox and classifies replies

## Qualification (per AI_AGENT_BRIEF.md)

Only businesses that pass ALL checks count as qualified:
- Real business in Portland metro area
- Google rating 4.0+ stars, 10–250 reviews
- Recent activity within 6 months
- No website OR verifiable upgrade opportunity
- Publicly listed, verified email address
- Not on the permanent exclusion list (24 previously contacted businesses)

## Limits

- **Gmail free**: 500 emails/day (you're sending 20)
- **Enrich**: check your plan limits at enrich.so
- **OpenRouter Nemotron**: free tier available
- **Tavily free**: 1,000 searches/month (backup)

## No domain, no paid services needed

Everything uses API keys only + your free Gmail account. No OAuth consent flows, no Enterprise plan, no domain verification.

## Kilo MCP Integration

Enrich is also configured in `~/.config/kilo/kilo.jsonc` as an MCP server. You can use Kilo's MCP tools directly:
- `enrich_lead_finder` — search for business leads
- `enrich_email_finder` — find emails from name + domain
- `enrich_email_validation` — verify email deliverability
