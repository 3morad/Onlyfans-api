# SFS Tracking Sync

Pulls **SFS campaign** tracking-link stats from the [OnlyFans API](https://app.onlyfansapi.com)
for all connected model accounts and upserts **daily** results into Airtable.

- **One row per SFS tracking link per DAY** (incremental, not cumulative):
  `Date · Donor / Page · SFS Model · Clicks · New Subscribers · Subscription CVR · AEPS · Spenders · Sales · Spending CVR`
- Only links whose campaign name starts with **`New SFS`** are synced.
- Days with no activity are skipped (set `INCLUDE_ZERO_DAYS=true` to keep them).
- Idempotent: re-running upserts each day's row (matched on **`Sync Key`** =
  `{link_id}_{YYYY-MM-DD}`), so late-attributed revenue is corrected automatically.

## What maps to what

Source: `GET /api/{account}/tracking-links/{id}/stats` → `daily_metrics[]`
(each entry is one day's **incremental** values).

| Airtable column     | Source |
|---------------------|--------|
| Date                | `daily_metrics[].timestamp` |
| Donor / Page        | parsed donor label, mapped to full name (`LILI FREE` → `Lilliana Flores Free`) |
| SFS Model           | the account that owns the link |
| Clicks              | `daily_metrics[].clicks` (that day) |
| New Subscribers     | `daily_metrics[].subs` (that day) |
| Subscription CVR    | New Subscribers ÷ Clicks |
| AEPS                | Sales ÷ New Subscribers |
| Spenders            | `daily_metrics[].spenders` (that day) |
| Sales               | `daily_metrics[].revenue` (that day) |
| Spending CVR        | Spenders ÷ New Subscribers |

## Setup

1. Install Python 3.10+.
2. From this folder:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in:
   - `ONLYFANS_API_KEY` — from the OnlyFansAPI dashboard.
   - `AIRTABLE_API_KEY` — a Personal Access Token (scopes: `data.records:read`,
     `data.records:write`, `schema.bases:read`) from
     <https://airtable.com/create/tokens>.
   - `AIRTABLE_BASE_ID` is preset to this base; `AIRTABLE_TABLE_NAME` to `SFS Daily`.

The target table must have these fields: `Sync Key` (text, primary), `Date` (date),
`Donor / Page` (text), `SFS Model` (single select), `Account ID`, `Username`,
`Campaign`, `Campaign Code` (number), `Campaign URL` (url), `Link Created` (date),
`Clicks` / `New Subscribers` / `Spenders` (number), `Sales` / `AEPS` (currency),
`Subscription CVR` / `Spending CVR` (percent), `Last Synced` (dateTime).

## Usage

```powershell
python run.py accounts            # list connected OnlyFans accounts
python run.py sync --dry-run      # pull + print, write nothing (good first test)
python run.py sync                # pull + upsert into Airtable
python run.py sync --account ellielunares   # one account only
```

## Schedule a daily run (Windows Task Scheduler)

`run_sync.ps1` runs the sync and logs to `.\logs\sync_<date>.log`.

Register it to run every day at 06:00 (adjust the path):

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"D:\Work Projects\Onlyfans-api-scraper\run_sync.ps1`""
$trigger = New-ScheduledTaskTrigger -Daily -At 6:00am
Register-ScheduledTask -TaskName "SFS Tracking Sync" -Action $action -Trigger $trigger -Description "Daily OnlyFans -> Airtable SFS sync"
```

Run it once on demand to verify:
```powershell
Start-ScheduledTask -TaskName "SFS Tracking Sync"
```

## Files

| File | Purpose |
|------|---------|
| `run.py`             | CLI entry point (`sync`, `accounts`) |
| `sync.py`            | Orchestration + row building |
| `onlyfans_client.py` | OnlyFans API client (accounts, tracking links, stats) |
| `airtable_client.py` | Airtable batched upsert |
| `donors.py`          | Campaign-name parsing + donor name mapping |
| `config.py`          | Env loading + model-name mapping |
| `run_sync.ps1`       | Task Scheduler wrapper (logs to `logs/`) |

## Notes

- Daily figures come from the tracking-link stats `daily_metrics` (incremental per day).
  Historical daily data only goes back to when the account was connected / daily
  recording began — earlier days aren't retrievable.
- The OnlyFans API has no daily rate limit; the client retries on `429`/`5xx`
  with backoff.
- New models/donors are handled automatically (Airtable `typecast` adds new
  single-select options; unknown donors fall back to a title-cased label —
  add them to `DONOR_ALIASES` in `donors.py` for exact sheet names).
