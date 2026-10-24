import asyncio
import re
import urllib.parse
from typing import Optional, Tuple
import httpx

from .config import DEFAULT_USER_AGENT
from .models import FunnelDiagnosis
from .parser import extract_nigerian_phone

SOCIAL_OR_WHATSAPP_DOMAINS = (
    "instagram.com",
    "facebook.com",
    "wa.me",
    "api.whatsapp.com",
    "chat.whatsapp.com",
    "whatsapp.com",
    "linktr.ee",
    "mainstack.me",
    "mainstack.app",
    "selar.co",
    "selar.com",
    "carrd.co",
    "taplink.cc",
    "beacons.ai",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "bio.link",
    "lnk.bio",
    "msha.ke",
    "snipfeed.co",
)

PARKED_DOMAIN_KEYWORDS = (
    "this domain is for sale",
    "domain parked",
    "buy this domain",
    "renew your domain",
    "godaddy parked",
    "namecheap parking",
    "under construction",
    "website coming soon",
    "domain has expired",
    "server not found",
)


def is_social_or_whatsapp(url: str) -> Optional[str]:
    """Returns the matched host if URL points to a social network, WhatsApp, or aggregator."""
    if not url:
        return None
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        if not netloc and "/" not in url:
            netloc = url.lower()
        for domain in SOCIAL_OR_WHATSAPP_DOMAINS:
            if domain in netloc or domain in url.lower():
                return domain
    except Exception:
        pass
    return None


async def audit_and_filter_candidate(
    client: httpx.AsyncClient,
    candidate: dict,
) -> Optional[Tuple[FunnelDiagnosis, str, str, int]]:
    """
    Applies The Golden Filter to a candidate business:
    1. Phone verification: Must have a valid Nigerian mobile phone.
    2. NO_WEBSITE (Score 100): No website field, ratingCount >= 3 (or from active IG).
    3. SOCIAL_OR_WHATSAPP_ONLY (Score 95): Website points to IG, WhatsApp, Linktree, TikTok, etc.
    4. TRULY_DEAD_DOMAIN (Score 90): Custom domain with DNS failure, connection refused, or 404/500/parking.
    5. DISCARD IMMEDIATELY: Working live custom website.

    Returns:
        (FunnelDiagnosis, flaw_detail, normalized_phone, score) OR None if discarded.
    """
    raw_phone = candidate.get("phone") or candidate.get("snippet")
    normalized_phone = extract_nigerian_phone(raw_phone)
    if not normalized_phone:
        # Without a valid Nigerian mobile, we cannot reach out via WhatsApp -> DISCARD
        return None

    raw_website = (candidate.get("bio_link") or candidate.get("website") or "").strip()
    rating_count = candidate.get("reviews") or 0
    source = candidate.get("source", "")

    # RULE 1: NO_WEBSITE (Score 100)
    if not raw_website or raw_website.lower() in ("none", "null", ""):
        # If from Google Maps, enforce ratingCount >= 3 to prove real customer activity
        if "places" in source or "maps" in source:
            if rating_count < 3:
                return None  # Discard unverified/inactive listings without reviews
            flaw = f"Active Google Maps listing ({rating_count} reviews) with no booking website"
        else:
            flaw = "Active Instagram profile with direct WhatsApp contact but zero booking link"
        return (FunnelDiagnosis.NO_WEBSITE, flaw, normalized_phone, 100)

    # RULE 2: SOCIAL_OR_WHATSAPP_ONLY (Score 95)
    matched_social = is_social_or_whatsapp(raw_website)
    if matched_social:
        flaw = f"Website button points to {matched_social} instead of an automated booking funnel"
        return (FunnelDiagnosis.SOCIAL_OR_WHATSAPP_ONLY, flaw, normalized_phone, 95)

    # RULE 3 & 4: Custom Domain Audit (Browser-header check)
    url_to_test = raw_website
    if not url_to_test.startswith("http://") and not url_to_test.startswith("https://"):
        url_to_test = "https://" + url_to_test

    try:
        resp = await client.get(
            url_to_test,
            follow_redirects=True,
            timeout=8.0,
        )
        final_url = str(resp.url)

        # Check if redirected to a social or WhatsApp page
        redirect_social = is_social_or_whatsapp(final_url)
        if redirect_social:
            flaw = f"Custom domain redirects to {redirect_social} instead of a real booking site"
            return (FunnelDiagnosis.SOCIAL_OR_WHATSAPP_ONLY, flaw, normalized_phone, 95)

        # Check for HTTP dead error codes (404, 500, 502, 503)
        if resp.status_code >= 400:
            flaw = f"Domain returns HTTP {resp.status_code} Error"
            return (FunnelDiagnosis.TRULY_DEAD_DOMAIN, flaw, normalized_phone, 90)

        # Check for parked / expired domain keywords
        html_sample = resp.text[:2500].lower()
        for kw in PARKED_DOMAIN_KEYWORDS:
            if kw in html_sample:
                flaw = f"Domain appears parked or expired ('{kw}')"
                return (FunnelDiagnosis.TRULY_DEAD_DOMAIN, flaw, normalized_phone, 90)

        # If it reached here with HTTP 200 and live custom content:
        # RULE: DISCARD IMMEDIATELY. Do not audit load times or viewports.
        return None

    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        flaw = "DNS failure / connection refused (NXDOMAIN or dead host)"
        return (FunnelDiagnosis.TRULY_DEAD_DOMAIN, flaw, normalized_phone, 90)
    except httpx.HTTPError as e:
        err = str(e)
        if "SSL" in err or "certificate" in err.lower():
            flaw = "Dead site: SSL Certificate invalid or expired"
            return (FunnelDiagnosis.TRULY_DEAD_DOMAIN, flaw, normalized_phone, 90)
        flaw = f"Dead site: Network error ({err[:40]})"
        return (FunnelDiagnosis.TRULY_DEAD_DOMAIN, flaw, normalized_phone, 90)
    except Exception as e:
        flaw = f"Dead site: Unreachable ({str(e)[:40]})"
        return (FunnelDiagnosis.TRULY_DEAD_DOMAIN, flaw, normalized_phone, 90)


async def batch_filter_candidates(
    candidates: list[dict],
    concurrency: int = 15,
) -> list[Tuple[dict, FunnelDiagnosis, str, str, int]]:
    """
    Applies The Golden Filter concurrently to a list of raw candidates.
    Returns list of tuples: (candidate, diagnosis, flaw_detail, normalized_phone, score)
    Only retained leads are returned. All working sites and invalid numbers are discarded.
    """
    semaphore = asyncio.Semaphore(concurrency)
    kept_leads = []

    async with httpx.AsyncClient(
        headers={"User-Agent": DEFAULT_USER_AGENT},
        verify=False,
    ) as client:
        async def _check(cand):
            async with semaphore:
                result = await audit_and_filter_candidate(client, cand)
                if result is not None:
                    diagnosis, flaw_detail, phone, score = result
                    return (cand, diagnosis, flaw_detail, phone, score)
                return None

        tasks = [_check(c) for c in candidates]
        results = await asyncio.gather(*tasks)
        for r in results:
            if r is not None:
                kept_leads.append(r)

    return kept_leads
