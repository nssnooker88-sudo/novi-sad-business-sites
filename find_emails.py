#!/usr/bin/env python3
"""
Multi-source email finder.

For every business without an email, tries in order:
  1. Their own website (contact/kontakt/o-nama pages)
  2. CompanyWall.rs (name + phone search)
  3. DuckDuckGo HTML search

Usage:
    python find_emails.py                    # all without email
    python find_emails.py --scope no_website # active, no site only
    python find_emails.py --scope high_priority
    python find_emails.py --limit 100        # cap for testing
"""

import argparse
import os
import re
import random
import sqlite3
import ssl
import time
import urllib.parse
import urllib.request

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "businesses.sqlite")

ssl_ctx = ssl._create_unverified_context()

EMAIL_RE = re.compile(r'[\w\.\+\-]+@[\w\.\-]+\.[a-zA-Z]{2,}')
_JUNK = ('png', 'jpg', 'jpeg', 'gif', 'js', 'css', 'svg', 'woff', 'ttf', 'ico', 'w3.org')
_FAKE = ('example', 'domain', 'sentry', 'yourmail', 'email@', 'test@', 'duckduckgo', 'noreply', 'no-reply')
# Only accept well-known TLDs — blocks spam domains like .plpla.or.jp
_GOOD_TLDS = {'com', 'rs', 'net', 'org', 'info', 'biz', 'co', 'io', 'me', 'eu', 'de', 'hr', 'ba', 'mk', 'si'}

CONTACT_PATHS = ['', '/contact', '/kontakt', '/kontakti', '/o-nama', '/about', '/o-nama-kontakt']


def _get(url, timeout=12):
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'sr-RS,sr;q=0.9,en-US;q=0.8',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=timeout) as r:
            charset = r.headers.get_content_charset() or 'utf-8'
            return r.read().decode(charset, errors='replace')
    except Exception:
        return None


def _clean_emails(html):
    if not html:
        return []
    # Prefer explicit mailto links
    mailtos = re.findall(r'mailto:([\w\.\+\-]+@[\w\.\-]+\.[a-zA-Z]{2,})', html, re.IGNORECASE)
    all_e = EMAIL_RE.findall(html)
    combined = mailtos + [e for e in all_e if e not in mailtos]
    result = []
    for e in combined:
        local = e.split('@')[0]
        tld = e.rsplit('.', 1)[-1].lower()
        if any(e.lower().endswith(s) for s in _JUNK):
            continue
        if any(f in e.lower() for f in _FAKE):
            continue
        if tld not in _GOOD_TLDS:
            continue
        if local.startswith('.') or local.endswith('.') or len(local) < 2:
            continue
        result.append(e)
    return result


# ---------------------------------------------------------------------------
# Source 1 — Business website
# ---------------------------------------------------------------------------
def from_website(website_url):
    if not website_url:
        return None
    base = website_url.rstrip('/')
    if not base.startswith('http'):
        base = 'https://' + base
    for path in CONTACT_PATHS:
        html = _get(base + path)
        emails = _clean_emails(html)
        if emails:
            return emails[0]
        time.sleep(0.4)
    return None


# ---------------------------------------------------------------------------
# Source 2 — CompanyWall.rs
# ---------------------------------------------------------------------------
def _companywall_profile_email(profile_path):
    html = _get('https://www.companywall.rs' + profile_path)
    emails = _clean_emails(html)
    return emails[0] if emails else None


def from_companywall(name, phone=None):
    queries = _cw_queries(name)
    for q in queries:
        encoded = urllib.parse.quote(q)
        html = _get(f'https://www.companywall.rs/pretraga?n={encoded}')
        links = re.findall(r'href="(/firma/[^"]*)"', html or '')
        links = list(dict.fromkeys(links))  # dedupe
        for link in links[:2]:
            email = _companywall_profile_email(link)
            if email:
                return email
            time.sleep(0.5 + random.random() * 0.5)
    # Fallback: search by phone last-6 digits
    if phone:
        digits = re.sub(r'[^\d]', '', phone)
        if len(digits) >= 6:
            html = _get(f'https://www.companywall.rs/pretraga?n={digits[-6:]}')
            links = re.findall(r'href="(/firma/[^"]*)"', html or '')
            for link in links[:1]:
                email = _companywall_profile_email(link)
                if email:
                    return email
    return None


def _cw_queries(name):
    clean = re.sub(r'[\-\(\)\:\,\|]', ' ', name)
    clean = re.sub(r'\s+', ' ', clean).strip()
    queries = [clean]
    if 'novi sad' not in clean.lower():
        queries.append(f'{clean} Novi Sad')
    return queries


# ---------------------------------------------------------------------------
# Source 3 — DuckDuckGo HTML
# ---------------------------------------------------------------------------
def from_duckduckgo(name):
    # Strip special chars for fallback query
    clean_name = re.sub(r'[""„\'\-\(\)\:\,\|]', ' ', name).strip()
    queries = [
        f'"{name}" Novi Sad email kontakt',
        f'{clean_name} Novi Sad "@gmail" OR "@yahoo" OR "@rs"',
    ]
    for q in queries:
        html = _get(f'https://html.duckduckgo.com/html/?q={urllib.parse.quote(q)}')
        if not html:
            continue
        text = re.sub(r'<[^>]+>', ' ', html)
        emails = _clean_emails(text)
        emails = [e for e in emails if 'duckduckgo' not in e]
        if emails:
            return emails[0]
        time.sleep(0.8)
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
SOURCES = [
    ('website',      lambda r: from_website(r['website'])),
    ('duckduckgo',   lambda r: from_duckduckgo(r['business_name'] or '')),
]

SCOPE_WHERE = {
    'all':           "email IS NULL OR email = ''",
    'no_website':    "has_website = 0 AND is_active = 1 AND (email IS NULL OR email = '')",
    'high_priority': "lead_status = 'HIGH_PRIORITY' AND (email IS NULL OR email = '')",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scope', choices=list(SCOPE_WHERE), default='all')
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = (
        "SELECT business_id, business_name, website, phone, address, lead_status "
        f"FROM businesses WHERE {SCOPE_WHERE[args.scope]} "
        "ORDER BY purchase_probability_score DESC, website_need_score DESC"
    )
    if args.limit:
        sql += f' LIMIT {args.limit}'

    rows = [dict(r) for r in conn.execute(sql).fetchall()]
    print(f"Targets: {len(rows)} businesses (scope={args.scope})\n")

    found = skipped = 0

    for i, row in enumerate(rows):
        bid  = row['business_id']
        name = row['business_name'] or '?'
        print(f"[{i+1}/{len(rows)}] {name}  [{row['lead_status']}]")

        email = None
        source = None

        for src_name, src_fn in SOURCES:
            # Skip website source if no website
            if src_name == 'website' and not row['website']:
                continue
            try:
                result = src_fn(row)
            except Exception as e:
                print(f"  {src_name}: error — {e}")
                result = None

            if result:
                email = result
                source = src_name
                break

            time.sleep(0.8 + random.random() * 1.2)

        if email:
            print(f"  -> {source}: {email}")
            conn.execute(
                "UPDATE businesses SET email=?, email_source=?, updated_at=datetime('now') WHERE business_id=?",
                (email, source, bid),
            )
            conn.commit()
            found += 1
        else:
            print("  -> not found")
            skipped += 1

        # Rate-limit between companies
        time.sleep(1.5 + random.random() * 1.5)

    print(f"\nDone. Found {found} new emails, {skipped} not found.")
    conn.close()


if __name__ == '__main__':
    main()
