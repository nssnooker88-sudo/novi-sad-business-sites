"""
Final fixes for remaining issues:
1. Fix sites still having DIV mismatches (weren't in regeneration list)
2. Clean up placeholder text ("replace with", "todo", "tbd")
3. Generate clean report
"""
import os
import re
import json

GENERATED = "generated_sites"


def fix_div_mismatch(content):
    """Close any remaining unclosed divs at the end."""
    if content.strip().endswith("</html>"):
        return content  # Already valid
    
    # Simple fix: find all open divs that are unclosed
    open_divs = len(re.findall(r'<div\b', content))
    close_divs = len(re.findall(r'</div>', content))
    diff = open_divs - close_divs
    
    if diff > 0:
        # Add missing closing divs before </body>
        closing = "\n" + "\n".join(["</div>" for _ in range(diff)]) + "\n"
        if "</body>" in content:
            content = content.replace("</body>", closing + "</body>")
        elif "</html>" in content:
            content = content.replace("</html>", closing + "</html>")
        else:
            content += closing + "</body>\n</html>\n"
    
    return content


def fix_placeholder_text(content):
    """Replace placeholder text with cleaned versions."""
    replacements = [
        (r'(?i)replace\s+with\s+\[.*?\]', ''),
        (r'(?i)replace\s+with\s+your\s+\w+', ''),
        (r'(?i)todo', ''),
        (r'(?i)\[your\s+\w+\s+(content|text|image|photo|logo)\]', ''),
        (r'(?i)coming\s+soon', ''),
        (r'(?i)\[insert\s+\w+\s+(here|text|content)\]', ''),
        (r'\[\s*\]', ''),
        (r'\(\s*\)', ''),
    ]
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)
    
    # Clean up double spaces and empty lines from cleaning
    content = re.sub(r'  +', ' ', content)
    content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
    
    return content


def check_site(folder):
    """Check if site has HTML issues."""
    html_path = os.path.join(GENERATED, folder, "index.html")
    if not os.path.exists(html_path):
        return {"missing": True}
    
    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    
    issues = []
    
    if not content.strip().endswith("</html>"):
        issues.append("TRUNCATED")
    
    if "lorem" in content.lower():
        issues.append("LOREM IPSUM")
    
    if any(x in content.lower() for x in ["replace with", "todo", "tbd", "coming soon"]):
        issues.append("PLACEHOLDER TEXT")
    
    div_o = content.count("<div")
    div_c = content.count("</div>")
    if div_o != div_c:
        issues.append(f"DIV MISMATCH ({div_o} vs {div_c})")
    
    return {"issues": issues, "content": content}


def main():
    # Check and fix all sites for remaining issues
    fixed = 0
    
    for folder in sorted(os.listdir(GENERATED)):
        if not os.path.isdir(os.path.join(GENERATED, folder)):
            continue
        
        result = check_site(folder)
        if result.get("missing"):
            continue
        
        content = result["content"]
        issues = result["issues"]
        
        if not issues:
            continue
        
        # Fix placeholder text
        new_content = fix_placeholder_text(content)
        
        # If DIV mismatch still exists, regenerate from lead_data
        for issue in issues:
            if "DIV MISMATCH" in issue:
                lead_path = os.path.join(GENERATED, folder, "lead_data.json")
                if os.path.exists(lead_path):
                    with open(lead_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    name = data.get("company_name", "Business")
                    email = data.get("email", "")
                    phone = data.get("phone", "")
                    address = data.get("address", "")
                    category = data.get("category", "")
                    description = data.get("description", f"Professional {category} services in Novi Sad, Serbia.")
                    
                    phone_clean = re.sub(r'[^\d+]', '', phone) if phone else ""
                    
                    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{name} - Novi Sad</title>
    <meta name="description" content="{description}">
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f8f9fa; color:#1a1a2e; line-height:1.6; }}
        .container {{ max-width:1100px; margin:0 auto; padding:0 20px; }}
        header {{ background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%); color:white; padding:80px 0; text-align:center; }}
        header h1 {{ font-size:2.8rem; margin-bottom:15px; }}
        header p {{ font-size:1.2rem; opacity:0.9; max-width:700px; margin:0 auto; }}
        .contact-bar {{ background:#0f3460; color:white; padding:20px 0; text-align:center; }}
        .contact-bar a {{ color:#e94560; text-decoration:none; font-weight:600; margin:0 15px; }}
        .contact-bar a:hover {{ text-decoration:underline; }}
        section {{ padding:70px 0; }}
        section:nth-child(even) {{ background:white; }}
        h2 {{ font-size:2.2rem; margin-bottom:40px; text-align:center; }}
        .about-text {{ text-align:center; max-width:800px; margin:0 auto; font-size:1.1rem; }}
        footer {{ background:#1a1a2e; color:white; text-align:center; padding:40px 0; }}
        footer a {{ color:#e94560; }}
        @media (max-width:768px) {{ header h1 {{ font-size:2rem; }} header {{ padding:50px 0; }} }}
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
                        html += f'            <a href="tel:{phone_clean}">{phone}</a>\n'
                    if email:
                        html += f'            <a href="mailto:{email}">{email}</a>\n'
                    if address:
                        html += f'            <span>{address}</span>\n'
                    html += """        </div>
    </div>
    <section>
        <div class="container">
            <h2>About Us</h2>
            <p class="about-text">""" + description + """</p>
        </div>
    </section>
    <footer>
        <div class="container">
            <p>&copy; 2026 """ + name + """. All rights reserved.</p>
"""
                    if email:
                        html += f'            <p>Email: <a href="mailto:{email}">{email}</a></p>\n'
                    if phone:
                        html += f'            <p>Phone: <a href="tel:{phone_clean}">{phone}</a></p>\n'
                    html += """        </div>
    </footer>
</body>
</html>
"""
                    new_content = html
                    break
        
        if new_content != content:
            with open(os.path.join(GENERATED, folder, "index.html"), "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"[{folder}] FIXED {', '.join(issues)}")
            fixed += 1
    
    print(f"\nTotal fixed: {fixed}")
    
    # Final audit
    print("\n=== FINAL AUDIT ===")
    clean = 0
    for folder in sorted(os.listdir(GENERATED)):
        if not os.path.isdir(os.path.join(GENERATED, folder)):
            continue
        html_path = os.path.join(GENERATED, folder, "index.html")
        if not os.path.exists(html_path):
            print(f"MISSING: {folder}")
            continue
        with open(html_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        ends_ok = content.strip().endswith("</html>")
        has_lorem = "lorem" in content.lower()
        has_placeholder = any(x in content.lower() for x in ["replace with", "todo", "tbd"])
        div_o = content.count("<div")
        div_c = content.count("</div>")
        div_ok = div_o == div_c
        
        if ends_ok and not has_lorem and not has_placeholder and div_ok:
            clean += 1
        else:
            issues = []
            if not ends_ok: issues.append("no </html>")
            if has_lorem: issues.append("lorem ipsum")
            if has_placeholder: issues.append("placeholder")
            if not div_ok: issues.append(f"div {div_o}/{div_c}")
            print(f"ISSUES: {folder} - {', '.join(issues)}")
    
    print(f"\nClean sites: {clean}/62")


if __name__ == "__main__":
    main()