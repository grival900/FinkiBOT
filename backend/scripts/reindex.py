"""CLI entrypoint for a manual scrape + index pass:

    python -m backend.scripts.reindex [frequent|slow] [--incremental]
    python -m backend.scripts.reindex --scraper finki_hub.sessions
    python -m backend.scripts.reindex --list

Equivalent to POSTing to `/admin/reindex` (with the same optional `cadence`,
`--scraper` and `--incremental`), but doesn't require the API server to be running —
useful for a first-time index build or ad-hoc debugging. With no cadence argument,
runs every enabled scraper regardless of cadence — see `backend/scrapers/registry.py`
for what "frequent" vs "slow" means.

`--scraper NAME` narrows the run to exactly that one scraper (see `--list` for valid
names) regardless of `cadence` — for when only one source actually needs re-fetching
(e.g. after fixing that source's own extraction code) and running every other
cadence-mate alongside it would just be extra rate-limited minutes for nothing.

`--incremental` skips any page whose URL is already in the database, so only genuinely
new documents are fetched. Much faster, but it will not notice edits to pages already
indexed (including a scraper/extraction *code* fix, which changes what a re-fetch of
an already-known URL would produce) — run a full (non-incremental) pass for that.
"""

import argparse
import logging

from backend.ingestion.pipeline import run_ingestion
from backend.scrapers.registry import SCRAPERS

logging.basicConfig(level=logging.INFO)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m backend.scripts.reindex")
    parser.add_argument(
        "cadence",
        nargs="?",
        choices=["frequent", "slow"],
        help="limit to this cadence group; ignored (and unnecessary) when --scraper is given",
    )
    parser.add_argument(
        "--scraper",
        metavar="NAME",
        help="limit to exactly this scraper by name, regardless of cadence — see --list",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="only fetch URLs not already in the database (skips edit detection)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print every scraper name (for use with --scraper) and exit",
    )
    args = parser.parse_args()

    if args.list:
        for entry in SCRAPERS:
            print(f"{entry.name}  (source={entry.source}, cadence={entry.cadence}, enabled={entry.enabled})")
        return

    stats = run_ingestion(None if args.scraper else args.cadence, incremental=args.incremental, name=args.scraper)
    print(stats)


if __name__ == "__main__":
    main()
