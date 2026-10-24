import hashlib
import json
import re
from typing import Any, List, Optional, Tuple
import requests

from .config import DEFAULT_USER_AGENT, GOOGLE_API_KEY, SERPER_API_KEY
from .models import Lead
from .parser import extract_nigerian_phone

IG_HANDLE_REGEX = re.compile(r"instagram\.com/([a-zA-Z0-9_\.]+)", re.IGNORECASE)
URL_EXTRACT_REGEX = re.compile(r"(https?://[^\s\)]+)", re.IGNORECASE)

# Prescribed high-ticket categories across Lagos & Abuja
PRESET_MAPS_TARGETS = [
    ("Shortlet apartment Lekki Lagos", "Shortlet Apartments", "Lekki, Lagos"),
    ("Serviced apartments Victoria Island", "Shortlet Apartments", "Victoria Island, Lagos"),
    ("Shortlet Ikoyi", "Shortlet Apartments", "Ikoyi, Lagos"),
    ("Shortlet Wuse Abuja", "Shortlet Apartments", "Wuse 2, Abuja"),
    ("Solar energy company Lagos", "Solar Installation", "Lagos"),
    ("Inverter installation Lekki", "Solar Installation", "Lekki, Lagos"),
    ("Solar installer Abuja", "Solar Installation", "Abuja"),
    ("Med spa Victoria Island", "Med-Spa & Aesthetics", "Victoria Island, Lagos"),
    ("Aesthetics clinic Lekki", "Med-Spa & Aesthetics", "Lekki, Lagos"),
    ("Dental clinic Lekki Phase 1", "Dental Clinic", "Lekki Phase 1, Lagos"),
    ("Fine dining restaurant Victoria Island", "Fine Dining", "Victoria Island, Lagos"),
]


def generate_lead_id(name: str, niche: str, location: str) -> str:
    """Generates a stable unique hash ID for the lead."""
    raw = f"{name.lower().strip()}_{niche.lower().strip()}_{location.lower().strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def clean_ig_title(title: str) -> Tuple[str, str]:
    """Cleans Instagram snippet title into (Business Name, Handle)."""
    handle = ""
    handle_match = re.search(r"\(@([a-zA-Z0-9_\.]+)\)", title)
    if handle_match:
        handle = handle_match.group(1)

    name = re.sub(r"•\s*Instagram.*$", "", title, flags=re.IGNORECASE)
    name = re.sub(r"\(@[a-zA-Z0-9_\.]+\)", "", name)
    name = name.strip(" -|:")
    return name or "Instagram Business", handle


def search_serper_maps(
    query: str,
    niche: str,
    location: str,
    limit: int = 20,
) -> List[dict]:
    """
    Engine A: Queries Google Maps / Places via Serper /maps API.
    Returns real Google Maps business cards with name, address, phone, website, rating, ratingCount.
    """
    if not SERPER_API_KEY:
        return []

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    body = {
        "q": query,
        "location": "Nigeria",
    }

    try:
        # First try /maps endpoint
        resp = requests.post("https://google.serper.dev/maps", json=body, headers=headers, timeout=20)
        if resp.status_code != 200:
            # Fallback to /places endpoint
            resp = requests.post("https://google.serper.dev/places", json=body, headers=headers, timeout=20)

        if resp.status_code == 200:
            data = resp.json()
            places = data.get("places", [])
            results = []
            for p in places:
                name = p.get("title", "Unknown Business")
                cid = p.get("cid")
                maps_url = f"https://www.google.com/maps?cid={cid}" if cid else ""
                phone = p.get("phoneNumber") or ""
                website = p.get("website") or ""
                rating = p.get("rating")
                rating_count = p.get("ratingCount") or 0

                results.append({
                    "name": name,
                    "niche": niche,
                    "location": location,
                    "ig_handle_url": "",
                    "bio_link": website,
                    "website": website,
                    "phone": phone,
                    "rating": rating,
                    "reviews": rating_count,
                    "maps_url": maps_url,
                    "address": p.get("address", ""),
                    "source": "serper_maps",
                })
            return results[:limit]
    except Exception as e:
        print(f"[Warning] Serper Maps error for '{query}': {e}")

    return []


def search_serper_instagram_dork(
    query_str: Optional[str] = None,
    niche: str = "Local Business",
    location: str = "Lagos, Nigeria",
    limit: int = 20,
) -> List[dict]:
    """
    Engine B: Queries active Instagram businesses with Nigerian phone numbers via Serper /search.
    Default query: site:instagram.com ("shortlet" OR "solar" OR "medspa" OR "dental") ...
    """
    if not SERPER_API_KEY:
        return []

    if not query_str:
        query_str = (
            'site:instagram.com (shortlet OR solar OR medspa OR dental) '
            '(Lekki OR "Victoria Island" OR Ikoyi OR Abuja) '
            '(080 OR 081 OR 090 OR 070 OR 091 OR 234 OR wa.me)'
        )

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }

    results = []
    pages_to_fetch = max(1, min((limit + 9) // 10, 4))

    for page in range(1, pages_to_fetch + 1):
        body = {
            "q": query_str,
            "page": page,
        }
        try:
            resp = requests.post("https://google.serper.dev/search", json=body, headers=headers, timeout=20)
            if resp.status_code != 200:
                break
            data = resp.json()
            raw_items = data.get("organic", [])

            for item in raw_items:
                link = item.get("link", "")
                if "instagram.com" not in link or "/p/" in link or "/reel/" in link:
                    continue

                title = item.get("title", "")
                snippet = item.get("snippet", "")
                biz_name, handle = clean_ig_title(title)

                # Extract bio link from snippet
                extracted_urls = URL_EXTRACT_REGEX.findall(snippet)
                bio_link = None
                for u in extracted_urls:
                    if "instagram.com" not in u:
                        bio_link = u
                        break

                phone = extract_nigerian_phone(snippet)

                # Determine niche from snippet or title
                detected_niche = niche
                text_lower = (title + " " + snippet).lower()
                if "shortlet" in text_lower or "apartment" in text_lower or "airbnb" in text_lower:
                    detected_niche = "Shortlet Apartments"
                elif "solar" in text_lower or "inverter" in text_lower:
                    detected_niche = "Solar Installation"
                elif "medspa" in text_lower or "aesthetic" in text_lower or "facial" in text_lower:
                    detected_niche = "Med-Spa & Aesthetics"
                elif "dental" in text_lower or "dentist" in text_lower or "teeth" in text_lower:
                    detected_niche = "Dental Clinic"

                # Determine location
                detected_loc = location
                if "lekki" in text_lower:
                    detected_loc = "Lekki, Lagos"
                elif "victoria island" in text_lower or " vi " in text_lower:
                    detected_loc = "Victoria Island, Lagos"
                elif "ikoyi" in text_lower:
                    detected_loc = "Ikoyi, Lagos"
                elif "abuja" in text_lower or "wuse" in text_lower or "maitama" in text_lower:
                    detected_loc = "Abuja"

                results.append({
                    "name": biz_name,
                    "niche": detected_niche,
                    "location": detected_loc,
                    "ig_handle_url": link,
                    "bio_link": bio_link,
                    "website": bio_link,
                    "phone": phone,
                    "snippet": snippet,
                    "source": "serper_instagram",
                })

            if len(results) >= limit:
                break
        except Exception as e:
            print(f"[Warning] Serper search error: {e}")
            break

    return results[:limit]
