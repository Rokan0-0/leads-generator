#!/usr/bin/env python3
"""
Migrates local SQLite database (leadpulse.db) to Turso Cloud SQLite.
Usage:
  python migrate_turso.py
"""
import sqlite3
from pathlib import Path
from rich.console import Console

from leadpulse.config import DB_PATH, TURSO_AUTH_TOKEN, TURSO_DATABASE_URL
from leadpulse.turso import execute_turso_query, is_turso_configured

console = Console()


def migrate():
    console.print("\n[bold cyan]🚀 LeadPulse NG -> Turso Cloud Database Migrator[/bold cyan]\n")

    if not is_turso_configured():
        console.print("[bold red]❌ Turso credentials not found in .env[/bold red]")
        console.print("Please set:\n  TURSO_DATABASE_URL=...\n  TURSO_AUTH_TOKEN=...\nin your .env file first.\n")
        return

    if not DB_PATH.exists():
        console.print(f"[bold red]❌ Local database not found at {DB_PATH}[/bold red]")
        return

    local_conn = sqlite3.connect(DB_PATH)
    local_conn.row_factory = sqlite3.Row

    console.print("📡 Connecting to Turso Cloud...")

    # 1. Initialize Tables in Turso
    console.print("1️⃣ Creating tables in Turso...")
    execute_turso_query("""
        CREATE TABLE IF NOT EXISTS leads (
            lead_id TEXT PRIMARY KEY,
            business_name TEXT NOT NULL,
            niche TEXT NOT NULL,
            location TEXT,
            address TEXT,
            ig_handle_url TEXT,
            current_bio_link TEXT,
            funnel_diagnosis TEXT NOT NULL,
            flaw_detail TEXT,
            whatsapp_number TEXT,
            whatsapp_direct_link TEXT,
            lead_score_num INTEGER,
            lead_score TEXT NOT NULL,
            ai_pitch_angle TEXT,
            custom_pitch TEXT,
            message_1 TEXT,
            message_2 TEXT,
            followup TEXT,
            demo_url TEXT,
            outreach_status TEXT DEFAULT 'Pending',
            dm_sent_at TEXT,
            followup_due_at TEXT,
            source TEXT,
            rating REAL,
            reviews_count INTEGER,
            maps_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    execute_turso_query("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    console.print("   ✓ Tables ready on Turso.")

    # 2. Migrate Leads
    local_leads = local_conn.execute("SELECT * FROM leads").fetchall()
    console.print(f"2️⃣ Uploading {len(local_leads)} leads from local database...")

    cols = [
        "lead_id", "business_name", "niche", "location", "address", "ig_handle_url",
        "current_bio_link", "funnel_diagnosis", "flaw_detail", "whatsapp_number",
        "whatsapp_direct_link", "lead_score_num", "lead_score", "ai_pitch_angle",
        "custom_pitch", "message_1", "message_2", "followup", "demo_url",
        "outreach_status", "dm_sent_at", "followup_due_at", "source", "rating",
        "reviews_count", "maps_url"
    ]
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"""
        INSERT OR REPLACE INTO leads ({', '.join(cols)})
        VALUES ({placeholders})
    """

    for idx, r in enumerate(local_leads, 1):
        vals = [r[c] if c in r.keys() else None for c in cols]
        execute_turso_query(sql, vals)
        if idx % 10 == 0 or idx == len(local_leads):
            console.print(f"   → Synced {idx}/{len(local_leads)} leads")

    # 3. Migrate Settings
    local_settings = local_conn.execute("SELECT * FROM app_settings").fetchall()
    console.print(f"3️⃣ Uploading {len(local_settings)} settings records...")
    for s in local_settings:
        execute_turso_query(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            [s["key"], s["value"]]
        )

    local_conn.close()
    console.print("\n[bold green]✅ Migration complete! Your database is now live on Turso Cloud.[/bold green]\n")


if __name__ == "__main__":
    migrate()
