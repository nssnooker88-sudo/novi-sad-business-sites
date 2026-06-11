"""Debug script: fetch one APR page and dump HTML structure."""
import json, re, ssl, sys, urllib.request
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

# Same SSL bypass used in verify_and_pages.py — proven to work on this machine
ctx = ssl._create_unverified_context()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
}

APR_SEARCH = "https://www.apr.gov.rs/reg/skr/skrHome.aspx"
APR_DETAIL = "https://www.apr.gov.rs/reg/skr/skrIndividualResult.aspx"


def get(url, params=None):
    if params:
        from urllib.parse import urlencode
        url = url + "?" + urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
            raw = resp.read()
            return raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"ERROR {url}: {e}")
        return ""

# 1) Search by name
name = "Pekara Krosti"
print(f"\n=== SEARCH for '{name}' (BDP) ===")
r = s.get(APR_SEARCH, params={"reg": "BDP", "Naziv": name, "showType": "1"},
          headers=HEADERS, timeout=20)
r.encoding = "utf-8"
html = r.text
print(f"Status: {r.status_code}, Length: {len(html)}")

soup = BeautifulSoup(html, "lxml")
# Print all tables found
tables = soup.find_all("table")
print(f"Tables found: {len(tables)}")
for i, t in enumerate(tables):
    rows = t.find_all("tr")
    print(f"  Table {i}: id={t.get('id')} class={t.get('class')} rows={len(rows)}")
    for j, tr in enumerate(rows[:4]):
        cells = [td.get_text(strip=True)[:40] for td in tr.find_all(["td","th"])]
        print(f"    Row {j}: {cells}")

# Print links that look like detail links
links = [(a.get_text(strip=True)[:40], a["href"][:80]) for a in soup.find_all("a", href=True) if "skr" in a["href"].lower()]
print(f"\nAPR-looking links: {len(links)}")
for name, href in links[:10]:
    print(f"  {name!r} -> {href}")

# 2) Also try PR (entrepreneurs)
print(f"\n=== SEARCH for '{name}' (PR) ===")
r2 = s.get(APR_SEARCH, params={"reg": "PR", "Naziv": name, "showType": "1"},
           headers=HEADERS, timeout=20)
r2.encoding = "utf-8"
html2 = r2.text
print(f"Status: {r2.status_code}, Length: {len(html2)}")
soup2 = BeautifulSoup(html2, "lxml")
tables2 = soup2.find_all("table")
print(f"Tables found: {len(tables2)}")
for i, t in enumerate(tables2):
    rows = t.find_all("tr")
    print(f"  Table {i}: id={t.get('id')} rows={len(rows)}")
    for j, tr in enumerate(rows[:3]):
        cells = [td.get_text(strip=True)[:40] for td in tr.find_all(["td","th"])]
        print(f"    Row {j}: {cells}")

# 3) Try PIB lookup (The Pub has PIB 115210171)
print("\n=== SEARCH by PIB 115210171 ===")
r3 = s.get(APR_SEARCH, params={"reg": "BDP", "PIB": "115210171", "showType": "1"},
           headers=HEADERS, timeout=20)
r3.encoding = "utf-8"
html3 = r3.text
print(f"Status: {r3.status_code}, Length: {len(html3)}")
soup3 = BeautifulSoup(html3, "lxml")
# dump a snippet with email-looking content
emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", html3)
print(f"Emails in response: {emails}")
tables3 = soup3.find_all("table")
print(f"Tables: {len(tables3)}")
for i, t in enumerate(tables3):
    rows = t.find_all("tr")
    print(f"  Table {i}: id={t.get('id')} rows={len(rows)}")
    for j, tr in enumerate(rows[:5]):
        cells = [td.get_text(strip=True)[:50] for td in tr.find_all(["td","th"])]
        if any(c for c in cells):
            print(f"    Row {j}: {cells}")
