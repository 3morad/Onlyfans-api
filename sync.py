"""Pull SFS tracking links from the OnlyFans API and refresh two Airtable tables:

  * SFS Tracking  - one row per campaign (CUMULATIVE, from the stats `summary`),
                    upserted on "Link ID".
  * SFS Daily     - one row per campaign per DAY (INCREMENTAL, from `daily_metrics`),
                    upserted on "Sync Key", each linked back to its campaign row.

Both tables are refreshed on every run.
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


def _link_context(account, link):
    created_iso = _date_iso(link.get("createdAt"))
    year = int(created_iso[:4]) if created_iso else datetime.now().year
    donor, start = parse_campaign(link.get("campaignName", ""), year)
    return {
        "donor": donor,
        "start_iso": start.isoformat() if start else created_iso,
        "created_iso": created_iso,
        "model": config.model_name(account),
        "link_id": str(link.get("id", "")),
        "campaign": link.get("campaignName", ""),
        "code": link.get("campaignCode"),
        "url": link.get("campaignUrl"),
        "acct_id": account.get("id", ""),
        "username": account.get("onlyfans_username", ""),
    }


def build_cumulative(ctx, summary, synced_at) -> dict:
    """One SFS Tracking row from the stats summary (cumulative)."""
    clicks = summary.get("clicks_total", 0) or 0
    subs = summary.get("subs_total", 0) or 0
    revenue = summary.get("revenue_total", 0) or 0
    spenders = summary.get("spenders_total", 0) or 0
    return {"fields": {
        "Campaign": ctx["campaign"],
        "Link ID": ctx["link_id"],
        "Date Start": ctx["start_iso"],
        "Donor / Page": ctx["donor"],
        "SFS Model": ctx["model"],
        "Account ID": ctx["acct_id"],
        "Username": ctx["username"],
        "Campaign Code": ctx["code"],
        "Campaign URL": ctx["url"],
        "Link Created": ctx["created_iso"],
        "Clicks": clicks,
        "New Subscribers": subs,
        "Sales": revenue,
        "Spenders": spenders,
        "Subscription CVR": ratio(subs, clicks),
        "AEPS": money(revenue, subs),
        "Spending CVR": ratio(spenders, subs),
        "Rev per Click": money(revenue, clicks),
        "Last Synced": synced_at,
    }}


def build_daily(ctx, daily_metrics, synced_at) -> list[dict]:
    """SFS Daily rows (one per day since the link was created)."""
    rows = []
    for day in daily_metrics or []:
        date = (day.get("timestamp") or "")[:10]
        if not date or (ctx["created_iso"] and date < ctx["created_iso"]):
            continue
        clicks = day.get("clicks", 0) or 0
        subs = day.get("subs", 0) or 0
        revenue = day.get("revenue", 0) or 0
        spenders = day.get("spenders", 0) or 0
        if not config.INCLUDE_ZERO_DAYS and not (clicks or subs or revenue or spenders):
            continue
        rows.append({"fields": {
            "Sync Key": f"{ctx['link_id']}_{date}",
            "Date": date,
            "Donor / Page": ctx["donor"],
            "SFS Model": ctx["model"],
            "Account ID": ctx["acct_id"],
            "Username": ctx["username"],
            "Campaign": ctx["campaign"],
            "Campaign Code": ctx["code"],
            "Campaign URL": ctx["url"],
            "Link Created": ctx["created_iso"],
            "Clicks": clicks,
            "New Subscribers": subs,
            "Sales": revenue,
            "Spenders": spenders,
            "Subscription CVR": ratio(subs, clicks),
            "AEPS": money(revenue, subs),
            "Spending CVR": ratio(spenders, subs),
            "Last Synced": synced_at,
        }})
    return rows


def collect(of: OnlyFansClient, accounts, prefix):
    """Return (cumulative_records, daily_pairs, per_model) where daily_pairs are
    (fields_dict, link_id) so daily rows can be linked after the campaign upsert."""
    synced_at = datetime.now(timezone.utc).isoformat()
    cumulative, daily_pairs, per_model = [], [], {}

    for account in accounts:
        model = config.model_name(account)
        acct_id = account.get("id")
        n_links = n_days = 0
        log.info("Scanning %s (%s)...", model, acct_id)
        for link in of.iter_tracking_links(acct_id):
            if not is_sfs(link.get("campaignName", ""), prefix):
                continue
            try:
                stats = of.get_link_stats(acct_id, link.get("id"))
            except Exception as exc:
                log.warning("  stats failed for link %s: %s", link.get("id"), exc)
                continue
            ctx = _link_context(account, link)
            cumulative.append(build_cumulative(ctx, stats.get("summary", {}), synced_at))
            for row in build_daily(ctx, stats.get("daily_metrics", []), synced_at):
                daily_pairs.append((row, ctx["link_id"]))
                n_days += 1
            n_links += 1
        per_model[model] = {"campaigns": n_links, "daily_rows": n_days}
        log.info("  %s: %d campaigns, %d daily rows", model, n_links, n_days)

    return cumulative, daily_pairs, per_model


def run(dry_run: bool = False, only_account: str | None = None) -> dict:
    of = OnlyFansClient(config.require_onlyfans(), config.ONLYFANS_API_BASE)
    accounts = of.list_accounts()
    if only_account:
        accounts = [a for a in accounts if only_account in (a.get("id"), a.get("onlyfans_username"))]
        if not accounts:
            raise SystemExit(f"No account matching '{only_account}'.")

    cumulative, daily_pairs, per_model = collect(of, accounts, config.SFS_PREFIX)
    log.info("Collected %d campaigns (cumulative) and %d daily rows.", len(cumulative), len(daily_pairs))
    log.info("OnlyFans API requests this run: %d (~%d credits @ 1 credit/request).",
             of.request_count, of.request_count)

    if dry_run:
        for fields, _ in sorted(daily_pairs, key=lambda p: (p[0]["fields"]["SFS Model"], p[0]["fields"]["Campaign"], p[0]["fields"]["Date"])):
            f = fields["fields"]
            log.info("  %s | %-15s | %-20s | clk=%-3s subs=%-3s sales=%-6s sp=%s",
                     f["Date"], f["SFS Model"], f["Donor / Page"], f["Clicks"], f["New Subscribers"], f["Sales"], f["Spenders"])
        return {"campaigns": len(cumulative), "daily_rows": len(daily_pairs), "per_model": per_model,
                "accounts": len(accounts), "api_requests": of.request_count,
                "credit_headers": of.credit_headers, "dry_run": True}

    api_key = config.require_airtable()

    # 1) Refresh SFS Tracking (cumulative) and capture each campaign's record id.
    at_cum = AirtableClient(api_key, config.AIRTABLE_BASE_ID, config.AIRTABLE_TABLE_NAME)
    res_cum = at_cum.upsert(cumulative, merge_on=config.CUMULATIVE_MERGE_FIELD)
    id_by_link = {}
    for rec in res_cum.get("records", []):
        lid = (rec.get("fields") or {}).get("Link ID")
        if lid:
            id_by_link[str(lid)] = rec["id"]
    log.info("SFS Tracking: %d created, %d updated.", res_cum["created"], res_cum["updated"])

    # 2) Link daily rows to their campaign, then upsert SFS Daily.
    daily_records = []
    for fields, link_id in daily_pairs:
        rid = id_by_link.get(str(link_id))
        if rid:
            fields["fields"][config.CAMPAIGN_LINK_FIELD] = [rid]
        daily_records.append(fields)
    at_daily = AirtableClient(api_key, config.AIRTABLE_BASE_ID, config.AIRTABLE_DAILY_TABLE)
    res_daily = at_daily.upsert(daily_records, merge_on=config.DAILY_MERGE_FIELD)
    log.info("SFS Daily: %d created, %d updated.", res_daily["created"], res_daily["updated"])

    return {
        "campaigns": len(cumulative), "daily_rows": len(daily_records),
        "tracking": {"created": res_cum["created"], "updated": res_cum["updated"]},
        "daily": {"created": res_daily["created"], "updated": res_daily["updated"]},
        "per_model": per_model,
        "accounts": len(accounts), "api_requests": of.request_count,
        "credit_headers": of.credit_headers,
    }
