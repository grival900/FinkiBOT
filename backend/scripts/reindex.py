"""CLI entrypoint for a manual scrape + index pass:

    python -m backend.scripts.reindex [frequent|slow] [--incremental]

Equivalent to POSTing to `/admin/reindex` (with the same optional `cadence` and
`--incremental`), but doesn't require the API server to be running — useful for a
first-time index build or ad-hoc debugging. With no cadence argument, runs every
enabled scraper regardless of cadence — see `backend/scrapers/registry.py` for what
"frequent" vs "slow" means.

`--incremental` skips any page whose URL is already in the database, so only genuinely
new documents are fetched. Much faster, but it will not notice edits to pages already
indexed — run a full (non-incremental) pass now and then for that.
"""

import argparse
import logging

from backend.ingestion.pipeline import run_ingestion

logging.basicConfig(level=logging.INFO)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m backend.scripts.reindex")
    parser.add_argument(
        "cadence",
        nargs="?",
        choices=["frequent", "slow"],
        help="limit to this cadence group; omit to run every enabled scraper",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="only fetch URLs not already in the database (skips edit detection)",
    )
    args = parser.parse_args()

    stats = run_ingestion(args.cadence, incremental=args.incremental)
    print(stats)


if __name__ == "__main__":
    main()
