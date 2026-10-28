#!/usr/bin/env bash
#
# setup.sh — One-command setup for Andrei's Web Dev Client Acquisition
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/andre1gr4ce/email-sender/main/scripts/setup.sh | bash
#
# Or clone and run:
#   git clone https://github.com/andre1gr4ce/email-sender.git
#   cd email-sender
#   bash scripts/setup.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Andrei's Web Dev Client Acquisition — Setup ==="
echo ""

# ── Check Python ──────────────────────────────────────────────────────
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# ── Create virtual environment ────────────────────────────────────────
VENV_DIR="$PROJECT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# ── Install dependencies ──────────────────────────────────────────────
echo "Installing dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

# ── Copy .env.example to .env ─────────────────────────────────────────
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "Creating .env from .env.example..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo ""
    echo "IMPORTANT: Edit $PROJECT_DIR/.env with your API keys:"
    echo "  - OPENROUTER_API_KEY (from openrouter.ai/keys)"
    echo "  - SEARCH_API_KEY (from tavily.com)"
    echo "  - SMTP_USER / SMTP_PASS (Gmail App Password)"
    echo "  - FROM_EMAIL (your verified Gmail address)"
    echo ""
else
    echo ".env already exists, skipping copy."
fi

# ── Initialize database ───────────────────────────────────────────────
echo "Initializing database..."
"$VENV_DIR/bin/python" -c "from src import db; db.init_db(); print('Database ready.')"

# ── Run tests ─────────────────────────────────────────────────────────
echo ""
echo "Running test suite..."
cp "$PROJECT_DIR/.env.test" "$PROJECT_DIR/.env"
"$VENV_DIR/bin/python" -m pytest "$PROJECT_DIR/tests/" -v

# ── Setup cron job (optional) ─────────────────────────────────────────
echo ""
read -p "Set up daily cron job? (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    CRON_LINE="0 14 * * 1-5 $VENV_DIR/bin/python $PROJECT_DIR/src/main.py >> $PROJECT_DIR/logs.txt 2>&1"
    (crontab -l 2>/dev/null | grep -v "email-sender" ; echo "$CRON_LINE") | crontab -
    echo "Cron job installed: weekdays at 14:00 UTC (9AM EST / 3PM CET)"
fi

echo ""
echo "=== Setup complete! ==="
echo ""
echo "To run the outreach:"
echo "  source $VENV_DIR/bin/activate"
echo "  python $PROJECT_DIR/src/main.py"
echo ""
echo "To run tests:"
echo "  source $VENV_DIR/bin/activate"
echo "  python -m pytest $PROJECT_DIR/tests/ -v"
echo ""
echo "Next steps:"
echo "  1. Edit $PROJECT_DIR/.env with your API keys"
echo "  2. Verify your Gmail address in the sender settings"
echo "  3. Run: python src/main.py"
