import asyncio
import sys
import time
from typing import List, Optional
from rich.console import Console
from rich.table import Table

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from .auditor import batch_filter_candidates
from .config import GOOGLE_API_KEY, SERPER_API_KEY
from .discovery import PRESET_MAPS_TARGETS, generate_lead_id, search_serper_instagram_dork, search_serper_maps
from .enricher import get_pitch_angle, get_pitch_sequence
from .models import FunnelDiagnosis, Lead, LeadScoreBucket, OutreachStatus
from .parser import generate_whatsapp_pitch_link
from .storage import export_to_csv, get_all_settings, save_leads, sync_to_google_sheets

console = Console(legacy_windows=False)


async def execute_lead_pulse(
    niche: Optional[str] = None,
    location: Optional[str] = None,
    limit: int = 20,
    full_sweep: bool = False,
) -> List[Lead]:
    """
    Executes the Dual-Engine Discovery & Golden Filter LeadPulse pipeline:
    1. Engine A: Google Maps via Serper /maps API
    2. Engine B: Instagram Dorks with Nigerian phone numbers via Serper /search API
    3. The Golden Filter: Discards working websites; keeps only NO_WEBSITE, SOCIAL_OR_WHATSAPP_ONLY, TRULY_DEAD_DOMAIN
    4. Gemini Flash AI: Generates hyper-personalized cold outreach hook referencing exact Google Maps rating/reviews
    5. Storage: SQLite persistence + exact 10-column CSV export
    """
    console.print(f"\n[bold cyan]⚡ LeadPulse NG - Dual-Engine High-Ticket Auditor Starting...[/bold cyan]")

    raw_candidates: List[dict] = []
    seen_keys = set()

    def add_candidate(c: dict):
        # Deduplicate candidates by name and location
        key = (c.get("name", "").strip().lower(), c.get("phone", "").strip())
        if key not in seen_keys:
            seen_keys.add(key)
            raw_candidates.append(c)

    if full_sweep or not niche:
        console.print("[bold yellow]🚀 Running Full Sweep across High-Ticket Lagos & Abuja Categories...[/bold yellow]")

        # Engine A: Preset High-Ticket Google Maps searches
        console.print(f"📍 Querying {len(PRESET_MAPS_TARGETS)} high-ticket Google Maps categories via Serper /maps...")
        for query_str, cat_niche, cat_loc in PRESET_MAPS_TARGETS:
            maps_results = search_serper_maps(query_str, cat_niche, cat_loc, limit=15)
            for r in maps_results:
                add_candidate(r)
        console.print(f"   ✓ Discovered {len(raw_candidates)} total candidates from Google Maps")

        # Engine B: Instagram Dorks with Nigerian phone numbers
        console.print("🔍 Dorking active Instagram businesses with Nigerian numbers via Serper /search...")
        ig_results = search_serper_instagram_dork(limit=30)
        for r in ig_results:
            add_candidate(r)
        console.print(f"   ✓ Discovered {len(ig_results)} candidates from Instagram dorks")

    else:
        # Targeted search for user-specified niche & location
        loc = location or "Lagos, Nigeria"
        console.print(f"🎯 Target Niche: [bold green]{niche}[/bold green] | Location: [bold green]{loc}[/bold green]")

        # Engine A: Google Maps
        if SERPER_API_KEY:
            console.print(f"📍 Searching Google Maps listings via Serper /maps for '{niche} in {loc}'...")
            maps_results = search_serper_maps(f"{niche} in {loc}", niche, loc, limit=limit)
            console.print(f"   ✓ Found {len(maps_results)} Google Maps candidates")
            for r in maps_results:
                add_candidate(r)

        # Engine B: Instagram
        if SERPER_API_KEY:
            console.print(f"🔍 Dorking Instagram profiles for '{niche}' in '{loc}'...")
            custom_dork = f'site:instagram.com {loc} {niche} (080 OR 081 OR 090 OR 070 OR 091 OR 234 OR wa.me)'
            ig_results = search_serper_instagram_dork(query_str=custom_dork, niche=niche, location=loc, limit=limit)
            console.print(f"   ✓ Found {len(ig_results)} Instagram candidates")
            for r in ig_results:
                add_candidate(r)

    total_candidates = len(raw_candidates)
    if not total_candidates:
        console.print("[bold yellow]⚠️ No candidates discovered from live HTTP search results for this query.[/bold yellow]")
        return []

    console.print(f"\n[bold]Applying The Golden Filter on {total_candidates} raw candidates...[/bold]")
    console.print("[dim]Checking website fields, verifying Nigerian mobile numbers, and discarding working sites...[/dim]")

    start_audit = time.time()
    # Apply The Golden Filter
    kept_raw = await batch_filter_candidates(raw_candidates, concurrency=15)
    audit_time = round(time.time() - start_audit, 2)

    discarded_count = total_candidates - len(kept_raw)
    console.print(
        f"⚡ Filtered {total_candidates} candidates in [bold green]{audit_time}s[/bold green]: "
        f"[bold green]{len(kept_raw)} QUALIFIED[/bold green] (discarded {discarded_count} working sites or invalid numbers)"
    )

    if not kept_raw:
        console.print("[yellow]All inspected candidates had working websites or lacked valid Nigerian mobile phones.[/yellow]")
        return []

    # Process ONLY the kept, high-score leads through Gemini API
    console.print(f"\n[bold]Generating personalized sales pitches with Gemini 2.5 Flash for {len(kept_raw)} leads...[/bold]")
    processed_leads: List[Lead] = []

    settings = get_all_settings()
    templates = settings.get("portfolio_templates", {})
    include_demo = settings.get("include_demo_link", True)

    for item, diagnosis, flaw_detail, phone, score in kept_raw:
        biz_name = item.get("name", "Unknown Business")
        biz_niche = item.get("niche", niche or "Local Business")
        biz_location = item.get("location", location or "Lagos, Nigeria")
        biz_address = item.get("address", "")
        rating = item.get("rating")
        reviews = item.get("reviews")

        # Find matching niche demo template url & demo features
        niche_configs = settings.get("niche_configs", {})
        demo_url = None
        demo_features = None
        for n_key, cfg in niche_configs.items():
            if n_key.lower() in biz_niche.lower() or biz_niche.lower() in n_key.lower():
                demo_url = cfg.get("demo_url")
                demo_features = cfg.get("demo_features")
                break

        if not demo_url:
            for n_key, u in templates.items():
                if n_key.lower() in biz_niche.lower() or biz_niche.lower() in n_key.lower():
                    demo_url = u
                    break

        # Generate the strict 3-message sequence via Gemini
        seq = get_pitch_sequence(
            business_name=biz_name,
            area=biz_location,
            category=biz_niche,
            diagnosis=diagnosis,
            flaw_detail=flaw_detail,
            rating=rating,
            reviews_count=reviews,
            demo_url=demo_url or "",
            demo_features=demo_features,
        )

        pitch_angle = seq["message_1"]

        # Generate 1-click WhatsApp Outreach Link (Message 1 has NO links)
        wa_link = generate_whatsapp_pitch_link(
            phone=phone,
            business_name=biz_name,
            pitch_angle=pitch_angle,
            demo_url=None,
        )

        lead_id = generate_lead_id(biz_name, biz_niche, biz_location)

        lead = Lead(
            lead_id=lead_id,
            business_name=biz_name,
            niche=biz_niche,
            location=biz_location,
            address=biz_address,
            ig_handle_url=item.get("ig_handle_url", ""),
            current_bio_link=item.get("bio_link") or item.get("website"),
            funnel_diagnosis=diagnosis,
            flaw_detail=flaw_detail,
            whatsapp_number=phone,
            whatsapp_direct_link=wa_link,
            lead_score_num=score,
            lead_score=LeadScoreBucket.HIGH,
            ai_pitch_angle=pitch_angle,
            message_1=seq["message_1"],
            message_2=seq["message_2"],
            followup=seq["followup"],
            demo_url=demo_url,
            outreach_status=OutreachStatus.PENDING,
            source=item.get("source", "search"),
            rating=rating,
            reviews_count=reviews,
            maps_url=item.get("maps_url"),
        )
        processed_leads.append(lead)

    # Sort leads by score descending (100 -> 95 -> 90) then by review count descending
    processed_leads.sort(key=lambda x: (x.lead_score_num, x.reviews_count or 0), reverse=True)

    # Save to SQLite database
    inserted, updated = save_leads(processed_leads)
    console.print(f"💾 Persisted to SQLite database ([bold green]+{inserted} new, {updated} updated[/bold green])")

    # Export qualified leads to exact PRD 10-column CSV
    csv_path = export_to_csv()
    console.print(f"📄 Exported qualified leads to [bold underline green]{csv_path}[/bold underline green]")

    # Optional Google Sheets Sync
    synced, sheet_msg = sync_to_google_sheets()
    if synced:
        console.print(f"☁ [green]{sheet_msg}[/green]")

    return processed_leads


def display_leads_table(leads: List[Lead]):
    """Renders a beautiful summary table in terminal using Rich."""
    table = Table(title="🔥 LeadPulse NG - Qualified High-Ticket Leads (Golden Filter)", header_style="bold magenta")

    table.add_column("Score", justify="center", style="bold cyan")
    table.add_column("Business Name", style="bold white", max_width=25)
    table.add_column("Niche", style="green", max_width=18)
    table.add_column("Funnel Flaw", style="red", max_width=22)
    table.add_column("WhatsApp", style="bold yellow", max_width=15)
    table.add_column("AI Pitch Angle", style="dim white", max_width=45)

    for lead in leads[:25]:
        score_label = f"{lead.lead_score_num} (High)"
        flaw_display = f"{lead.funnel_diagnosis.value}\n{lead.flaw_detail[:35]}"
        table.add_row(
            score_label,
            lead.business_name,
            lead.niche,
            flaw_display,
            lead.whatsapp_number or "None",
            lead.ai_pitch_angle,
        )

    console.print("\n", table)
