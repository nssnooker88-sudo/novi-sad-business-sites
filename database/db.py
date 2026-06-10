"""
SQLite persistence layer.

- businesses table keyed by business_id (Google place id) — upsert, no dupes.
- processed table — cache of place ids already fully fetched, for resume.
- categories table — search terms already processed, for resume.
"""

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    business_id                 TEXT PRIMARY KEY,
    google_maps_url             TEXT,
    business_name               TEXT,
    category                    TEXT,
    subcategory                 TEXT,
    phone                       TEXT,
    address                     TEXT,
    rating                      REAL,
    review_count                INTEGER,
    website                     TEXT,
    has_website                 INTEGER,
    is_active                   INTEGER,
    latest_review_date          TEXT,
    business_quality_score      INTEGER,
    website_need_score          INTEGER,
    purchase_probability_score  INTEGER,
    lead_status                 TEXT,
    latitude                    REAL,
    longitude                   REAL,
    description                 TEXT,
    reviews_text                TEXT,
    photo_count                 INTEGER,
    opening_hours               TEXT,
    business_status             TEXT,
    types_raw                   TEXT,
    pib                         TEXT,
    registration_number         TEXT,
    email                       TEXT,
    created_at                  TEXT,
    updated_at                  TEXT
);

CREATE TABLE IF NOT EXISTS processed (
    business_id TEXT PRIMARY KEY,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    term TEXT PRIMARY KEY,
    processed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_lead_status ON businesses(lead_status);
CREATE INDEX IF NOT EXISTS idx_has_website ON businesses(has_website);
"""

# Columns that map 1:1 from a business dict into the table.
_COLUMNS = [
    "business_id", "google_maps_url", "business_name", "category", "subcategory",
    "phone", "address", "rating", "review_count", "website", "has_website",
    "is_active", "latest_review_date", "business_quality_score",
    "website_need_score", "purchase_probability_score", "lead_status",
    "latitude", "longitude", "description", "reviews_text", "photo_count",
    "opening_hours", "business_status", "types_raw", "pib", "registration_number", "email", "created_at", "updated_at",
]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        
        # Run migrations for existing DBs
        for col in ["pib", "registration_number", "email"]:
            try:
                self.conn.execute(f"ALTER TABLE businesses ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    # --- resume helpers ------------------------------------------------------
    def processed_ids(self):
        rows = self.conn.execute("SELECT business_id FROM processed").fetchall()
        return {r["business_id"] for r in rows}

    def processed_categories(self):
        rows = self.conn.execute("SELECT term FROM categories").fetchall()
        return [r["term"] for r in rows]

    def mark_processed(self, business_id):
        self.conn.execute(
            "INSERT OR REPLACE INTO processed(business_id, processed_at) VALUES (?, ?)",
            (business_id, _now_iso()),
        )

    def mark_category_done(self, term):
        self.conn.execute(
            "INSERT OR REPLACE INTO categories(term, processed_at) VALUES (?, ?)",
            (term, _now_iso()),
        )

    # --- writes --------------------------------------------------------------
    def upsert(self, b: dict):
        existing = self.conn.execute(
            "SELECT created_at FROM businesses WHERE business_id = ?",
            (b["business_id"],),
        ).fetchone()
        now = _now_iso()
        b["created_at"] = existing["created_at"] if existing else now
        b["updated_at"] = now

        values = [b.get(col) for col in _COLUMNS]
        # SQLite stores bools as ints.
        values = [int(v) if isinstance(v, bool) else v for v in values]

        placeholders = ",".join("?" for _ in _COLUMNS)
        cols = ",".join(_COLUMNS)
        self.conn.execute(
            f"INSERT OR REPLACE INTO businesses ({cols}) VALUES ({placeholders})",
            values,
        )

    def commit(self):
        self.conn.commit()

    # --- reads / exports -----------------------------------------------------
    def all_rows(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM businesses ORDER BY business_name"
        ).fetchall()]

    def no_website_rows(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM businesses WHERE has_website = 0 ORDER BY business_name"
        ).fetchall()]

    def high_priority_rows(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM businesses WHERE lead_status = 'HIGH_PRIORITY' "
            "ORDER BY purchase_probability_score DESC"
        ).fetchall()]

    def top_leads_rows(self, limit=None):
        sql = (
            "SELECT * FROM businesses "
            "WHERE has_website = 0 AND is_active = 1 "
            "ORDER BY purchase_probability_score DESC, "
            "website_need_score DESC, business_quality_score DESC"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [dict(r) for r in self.conn.execute(sql).fetchall()]

    def count(self):
        return self.conn.execute("SELECT COUNT(*) c FROM businesses").fetchone()["c"]

    def close(self):
        self.conn.commit()
        self.conn.close()
