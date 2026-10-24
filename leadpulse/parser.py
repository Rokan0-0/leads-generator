import re
import urllib.parse
from typing import Optional, Tuple

# Regex to detect Nigerian phone numbers in bios, strings, URLs, and wa.me links
# Formats: 080..., 070..., 090..., 091..., 081..., +234..., 234...
NG_PHONE_REGEX = re.compile(
    r"(?:(?:\+?234[\s\-]?)|(?:0))([789][01]\d[\s\-]?\d{3}[\s\-]?\d{4})",
    re.IGNORECASE
)

WA_LINK_REGEX = re.compile(
    r"(?:wa\.me/(?:send\?phone=)?|api\.whatsapp\.com/send\?(?:.*&)?phone=)(234[789][01]\d{8}|0[789][01]\d{8})",
    re.IGNORECASE
)


def extract_nigerian_phone(text: Optional[str]) -> Optional[str]:
    """Extracts and normalizes a Nigerian phone number to +234... format."""
    if not text:
        return None

    # First check for direct wa.me link patterns
    wa_match = WA_LINK_REGEX.search(text)
    if wa_match:
        digits = re.sub(r"\D", "", wa_match.group(1))
        if digits.startswith("0"):
            digits = "234" + digits[1:]
        if len(digits) == 13 and digits.startswith("234"):
            return f"+{digits}"

    # General regex search
    match = NG_PHONE_REGEX.search(text)
    if match:
        cleaned = re.sub(r"\D", "", match.group(0))
        if cleaned.startswith("0"):
            cleaned = "234" + cleaned[1:]
        elif cleaned.startswith("234"):
            pass
        elif len(cleaned) == 10 and cleaned[0] in "789":
            cleaned = "234" + cleaned

        if len(cleaned) == 13 and cleaned.startswith("234"):
            return f"+{cleaned}"

    return None


def generate_whatsapp_pitch_link(
    phone: Optional[str],
    business_name: str,
    pitch_angle: str = "",
    demo_url: Optional[str] = None,
) -> Optional[str]:
    """Generates a direct, clickable WhatsApp link with pre-filled cold outreach text."""
    if not phone:
        return None

    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None

    if digits.startswith("0"):
        digits = "234" + digits[1:]

    # Use the personalized pitch angle if provided, otherwise use a high-converting hook
    if pitch_angle and pitch_angle.strip():
        clean_pitch = pitch_angle.strip()
        # If the pitch does not start with a greeting or business name, prepend it
        if not (clean_pitch.lower().startswith("hi ") or clean_pitch.lower().startswith("hello ")):
            msg = f"Hi {business_name}, {clean_pitch}"
        else:
            msg = clean_pitch
    else:
        msg = (
            f"Hi {business_name}, I was looking through your online presence and noticed "
            f"a quick opportunity to boost your bookings/inquiries. "
            f"I put together a quick solution preview for you—can I send it over?"
        )

    # Append niche demo portfolio link if provided
    if demo_url and demo_url.strip():
        msg += f"\n\nHere is a quick sample preview of what we can build for you: {demo_url.strip()}"

    encoded_msg = urllib.parse.quote(msg)
    return f"https://wa.me/{digits}?text={encoded_msg}"
