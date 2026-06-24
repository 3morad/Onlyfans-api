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
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "SFS Daily").strip()

# --- Sync ---
SFS_PREFIX = os.getenv("SFS_PREFIX", "New SFS").strip()

# Write one row per campaign per DAY (incremental). Days with no activity are
# skipped unless INCLUDE_ZERO_DAYS=true.
INCLUDE_ZERO_DAYS = os.getenv("INCLUDE_ZERO_DAYS", "false").strip().lower() in ("1", "true", "yes")

# Upsert key field in Airtable. One row per (tracking link, day): "{link_id}_{YYYY-MM-DD}".
MERGE_FIELD = "Sync Key"


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
