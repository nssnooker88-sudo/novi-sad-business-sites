"""Export engine — writes the five CSVs and the JSON dump."""

import json
import logging
import os

import pandas as pd

LOG = logging.getLogger("parser")

# Column order for human-friendly CSVs.
CSV_COLUMNS = [
    "business_name", "category", "lead_status", "has_website", "website",
    "phone", "email", "pib", "registration_number", "address", "rating", "review_count",
    "business_quality_score", "website_need_score",
    "purchase_probability_score", "is_active", "latest_review_date",
    "google_maps_url", "latitude", "longitude", "business_id",
]


def _df(rows):
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for col in CSV_COLUMNS:
        if col not in df.columns:
            df[col] = None
    ordered = CSV_COLUMNS + [c for c in df.columns if c not in CSV_COLUMNS]
    return df[ordered]


def export_all(db, out_dir, export_csv=True, export_json=True):
    os.makedirs(out_dir, exist_ok=True)

    if export_csv:
        _write(_df(db.all_rows()),
               os.path.join(out_dir, "businesses_all.csv"))
        _write(_df(db.no_website_rows()),
               os.path.join(out_dir, "businesses_no_website.csv"))
        _write(_df(db.high_priority_rows()),
               os.path.join(out_dir, "businesses_high_priority.csv"))
        _write(_df(db.top_leads_rows()),
               os.path.join(out_dir, "top_leads.csv"))

    if export_json:
        path = os.path.join(out_dir, "businesses.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(db.all_rows(), f, ensure_ascii=False, indent=2)
        LOG.info("wrote %s", path)


def _write(df, path):
    df.to_csv(path, index=False, encoding="utf-8")
    LOG.info("wrote %s (%d rows)", path, len(df))
