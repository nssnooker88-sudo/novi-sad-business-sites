"""
Audit all generated websites for completeness issues.
Checks for: placeholder text, missing sections, broken HTML, etc.
"""
import os
import re

GENERATED = "generated_sites"
issues = []
total = 0

for folder in sorted(os.listdir(GENERATED)):
    folder_path = os.path.join(GENERATED, folder)
    if not os.path.isdir(folder_path):
        continue
    
    html_path = os.path.join(folder_path, "index.html")
    if not os.path.exists(html_path):
        issues.append((folder, "MISSING index.html"))
        continue
    
    total += 1
    with open(html_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    
    size = len(content)
    lower = content.lower()
    checks = []
    
    # Size check
    if size < 500:
        checks.append(f"TOO SMALL ({size} bytes)")
    
    # Placeholder text checks
    if "lorem" in lower:
        checks.append("LOREM IPSUM placeholder text")
    
    if "todo" in lower or "tbd" in lower or "coming soon" in lower:
        checks.append("PLACEHOLDER text (todo/tbd/coming soon)")
    
    if "replace with" in lower:
        checks.append("POSSIBLE placeholder (replace with)")
    
    if "your business" in lower or "your company" in lower:
        checks.append("GENERIC text (your business/company)")
    
    if "sample" in lower:
        checks.append("SAMPLE text")
    
    if "example" in lower:
        checks.append("EXAMPLE text")
    
    if "under construction" in lower:
        checks.append("UNDER CONSTRUCTION")
    
    # Check for empty brackets
    if "[]" in content or "()" in content:
        checks.append("EMPTY brackets/parentheses")
    
    # Check for missing contact info
    if "tel:" not in content and "phone" not in lower[:3000]:
        checks.append("NO phone number")
    
    if "mailto:" not in content and "email" not in lower[:3000]:
        checks.append("NO email link")
    
    # Check for broken HTML (tag balance)
    div_open = content.count("<div")
    div_close = content.count("</div>")
    if div_open != div_close:
        checks.append(f"DIV MISMATCH ({div_open} open vs {div_close} close)")
    
    section_open = content.count("<section")
    section_close = content.count("</section>")
    if section_open != section_close:
        checks.append(f"SECTION MISMATCH ({section_open} open vs {section_close} close)")
    
    # Check for missing meta viewport (mobile responsiveness)
    if "viewport" not in lower[:1000]:
        checks.append("NO viewport meta tag")
    
    # Check for missing title
    if "<title>" not in content and "<title " not in content:
        checks.append("NO title tag")
    
    # Check for very short content (might be incomplete)
    text_only = re.sub(r'<[^>]+>', '', content).strip()
    word_count = len(text_only.split())
    if word_count < 50:
        checks.append(f"VERY SHORT content ({word_count} words)")
    
    if checks:
        issues.append((folder, "; ".join(checks)))

print(f"Total sites checked: {total}")
print(f"Sites with issues: {len(issues)}")
print()

# Group by severity
critical = [i for i in issues if any(x in i[1] for x in ["MISSING", "TOO SMALL", "LOREM", "DIV MISMATCH", "SECTION MISMATCH"])]
warnings = [i for i in issues if i not in critical]

if critical:
    print("=== CRITICAL ISSUES ===")
    for folder, problem in critical:
        print(f"  [{folder}] {problem}")
    print()

if warnings:
    print("=== WARNINGS ===")
    for folder, problem in warnings:
        print(f"  [{folder}] {problem}")
    print()

print(f"Clean sites (no issues): {total - len(issues)}/{total}")