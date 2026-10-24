import json
import re
from typing import Any, Dict, List, Optional
import httpx
from .config import GEMINI_API_KEY
from .models import FunnelDiagnosis


def generate_rule_based_sequence(
    business_name: str,
    area: str,
    category: str,
    diagnosis: FunnelDiagnosis,
    flaw_detail: str,
    rating: Optional[float] = None,
    reviews_count: Optional[int] = None,
    demo_url: str = "",
    demo_features: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Fallback generator strictly following the Lagos web developer outreach rules."""
    short_name = business_name.strip()
    clean_area = area.replace("Nigeria", "").replace(", Lagos", "").replace(", Abuja", "").strip(" ,")
    
    # Review proof string
    proof_str = ""
    if reviews_count:
        if clean_area:
            proof_str = f"{reviews_count}+ reviews on Google Maps in {clean_area}"
        else:
            proof_str = f"{reviews_count}+ reviews on Google Maps"
    elif clean_area:
        proof_str = f"a great local presence in {clean_area}"
    else:
        proof_str = "an active local profile"

    # Niche action & features
    cat_lower = category.lower()
    if "restaurant" in cat_lower or "dining" in cat_lower or "lounge" in cat_lower:
        action = "see your menu and book a table"
        cat_display = "restaurants and lounges"
        default_features = "browse the menu, see opening hours and send a table request from their phone"
    elif "shortlet" in cat_lower or "apartment" in cat_lower:
        action = "view photos, check availability and book dates"
        cat_display = "shortlet apartments"
        default_features = "browse apartment photos, check calendar dates and send a reservation request from their phone"
    elif "solar" in cat_lower or "inverter" in cat_lower:
        action = "see your packages and request an installation quote"
        cat_display = "solar installers"
        default_features = "view inverter packages, check estimated pricing and request a site audit from their phone"
    elif "spa" in cat_lower or "aesthetic" in cat_lower or "med" in cat_lower:
        action = "see treatments, prices and book appointments"
        cat_display = "aesthetics clinics and spas"
        default_features = "browse your service menu, check treatment prices and book an appointment from their phone"
    elif "dental" in cat_lower or "dentist" in cat_lower:
        action = "browse services and book a consultation"
        cat_display = "dental clinics"
        default_features = "browse dental services, check opening hours and book an appointment from their phone"
    else:
        action = "see your services and book directly"
        cat_display = category.lower()
        default_features = "browse services, see pricing and send an inquiry from their phone"

    features_text = ", ".join(demo_features) if demo_features else default_features

    # Message 1: at most 2 sentences, no links, ends with easy question
    msg_1 = (
        f"Hi {short_name} team, I saw you have {proof_str} but no website for guests to {action}. "
        f"I made a sample site for {cat_display}—want me to send it over?"
    )

    # Message 2: includes demo URL, describes features, ends with branding question
    demo_link = demo_url if demo_url else "https://preview-site.vercel.app"
    msg_2 = (
        f"Here’s the sample: {demo_link}. "
        f"It’s a demo, but guests can {features_text}. "
        f"If you like it, I can set one up with {short_name}’s logo and photos, with no setup cost. Want me to?"
    )

    # Follow-up (day 3): short, polite, offers video or screenshot, easy way out
    msg_followup = (
        f"Hi, following up on the sample site for {short_name}. No pressure at all. "
        f"If it’s useful I can send a short video of how it works. Just say yes."
    )

    return {
        "message_1": msg_1,
        "message_2": msg_2,
        "followup": msg_followup,
    }


def generate_gemini_pitch_sequence(
    business_name: str,
    area: str,
    category: str,
    diagnosis: FunnelDiagnosis,
    flaw_detail: str,
    rating: Optional[float] = None,
    reviews_count: Optional[int] = None,
    demo_url: str = "",
    demo_features: Optional[List[str]] = None,
) -> Optional[Dict[str, str]]:
    """Generates the 3-part outreach sequence using Gemini API strictly enforcing user rules."""
    if not GEMINI_API_KEY:
        return None

    clean_area = area.replace("Nigeria", "").strip(" ,")
    features_list = demo_features or [
        "browse services and photos",
        "check opening hours and availability",
        "send a direct inquiry to WhatsApp"
    ]
    features_json = json.dumps(features_list)

    system_instruction = (
        "You write WhatsApp outreach messages from a Lagos web developer to small business owners.\n"
        "You receive: the lead's data (name, area, category, rating, reviews) and a niche config.\n\n"
        'Return JSON: {"message_1": "...", "message_2": "...", "followup": "..."}\n\n'
        "Rules:\n"
        "- Tell it to use 'I' and never 'we'.\n"
        "- message_1: at most TWO sentences. Greet using the business name (e.g. 'Hi {business_name} team,'). "
        "One specific hook from the lead data (reviews and area). State the niche-specific benefit. End with one easy question (e.g. 'Want me to send it over?'). NO links.\n"
        f"- message_2 (after they say yes): include the demo URL '{demo_url}' and describe it as a sample for their type of business. "
        f"MUST ONLY describe features listed in this niche config: {features_json}. "
        f"Must end with: 'If you like it, I can set one up with {business_name}’s logo and photos, with no setup cost. Want me to?'. Total 2 to 3 sentences.\n"
        f"- followup (day 3): 1 to 2 sentences, short, polite, and offers one new thing (a short video or screenshot of how it works) with an easy way out ('No pressure at all... Just say yes').\n"
        "- Plain, friendly English. No hype, no emojis (max one), no 'guaranteed', no ranking promises, no fake claims about having built something for them.\n"
        "- Use only facts present in the lead data. If something is missing, don't invent it.\n"
        "- Never mention AI.\n"
    )

    lead_payload = {
        "name": business_name,
        "area": clean_area or "Lagos",
        "category": category,
        "rating": rating,
        "reviews": reviews_count,
        "flaw": diagnosis.value,
        "demo_url": demo_url,
        "allowed_demo_features": features_list
    }

    prompt = (
        f"{system_instruction}\n\n"
        f"Lead Data:\n{json.dumps(lead_payload, indent=2)}\n\n"
        f"Respond ONLY with the JSON object."
    )

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash"]
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        try:
            with httpx.Client(timeout=12.0) as client:
                resp = client.post(
                    url,
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.5,
                            "responseMimeType": "application/json",
                            "maxOutputTokens": 400,
                        },
                    },
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            raw_text = parts[0].get("text", "").strip()
                            # Parse JSON
                            parsed = json.loads(raw_text)
                            if "message_1" in parsed and "message_2" in parsed and "followup" in parsed:
                                return parsed
        except Exception:
            continue

    return None


def get_pitch_sequence(
    business_name: str,
    area: str,
    category: str,
    diagnosis: FunnelDiagnosis,
    flaw_detail: str,
    rating: Optional[float] = None,
    reviews_count: Optional[int] = None,
    demo_url: str = "",
    demo_features: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Gets the 3-step outreach sequence via Gemini API, falling back to rule-based sequence."""
    if GEMINI_API_KEY:
        ai_seq = generate_gemini_pitch_sequence(
            business_name=business_name,
            area=area,
            category=category,
            diagnosis=diagnosis,
            flaw_detail=flaw_detail,
            rating=rating,
            reviews_count=reviews_count,
            demo_url=demo_url,
            demo_features=demo_features,
        )
        if ai_seq:
            return ai_seq

    return generate_rule_based_sequence(
        business_name=business_name,
        area=area,
        category=category,
        diagnosis=diagnosis,
        flaw_detail=flaw_detail,
        rating=rating,
        reviews_count=reviews_count,
        demo_url=demo_url,
        demo_features=demo_features,
    )


# Backwards compatibility helper
def get_pitch_angle(
    business_name: str,
    niche: str,
    diagnosis: FunnelDiagnosis,
    flaw_detail: str,
    rating: Optional[float] = None,
    reviews_count: Optional[int] = None,
    bio_text: str = "",
) -> str:
    seq = get_pitch_sequence(
        business_name=business_name,
        area="Lagos",
        category=niche,
        diagnosis=diagnosis,
        flaw_detail=flaw_detail,
        rating=rating,
        reviews_count=reviews_count,
    )
    return seq["message_1"]
