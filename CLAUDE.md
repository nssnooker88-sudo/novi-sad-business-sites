# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (use the local venv)
source .venv/bin/activate
pip install -r requirements.txt

# Set the API key (or put it directly in config.json -> api_key)
export GOOGLE_MAPS_API_KEY="your_key_here"

# Run / resume discovery
python main.py

# Common flags
python main.py --max-categories 5   # cheap test run (~5 API queries)
python main.py --reset               # wipe DB and start fresh
python main.py --no-export           # skip CSV/JSON export at the end

# Phase 2: enrich HIGH_PRIORITY leads with PIB/MB/email from CompanyWall
python enrich_leads.py

# Phase 3: merge datasets and generate website prompt JSON
python enrichment_pipeline.py
```

No test suite exists. Scoring logic in `scraper/scoring.py` is pure functions — run them directly in the REPL to verify changes.

## Architecture

The project is a **two-stage lead-generation pipeline** targeting Novi Sad businesses that lack a website.

### Stage 1 — Discovery (`main.py`)

`main.py` is the CLI entry point. It orchestrates:

1. **CategoryQueue** (`scraper/categories.py`) — starts from `SEED_CATEGORIES` and expands recursively. When a discovered business exposes a Google place type not yet searched, that type is enqueued as a new search term. Processed terms are cached in the `categories` SQLite table so runs resume.

2. **PlacesClient** (`scraper/places_client.py`) — async client for the Google Places API v1 (New). Two calls per business: `searchText` to get place IDs, `places/{id}` for full details. Field masks are kept minimal — adding fields here bumps requests into pricier SKU tiers. Reviews are hard-capped at 5 by Google regardless of config.

3. **Scoring** (`scraper/scoring.py`) — pure functions, no I/O. Three independent scores (0–100): `business_quality_score` (reviews, rating, completeness, recency), `website_need_score` (keyword map against category/types), `purchase_probability_score` (composite of the other two + has_website flag). A business is `HIGH_PRIORITY` when active, has no website, and both `website_need_score` and `purchase_probability_score` exceed the thresholds in `config.json` (default 70).

4. **Database** (`database/db.py`) — SQLite with three tables: `businesses` (full records, keyed by Google place ID), `processed` (resume cache of fetched IDs), `categories` (resume cache of searched terms). `upsert` preserves `created_at` on re-fetch. Schema migrations for new columns run automatically at startup via `ALTER TABLE … ADD COLUMN` wrapped in try/except.

5. **Exporter** (`scraper/exporter.py`) — writes four CSVs and one JSON to `output/`. Column order is defined by `CSV_COLUMNS`.

### Stage 2 — Enrichment

- **`enrich_leads.py`** — scrapes [companywall.rs](https://www.companywall.rs) (Serbian business registry) to add PIB (tax ID), registration number, and email to `HIGH_PRIORITY` rows in the SQLite DB. Uses fuzzy name matching with `difflib`. Has a hardcoded absolute `DB_PATH` — update this if the project moves.

- **`enrichment_pipeline.py`** — merges three datasets (SQLite DB, an email CSV, a research CSV) and generates per-business website prompt JSON in `output/unified_companies.json`. Uses an archetype system (`ARCHETYPE_CONFIG` dict) that maps business categories to website design styles, CTAs, and image guidance.

### Configuration (`config.json`)

The single config file controls location bias (lat/lng/radius), API key, concurrency, scoring thresholds, and export flags. The API key can be overridden at runtime via the `GOOGLE_MAPS_API_KEY` env var.

### Coverage limit

Each search query returns at most ~60 results (20 × 3 pages). To expand coverage beyond what category breadth provides, split `location_bias` into a grid of smaller circles and run per cell.
