"""
APR Email Enricher (Playwright edition)
========================================
Uses a headless Chromium browser to search pretraga.apr.gov.rs — the new
Serbian Business Registry portal — and extract email addresses. This avoids
the FortiWeb WAF that blocks plain HTTP clients.

Targets (in order of priority):
  - HIGH_PRIORITY leads without email          (default)
  - NO_WEBSITE leads without email             (--all-no-website)
  - Entire DB without email                    (--all)

Usage:
    python apr_email_enricher.py                   # HIGH_PRIORITY only
    python apr_email_enricher.py --all-no-website
    python apr_email_enricher.py --all
    python apr_email_enricher.py --dry-run         # print, don't save
    python apr_email_enricher.py --limit 10        # cap for testing
    python apr_email_enricher.py --visible         # show browser window
"""

import argparse
import logging
import os
import re
import sqlite3
import sys
import time
from difflib import SequenceMatcher

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
ROOT    = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "database", "businesses.sqlite")

APR_SEARCH_BD  = "https://pretraga.apr.gov.rs/searchBD"
APR_SEARCH_PRU = "https://pretraga.apr.gov.rs/searchPRU"

PAGE_DELAY      = 2.0    # seconds between businesses (be a polite guest)
MATCH_THRESHOLD = 0.50   # fuzzy-match ratio for name matching

EMAIL_RE   = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
SKIP_DOMS  = {"apr.gov.rs", "example.com", "domain.com", "email.com",
              "mail.com", "test.com"}

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


def extract_emails(text: str) -> list[str]:
    return [
        e.lower() for e in EMAIL_RE.findall(text)
        if e.split("@")[-1].lower() not in SKIP_DOMS
    ]


def best_name_match(query: str, candidates: list[str]) -> tuple[int, float]:
    q = query.lower().strip()
    best_i, best_score = 0, 0.0
    for i, c in enumerate(candidates):
        score = SequenceMatcher(None, q, c.lower().strip()).ratio()
        if score > best_score:
            best_score, best_i = score, i
    return best_i, best_score


# ---------------------------------------------------------------------------
# Playwright helpers
# ---------------------------------------------------------------------------
def wait_for_spa(page, timeout=10000):
    """Wait for the React SPA to finish mounting."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PWTimeout:
        pass


def search_apr(page, search_url: str, query: str, by_pib: bool = False) -> bool:
    """
    Navigate to APR search page, fill in the query, submit.
    Returns True if results appeared.
    """
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        wait_for_spa(page)

        if by_pib:
            # Try to find PIB input field
            pib_input = page.query_selector(
                'input[placeholder*="PIB" i], input[name*="pib" i], '
                'input[id*="pib" i], input[aria-label*="PIB" i]'
            )
            if pib_input:
                pib_input.fill(query)
                pib_input.press("Enter")
                wait_for_spa(page)
                return True

        # Default: fill the name/naziv search input
        name_input = page.query_selector(
            'input[placeholder*="naziv" i], input[placeholder*="name" i], '
            'input[name*="naziv" i], input[type="search"], '
            'input[placeholder*="pretrag" i], input[aria-label*="naziv" i]'
        )
        if not name_input:
            # fallback: first visible text input
            inputs = page.query_selector_all('input[type="text"]')
            name_input = inputs[0] if inputs else None

        if name_input:
            name_input.fill(query)
            name_input.press("Enter")
            wait_for_spa(page)
            return True

        log.debug("  no input found on %s", search_url)
        return False
    except PWTimeout:
        log.debug("  timeout searching for '%s'", query)
        return False
    except Exception as e:
        log.debug("  search error: %s", e)
        return False


def get_result_names(page) -> list[str]:
    """Return the list of business names shown in search results."""
    names = []
    # Common patterns: table rows, list items, result cards
    selectors = [
        "table tbody tr td:first-child",
        ".result-item .name",
        "[class*='result'] [class*='name']",
        "tbody tr",
    ]
    for sel in selectors:
        els = page.query_selector_all(sel)
        if els:
            names = [el.inner_text().strip() for el in els if el.inner_text().strip()]
            if names:
                break
    return names


def click_result(page, index: int = 0) -> bool:
    """Click the nth search result row/link."""
    try:
        selectors = [
            "table tbody tr",
            ".result-item",
            "[class*='result-row']",
            "[class*='ResultRow']",
        ]
        for sel in selectors:
            rows = page.query_selector_all(sel)
            if rows and index < len(rows):
                rows[index].click()
                wait_for_spa(page, timeout=15000)
                return True
        return False
    except Exception:
        return False


def extract_email_from_detail(page) -> str:
    """
    Extract email from APR detail/profile page.
    Tries: labeled fields, mailto links, then regex over full page text.
    """
    # Try mailto links first (most reliable)
    mailto_links = page.query_selector_all('a[href^="mailto:"]')
    for link in mailto_links:
        href = link.get_attribute("href") or ""
        email = href.replace("mailto:", "").split("?")[0].strip().lower()
        if email and email.split("@")[-1] not in SKIP_DOMS:
            return email

    # Try labeled field: look for row/cell after "e-mail", "email", "pošta"
    label_selectors = [
        'td:has-text("mail") + td',
        'td:has-text("Mail") + td',
        'td:has-text("е-пошта") + td',
        'td:has-text("Е-пошта") + td',
        '[class*="email"] [class*="value"]',
        '[class*="Email"] [class*="value"]',
    ]
    for sel in label_selectors:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                emails = extract_emails(text)
                if emails:
                    return emails[0]
        except Exception:
            pass

    # Fallback: regex over entire page text
    text = page.inner_text("body")
    emails = extract_emails(text)
    return emails[0] if emails else ""


# ---------------------------------------------------------------------------
# Core enrichment
# ---------------------------------------------------------------------------
def enrich_one(page, biz: dict, dry_run: bool) -> bool:
    name = biz["business_name"]
    pib  = (biz.get("pib") or "").strip()

    email_found = ""

    # Strategy 1: search by PIB if available
    if pib:
        ok = search_apr(page, APR_SEARCH_BD, pib, by_pib=True)
        if ok:
            email_found = extract_email_from_detail(page)
            if not email_found:
                # Maybe it listed results — click the first one
                names = get_result_names(page)
                if names:
                    if click_result(page, 0):
                        email_found = extract_email_from_detail(page)

    # Strategy 2: search by name (BD = companies)
    if not email_found:
        ok = search_apr(page, APR_SEARCH_BD, name, by_pib=False)
        if ok:
            names = get_result_names(page)
            if names:
                best_i, score = best_name_match(name, names)
                log.debug("  BD name match: '%s' -> '%s' (%.2f)", name, names[best_i], score)
                if score >= MATCH_THRESHOLD:
                    if click_result(page, best_i):
                        email_found = extract_email_from_detail(page)

    # Strategy 3: PRU = entrepreneurs
    if not email_found:
        ok = search_apr(page, APR_SEARCH_PRU, name, by_pib=False)
        if ok:
            names = get_result_names(page)
            if names:
                best_i, score = best_name_match(name, names)
                log.debug("  PRU name match: '%s' -> '%s' (%.2f)", name, names[best_i], score)
                if score >= MATCH_THRESHOLD:
                    if click_result(page, best_i):
                        email_found = extract_email_from_detail(page)

    if not email_found:
        return False

    log.info("  FOUND  %-42s  =>  %s", name[:42], email_found)
    if not dry_run:
        save_result(biz["business_id"], email_found, pib)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="APR Email Enricher (Playwright)")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--all-no-website", action="store_true")
    grp.add_argument("--all",            action="store_true")
    ap.add_argument("--dry-run",  action="store_true", help="print, don't save")
    ap.add_argument("--limit",    type=int, default=None)
    ap.add_argument("--visible",  action="store_true", help="show browser window")
    args = ap.parse_args()

    mode = "all" if args.all else "all_no_website" if args.all_no_website else "high_priority"
    targets = get_targets(mode)
    if args.limit:
        targets = targets[: args.limit]

    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    log.info("Targets: %d  |  mode: %s  |  dry_run: %s", len(targets), mode, args.dry_run)

    found = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.visible)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="sr-RS",
            ignore_https_errors=True,
        )
        page = context.new_page()

        # Warm up: visit APR home once to establish session / pass WAF challenge
        log.info("Warming up session on APR...")
        try:
            page.goto("https://pretraga.apr.gov.rs", wait_until="domcontentloaded", timeout=30000)
            wait_for_spa(page)
            time.sleep(1)
        except Exception as e:
            log.warning("Warmup failed: %s", e)

        for i, biz in enumerate(targets, 1):
            log.info("[%d/%d] %s  (PIB: %s)",
                     i, len(targets),
                     biz["business_name"],
                     biz.get("pib") or "-")

            ok = enrich_one(page, biz, args.dry_run)
            if ok:
                found += 1

            time.sleep(PAGE_DELAY)

        browser.close()

    log.info("=" * 54)
    log.info("Done — emails found: %d / %d", found, len(targets))
    if args.dry_run:
        log.info("DRY RUN — nothing saved to DB.")


if __name__ == "__main__":
    main()
