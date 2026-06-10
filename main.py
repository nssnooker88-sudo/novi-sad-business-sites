"""
Local Business Discovery Engine — CLI entry point.

Discovers Novi Sad businesses via the Google Places API (New), scores them as
website-sales leads, stores everything in SQLite, and exports ranked datasets.

Usage:
    export GOOGLE_MAPS_API_KEY="..."     # or put it in config.json
    python main.py                       # resume / continue a run
    python main.py --reset               # wipe DB and start fresh
    python main.py --max-categories 20   # cap categories this run (testing)
    python main.py --no-export           # skip CSV/JSON at the end
"""

import argparse
import asyncio
import json
import logging
import os
import sys

from database.db import Database
from scraper.categories import CategoryQueue
from scraper.places_client import PlacesClient
from scraper.scoring import score_business
from scraper import exporter

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "database", "businesses.sqlite")
OUT_DIR = os.path.join(ROOT, "output")
LOG_DIR = os.path.join(ROOT, "logs")


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    log = logging.getLogger("parser")
    log.setLevel(logging.INFO)
    log.handlers.clear()

    fh = logging.FileHandler(os.path.join(LOG_DIR, "parser.log"), encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)

    eh = logging.FileHandler(os.path.join(LOG_DIR, "errors.log"), encoding="utf-8")
    eh.setLevel(logging.ERROR)
    eh.setFormatter(fmt)
    log.addHandler(eh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    log.addHandler(ch)
    return log


def load_config():
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    key = cfg.get("api_key") or os.environ.get(cfg.get("api_key_env", ""), "")
    cfg["api_key"] = key
    return cfg


async def run(cfg, log, max_categories=None):
    db = Database(DB_PATH)
    queue = CategoryQueue(processed=db.processed_categories())
    done_ids = db.processed_ids()
    log.info("resume: %d businesses, %d categories already done, %d queued",
             db.count(), len(db.processed_categories()), len(queue))

    bias = cfg["location_bias"]
    bias = {**bias, "hint": f'{cfg["city"]} {cfg["country"]}'}
    hp_cfg = cfg["high_priority"]
    processed_since_save = 0
    cats_this_run = 0

    async with PlacesClient(
        cfg["api_key"],
        language_code=cfg["language_code"],
        region_code=cfg["region_code"],
        concurrency=cfg["concurrency"],
        request_delay=cfg["request_delay_seconds"],
    ) as client:

        while queue:
            if max_categories and cats_this_run >= max_categories:
                log.info("hit --max-categories limit (%d)", max_categories)
                break
            term = queue.pop()
            cats_this_run += 1
            log.info("category [%d left]: %s", len(queue), term)

            ids = await client.search_ids(term, bias, cfg["max_pages_per_query"])
            new_ids = [i for i in ids if i not in done_ids]
            log.info("  found %d ids (%d new)", len(ids), len(new_ids))

            # Fetch details concurrently (semaphore lives inside the client).
            details = await asyncio.gather(
                *[client.get_details(i, cfg["max_reviews_per_business"])
                  for i in new_ids]
            )

            for b in details:
                if not b or not b.get("business_id"):
                    continue
                score_business(b, cfg["inactive_after_months"], hp_cfg)
                db.upsert(b)
                db.mark_processed(b["business_id"])
                done_ids.add(b["business_id"])
                # Recursive category discovery from this business's types.
                queue.expand_from_types(b.get("types_raw", "").split(","))
                processed_since_save += 1
                if processed_since_save >= cfg["save_interval"]:
                    db.commit()
                    processed_since_save = 0
                    log.info("  ...saved (%d total)", db.count())

            db.mark_category_done(term)
            db.commit()

    log.info("discovery complete: %d businesses total", db.count())

    if cfg.get("export_csv") or cfg.get("export_json"):
        exporter.export_all(db, OUT_DIR,
                            export_csv=cfg.get("export_csv", True),
                            export_json=cfg.get("export_json", True))
    _summary(db, log)
    db.close()


def _summary(db, log):
    rows = db.all_rows()
    total = len(rows)
    no_site = sum(1 for r in rows if not r["has_website"])
    hp = sum(1 for r in rows if r["lead_status"] == "HIGH_PRIORITY")
    log.info("=" * 48)
    log.info("TOTAL businesses     : %d", total)
    log.info("Without website      : %d", no_site)
    log.info("HIGH_PRIORITY leads  : %d", hp)
    log.info("Outputs in           : %s", OUT_DIR)
    log.info("=" * 48)


def main():
    ap = argparse.ArgumentParser(description="Local Business Discovery Engine")
    ap.add_argument("--reset", action="store_true", help="wipe DB and start fresh")
    ap.add_argument("--max-categories", type=int, default=None,
                    help="cap categories this run (useful for testing)")
    ap.add_argument("--no-export", action="store_true", help="skip exports")
    args = ap.parse_args()

    log = setup_logging()
    cfg = load_config()

    if not cfg["api_key"]:
        log.error("No API key. Set GOOGLE_MAPS_API_KEY or config.json:api_key")
        sys.exit(1)

    if args.no_export:
        cfg["export_csv"] = cfg["export_json"] = False

    if args.reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        log.info("DB reset.")

    try:
        asyncio.run(run(cfg, log, max_categories=args.max_categories))
    except KeyboardInterrupt:
        log.info("interrupted — progress saved, rerun to resume.")


if __name__ == "__main__":
    main()
