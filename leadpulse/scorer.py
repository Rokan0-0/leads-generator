from typing import Optional
from .models import FunnelDiagnosis, LeadScoreBucket


def calculate_lead_score(
    diagnosis: FunnelDiagnosis,
    flaw_detail: str = "",
    niche: str = "",
    reviews_count: Optional[int] = None,
    has_phone: bool = True,
) -> tuple[int, LeadScoreBucket]:
    """
    Calculates vulnerability score according to the Golden Filter:
    - NO_WEBSITE: 100 (High)
    - SOCIAL_OR_WHATSAPP_ONLY: 95 (High)
    - TRULY_DEAD_DOMAIN: 90 (High)
    """
    if diagnosis == FunnelDiagnosis.NO_WEBSITE:
        score = 100
    elif diagnosis == FunnelDiagnosis.SOCIAL_OR_WHATSAPP_ONLY:
        score = 95
    elif diagnosis == FunnelDiagnosis.TRULY_DEAD_DOMAIN:
        score = 90
    else:
        score = 80

    return score, LeadScoreBucket.HIGH

