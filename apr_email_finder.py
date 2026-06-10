#!/usr/bin/env python3
"""
APR email finder via 2captcha.

Flow per company:
  1. Solve reCAPTCHA via 2captcha (token reused up to 110s across searches)
  2. GET /api/search/PrivrednaDrustva/PretragaNaziva?naziv=...  (G-TOKEN header)
  3. GET /api/details/PrivrednaDrustva/{id}/KontaktPodaci
  4. Also try Preduzetnici (sole proprietors) if company search fails
  5. Save email to SQLite

Usage:
    python apr_email_finder.py --key 991f5cb37c37cd181c3b769f7cd006bb
    python apr_email_finder.py --key ... --scope high_priority
    python apr_email_finder.py --key ... --scope no_website --limit 100
"""

import argparse
import http.cookiejar
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import ssl
import random

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "businesses.sqlite")

RECAPTCHA_SITEKEY    = "6LcO8psUAAAAAIc1rYcmQPWJLJ0dcqfn79IvUi-5"
RECAPTCHA_ACTION     = "search"   # reCAPTCHA v3 action name used by APR
APR_BASE             = "https://pretraga.apr.gov.rs"
APR_API              = f"{APR_BASE}/api"

ssl_ctx = ssl._create_unverified_context()

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


# ---------------------------------------------------------------------------
# Session / CSRF helpers
# ---------------------------------------------------------------------------

class Session:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl_ctx),
            urllib.request.HTTPCookieProcessor(self.cj),
        )
        self.ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        self.csrf_token = ""

    def _req(self, url, accept="application/json", extra_headers=None):
        headers = {
            "User-Agent": self.ua,
            "Accept": accept,
            "Referer": APR_BASE + "/",
        }
        if extra_headers:
            headers.update(extra_headers)
        return urllib.request.Request(url, headers=headers)

    def init_session(self):
        """Load main page (gets cookies) then extract CSRF token."""
        self.opener.open(self._req(APR_BASE + "/", accept="text/html"), timeout=12).read()
        with self.opener.open(self._req(APR_BASE + "/fwb/csrf_check_req_check.js", accept="*/*"), timeout=10) as r:
            js = r.read().decode("utf-8", errors="replace")
        m = re.search(r"csrftoken\s*=\s*'([^']+)'", js)
        self.csrf_token = m.group(1) if m else ""
        print(f"  Session ready. CSRF: {self.csrf_token[:20]}...")

    def get_json(self, path, g_token, referer=None):
        ts = int(time.time() * 1000)
        sep = "&" if "?" in path else "?"
        url = f"{APR_API}{path}{sep}_={ts}&tknfv={urllib.parse.quote(self.csrf_token)}"
        try:
            with self.opener.open(self._req(url, extra_headers={
                "g-token": g_token,
                "Origin": APR_BASE,
                "Referer": referer or (APR_BASE + "/"),
                "Accept-Language": "sr-RS,sr;q=0.9,en-US;q=0.8,en;q=0.7",
                "X-Requested-With": "XMLHttpRequest",
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }), timeout=15) as r:
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 422 and "data not found" in body:
                raise NoResultsError("no results")
            if "reCAPTCHA" in body:
                raise RecaptchaError("reCAPTCHA expired")
            raise


class RecaptchaError(Exception):
    pass

class NoResultsError(Exception):
    pass


# ---------------------------------------------------------------------------
# 2captcha integration
# ---------------------------------------------------------------------------

def solve_recaptcha(api_key, max_wait=120):
    """Submit reCAPTCHA v3 task to 2captcha, return g-recaptcha-response."""
    print("  Solving reCAPTCHA v3 via 2captcha...", end=" ", flush=True)

    # Submit task — v3 with action name
    submit_url = (
        "http://2captcha.com/in.php"
        f"?key={api_key}"
        f"&method=userrecaptcha"
        f"&version=v3"
        f"&action={RECAPTCHA_ACTION}"
        f"&min_score=0.3"
        f"&googlekey={RECAPTCHA_SITEKEY}"
        f"&pageurl={urllib.parse.quote(APR_BASE + '/')}"
        f"&json=1"
    )
    with urllib.request.urlopen(submit_url, timeout=15) as r:
        resp = json.loads(r.read().decode())
    if resp.get("status") != 1:
        raise RuntimeError(f"2captcha submit error: {resp}")
    task_id = resp["request"]

    # Poll for result
    get_url = f"http://2captcha.com/res.php?key={api_key}&action=get&id={task_id}&json=1"
    elapsed = 0
    time.sleep(20)  # initial wait
    while elapsed < max_wait:
        with urllib.request.urlopen(get_url, timeout=10) as r:
            result = json.loads(r.read().decode())
        if result.get("status") == 1:
            token = result["request"]
            print(f"got token ({len(token)} chars)")
            return token
        if result.get("request") == "CAPCHA_NOT_READY":
            print(".", end="", flush=True)
            time.sleep(5)
            elapsed += 5
        else:
            raise RuntimeError(f"2captcha error: {result}")
    raise RuntimeError("2captcha timed out")


# ---------------------------------------------------------------------------
# APR search logic
# ---------------------------------------------------------------------------

# Generic prefix words to strip when building fallback search terms
_GENERIC = {
    'pekara', 'restoran', 'kafic', 'kafana', 'hotel', 'hostel', 'apartman', 'stan',
    'salon', 'frizerski', 'kozmeticki', 'studio', 'centar', 'servis', 'auto',
    'taxi', 'prevoz', 'agencija', 'kancelarija', 'ordinacija', 'ambulanta',
    'advokat', 'doktor', 'dr', 'bar', 'caffe', 'cafe', 'picerija', 'pizza',
    'shop', 'prodavnica', 'market', 'gym', 'fitness', 'spa', 'wellness',
    'vulkanizer', 'keramicar', 'elektricar', 'vodoinstalater',
    'turisticka', 'rent', 'car', 'ns', 'novi', 'sad',
}


def _name_variants(name):
    """Return list of search terms to try, from most to least specific."""
    variants = [name]
    # Try each individual word that isn't a generic term
    words = re.split(r'[\s\-\.\/\,\(\)]+', name)
    keywords = [w for w in words if len(w) >= 4 and w.lower() not in _GENERIC]
    if keywords:
        # Multi-keyword: first two unique words
        if len(keywords) >= 2:
            variants.append(' '.join(keywords[:2]))
        # Single best keyword (longest non-generic word)
        best = max(keywords, key=len)
        if best != name and best not in variants:
            variants.append(best)
    return variants


def search_apr(session, name, g_token):
    """Search all entities by name. Tries multiple name variants. Returns list of hits."""
    for variant in _name_variants(name):
        enc = urllib.parse.quote(variant)
        try:
            raw = session.get_json(f"/search?poslovno_ime={enc}&registar_id=0&status_id=0", g_token)
        except NoResultsError:
            continue  # try next variant
        if not raw:
            continue
        data = json.loads(raw)
        if isinstance(data, dict):
            items = data.get("data", [])
            if isinstance(items, list) and items:
                print(f"    found via: '{variant}'")
                return items
    return []


_DELETED_STATUS = ("брисан", "obrisan", "deleted", "likvidiran", "u stečaju")


def _is_deleted(hit):
    """Return True if the APR search result is for a deleted/inactive entity."""
    result = hit.get("result") or {}
    status = (result.get("statusNameDescription") or "").lower()
    return any(d in status for d in _DELETED_STATUS)


def _extract_emails(raw):
    if not raw:
        return []
    try:
        data = json.loads(raw)
        text = json.dumps(data)
    except Exception:
        text = raw
    result = []
    for e in EMAIL_RE.findall(text):
        cleaned = clean_email(e)
        if cleaned:
            result.append(cleaned)
    return result


def get_detail(session, detail_url, g_token, debug=False):
    """Fetch full detail for a hit. Returns (email_or_None, raw, detail_page_url)."""
    path = detail_url.replace("/api", "", 1)
    detail_page_url = APR_BASE + path
    try:
        raw = session.get_json(path, g_token, referer=APR_BASE + "/")
        if debug:
            print(f"    DETAIL: {raw[:600]}")
        emails = _extract_emails(raw)
        if emails:
            return emails[0], raw, detail_page_url
        return None, raw, detail_page_url
    except Exception as e:
        return None, None, APR_BASE + "/"


def get_contact(session, detail_url, g_token, detail_page_url=None, debug=False):
    """Fetch KontaktPodaci tab for a hit. WAF allows ?tab= form; /KontaktPodaci sub-path is blocked."""
    path = detail_url.replace("/api", "", 1)
    sep = "&" if "?" in path else "?"
    contact_path = f"{path}{sep}tab=KontaktPodaci"
    referer = detail_page_url or (APR_BASE + "/")
    try:
        raw = session.get_json(contact_path, g_token, referer=referer)
        if debug:
            print(f"    CONTACT: {raw[:600]}")
        emails = _extract_emails(raw)
        if emails:
            return emails[0]
    except Exception as e:
        if debug:
            print(f"    CONTACT err: {e}")
    return None


def find_email_apr(session, name, g_token):
    """Search APR, fetch contact data for each active hit."""
    try:
        results = search_apr(session, name, g_token)
        active = [h for h in results if not _is_deleted(h)]
        print(f"  APR hits: {len(results)} ({len(active)} active)")
        debug = len(active) <= 3  # verbose only when few candidates
        for hit in active[:3]:
            detail_url = (hit.get("result") or {}).get("url")
            if not detail_url:
                continue
            # 1. Get main detail (sometimes has email)
            email, raw, detail_page_url = get_detail(session, detail_url, g_token, debug=debug)
            if email:
                return email
            # 2. Try KontaktPodaci tab
            email = get_contact(session, detail_url, g_token, detail_page_url, debug=debug)
            if email:
                return email
            time.sleep(0.5)
    except RecaptchaError:
        raise
    except Exception as e:
        print(f"  search error: {e}")

    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key",   required=True, help="2captcha API key")
    ap.add_argument("--scope", choices=list(SCOPE_WHERE), default="no_website")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    sql = (
        f"SELECT business_id, business_name FROM businesses "
        f"WHERE {SCOPE_WHERE[args.scope]} "
        f"ORDER BY purchase_probability_score DESC"
    )
    if args.limit:
        sql += f" LIMIT {args.limit}"

    rows = [dict(r) for r in conn.execute(sql).fetchall()]
    print(f"Targets: {len(rows)} businesses (scope={args.scope})\n")

    session = Session()
    session.init_session()

    g_token = None
    token_born = 0
    TOKEN_TTL = 100  # refresh token before ~120s Google expiry

    found = 0

    for i, row in enumerate(rows):
        bid  = row["business_id"]
        name = row["business_name"] or ""
        print(f"[{i+1}/{len(rows)}] {name}")

        if g_token is None or (time.time() - token_born) > TOKEN_TTL:
            try:
                g_token = solve_recaptcha(args.key)
                token_born = time.time()
            except Exception as e:
                print(f"  2captcha error: {e}. Retrying in 30s...")
                time.sleep(30)
                try:
                    g_token = solve_recaptcha(args.key)
                    token_born = time.time()
                except Exception as e2:
                    print(f"  Failed: {e2}. Skipping.")
                    continue

        try:
            email = find_email_apr(session, name, g_token)
        except RecaptchaError:
            print("  reCAPTCHA expired, refreshing...")
            g_token = None
            continue
        except Exception as e:
            print(f"  error: {e}")
            email = None

        if email:
            print(f"  -> APR: {email}")
            conn.execute(
                "UPDATE businesses SET email=?, email_source='apr', updated_at=datetime('now') WHERE business_id=?",
                (email, bid),
            )
            conn.commit()
            found += 1
        else:
            print("  -> not found")

        time.sleep(0.5 + random.random() * 0.5)

    print(f"\nDone. Found {found}/{len(rows)} emails from APR.")
    conn.close()


if __name__ == "__main__":
    main()
