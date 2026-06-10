"""
APR Email Enricher
==================
Searches the Serbian Business Registry (APR, apr.gov.rs) for email addresses
and writes them back into the SQLite database.

Strategy:
  1. For businesses with a PIB already in the DB → look up directly by PIB.
  2. For the rest → search APR by business name.

Targets (in order of priority):
  - HIGH_PRIORITY leads without email          (default)
  - NO_WEBSITE leads without email             (--all-no-website)
  - Entire DB without email                    (--all)

Usage:
    python apr_email_enricher.py                  # HIGH_PRIORITY only
    python apr_email_enricher.py --all-no-website
    python apr_email_enricher.py --all
    python apr_email_enricher.py --dry-run        # print, don't save
    python apr_email_enricher.py --limit 10       # cap for testing
"""

import argparse
import logging
import os
import re
import sqlite3
import ssl
import sys
import time
import urllib3
from difflib import SequenceMatcher

import requests
import urllib3.contrib.pyopenssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from bs4 import BeautifulSoup

urllib3.disable_warnings()


class NoVerifyAdapter(HTTPAdapter):
    """HTTP adapter that uses a bare SSL context — no Windows cert store loaded."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        self.poolmanager = PoolManager(*args, **kwargs)

# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "database", "businesses.sqlite")

APR_BASE = "https://www.apr.gov.rs"
APR_SEARCH = f"{APR_BASE}/reg/skr/skrHome.aspx"
APR_DETAIL = f"{APR_BASE}/reg/skr/skrIndividualResult.aspx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_DELAY   = 1.5    # seconds between APR requests
MATCH_THRESHOLD = 0.50   # minimum fuzzy-match ratio to trust a name result

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
SKIP_DOMAINS = {"apr.gov.rs", "example.com", "domain.com", "email.com",
                "mail.com", "test.com", "yourcompany.com"}

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(ROOT, "logs", "apr_enricher.log"), encoding="utf-8"
        ),
    ],
)
log = logging.getLogger("apr")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_targets(mode: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if mode == "high_priority":
        sql = (
            "SELECT business_id, business_name, pib, registration_number, phone "
            "FROM businesses "
            "WHERE lead_status = 'HIGH_PRIORITY' AND (email IS NULL OR email = '') "
            "ORDER BY purchase_probability_score DESC"
        )
    elif mode == "all_no_website":
        sql = (
            "SELECT business_id, business_name, pib, registration_number, phone "
            "FROM businesses "
            "WHERE has_website = 0 AND is_active = 1 AND (email IS NULL OR email = '') "
            "ORDER BY purchase_probability_score DESC"
        )
    else:
        sql = (
            "SELECT business_id, business_name, pib, registration_number, phone "
            "FROM businesses WHERE email IS NULL OR email = '' "
            "ORDER BY purchase_probability_score DESC"
        )
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_result(business_id: str, email: str, pib: str = "", reg_num: str = ""):
    conn = sqlite3.connect(DB_PATH)
    parts, vals = ["email = ?"], [email]
    if pib:
        parts.append("pib = ?"); vals.append(pib)
    if reg_num:
        parts.append("registration_number = ?"); vals.append(reg_num)
    vals.append(business_id)
    conn.execute(f"UPDATE businesses SET {', '.join(parts)} WHERE business_id = ?", vals)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------
def get_html(session: requests.Session, url: str, params: dict = None) -> str:
    try:
        r = session.get(url, params=params, headers=HEADERS, verify=False, timeout=20)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return r.text
    except Exception as e:
        log.debug("HTTP error %s %s: %s", url, params, e)
        return ""


def extract_emails(html: str) -> list[str]:
    found = EMAIL_RE.findall(html)
    return [
        e.lower() for e in found
        if e.split("@")[-1].lower() not in SKIP_DOMAINS
    ]


def parse_search_results(html: str) -> list[dict]:
    """Parse APR search results table → list of {name, mb, pib, url}."""
    soup = BeautifulSoup(html, "lxml")
    results = []
    # APR renders results in a table — find by content heuristic
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        for tr in rows[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if not cells:
                continue
            link_tag = tr.find("a", href=True)
            href = link_tag["href"] if link_tag else None
            url = (APR_BASE + href) if href and href.startswith("/") else href
            name = cells[0] if cells else ""
            mb = next((c for c in cells if re.match(r"^\d{8}$", c)), "")
            pib = next((c for c in cells if re.match(r"^\d{9}$", c)), "")
            if name:
                results.append({"name": name, "mb": mb, "pib": pib, "url": url})
    return results


def best_match(query: str, results: list[dict]) -> dict | None:
    q = query.lower().strip()
    best, best_score = None, 0.0
    for r in results:
        score = SequenceMatcher(None, q, r["name"].lower()).ratio()
        if score > best_score:
            best_score, best = score, r
    return best if best and best_score >= MATCH_THRESHOLD else None


# ---------------------------------------------------------------------------
# APR lookup strategies
# ---------------------------------------------------------------------------
def lookup_by_mb(session: requests.Session, mb: str) -> str:
    """Direct detail page by registration number (MB)."""
    return get_html(session, APR_DETAIL, {"Reg": "BDP", "RegistracijaBroj": mb})


def lookup_by_pib(session: requests.Session, pib: str) -> tuple[str, str, str]:
    """
    Search APR by PIB.
    Returns (html_of_detail_page, found_pib, found_mb).
    """
    html = get_html(session, APR_SEARCH, {"reg": "BDP", "PIB": pib, "showType": "1"})
    # If APR returned a detail page directly (contains the company info)
    if "PIB:" in html or "Poreski" in html or "poreski" in html:
        return html, pib, ""
    # Otherwise parse the search result list
    results = parse_search_results(html)
    if results and results[0].get("url"):
        detail_html = get_html(session, results[0]["url"])
        return detail_html, results[0].get("pib", pib), results[0].get("mb", "")
    return html, pib, ""


def search_by_name(session: requests.Session, name: str) -> tuple[str, str, str]:
    """
    Search APR by business name.
    Returns (html_of_best_match_detail, pib, mb) or ("", "", "").
    """
    for reg in ("BDP", "PR"):
        html = get_html(session, APR_SEARCH, {"reg": reg, "Naziv": name, "showType": "1"})
        results = parse_search_results(html)
        match = best_match(name, results)
        if match:
            log.debug("  name match ratio OK: '%s' → '%s'", name, match["name"])
            detail_html = ""
            if match.get("url"):
                detail_html = get_html(session, match["url"])
            return detail_html or html, match.get("pib", ""), match.get("mb", "")
        time.sleep(0.5)
    return "", "", ""


# ---------------------------------------------------------------------------
# Per-business enrichment
# ---------------------------------------------------------------------------
def enrich_one(session: requests.Session, biz: dict, dry_run: bool) -> bool:
    name = biz["business_name"]
    pib  = (biz.get("pib") or "").strip()
    mb   = (biz.get("registration_number") or "").strip()

    html, found_pib, found_mb = "", pib, mb

    if mb:
        html = lookup_by_mb(session, mb)
        found_mb = mb
    elif pib:
        html, found_pib, found_mb = lookup_by_pib(session, pib)
    else:
        html, found_pib, found_mb = search_by_name(session, name)

    if not html:
        log.debug("  no APR data for '%s'", name)
        return False

    emails = extract_emails(html)
    if not emails:
        log.debug("  no email in APR page for '%s'", name)
        return False

    email = emails[0]
    log.info("  FOUND  %-42s  =>  %s", name[:42], email)

    if not dry_run:
        save_result(biz["business_id"], email, found_pib, found_mb)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="APR Email Enricher")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--all-no-website", action="store_true")
    grp.add_argument("--all",            action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="print results but don't write to DB")
    ap.add_argument("--limit", type=int, default=None,
                    help="max businesses to process (useful for testing)")
    args = ap.parse_args()

    mode = "all" if args.all else "all_no_website" if args.all_no_website else "high_priority"

    targets = get_targets(mode)
    if args.limit:
        targets = targets[: args.limit]

    log.info("Targets: %d  |  mode: %s  |  dry_run: %s", len(targets), mode, args.dry_run)

    session = requests.Session()
    found = 0

    for i, biz in enumerate(targets, 1):
        log.info("[%d/%d] %s  (PIB: %s  MB: %s)",
                 i, len(targets),
                 biz["business_name"],
                 biz.get("pib") or "-",
                 biz.get("registration_number") or "-")

        ok = enrich_one(session, biz, args.dry_run)
        if ok:
            found += 1
        time.sleep(REQUEST_DELAY)

    log.info("=" * 54)
    log.info("Done — emails found: %d / %d", found, len(targets))
    if args.dry_run:
        log.info("DRY RUN — nothing saved to DB.")


if __name__ == "__main__":
    main()
