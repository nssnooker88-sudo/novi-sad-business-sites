# Local Business Discovery Engine

Discovers businesses in Novi Sad via the **Google Places API (New)**, scores
them as website-sales leads, stores everything in SQLite, and exports ranked
CSV/JSON datasets for a downstream website-generation pipeline.

## Setup

```bash
pip install -r requirements.txt

# Get a key: console.cloud.google.com -> enable "Places API (New)" -> create key
export GOOGLE_MAPS_API_KEY="your_key_here"     # or paste into config.json -> api_key
```

## Run

```bash
python main.py                    # run / resume
python main.py --reset            # wipe DB, start fresh
python main.py --max-categories 5 # small test run first (cheap, ~5 queries)
python main.py --no-export        # skip CSV/JSON at the end
```

Start with `--max-categories 5` to confirm your key works before the full run.

## Outputs (`output/`)

| File | Contents |
|------|----------|
| `businesses_all.csv` | everything found |
| `businesses_no_website.csv` | `has_website = false` |
| `businesses_high_priority.csv` | `lead_status = HIGH_PRIORITY` |
| `top_leads.csv` | active + no-website, ranked by purchase → need → quality |
| `businesses.json` | full JSON dump |

Lead is **HIGH_PRIORITY** when: no website **and** active **and**
`website_need_score > 70` **and** `purchase_probability_score > 70`.

## Resume

Progress is saved every `save_interval` businesses. Processed place ids and
finished categories are cached in SQLite, so rerunning continues where it
stopped and never re-fetches a completed business (use `--reset` to force).

## Two hard limits of the official API (read this)

1. **Max 5 reviews per place.** Google's New Places API returns at most 5
   reviews regardless of `max_reviews_per_business`. Enough for activity /
   latest-review signals; `reviews_text` is just shorter than 50.
2. **Max ~60 results per search query** (20 × 3 pages). Coverage comes from
   running many category queries + recursive category discovery, not from one
   big search. To go deeper, split `location_bias` into a grid of smaller
   circles across the city and run per cell.

## Cost (as of 2025+ pricing)

Google dropped the flat $200/month credit on 1 Mar 2025. Now each SKU has a
free monthly cap: Place Details / Text Search (New) are **Pro** SKUs with
~5,000 free events/month each. New Cloud accounts also get a $300 / 90-day
trial. A one-time Novi Sad sweep (a few thousand places) typically lands inside
the free cap + trial. Keep the field masks in `places_client.py` lean —
requesting extra field groups bumps you into pricier tiers.

## Structure

```
main.py                 CLI: orchestration, logging, resume, exports
config.json             city, location bias, limits, scoring thresholds
requirements.txt
database/db.py          SQLite schema, upsert, dedupe, resume cache, exports
scraper/places_client.py  async Places API (New) client: search + details
scraper/categories.py   seed list + recursive category queue
scraper/scoring.py      is_active + 3 scores + lead classification (pure fns)
scraper/exporter.py     CSV + JSON writers
```

## Tuning the scoring

All scoring is in `scraper/scoring.py` as pure functions:
- `_NEED_KEYWORDS` — category → website-need score map. Add Serbian terms or
  adjust weights here.
- `business_quality_score` / `purchase_probability_score` — weightings are
  commented inline.
