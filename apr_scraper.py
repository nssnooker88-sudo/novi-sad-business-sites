#!/usr/bin/env python3
"""
APR (apr.gov.rs) email/contact scraper.

Uses stealth headless Chromium to bypass reCAPTCHA.
Searches PrivrednaDrustva + Preduzetnici by name, fetches KontaktPodaci,
saves email to SQLite.

Usage:
    python apr_scraper.py                    # all without email
    python apr_scraper.py --scope no_website
    python apr_scraper.py --scope high_priority
    python apr_scraper.py --limit 50
"""

import argparse
import json
import os
import random
import re
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "businesses.sqlite")

SCOPE_WHERE = {
    'all':           "email IS NULL OR email = ''",
    'no_website':    "has_website = 0 AND is_active = 1 AND (email IS NULL OR email = '')",
    'high_priority': "lead_status = 'HIGH_PRIORITY' AND (email IS NULL OR email = '')",
}

EMAIL_RE = re.compile(r'[\w\.\+\-]+@[\w\.\-]+\.[a-zA-Z]{2,}')
_GOOD_TLDS = {'com', 'rs', 'net', 'org', 'info', 'biz', 'co', 'io', 'me', 'eu', 'de', 'hr', 'ba', 'mk', 'si'}
_FAKE = ('noreply', 'no-reply', 'example', 'domain', 'sentry', 'duckduckgo')


def clean_email(e):
    local = e.split('@')[0]
    tld = e.rsplit('.', 1)[-1].lower()
    if tld not in _GOOD_TLDS:
        return None
    if local.startswith('.') or local.endswith('.') or len(local) < 2:
        return None
    if any(f in e.lower() for f in _FAKE):
        return None
    return e


def search_apr(page, name, pib=None):
    """Search APR for a company and return contact email."""
    captured_responses = []

    def on_response(resp):
        if '/api/' in resp.url and 'pretraga.apr.gov.rs' in resp.url:
            try:
                captured_responses.append((resp.url, resp.json()))
            except Exception:
                pass

    page.on('response', on_response)

    try:
        # --- Search PrivrednaDrustva (companies) ---
        page.goto('https://pretraga.apr.gov.rs/search/PrivrednaDrustva/PretragaNaziva', timeout=20000)
        page.wait_for_load_state('networkidle', timeout=12000)

        # Find the name input
        inp = page.query_selector('input[name="naziv"], input[placeholder*="aziv"], input[type="text"]')
        if not inp:
            # Try waiting for React to render
            page.wait_for_selector('input', timeout=8000)
            inp = page.query_selector('input')

        if inp:
            inp.fill(name)
            page.keyboard.press('Enter')
            page.wait_for_load_state('networkidle', timeout=10000)
            time.sleep(1.5)

            # Look for company links in results
            links = page.query_selector_all('a[href*="/details/PrivrednaDrustva/"]')
            if links:
                links[0].click()
                page.wait_for_load_state('networkidle', timeout=10000)
                time.sleep(1)

                # Click KontaktPodaci tab/link
                contact_link = page.query_selector('a[href*="KontaktPodaci"], button:has-text("Kontakt"), a:has-text("Kontakt")')
                if contact_link:
                    contact_link.click()
                    page.wait_for_load_state('networkidle', timeout=8000)
                    time.sleep(1)

        # --- Also try Preduzetnici (sole proprietors) ---
        if not _find_email_in_responses(captured_responses):
            page.goto('https://pretraga.apr.gov.rs/search/Preduzetnici', timeout=15000)
            page.wait_for_load_state('networkidle', timeout=10000)
            inp2 = page.query_selector('input[name="naziv"], input[type="text"]')
            if inp2:
                inp2.fill(name)
                page.keyboard.press('Enter')
                page.wait_for_load_state('networkidle', timeout=10000)
                time.sleep(1.5)

                links2 = page.query_selector_all('a[href*="/details/Preduzetnici/"]')
                if links2:
                    links2[0].click()
                    page.wait_for_load_state('networkidle', timeout=10000)
                    time.sleep(1)
                    contact_link2 = page.query_selector('a[href*="KontaktPodaci"], button:has-text("Kontakt"), a:has-text("Kontakt")')
                    if contact_link2:
                        contact_link2.click()
                        page.wait_for_load_state('networkidle', timeout=8000)
                        time.sleep(1)

        return _find_email_in_responses(captured_responses)

    finally:
        page.remove_listener('response', on_response)


def _find_email_in_responses(responses):
    """Scan captured JSON responses for an email address."""
    for url, data in responses:
        text = json.dumps(data)
        candidates = EMAIL_RE.findall(text)
        for e in candidates:
            cleaned = clean_email(e)
            if cleaned:
                return cleaned
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scope', choices=list(SCOPE_WHERE), default='no_website')
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = (
        f"SELECT business_id, business_name, pib FROM businesses "
        f"WHERE {SCOPE_WHERE[args.scope]} "
        f"ORDER BY purchase_probability_score DESC"
    )
    if args.limit:
        sql += f' LIMIT {args.limit}'

    rows = [dict(r) for r in conn.execute(sql).fetchall()]
    print(f"Targets: {len(rows)} businesses (scope={args.scope})")

    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    found = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            locale='sr-RS',
            viewport={'width': 1280, 'height': 800},
        )
        page = ctx.new_page()
        Stealth().apply_stealth_sync(page)

        # Warm up — load main page once to get session + reCAPTCHA
        page.goto('https://pretraga.apr.gov.rs/', timeout=20000)
        page.wait_for_load_state('networkidle', timeout=15000)
        print("Browser warmed up.")

        for i, row in enumerate(rows):
            bid  = row['business_id']
            name = row['business_name'] or ''
            pib  = row.get('pib')
            print(f"[{i+1}/{len(rows)}] {name}")

            try:
                email = search_apr(page, name, pib)
            except Exception as e:
                print(f"  error: {e}")
                email = None

            if email:
                print(f"  -> APR: {email}")
                conn.execute(
                    "UPDATE businesses SET email=?, email_source='apr', updated_at=datetime('now') WHERE business_id=?",
                    (email, bid)
                )
                conn.commit()
                found += 1
            else:
                print("  -> not found")

            time.sleep(1.5 + random.random() * 1.5)

        browser.close()

    print(f"\nDone. Found {found}/{len(rows)} emails from APR.")
    conn.close()


if __name__ == '__main__':
    main()
