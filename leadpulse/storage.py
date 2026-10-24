import csv
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DB_PATH, DEFAULT_EXPORT_CSV, DEFAULT_NICHE_CONFIGS, GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_SHEET_NAME
from .models import FunnelDiagnosis, Lead, LeadScoreBucket, OutreachStatus
from .turso import execute_turso_query, is_turso_configured


def get_db_connection() -> sqlite3.Connection:
    """Creates and initializes the SQLite database schema with auto-migrations."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
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

    # Auto-migrate any missing columns for existing databases
    existing_cols = {c[1] for c in conn.execute("PRAGMA table_info(leads)").fetchall()}
    new_cols = [
        ("address", "TEXT"),
        ("custom_pitch", "TEXT"),
        ("demo_url", "TEXT"),
        ("message_1", "TEXT"),
        ("message_2", "TEXT"),
        ("followup", "TEXT"),
        ("dm_sent_at", "TEXT"),
        ("followup_due_at", "TEXT"),
    ]
    for col, col_type in new_cols:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col} {col_type}")

    # Settings table for PWA (portfolio templates, PIN, default pitch configs)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def get_setting(key: str, default: Any = None) -> Any:
    """Retrieves an application setting from Turso or local SQLite."""
    if is_turso_configured():
        rows = execute_turso_query("SELECT value FROM app_settings WHERE key = ?", [key])
        if rows:
            try:
                return json.loads(rows[0]["value"])
            except Exception:
                return rows[0]["value"]
        return default

    conn = get_db_connection()
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]
    return default


def set_setting(key: str, value: Any):
    """Sets an application setting in Turso or local SQLite."""
    val_str = json.dumps(value) if not isinstance(value, str) else value
    if is_turso_configured():
        execute_turso_query("""
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, [key, val_str])
        return

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, val_str))
    conn.commit()
    conn.close()


def get_all_settings() -> Dict[str, Any]:
    """Retrieves all application settings with sensible defaults."""
    default_templates = {
        "Shortlet Apartments": "https://shortlet-preview-lagos.vercel.app",
        "Solar Installation": "https://solar-flow-nigeria.vercel.app",
        "Aesthetics & Med-Spa": "https://glow-aesthetics-preview.vercel.app",
        "Dental Clinic": "https://smile-dental-care.vercel.app",
        "Fine Dining": "https://savory-lounge-dining.vercel.app",
    }
    
    if is_turso_configured():
        rows = execute_turso_query("SELECT key, value FROM app_settings")
    else:
        conn = get_db_connection()
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        conn.close()

    settings_dict = {}
    for r in rows:
        try:
            settings_dict[r["key"]] = json.loads(r["value"])
        except Exception:
            settings_dict[r["key"]] = r["value"]

    if "portfolio_templates" not in settings_dict:
        settings_dict["portfolio_templates"] = default_templates
    if "niche_configs" not in settings_dict:
        settings_dict["niche_configs"] = DEFAULT_NICHE_CONFIGS
    if "include_demo_link" not in settings_dict:
        settings_dict["include_demo_link"] = True
    if "access_pin" not in settings_dict:
        settings_dict["access_pin"] = "1234"

    return settings_dict


def save_leads(leads: List[Lead]) -> tuple[int, int]:
    """
    Upserts leads into Turso or local SQLite database.
    Deduplicates primarily on normalized WhatsApp phone number (if present), or lead_id.
    Returns: (inserted_count, updated_count)
    """
    if is_turso_configured():
        inserted = 0
        updated = 0
        for lead in leads:
            existing = None
            if lead.whatsapp_number:
                rows = execute_turso_query(
                    "SELECT lead_id, outreach_status FROM leads WHERE whatsapp_number = ?",
                    [lead.whatsapp_number]
                )
                if rows:
                    existing = rows[0]

            if not existing:
                rows = execute_turso_query(
                    "SELECT lead_id, outreach_status FROM leads WHERE lead_id = ?",
                    [lead.lead_id]
                )
                if rows:
                    existing = rows[0]

            target_id = existing["lead_id"] if existing else lead.lead_id

            if existing:
                execute_turso_query("""
                    UPDATE leads SET
                        business_name = ?, niche = ?, location = ?,
                        address = COALESCE(NULLIF(?, ''), address),
                        ig_handle_url = ?, current_bio_link = ?, funnel_diagnosis = ?,
                        flaw_detail = ?, whatsapp_number = ?, whatsapp_direct_link = ?,
                        lead_score_num = ?, lead_score = ?,
                        ai_pitch_angle = COALESCE(NULLIF(ai_pitch_angle, ''), ?),
                        message_1 = COALESCE(NULLIF(?, ''), message_1),
                        message_2 = COALESCE(NULLIF(?, ''), message_2),
                        followup = COALESCE(NULLIF(?, ''), followup),
                        demo_url = COALESCE(NULLIF(?, ''), demo_url),
                        source = ?, rating = COALESCE(?, rating),
                        reviews_count = COALESCE(?, reviews_count), maps_url = COALESCE(?, maps_url),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE lead_id = ?
                """, [
                    lead.business_name, lead.niche, lead.location, lead.address or "",
                    lead.ig_handle_url, lead.current_bio_link, lead.funnel_diagnosis.value,
                    lead.flaw_detail, lead.whatsapp_number, lead.whatsapp_direct_link,
                    lead.lead_score_num, lead.lead_score.value, lead.ai_pitch_angle,
                    lead.message_1 or "", lead.message_2 or "", lead.followup or "",
                    lead.demo_url or "",
                    lead.source, lead.rating, lead.reviews_count, lead.maps_url,
                    target_id,
                ])
                updated += 1
            else:
                execute_turso_query("""
                    INSERT INTO leads (
                        lead_id, business_name, niche, location, address, ig_handle_url,
                        current_bio_link, funnel_diagnosis, flaw_detail, whatsapp_number,
                        whatsapp_direct_link, lead_score_num, lead_score, ai_pitch_angle,
                        custom_pitch, message_1, message_2, followup, demo_url,
                        outreach_status, dm_sent_at, followup_due_at, source, rating,
                        reviews_count, maps_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    lead.lead_id, lead.business_name, lead.niche, lead.location,
                    lead.address or "", lead.ig_handle_url, lead.current_bio_link,
                    lead.funnel_diagnosis.value, lead.flaw_detail, lead.whatsapp_number,
                    lead.whatsapp_direct_link, lead.lead_score_num, lead.lead_score.value,
                    lead.ai_pitch_angle, lead.custom_pitch, lead.message_1, lead.message_2,
                    lead.followup, lead.demo_url, lead.outreach_status.value,
                    lead.dm_sent_at, lead.followup_due_at, lead.source, lead.rating,
                    lead.reviews_count, lead.maps_url,
                ])
                inserted += 1
        return inserted, updated

    conn = get_db_connection()
    inserted = 0
    updated = 0

    for lead in leads:
        # Check by WhatsApp phone first (if valid) to prevent duplicate leads across different queries
        existing = None
        if lead.whatsapp_number:
            existing = conn.execute(
                "SELECT lead_id, outreach_status, custom_pitch, demo_url, message_1, message_2, followup, dm_sent_at, followup_due_at FROM leads WHERE whatsapp_number = ?",
                (lead.whatsapp_number,)
            ).fetchone()

        if not existing:
            existing = conn.execute(
                "SELECT lead_id, outreach_status, custom_pitch, demo_url, message_1, message_2, followup, dm_sent_at, followup_due_at FROM leads WHERE lead_id = ?",
                (lead.lead_id,)
            ).fetchone()

        target_id = existing["lead_id"] if existing else lead.lead_id

        if existing:
            # Preserve user's manual outreach status and custom edits
            conn.execute("""
                UPDATE leads SET
                    business_name = ?,
                    niche = ?,
                    location = ?,
                    address = COALESCE(NULLIF(?, ''), address),
                    ig_handle_url = ?,
                    current_bio_link = ?,
                    funnel_diagnosis = ?,
                    flaw_detail = ?,
                    whatsapp_number = ?,
                    whatsapp_direct_link = ?,
                    lead_score_num = ?,
                    lead_score = ?,
                    ai_pitch_angle = COALESCE(NULLIF(ai_pitch_angle, ''), ?),
                    message_1 = COALESCE(NULLIF(?, ''), message_1),
                    message_2 = COALESCE(NULLIF(?, ''), message_2),
                    followup = COALESCE(NULLIF(?, ''), followup),
                    demo_url = COALESCE(NULLIF(?, ''), demo_url),
                    source = ?,
                    rating = COALESCE(?, rating),
                    reviews_count = COALESCE(?, reviews_count),
                    maps_url = COALESCE(?, maps_url),
                    updated_at = CURRENT_TIMESTAMP
                WHERE lead_id = ?
            """, (
                lead.business_name, lead.niche, lead.location, lead.address or "",
                lead.ig_handle_url, lead.current_bio_link, lead.funnel_diagnosis.value,
                lead.flaw_detail, lead.whatsapp_number, lead.whatsapp_direct_link,
                lead.lead_score_num, lead.lead_score.value, lead.ai_pitch_angle,
                lead.message_1 or "", lead.message_2 or "", lead.followup or "",
                lead.demo_url or "",
                lead.source, lead.rating, lead.reviews_count, lead.maps_url,
                target_id,
            ))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO leads (
                    lead_id, business_name, niche, location, address, ig_handle_url,
                    current_bio_link, funnel_diagnosis, flaw_detail, whatsapp_number,
                    whatsapp_direct_link, lead_score_num, lead_score, ai_pitch_angle,
                    custom_pitch, message_1, message_2, followup, demo_url,
                    outreach_status, dm_sent_at, followup_due_at, source, rating,
                    reviews_count, maps_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lead.lead_id, lead.business_name, lead.niche, lead.location,
                lead.address or "", lead.ig_handle_url, lead.current_bio_link,
                lead.funnel_diagnosis.value, lead.flaw_detail, lead.whatsapp_number,
                lead.whatsapp_direct_link, lead.lead_score_num, lead.lead_score.value,
                lead.ai_pitch_angle, lead.custom_pitch, lead.message_1, lead.message_2,
                lead.followup, lead.demo_url, lead.outreach_status.value,
                lead.dm_sent_at, lead.followup_due_at, lead.source, lead.rating,
                lead.reviews_count, lead.maps_url,
            ))
            inserted += 1

    conn.commit()
    conn.close()
    return inserted, updated


def get_all_leads(
    min_score: int = 0,
    status: Optional[str] = None,
    diagnosis: Optional[str] = None,
    niche: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "score",
) -> List[Lead]:
    """Retrieves leads with optional filtering and sorting from Turso or local SQLite."""
    conditions = ["lead_score_num >= ?"]
    params: List[Any] = [min_score]

    if status and status.lower() != "all":
        conditions.append("outreach_status = ?")
        params.append(status)

    if diagnosis and diagnosis.lower() != "all":
        conditions.append("funnel_diagnosis = ?")
        params.append(diagnosis)

    if niche and niche.lower() != "all":
        conditions.append("niche LIKE ?")
        params.append(f"%{niche}%")

    if search and search.strip():
        conditions.append("(business_name LIKE ? OR location LIKE ? OR address LIKE ? OR whatsapp_number LIKE ?)")
        s = f"%{search.strip()}%"
        params.extend([s, s, s, s])

    order_clause = "lead_score_num DESC, reviews_count DESC"
    if sort_by == "newest":
        order_clause = "created_at DESC"
    elif sort_by == "reviews":
        order_clause = "reviews_count DESC, rating DESC"
    elif sort_by == "name":
        order_clause = "business_name ASC"

    query = f"SELECT * FROM leads WHERE {' AND '.join(conditions)} ORDER BY {order_clause}"

    if is_turso_configured():
        rows = execute_turso_query(query, params)
    else:
        conn = get_db_connection()
        rows = conn.execute(query, params).fetchall()
        conn.close()

    results = []
    for r in rows:
        lead = Lead(
            lead_id=r["lead_id"],
            business_name=r["business_name"],
            niche=r["niche"],
            location=r["location"] or "",
            address=r["address"] if "address" in r.keys() else "",
            ig_handle_url=r["ig_handle_url"] or "",
            current_bio_link=r["current_bio_link"],
            funnel_diagnosis=FunnelDiagnosis(r["funnel_diagnosis"]),
            flaw_detail=r["flaw_detail"] or "",
            whatsapp_number=r["whatsapp_number"],
            whatsapp_direct_link=r["whatsapp_direct_link"],
            lead_score_num=r["lead_score_num"] or 50,
            lead_score=LeadScoreBucket(r["lead_score"]),
            ai_pitch_angle=r["ai_pitch_angle"] or "",
            custom_pitch=r["custom_pitch"] if "custom_pitch" in r.keys() else None,
            message_1=r["message_1"] if "message_1" in r.keys() else "",
            message_2=r["message_2"] if "message_2" in r.keys() else "",
            followup=r["followup"] if "followup" in r.keys() else "",
            demo_url=r["demo_url"] if "demo_url" in r.keys() else None,
            outreach_status=OutreachStatus(r["outreach_status"]) if r["outreach_status"] in [e.value for e in OutreachStatus] else OutreachStatus.PENDING,
            dm_sent_at=r["dm_sent_at"] if "dm_sent_at" in r.keys() else None,
            followup_due_at=r["followup_due_at"] if "followup_due_at" in r.keys() else None,
            source=r["source"] or "unknown",
            rating=r["rating"],
            reviews_count=r["reviews_count"],
            maps_url=r["maps_url"],
        )
        results.append(lead)
    return results


def update_lead_status(lead_id: str, new_status: str) -> int:
    """Updates outreach status for a lead matching lead_id."""
    if is_turso_configured():
        execute_turso_query(
            "UPDATE leads SET outreach_status = ?, updated_at = CURRENT_TIMESTAMP WHERE lead_id = ?",
            [new_status, lead_id]
        )
        return 1

    conn = get_db_connection()
    count = conn.execute(
        "UPDATE leads SET outreach_status = ?, updated_at = CURRENT_TIMESTAMP WHERE lead_id = ?",
        (new_status, lead_id)
    ).rowcount
    conn.commit()
    conn.close()
    return count


def record_lead_dm_sent(lead_id: str) -> int:
    """Records that Message 1 was sent and sets Day 3 follow-up schedule."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    due = now + timedelta(days=3)

    if is_turso_configured():
        execute_turso_query("""
            UPDATE leads SET
                outreach_status = 'DM Sent',
                dm_sent_at = ?,
                followup_due_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE lead_id = ?
        """, [now.isoformat(), due.isoformat(), lead_id])
        return 1

    conn = get_db_connection()
    count = conn.execute("""
        UPDATE leads SET
            outreach_status = 'DM Sent',
            dm_sent_at = ?,
            followup_due_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE lead_id = ?
    """, (now.isoformat(), due.isoformat(), lead_id)).rowcount
    conn.commit()
    conn.close()
    return count


def update_lead_messages(
    lead_id: str,
    message_1: Optional[str] = None,
    message_2: Optional[str] = None,
    followup: Optional[str] = None,
    demo_url: Optional[str] = None,
) -> int:
    """Updates the 3-step outreach messages for a lead."""
    if is_turso_configured():
        execute_turso_query("""
            UPDATE leads SET
                message_1 = COALESCE(?, message_1),
                message_2 = COALESCE(?, message_2),
                followup = COALESCE(?, followup),
                demo_url = COALESCE(?, demo_url),
                updated_at = CURRENT_TIMESTAMP
            WHERE lead_id = ?
        """, [message_1, message_2, followup, demo_url, lead_id])
        return 1

    conn = get_db_connection()
    count = conn.execute("""
        UPDATE leads SET
            message_1 = COALESCE(?, message_1),
            message_2 = COALESCE(?, message_2),
            followup = COALESCE(?, followup),
            demo_url = COALESCE(?, demo_url),
            updated_at = CURRENT_TIMESTAMP
        WHERE lead_id = ?
    """, (message_1, message_2, followup, demo_url, lead_id)).rowcount
    conn.commit()
    conn.close()
    return count


def update_lead_pitch(
    lead_id: str,
    custom_pitch: str,
    whatsapp_direct_link: Optional[str] = None,
    demo_url: Optional[str] = None,
) -> int:
    """Updates custom pitch and WhatsApp direct link for a lead."""
    if is_turso_configured():
        execute_turso_query("""
            UPDATE leads SET
                custom_pitch = ?,
                whatsapp_direct_link = COALESCE(?, whatsapp_direct_link),
                demo_url = COALESCE(?, demo_url),
                updated_at = CURRENT_TIMESTAMP
            WHERE lead_id = ?
        """, [custom_pitch, whatsapp_direct_link, demo_url, lead_id])
        return 1

    conn = get_db_connection()
    count = conn.execute("""
        UPDATE leads SET
            custom_pitch = ?,
            whatsapp_direct_link = COALESCE(?, whatsapp_direct_link),
            demo_url = COALESCE(?, demo_url),
            updated_at = CURRENT_TIMESTAMP
        WHERE lead_id = ?
    """, (custom_pitch, whatsapp_direct_link, demo_url, lead_id)).rowcount
    conn.commit()
    conn.close()
    return count


def export_to_csv(filepath: Optional[Path] = None, min_score: int = 0) -> Path:
    """Exports all qualified leads to CSV with fallback if locked by Windows Excel."""
    target_path = filepath or DEFAULT_EXPORT_CSV
    leads = get_all_leads(min_score=min_score)

    headers = [
        "Lead_ID",
        "Business_Name",
        "Niche",
        "Address",
        "Rating",
        "Reviews_Count",
        "IG_Handle_URL",
        "Current_Bio_Link",
        "Funnel_Diagnosis",
        "WhatsApp_Number",
        "Lead_Score",
        "AI_Pitch_Angle",
        "Outreach_Status",
        "WhatsApp_Direct_Link",
        "Score_Points",
        "Flaw_Detail",
    ]

    try:
        with open(target_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for lead in leads:
                writer.writerow(lead.to_csv_row())
        return target_path
    except PermissionError:
        # File is locked in Excel, write to a timestamped file so the process doesn't crash
        alt_path = target_path.with_name(f"leads_{int(time.time())}.csv")
        with open(alt_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for lead in leads:
                writer.writerow(lead.to_csv_row())
        return alt_path


def sync_to_google_sheets(
    sheet_name: Optional[str] = None,
    service_account_file: Optional[str] = None,
) -> tuple[bool, str]:
    """Syncs SQLite leads to Google Sheets via gspread if credentials are provided."""
    creds_file = service_account_file or GOOGLE_SERVICE_ACCOUNT_FILE
    target_sheet = sheet_name or GOOGLE_SHEET_NAME

    if not creds_file or not Path(creds_file).exists():
        return False, f"Google Service Account file not found at: '{creds_file}'"

    try:
        import gspread
        gc = gspread.service_account(filename=creds_file)

        try:
            sh = gc.open(target_sheet)
        except gspread.SpreadsheetNotFound:
            sh = gc.create(target_sheet)

        worksheet = sh.get_worksheet(0)
        leads = get_all_leads()

        headers = [
            "Lead_ID", "Business_Name", "Niche", "IG_Handle_URL", "Current_Bio_Link",
            "Funnel_Diagnosis", "WhatsApp_Number", "Lead_Score", "AI_Pitch_Angle",
            "Outreach_Status", "WhatsApp_Direct_Link", "Score_Points", "Flaw_Detail",
        ]

        rows = [headers]
        for lead in leads:
            row_dict = lead.to_csv_row()
            rows.append([str(row_dict.get(h, "")) for h in headers])

        worksheet.clear()
        worksheet.update("A1", rows)
        return True, f"Successfully synced {len(leads)} leads to Google Sheet '{target_sheet}'"
    except Exception as e:
        return False, f"Google Sheets Sync failed: {str(e)}"
