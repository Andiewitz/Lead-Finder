# Lead Outreach Automation

Run the autonomous lead outreach system from within Kilo.

## Usage

```
/lead-outreach <action>
```

## Actions

| Action | Description |
|--------|-------------|
| `run` | Run the outreach automation once (sends up to 20 emails) |
| `test` | Send a test email to galletoandre94@gmail.com |
| `tests` | Run all 14 unit tests |
| `status` | Show current configuration and database status |

## Examples

```
/lead-outreach run
/lead-outreach test
/lead-outreach tests
```

## Setup

1. `cd ~/Desktop/email-sender`
2. `source venv/bin/activate`
3. Edit `.env` with your API keys (OpenRouter, Gmail App Password, Tavily)
4. Run: `python main.py`

## Cron

Already configured: weekdays at 14:00 UTC (9AM EST / 3PM CET)
