import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# API Keys
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "LeadPulse NG Leads").strip()

# Turso Cloud SQLite (Optional, for persistent cloud hosting on Render)
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "").strip()

# Database & File Paths
DB_PATH = BASE_DIR / "leadpulse.db"
DEFAULT_EXPORT_CSV = BASE_DIR / "leads.csv"

# Request Headers
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# Target Niches & Locations
DEFAULT_NICHES = [
    "Shortlet Apartments",
    "Solar Installation Company",
    "Aesthetics Clinic & Med Spa",
    "Dental Clinic",
    "Fine Dining",
    "Luxury Car Rental",
    "Real Estate Developer",
    "Event Venue & Decor",
]

DEFAULT_NICHE_CONFIGS = {
    "Shortlet Apartments": {
        "label": "Shortlet Apartments",
        "demo_url": "https://shortlet-preview-lagos.vercel.app",
        "demo_features": [
            "browse apartment photos and amenities",
            "see nightly rates and availability",
            "send a direct booking request to WhatsApp with dates and guest count"
        ]
    },
    "Solar Installation": {
        "label": "Solar Installation",
        "demo_url": "https://solar-flow-nigeria.vercel.app",
        "demo_features": [
            "browse inverter and battery packages with estimated prices",
            "calculate energy load requirements for homes or offices",
            "request a free site audit quote directly on WhatsApp"
        ]
    },
    "Aesthetics & Med-Spa": {
        "label": "Aesthetics & Med-Spa",
        "demo_url": "https://glow-aesthetics-preview.vercel.app",
        "demo_features": [
            "see service menu with treatment pricing and details",
            "browse before-and-after skin care packages",
            "request an appointment slot directly to WhatsApp"
        ]
    },
    "Dental Clinic": {
        "label": "Dental Clinic",
        "demo_url": "https://smile-dental-care.vercel.app",
        "demo_features": [
            "browse dental treatments like scaling, whitening and braces",
            "see consultation hours and doctor profiles",
            "book an appointment slot directly to WhatsApp"
        ]
    },
    "Fine Dining": {
        "label": "Fine Dining & Lounges",
        "demo_url": "https://savory-lounge-dining.vercel.app",
        "demo_features": [
            "browse the food and drinks menu",
            "see opening hours and lounge ambience photos",
            "send a table reservation request with party size directly from their phone"
        ]
    }
}

DEFAULT_LOCATIONS = [
    "Lekki Phase 1, Lagos",
    "Victoria Island, Lagos",
    "Ikoyi, Lagos",
    "Ikeja GRA, Lagos",
    "Maitama, Abuja",
    "Wuse 2, Abuja",
]
