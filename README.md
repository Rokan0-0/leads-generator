# LeadPulse NG – Mobile Lead Hub & Bio-Link Auditor

A mobile-first lead discovery, audit, and direct WhatsApp pitching system built for agencies targeting high-ticket Nigerian local service businesses (Short-lets, Solar Installers, Med-Spas, Aesthetics Clinics, Dental, Fine Dining) that are losing revenue to missing websites, dead links, or raw WhatsApp funnels.

---

## ⚡ Core Features

- **Mobile PWA Dashboard**:
  - Installable directly to your phone's home screen (iOS & Android).
  - PIN passcode protected personal access.
  - Tabbed pipeline views: **Inbox (Pending)**, **Preview Built**, **DM Sent**, **Closed**.
  - 1-tap quick presets (Lekki Shortlets, Lagos Solar, VI Med-Spas, Ikeja Dental, VI Fine Dining, Full Sweep).
  - Real-time Server-Sent Events (SSE) streaming progress during live audits.
- **WhatsApp Pitch Outreach Engine**:
  - Generates direct, clickable WhatsApp links (`wa.me`) with tailored, conversational pitch copy referencing the business's exact Google rating and review count.
  - Support for **Niche Demo Portfolio Links**: attach live preview URLs (e.g. sample shortlet or clinic website) directly to outreach messages.
  - Tapping **"Open in WhatsApp"** launches WhatsApp on your phone with the pre-filled message and automatically advances lead status to **DM Sent**.
- **Discovery & The Golden Filter**:
  - Google Maps listings via Serper.dev (`/maps` and `/places`).
  - Active Instagram profile dorking with Nigerian mobile number extraction (`+234...`).
  - Asynchronous website health checking: discards working websites, retaining only prospects with `NO_WEBSITE` (100 pts), `SOCIAL_OR_WHATSAPP_ONLY` (95 pts), or `TRULY_DEAD_DOMAIN` (90 pts).
- **Hardened Persistence & Deduplication**:
  - Deduplicates on normalized E.164 phone numbers (`+234...`) across different queries.
  - Preserves business address, rating, reviews count, custom pitches, and demo portfolio links.
  - Safe CSV export with fallback protection against Windows Excel file locks.

---

## 🚀 Quickstart & Mobile PWA Setup

### 1. Configure Environment
Copy `.env.example` to `.env` and insert your API keys:
```ini
SERPER_API_KEY=your_serper_key_here
GEMINI_API_KEY=your_gemini_api_key
```

### 2. Launch the Mobile PWA Server
```powershell
.venv\Scripts\python.exe run.py serve
```
The server will start on port `8000`.

### 3. Access on Your Phone
1. Ensure your phone and computer are on the same Wi-Fi network.
2. Find your computer's local IP address (e.g. `192.168.1.50`).
3. Open Safari (iOS) or Chrome (Android) on your phone and browse to:
   ```
   http://192.168.1.50:8000
   ```
4. Enter the default PIN: `1234` (configurable in app settings).
5. Tap **Share / Menu** $\rightarrow$ **"Add to Home Screen"** to install it as a standalone app!

---

## 💻 CLI Usage

You can also run LeadPulse from your terminal:

```powershell
# Launch the Mobile PWA server
.venv\Scripts\python.exe run.py serve

# Run an on-demand audit for Lekki Shortlets
.venv\Scripts\python.exe run.py collect --niche "Shortlet Apartments" --location "Lekki Phase 1, Lagos"

# Run a quick 5-lead verification test
.venv\Scripts\python.exe run.py test

# View all saved leads in your terminal
.venv\Scripts\python.exe run.py view

# Export qualified leads (Score >= 80) to leads.csv
.venv\Scripts\python.exe run.py export --min-score 80

# Mark outreach status
.venv\Scripts\python.exe run.py mark "Ox restaurant" "DM Sent"
```

---

## 📊 Output Schema (`leads.csv`)

| Column | Description |
|---|---|
| `Lead_ID` | Stable MD5 unique identifier |
| `Business_Name` | Business display name |
| `Niche` | Target industry |
| `Address` | Physical address or locality |
| `Rating` | Google Maps star rating (e.g. 4.8) |
| `Reviews_Count` | Number of verified customer reviews |
| `IG_Handle_URL` | Direct Instagram profile URL |
| `Current_Bio_Link` | Extracted bio link or website |
| `Funnel_Diagnosis` | `NO_WEBSITE`, `SOCIAL_OR_WHATSAPP_ONLY`, `TRULY_DEAD_DOMAIN` |
| `WhatsApp_Number` | Normalized Nigerian phone (`+234...`) |
| `Lead_Score` | Urgency tier (`High` / `Medium` / `Low`) |
| `AI_Pitch_Angle` | Custom pitch message |
| `Outreach_Status` | `Pending` $\rightarrow$ `Preview Built` $\rightarrow$ `DM Sent` $\rightarrow$ `Closed` |
| `WhatsApp_Direct_Link` | One-click clickable WhatsApp chat link with pre-filled message |
| `Score_Points` | Numerical vulnerability score (1–100) |
| `Flaw_Detail` | Specific diagnosis details |
