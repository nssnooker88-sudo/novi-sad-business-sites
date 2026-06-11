"""
Fix broken HTML in generated sites:
1. Close all unclosed tags (div, section, body, html)
2. Generate missing index.html for 022_dental_excellence
3. Add phone/email contact info where missing
"""
import os
import re
import json
from html.parser import HTMLParser

GENERATED = "generated_sites"

# Tags that need closing
VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", 
                 "link", "meta", "param", "source", "track", "wbr"}
# Tags that auto-close
AUTO_CLOSE = {"li", "dt", "dd", "p", "td", "th", "tr", "thead", "tbody", "tfoot",
              "option", "optgroup"}


class TagFixer(HTMLParser):
    """Track open tags and determine what needs closing."""
    def __init__(self):
        super().__init__()
        self.open_tags = []
        self.errors = []
    
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in VOID_ELEMENTS:
            self.open_tags.append(tag)
    
    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.open_tags:
            # Remove this tag and all unclosed tags after it
            idx = len(self.open_tags) - 1 - self.open_tags[::-1].index(tag)
            self.open_tags = self.open_tags[:idx]
        elif tag in self.open_tags:
            self.open_tags.remove(tag)


def fix_html(content):
    """Fix truncated HTML by closing all open tags."""
    # First, check if it already ends properly
    stripped = content.strip()
    if stripped.endswith("</html>"):
        return content  # Already fine
    
    # Parse to find open tags
    fixer = TagFixer()
    try:
        fixer.feed(content)
    except Exception:
        pass
    
    open_tags = fixer.open_tags
    
    # Build closing tags in reverse order
    closing = []
    for tag in reversed(open_tags):
        if tag == "body" or tag == "html":
            closing.append(f"</{tag}>")
        elif tag not in AUTO_CLOSE:
            closing.append(f"</{tag}>")
    
    # Always ensure body and html are closed
    if "body" not in [t.lower() for t in open_tags]:
        closing.append("</body>")
    if "html" not in [t.lower() for t in open_tags]:
        closing.append("</html>")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_closing = []
    for tag in closing:
        if tag not in seen:
            seen.add(tag)
            unique_closing.append(tag)
    
    fixed = content.rstrip() + "\n" + "\n".join(unique_closing) + "\n"
    return fixed


def generate_missing_site(folder):
    """Generate a basic index.html for a site that's missing it."""
    lead_path = os.path.join(GENERATED, folder, "lead_data.json")
    if not os.path.exists(lead_path):
        return False
    
    with open(lead_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    name = data.get("company_name", "Business")
    email = data.get("email", "")
    phone = data.get("phone", "")
    address = data.get("address", "")
    category = data.get("category", "")
    rating = data.get("rating", "")
    description = data.get("description", f"Professional {category} services in Novi Sad.")
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} – Novi Sad</title>
    <meta name="description" content="{description}">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8f9fa; color: #1a1a2e; line-height: 1.6; }}
        .container {{ max-width: 1100px; margin: 0 auto; padding: 0 20px; }}
        header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 60px 0; text-align: center; }}
        header h1 {{ font-size: 2.5rem; margin-bottom: 10px; }}
        header p {{ font-size: 1.1rem; opacity: 0.9; }}
        .contact-bar {{ background: #0f3460; color: white; padding: 15px 0; text-align: center; }}
        .contact-bar a {{ color: #e94560; text-decoration: none; font-weight: 600; }}
        .contact-bar a:hover {{ text-decoration: underline; }}
        section {{ padding: 60px 0; }}
        section:nth-child(even) {{ background: white; }}
        h2 {{ font-size: 2rem; margin-bottom: 30px; text-align: center; }}
        .info-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 30px; }}
        .info-card {{ background: #f8f9fa; padding: 25px; border-radius: 12px; text-align: center; }}
        .info-card h3 {{ margin-bottom: 10px; color: #0f3460; }}
        .rating {{ font-size: 1.5rem; color: #f39c12; }}
        footer {{ background: #1a1a2e; color: white; text-align: center; padding: 30px 0; }}
        footer a {{ color: #e94560; }}
        @media (max-width: 768px) {{ header h1 {{ font-size: 1.8rem; }} }}
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>{name}</h1>
            <p>{description}</p>
        </div>
    </header>
    
    <div class="contact-bar">
        <div class="container">
"""
    if phone:
        html += f'            📞 <a href="tel:{phone.replace(" ", "")}">{phone}</a>\n'
    if email:
        html += f'            ✉️ <a href="mailto:{email}">{email}</a>\n'
    if address:
        html += f'            📍 {address}\n'
    
    html += """        </div>
    </div>
    
    <section>
        <div class="container">
            <h2>About Us</h2>
            <p style="text-align:center;max-width:800px;margin:0 auto;font-size:1.1rem;">"""
    html += description
    html += """</p>
        </div>
    </section>
"""
    
    if rating:
        html += f"""
    <section>
        <div class="container">
            <h2>Rating</h2>
            <div class="rating" style="text-align:center;font-size:2rem;">{'★' * int(float(rating))}{'☆' * (5 - int(float(rating)))} {rating}/5</div>
        </div>
    </section>
"""
    
    html += f"""
    <footer>
        <div class="container">
            <p>&copy; 2026 {name}. All rights reserved.</p>
"""
    if email:
        html += f'            <p>Email: <a href="mailto:{email}">{email}</a></p>\n'
    if phone:
        html += f'            <p>Phone: <a href="tel:{phone.replace(" ", "")}">{phone}</a></p>\n'
    
    html += """        </div>
    </footer>
</body>
</html>
"""
    
    with open(os.path.join(GENERATED, folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return True


def add_contact_info(content, phone, email):
    """Add phone/email to the HTML if missing."""
    if not phone and not email:
        return content
    
    additions = []
    if phone and "tel:" not in content:
        additions.append(f'<a href="tel:{phone.replace(" ", "")}">{phone}</a>')
    if email and "mailto:" not in content:
        additions.append(f'<a href="mailto:{email}">{email}</a>')
    
    if not additions:
        return content
    
    # Try to add before </footer> or at end of body
    contact_html = '\n<div class="contact-info" style="text-align:center;padding:20px;background:#f0f0f0;">\n'
    contact_html += ' | '.join(additions)
    contact_html += '\n</div>\n'
    
    if "</footer>" in content:
        content = content.replace("</footer>", contact_html + "</footer>")
    elif "</body>" in content:
        content = content.replace("</body>", contact_html + "</body>")
    else:
        content += contact_html
    
    return content


def main():
    # Sites with broken HTML (need tag closing)
    broken_folders = [
        "004_kljuc╠Мar_novi_sad_auto_bravar_novi_sad",
        "010_the_pub",
        "012_beg_servis",
        "017_stomatolis╠Мka_ordinacija_mm_dent",
        "025_elektrotim_doo",
        "028_servis_klima_novi_sad",
        "030_apartment_cactus_021",
        "031_dr_kruna",
        "038_skoc╠Мko",
        "042_moj_pedijatar_dr_andric_sanja",
        "051_ice",
        "053_specijalistic╠Мka_internistic╠Мka_ordinacija_dr_nedeljkovic╠Б",
        "054_nlo_instalacije",
        "055_vodoinstalater_instalacije_duka",
        "058_spinalis",
        "061_tiffany_apartment",
    ]
    
    # Sites missing contact info
    no_contact_folders = [
        "006_hostel_milkaza",
        "026_kljuc╠Мar_bravar_hitna_sluz╠Мba_novi_sad",
        "032_prima_pizza",
        "039_dental_district_stomatolos╠Мka_ordinacija_novi_sad",
        "040_soleil_medica",
        "048_advokat_jovana_savic╠Б",
        "052_campus_hostel",
        "056_kljuc╠М_servis_novi_sad_auto_kljuc╠Мar",
        "059_advokat_nada_korac╠Б",
        "060_dentistry",
    ]
    
    fixed_count = 0
    
    # Fix broken HTML
    print("=== Fixing broken HTML ===")
    for folder in broken_folders:
        path = os.path.join(GENERATED, folder, "index.html")
        if not os.path.exists(path):
            print(f"  [{folder}] SKIP - no index.html")
            continue
        
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        fixed = fix_html(content)
        
        if fixed != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(fixed)
            print(f"  [{folder}] FIXED - tags closed")
            fixed_count += 1
        else:
            print(f"  [{folder}] OK - no fix needed")
    
    # Generate missing site
    print("\n=== Generating missing site ===")
    if generate_missing_site("022_dental_excellence"):
        print("  [022_dental_excellence] GENERATED index.html from lead_data")
        fixed_count += 1
    else:
        print("  [022_dental_excellence] FAILED - no lead_data.json")
    
    # Add contact info
    print("\n=== Adding contact info ===")
    for folder in no_contact_folders:
        path = os.path.join(GENERATED, folder, "index.html")
        if not os.path.exists(path):
            continue
        
        # Read lead_data for phone/email
        lead_path = os.path.join(GENERATED, folder, "lead_data.json")
        phone = ""
        email = ""
        if os.path.exists(lead_path):
            with open(lead_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            phone = data.get("phone", "")
            email = data.get("email", "")
        
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        
        new_content = add_contact_info(content, phone, email)
        
        if new_content != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"  [{folder}] ADDED contact info (phone: {bool(phone)}, email: {bool(email)})")
            fixed_count += 1
        else:
            print(f"  [{folder}] OK - contact info already present")
    
    print(f"\n{'='*50}")
    print(f"Total fixes applied: {fixed_count}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()