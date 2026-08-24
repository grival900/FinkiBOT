"""CLI entrypoint for a manual scrape + index pass: `python -m backend.scripts.reindex
[frequent|slow]`

Equivalent to POSTing to `/admin/reindex` (with the same optional `cadence`), but
doesn't require the API server to be running — useful for a first-time index build or
ad-hoc debugging. With no argument, runs every enabled scraper regardless of cadence —
see `backend/scrapers/registry.py` for what "frequent" vs "slow" means.
"""

import logging
import sys

from backend.ingestion.pipeline import run_ingestion

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg not in (None, "frequent", "slow"):
        print("Usage: python -m backend.scripts.reindex [frequent|slow]", file=sys.stderr)
        sys.exit(1)
    stats = run_ingestion(arg)
    print(stats)
