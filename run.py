"""CLI entry point for the SFS tracking sync.

Usage:
  python run.py sync                  # pull from OnlyFans API and upsert into Airtable
  python run.py sync --dry-run        # pull only, print what would be written
  python run.py sync --account acct_xxx   # limit to one account (id or username)
  python run.py accounts              # list connected OnlyFans accounts
"""
from __future__ import annotations

import sys
import argparse
import logging

import config


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_sync(args):
    import sync

    result = sync.run(dry_run=args.dry_run, only_account=args.account)
    print("\n=== Summary ===")
    for model, n in result.get("per_model", {}).items():
        print(f"  {model}: {n['campaigns']} campaigns, {n['daily_rows']} daily rows")
    print(f"  TOTAL: {result['campaigns']} campaigns, {result['daily_rows']} daily rows")
    if args.dry_run:
        print("  DRY RUN - nothing written.")
    else:
        t, d = result["tracking"], result["daily"]
        print(f"  SFS Tracking -> {t['created']} created, {t['updated']} updated")
        print(f"  SFS Daily    -> {d['created']} created, {d['updated']} updated")

    req = result.get("api_requests", 0)
    accts = result.get("accounts", 0) or 1
    print("  --- API cost (OnlyFans) ---")
    print(f"  This run: ~{req} credits across {accts} account(s) @ 1 credit/request")
    print(f"  If run daily: ~{req * 30} credits/month vs ~{accts * 10000} included ({accts} x 10,000)")
    if result.get("credit_headers"):
        print(f"  API-reported: {result['credit_headers']}")


def cmd_accounts(args):
    from onlyfans_client import OnlyFansClient

    of = OnlyFansClient(config.require_onlyfans(), config.ONLYFANS_API_BASE)
    for a in of.list_accounts():
        print(f"  {a.get('id'):<40} {config.model_name(a):<20} @{a.get('onlyfans_username')}")


def main(argv=None):
    setup_logging()
    parser = argparse.ArgumentParser(description="Sync SFS tracking links from OnlyFans API to Airtable.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="Pull SFS links and upsert into Airtable.")
    p_sync.add_argument("--dry-run", action="store_true", help="Print rows instead of writing.")
    p_sync.add_argument("--account", help="Limit to one account (id or username).")
    p_sync.set_defaults(func=cmd_sync)

    p_acc = sub.add_parser("accounts", help="List connected OnlyFans accounts.")
    p_acc.set_defaults(func=cmd_accounts)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:
        logging.getLogger("run").error("FAILED: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
