"""Pull SFS tracking links from the OnlyFans API and upsert DAILY rows into Airtable.

One Airtable row per SFS tracking link per DAY (incremental values), keyed by
"Sync Key" = "{tracking_link_id}_{YYYY-MM-DD}". Re-runs upsert the same day's row,
so late-attributed revenue is corrected automatically.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import config
from donors import is_sfs, parse_campaign
from onlyfans_client import OnlyFansClient
from airtable_client import AirtableClient

log = logging.getLogger("sync")


def ratio(num, den):
    """num/den as a 0..1 ratio (Airtable percent), or 0 when den is 0."""
    try:
        num, den = float(num or 0), float(den or 0)
        return round(num / den, 4) if den else 0
    except (TypeError, ValueError):
        return 0


def money(num, den):
    try:
        num, den = float(num or 0), float(den or 0)
        return round(num / den, 2) if den else 0
    except (TypeError, ValueError):
        return 0


def _date_iso(dt_string):
    if not dt_string:
        return None
    try:
        return datetime.fromisoformat(dt_string.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return dt_string[:10] if len(dt_string) >= 10 else None


def build_daily_records(account: dict, link: dict, daily_metrics: list, synced_at: str) -> list[dict]:
    """Turn a link's daily_metrics into one Airtable record per day."""
    created_iso = _date_iso(link.get("createdAt"))
    fallback_year = int(created_iso[:4]) if created_iso else datetime.now().year
    donor, _ = parse_campaign(link.get("campaignName", ""), fallback_year)
    model = config.model_name(account)
    link_id = link.get("id")

    records = []
    for day in daily_metrics or []:
        date = (day.get("timestamp") or "")[:10]
        if not date:
            continue
        if created_iso and date < created_iso:
            continue  # don't log days before the link existed
        clicks = day.get("clicks", 0) or 0
        subs = day.get("subs", 0) or 0
        revenue = day.get("revenue", 0) or 0
        spenders = day.get("spenders", 0) or 0
        if not config.INCLUDE_ZERO_DAYS and not (clicks or subs or revenue or spenders):
            continue  # skip empty days
        records.append({"fields": {
            "Sync Key": f"{link_id}_{date}",
            "Date": date,
            "Donor / Page": donor,
            "SFS Model": model,
            "Account ID": account.get("id", ""),
            "Username": account.get("onlyfans_username", ""),
            "Campaign": link.get("campaignName", ""),
            "Campaign Code": link.get("campaignCode"),
            "Campaign URL": link.get("campaignUrl"),
            "Link Created": created_iso,
            "Clicks": clicks,
            "New Subscribers": subs,
            "Sales": revenue,
            "Spenders": spenders,
            "Subscription CVR": ratio(subs, clicks),
            "AEPS": money(revenue, subs),
            "Spending CVR": ratio(spenders, subs),
            "Last Synced": synced_at,
        }})
    return records


def collect_records(of: OnlyFansClient, accounts: list[dict], prefix: str) -> tuple[list[dict], dict]:
    synced_at = datetime.now(timezone.utc).isoformat()
    records: list[dict] = []
    per_model: dict[str, int] = {}

    for account in accounts:
        model = config.model_name(account)
        acct_id = account.get("id")
        rows_for_model = 0
        log.info("Scanning %s (%s)...", model, acct_id)
        for link in of.iter_tracking_links(acct_id):
            if not is_sfs(link.get("campaignName", ""), prefix):
                continue
            try:
                stats = of.get_link_stats(acct_id, link.get("id"))
            except Exception as exc:
                log.warning("  stats failed for link %s: %s", link.get("id"), exc)
                continue
            day_rows = build_daily_records(account, link, stats.get("daily_metrics", []), synced_at)
            records.extend(day_rows)
            rows_for_model += len(day_rows)
        per_model[model] = rows_for_model
        log.info("  %d daily rows for %s", rows_for_model, model)

    return records, per_model


def run(dry_run: bool = False, only_account: str | None = None) -> dict:
    of = OnlyFansClient(config.require_onlyfans(), config.ONLYFANS_API_BASE)
    accounts = of.list_accounts()
    if only_account:
        accounts = [a for a in accounts if only_account in (a.get("id"), a.get("onlyfans_username"))]
        if not accounts:
            raise SystemExit(f"No account matching '{only_account}'.")

    records, per_model = collect_records(of, accounts, config.SFS_PREFIX)
    log.info("Collected %d daily rows across %d accounts.", len(records), len(accounts))

    if dry_run:
        for r in sorted(records, key=lambda x: (x["fields"]["SFS Model"], x["fields"]["Date"])):
            f = r["fields"]
            log.info("  %s | %-16s | %-22s | clk=%-3s subs=%-3s sales=%-6s sp=%s",
                     f["Date"], f["SFS Model"], f["Donor / Page"], f["Clicks"], f["New Subscribers"], f["Sales"], f["Spenders"])
        return {"records": len(records), "per_model": per_model, "dry_run": True}

    at = AirtableClient(config.require_airtable(), config.AIRTABLE_BASE_ID, config.AIRTABLE_TABLE_NAME)
    result = at.upsert(records, merge_on=config.MERGE_FIELD)
    log.info("Airtable upsert: %d created, %d updated.", result["created"], result["updated"])
    return {"records": len(records), "per_model": per_model, **result}
