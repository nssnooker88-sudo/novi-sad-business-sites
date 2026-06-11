"""
Analyze broken HTML sites in detail to understand what needs fixing.
"""
import os
import re

GENERATED = "generated_sites"

# Sites with critical HTML issues
critical_folders = [
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

# Missing index.html
missing_html = ["022_dental_excellence"]

for folder in critical_folders:
    path = os.path.join(GENERATED, folder, "index.html")
    if not os.path.exists(path):
        print(f"[{folder}] MISSING index.html")
        continue
    
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    
    size = len(content)
    ends_with_html = content.strip().endswith("</html>")
    ends_with_body = content.strip().endswith("</body>")
    html_count = content.count("</html>")
    body_count = content.count("</body>")
    div_open = content.count("<div")
    div_close = content.count("</div>")
    section_open = content.count("<section")
    section_close = content.count("</section>")
    
    print(f"[{folder}]")
    print(f"  Size: {size} bytes")
    print(f"  Ends with </html>: {ends_with_html} (count: {html_count})")
    print(f"  Ends with </body>: {ends_with_body} (count: {body_count})")
    print(f"  Div: {div_open} open / {div_close} close (diff: {div_open - div_close})")
    print(f"  Section: {section_open} open / {section_close} close (diff: {section_open - section_close})")
    
    # Show last 300 chars
    print(f"  Last 300 chars:")
    print(f"    {repr(content[-300:])}")
    print()

print("=== MISSING HTML ===")
for folder in missing_html:
    path = os.path.join(GENERATED, folder)
    if os.path.isdir(path):
        print(f"[{folder}] Contents: {os.listdir(path)}")
    else:
        print(f"[{folder}] Folder not found")