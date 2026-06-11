"""
Regenerate websites that came out as incomplete/bare skeletons.
These are sites where the AI model truncated output, resulting in
~2.9KB pages missing Services, Reviews, and Why Choose Us sections.

Uses a stronger prompt with explicit size requirements and section validation.
"""
import json
import os
import re
import urllib.request
import ssl
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
GENERATED = os.path.join(ROOT, "generated_sites")
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not API_KEY:
    # Fallback: try loading from config.json
    config_path = os.path.join(ROOT, "config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            config = json.load(f)
        API_KEY = config.get("api_key", config.get("openrouter_api_key", ""))
if not API_KEY:
    print("ERROR: No API key found. Set OPENROUTER_API_KEY env var or add api_key to config.json")
    sys.exit(1)

STRONG_PROMPT_TEMPLATE = """You are a professional web designer. Generate a COMPLETE, FULLY-STYLED single-page HTML website for a local business.

CRITICAL: The generated website MUST be at least 800-1500 lines of code and include ALL of the following sections:

1. HEADER/HERO — with business name, tagline, and CTA button
2. SERVICES — detailed service cards using actual services provided
3. WHY CHOOSE US — unique selling points as cards with icons
4. REVIEWS — customer testimonials/review summaries (use actual review themes)
5. CONTACT — phone, email, address with clickable links
6. FOOTER — copyright and business info

DESIGN REQUIREMENTS:
• Modern 2025/2026 design
• Mobile-first responsive layout
• Custom CSS (no frameworks, no CDN)
• Smooth scroll navigation
• Professional typography with system fonts
• Unique color scheme for this business type
• Animated elements (subtle hover effects, transitions)
• Clean, spacious layout with proper spacing

BUSINESS DATA:
{lead_data}

RULES:
- Return ONLY valid HTML, no markdown, no explanations
- Start with <!DOCTYPE html> and end with </html>
- Do NOT use any external CDN, libraries, or fonts
- All CSS must be embedded in <style> in <head>
- All JS must be embedded in <script> at end of body
- Use actual contact info: phone, email, address from the data
- Never invent fake testimonials — use the review_summary as themes
- Make each website UNIQUE — different layout, colors, and styling based on the business type
- The page must be production-ready and look professionally designed

OUTPUT FORMAT:
<!DOCTYPE html>
...
</html>
"""


def is_site_bad(folder):
    """Check if a site is incomplete (missing sections or too small)."""
    html_path = os.path.join(GENERATED, folder, "index.html")
    if not os.path.exists(html_path):
        return True
    c = open(html_path, "r", encoding="utf-8").read()
    size = len(c)
    if size < 5000:
        return True
    has_services = "Service" in c
    has_reviews = "Review" in c or "Testimonial" in c or "testimonial" in c
    if not (has_services and has_reviews):
        return True
    return False


def get_bad_sites():
    """Get list of folders that need regeneration."""
    folders = sorted([f for f in os.listdir(GENERATED) if os.path.isdir(os.path.join(GENERATED, f))])
    bad = []
    for folder in folders:
        lead_json = os.path.join(GENERATED, folder, "lead_data.json")
        if not os.path.exists(lead_json):
            continue
        if is_site_bad(folder):
            data = json.load(open(lead_json, "r", encoding="utf-8"))
            bad.append((folder, data))
    return bad


def call_api(prompt, retries=3):
    """Call OpenRouter API to generate HTML."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": "deepseek/deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 16384,
        "stream": False
    }
    data = json.dumps(payload).encode("utf-8")
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {API_KEY}")
            req.add_header("HTTP-Referer", "https://github.com/nsdrimtim21/novi-sad-business-sites")
            req.add_header("X-Title", "Business Website Regenerator")
            ctx = ssl._create_unverified_context()
            
            with urllib.request.urlopen(req, context=ctx, timeout=300) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            
            choices = result.get("choices", [])
            if not choices:
                error = result.get("error", {}).get("message", "unknown")
                print(f"    API error (attempt {attempt+1}): {error}")
                time.sleep(5)
                continue
            
            text = choices[0].get("message", {}).get("content", "")
            if not text:
                print(f"    Empty response (attempt {attempt+1})")
                time.sleep(5)
                continue
            
            return text, None
            
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"    HTTP {e.code} (attempt {attempt+1}): {error_body[:200]}")
            if e.code == 429:
                time.sleep(10)
            else:
                time.sleep(5)
        except Exception as e:
            print(f"    Exception (attempt {attempt+1}): {e}")
            time.sleep(5)
    
    return None, "All retries failed"


def extract_html(text):
    """Extract clean HTML from API response."""
    text = text.strip()
    # Try markdown code blocks first
    m = re.search(r'```(?:html)?\s*\n(<!DOCTYPE html>.*?</html>)\s*\n```', text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Try raw DOCTYPE
    m = re.search(r'(<!DOCTYPE html>.*?</html>)', text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Try raw html tag
    m = re.search(r'(<html.*?</html>)', text, re.DOTALL | re.IGNORECASE)
    if m:
        return '<!DOCTYPE html>\n' + m.group(1).strip()
    return text


def validate_html(html):
    """Check if generated HTML has all required sections."""
    checks = {
        "Services": "Service" in html,
        "Reviews": "Review" in html or "Testimonial" in html or "testimonial" in html,
        "Contact": "Contact" in html,
        "CTA Button": "button" in html or "cta" in html.lower() or "call" in html.lower(),
        "Footer": "footer" in html or "</footer>" in html,
        "CSS Style": "<style>" in html,
        "Min Size": len(html) >= 8000,
        "Proper End": html.strip().endswith("</html>"),
    }
    all_good = all(checks.values())
    return all_good, checks


def main():
    bad_sites = get_bad_sites()
    
    print(f"=" * 60)
    print(f"Found {len(bad_sites)} sites that need regeneration")
    print(f"=" * 60)
    print()
    
    success = 0
    fail = 0
    skipped = 0
    
    for i, (folder, data) in enumerate(bad_sites, 1):
        name = data.get("company_name", folder)
        category = data.get("category", "")
        
        print(f"[{i}/{len(bad_sites)}] {name} ({category}) [{folder}]")
        
        # Build the prompt
        lead_json = json.dumps(data, indent=2, ensure_ascii=False)
        prompt = STRONG_PROMPT_TEMPLATE.format(lead_data=lead_json)
        
        # Call API
        print(f"    Calling OpenRouter API...")
        html, error = call_api(prompt)
        
        if error:
            print(f"    ❌ FAILED: {error}")
            fail += 1
            continue
        
        clean_html = extract_html(html)
        
        # Validate
        valid, checks = validate_html(clean_html)
        size = len(clean_html)
        
        print(f"    Size: {size} bytes")
        for check_name, passed in checks.items():
            status = "✓" if passed else "✗"
            print(f"      {status} {check_name}")
        
        if not valid:
            print(f"    ⚠ Validation failed but saving anyway")
        
        # Save
        html_path = os.path.join(GENERATED, folder, "index.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(clean_html)
        
        print(f"    ✓ Saved ({size} bytes)")
        success += 1
        
        # Small delay between requests
        time.sleep(2)
    
    print()
    print(f"=" * 60)
    print(f"Regeneration complete!")
    print(f"  Total: {len(bad_sites)}")
    print(f"  Success: {success}")
    print(f"  Failed: {fail}")
    print(f"  Skipped: {skipped}")
    print(f"=" * 60)


if __name__ == "__main__":
    main()