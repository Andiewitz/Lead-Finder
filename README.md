# Lead Finder

A terminal and MCP tool for discovering potential business leads, drafting individual outreach emails, and checking replies. Search results are **candidates**, not verified or qualified leads. Review the source, contact address, business details, and any message before outreach.

## Setup

Requirements: Node.js 18 or later and Python 3.10 or later. From the repository directory:

```sh
npm install
python -m pip install -r requirements.txt
npm link
lead-finder --config
```

If the CLI cannot find Python, set `LEAD_FINDER_PYTHON` to the Python executable with the installed dependencies. The wizard stores settings in `~/.lead-finder/.env` and uses `~/.lead-finder/leads.db` by default. `LEAD_FINDER_HOME` can select another directory. An existing repository `.env` remains supported. Environment variables take precedence over the file. Protect this directory: it contains credentials and lead data.

Tavily's `SEARCH_API_KEY` is needed for discovery. Sending requires `FROM_NAME`, `FROM_EMAIL`, `SMTP_USER`, and `SMTP_PASS`; reply checking requires IMAP credentials. OpenRouter is optional: without it the writer uses a template. Configure `PORTFOLIO_URL` and `GITHUB_URL` in the environment or settings file to include your own links.

## Workflow

```sh
# Find candidates without sending email
lead-finder find-leads --industry "handyman" --location "Portland, OR" --count 10

# Generate a draft without sending
lead-finder send-email --email person@example.com --company "Example" --personalization "A detail you verified" --preview

# Generate and send one message
lead-finder send-email --email person@example.com --company "Example" --personalization "A detail you verified"

lead-finder status
lead-finder check-replies
lead-finder blacklist --email example.com --reason "Do not contact"
lead-finder search --query "Example"
lead-finder --tui
```

The terminal menu asks for confirmation before a send. A preview and a subsequent send each generate a draft; AI-generated wording may differ. The preview is not an approved draft that can be sent unchanged. The old `run` command now performs discovery only. It does not send queued or newly discovered leads. Existing whitelist data remains in the database but is not automatically sent.

Discovery uses search snippets and publicly found addresses. It does not verify ratings, review counts, website status, recent activity, ownership of an address, or the accuracy of a snippet. The user must review these before contacting anyone. Search results and drafts can be sent to the configured search and AI providers, respectively; reply text may be sent to the AI provider when classification is enabled.

## Sending and replies

Each direct send checks the address and exact domain against the do-not-contact list, checks prior sends, and reserves the configured daily quota before connecting to SMTP. The limit resets at midnight UTC. The default is 20. Failed or interrupted SMTP operations can have an unknown outcome; these appear as `needs_send_review` in status and block another send to that recipient. Inspect the mailbox and database before resolving such a record; there is not yet a dedicated resolution command.

Reply polling checks the past seven days of the configured inbox and matches sender addresses to previously sent leads. It records processed message IDs and suppresses addresses for several explicit opt-out phrases. Automated matching and classification can miss replies or opt-outs, especially replies from another address or unusual formats. Review the inbox and do-not-contact list manually as well.

The footer is not a guarantee of legal compliance. Review applicable requirements and your message content before sending.

## MCP

Run `lead-finder start` through stdio from your MCP client. The tools are `find_leads`, `send_email` (supports `preview`), `check_replies`, `get_stats`, `add_to_blacklist`, and `search_leads`. Supply settings through the environment or the configuration file. In an interactive terminal, `start` opens the dashboard instead.

## Development

```sh
python -m pip install -r requirements.txt pytest ruff
python -m pytest tests -q
ruff check src tests
```

The tests mock external services; a passing suite does not verify a real Tavily, SMTP, IMAP, or MCP client connection. The Python and Node CLI code is in `src/` and `bin/` respectively.
