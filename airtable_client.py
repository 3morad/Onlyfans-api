"""Minimal Airtable client with batched upsert support."""
from __future__ import annotations

import time
import logging

import requests

log = logging.getLogger("airtable")

API_ROOT = "https://api.airtable.com/v0"


class AirtableError(RuntimeError):
    pass


class AirtableClient:
    def __init__(self, api_key: str, base_id: str, table_name: str, timeout: int = 30):
        if not api_key:
            raise AirtableError("AIRTABLE_API_KEY is not set.")
        self.base_id = base_id
        self.table_name = table_name
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

    @property
    def _url(self) -> str:
        # Table name is URL-encoded by requests via the path; build manually to be safe.
        from urllib.parse import quote

        return f"{API_ROOT}/{self.base_id}/{quote(self.table_name)}"

    def upsert(self, records: list[dict], merge_on: str) -> dict:
        """Upsert records (list of {"fields": {...}}) matched on `merge_on`.

        Returns counts of created/updated. Batches of 10 per Airtable limits.
        """
        created, updated = 0, 0
        for i in range(0, len(records), 10):
            batch = records[i : i + 10]
            body = {
                "performUpsert": {"fieldsToMergeOn": [merge_on]},
                "records": batch,
                "typecast": True,
            }
            data = self._patch(body)
            created += len(data.get("createdRecords", []))
            updated += len(data.get("updatedRecords", []))
        return {"created": created, "updated": updated}

    def _patch(self, body: dict, max_retries: int = 5) -> dict:
        backoff = 2.0
        for attempt in range(1, max_retries + 1):
            resp = self.session.patch(self._url, json=body, timeout=self.timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt == max_retries:
                    raise AirtableError(f"PATCH failed: {resp.status_code} {resp.text[:300]}")
                wait = backoff * attempt
                log.warning("Airtable %s, retrying in %.0fs (%d/%d)", resp.status_code, wait, attempt, max_retries)
                time.sleep(wait)
                continue
            if not resp.ok:
                raise AirtableError(f"PATCH failed: {resp.status_code} {resp.text[:500]}")
            return resp.json()
        raise AirtableError("PATCH exhausted retries.")
