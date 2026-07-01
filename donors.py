"""Parse SFS campaign names into a donor name + start date.

Campaign names look like:  "New SFS - Leilani 6/18", "New SFS -Sabrina 6/18",
"New SFS - LILI FREE 6/18", "New SFS - Maya 2 6/18".

We extract the donor label and the date, then map the short donor label to the
full name used in the SFS Tracking sheet (e.g. "LILI FREE" -> "Lilliana Flores Free").
"""
from __future__ import annotations

import re
from datetime import date

# Short campaign label (normalised: lowercased, collapsed spaces) -> full sheet name.
DONOR_ALIASES = {
    "leilani": "Leilani Morales",
    "mei": "Mei Ortiz",
    "mati": "Mati Cruz",
    "maya": "Maya Blossom",
    "maya 2": "Maya Blossom 2",
    "selena": "Selena Ruby",
    "sabrina": "Sabrina Luv",
    "catalina": "Catalina Amor",
    "ellie": "Ellie Lunares",
    "lili free": "Lilliana Flores Free",
    "lili vip": "Lilliana Flores VIP",
    "lilliana free": "Lilliana Flores Free",
    "lilliana vip": "Lilliana Flores VIP",
    "lilliana flores free": "Lilliana Flores Free",
    "lilliana flores vip": "Lilliana Flores VIP",
    "camila": "Camila Fleur",
    "julieta": "Julieta Vega",
    "penelope": "Penelope Vega",
    "mia": "Mia Lune",
    "emma": "Emma Weiss",
    "miranda": "Miranda Blaze",
}

# --- Date tokens: numeric (6/18, 07/01/26) or month-name (Jun 16, June 16 2026) ---
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MONTH_NUM = {m: i for i, m in enumerate(_MONTHS, start=1)}
_MONTH_FULL = ["january", "february", "march", "april", "may", "june", "july",
               "august", "september", "october", "november", "december"]
# Full names first so "june" matches before the "jun" abbreviation.
_MONTH_ALT = "|".join(_MONTH_FULL + _MONTHS + ["sept"])
_DATE_NUM = r"\d{1,2}/\d{1,2}(?:/\d{2,4})?"
# Require the month be followed by whitespace + a day, so donor names that start
# with a month (e.g. "Maya" -> "May") are NOT mistaken for a date.
_DATE_NAME = r"(?:" + _MONTH_ALT + r")\.?\s+\d{1,2}(?:,?\s*\d{2,4})?"
_DATE = r"(?:" + _DATE_NUM + r"|" + _DATE_NAME + r")"

# SFS campaign name formats we recognise (donor = the model GIVING the shoutout):
#   "New SFS - Mei 6/18"               (original numeric-date style)
#   "SFS - Leilani - Jun 16"           (dash style, optional month-name date)
#   "SFS from Leilani to Emilia 07/01" (from <donor> to <model> style)
_IS_SFS_RE = re.compile(r"^\s*(?:new\s+)?sfs\b", re.IGNORECASE)
_SFS_FROM_RE = re.compile(
    r"^\s*(?:new\s+)?sfs\s+from\s+(?P<donor>.+?)\s+to\s+.+?(?:\s+(?P<date>" + _DATE + r"))?\s*$",
    re.IGNORECASE,
)
_SFS_DASH_RE = re.compile(
    r"^\s*(?:new\s+)?sfs\s*[-:]?\s*(?P<donor>.*?)\s*[-:]?\s*(?P<date>" + _DATE + r")?\s*$",
    re.IGNORECASE,
)


def is_sfs(campaign_name: str, prefix: str = "New SFS") -> bool:
    """True for any SFS campaign, regardless of style:
    'New SFS - ...', 'SFS - ...', or 'SFS from ... to ...'. The `prefix` arg is
    kept for compatibility but matching is now pattern-based (the naming
    convention varies across models)."""
    return bool(_IS_SFS_RE.match(campaign_name or ""))


def normalise(label: str) -> str:
    return re.sub(r"\s+", " ", (label or "").strip()).lower()


def map_donor(label: str) -> str:
    """Map a short campaign donor label to the full sheet name."""
    # Strip surrounding dashes/whitespace left over from messy names
    # like "CATALINA-", "MAYA 2 -", "- Leilani".
    label = re.sub(r"^[\s\-]+|[\s\-]+$", "", label or "")
    key = normalise(label)
    if key in DONOR_ALIASES:
        return DONOR_ALIASES[key]
    # Unknown: title-case the label so it is at least readable.
    return label.strip().title() if label else ""


def parse_date(token: str | None, fallback_year: int) -> date | None:
    if not token:
        return None
    token = token.strip()
    # Numeric: M/D or M/D/YY[YY]
    if "/" in token:
        parts = token.split("/")
        try:
            month = int(parts[0])
            day = int(parts[1])
            year = int(parts[2]) if len(parts) >= 3 else fallback_year
            if year < 100:
                year += 2000
            return date(year, month, day)
        except (ValueError, IndexError):
            return None
    # Month-name: "Jun 16", "June 16", "Jun 16 2026", "Jun 16, 26"
    m = re.match(r"([a-zA-Z]{3,})\.?\s+(\d{1,2})(?:,?\s*(\d{2,4}))?", token)
    if m:
        month = _MONTH_NUM.get(m.group(1)[:3].lower())
        if month:
            day = int(m.group(2))
            year = int(m.group(3)) if m.group(3) else fallback_year
            if year < 100:
                year += 2000
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def parse_campaign(campaign_name: str, fallback_year: int) -> tuple[str, date | None]:
    """Return (full_donor_name, start_date) parsed from a campaign name.

    Tries the 'from <donor> to <model>' style first, then the dash style.
    """
    name = (campaign_name or "").strip()
    m = _SFS_FROM_RE.match(name) or _SFS_DASH_RE.match(name)
    if not m:
        return name, None
    donor = map_donor(m.group("donor"))
    start = parse_date(m.group("date"), fallback_year)
    return donor, start
