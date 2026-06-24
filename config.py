"""Configuration and environment loading for the SFS tracking sync."""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise SystemExit(
            f"Missing required environment variable: {name}\n"
            f"Copy .env.example to .env and fill it in."
        )
    return val


# --- OnlyFans API ---
ONLYFANS_API_KEY = os.getenv("ONLYFANS_API_KEY", "").strip()
ONLYFANS_API_BASE = os.getenv("ONLYFANS_API_BASE", "https://app.onlyfansapi.com/api").rstrip("/")

# --- Airtable ---
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "").strip()
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "apppn8mDeO3pvAFpc").strip()

# Two tables, refreshed every run:
#   - SFS Tracking: one row per campaign (cumulative, from the API summary). Key = Link ID.
#   - SFS Daily:    one row per campaign per day (incremental). Key = Sync Key.
#                   Each daily row links back to its campaign in SFS Tracking.
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "SFS Tracking").strip()
AIRTABLE_DAILY_TABLE = os.getenv("AIRTABLE_DAILY_TABLE", "SFS Daily").strip()

CUMULATIVE_MERGE_FIELD = "Link ID"       # upsert key for SFS Tracking
DAILY_MERGE_FIELD = "Sync Key"           # upsert key for SFS Daily
CAMPAIGN_LINK_FIELD = "Campaign Link"    # linked-record field in SFS Daily -> SFS Tracking

# --- Sync ---
SFS_PREFIX = os.getenv("SFS_PREFIX", "New SFS").strip()

# Log one SFS Daily row for every day since the campaign was created (incl. zero
# days). Set INCLUDE_ZERO_DAYS=false to log only days that had activity.
INCLUDE_ZERO_DAYS = os.getenv("INCLUDE_ZERO_DAYS", "true").strip().lower() in ("1", "true", "yes")


def require_onlyfans() -> str:
    return _require("ONLYFANS_API_KEY")


def require_airtable() -> str:
    _require("AIRTABLE_API_KEY")
    return AIRTABLE_API_KEY


# Map an OnlyFans account (by username) to the clean "SFS Model" name used in the
# sheet / Airtable single-select. Unknown accounts fall back to their display name.
MODEL_NAME_BY_USERNAME = {
    "ellielunares": "Ellie Lunares",
    "leilanimorales": "Leilani Morales",
    "matikruz": "Mati Cruz",
    "lilliana2prettyy": "Lilliana Flores",
    "mayasparkly": "Maya Blossom",
}


def model_name(account: dict) -> str:
    """Return the clean SFS Model name for an account dict from /api/accounts."""
    username = (account.get("onlyfans_username") or "").lower()
    if username in MODEL_NAME_BY_USERNAME:
        return MODEL_NAME_BY_USERNAME[username]
    # Fall back: strip common suffixes from the display name.
    name = account.get("display_name") or username or account.get("id", "")
    for suffix in (" Free Account", " Meta Ads", " Account", " 1"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.strip()
