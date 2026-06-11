"""
Generate personalized cold-email campaigns for drimtim.
Each business gets a custom HTML + plain text email with their unique site URL.

Usage:
    python generate_emails.py              # Generate all 61 emails
    python generate_emails.py --lang sr    # Serbian (default)
    python generate_emails.py --lang ru    # Russian
    python generate_emails.py --lang en    # English
"""
import json
import os
import re
import urllib.parse

ROOT = os.path.dirname(os.path.abspath(__file__))
GENERATED = os.path.join(ROOT, "generated_sites")
SLUG_PATH = os.path.join(ROOT, "_slug_mapping.json")
OUTPUT_DIR = os.path.join(ROOT, "emails")
BASE_URL = "https://nsdrimtim21.github.io/novi-sad-business-sites"

DREAMTIM = {
    "company": "drimtim",
    "tagline": "Digital solutions for your business",
    "email": "info@drimtim.rs",
    "phone": "",
    "website": "https://drimtim.studio",
}

TEMPLATES = {
    "sr": {
        "greeting": "Poštovani {name},",
        "intro": "Piše vam tim iz kompanije drimtim.",
        "problem": "Primetili smo da Vaš biznis još uvek nema svoj veb-sajt. U današnje vreme je veoma važno imati online prisustvo kako bi Vas klijenti lako pronašli.",
        "offer": "Pripremili smo za Vas BESPLATAN demo sajt. Pogledajte kako bi mogao da izgleda:",
        "link": "👉 {url}",
        "benefits": [
            "Moderan, responzivan dizajn",
            "Vaše kontakt informacije i usluge",
            "Spremnost za Google promociju",
            "Mogućnost lakog dodavanja novih stranica",
        ],
        "cta": "Ukoliko Vam se sajt dopada, možete ga otkupiti za mali iznos. Takođe možemo:",
        "extras": [
            "Dodati nove sekcije i stranice",
            "Unaprediti dizajn prema Vašem brendu",
            "Povezati online zakazivanje/poručivanje",
            "Podesiti SEO optimizaciju",
            "Integrisati društvene mreže",
        ],
        "closing": "Kontaktirajte nas i dogovorićemo sve detalje!",
        "signoff": "Srdačno,\ndrimtim\n{email}\n{website}",
        "personalize": "Primetili smo da se bavite {category} delatnošću{services}{address}.",
    },
    "ru": {
        "greeting": "Здравствуйте, {name}!",
        "intro": "Вам пишет команда drimtim.",
        "problem": "Мы заметили, что у вашего бизнеса пока нет собственного сайта. В современном мире это очень важно — иметь онлайн-присутствие, чтобы клиенты могли легко вас найти.",
        "offer": "Мы подготовили для вас БЕСПЛАТНЫЙ демо-сайт. Посмотрите, как он может выглядеть:",
        "link": "👉 {url}",
        "benefits": [
            "Современный, адаптивный дизайн",
            "Ваши контактные данные и услуги",
            "Готовность к продвижению в Google",
            "Возможность легко добавить новые страницы",
        ],
        "cta": "Если вам нравится сайт, вы можете выкупить его за небольшую сумму. Мы также можем:",
        "extras": [
            "Добавить новые разделы и страницы",
            "Улучшить дизайн под ваш бренд",
            "Подключить онлайн-запись/заказ",
            "Настроить SEO продвижение",
            "Интегрировать социальные сети",
        ],
        "closing": "Свяжитесь с нами, и мы обсудим все детали!",
        "signoff": "С уважением,\nКоманда drimtim\n{email}\n{website}",
        "personalize": "Мы заметили, что вы занимаетесь {category}{services}{address}.",
    },
    "en": {
        "greeting": "Hello {name},",
        "intro": "This is the team at drimtim.",
        "problem": "We noticed that your business doesn't have a website yet. In today's digital world, having an online presence is essential for customers to find you easily.",
        "offer": "We've prepared a FREE demo website for you. Take a look:",
        "link": "👉 {url}",
        "benefits": [
            "Modern, responsive design",
            "Your contact information and services",
            "Ready for Google promotion",
            "Easy to add new pages",
        ],
        "cta": "If you like the website, you can purchase it for a small fee. We can also:",
        "extras": [
            "Add new sections and pages",
            "Improve the design to match your brand",
            "Set up online booking/ordering",
            "Configure SEO optimization",
            "Integrate social media",
        ],
        "closing": "Contact us and we'll discuss all the details!",
        "signoff": "Best regards,\ndrimtim\n{email}\n{website}",
        "personalize": "We noticed you're in the {category} business{services}{address}.",
    },
}


def load_data():
    """Load slug mapping and lead data for all generated businesses."""
    slug_map = {}
    if os.path.exists(SLUG_PATH):
        with open(SLUG_PATH, "r", encoding="utf-8") as f:
            slug_map = json.load(f)

    businesses = []
    folder_names = sorted(
        d for d in os.listdir(GENERATED)
        if os.path.isdir(os.path.join(GENERATED, d))
    )
    for folder_name in folder_names:
        slug = slug_map.get(folder_name) or re.sub(
            r"[^a-z0-9]+", "-",
            folder_name.lower().split("_", 1)[-1]
        ).strip("-")
        lead_path = os.path.join(GENERATED, folder_name, "lead_data.json")
        data = {}
        if os.path.exists(lead_path):
            with open(lead_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        biz = {
            "name": data.get("company_name", folder_name),
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "category": data.get("category", ""),
            "address": data.get("address", ""),
            "archetype": data.get("archetype", ""),
            "services": data.get("services", []),
            "usp": data.get("usp", []),
            "site_url": f"{BASE_URL}/{urllib.parse.quote(slug)}/",
            "folder": folder_name,
            "slug": slug,
        }
        businesses.append(biz)

    return businesses


def personalize(biz, lang):
    """Generate a personalized sentence about the business."""
    t = TEMPLATES[lang]
    category = biz["category"].lower() if biz["category"] else "your field"
    services = ""
    if biz["services"]:
        svc = ", ".join(biz["services"][:2]).lower()
        services = f", sa uslugama: {svc}" if lang == "sr" else f", offering {svc}"
    address = ""
    if biz["address"]:
        address = f" na adresi {biz['address']}" if lang == "sr" else f" at {biz['address']}"

    return t["personalize"].format(category=category, services=services, address=address)


def build_plain_text(biz, lang="sr"):
    """Build the full plain text email body."""
    t = TEMPLATES[lang]
    personal = personalize(biz, lang)

    benefits = "\n".join(f"• {b}" for b in t["benefits"])
    extras = "\n".join(f"• {e}" for e in t["extras"])
    signoff = t["signoff"].format(
        email=DREAMTIM["email"],
        phone=DREAMTIM["phone"],
        website=DREAMTIM["website"],
    )

    return f"""\
{t['greeting'].format(name=biz['name'])}

{t['intro']}

{t['problem']}

{personal}

{t['offer']}

{t['link'].format(url=biz['site_url'])}

Šta dobijate:
{benefits}

{t['cta']}
{extras}

{t['closing']}

{signoff}
"""


def build_html_email(biz, lang="sr"):
    """Build the full HTML email."""
    plain = build_plain_text(biz, lang)

    html = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>drimtim — {biz['name']}</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f4f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f4;padding:20px 0;">
        <tr>
            <td align="center">
                <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
                    <tr>
                        <td style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);padding:40px 30px;text-align:center;">
                            <h1 style="color:#ffffff;margin:0;font-size:28px;font-weight:700;">{DREAMTIM['company']}</h1>
                            <p style="color:#e94560;margin:8px 0 0 0;font-size:16px;">{DREAMTIM['tagline']}</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:40px 30px;">
                            <pre style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:15px;line-height:1.7;color:#333;white-space:pre-wrap;margin:0;">{plain}</pre>
                        </td>
                    </tr>
                    <tr>
                        <td style="background:#f8f9fa;padding:20px 30px;text-align:center;border-top:1px solid #eee;">
                            <p style="margin:0;font-size:13px;color:#888;">
                                {DREAMTIM['company']} &bull; {DREAMTIM['email']}
                            </p>
                            <p style="margin:8px 0 0 0;font-size:12px;color:#aaa;">
                                You received this email because we believe your business could benefit from a website.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""
    return html


def generate_all_emails(lang="sr"):
    """Generate all emails."""
    businesses = load_data()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    summary = []
    total = 0

    for biz in businesses:
        if not biz["email"]:
            print(f"  SKIP [{biz['folder']}] {biz['name']} — no email")
            continue

        html = build_html_email(biz, lang)
        plain = build_plain_text(biz, lang)

        safe = re.sub(r'[^\w\s-]', '', biz["name"]).strip().replace(" ", "_").lower()[:40]
        safe = safe or f"business_{biz['folder'][:3]}"

        html_path = os.path.join(OUTPUT_DIR, f"{safe}.html")
        txt_path = os.path.join(OUTPUT_DIR, f"{safe}.txt")
        md_path = os.path.join(OUTPUT_DIR, f"{safe}.md")

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(plain)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(plain)

        summary.append({
            "name": biz["name"],
            "email": biz["email"],
            "folder": biz["folder"],
            "slug": biz["slug"],
            "site_url": biz["site_url"],
            "html_file": f"{safe}.html",
            "txt_file": f"{safe}.txt",
            "md_file": f"{safe}.md",
        })

        total += 1
        print(f"  ✓ [{biz['folder']}] {biz['name']:40s} → {biz['email']:35s} → {safe}.html")

    # Summary JSON
    with open(os.path.join(OUTPUT_DIR, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # Master index
    rows = "".join(
        f"""
        <tr>
            <td><a href="{i['html_file']}">{i['name']}</a></td>
            <td><a href="mailto:{i['email']}">{i['email']}</a></td>
            <td><a href="{i['site_url']}" target="_blank">View Site</a></td>
            <td><a href="{i['txt_file']}">TXT</a></td>
        </tr>"""
        for i in summary
    )

    index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>drimtim — Generated Emails ({lang})</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f5f5f7; color:#1d1d1f; padding:40px 20px; }}
        h1 {{ font-size:2rem; margin-bottom:8px; }}
        p {{ color:#6e6e73; margin-bottom:24px; }}
        table {{ width:100%; border-collapse:collapse; background:white; border-radius:12px; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,0.08); }}
        th {{ background:#1a1a2e; color:white; padding:12px 16px; text-align:left; font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em; }}
        td {{ padding:10px 16px; border-bottom:1px solid #eee; font-size:0.9rem; }}
        tr:last-child td {{ border-bottom:none; }}
        a {{ color:#0f3460; text-decoration:none; }}
        a:hover {{ text-decoration:underline; color:#e94560; }}
        .count {{ display:inline-block; background:#e94560; color:white; padding:2px 10px; border-radius:20px; font-size:0.8rem; margin-left:10px; }}
    </style>
</head>
<body>
    <h1>drimtim — Generated Emails ({lang}) <span class="count">{len(summary)}</span></h1>
    <p>Cold email campaign for Novi Sad businesses without websites.</p>
    <table>
        <thead><tr><th>Business</th><th>Email</th><th>Site URL</th><th>Plain Text</th></tr></thead>
        <tbody>{rows}</tbody>
    </table>
</body>
</html>"""

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)

    print(f"\n{'='*60}")
    print(f"✅ Generated {total} emails ({lang}) in {OUTPUT_DIR}/")
    print(f"{'='*60}")


if __name__ == "__main__":
    import sys
    lang = "sr"
    if "--lang" in sys.argv:
        idx = sys.argv.index("--lang")
        if idx + 1 < len(sys.argv):
            lang = sys.argv[idx + 1]
    generate_all_emails(lang)
