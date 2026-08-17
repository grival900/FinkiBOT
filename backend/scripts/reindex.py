"""CLI entrypoint for a manual scrape + index pass: `python -m backend.scripts.reindex`

Equivalent to POSTing to `/admin/reindex`, but doesn't require the API server to be
running — useful for a first-time index build or ad-hoc debugging.
"""

import logging

from backend.ingestion.pipeline import run_full_ingestion

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    stats = run_full_ingestion()
    print(stats)
