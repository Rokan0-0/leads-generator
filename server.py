import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Header, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from leadpulse.auditor import batch_filter_candidates
from leadpulse.config import SERPER_API_KEY
from leadpulse.discovery import PRESET_MAPS_TARGETS, generate_lead_id, search_serper_instagram_dork, search_serper_maps
from leadpulse.enricher import get_pitch_angle, get_pitch_sequence
from leadpulse.models import FunnelDiagnosis, Lead, LeadScoreBucket, OutreachStatus
from leadpulse.parser import generate_whatsapp_pitch_link
from leadpulse.pipeline import execute_lead_pulse
from leadpulse.storage import (
    export_to_csv,
    get_all_leads,
    get_all_settings,
    get_db_connection,
    get_setting,
    record_lead_dm_sent,
    save_leads,
    set_setting,
    update_lead_messages,
    update_lead_pitch,
    update_lead_status,
)

app = FastAPI(title="LeadPulse NG Mobile PWA API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)


class StatusUpdateRequest(BaseModel):
    status: str


class MessagesUpdateRequest(BaseModel):
    message_1: Optional[str] = None
    message_2: Optional[str] = None
    followup: Optional[str] = None


class PitchUpdateRequest(BaseModel):
    custom_pitch: str
    include_demo: bool = True


class SettingsUpdateRequest(BaseModel):
    portfolio_templates: Dict[str, str]
    niche_configs: Optional[Dict[str, Any]] = None
    include_demo_link: bool = True
    access_pin: str = "1234"


class PinVerifyRequest(BaseModel):
    pin: str


class ScrapeRequest(BaseModel):
    niche: Optional[str] = None
    location: Optional[str] = None
    limit: int = 15
    full_sweep: bool = False


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": "LeadPulse NG", "version": "2.0.0"}


@app.post("/api/auth/verify")
async def verify_pin(req: PinVerifyRequest):
    settings = get_all_settings()
    correct_pin = str(settings.get("access_pin", "1234")).strip()
    user_pin = str(req.pin).strip()
    if user_pin == correct_pin:
        return {"valid": True}
    return {"valid": False}


@app.get("/api/settings")
async def get_settings():
    return get_all_settings()


@app.post("/api/settings")
async def save_settings(req: SettingsUpdateRequest):
    set_setting("portfolio_templates", req.portfolio_templates)
    set_setting("include_demo_link", req.include_demo_link)
    set_setting("access_pin", req.access_pin)
    return {"status": "success", "settings": get_all_settings()}


@app.get("/api/leads")
async def list_leads(
    status: Optional[str] = Query("all"),
    diagnosis: Optional[str] = Query("all"),
    niche: Optional[str] = Query("all"),
    search: Optional[str] = Query(""),
    sort_by: str = Query("score"),
    min_score: int = Query(0),
):
    from datetime import datetime, timezone
    leads = get_all_leads(
        min_score=min_score,
        status=status,
        diagnosis=diagnosis,
        niche=niche,
        search=search,
        sort_by=sort_by,
    )

    # Compute overall pipeline counts
    all_raw = get_all_leads(min_score=0)
    counts_by_status = {
        "all": len(all_raw),
        "Pending": sum(1 for l in all_raw if l.outreach_status.value == "Pending"),
        "Preview Built": sum(1 for l in all_raw if l.outreach_status.value == "Preview Built"),
        "DM Sent": sum(1 for l in all_raw if l.outreach_status.value == "DM Sent"),
        "Replied": sum(1 for l in all_raw if l.outreach_status.value == "Replied"),
        "Demo Sent": sum(1 for l in all_raw if l.outreach_status.value == "Demo Sent"),
        "Follow-up Sent": sum(1 for l in all_raw if l.outreach_status.value == "Follow-up Sent"),
        "Closed": sum(1 for l in all_raw if l.outreach_status.value == "Closed"),
    }
    counts_by_diagnosis = {
        "all": len(all_raw),
        "NO_WEBSITE": sum(1 for l in all_raw if l.funnel_diagnosis.value == "NO_WEBSITE"),
        "SOCIAL_OR_WHATSAPP_ONLY": sum(1 for l in all_raw if l.funnel_diagnosis.value == "SOCIAL_OR_WHATSAPP_ONLY"),
        "TRULY_DEAD_DOMAIN": sum(1 for l in all_raw if l.funnel_diagnosis.value == "TRULY_DEAD_DOMAIN"),
    }

    # Extract distinct niches
    niches = sorted(list({l.niche for l in all_raw if l.niche}))

    now_iso = datetime.now(timezone.utc).isoformat()
    leads_data = []
    for l in leads:
        d = l.model_dump()
        # Calculate if followup is due (past followup_due_at and status is DM Sent or Preview Built)
        is_due = False
        if l.followup_due_at and l.outreach_status.value in ["DM Sent", "Preview Built"]:
            is_due = (l.followup_due_at <= now_iso)
        d["is_followup_due"] = is_due
        leads_data.append(d)

    return {
        "leads": leads_data,
        "total": len(leads),
        "counts_by_status": counts_by_status,
        "counts_by_diagnosis": counts_by_diagnosis,
        "niches": niches,
    }


@app.post("/api/leads/{lead_id}/status")
async def update_status(lead_id: str, req: StatusUpdateRequest):
    valid_statuses = [
        "Pending", "Preview Built", "DM Sent", "Replied",
        "Demo Sent", "Follow-up Sent", "Closed"
    ]
    if req.status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status value")

    if req.status == "DM Sent":
        count = record_lead_dm_sent(lead_id)
    else:
        count = update_lead_status(lead_id, req.status)

    if count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"status": "success", "lead_id": lead_id, "new_status": req.status}


@app.post("/api/leads/{lead_id}/messages")
async def save_lead_messages(lead_id: str, req: MessagesUpdateRequest):
    count = update_lead_messages(
        lead_id=lead_id,
        message_1=req.message_1,
        message_2=req.message_2,
        followup=req.followup,
    )
    if count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"status": "success", "lead_id": lead_id}


@app.post("/api/leads/{lead_id}/pitch")
async def save_custom_pitch(lead_id: str, req: PitchUpdateRequest):
    leads = [l for l in get_all_leads() if l.lead_id == lead_id]
    if not leads:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead = leads[0]

    settings = get_all_settings()
    templates = settings.get("portfolio_templates", {})
    demo_url = lead.demo_url
    if not demo_url:
        for n_key, u in templates.items():
            if n_key.lower() in lead.niche.lower() or lead.niche.lower() in n_key.lower():
                demo_url = u
                break

    new_wa_link = generate_whatsapp_pitch_link(
        phone=lead.whatsapp_number,
        business_name=lead.business_name,
        pitch_angle=req.custom_pitch,
        demo_url=demo_url if req.include_demo else None,
    )

    update_lead_pitch(
        lead_id=lead_id,
        custom_pitch=req.custom_pitch,
        whatsapp_direct_link=new_wa_link,
        demo_url=demo_url,
    )

    return {
        "status": "success",
        "lead_id": lead_id,
        "custom_pitch": req.custom_pitch,
        "whatsapp_direct_link": new_wa_link,
    }


@app.post("/api/leads/{lead_id}/regenerate-pitch")
async def regenerate_pitch(lead_id: str):
    leads = [l for l in get_all_leads() if l.lead_id == lead_id]
    if not leads:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead = leads[0]

    settings = get_all_settings()
    niche_configs = settings.get("niche_configs", {})
    templates = settings.get("portfolio_templates", {})
    demo_url = lead.demo_url
    demo_features = None

    for n_key, cfg in niche_configs.items():
        if n_key.lower() in lead.niche.lower() or lead.niche.lower() in n_key.lower():
            if not demo_url:
                demo_url = cfg.get("demo_url")
            demo_features = cfg.get("demo_features")
            break

    if not demo_url:
        for n_key, u in templates.items():
            if n_key.lower() in lead.niche.lower() or lead.niche.lower() in n_key.lower():
                demo_url = u
                break

    seq = get_pitch_sequence(
        business_name=lead.business_name,
        area=lead.location or lead.address or "Lagos",
        category=lead.niche,
        diagnosis=lead.funnel_diagnosis,
        flaw_detail=lead.flaw_detail,
        rating=lead.rating,
        reviews_count=lead.reviews_count,
        demo_url=demo_url or "",
        demo_features=demo_features,
    )

    update_lead_messages(
        lead_id=lead_id,
        message_1=seq["message_1"],
        message_2=seq["message_2"],
        followup=seq["followup"],
        demo_url=demo_url,
    )

    return {
        "status": "success",
        "lead_id": lead_id,
        "sequence": seq,
        "message_1": seq["message_1"],
        "message_2": seq["message_2"],
        "followup": seq["followup"],
    }


@app.get("/api/scrape/stream")
async def stream_scrape(
    niche: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    limit: int = Query(15),
    full_sweep: bool = Query(False),
):
    """Server-Sent Events endpoint to stream live scraping progress to the phone."""
    async def event_generator():
        yield f"data: {json.dumps({'type': 'start', 'message': 'Starting LeadPulse discovery engine...'})}\n\n"
        await asyncio.sleep(0.1)

        raw_candidates: List[dict] = []
        seen_keys = set()

        def add_candidate(c: dict):
            key = (c.get("name", "").strip().lower(), c.get("phone", "").strip())
            if key not in seen_keys:
                seen_keys.add(key)
                raw_candidates.append(c)

        if full_sweep or not niche:
            yield f"data: {json.dumps({'type': 'step', 'step': 'maps', 'message': f'Querying {len(PRESET_MAPS_TARGETS)} high-ticket categories across Lagos & Abuja...'})}\n\n"
            for query_str, cat_niche, cat_loc in PRESET_MAPS_TARGETS:
                maps_results = search_serper_maps(query_str, cat_niche, cat_loc, limit=10)
                for r in maps_results:
                    add_candidate(r)
                yield f"data: {json.dumps({'type': 'progress', 'candidates_count': len(raw_candidates), 'message': f'Scraped {query_str} ({len(maps_results)} found)'})}\n\n"
                await asyncio.sleep(0.05)

            yield f"data: {json.dumps({'type': 'step', 'step': 'ig', 'message': 'Dorking Instagram profiles with Nigerian phone numbers...'})}\n\n"
            ig_results = search_serper_instagram_dork(limit=25)
            for r in ig_results:
                add_candidate(r)
            yield f"data: {json.dumps({'type': 'progress', 'candidates_count': len(raw_candidates), 'message': f'Found {len(ig_results)} IG candidates'})}\n\n"
        else:
            loc = location or "Lagos, Nigeria"
            maps_msg = f"Searching Google Maps for '{niche}' in '{loc}'..."
            yield f"data: {json.dumps({'type': 'step', 'step': 'maps', 'message': maps_msg})}\n\n"
            if SERPER_API_KEY:
                maps_results = search_serper_maps(f"{niche} in {loc}", niche, loc, limit=limit)
                for r in maps_results:
                    add_candidate(r)
                yield f"data: {json.dumps({'type': 'progress', 'candidates_count': len(raw_candidates), 'message': f'Found {len(maps_results)} Google Maps listings'})}\n\n"

                ig_msg = f"Dorking Instagram profiles for '{niche}'..."
                yield f"data: {json.dumps({'type': 'step', 'step': 'ig', 'message': ig_msg})}\n\n"
                custom_dork = f'site:instagram.com {loc} {niche} (080 OR 081 OR 090 OR 070 OR 091 OR 234 OR wa.me)'
                ig_results = search_serper_instagram_dork(query_str=custom_dork, niche=niche, location=loc, limit=limit)
                for r in ig_results:
                    add_candidate(r)
                yield f"data: {json.dumps({'type': 'progress', 'candidates_count': len(raw_candidates), 'message': f'Found {len(ig_results)} Instagram profiles'})}\n\n"

        if not raw_candidates:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No candidates found for this query.'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'step', 'step': 'audit', 'message': f'Applying Golden Filter across {len(raw_candidates)} candidates concurrently...'})}\n\n"
        kept_raw = await batch_filter_candidates(raw_candidates, concurrency=15)

        discarded = len(raw_candidates) - len(kept_raw)
        yield f"data: {json.dumps({'type': 'step', 'step': 'filtered', 'message': f'{len(kept_raw)} QUALIFIED leads found ({discarded} discarded with working sites or invalid numbers)'})}\n\n"

        if not kept_raw:
            yield f"data: {json.dumps({'type': 'complete', 'new_leads': 0, 'message': 'All candidates had working websites or lacked valid Nigerian numbers.'})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'step', 'step': 'pitching', 'message': f'Crafting personalized pitches with Gemini AI for {len(kept_raw)} leads...'})}\n\n"

        settings = get_all_settings()
        templates = settings.get("portfolio_templates", {})
        include_demo = settings.get("include_demo_link", True)
        processed_leads: List[Lead] = []

        for item, diagnosis, flaw_detail, phone, score in kept_raw:
            biz_name = item.get("name", "Unknown Business")
            biz_niche = item.get("niche", niche or "Local Business")
            biz_location = item.get("location", location or "Lagos, Nigeria")
            biz_address = item.get("address", "")
            rating = item.get("rating")
            reviews = item.get("reviews")

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

        inserted, updated = save_leads(processed_leads)
        export_to_csv()

        yield f"data: {json.dumps({'type': 'complete', 'new_leads': inserted, 'updated_leads': updated, 'total_qualified': len(processed_leads), 'message': f'Done! Added {inserted} new hot leads.'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/export/csv")
async def download_csv():
    csv_path = export_to_csv()
    return FileResponse(
        path=csv_path,
        media_type="text/csv",
        filename="leads.csv",
    )


# Serve Static PWA files
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting LeadPulse NG PWA Server on http://0.0.0.0:8000")
    print("📱 On your phone, connect to your computer's IP address on port 8000 (e.g. http://192.168.1.X:8000)\n")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
