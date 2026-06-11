"""Debug: extract APR email from PIB response, find name-search endpoint."""
import http.cookiejar, json, re, ssl, sys, urllib.request
from urllib.parse import urlencode

sys.stdout.reconfigure(encoding="utf-8")
ctx = ssl._create_unverified_context()
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=ctx),
    urllib.request.HTTPCookieProcessor(cj),
)

BASE = "https://pretraga.apr.gov.rs"

HEADERS_HTML = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
}
HEADERS_JSON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
    "Referer": "https://pretraga.apr.gov.rs/searchBD",
}


def fetch(url, params=None, headers=None):
    h = headers or HEADERS_HTML
    full_url = (url + "?" + urlencode(params)) if params else url
    req = urllib.request.Request(full_url, headers=h)
    try:
        with opener.open(req, timeout=25) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            print(f"  GET {full_url[:100]}  -> {resp.status}  len={len(raw)}")
            try:
                return json.loads(raw)
            except Exception:
                return raw
    except urllib.error.HTTPError as e:
        print(f"  GET {full_url[:100]}  -> HTTP {e.code}")
        return None
    except Exception as e:
        print(f"  GET {full_url[:100]}  -> ERROR: {e}")
        return None


# Prime session
fetch(BASE, headers=HEADERS_HTML)
fetch(f"{BASE}/searchBD", headers=HEADERS_HTML)

# 1) Full response from PIB search
print("\n=== PIB 115210171 (The Pub) full response ===")
r = fetch(f"{BASE}/api/BD/search", params={"pib": "115210171"}, headers=HEADERS_JSON)
print(json.dumps(r, indent=2, ensure_ascii=False) if isinstance(r, (dict,list)) else r)

# 2) PIB search for Radio Cafe (pib 115147664)
print("\n=== PIB 115147664 (Radio Cafe) ===")
r2 = fetch(f"{BASE}/api/BD/search", params={"pib": "115147664"}, headers=HEADERS_JSON)
print(json.dumps(r2, indent=2, ensure_ascii=False) if isinstance(r2, (dict,list)) else r2)

# 3) Try name-based search with different param names  (needs session cookies)
print("\n=== Name search attempts ===")
for p in [
    {"naziv": "Pekara Krosti"},
    {"name": "Pekara Krosti"},
    {"searchNaziv": "Pekara"},
    {"searchTerm": "Pekara"},
    {"filter": "Pekara"},
    {"q": "Pekara"},
]:
    r3 = fetch(f"{BASE}/api/BD/search", params=p, headers=HEADERS_JSON)
    if r3 and r3 != {"title": "404 Not Found"}:
        print(f"  HIT with params {p}: {str(r3)[:200]}")

# 4) Try /api/BD/searchByName  /api/BD/list  etc.
print("\n=== Alternative BD endpoints ===")
for ep in [
    "/api/BD/searchByName",
    "/api/BD/list",
    "/api/BD/pretraga",
    "/api/BD/find",
    "/api/BD/getAll",
    "/api/BD/searchNaziv",
    "/api/BD/naziv",
    "/api/PRU/search",
    "/api/PRU/search",
]:
    fetch(f"{BASE}{ep}", params={"naziv": "Pekara"}, headers=HEADERS_JSON)

# 5) If we got an ID from the PIB lookup, try detail endpoint
if isinstance(r, (dict, list)):
    # look for IDs in the response
    rstr = json.dumps(r)
    ids = re.findall(r'"(?:id|Id|ID|registrationId|subjectId)"\s*:\s*(\d+)', rstr)
    mbs = re.findall(r'"(?:mb|MB|maticniBroj)"\s*:\s*"?(\d{8})"?', rstr)
    print(f"\nIDs found: {ids},  MBs found: {mbs}")
    for mb in mbs[:3]:
        for ep in [f"/api/BD/{mb}", f"/api/BD/detail/{mb}", f"/api/BD/details/{mb}"]:
            fetch(f"{BASE}{ep}", headers=HEADERS_JSON)
