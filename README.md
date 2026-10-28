# Andrei's Web Dev Client Acquisition

Autonomous lead outreach automation for freelance web developers. Find Portland-area small businesses, research them, write personalized cold emails, send via Gmail SMTP, and track replies — all with zero OAuth, zero domain verification, and $0 in paid services.

## Features

| Feature | Description |
|---------|-------------|
| **Lead Discovery** | Tavily web search finds Portland-area businesses (cleaning, landscaping, handyman, auto detailing, pet grooming, pressure washing) |
| **AI Writing** | OpenRouter Nemotron 3.5 Super VL writes personalized cold emails (template fallback when rate-limited) |
| **Email Sending** | Gmail SMTP — no domain verification, no paid email service |
| **Reply Tracking** | IMAP monitoring with keyword-based classification (Interested / Not interested / Out of office) |
| **Blacklist** | Permanent do-not-contact list |
| **Whitelist** | Qualified leads saved when daily quota is full |
| **Confirmation Email** | Summary sent to operator after every run |
| **SQLite Database** | Indexed leads, blacklist, whitelist tables |
| **CAN-SPAM Ready** | Opt-out footer in every email |

## Quick Start

### 1. Clone

```bash
git clone https://github.com/andre1gr4ce/email-sender.git
cd email-sender
```

### 2. Run Setup

```bash
bash scripts/setup.sh
```

This creates a virtual environment, installs dependencies, copies `.env.example` to `.env`, initializes the database, runs tests, and optionally sets up a cron job.

### 3. Configure `.env`

Edit `.env` with your API keys:

```ini
OPENROUTER_API_KEY=sk-or-...          # from openrouter.ai/keys
SEARCH_API_KEY=tvly-dev-...           # from tavily.com (free tier)
SMTP_USER=your_email@gmail.com        # your Gmail address
SMTP_PASS=your_16_char_app_password   # Gmail App Password (2FA required)
FROM_EMAIL=your_email@gmail.com
FROM_NAME=Your Name
FROM_COMPANY=Your Company
DAILY_LIMIT=20
```

**Gmail App Password:** Enable 2-Step Verification, then go to myaccount.google.com/apppasswords to generate a 16-character password.

### 4. Run

```bash
source venv/bin/activate
python src/main.py
```

### 5. Automate (Cron)

The setup script can install a cron job that runs weekdays at 14:00 UTC (9AM EST / 3PM CET):

```bash
0 14 * * 1-5 /path/to/venv/bin/python /path/to/email-sender/src/main.py >> /path/to/email-sender/logs.txt 2>&1
```

## npm Package + MCP Server (OpenCode / KiloCode)

Install `@andrewitz/lead-finder` from npm to use the lead outreach system as an MCP server in OpenCode or KiloCode:

```bash
npm install -g @andrewitz/lead-finder
```

This installs the `lead-finder` CLI and the MCP server. Configure your AI assistant to connect to it:

### OpenCode MCP Config (`~/.opencode/mcp.json` or `.mcp.opencode.json`)

```json
{
  "mcpServers": {
    "lead-finder": {
      "command": "npx",
      "args": ["-y", "@andrewitz/lead-finder@latest", "start"],
      "env": {
        "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}",
        "SEARCH_API_KEY": "${SEARCH_API_KEY}",
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "${SMTP_USER}",
        "SMTP_PASS": "${SMTP_PASS}",
        "IMAP_HOST": "imap.gmail.com",
        "IMAP_USER": "${SMTP_USER}",
        "IMAP_PASS": "${SMTP_PASS}",
        "FROM_NAME": "Andrei",
        "FROM_EMAIL": "${SMTP_USER}",
        "FROM_COMPANY": "Andrei Freelance Web Development",
        "VALUE_PROP": "I build custom websites for small businesses",
        "DAILY_LIMIT": "20",
        "DB_PATH": "${HOME}/.lead-finder/leads.db"
      }
    }
  }
}
```

### KiloCode MCP Config (`~/.kilocode/mcp.json` or `.mcp.kilocode.json`)

```json
{
  "mcpServers": {
    "lead-finder": {
      "command": "npx",
      "args": ["-y", "@andrewitz/lead-finder@latest", "start"],
      "env": {
        "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}",
        "SEARCH_API_KEY": "${SEARCH_API_KEY}",
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "${SMTP_USER}",
        "SMTP_PASS": "${SMTP_PASS}",
        "IMAP_HOST": "imap.gmail.com",
        "IMAP_USER": "${SMTP_USER}",
        "IMAP_PASS": "${SMTP_PASS}",
        "FROM_NAME": "Andrei",
        "FROM_EMAIL": "${SMTP_USER}",
        "FROM_COMPANY": "Andrei Freelance Web Development",
        "VALUE_PROP": "I build custom websites for small businesses",
        "DAILY_LIMIT": "20",
        "DB_PATH": "${HOME}/.lead-finder/leads.db"
      }
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `find_leads` | Discover Portland-area small businesses via Tavily web search |
| `send_email` | Send a personalized cold email via Gmail SMTP |
| `check_replies` | Poll IMAP inbox and classify replies (Interested / Not interested / Out of office) |
| `get_stats` | View campaign statistics (sent today, total, drafts, whitelist, blacklist) |
| `add_to_blacklist` | Add an email/domain to the permanent do-not-contact list |
| `search_leads` | Search existing lead database by name, email, or category |

### CLI Commands

```bash
# Start MCP server (for OpenCode/KiloCode)
lead-finder start

# Discover new leads
lead-finder find-leads --industry "cleaning services" --location "Portland, OR"

# Send a single email
lead-finder send-email --email grace@example.com --company "Grace Cleaning" --personalization "They offer eco-friendly cleaning"

# Check for replies
lead-finder check-replies

# View statistics
lead-finder status

# Blacklist an email
lead-finder blacklist --email spam@example.com --reason "Spam complainer"

# Search existing leads
lead-finder search --query "handyman"
```


## Architecture

```
src/
├── __init__.py
├── db.py           # SQLite: leads, blacklist, whitelist + indexes
├── discovery.py    # Tavily search + email extraction
├── writer.py       # OpenRouter primary, template fallback
├── sender.py       # Gmail SMTP + confirmation email
├── classifier.py   # OpenRouter keyword reply classification
└── main.py         # Orchestrator: full pipeline + CLI subcommands

bin/
└── lead-finder     # CLI entry point

src/mcp_server.js   # MCP server over stdio (for OpenCode/KiloCode)
```

### Database Tables

| Table | Purpose |
|-------|---------|
| `leads` | Sent or attempted leads (22 fields per AI_AGENT_BRIEF.md) |
| `blacklist` | Permanent do-not-contact emails |
| `whitelist` | Qualified leads found but not sent (saved for future runs) |

### Indexes

`leads(email)`, `leads(name)`, `leads(status)`, `leads(date)`, `blacklist(email)`, `whitelist(email)`, `whitelist(priority)`

## Qualification Rules

A business counts as a qualified lead only if ALL of the following are true:

- **No website** (or verifiable upgrade opportunity)
- **Google rating ≥ 4.0 stars** with 10–250 reviews
- **Recent activity** within the past 6 months
- **Public business email** (never guessed or constructed)
- **Not on the exclusion list** (24 previously contacted businesses)
- **Not a directory/aggregator** (Yelp, YellowPages, Thumbtack, etc.)
- **Not a website builder site** (WordPress, Wix, Squarespace, etc.)

## Email Format

Every email follows the AI_AGENT_BRIEF.md template:

- Short, non-deceptive subject line
- Verified opening detail about the business
- Concrete website benefits (category-specific)
- "My name is Andrei, and I'm a web developer who builds websites for small businesses."
- Portfolio + GitHub links
- Low-pressure call to action
- CAN-SPAM opt-out footer

## Limits & Safety

| Limit | Value |
|-------|-------|
| Default daily emails | 20 |
| Gmail free tier | 500/day |
| Recommended warm-up | Start at 20/day for 2 weeks |
| Max recommended | 50/day |
| Retry backoff | Exponential (1s, 2s, 4s, 8s, 16s) |

## Testing

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

21 unit tests covering all modules. CI runs on GitHub Actions for Python 3.10/3.11/3.12.

## License

MIT License — see [LICENSE](LICENSE) for details.

## Disclaimer

This tool automates cold email outreach. You are responsible for complying with CAN-SPAM, GDPR, and other applicable laws. Always include an opt-out mechanism and honor opt-out requests promptly.

## Contributing

Bug reports and pull requests are welcome. Please do not commit API keys or secrets. See [CONTRIBUTING.md](CONTRIBUTING.md) if it exists, or open an issue to discuss.
