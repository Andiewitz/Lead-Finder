"""
Database module for Andrei's Web Dev Client Acquisition.

Manages three tables:
  - leads:      Sent or attempted lead records
  - blacklist:  Never-contact-again list (emails)
  - whitelist:  Qualified leads found but not sent (saved for future runs)

All tables are indexed on email, name, status, and date columns for fast lookups.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LEAD_COLUMNS = [
    "lead_number",
    "business_name",
    "business_category",
    "city_state",
    "owner_contact_name",
    "public_business_email",
    "email_source_url",
    "business_phone",
    "website_status",
    "website_evidence",
    "google_rating",
    "google_review_count",
    "google_business_profile_url",
    "recent_activity_date",
    "recent_activity_source_url",
    "personalization_fact",
    "personalization_source_url",
    "qualification_status",
    "confidence_level",
    "email_subject",
    "email_body",
]


def get_connection(db_path: str = "leads.db") -> sqlite3.Connection:
    """Open a SQLite connection with row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = "leads.db") -> None:
    """Create all tables and indexes if they don't exist."""
    conn = get_connection(db_path)
    c = conn.cursor()

    # ── leads table ──────────────────────────────────────────────────
    c.execute(
        """
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
        """
    )

    # ── blacklist table ──────────────────────────────────────────────
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            business_name TEXT,
            reason TEXT,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # ── whitelist table ──────────────────────────────────────────────
    c.execute(
        """
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
        """
    )

    # ── Migration: add lead_number to existing whitelist tables ──────
    try:
        c.execute("ALTER TABLE whitelist ADD COLUMN lead_number INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # ── Indexes for fast lookups ─────────────────────────────────────
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(public_business_email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_name ON leads(business_name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(sending_status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_leads_date ON leads(sent_timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_email ON blacklist(email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_whitelist_email ON whitelist(public_business_email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_whitelist_priority ON whitelist(priority DESC)")

    conn.commit()
    conn.close()


def add_lead_record(data: Dict[str, Any], table: str = "leads", db_path: str = "leads.db") -> int:
    """Insert a lead record into the specified table. Returns the new row id."""
    conn = get_connection(db_path)
    c = conn.cursor()

    cols = [
        "lead_number",
        "business_name",
        "business_category",
        "city_state",
        "owner_contact_name",
        "public_business_email",
        "email_source_url",
        "business_phone",
        "website_status",
        "website_evidence",
        "google_rating",
        "google_review_count",
        "google_business_profile_url",
        "recent_activity_date",
        "recent_activity_source_url",
        "personalization_fact",
        "personalization_source_url",
        "qualification_status",
        "confidence_level",
        "email_subject",
        "email_body",
    ]
    placeholders = ", ".join(["?"] * len(cols))
    col_str = ", ".join(cols)
    values = [data.get(col) for col in cols]

    c.execute(f"INSERT INTO {table} ({col_str}) VALUES ({placeholders})", values)
    conn.commit()
    lid = c.lastrowid
    conn.close()
    return lid


def mark_sent(lead_id: int, table: str = "leads", db_path: str = "leads.db") -> None:
    """Mark a lead as sent with timestamp."""
    conn = get_connection(db_path)
    c = conn.cursor()
    c.execute(
        f"UPDATE {table} SET sending_status='sent', sent_timestamp=? WHERE id=?",
        (datetime.now(timezone.utc).isoformat(), lead_id),
    )
    conn.commit()
    conn.close()


def get_draft_leads(limit: int, table: str = "leads", db_path: str = "leads.db") -> List[Dict[str, Any]]:
    """Fetch draft leads up to the given limit."""
    conn = get_connection(db_path)
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table} WHERE sending_status='draft' LIMIT ?", (limit,))
    cols = [d[0] for d in c.description]
    rows = c.fetchall()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def email_exists(email_addr: str, table: str = "leads", db_path: str = "leads.db") -> bool:
    """Check if an email already exists in any table (leads, blacklist, whitelist)."""
    conn = get_connection(db_path)
    c = conn.cursor()

    c.execute(f"SELECT id FROM {table} WHERE public_business_email=?", (email_addr,))
    if c.fetchone():
        conn.close()
        return True

    c.execute("SELECT id FROM blacklist WHERE email=?", (email_addr,))
    if c.fetchone():
        conn.close()
        return True

    c.execute("SELECT id FROM whitelist WHERE public_business_email=?", (email_addr,))
    if c.fetchone():
        conn.close()
        return True

    conn.close()
    return False


def is_blacklisted(email_addr: str, db_path: str = "leads.db") -> bool:
    """Check if an email is on the blacklist."""
    conn = get_connection(db_path)
    c = conn.cursor()
    c.execute("SELECT id FROM blacklist WHERE email=?", (email_addr,))
    row = c.fetchone()
    conn.close()
    return row is not None


def add_to_blacklist(email_addr: str, business_name: str = "", reason: str = "", db_path: str = "leads.db") -> None:
    """Add an email to the blacklist (never contact again)."""
    conn = get_connection(db_path)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT OR IGNORE INTO blacklist (email, business_name, reason) VALUES (?, ?, ?)",
            (email_addr, business_name, reason),
        )
        conn.commit()
    except sqlite3.Error:
        pass
    conn.close()


def add_to_whitelist(data: Dict[str, Any], db_path: str = "leads.db") -> int:
    """Save a qualified lead to the whitelist for future sending runs."""
    lid = add_lead_record(data, table="whitelist", db_path=db_path)

    # Set priority if provided
    if data.get("priority") is not None:
        conn = get_connection(db_path)
        c = conn.cursor()
        c.execute("UPDATE whitelist SET priority=? WHERE id=?", (data["priority"], lid))
        conn.commit()
        conn.close()

    return lid


def get_whitelist_leads(limit: int, db_path: str = "leads.db") -> List[Dict[str, Any]]:
    """Fetch whitelisted leads ordered by priority, then oldest first."""
    conn = get_connection(db_path)
    c = conn.cursor()
    c.execute(
        "SELECT * FROM whitelist ORDER BY priority DESC, added_at ASC LIMIT ?",
        (limit,),
    )
    cols = [d[0] for d in c.description]
    rows = c.fetchall()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def move_whitelist_to_leads(lead_id: int, db_path: str = "leads.db") -> Optional[int]:
    """Move a whitelisted lead into the leads table for sending. Returns new lead id."""
    conn = get_connection(db_path)
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

    new_id = add_lead_record(data, table="leads", db_path=db_path)

    c.execute("DELETE FROM whitelist WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()
    return new_id


def search_leads(query: str, table: str = "leads", db_path: str = "leads.db") -> List[Dict[str, Any]]:
    """Search leads by business name, email, or category."""
    conn = get_connection(db_path)
    c = conn.cursor()
    like = f"%{query}%"
    c.execute(
        f"""
        SELECT * FROM {table}
        WHERE business_name LIKE ? OR public_business_email LIKE ? OR business_category LIKE ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (like, like, like),
    )
    cols = [d[0] for d in c.description]
    rows = c.fetchall()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]


def get_stats(db_path: str = "leads.db") -> Dict[str, int]:
    """Return summary statistics for all tables."""
    conn = get_connection(db_path)
    c = conn.cursor()

    stats: Dict[str, int] = {}

    c.execute("SELECT COUNT(*) FROM leads WHERE sending_status='sent'")
    stats["sent"] = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM leads WHERE sending_status='draft'")
    stats["draft"] = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM whitelist")
    stats["whitelist"] = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM blacklist")
    stats["blacklist"] = c.fetchone()[0]

    today = datetime.now(timezone.utc).date().isoformat()
    c.execute(
        "SELECT COUNT(DISTINCT public_business_email) FROM leads "
        "WHERE sending_status='sent' AND date(sent_timestamp)=?",
        (today,),
    )
    stats["sent_today"] = c.fetchone()[0]

    conn.close()
    return stats


def get_all_stats(db_path: str = "leads.db") -> Dict[str, Any]:
    """Return detailed statistics including recent activity."""
    conn = get_connection(db_path)
    c = conn.cursor()

    stats: Dict[str, Any] = {}

    # Counts by status
    c.execute("SELECT sending_status, COUNT(*) FROM leads GROUP BY sending_status")
    stats["by_status"] = dict(c.fetchall())

    # Counts by category
    c.execute("SELECT business_category, COUNT(*) FROM leads GROUP BY business_category")
    stats["by_category"] = dict(c.fetchall())

    # Sent today
    today = datetime.now(timezone.utc).date().isoformat()
    c.execute(
        "SELECT COUNT(DISTINCT public_business_email) FROM leads "
        "WHERE sending_status='sent' AND date(sent_timestamp)=?",
        (today,),
    )
    stats["sent_today"] = c.fetchone()[0]

    # Total unique emails
    c.execute("SELECT COUNT(DISTINCT public_business_email) FROM leads WHERE sending_status='sent'")
    stats["total_sent"] = c.fetchone()[0]

    conn.close()
    return stats
