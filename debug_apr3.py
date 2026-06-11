"""
Find APR React app's actual routes by fetching its JS bundle.
Also check if /BD route works as the search page.
"""
import re, ssl, sys, time, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
ctx = ssl._create_unverified_context()

H_HTML = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124",
    "Accept": "text/html,*/*",
    "Accept-Language": "sr-RS,sr;q=0.9",
}


def get_text(url, headers=H_HTML):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
            raw = r.read()
            text = raw.decode("utf-8", errors="replace")
            print(f"  {url[:80]} -> {r.status} len={len(text)}")
            return text
    except Exception as e:
        print(f"  {url[:80]} -> ERROR: {e}")
        return ""


# 1) Get the main page to find the current JS bundle hash
print("=== Finding current JS bundle ===")
html = get_text("https://pretraga.apr.gov.rs/")
if html:
    js_srcs = re.findall(r'src=["\']([^"\']*\.js)["\']', html)
    print(f"JS files: {js_srcs}")
    # Try to fetch the main bundle
    for src in js_srcs:
        if "main" in src.lower() or "chunk" in src.lower():
            full_url = ("https://pretraga.apr.gov.rs" + src) if src.startswith("/") else src
            print(f"\n=== Fetching JS bundle: {full_url} ===")
            js = get_text(full_url)
            if js and len(js) > 1000:
                # Find route paths
                paths = re.findall(r'["\`](/[a-zA-Z][a-zA-Z0-9/_-]{2,50})["\`]', js)
                unique_paths = list(dict.fromkeys(paths))
                print(f"  Route-like paths in JS: {unique_paths[:40]}")
                # Find API endpoints
                api = re.findall(r'["\`](/api/[^"\'`\s]{3,60})["\`]', js)
                print(f"  API paths: {list(dict.fromkeys(api))[:30]}")
                # Find PIB/naziv/search params
                params = re.findall(r'["\`](?:pib|naziv|mb|PIB|Naziv|MB)["\`]', js, re.I)
                print(f"  Known param names: {list(set(params))}")
            break

# 2) Try various route candidates
print("\n=== Testing route candidates ===")
for path in ["/BD", "/searchBD", "/bd", "/search", "/pretraga", "/pretragaBD", "/privredna", "/entities"]:
    get_text(f"https://pretraga.apr.gov.rs{path}")
