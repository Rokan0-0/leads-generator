from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class FunnelDiagnosis(str, Enum):
    NO_WEBSITE = "NO_WEBSITE"                          # Missing website on Google Maps / IG bio (Score 100)
    SOCIAL_OR_WHATSAPP_ONLY = "SOCIAL_OR_WHATSAPP_ONLY" # Website button points to IG, WhatsApp, Linktree, TikTok, etc. (Score 95)
    TRULY_DEAD_DOMAIN = "TRULY_DEAD_DOMAIN"            # Custom domain returns DNS failure, connection refused, or 404/500 (Score 90)


class LeadScoreBucket(str, Enum):
    HIGH = "High"      # >= 80
    MEDIUM = "Medium"  # 60 - 79
    LOW = "Low"        # < 60


class OutreachStatus(str, Enum):
    PENDING = "Pending"
    PREVIEW_BUILT = "Preview Built"
    DM_SENT = "DM Sent"
    REPLIED = "Replied"
    DEMO_SENT = "Demo Sent"
    FOLLOWUP_SENT = "Follow-up Sent"
    CLOSED = "Closed"


class Lead(BaseModel):
    lead_id: str = Field(..., description="Unique hash / identifier for lead")
    business_name: str
    niche: str
    location: str = ""
    address: Optional[str] = ""
    ig_handle_url: str = ""
    current_bio_link: Optional[str] = None
    funnel_diagnosis: FunnelDiagnosis = FunnelDiagnosis.NO_WEBSITE
    flaw_detail: str = ""
    whatsapp_number: Optional[str] = None
    whatsapp_direct_link: Optional[str] = None
    lead_score_num: int = 100
    lead_score: LeadScoreBucket = LeadScoreBucket.HIGH
    ai_pitch_angle: str = ""
    custom_pitch: Optional[str] = None
    message_1: Optional[str] = ""
    message_2: Optional[str] = ""
    followup: Optional[str] = ""
    demo_url: Optional[str] = None
    outreach_status: OutreachStatus = OutreachStatus.PENDING
    dm_sent_at: Optional[str] = None
    followup_due_at: Optional[str] = None
    source: str = "search"
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    maps_url: Optional[str] = None

    def to_csv_row(self) -> dict:
        """Converts model to exact PRD schema row plus enriched fields."""
        return {
            "Lead_ID": self.lead_id,
            "Business_Name": self.business_name,
            "Niche": self.niche,
            "Address": self.address or self.location or "",
            "Rating": self.rating if self.rating is not None else "",
            "Reviews_Count": self.reviews_count if self.reviews_count is not None else "",
            "IG_Handle_URL": self.ig_handle_url,
            "Current_Bio_Link": self.current_bio_link or "None",
            "Funnel_Diagnosis": self.funnel_diagnosis.value,
            "WhatsApp_Number": self.whatsapp_number or "Not Found",
            "Lead_Score": self.lead_score.value,
            "AI_Pitch_Angle": self.custom_pitch or self.message_1 or self.ai_pitch_angle,
            "Outreach_Status": self.outreach_status.value,
            "DM_Sent_At": self.dm_sent_at or "",
            "Followup_Due_At": self.followup_due_at or "",
            "WhatsApp_Direct_Link": self.whatsapp_direct_link or "",
            "Score_Points": self.lead_score_num,
            "Flaw_Detail": self.flaw_detail,
        }
