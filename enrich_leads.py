"""
Enrich Leads Script.
Queries CompanyWall directly to find official PIB, MB, and email contacts for high-priority leads,
and updates them in the SQLite database.
"""

import sqlite3
import urllib.request
import urllib.parse
import ssl
import re
import time
import random
import os

from database.db import Database

DB_PATH = "/Users/mnengert/Desktop/БОТ/БОТ КЛОД/database/businesses.sqlite"
ssl_context = ssl._create_unverified_context()

def get_html(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'sr-RS,sr;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ssl_context) as response:
            return response.read().decode('utf-8')
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None

def search_companywall(query_val):
    query = urllib.parse.quote(query_val)
    url = f"https://www.companywall.rs/pretraga?n={query}"
    html = get_html(url)
    if not html:
        return []
    links = re.findall(r'href="(/firma/[^"]*)"', html)
    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for l in links:
        if l not in seen:
            seen.add(l)
            deduped.append(l)
    return deduped

def parse_profile(html):
    if not html:
        return None, None, None
    
    # PIB (9 digits, starts with 1)
    pib_match = re.search(r'PIB[^\d]*(\d{9})', html, re.IGNORECASE)
    pib = pib_match.group(1) if pib_match else None
    
    # Matični broj (8 digits)
    mb_match = re.search(r'(?:Matični broj|MB)[^\d]*(\d{8})', html, re.IGNORECASE)
    mb = mb_match.group(1) if mb_match else None
    
    # Email mailto link
    email_match = re.search(r'mailto:([\w\.-]+@[\w\.-]+\.\w+)', html, re.IGNORECASE)
    email = email_match.group(1) if email_match else None
    
    if not email:
        # Fallback to search in text
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', html)
        valid_emails = [e for e in emails if not e.endswith(('png', 'jpg', 'jpeg', 'gif', 'js', 'css', 'w3.org'))]
        email = valid_emails[0] if valid_emails else None
        
    return pib, mb, email

def clean_phone(phone):
    if not phone:
        return ""
    # Remove all non-digits except +
    return re.sub(r'[^\d]', '', phone)

def transliterate(text):
    replacements = {
        'č': 'c', 'ć': 'c', 'š': 's', 'đ': 'd', 'ž': 'z',
        'Č': 'C', 'Ć': 'C', 'Š': 'S', 'Đ': 'D', 'Ž': 'Z'
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

def is_valid_match(query_name, profile_link, business_address=""):
    # Extract slug from profile link
    # profile_link is e.g. "/firma/advokat-milica-savic/MMx5Lcn7R"
    parts = [p for p in profile_link.split('/') if p]
    if not parts:
        return False
    slug = parts[-2] if len(parts) >= 2 else parts[0]
    
    # Transliterate and normalize both
    query_norm = transliterate(query_name.lower())
    slug_norm = transliterate(slug.replace('-', ' ').lower())
    
    # Clean special chars
    query_norm = re.sub(r'[^\w\s]', ' ', query_norm)
    query_norm = re.sub(r'\s+', ' ', query_norm).strip()
    
    slug_norm = re.sub(r'[^\w\s]', ' ', slug_norm)
    slug_norm = re.sub(r'\s+', ' ', slug_norm).strip()
    
    # Stopwords to filter out
    stopwords = {
        'advokat', 'advokatska', 'kancelarija', 'dr', 'za', 'krivicno', 'krivično', 'pravo',
        'stomatolog', 'stomatoloska', 'stomatološka', 'ordinacija', 'dent', 'dental',
        'vulkanizer', 'vulkanizerska', 'vulkanizerski', 'gume',
        'auto', 'servis', 'mehanicar', 'mehaničar', 'automehanicar', 'automehaničar',
        'vodoinstalater', 'vodoinstalaterska', 'instalacije',
        'klima', 'klime', 'rashladni', 'grejanje',
        'salon', 'lepote', 'beauty', 'frizerski', 'frizersko', 'kozmeticki', 'kozmetički', 'studio', 'masaza', 'masaža', 'massage',
        'apartman', 'apartmani', 'apartments', 'rooms', 'hostel', 'hotel', 'smestaj', 'smeštaj', 'stan na dan',
        'moler', 'molerski', 'gips', 'fasada',
        'agencija', 'nekretnine', 'taksi', 'taxi',
        'doo', 'pr', 'szr', 'str', 'od', 'kd', 'novi', 'sad', 'ns', 'firma'
    }
    
    query_words = [w for w in query_norm.split() if w and w not in stopwords]
    if not query_words:
        query_words = [w for w in query_norm.split() if w]
        
    slug_words = set(slug_norm.split())
    
    # Check if all query words are matched in slug words
    for w in query_words:
        matched = False
        for sw in slug_words:
            if w == sw:
                matched = True
                break
            if len(w) >= 3 and len(sw) >= 3:
                if w in sw or sw in w:
                    matched = True
                    break
        if not matched:
            return False
            
    # Geo-filtering: check if the slug contains a Serbian city that is not in the address
    serbian_cities = {
        'beograd', 'nis', 'nis', 'kragujevac', 'subotica', 'zrenjanin', 'golubac', 'pancevo',
        'sabac', 'valjevo', 'cacak', 'kraljevo', 'novi-pazar', 'leskovac', 'vranje',
        'smederevo', 'kikinda', 'sombor', 'pirot', 'pozarevac', 'jagodina', 'vrsac',
        'bor', 'prokuplje', 'loznica', 'sremska-mitrovica', 'ruma', 'indija', 'krusevac',
        'uzice', 'pozega', 'obrenovac', 'lazarevac', 'mladenovac', 'vlasotince', 'vrbas',
        'becej', 'kula', 'temerin', 'sid', 'knjazevac', 'negotin', 'zajecar',
        'aleksinac', 'svrljig', 'trstenik', 'backa-palanka'
    }
    
    addr_norm = transliterate(business_address.lower()) if business_address else ""
    ns_regions = {'novi sad', 'futog', 'veternik', 'petrovaradin', 'sremska kamenica', 'sremska-kamenica'}
    
    for city in serbian_cities:
        if city in slug_words:
            if city in ns_regions:
                continue
            if city not in addr_norm:
                print(f"  Geo-filtered: matched city '{city}' in slug, but not in address '{business_address}'")
                return False
            
    return True

def generate_search_terms(name):
    terms = []
    
    # 1. Cleaned full name
    clean = re.sub(r'[\-\(\)\:\,\|]', ' ', name)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if clean:
        terms.append(clean)
        
    # 2. Parts separated by delimiters
    parts = re.split(r'[\|\-\(\)\:\,]', name)
    for p in parts:
        p_clean = re.sub(r'\s+', ' ', p).strip()
        if len(p_clean) >= 3:
            terms.append(p_clean)
            
    # 3. Strip common generic prefixes / category words
    stopwords = [
        r'\badvokat\b', r'\badvokatska\b', r'\bkancelarija\b', r'\bdr\b', r'\bza\b', r'\bkrivično\b', r'\bkrivicno\b', r'\bpravo\b',
        r'\bstomatolog\b', r'\bstomatološka\b', r'\bstomatoloska\b', r'\bordinacija\b', r'\bdent\b', r'\bdental\b',
        r'\bvulkanizer\b', r'\bvulkanizerska\b', r'\bvulkanizerski\b', r'\bgume\b',
        r'\bauto\b', r'\bservis\b', r'\bmehaničar\b', r'\bmehanicar\b', r'\bautomehaničar\b',
        r'\bvodoinstalater\b', r'\bvodoinstalaterska\b', r'\binstalacije\b',
        r'\bklima\b', r'\bklime\b', r'\brashladni\b', r'\bgrejanje\b',
        r'\bsalon\b', r'\blepote\b', r'\bbeauty\b', r'\bfrizerski\b', r'\bfrizersko\b', r'\bkozmetički\b', r'\bkozmeticki\b', r'\bstudio\b', r'\bmasaža\b', r'\bmasaza\b',
        r'\bapartman\b', r'\bapartmani\b', r'\bapartments\b', r'\brooms\b', r'\bhostel\b', r'\bhotel\b', r'\bsmeštaj\b', r'\bsmestaj\b', r'\bstan na dan\b',
        r'\bmoler\b', r'\bmolerski\b', r'\bgips\b', r'\bfasada\b',
        r'\bagencija\b', r'\bnekretnine\b',
        r'\btaksi\b', r'\btaxi\b',
        r'\bd\.o\.o\b', r'\bdoo\b', r'\bpr\b', r'\bszr\b', r'\bstr\b', r'\bod\b', r'\bkd\b',
        r'\bnovi sad\b', r'\bnovom sadu\b', r'\bns\b'
    ]
    
    for term in list(terms):
        t_low = term.lower()
        for sw in stopwords:
            t_low = re.sub(sw, '', t_low)
        t_clean = re.sub(r'\s+', ' ', t_low).strip()
        if len(t_clean) >= 3:
            terms.append(t_clean.title())
            
    # 4. Append "Novi Sad" where not present
    extended = []
    for t in terms:
        extended.append(t)
        if "novi sad" not in t.lower() and "novom sadu" not in t.lower():
            extended.append(f"{t} Novi Sad")
            
    # Dedup preserving order
    seen = set()
    unique = []
    for t in extended:
        t_low = t.lower()
        if t_low not in seen:
            seen.add(t_low)
            unique.append(t)
            
    return unique

def main():
    # Initialize Database to trigger column migrations
    db = Database(DB_PATH)
    db.close()
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Get all high priority leads that don't have PIB/email yet
    cursor = conn.cursor()
    cursor.execute("""
        SELECT business_id, business_name, phone, address, category 
        FROM businesses 
        WHERE lead_status = 'HIGH_PRIORITY' AND pib IS NULL
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    
    print(f"Found {len(rows)} HIGH_PRIORITY leads without PIB/email data.")
    
    success_count = 0
    
    for i, row in enumerate(rows):
        b_id = row['business_id']
        name = row['business_name']
        phone = row['phone']
        address = row['address']
        
        print(f"[{i+1}/{len(rows)}] Process lead: '{name}'")
        
        # Strategies for searching:
        # Try search terms generated from name
        queries = generate_search_terms(name)
        links = []
        for q in queries:
            print(f"  Searching CompanyWall for: '{q}'")
            candidate_links = search_companywall(q)
            # Verify matches passing address
            valid_links = [l for l in candidate_links if is_valid_match(name, l, address)]
            if valid_links:
                links = valid_links
                break
                
        # If no valid match found via name, try search by phone
        if not links and phone:
            digits = clean_phone(phone)
            # Serbian local phones might be 021... or 06...
            # Search by last 6 digits of the phone which is very unique
            if len(digits) >= 6:
                print(f"  Searching CompanyWall by phone suffix: '{digits[-6:]}'")
                links = search_companywall(digits[-6:])
            
        if not links:
            print("  No companywall profile found.")
            time.sleep(1 + random.random() * 2)
            continue
            
        # Visit first matched profile
        profile_link = "https://www.companywall.rs" + links[0]
        print(f"  Found profile: {profile_link}")
        
        # Delay before visiting profile to avoid block
        time.sleep(1 + random.random() * 2)
        
        prof_html = get_html(profile_link)
        pib, mb, email = parse_profile(prof_html)
        
        if pib or mb or email:
            print(f"  Enriched: PIB={pib}, MB={mb}, EMAIL={email}")
            conn.execute("""
                UPDATE businesses 
                SET pib = ?, registration_number = ?, email = ?, updated_at = datetime('now')
                WHERE business_id = ?
            """, (pib, mb, email, b_id))
            conn.commit()
            success_count += 1
        else:
            print("  Failed to parse fields from profile.")
            
        # Sleep between loops
        time.sleep(2 + random.random() * 2)

    print(f"\nEnrichment complete. Successfully enriched {success_count} leads.")
    conn.close()

if __name__ == "__main__":
    main()
