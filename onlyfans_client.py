"""Thin client for the OnlyFans API (https://app.onlyfansapi.com).

Endpoints used:
  GET /api/accounts                                      -> list connected accounts
  GET /api/{account}/tracking-links                      -> list tracking links (cumulative)
  GET /api/{account}/tracking-links/{id}/stats           -> summary + daily/monthly metrics
"""
from __future__ import annotations

import time
import logging
from typing import Iterator

import requests

log = logging.getLogger("onlyfans")


class OnlyFansError(RuntimeError):
    pass


class OnlyFansClient:
    def __init__(self, api_key: str, base_url: str, timeout: int = 60):
        if not api_key:
            raise OnlyFansError("ONLYFANS_API_KEY is not set.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": "sfs-tracking-sync/1.0",
            }
        )

    # --- low level ---
    def _get(self, path: str, params: dict | None = None, max_retries: int = 5) -> dict:
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        backoff = 2.0
        for attempt in range(1, max_retries + 1):
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == max_retries:
                    raise OnlyFansError(f"GET {url} failed: {resp.status_code} {resp.text[:300]}")
                wait = backoff * attempt
                log.warning("GET %s -> %s, retrying in %.0fs (%d/%d)", url, resp.status_code, wait, attempt, max_retries)
                time.sleep(wait)
                continue
            if resp.status_code == 401:
                raise OnlyFansError("401 Unauthorized - check ONLYFANS_API_KEY.")
            if not resp.ok:
                raise OnlyFansError(f"GET {url} failed: {resp.status_code} {resp.text[:300]}")
            return resp.json()
        raise OnlyFansError(f"GET {url} exhausted retries.")

    # --- API methods ---
    def list_accounts(self) -> list[dict]:
        data = self._get("accounts")
        return data.get("response", data.get("data", []))

    def iter_tracking_links(self, account_id: str, page_size: int = 50) -> Iterator[dict]:
        """Yield every tracking link for an account (cumulative stats included)."""
        offset = 0
        while True:
            data = self._get(
                f"{account_id}/tracking-links",
                params={
                    "limit": page_size,
                    "offset": offset,
                    "sortby": "created_date",
                    "sort": "desc",
                },
            )
            payload = data.get("response", {}).get("data", {})
            items = payload.get("list", [])
            for item in items:
                yield item
            if not payload.get("hasMore") or not items:
                break
            offset += page_size

    def get_link_stats(self, account_id: str, link_id, date_start=None, date_end=None) -> dict:
        """Return the full stats payload for a tracking link.

        Shape: {"summary": {clicks_total, subs_total, revenue_total, spenders_total},
                "daily_metrics": [{timestamp, clicks, subs, revenue, spenders}, ...],
                "monthly_metrics": [...]}
        `daily_metrics` are INCREMENTAL per-day values (not cumulative).
        """
        params = {}
        if date_start:
            params["date_start"] = date_start
        if date_end:
            params["date_end"] = date_end
        data = self._get(f"{account_id}/tracking-links/{link_id}/stats", params=params or None)
        return data.get("response", {}).get("data", {})
