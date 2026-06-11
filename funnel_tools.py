"""Generated-site repair and cold-outreach funnel dashboard utilities."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sqlite3
import urllib.parse
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GENERATED_DIR = ROOT / "generated_sites"
EMAILS_DIR = ROOT / "emails"
DB_PATH = ROOT / "database" / "businesses.sqlite"
BASE_URL = "https://nsdrimtim21.github.io/novi-sad-business-sites"


def extract_html_document(text: str) -> str:
    """Return only the HTML document from model output."""
    text = text.strip()
    patterns = [
        r"```(?:html)?\s*\r?\n(<!DOCTYPE html>.*?</html>)\s*\r?\n```",
        r"(<!DOCTYPE html>.*?</html>)",
        r"(<html\b.*?</html>)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        doc = match.group(1).strip()
        if not doc.lower().startswith("<!doctype html>"):
            doc = "<!DOCTYPE html>\n" + doc
        return doc
    return text


def audit_site_html(text: str) -> list[str]:
    """Return structural issues that make a generated site unsafe to ship."""
    lower = text.lower()
    issues: list[str] = []
    if not text.lstrip().lower().startswith("<!doctype html>"):
        issues.append("missing_doctype")
    if not text.rstrip().lower().endswith("</html>"):
        issues.append("missing_closing_html")
    if "<style" not in lower:
        issues.append("missing_embedded_css")
    if 'name="viewport"' not in lower and "name='viewport'" not in lower:
        issues.append("missing_viewport")
    if "<body" not in lower or "</body>" not in lower:
        issues.append("missing_body")
    if "service" not in lower and "uslug" not in lower:
        issues.append("missing_services")
    if "review" not in lower and "testimonial" not in lower and "utis" not in lower:
        issues.append("missing_reviews")
    if "contact" not in lower and "kontakt" not in lower:
        issues.append("missing_contact_section")
    if "mailto:" not in lower and "tel:" not in lower:
        issues.append("missing_contact_link")
    if "```" in text:
        issues.append("markdown_fence")
    if re.search(r"\b(todo|placeholder|lorem ipsum)\b", text, re.IGNORECASE):
        issues.append("placeholder_text")
    if len(text) < 5000:
        issues.append("too_small")
    return issues


def phone_href(phone: str) -> str:
    return re.sub(r"[^\d+]", "", phone or "")


def _lead_value(lead: dict, key: str, default: str = "") -> str:
    value = lead.get(key)
    if value is None:
        return default
    return str(value)


def build_fallback_site(lead: dict) -> str:
    """Build a complete prompt-faithful single-file site from lead data."""
    name = _lead_value(lead, "company_name", "Local Business")
    category = _lead_value(lead, "category", "local service")
    archetype = _lead_value(lead, "archetype", "Local Business")
    style = _lead_value(lead, "website_style", "modern, professional, clean")
    goal = _lead_value(lead, "website_goal", "contact_us")
    phone = _lead_value(lead, "phone")
    email = _lead_value(lead, "email")
    address = _lead_value(lead, "address")
    services = lead.get("services") or [f"Professional {category} services"]
    usps = lead.get("usp") or [f"Reliable {category} service in Novi Sad"]
    review_summary = _lead_value(lead, "review_summary", "Positive customer feedback")
    tel = phone_href(phone)

    cta_label = {
        "book_appointment": "Book Appointment",
        "request_quote": "Request Quote",
        "visit_store": "Plan a Visit",
        "order_now": "Order Now",
        "call_now": "Call Now",
    }.get(goal, "Contact Us")
    cta_href = f"tel:{tel}" if tel and goal in {"call_now", "order_now"} else f"mailto:{email}"

    safe_name = html.escape(name)
    safe_category = html.escape(category)
    safe_archetype = html.escape(archetype)
    safe_style = html.escape(style)
    category_lower = category.lower()

    visual = _visual_system(category_lower, style)
    hero_line = _hero_line(name, category, goal, review_summary)
    support_line = _support_line(name, category, services, usps)
    section_label = visual["label"]

    service_cards = "\n".join(
        f"""
        <article class="card">
          <span class="card-kicker">{html.escape(section_label)}</span>
          <h3>{html.escape(str(service))}</h3>
          <p>{html.escape(_service_sentence(str(service), category, name))}</p>
        </article>"""
        for service in services[:6]
    )
    usp_cards = "\n".join(
        f"""
        <article class="proof-item">
          <strong>{html.escape(str(usp))}</strong>
          <span>{html.escape(_proof_sentence(str(usp), category))}</span>
        </article>"""
        for usp in usps[:6]
    )
    review_text = (
        f"Recurring review themes: {review_summary}."
        if review_summary.strip()
        else "Review content is limited in the supplied data, so this section summarizes only the available quality signals."
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_name} | {safe_category} in Novi Sad</title>
  <meta name="description" content="{safe_name} offers {safe_category.lower()} services in Novi Sad. Contact by phone or email.">
  <meta property="og:title" content="{safe_name}">
  <meta property="og:description" content="{safe_category} services in Novi Sad with direct contact information.">
  <style>
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      color: {visual["ink"]};
      background: {visual["paper"]};
      line-height: 1.6;
    }}
    a {{ color: inherit; }}
    .shell {{ width: min(1120px, calc(100% - 32px)); margin: 0 auto; }}
    header {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: {visual["nav_bg"]};
      border-bottom: 1px solid {visual["line"]};
      backdrop-filter: blur(14px);
    }}
    nav {{
      min-height: 68px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
    }}
    .brand {{ font-weight: 800; letter-spacing: 0; }}
    .nav-links {{ display: flex; gap: 18px; font-size: 0.94rem; color: #44515a; }}
    .nav-links a {{ text-decoration: none; }}
    .hero {{
      padding: 86px 0 72px;
      background:
        linear-gradient(135deg, {visual["hero_a"]}, {visual["hero_b"]}),
        linear-gradient(145deg, transparent 0 52%, {visual["wash"]} 52% 100%);
    }}
    .hero-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
      gap: 42px;
      align-items: center;
    }}
    .eyebrow {{
      margin: 0 0 14px;
      color: {visual["accent"]};
      font-weight: 800;
      text-transform: uppercase;
      font-size: 0.82rem;
    }}
    h1 {{
      margin: 0;
      max-width: 780px;
      font-size: clamp(2.3rem, 5vw, 4.9rem);
      line-height: 1.02;
      letter-spacing: 0;
    }}
    .lead {{
      max-width: 680px;
      margin: 22px 0 0;
      color: #44515a;
      font-size: 1.12rem;
    }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 30px; }}
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 48px;
      padding: 0 20px;
      border-radius: 8px;
      text-decoration: none;
      font-weight: 800;
      background: {visual["button"]};
      color: #fff;
    }}
    .btn.secondary {{ background: #fff; color: {visual["ink"]}; border: 1px solid {visual["line"]}; }}
    .snapshot {{
      background: #ffffff;
      border: 1px solid {visual["line"]};
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 18px 50px rgba(25, 31, 35, 0.08);
    }}
    .snapshot h2 {{ margin: 0 0 14px; font-size: 1.15rem; }}
    .snapshot p {{ margin: 0 0 12px; color: #44515a; }}
    section {{ padding: 68px 0; }}
    .section-head {{ max-width: 720px; margin-bottom: 28px; }}
    .section-head h2 {{ margin: 0 0 10px; font-size: clamp(1.7rem, 3vw, 2.5rem); }}
    .section-head p {{ margin: 0; color: #5a666f; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
    }}
    .card, .proof-item {{
      background: #fff;
      border: 1px solid {visual["line"]};
      border-radius: 8px;
      padding: 22px;
    }}
    .card-kicker {{
      display: block;
      color: {visual["accent"]};
      font-size: 0.78rem;
      font-weight: 800;
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    .card h3 {{ margin: 0 0 10px; font-size: 1.16rem; }}
    .card p, .proof-item span {{ color: #5a666f; }}
    .proof {{
      background: {visual["dark"]};
      color: #fff;
    }}
    .proof .section-head p, .proof-item span {{ color: #c7d0d5; }}
    .proof-item {{ background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.16); }}
    .proof-item strong {{ display: block; margin-bottom: 8px; }}
    .review-box {{
      background: #fff;
      border-left: 5px solid {visual["accent"]};
      padding: 26px;
      border-radius: 8px;
      color: #44515a;
      font-size: 1.08rem;
    }}
    .contact-band {{
      background: {visual["contact"]};
      color: #fff;
    }}
    .contact-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
    }}
    .contact-card {{
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.2);
      border-radius: 8px;
      padding: 20px;
      overflow-wrap: anywhere;
    }}
    .contact-card span {{ display: block; color: #d7edf4; font-size: 0.82rem; margin-bottom: 8px; }}
    .contact-card a {{ font-weight: 800; text-decoration: none; }}
    .micro-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }}
    .micro {{ border-top: 1px solid {visual["line"]}; padding-top: 12px; color: #5a666f; font-size: .94rem; }}
    footer {{ padding: 24px 0; background: #11181d; color: #cad2d7; font-size: 0.92rem; }}
    @media (max-width: 820px) {{
      .hero-grid, .grid, .contact-grid, .micro-grid {{ grid-template-columns: 1fr; }}
      .nav-links {{ display: none; }}
      .hero {{ padding-top: 56px; }}
    }}
  </style>
</head>
<body>
  <header>
    <nav class="shell">
      <div class="brand">{safe_name}</div>
      <div class="nav-links">
        <a href="#services">Services</a>
        <a href="#reviews">Reviews</a>
        <a href="#contact">Contact</a>
      </div>
    </nav>
  </header>

  <main>
    <section class="hero">
      <div class="shell hero-grid">
        <div>
          <p class="eyebrow">{safe_category} / Novi Sad</p>
          <h1>{html.escape(hero_line)}</h1>
          <p class="lead">{html.escape(support_line)}</p>
          <div class="actions">
            <a class="btn" href="{html.escape(cta_href)}">{html.escape(cta_label)}</a>
            <a class="btn secondary" href="#services">View Services</a>
          </div>
          <div class="micro-grid">
            <div class="micro">Service area: Novi Sad</div>
            <div class="micro">Category: {safe_category}</div>
            <div class="micro">Direct contact: {html.escape(phone or email)}</div>
          </div>
        </div>
        <aside class="snapshot" aria-label="Business snapshot">
          <h2>Business Snapshot</h2>
          <p><strong>Category:</strong> {safe_category}</p>
          <p><strong>Goal:</strong> {html.escape(cta_label)}</p>
          <p><strong>Address:</strong> {html.escape(address)}</p>
        </aside>
      </div>
    </section>

    <section id="services">
      <div class="shell">
        <div class="section-head">
          <h2>Services</h2>
          <p>Available services from the business profile.</p>
        </div>
        <div class="grid">{service_cards}
        </div>
      </div>
    </section>

    <section class="proof">
      <div class="shell">
        <div class="section-head">
          <h2>Why Choose Us</h2>
          <p>Helpful signals before you call, book, or request details.</p>
        </div>
        <div class="grid">{usp_cards}
        </div>
      </div>
    </section>

    <section id="reviews">
      <div class="shell">
        <div class="section-head">
          <h2>Reviews</h2>
          <p>Recurring themes from the available review information.</p>
        </div>
        <div class="review-box">{html.escape(review_text)}</div>
      </div>
    </section>

    <section id="contact" class="contact-band">
      <div class="shell">
        <div class="section-head">
          <h2>Contact</h2>
          <p>Call, email, or use the address below.</p>
        </div>
        <div class="contact-grid">
          <div class="contact-card"><span>Phone</span><a href="tel:{html.escape(tel)}">{html.escape(phone)}</a></div>
          <div class="contact-card"><span>Email</span><a href="mailto:{html.escape(email)}">{html.escape(email)}</a></div>
          <div class="contact-card"><span>Address</span>{html.escape(address)}</div>
        </div>
      </div>
    </section>
  </main>

  <footer>
    <div class="shell">&copy; 2026 {safe_name}. {safe_category} in Novi Sad.</div>
  </footer>
  <script>
    document.querySelectorAll('a[href^="#"]').forEach(function(link) {{
      link.addEventListener("click", function(event) {{
        var target = document.querySelector(link.getAttribute("href"));
        if (!target) return;
        event.preventDefault();
        target.scrollIntoView({{ behavior: "smooth", block: "start" }});
      }});
    }});
  </script>
</body>
</html>
"""


def _visual_system(category: str, style: str) -> dict[str, str]:
    if any(word in category for word in ["dent", "doctor", "clinic", "health", "therap"]):
        return {
            "label": "Care",
            "ink": "#102027",
            "paper": "#eef6f5",
            "nav_bg": "rgba(238,246,245,.94)",
            "line": "#cfe1df",
            "accent": "#147c75",
            "button": "#147c75",
            "dark": "#103c43",
            "contact": "#147c75",
            "hero_a": "rgba(255,255,255,.94)",
            "hero_b": "rgba(214,236,234,.76)",
            "wash": "rgba(20,124,117,.12)",
        }
    if any(word in category for word in ["restaurant", "pizza", "venue", "breakfast", "hotel", "hostel"]):
        return {
            "label": "Offer",
            "ink": "#231711",
            "paper": "#fff7ed",
            "nav_bg": "rgba(255,247,237,.94)",
            "line": "#ead8c1",
            "accent": "#b4511d",
            "button": "#7f2d12",
            "dark": "#351f16",
            "contact": "#9a3412",
            "hero_a": "rgba(255,255,255,.9)",
            "hero_b": "rgba(254,215,170,.64)",
            "wash": "rgba(180,81,29,.12)",
        }
    if any(word in category for word in ["locksmith", "plumber", "electrician", "contractor"]):
        return {
            "label": "Service",
            "ink": "#172026",
            "paper": "#f5f7f8",
            "nav_bg": "rgba(245,247,248,.94)",
            "line": "#d6dde1",
            "accent": "#1f6f8b",
            "button": "#172026",
            "dark": "#12212b",
            "contact": "#1f6f8b",
            "hero_a": "rgba(255,255,255,.92)",
            "hero_b": "rgba(217,226,232,.78)",
            "wash": "rgba(31,111,139,.13)",
        }
    if any(word in category for word in ["attorney", "accounting", "insurance", "real estate"]):
        return {
            "label": "Advisory",
            "ink": "#171a22",
            "paper": "#f6f4ef",
            "nav_bg": "rgba(246,244,239,.94)",
            "line": "#ded6c9",
            "accent": "#765a2a",
            "button": "#171a22",
            "dark": "#20202a",
            "contact": "#765a2a",
            "hero_a": "rgba(255,255,255,.9)",
            "hero_b": "rgba(229,221,207,.7)",
            "wash": "rgba(118,90,42,.12)",
        }
    return {
        "label": "Service",
        "ink": "#172026",
        "paper": "#f7f4ef",
        "nav_bg": "rgba(247,244,239,.94)",
        "line": "#ddd4c7",
        "accent": "#266c84",
        "button": "#172026",
        "dark": "#172026",
        "contact": "#266c84",
        "hero_a": "rgba(255,255,255,.86)",
        "hero_b": "rgba(235,226,214,.7)",
        "wash": "rgba(38,108,132,.13)",
    }


def _hero_line(name: str, category: str, goal: str, review_summary: str) -> str:
    c = category.lower()
    if "restaurant" in c:
        return f"{name}: food in Novi Sad with direct ordering by phone"
    if "hotel" in c or "hostel" in c or "breakfast" in c:
        return f"{name}: stay in Novi Sad with direct booking contact"
    if "locksmith" in c:
        return f"{name}: locksmith help in Novi Sad, one call away"
    if "plumber" in c:
        return f"{name}: plumbing help in Novi Sad with direct contact"
    if "electrician" in c:
        return f"{name}: electrical service in Novi Sad with direct contact"
    if any(word in c for word in ["dent", "doctor", "clinic", "health", "therap"]):
        return f"{name}: {category.lower()} care in Novi Sad by appointment"
    if "attorney" in c:
        return f"{name}: legal contact in Novi Sad for consultation requests"
    if goal == "call_now":
        return f"{name}: {category.lower()} service in Novi Sad, ready for your call"
    if goal == "book_appointment":
        return f"{name}: appointment-ready {category.lower()} care in Novi Sad"
    if goal == "request_quote":
        return f"{name}: clear {category.lower()} help for your next step"
    if goal == "visit_store":
        return f"{name}: a local {category.lower()} destination in Novi Sad"
    if review_summary:
        return f"{name}: {category.lower()} shaped by customer trust"
    return f"{name}: professional {category.lower()} in Novi Sad"


def _support_line(name: str, category: str, services: list, usps: list) -> str:
    service = str(services[0]) if services else f"{category} services"
    usp = str(usps[0]).rstrip(".") if usps else "available business information"
    return f"Contact {name} directly for {service.lower()} in Novi Sad. Key trust signal: {usp.lower()}."


def _service_sentence(service: str, category: str, name: str) -> str:
    return f"{service} is the available {category.lower()} service listed for {name}. Use the contact details below to ask for current availability."


def _proof_sentence(usp: str, category: str) -> str:
    return f"A useful signal when comparing local {category.lower()} providers in Novi Sad."


def load_lead_data(site_dir: Path) -> dict:
    path = site_dir / "lead_data.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_slug_map() -> dict[str, str]:
    path = ROOT / "_slug_mapping.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def fallback_slug(folder: str) -> str:
    stem = folder.split("_", 1)[-1].lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return slug or folder.lower()


def site_url_for_slug(slug: str) -> str:
    return f"{BASE_URL}/{urllib.parse.quote(slug)}/"


def collect_sites(generated_dir: Path = GENERATED_DIR) -> list[dict]:
    slug_map = load_slug_map()
    sites = []
    for site_dir in sorted(p for p in generated_dir.iterdir() if p.is_dir()):
        lead = load_lead_data(site_dir)
        html_path = site_dir / "index.html"
        text = html_path.read_text(encoding="utf-8", errors="replace") if html_path.exists() else ""
        issues = audit_site_html(text) if text else ["missing_index"]
        slug = slug_map.get(site_dir.name) or fallback_slug(site_dir.name)
        sites.append(
            {
                "folder": site_dir.name,
                "slug": slug,
                "url": site_url_for_slug(slug),
                "name": lead.get("company_name") or site_dir.name,
                "category": lead.get("category") or "",
                "email": lead.get("email") or "",
                "score": lead.get("purchase_probability_score") or "",
                "issues": issues,
            }
        )
    return sites


def publish_slug_sites(generated_dir: Path = GENERATED_DIR) -> list[dict]:
    """Copy generated site HTML into root slug folders for GitHub Pages URLs."""
    published = []
    for site in collect_sites(generated_dir):
        src = generated_dir / site["folder"] / "index.html"
        dst_dir = ROOT / site["slug"]
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst_dir / "index.html")
        published.append(site)
    return published


def repair_generated_sites(generated_dir: Path = GENERATED_DIR) -> list[dict]:
    results = []
    for site_dir in sorted(p for p in generated_dir.iterdir() if p.is_dir()):
        html_path = site_dir / "index.html"
        lead = load_lead_data(site_dir)
        original = html_path.read_text(encoding="utf-8", errors="replace") if html_path.exists() else ""
        cleaned = extract_html_document(original)
        issues_after_clean = audit_site_html(cleaned)
        action = "unchanged"
        final_html = cleaned

        if issues_after_clean:
            final_html = build_fallback_site(lead)
            action = "fallback"
        elif cleaned != original:
            action = "cleaned"

        if final_html != original:
            html_path.write_text(final_html, encoding="utf-8", newline="\n")

        results.append(
            {
                "folder": site_dir.name,
                "name": lead.get("company_name") or site_dir.name,
                "action": action,
                "issues": audit_site_html(final_html),
            }
        )
    return results


def build_gallery_html(sites: list[dict]) -> str:
    rows = []
    for site in sites:
        issues = site.get("issues") or []
        status = "OK" if not issues else "Needs review"
        status_class = "ok" if not issues else "bad"
        rows.append(
            f"""
        <article class="card">
          <div>
            <h2>{html.escape(str(site["name"]))}</h2>
            <p>{html.escape(str(site.get("category") or "Uncategorized"))}</p>
            <small>{html.escape(str(site.get("email") or "No email"))}</small>
          </div>
          <span class="status {status_class}">{status}</span>
          <a href="{html.escape(site["folder"])}/index.html" target="_blank">Open Website</a>
        </article>"""
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Generated Business Websites</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;background:#f6f3ee;color:#172026;padding:32px 18px}}.container{{max-width:1180px;margin:0 auto}}header{{display:flex;justify-content:space-between;gap:16px;align-items:end;margin-bottom:24px}}h1{{margin:0 0 6px;font-size:clamp(2rem,4vw,3.4rem);letter-spacing:0}}p{{margin:0;color:#5b6870}}.stats{{background:#fff;border:1px solid #ddd4c7;border-radius:8px;padding:16px}}.stats span{{font-weight:800}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}}.card{{min-height:190px;background:#fff;border:1px solid #ddd4c7;border-radius:8px;padding:18px;display:flex;flex-direction:column;justify-content:space-between;gap:14px}}h2{{font-size:1.02rem;margin:0 0 5px}}small{{display:block;margin-top:8px;color:#6b767d;overflow-wrap:anywhere}}a{{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:0 14px;border-radius:8px;background:#172026;color:#fff;text-decoration:none;font-weight:750}}.status{{width:max-content;border-radius:999px;padding:4px 9px;font-size:.78rem;font-weight:800}}.ok{{background:#dff3e6;color:#12652f}}.bad{{background:#ffe1dc;color:#992414}}@media(max-width:720px){{header{{display:block}}.stats{{margin-top:14px}}}}
</style>
</head>
<body>
<div class="container">
<header>
  <div>
    <h1>Generated Business Websites</h1>
    <p>Single-file demo websites for Novi Sad cold outreach.</p>
  </div>
  <div class="stats">Total websites: <span>{len(sites)}</span></div>
</header>
<main class="grid">{''.join(rows)}
</main>
</div>
</body>
</html>
"""


def write_gallery(generated_dir: Path = GENERATED_DIR) -> list[dict]:
    sites = collect_sites(generated_dir)
    (generated_dir / "index.html").write_text(build_gallery_html(sites), encoding="utf-8", newline="\n")
    return sites


def _scalar(conn: sqlite3.Connection, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


def load_email_summary() -> list[dict]:
    path = EMAILS_DIR / "_summary.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def build_campaign_rows(sites: list[dict]) -> list[dict]:
    email_summary = load_email_summary()
    by_folder = {row.get("folder"): row for row in email_summary}
    rows = []
    for site in sites:
        email_row = by_folder.get(site["folder"], {})
        has_email = bool(site.get("email"))
        has_site = not site.get("issues")
        has_outreach = bool(email_row.get("html_file"))
        rows.append(
            {
                "name": site["name"],
                "category": site["category"],
                "folder": site["folder"],
                "slug": site["slug"],
                "site_url": site["url"],
                "email": site.get("email") or "",
                "has_site": has_site,
                "has_email": has_email,
                "has_outreach_email": has_outreach,
                "email_preview": f"emails/{email_row.get('html_file')}" if has_outreach else "",
                "ready": has_site and has_email and has_outreach,
                "issues": site.get("issues") or [],
            }
        )
    return rows


def build_dashboard_model(db_path: Path = DB_PATH, generated_count: int | None = None, email_count: int | None = None) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    metrics = {
        "total_businesses": _scalar(conn, "SELECT COUNT(*) FROM businesses"),
        "active_businesses": _scalar(conn, "SELECT COUNT(*) FROM businesses WHERE is_active = 1"),
        "no_website": _scalar(conn, "SELECT COUNT(*) FROM businesses WHERE has_website = 0"),
        "active_no_website": _scalar(conn, "SELECT COUNT(*) FROM businesses WHERE has_website = 0 AND is_active = 1"),
        "high_priority": _scalar(conn, "SELECT COUNT(*) FROM businesses WHERE lead_status = 'HIGH_PRIORITY'"),
        "high_priority_with_email": _scalar(conn, "SELECT COUNT(*) FROM businesses WHERE lead_status = 'HIGH_PRIORITY' AND email IS NOT NULL AND email != ''"),
        "all_with_email": _scalar(conn, "SELECT COUNT(*) FROM businesses WHERE email IS NOT NULL AND email != ''"),
        "generated_sites": generated_count if generated_count is not None else len([p for p in GENERATED_DIR.iterdir() if p.is_dir()]),
        "generated_emails": email_count if email_count is not None else len(json.loads((EMAILS_DIR / "_summary.json").read_text(encoding="utf-8"))) if (EMAILS_DIR / "_summary.json").exists() else 0,
    }
    status_rows = [
        dict(r)
        for r in conn.execute(
            """
            SELECT COALESCE(lead_status, 'UNKNOWN') AS status, COUNT(*) AS count
            FROM businesses
            GROUP BY COALESCE(lead_status, 'UNKNOWN')
            ORDER BY count DESC
            """
        )
    ]
    category_rows = [
        dict(r)
        for r in conn.execute(
            """
            SELECT COALESCE(category, 'Uncategorized') AS category, COUNT(*) AS count
            FROM businesses
            WHERE has_website = 0 AND is_active = 1
            GROUP BY COALESCE(category, 'Uncategorized')
            ORDER BY count DESC
            LIMIT 15
            """
        )
    ]
    source_rows = []
    if "email_source" in [r["name"] for r in conn.execute("PRAGMA table_info(businesses)")]:
        source_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT COALESCE(NULLIF(email_source, ''), 'unknown') AS source, COUNT(*) AS count
                FROM businesses
                WHERE email IS NOT NULL AND email != ''
                GROUP BY COALESCE(NULLIF(email_source, ''), 'unknown')
                ORDER BY count DESC
                """
            )
        ]
    top_remaining = [
        dict(r)
        for r in conn.execute(
            """
            SELECT business_name, category, purchase_probability_score
            FROM businesses
            WHERE lead_status = 'HIGH_PRIORITY' AND (email IS NULL OR email = '')
            ORDER BY purchase_probability_score DESC
            LIMIT 25
            """
        )
    ]
    conn.close()
    return {
        "metrics": metrics,
        "lead_statuses": status_rows,
        "top_categories": category_rows,
        "email_sources": source_rows,
        "top_remaining": top_remaining,
    }


def build_dashboard_html(model: dict, sites: list[dict]) -> str:
    metrics = model["metrics"]
    campaign_rows = build_campaign_rows(sites)
    ready_count = sum(1 for row in campaign_rows if row["ready"])
    site_count = sum(1 for row in campaign_rows if row["has_site"])
    email_count = sum(1 for row in campaign_rows if row["has_email"])
    cards = [
        ("Total businesses", "total_businesses"),
        ("Active businesses", "active_businesses"),
        ("Active no website", "active_no_website"),
        ("High priority", "high_priority"),
        ("HP with email", "high_priority_with_email"),
        ("Generated sites", "generated_sites"),
        ("Generated emails", "generated_emails"),
    ]
    card_html = "".join(
        f"<article class=\"metric\"><span>{label}</span><strong>{metrics[key]}</strong></article>"
        for label, key in cards
    )
    source_rows = "".join(
        f"<tr><td>{html.escape(str(row['source']))}</td><td>{row['count']}</td></tr>"
        for row in model["email_sources"]
    ) or "<tr><td colspan=\"2\">No source data yet.</td></tr>"
    status_rows = "".join(
        f"<tr><td><span class=\"pill\">{html.escape(str(row['status']))}</span></td><td>{row['count']}</td></tr>"
        for row in model["lead_statuses"]
    )
    category_rows = "".join(
        f"<tr><td>{html.escape(str(row['category']))}</td><td>{row['count']}</td></tr>"
        for row in model["top_categories"]
    )
    remaining_rows = "".join(
        f"<tr><td>{html.escape(str(row['business_name']))}</td><td>{html.escape(str(row['category'] or ''))}</td><td>{row['purchase_probability_score']}</td></tr>"
        for row in model["top_remaining"]
    ) or "<tr><td colspan=\"3\">No high-priority email gaps.</td></tr>"
    bad_sites = [site for site in sites if site.get("issues")]
    bad_rows = "".join(
        f"<tr><td>{html.escape(str(site['name']))}</td><td>{html.escape(site['folder'])}</td><td>{html.escape(', '.join(site['issues']))}</td></tr>"
        for site in bad_sites
    ) or "<tr><td colspan=\"3\">All generated sites passed structural validation.</td></tr>"
    campaign_html = "".join(
        f"""
        <tr>
          <td>{html.escape(str(row['name']))}<small>{html.escape(str(row['category']))}</small></td>
          <td><a href="{html.escape(row['site_url'])}" target="_blank">{html.escape(row['slug'])}</a></td>
          <td>{html.escape(row['email']) if row['email'] else '<span class="muted">missing</span>'}</td>
          <td>{'<span class="ok">Ready</span>' if row['ready'] else '<span class="warn">Not ready</span>'}</td>
          <td>{f'<a href="{html.escape(row["email_preview"])}">Email</a>' if row['email_preview'] else '<span class="muted">none</span>'}</td>
        </tr>"""
        for row in campaign_rows
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cold Outreach Funnel Dashboard</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;background:#f7f4ef;color:#172026}}.shell{{width:min(1280px,calc(100% - 32px));margin:0 auto}}header{{padding:42px 0 24px}}h1{{font-size:clamp(2rem,4vw,3.5rem);margin:0 0 8px;letter-spacing:0}}p{{margin:0;color:#5b6870}}.metrics{{display:grid;grid-template-columns:repeat(7,1fr);gap:12px;margin:20px 0 18px}}.metric{{background:#fff;border:1px solid #ddd4c7;border-radius:8px;padding:16px}}.metric span{{display:block;color:#66727a;font-size:.82rem;margin-bottom:8px}}.metric strong{{font-size:2rem}}.readiness{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:0 0 28px}}.readiness div{{background:#172026;color:#fff;border-radius:8px;padding:16px}}.readiness span{{display:block;color:#cbd5db;font-size:.82rem;margin-bottom:6px}}.readiness strong{{font-size:1.7rem}}section{{margin:0 0 28px}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.panel{{background:#fff;border:1px solid #ddd4c7;border-radius:8px;padding:18px;overflow:auto}}h2{{margin:0 0 14px;font-size:1.2rem}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px 8px;border-bottom:1px solid #ece4d9;text-align:left;font-size:.92rem;vertical-align:top}}th{{color:#5b6870;font-size:.78rem;text-transform:uppercase}}td small{{display:block;color:#6b767d;margin-top:3px}}a{{color:#0f5f7a;text-decoration:none;font-weight:700}}.actions{{display:flex;gap:12px;flex-wrap:wrap;margin-top:18px}}a.button{{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:0 14px;border-radius:8px;background:#172026;color:#fff;text-decoration:none;font-weight:800}}.ok{{display:inline-block;background:#dff3e6;color:#12652f;border-radius:999px;padding:4px 9px;font-weight:800;font-size:.78rem}}.warn{{display:inline-block;background:#ffe8bf;color:#7a4300;border-radius:999px;padding:4px 9px;font-weight:800;font-size:.78rem}}.muted{{color:#8a949b}}.pill{{display:inline-block;background:#eef3f5;border-radius:999px;padding:4px 9px;font-weight:800;font-size:.78rem}}@media(max-width:1000px){{.metrics,.readiness{{grid-template-columns:repeat(2,1fr)}}.two{{grid-template-columns:1fr}}}}@media(max-width:640px){{.metrics,.readiness{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="shell">
<header>
  <h1>Cold Outreach Funnel Dashboard</h1>
  <p>Discovery, priority grading, email enrichment, generated websites, and campaign readiness in one place.</p>
  <div class="actions">
    <a class="button" href="generated_sites/index.html">Review Websites</a>
    <a class="button" href="emails/index.html">Review Emails</a>
  </div>
</header>
<main>
  <section class="metrics">{card_html}</section>
  <section class="readiness">
    <div><span>Campaign-ready recipients</span><strong>{ready_count}</strong></div>
    <div><span>Generated sites OK</span><strong>{site_count}</strong></div>
    <div><span>Generated-site emails found</span><strong>{email_count}</strong></div>
    <div><span>Generated outreach emails</span><strong>{metrics['generated_emails']}</strong></div>
  </section>
  <section class="two">
    <div class="panel"><h2>Lead Status Breakdown</h2><table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody>{status_rows}</tbody></table></div>
    <div class="panel"><h2>Email Sources</h2><table><thead><tr><th>Source</th><th>Count</th></tr></thead><tbody>{source_rows}</tbody></table></div>
  </section>
  <section class="two">
    <div class="panel"><h2>Top Active No-Website Categories</h2><table><thead><tr><th>Category</th><th>Count</th></tr></thead><tbody>{category_rows}</tbody></table></div>
    <div class="panel"><h2>Generated Site QA</h2><table><thead><tr><th>Business</th><th>Folder</th><th>Issues</th></tr></thead><tbody>{bad_rows}</tbody></table></div>
  </section>
  <section class="panel"><h2>High-Priority Leads Still Missing Email</h2><table><thead><tr><th>Business</th><th>Category</th><th>Score</th></tr></thead><tbody>{remaining_rows}</tbody></table></section>
  <section class="panel"><h2>Generated Site Campaign Readiness</h2><table><thead><tr><th>Business</th><th>Site URL</th><th>Recipient Email</th><th>Status</th><th>Email Preview</th></tr></thead><tbody>{campaign_html}</tbody></table></section>
</main>
</div>
</body>
</html>
"""


def write_dashboard(db_path: Path = DB_PATH, generated_dir: Path = GENERATED_DIR) -> dict:
    sites = collect_sites(generated_dir)
    model = build_dashboard_model(db_path, generated_count=len(sites))
    (ROOT / "dashboard.html").write_text(build_dashboard_html(model, sites), encoding="utf-8", newline="\n")
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair generated sites and build funnel dashboard.")
    parser.add_argument("command", choices=["audit-sites", "repair-sites", "gallery", "publish-sites", "dashboard", "all"])
    args = parser.parse_args()

    if args.command == "audit-sites":
        sites = collect_sites()
        bad = [site for site in sites if site["issues"]]
        print(f"Sites: {len(sites)} | Bad: {len(bad)}")
        for site in bad:
            print(f"{site['folder']}: {', '.join(site['issues'])}")
    elif args.command == "repair-sites":
        results = repair_generated_sites()
        print(f"Repaired/checked: {len(results)}")
        for row in results:
            if row["action"] != "unchanged" or row["issues"]:
                print(f"{row['folder']}: {row['action']} | issues={row['issues']}")
    elif args.command == "gallery":
        sites = write_gallery()
        print(f"Wrote gallery for {len(sites)} sites.")
    elif args.command == "publish-sites":
        sites = publish_slug_sites()
        print(f"Published {len(sites)} root slug site folders.")
    elif args.command == "dashboard":
        model = write_dashboard()
        print(f"Wrote dashboard.html with {model['metrics']['generated_sites']} generated sites.")
    elif args.command == "all":
        repair_generated_sites()
        publish_slug_sites()
        sites = write_gallery()
        model = write_dashboard()
        print(f"Done. Sites: {len(sites)} | Emails: {model['metrics']['all_with_email']}")


if __name__ == "__main__":
    main()
