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

# "New SFS" (any spacing / optional dash) <donor> <M/D[/YY]>
_CAMPAIGN_RE = re.compile(
    r"^\s*new\s*sfs\s*-?\s*(?P<donor>.*?)\s*(?P<date>\d{1,2}/\d{1,2}(?:/\d{2,4})?)?\s*$",
    re.IGNORECASE,
)


def is_sfs(campaign_name: str, prefix: str = "New SFS") -> bool:
    return (campaign_name or "").strip().lower().startswith(prefix.strip().lower())


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
    parts = token.split("/")
    try:
        month = int(parts[0])
        day = int(parts[1])
        if len(parts) >= 3:
            year = int(parts[2])
            if year < 100:
                year += 2000
        else:
            year = fallback_year
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def parse_campaign(campaign_name: str, fallback_year: int) -> tuple[str, date | None]:
    """Return (full_donor_name, start_date) parsed from a campaign name."""
    m = _CAMPAIGN_RE.match(campaign_name or "")
    if not m:
        return (campaign_name or "").strip(), None
    donor = map_donor(m.group("donor"))
    start = parse_date(m.group("date"), fallback_year)
    return donor, start
