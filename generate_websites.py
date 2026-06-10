"""
Website Generator for Business Leads.

Reads businesses with emails from SQLite, constructs a prompt for each lead
using the Single HTML Website Generator template, calls OpenRouter API (DeepSeek)
to generate a unique website, and saves each as an HTML file.

Usage:
    python generate_websites.py                              # generate for all leads with emails
    python generate_websites.py --limit 5                    # generate for first 5 leads only
    python generate_websites.py --start 23                   # start from lead #23
    python generate_websites.py --business-id <id>           # generate for one specific lead
    python generate_websites.py --list                       # list available leads without generating
    python generate_websites.py --api-key <key>              # pass OpenRouter API key directly
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import urllib.request
import ssl

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "database", "businesses.sqlite")
OUT_DIR = os.path.join(ROOT, "generated_sites")

PROMPT_TEMPLATE = """You are a senior web designer, UX specialist and conversion copywriter.

Your task is to generate a COMPLETE SINGLE-FILE WEBSITE.

Output only one file:

index.html

No additional files.

No backend.

No build process.

No frameworks.

No React.

No Vue.

No Tailwind CDN.

Everything must be contained in a single HTML file.

---

# INPUT

{input_json}

---

# OBJECTIVE

Generate a professional local business website.

The website must look like it was custom-built for this company.

Never look like a generic template.

Every company should receive:

* unique headline
* unique structure
* unique copy
* unique service descriptions
* unique value proposition

Use available business data.

---

# TECHNICAL REQUIREMENTS

Generate:

* one HTML file
* embedded CSS
* embedded JavaScript

No external dependencies.

No CDN libraries.

No external fonts.

No external frameworks.

Must work immediately after opening index.html.

---

# DESIGN REQUIREMENTS

Modern 2026 design.

Clean layout.

Large spacing.

Strong typography.

Mobile-first.

Responsive.

Fast loading.

Professional appearance.

---

# CONTENT RULES

Use only supplied information.

Never invent:

* certifications
* awards
* years in business
* employees
* services

Use reviews and services as primary content sources.

---

# CONTACT INFORMATION

Always use actual values.

Insert:

Phone:
{phone}

Email:
{email}

Address:
{address}

Never modify contact information.

Never generate fake contacts.

---

# CTA

Generate CTA based on website_goal.

{cta_instruction}

---

# REQUIRED SECTIONS

Hero

Services

Why Choose Us

Reviews

Contact

Only add extra sections when relevant.

---

# HERO SECTION

Generate:

* unique headline
* supporting text
* CTA button

The headline must be specific to the business.

Avoid generic marketing language.

---

# SERVICES

Create cards based on actual services.

Do not invent services.

---

# REVIEWS

Use review insights.

Summarize recurring themes.

Do not generate fake testimonials.

---

# CONTACT SECTION

Display:

* phone
* email
* address

Create clickable links.

Phone:

tel:{phone_digits}

Email:

mailto:{email}

---

# SEO

Generate:

* title
* meta description
* Open Graph tags

Use provided keywords naturally.

---

# OUTPUT FORMAT

Return only valid HTML.

No markdown.

No explanations.

No comments outside HTML.

The response must start with:

<!DOCTYPE html>

and end with:

</html>

---

# CRITICAL RULES

Generate a complete website.

Generate only HTML.

No explanations.

No markdown.

No placeholders.

No TODO items.

No fake information.

The output must be production-ready."""


def get_cta_instruction(website_goal):
    goals = {
        "call_now": {"text": "Call Now", "action": "tel:{{phone}}"},
        "book_appointment": {"text": "Book Appointment", "action": "mailto:{{email}}"},
        "request_quote": {"text": "Request Quote", "action": "mailto:{{email}}"},
        "visit_store": {"text": "Visit Us", "action": None},
        "order_now": {"text": "Order Now", "action": "tel:{{phone}}"},
        "contact_us": {"text": "Contact Us", "action": "mailto:{{email}}"}
    }
    goal = goals.get(website_goal, goals["call_now"])
    return f"""Generate CTA based on website_goal.

website_goal: {website_goal}

Button:
{goal['text']}

Action:
{goal['action']}"""


def determine_website_goal(category, subcategory):
    call_cats = {"plumber", "electrician", "locksmith", "doctor", "dentist",
                 "veterinary_care", "car_rental", "taxi", "restaurant", "hotel",
                 "hair_salon", "general_contractor"}
    quote_cats = {"attorney", "accounting", "insurance_agency", "real_estate_agency"}
    appt_cats = {"dentist", "doctor", "physical_therapist", "medical_clinic",
                 "dental_clinic", "hair_salon", "veterinary_care"}
    visit_cats = {"shopping_mall", "jewelry_store", "pet_store", "store",
                  "wedding_venue", "live_music_venue", "bed_and_breakfast"}
    sub = subcategory.lower() if subcategory else ""
    cat = category.lower() if category else ""
    if sub in appt_cats or cat in appt_cats:
        return "book_appointment"
    if sub in quote_cats or cat in quote_cats:
        return "request_quote"
    if sub in visit_cats or cat in visit_cats:
        return "visit_store"
    if sub in call_cats or cat in call_cats:
        return "call_now"
    return "call_now"


def extract_review_themes(reviews_text):
    if not reviews_text:
        return ""
    positive_words = [
        "professional", "kind", "friendly", "recommend", "excellent", "great",
        "best", "top", "fast", "quick", "affordable", "reasonable", "expert",
        "knowledgeable", "helpful", "satisfied", "happy", "amazing", "wonderful",
        "fantastic", "outstanding", "superb", "perfect", "love", "trust",
        "profesionalan", "ljubazan", "stručan", "preporuka", "odličan",
        "super", "brz", "pouzdan", "korektan", "profesionalno", "kvalitet"
    ]
    themes = []
    text_lower = reviews_text.lower()
    for word in positive_words:
        if word in text_lower:
            themes.append(word.capitalize())
    seen = set()
    unique = []
    for t in themes:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return ", ".join(unique[:5]) if unique else "Positive customer experiences"


def extract_services_from_reviews(reviews_text, category):
    if not reviews_text:
        return []
    services = set()
    text_lower = reviews_text.lower()
    kw_map = {
        "locksmith": ["key making", "lock repair", "car keys", "spare keys", "key duplication",
                      "lock installation", "emergency unlocking", "key cutting", "sharpening"],
        "plumber": ["pipe repair", "drain cleaning", "water heater", "installation",
                    "leak repair", "plumbing", "bathroom renovation"],
        "dentist": ["teeth cleaning", "fillings", "checkup", "whitening", "extraction",
                    "crowns", "implants", "pediatric dentistry", "prosthetics"],
        "physical_therapist": ["massage", "therapy", "rehabilitation", "sports injury",
                               "back pain", "manual therapy", "exercise"],
        "attorney": ["legal advice", "representation", "consultation", "contracts", "litigation"],
        "hair_salon": ["haircut", "hairstyling", "coloring", "blow dry", "men's haircut"],
        "restaurant": ["pizza", "dine-in", "takeaway", "delivery", "lunch", "dinner"],
        "hotel": ["accommodation", "rooms", "breakfast", "parking", "event space"],
        "veterinary_care": ["checkup", "surgery", "vaccination", "pet care", "consultation"],
        "car_rental": ["car rental", "rent a car", "vehicle rental", "long term rental"],
        "general_contractor": ["renovation", "repair", "installation", "construction", "decoration"],
        "medical_clinic": ["consultation", "examination", "treatment", "checkup", "diagnostics"],
        "jewelry_store": ["jewelry", "repair", "custom design", "watches", "rings"],
        "pet_store": ["pet food", "accessories", "veterinary", "grooming", "pet supplies"],
        "real_estate_agency": ["rental", "apartment", "property", "short term", "long term"],
        "wedding_venue": ["wedding", "celebration", "party", "event", "garden", "catering"],
        "live_music_venue": ["live music", "concert", "event", "stand up", "performance"],
        "bed_and_breakfast": ["accommodation", "breakfast", "rooms", "stay", "parking"],
        "shopping_mall": ["shopping", "paint", "decor", "home improvement", "materials"],
        "insurance_agency": ["insurance", "policy", "coverage", "consultation"],
        "electrician": ["electrical", "installation", "repair", "wiring", "lighting"],
        "accounting": ["accounting", "bookkeeping", "tax", "consulting", "financial"],
        "health": ["consultation", "therapy", "treatment", "wellness"],
        "doctor": ["consultation", "examination", "treatment", "checkup"]
    }
    cat_lower = category.lower() if category else ""
    keywords = kw_map.get(cat_lower, [])
    for kw in keywords:
        if kw in text_lower:
            services.add(kw.capitalize())
    return list(services)


def build_input_json(row):
    category = row.get("category") or ""
    subcategory = row.get("subcategory") or ""
    business_name = row.get("business_name") or ""
    phone = row.get("phone") or ""
    email = row.get("email") or ""
    address = row.get("address") or ""
    reviews_text = row.get("reviews_text") or ""
    description = row.get("description") or ""
    rating = row.get("rating")
    review_count = row.get("review_count")

    website_goal = determine_website_goal(category, subcategory)
    services = extract_services_from_reviews(reviews_text, subcategory or category)
    if not services:
        services = [f"Professional {category} Services"] if category else ["Professional Services"]

    review_summary = extract_review_themes(reviews_text)

    usp = []
    if rating and rating >= 4.5:
        usp.append(f"Exceptional {rating}-star rating from customers")
    if review_count and review_count > 50:
        usp.append(f"Trusted by over {review_count} satisfied clients")
    if "fast" in reviews_text.lower() or "quick" in reviews_text.lower():
        usp.append("Fast and efficient service")
    if "professional" in reviews_text.lower():
        usp.append("Professional and reliable service")
    if "affordable" in reviews_text.lower() or "reasonable" in reviews_text.lower() or "cheap" in reviews_text.lower():
        usp.append("Affordable pricing")
    if not usp:
        usp.append(f"Professional {category} services in Novi Sad")

    recommended_sections = ["Hero", "Services", "Why Choose Us", "Reviews", "Contact"]
    if description:
        recommended_sections.insert(1, "About")

    seo_keywords = {
        "primary": [business_name, f"{category} Novi Sad", f"{category} {subcategory}"],
        "secondary": [f"best {category.lower()} in Novi Sad", f"{category.lower()} services Serbia",
                      f"professional {category.lower()}"]
    }

    style_map = {
        "attorney": "professional, trustworthy, elegant",
        "dentist": "clean, modern, calming",
        "doctor": "clean, professional, trustworthy",
        "medical_clinic": "clean, professional, modern",
        "dental_clinic": "clean, modern, calming",
        "plumber": "trustworthy, straightforward, modern",
        "electrician": "trustworthy, straightforward, modern",
        "locksmith": "trustworthy, fast, modern",
        "restaurant": "warm, appetizing, modern",
        "hotel": "elegant, welcoming, modern",
        "bed_and_breakfast": "cozy, welcoming, charming",
        "hair_salon": "stylish, modern, elegant",
        "veterinary_care": "caring, professional, warm",
        "pet_store": "friendly, colorful, welcoming",
        "car_rental": "modern, trustworthy, professional",
        "real_estate_agency": "professional, modern, trustworthy",
        "general_contractor": "professional, reliable, modern",
        "jewelry_store": "elegant, luxurious, sophisticated",
        "wedding_venue": "romantic, elegant, beautiful",
        "live_music_venue": "vibrant, modern, energetic",
        "shopping_mall": "modern, spacious, welcoming",
        "insurance_agency": "professional, trustworthy, secure",
        "physical_therapist": "calming, professional, healing",
        "accounting": "professional, trustworthy, organized"
    }
    website_style = style_map.get(subcategory or category, "modern, professional, clean")

    archetype_map = {
        "plumber": "Local Service Provider",
        "electrician": "Local Service Provider",
        "locksmith": "Local Service Provider",
        "dentist": "Healthcare Professional",
        "doctor": "Healthcare Professional",
        "medical_clinic": "Healthcare Professional",
        "dental_clinic": "Healthcare Professional",
        "physical_therapist": "Healthcare Professional",
        "veterinary_care": "Healthcare Professional",
        "attorney": "Professional Service Provider",
        "accounting": "Professional Service Provider",
        "insurance_agency": "Professional Service Provider",
        "restaurant": "Local Business",
        "hotel": "Hospitality Provider",
        "bed_and_breakfast": "Hospitality Provider",
        "hair_salon": "Personal Service Provider",
        "car_rental": "Service Provider",
        "real_estate_agency": "Service Provider",
        "general_contractor": "Service Provider",
        "jewelry_store": "Retail Business",
        "pet_store": "Retail Business",
        "shopping_mall": "Retail Business",
        "wedding_venue": "Event Venue",
        "live_music_venue": "Entertainment Venue"
    }
    archetype = archetype_map.get(subcategory or category, "Local Business")

    return {
        "company_name": business_name,
        "category": category,
        "archetype": archetype,
        "website_style": website_style,
        "website_goal": website_goal,
        "phone": phone,
        "email": email,
        "address": address,
        "services": services,
        "usp": usp,
        "review_summary": review_summary,
        "recommended_sections": recommended_sections,
        "seo_keywords": seo_keywords
    }


def build_prompt(row):
    input_data = build_input_json(row)
    input_json = json.dumps(input_data, indent=2, ensure_ascii=False)
    phone = row.get("phone") or ""
    email = row.get("email") or ""
    address = row.get("address") or ""
    phone_digits = re.sub(r'[^\d+]', '', phone)
    website_goal = input_data["website_goal"]
    cta_instruction = get_cta_instruction(website_goal)
    prompt = PROMPT_TEMPLATE.format(
        input_json=input_json, phone=phone, email=email,
        address=address, phone_digits=phone_digits, cta_instruction=cta_instruction
    )
    return prompt, input_data


def call_openrouter_api(prompt, api_key, model="deepseek/deepseek-v4-flash"):
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 8192,
        "stream": False
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("HTTP-Referer", "https://github.com/")
    req.add_header("X-Title", "Business Website Generator")
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        choices = result.get("choices", [])
        if not choices:
            error = result.get("error", {}).get("message", "unknown")
            return None, f"API error: {error}"
        text = choices[0].get("message", {}).get("content", "")
        if not text:
            return None, "Empty response from API"
        return text, None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        return None, f"HTTP {e.code}: {error_body}"
    except Exception as e:
        return None, str(e)


def extract_html(text):
    text = text.strip()
    m = re.search(r'```(?:html)?\s*\n(<!DOCTYPE html>.*?</html>)\s*\n```', text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r'```(?:html)?\s*\r?\n(<!DOCTYPE html>.*?</html>)\s*\r?\n```', text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r'(<!DOCTYPE html>.*?</html>)', text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    if text.startswith('<!DOCTYPE html>') or text.startswith('<html'):
        return text
    m = re.search(r'(<html.*?</html>)', text, re.DOTALL | re.IGNORECASE)
    if m:
        return '<!DOCTYPE html>\n' + m.group(1).strip()
    return text


def sanitize_filename(name):
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[-\s]+', '_', name)
    return name.strip('_').lower()[:80]


def get_businesses(db_path, limit=None, business_id=None, status_filter=None):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM businesses WHERE email IS NOT NULL AND email != ''"
    params = []
    if business_id:
        query += " AND business_id = ?"
        params.append(business_id)
    if status_filter:
        query += " AND lead_status = ?"
        params.append(status_filter)
    query += " ORDER BY purchase_probability_score DESC"
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = [dict(r) for r in conn.execute(query).fetchall()]
    conn.close()
    return rows


def list_businesses(db_path):
    rows = get_businesses(db_path)
    print(f"\n{'ID':<5} {'Business Name':<40} {'Category':<20} {'Email':<35} {'Score':<6}")
    print("-" * 110)
    for i, row in enumerate(rows, 1):
        score = row.get("purchase_probability_score") or 0
        name = (row.get("business_name") or "")[:38]
        cat = (row.get("category") or "")[:18]
        email = (row.get("email") or "")[:33]
        print(f"{i:<5} {name:<40} {cat:<20} {email:<35} {score:<6}")
    print(f"\nTotal: {len(rows)} leads with emails")


def generate_index_page(out_dir, rows):
    sites = []
    for i, row in enumerate(rows, 1):
        name = row.get("business_name") or "Unknown"
        safe_name = sanitize_filename(name)
        biz_dir = f"{i:03d}_{safe_name}"
        html_path = os.path.join(biz_dir, "index.html")
        if os.path.exists(os.path.join(out_dir, html_path)):
            sites.append({
                "name": name,
                "category": row.get("category") or "",
                "path": html_path,
                "score": row.get("purchase_probability_score") or 0,
                "email": row.get("email") or ""
            })
    if not sites:
        return
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Generated Business Websites</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f7;color:#1d1d1f;padding:40px 20px}
.container{max-width:1000px;margin:0 auto}
h1{font-size:2rem;margin-bottom:8px}
.subtitle{color:#6e6e73;margin-bottom:32px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}
.card{background:white;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.04);transition:transform .2s,box-shadow .2s}
.card:hover{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,0.08)}
.card h3{font-size:1rem;margin-bottom:4px}
.card .category{font-size:.85rem;color:#6e6e73;margin-bottom:8px}
.card .meta{font-size:.8rem;color:#6e6e73;margin-bottom:12px}
.card .score{display:inline-block;background:#0071e3;color:white;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600}
.card a{display:inline-block;margin-top:8px;color:#0071e3;text-decoration:none;font-size:.9rem;font-weight:500}
.card a:hover{text-decoration:underline}
.stats{margin-bottom:24px;padding:16px;background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.04)}
.stats span{font-weight:600}
</style>
</head>
<body>
<div class="container">
<h1>Generated Business Websites</h1>
<p class="subtitle">AI-generated single-file websites for each lead</p>
<div class="stats"><p>Total websites: <span>""" + str(len(sites)) + """</span></p></div>
<div class="grid">"""
    for site in sites:
        html += f"""
<div class="card">
<h3>{site['name']}</h3>
<div class="category">{site['category']}</div>
<div class="meta">{site['email']}</div>
<span class="score">Score: {site['score']}</span>
<br>
<a href="{site['path']}" target="_blank">Open Website →</a>
</div>"""
    html += """
</div>
</div>
</body>
</html>"""
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Index page: {os.path.join(out_dir, 'index.html')}")


def main():
    ap = argparse.ArgumentParser(description="Generate websites for business leads")
    ap.add_argument("--limit", type=int, default=None, help="Limit number of websites to generate")
    ap.add_argument("--business-id", type=str, default=None, help="Generate for a specific business ID")
    ap.add_argument("--list", action="store_true", help="List available leads and exit")
    ap.add_argument("--api-key", type=str, default=None, help="OpenRouter API key (or set OPENROUTER_API_KEY env var)")
    ap.add_argument("--model", type=str, default="deepseek/deepseek-v4-flash", help="Model name on OpenRouter")
    ap.add_argument("--start", type=int, default=1, help="Start from lead number (default: 1)")
    ap.add_argument("--status", type=str, default=None, help="Filter by lead status")
    ap.add_argument("--dry-run", action="store_true", help="Generate prompts only, don't call API")
    ap.add_argument("--prompt-only", action="store_true", help="Print prompt for first lead and exit")
    args = ap.parse_args()

    api_key = args.api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key and not args.list and not args.dry_run and not args.prompt_only:
        print("Error: OpenRouter API key required.")
        print("Set OPENROUTER_API_KEY environment variable or pass --api-key")
        sys.exit(1)

    if args.list:
        list_businesses(DB_PATH)
        return

    rows = get_businesses(DB_PATH, limit=args.limit, business_id=args.business_id, status_filter=args.status)
    if not rows:
        print("No leads with emails found in database.")
        return

    print(f"Found {len(rows)} leads with emails. Starting from lead #{args.start}.")
    os.makedirs(OUT_DIR, exist_ok=True)

    if args.prompt_only:
        prompt, input_data = build_prompt(rows[0])
        print(prompt)
        return

    success_count = 0
    fail_count = 0

    for i, row in enumerate(rows, 1):
        if i < args.start:
            continue
        name = row.get("business_name") or "Unknown"
        email = row.get("email") or ""

        print(f"\n[{i}/{len(rows)}] Generating website for: {name}")
        print(f"    Email: {email}  Category: {row.get('category')}")

        prompt, input_data = build_prompt(row)
        safe_name = sanitize_filename(name)
        biz_dir = os.path.join(OUT_DIR, f"{i:03d}_{safe_name}")
        os.makedirs(biz_dir, exist_ok=True)

        with open(os.path.join(biz_dir, "lead_data.json"), "w", encoding="utf-8") as f:
            json.dump(input_data, f, indent=2, ensure_ascii=False)
        with open(os.path.join(biz_dir, "prompt.txt"), "w", encoding="utf-8") as f:
            f.write(prompt)

        if args.dry_run:
            print(f"    [DRY RUN] Saved to {biz_dir}")
            continue

        print(f"    Calling OpenRouter API ({args.model})...")
        html, error = call_openrouter_api(prompt, api_key, model=args.model)
        if error:
            print(f"    FAILED: {error}")
            fail_count += 1
            continue

        clean_html = extract_html(html)
        html_path = os.path.join(biz_dir, "index.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(clean_html)
        print(f"    ✓ Saved: {html_path}")
        success_count += 1

    print(f"\n{'='*60}")
    print(f"GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"Processed: {len(rows)}  Success: {success_count}  Failed: {fail_count}")
    print(f"Output: {OUT_DIR}")

    if success_count > 0:
        generate_index_page(OUT_DIR, rows)


if __name__ == "__main__":
    main()