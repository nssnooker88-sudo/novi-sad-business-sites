"""
Restructure generated sites for clean GitHub Pages URLs.

Each site gets its own top-level folder so URLs are clean:

  https://nssnooker88-sudo.github.io/novi-sad-business-sites/beg/
  https://nssnooker88-sudo.github.io/novi-sad-business-sites/fizio-protherapy/

Only index.html is published - no metadata files exposed.
Original generated_sites/ is kept as local archive.
"""
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))
GENERATED_DIR = os.path.join(ROOT, "generated_sites")


def slugify(name):
    """Convert business name to a clean URL slug."""
    name = name.strip()
    if not name:
        return "business"
    name = name.lower()
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[-\s]+', '-', name)
    name = name.strip('-')
    # Remove common filler words for shorter slugs
    for word in ['novi-sad', 'doo', 'company', 'in-novi-sad']:
        name = re.sub(rf'-{word}', '', name)
        name = re.sub(rf'{word}-', '', name)
    name = name.strip('-')
    if not name:
        return "business"
    return name[:60]


def clean_sites_folder():
    """Remove old site folders (non-project files) from root, except project files."""
    project_files = {
        '.gitignore', 'AGENTS.md', 'CLAUDE.md', 'README.md', 'requirements.txt',
        'config.example.json', 'main.py', 'enrich_leads.py', 'enrichment_pipeline.py',
        'generate_websites.py', 'find_emails.py', 'check_db.py', 'apr_scraper.py',
        'apr_email_finder.py', 'apr_email_enricher.py', 'debug_apr.py',
        'create_github_repo.py', 'enable_pages.py', 'verify_and_pages.py',
        'restructure_sites.py', 'database', 'scraper', 'venv', 'generated_sites',
        '.venv', '.claude', '.learnings', '__pycache__', 'logs', 'output', '.env',
        '_site_data', 'sites', '.github', 'build'
    }
    for item in os.listdir(ROOT):
        if item.startswith('.') or item in project_files:
            continue
        item_path = os.path.join(ROOT, item)
        if os.path.isdir(item_path):
            # Check if it's a site folder (has index.html, no .py files)
            has_html = os.path.exists(os.path.join(item_path, 'index.html'))
            has_py = any(f.endswith('.py') for f in os.listdir(item_path))
            if has_html and not has_py:
                print(f"  Removing old site folder: {item}/")
                shutil.rmtree(item_path)
        elif item.endswith('.html') and item != 'index.html':
            # Remove old stray HTML files
            os.remove(item_path)
            print(f"  Removing stray HTML: {item}")


def main():
    sites = []
    folders = sorted([
        f for f in os.listdir(GENERATED_DIR)
        if os.path.isdir(os.path.join(GENERATED_DIR, f)) and f[0].isdigit()
    ])

    print(f"Processing {len(folders)} site folders...\n")

    # First, clean up any previous site folders at root
    print("Cleaning up previous site folders...")
    clean_sites_folder()

    name_counter = {}
    slug_map = {}  # folder -> slug mapping for reference

    for folder in folders:
        folder_path = os.path.join(GENERATED_DIR, folder)

        # Read lead_data.json for business name
        lead_data_path = os.path.join(folder_path, "lead_data.json")
        business_name = folder[4:]  # fallback

        lead_data = {}
        if os.path.exists(lead_data_path):
            with open(lead_data_path, "r", encoding="utf-8") as f:
                lead_data = json.load(f)
            business_name = lead_data.get("company_name") or business_name

        # Create clean slug
        slug = slugify(business_name)

        # Handle duplicate slugs
        if slug in name_counter:
            name_counter[slug] += 1
            slug = f"{slug}-{name_counter[slug]}"
        else:
            name_counter[slug] = 1

        # Copy index.html to root-level folder
        src_html = os.path.join(folder_path, "index.html")
        if not os.path.exists(src_html):
            print(f"  ✗ {folder:50s} → no index.html found")
            continue

        target_dir = os.path.join(ROOT, slug)
        os.makedirs(target_dir, exist_ok=True)
        shutil.copy2(src_html, os.path.join(target_dir, "index.html"))

        print(f"  ✓ {folder:50s} → /{slug}/")
        slug_map[folder] = slug

        sites.append({
            "slug": slug,
            "name": business_name,
            "category": lead_data.get("category", ""),
            "email": lead_data.get("email", ""),
            "score": lead_data.get("purchase_probability_score", 0)
        })

    # Generate index.html at root (master directory)
    generate_root_index(sites)

    # Update .gitignore
    update_gitignore()

    # Save slug mapping for reference
    mapping_path = os.path.join(ROOT, "_slug_mapping.json")
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(slug_map, f, indent=2, ensure_ascii=False)
    print(f"\n  ✓ Slug mapping saved: _slug_mapping.json")

    print(f"\n{'='*60}")
    print(f"DONE! {len(sites)} sites restructured with clean URLs.")
    print(f"{'='*60}")
    print(f"\nSEND THESE URLs TO LEADS:")
    for s in sites:
        print(f"  https://nssnooker88-sudo.github.io/novi-sad-business-sites/{s['slug']}/")
    print(f"\nMASTER LIST:")
    print(f"  https://nssnooker88-sudo.github.io/novi-sad-business-sites/")


def generate_root_index(sites):
    """Generate the master index.html at the repo root."""
    cards = ""
    for s in sites:
        cards += f"""
<div class="card">
  <h3>{s['name'].replace('&', '&').replace('<', '<').replace('>', '>')}</h3>
  <div class="category">{s['category'].replace('&', '&').replace('<', '<').replace('>', '>')}</div>
  <div class="meta">{s['email'].replace('&', '&').replace('<', '<')}</div>
  <span class="score">Score: {s['score']}</span>
  <br>
  <a href="/novi-sad-business-sites/{s['slug']}/" target="_blank">Open Website →</a>
</div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Novi Sad Business Websites</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f7;color:#1d1d1f;padding:40px 20px}}
.container{{max-width:1200px;margin:0 auto}}
h1{{font-size:2rem;margin-bottom:8px}}
.subtitle{{color:#6e6e73;margin-bottom:32px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}}
.card{{background:white;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.04);transition:transform .2s,box-shadow .2s}}
.card:hover{{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,0.08)}}
.card h3{{font-size:1rem;margin-bottom:4px}}
.card .category{{font-size:.85rem;color:#6e6e73;margin-bottom:8px}}
.card .meta{{font-size:.8rem;color:#6e6e73;margin-bottom:12px}}
.card .score{{display:inline-block;background:#0071e3;color:white;padding:2px 8px;border-radius:4px;font-size:.75rem;font-weight:600}}
.card a{{display:inline-block;margin-top:8px;color:#0071e3;text-decoration:none;font-size:.9rem;font-weight:500}}
.card a:hover{{text-decoration:underline}}
.stats{{margin-bottom:24px;padding:16px;background:white;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,0.04)}}
.stats span{{font-weight:600}}
</style>
</head>
<body>
<div class="container">
<h1>Novi Sad Business Websites</h1>
<p class="subtitle">Professional websites generated for local businesses</p>
<div class="stats"><p>Total websites: <span>{len(sites)}</span></p></div>
<div class="grid">{cards}</div>
</div>
</body>
</html>"""

    index_path = os.path.join(ROOT, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✓ Root index.html generated with {len(sites)} sites")


def update_gitignore():
    """Ensure generated_sites/ and metadata are gitignored but site folders are not."""
    gitignore_path = os.path.join(ROOT, ".gitignore")
    with open(gitignore_path, "r") as f:
        lines = f.readlines()

    # Remove generated_sites/ line if present
    lines = [l for l in lines if l.strip() != "generated_sites/"]

    # Add generated_sites/ and _site_data/ and _slug_mapping.json
    entries_to_add = []
    if not any(l.strip() == "generated_sites/" for l in lines):
        entries_to_add.append("generated_sites/")
    if not any(l.strip() == "_site_data/" for l in lines):
        entries_to_add.append("_site_data/")
    if not any(l.strip() == "_slug_mapping.json" for l in lines):
        entries_to_add.append("_slug_mapping.json")

    if entries_to_add:
        # Add before any comment or at end
        lines.extend(["\n# Sensitive data\n"] + [f"{e}\n" for e in entries_to_add])

    with open(gitignore_path, "w") as f:
        f.writelines(lines)
    print(f"  ✓ .gitignore updated")


if __name__ == "__main__":
    main()