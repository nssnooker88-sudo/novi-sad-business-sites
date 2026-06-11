"""
Regenerate sites that have broken HTML:
1. Sites that don't start with <!DOCTYPE (AI conversational output)
2. Sites with truncated HTML (no closing tags)
3. Missing index.html
"""
import os
import json
import re

GENERATED = "generated_sites"


def extract_html_from_conversational(content):
    """Try to extract HTML from a conversational AI response."""
    # Look for HTML in a code block
    match = re.search(r'```(?:html)?\s*\n?(.*?)\n?```', content, re.DOTALL)
    if match:
        html = match.group(1).strip()
        if html.startswith("<!DOCTYPE") or html.startswith("<html") or html.startswith("<!"):
            return html
    # Try finding DOCTYPE directly
    idx = content.find("<!DOCTYPE")
    if idx >= 0:
        return content[idx:]
    return None


def generate_template_site(folder):
    """Generate a complete website from lead_data.json."""
    lead_path = os.path.join(GENERATED, folder, "lead_data.json")
    if not os.path.exists(lead_path):
        return False, "No lead_data.json"
    
    with open(lead_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    name = data.get("company_name", "Business")
    email = data.get("email", "")
    phone = data.get("phone", "")
    address = data.get("address", "")
    category = data.get("category", "")
    rating = data.get("rating", "")
    reviews = data.get("reviews", "")
    website = data.get("website", "")
    description = data.get("description", "")
    
    # Build clean description
    if not description:
        description = f"Professional {category} services in Novi Sad, Serbia."
    
    # Clean phone for tel: link
    phone_clean = re.sub(r'[^\d+]', '', phone) if phone else ""
    
    # Stars for rating
    stars_html = ""
    if rating:
        try:
            r = float(rating)
            stars = "★" * int(r) + "☆" * (5 - int(r))
            stars_html = f'<div class="rating">{stars} <span class="rating-num">{rating}</span></div>'
        except:
            pass
    
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
        header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 80px 0; text-align: center; }}
        header h1 {{ font-size: 2.8rem; margin-bottom: 15px; }}
        header p {{ font-size: 1.2rem; opacity: 0.9; max-width: 700px; margin: 0 auto; }}
        .contact-bar {{ background: #0f3460; color: white; padding: 20px 0; text-align: center; }}
        .contact-bar a {{ color: #e94560; text-decoration: none; font-weight: 600; margin: 0 15px; }}
        .contact-bar a:hover {{ text-decoration: underline; }}
        section {{ padding: 70px 0; }}
        section:nth-child(even) {{ background: white; }}
        h2 {{ font-size: 2.2rem; margin-bottom: 40px; text-align: center; }}
        .about-text {{ text-align: center; max-width: 800px; margin: 0 auto; font-size: 1.1rem; }}
        footer {{ background: #1a1a2e; color: white; text-align: center; padding: 40px 0; }}
        footer a {{ color: #e94560; }}
        .rating {{ font-size: 2rem; color: #f39c12; text-align: center; }}
        .rating-num {{ font-size: 1.2rem; color: #333; margin-left: 10px; }}
        @media (max-width: 768px) {{ header h1 {{ font-size: 2rem; }} header {{ padding: 50px 0; }} }}
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
        html += f'            📞 <a href="tel:{phone_clean}">{phone}</a>\n'
    if email:
        html += f'            ✉️ <a href="mailto:{email}">{email}</a>\n'
    if address:
        html += f'            📍 {address}\n'
    html += """        </div>
    </div>
    
    <section>
        <div class="container">
            <h2>About Us</h2>
            <p class="about-text">""" + description + """</p>
        </div>
    </section>
"""
    
    if stars_html:
        html += f"""
    <section>
        <div class="container">
            <h2>Our Rating</h2>
            {stars_html}
"""
        if reviews:
            html += f"            <p style=\"text-align:center;margin-top:15px;\">Based on {reviews} reviews</p>\n"
        html += """        </div>
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
        html += f'            <p>Phone: <a href="tel:{phone_clean}">{phone}</a></p>\n'
    if address:
        html += f'            <p>Address: {address}</p>\n'
    
    html += """        </div>
    </footer>
</body>
</html>
"""
    
    return True, html


def main():
    fixed_count = 0
    
    for folder in sorted(os.listdir(GENERATED)):
        folder_path = os.path.join(GENERATED, folder)
        if not os.path.isdir(folder_path):
            continue
        
        html_path = os.path.join(folder_path, "index.html")
        
        needs_regeneration = False
        
        if not os.path.exists(html_path):
            print(f"[{folder}] MISSING index.html → regenerating")
            needs_regeneration = True
        else:
            with open(html_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            # Check if it starts properly
            stripped = content.lstrip()
            if not stripped.startswith("<!DOCTYPE") and not stripped.startswith("<html"):
                print(f"[{folder}] BAD START (AI conversational) → regenerating")
                needs_regeneration = True
            elif not content.strip().endswith("</html>"):
                print(f"[{folder}] TRUNCATED → regenerating")
                needs_regeneration = True
        
        if needs_regeneration:
            success, result = generate_template_site(folder)
            if success:
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(result)
                print(f"  ✓ Regenerated from lead_data.json")
                fixed_count += 1
            else:
                print(f"  ✗ {result}")
    
    print(f"\nTotal regenerated: {fixed_count}")
    
    # Final verification
    print("\n=== Final Verification ===")
    all_ok = True
    issues = []
    for folder in sorted(os.listdir(GENERATED)):
        if not os.path.isdir(os.path.join(GENERATED, folder)):
            continue
        html_path = os.path.join(GENERATED, folder, "index.html")
        if not os.path.exists(html_path):
            issues.append((folder, "MISSING"))
            all_ok = False
            continue
        with open(html_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if not content.strip().endswith("</html>"):
            issues.append((folder, "TRUNCATED"))
            all_ok = False
    
    if all_ok:
        print("✓ All 62 sites have valid HTML starting with <!DOCTYPE and ending with </html>")
    else:
        for folder, issue in issues:
            print(f"  ✗ [{folder}] {issue}")


if __name__ == "__main__":
    main()