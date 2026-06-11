"""
Debug APR with correct route + API interception.
Routes from JS bundle:
  /search/PrivrednaDrustva/PretragaNaziva  — company name search
  /searchPru                               — entrepreneur search
  /details/PrivrednaDrustva                — company detail
"""
import re, sys, time
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://pretraga.apr.gov.rs"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, timeout=15000)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124",
        locale="sr-RS",
        ignore_https_errors=True,
    )
    page = ctx.new_page()
    page.set_default_timeout(20000)

    # Capture every /api/ call + response
    api_log = []
    def on_resp(resp):
        if "/api/" in resp.url:
            try:
                body = resp.body().decode("utf-8", errors="replace")
            except Exception:
                body = "<unreadable>"
            api_log.append({"url": resp.url, "status": resp.status, "body": body[:800]})
    page.on("response", on_resp)

    # 1) Warm-up — prime WAF session
    print("Warm up...")
    page.goto(BASE, wait_until="domcontentloaded", timeout=20000)
    try: page.wait_for_load_state("networkidle", timeout=6000)
    except PWTimeout: pass
    time.sleep(1)

    # 2) Load the name-search route
    print("Loading /search/PrivrednaDrustva/PretragaNaziva ...")
    page.goto(f"{BASE}/search/PrivrednaDrustva/PretragaNaziva",
              wait_until="domcontentloaded", timeout=20000)
    try: page.wait_for_load_state("networkidle", timeout=8000)
    except PWTimeout: pass
    time.sleep(2)

    print(f"URL: {page.url}")
    print(f"Title: {page.title()}")
    body = page.inner_text("body")
    print(f"Body[:400]: {body[:400]}")

    inputs = page.query_selector_all("input")
    print(f"\nInputs ({len(inputs)}):")
    for inp in inputs:
        print(f"  type={inp.get_attribute('type')!r}  "
              f"ph={inp.get_attribute('placeholder')!r}  "
              f"id={inp.get_attribute('id')!r}")

    # 3) Fill in name + submit
    print("\nFilling search: 'Pekara Krosti'")
    txt = page.query_selector('input[type="text"], input:not([type="hidden"]):not([type="submit"])')
    if txt:
        txt.fill("Pekara Krosti")
        txt.press("Enter")
        try: page.wait_for_load_state("networkidle", timeout=10000)
        except PWTimeout: pass
        time.sleep(2)
        print(f"After search body[:600]: {page.inner_text('body')[:600]}")
    else:
        print("  No text input found. All elements:")
        for el in page.query_selector_all("*")[:20]:
            tag = el.evaluate("el => el.tagName")
            print(f"    {tag}")

    print(f"\n=== API calls captured ({len(api_log)}) ===")
    for entry in api_log:
        print(f"  [{entry['status']}] {entry['url']}")
        print(f"    body: {entry['body'][:300]}")

    # 4) Click first result if present
    rows = page.query_selector_all("table tbody tr")
    print(f"\nResult table rows: {len(rows)}")
    if rows:
        rows[0].click()
        try: page.wait_for_load_state("networkidle", timeout=10000)
        except PWTimeout: pass
        time.sleep(2)
        print(f"Detail URL: {page.url}")
        detail_body = page.inner_text("body")
        print(f"Detail body[:800]: {detail_body[:800]}")
        emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", detail_body)
        print(f"Emails found: {emails}")
        mailtos = [a.get_attribute("href") for a in page.query_selector_all('a[href^="mailto:"]')]
        print(f"Mailto links: {mailtos}")

    # 5) Also try PIB search
    print("\n=== PIB search: 115210171 ===")
    page.goto(f"{BASE}/search/PrivrednaDrustva/PretragaNaziva",
              wait_until="domcontentloaded", timeout=20000)
    try: page.wait_for_load_state("networkidle", timeout=6000)
    except PWTimeout: pass
    time.sleep(1)
    pib_input = page.query_selector('input[placeholder*="PIB" i], input[id*="pib" i]')
    if pib_input:
        pib_input.fill("115210171")
        pib_input.press("Enter")
    else:
        # Try all inputs — fill second one if there are two (name + PIB)
        all_inputs = page.query_selector_all('input:not([type="hidden"])')
        print(f"  Inputs available: {len(all_inputs)}")
        for i, inp in enumerate(all_inputs):
            print(f"  [{i}] ph={inp.get_attribute('placeholder')!r} id={inp.get_attribute('id')!r}")
        if len(all_inputs) >= 2:
            all_inputs[1].fill("115210171")
            all_inputs[1].press("Enter")
        elif all_inputs:
            all_inputs[0].fill("115210171")
            all_inputs[0].press("Enter")
    try: page.wait_for_load_state("networkidle", timeout=8000)
    except PWTimeout: pass
    time.sleep(2)
    pib_body = page.inner_text("body")
    print(f"PIB search body[:400]: {pib_body[:400]}")

    print(f"\n=== Final API log ({len(api_log)}) ===")
    for entry in api_log:
        print(f"  [{entry['status']}] {entry['url']}")
        print(f"    {entry['body'][:400]}")

    page.screenshot(path="apr_screenshot.png")
    print("\nScreenshot: apr_screenshot.png")
    browser.close()

print("Done.")
