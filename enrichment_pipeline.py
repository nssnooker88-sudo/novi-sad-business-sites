#!/usr/bin/env python3
"""
Business Data Enrichment & Website Prompt Generation Pipeline.
Integrates Dataset A (SQLite DB), Dataset B (Email CSV), and Dataset C (Research CSV).
Produces unified company profiles and custom website prompts in JSON format.
"""

import os
import sys
import re
import json
import sqlite3
import argparse
import difflib
from urllib.parse import urlparse

# Ensure pandas is available
try:
    import pandas as pd
except ImportError:
    print("Error: pandas is required to run this pipeline. Please run the script in the virtual environment.")
    sys.exit(1)

# List of Serbian legal suffixes and common business descriptors to strip
SERBIAN_LEGAL_SUFFIXES = [
    r'\bd\.o\.o\b', r'\bdoo\b', r'\bpr\b', r'\bszr\b', r'\bstr\b',
    r'\bod\b', r'\bkd\b', r'\ba\.d\b', r'\bad\b', r'\bdooel\b',
    r'\bpreduzetnik\b', r'\bradnja\b', r'\bordinacija\b', r'\bkancelarija\b',
    r'\budruzenje\b', r'\budruženje\b', r'\bdr\b', r'\bdooel\b',
    r'\bdooel-import\b', r'\bs\.p\b', r'\bsp\b', r'\bpreduzece\b', r'\bpreduzeće\b'
]

# Archetype dictionary with mapping configurations
ARCHETYPE_CONFIG = {
    "emergency_service": {
        "style": "High-contrast, action-oriented design with bright emergency accents (red/orange) and large, prominent tap-to-call buttons.",
        "goal": "Direct phone calls for immediate service requests.",
        "tone": "Urgent, reliable, and highly professional.",
        "sections": ["Hero", "Emergency Callout", "Services", "Why Choose Us", "Reviews", "FAQ", "Contact", "Map"],
        "cta_label": "Call Now",
        "image_style": "Action-oriented, practical, authentic photos of technicians on-site, vans, and tools.",
        "image_subjects": ["Technician working on-site", "Emergency response vehicle", "Close-up of tools and equipment"],
        "avoid_images": ["Generic smiling office staff", "Clean corporate boardroom handshakes", "Sunset landscapes"]
    },
    "beauty": {
        "style": "Elegant, chic aesthetic using soft pastel or warm earthy tones, premium minimalist layout, and stylish serif typography.",
        "goal": "Book online appointments or consultations.",
        "tone": "Warm, welcoming, luxurious, and detail-oriented.",
        "sections": ["Hero", "About", "Services", "Pricing", "Portfolio", "Reviews", "Booking Form", "Contact", "Map"],
        "cta_label": "Book Appointment",
        "image_style": "Aesthetic, clean, bright lighting, relaxing atmosphere, close-up details.",
        "image_subjects": ["Salon interior view", "Beauty treatment session in progress", "Close-up of premium cosmetic products"],
        "avoid_images": ["Industrial machinery", "Generic medical rooms", "Graphs or charts"]
    },
    "healthcare": {
        "style": "Clean, trust-focused layout with a professional blue, teal, or green color palette, generous whitespace, and readable sans-serif typography.",
        "goal": "Schedule an appointment, consultation, or clinical visit.",
        "tone": "Reassuring, professional, authoritative, and compassionate.",
        "sections": ["Hero", "About", "Services", "Team", "Why Choose Us", "Reviews", "FAQ", "Booking Form", "Contact", "Map"],
        "cta_label": "Schedule Consult",
        "image_style": "Professional, bright, warm, reassuring, clean clinical spaces.",
        "image_subjects": ["Friendly doctor or specialist", "Modern clinic examination room", "Medical diagnostic equipment"],
        "avoid_images": ["Scary-looking needles or surgeries", "Dark or gloomy interiors", "Cartoon illustrations"]
    },
    "food": {
        "style": "Appetizing, sensory-rich layout with rich warm tones (amber, deep red, forest green), large high-quality food photography, and integrated menu displays.",
        "goal": "Place online orders, reserve a table, or view the menu.",
        "tone": "Inviting, friendly, casual, and passionate.",
        "sections": ["Hero", "About", "Services", "Pricing", "Portfolio", "Reviews", "Opening Hours", "Lead Form", "Contact", "Map"],
        "cta_label": "Reserve a Table",
        "image_style": "Close-up food shots, warm lighting, vibrant colors, active dining environments.",
        "image_subjects": ["Freshly prepared signature dish", "Warm restaurant interior dining area", "Chef preparing food in kitchen"],
        "avoid_images": ["Cold corporate office spaces", "Abstract art", "Empty tables or dark rooms"]
    },
    "professional_services": {
        "style": "Structured, corporate, professional layout with deep blues, grays, and whites, strong layout lines, and authoritative serif typography.",
        "goal": "Request a consult, contact the office, or submit a case details form.",
        "tone": "Trustworthy, expert, serious, and precise.",
        "sections": ["Hero", "About", "Services", "Team", "Why Choose Us", "Reviews", "FAQ", "Lead Form", "Contact", "Map"],
        "cta_label": "Request Consultation",
        "image_style": "Professional, executive, crisp lighting, high quality corporate settings.",
        "image_subjects": ["Modern office building or workspace", "Lawyer or consultant looking professional", "Meeting room with notebook and pen"],
        "avoid_images": ["Casual beach scenes", "Over-the-top party environments", "Generic cartoony stock graphics"]
    },
    "home_improvement": {
        "style": "Clean, service-focused design using contrasting colors (e.g. blue and yellow/orange), featuring review badges, project galleries, and simple estimate request forms.",
        "goal": "Request a free quote, project estimate, or service call.",
        "tone": "Reliable, skilled, honest, and hardworking.",
        "sections": ["Hero", "About", "Services", "Portfolio", "Why Choose Us", "Reviews", "FAQ", "Lead Form", "Contact", "Map"],
        "cta_label": "Request Free Quote",
        "image_style": "Before-and-after projects, active workers on site, crisp and clear project completions.",
        "image_subjects": ["Completed remodeling project", "Craftsman or technician at work", "Detailed view of quality materials used"],
        "avoid_images": ["Stock office layouts", "Abstract concepts", "Blurry mobile phone pictures"]
    },
    "automotive": {
        "style": "Sleek, dark or high-contrast scheme, showcasing quality guarantees, direct phone calls, and clear services checklists.",
        "goal": "Book a service, call the shop, or request an estimate.",
        "tone": "Expert, efficient, robust, and customer-first.",
        "sections": ["Hero", "About", "Services", "Pricing", "Why Choose Us", "Reviews", "FAQ", "Booking Form", "Contact", "Map"],
        "cta_label": "Schedule Service",
        "image_style": "Action shots in workshop, shiny polished vehicles, professional machinery.",
        "image_subjects": ["Mechanic servicing a vehicle", "Close-up of car engine or wheels", "Clean and organized auto workshop interior"],
        "avoid_images": ["Corporate boardroom presentations", "Cooking or culinary themes", "Generic city skylines"]
    },
    "fitness": {
        "style": "Dynamic, energetic, bold layout using vibrant neon or dark high-contrast themes, featuring class schedules, trainer profiles, and membership signups.",
        "goal": "Join the gym, book a trial class, or buy a pass.",
        "tone": "Motivating, energetic, supportive, and active.",
        "sections": ["Hero", "About", "Services", "Pricing", "Team", "Reviews", "FAQ", "Lead Form", "Contact", "Map"],
        "cta_label": "Get Free Trial",
        "image_style": "Dynamic, high contrast, active movements, bright motivating fitness centers.",
        "image_subjects": ["Person training or lifting weights", "Modern gym interior with workout gear", "Group fitness training session"],
        "avoid_images": ["Sedentary office settings", "Medical patients in hospital beds", "Sweets or junk food"]
    },
    "retail": {
        "style": "Clean, product-focused layout, high usability, light backgrounds, direct catalog highlights, and customer reviews sections.",
        "goal": "View the products, call for availability, or visit the shop.",
        "tone": "Friendly, helpful, warm, and inviting.",
        "sections": ["Hero", "About", "Services", "Portfolio", "Reviews", "FAQ", "Opening Hours", "Contact", "Map"],
        "cta_label": "Shop Now",
        "image_style": "Bright, colorful, showcasing product variety and welcoming storefronts.",
        "image_subjects": ["Inside view of the shop showcasing products", "Close-up of premium products on shelf", "Smiling staff helping at checkout"],
        "avoid_images": ["Industrial factories", "Abstract network nodes", "Generic office boardrooms"]
    },
    "general_local_business": {
        "style": "Friendly, welcoming local design, clean grid architecture, trust credentials, and easy-to-use booking or contact forms.",
        "goal": "Submit a contact form or request more information.",
        "tone": "Friendly, professional, helpful, and community-focused.",
        "sections": ["Hero", "About", "Services", "Why Choose Us", "Reviews", "Contact", "Map", "Opening Hours"],
        "cta_label": "Contact Us",
        "image_style": "Authentic, friendly, local storefronts, professional staff.",
        "image_subjects": ["Shop front or workspace", "Team members smiling", "Close-up of business operations"],
        "avoid_images": ["Hyper-corporate skyscrapers", "Extreme luxury", "Overly dark imagery"]
    }
}

# Generic domain list to ignore during domain-based matching
GENERIC_DOMAINS = {
    'gmail.com', 'yahoo.com', 'outlook.com', 'mail.ru', 'hotmail.com',
    'facebook.com', 'instagram.com', 'sbb.rs', 'eunet.rs', 'nadlanu.com',
    'mts.rs', 'open.telekom.rs', 'yandex.com', 'mail.com', 'icloud.com'
}

def normalize_company_name(name):
    """
    Phase 1: Normalize company name by lowercasing, removing punctuation,
    Serbian legal suffixes, duplicate spaces, and special symbols.
    """
    if not name or not isinstance(name, str):
        return ""
    # Lowercase
    n = name.lower()
    # Strip common Serbian legal suffixes
    for pattern in SERBIAN_LEGAL_SUFFIXES:
        n = re.sub(pattern, ' ', n)
    # Remove punctuation & special symbols
    n = re.sub(r'[^\w\s]', ' ', n)
    # Remove duplicate spaces and strip
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def extract_clean_domain(url):
    """
    Helper to extract clean domain from website URLs or email addresses.
    Excludes generic domains.
    """
    if not url or not isinstance(url, str):
        return ""
    val = url.lower().strip()
    if "@" in val:
        val = val.split("@")[-1]
    # Remove http://, https://, www.
    val = re.sub(r'^(https?://)?(www\.)?', '', val)
    # Take only primary domain path
    val = val.split("/")[0]
    if val in GENERIC_DOMAINS:
        return ""
    return val

def clean_phone_number(phone):
    """
    Format phone number to standardized tel: format without changing the numeric value.
    """
    if not phone:
        return ""
    # Standardize spaces and keep digits/plus sign
    cleaned = re.sub(r'[^\d\+]', '', str(phone))
    if cleaned.startswith("0") and not cleaned.startswith("00"):
        # Local Serbian formatting fallback to prefix +381
        cleaned = "+381" + cleaned[1:]
    return cleaned

def match_company(biz_a, df_b, df_c):
    """
    Phase 2: Company Matching Logic.
    Returns (matched_row_b_dict, matched_row_c_dict, match_confidence, match_status)
    """
    place_id = biz_a.get("business_id", "")
    domain_a = extract_clean_domain(biz_a.get("website", ""))
    norm_name_a = normalize_company_name(biz_a.get("business_name", ""))
    address_a = biz_a.get("address", "")
    
    best_b = None
    best_c = None
    confidence_b = 0.0
    confidence_c = 0.0
    
    # Matching against Dataset B (Emails)
    if not df_b.empty:
        for _, row in df_b.iterrows():
            row_dict = dict(row)
            row_domain = extract_clean_domain(row_dict.get("domain", "")) or extract_clean_domain(row_dict.get("email", ""))
            row_norm_name = normalize_company_name(row_dict.get("company_name", ""))
            
            # Check 1: Domain Match
            if domain_a and row_domain and domain_a == row_domain:
                best_b = row_dict
                confidence_b = 0.95
                break
            
            # Check 2: Exact Name Match
            if norm_name_a and row_norm_name and norm_name_a == row_norm_name:
                best_b = row_dict
                confidence_b = 0.90
                # Keep checking in case a better domain match exists
                
            # Check 3: Fuzzy Name Match
            if norm_name_a and row_norm_name:
                ratio = difflib.SequenceMatcher(None, norm_name_a, row_norm_name).ratio()
                if ratio > 0.85 and (0.70 + (ratio - 0.85) * 2) > confidence_b:
                    best_b = row_dict
                    confidence_b = round(0.70 + (ratio - 0.85) * 2, 2)
                    
    # Matching against Dataset C (Research)
    if not df_c.empty:
        for _, row in df_c.iterrows():
            row_dict = dict(row)
            row_norm_name = normalize_company_name(row_dict.get("company_name", ""))
            row_phone = clean_phone_number(row_dict.get("phone", ""))
            phone_a = clean_phone_number(biz_a.get("phone", ""))
            row_email = row_dict.get("email", "")
            email_a = biz_a.get("email", "")
            row_address = row_dict.get("address", "")
            
            # Check 1: Phone Match
            if phone_a and row_phone and phone_a == row_phone:
                best_c = row_dict
                confidence_c = 0.95
                break
                
            # Check 2: Email Match
            if email_a and row_email and email_a.lower() == row_email.lower():
                best_c = row_dict
                confidence_c = 0.95
                break
            
            # Check 3: Exact Name Match
            if norm_name_a and row_norm_name and norm_name_a == row_norm_name:
                best_c = row_dict
                confidence_c = 0.90
                
            # Check 4: Fuzzy Name Match
            if norm_name_a and row_norm_name:
                ratio = difflib.SequenceMatcher(None, norm_name_a, row_norm_name).ratio()
                if ratio > 0.85 and (0.70 + (ratio - 0.85) * 2) > confidence_c:
                    best_c = row_dict
                    confidence_c = round(0.70 + (ratio - 0.85) * 2, 2)
            
            # Check 5: Address Similarity
            if address_a and row_address:
                addr_ratio = difflib.SequenceMatcher(None, address_a.lower(), row_address.lower()).ratio()
                if addr_ratio > 0.80 and norm_name_a and row_norm_name:
                    name_ratio = difflib.SequenceMatcher(None, norm_name_a, row_norm_name).ratio()
                    if name_ratio > 0.60:
                        calc_conf = round(0.60 + (addr_ratio - 0.80) + (name_ratio - 0.60), 2)
                        calc_conf = min(0.85, calc_conf)
                        if calc_conf > confidence_c:
                            best_c = row_dict
                            confidence_c = calc_conf

    # Resolve final match status and confidence
    final_confidence = max(confidence_b, confidence_c)
    if final_confidence == 0.0:
        # If absolutely no match found, this is an unmatched entity
        status = "unmatched"
    elif final_confidence >= 0.85:
        status = "matched"
    else:
        status = "review_required"
        
    return best_b, best_c, final_confidence, status

def resolve_single_source_of_truth(biz_a, matched_b, matched_c):
    """
    Phase 3: Resolve conflicts using strict priority logic:
    Research CSV (C) > Email Discovery (B) > Parser DB (A).
    """
    merged = {}
    
    # Priority resolution helper
    def get_value(field_key, default_val=None):
        if matched_c and matched_c.get(field_key) and not pd.isna(matched_c.get(field_key)):
            return matched_c.get(field_key)
        if matched_b and matched_b.get(field_key) and not pd.isna(matched_b.get(field_key)):
            return matched_b.get(field_key)
        if biz_a and biz_a.get(field_key) and not pd.isna(biz_a.get(field_key)):
            return biz_a.get(field_key)
        return default_val

    # Mapping distinct field layouts to SSoT
    merged["company_id"] = biz_a.get("business_id", "")
    
    # Resolve company name
    name_c = matched_c.get("company_name") if matched_c else None
    name_b = matched_b.get("company_name") if matched_b else None
    name_a = biz_a.get("business_name")
    merged["company_name"] = name_c or name_b or name_a or ""
    
    # Resolve email
    email_c = matched_c.get("email") if matched_c else None
    email_b = matched_b.get("email") if matched_b else None
    email_a = biz_a.get("email")
    merged["email"] = email_c or email_b or email_a or ""
    
    # Resolve phone
    phone_c = matched_c.get("phone") if matched_c else None
    phone_a = biz_a.get("phone")
    merged["phone"] = phone_c or phone_a or ""
    
    # Resolve address
    addr_c = matched_c.get("address") if matched_c else None
    addr_a = biz_a.get("address")
    merged["address"] = addr_c or addr_a or ""
    
    # Resolve domain
    domain_c = extract_clean_domain(matched_c.get("domain", "")) if matched_c else ""
    domain_b = matched_b.get("domain") if matched_b else None
    web_a = biz_a.get("website")
    merged["domain"] = domain_c or domain_b or extract_clean_domain(web_a) or ""
    
    # Gather other inputs needed for review and strategy processing
    merged["reviews_text"] = matched_c.get("reviews") if matched_c and not pd.isna(matched_c.get("reviews")) else biz_a.get("reviews_text", "")
    merged["review_summaries"] = matched_c.get("review summaries") if matched_c else ""
    merged["extracted_services"] = matched_c.get("extracted services") if matched_c else ""
    merged["business_notes"] = matched_c.get("business notes") if matched_c else ""
    merged["category_hints"] = matched_c.get("category hints") if matched_c else ""
    
    merged["rating"] = biz_a.get("rating", 0.0)
    merged["review_count"] = biz_a.get("review_count", 0)
    merged["description"] = biz_a.get("description", "")
    merged["google_category"] = biz_a.get("category", "")
    merged["types_raw"] = biz_a.get("types_raw", "")
    
    return merged

def detect_normalized_category(merged):
    """
    Phase 4: Determine actual business type/category.
    """
    # 1. Check Research CSV category hints
    if merged.get("category_hints") and not pd.isna(merged["category_hints"]):
        return str(merged["category_hints"]).strip().title()
        
    # 2. Derive from SQLite Google categories
    g_cat = merged.get("google_category") or ""
    types = merged.get("types_raw") or ""
    
    if g_cat:
        # Map specific Google categories to clean ones
        g_cat_lower = g_cat.lower()
        if "dentist" in g_cat_lower or "dental" in g_cat_lower:
            return "Dental Clinic"
        if "beauty" in g_cat_lower or "hair" in g_cat_lower or "nail" in g_cat_lower:
            return "Beauty Salon"
        if "law" in g_cat_lower or "legal" in g_cat_lower or "attorney" in g_cat_lower:
            return "Legal Services"
        if "locksmith" in g_cat_lower or "ključ" in g_cat_lower:
            return "Locksmith Service"
        if "plumb" in g_cat_lower or "vodoinstalater" in g_cat_lower:
            return "Plumbing Service"
        if "electric" in g_cat_lower or "struja" in g_cat_lower:
            return "Electrical Services"
        if "restaurant" in g_cat_lower or "pizz" in g_cat_lower or "picerija" in g_cat_lower:
            return "Restaurant"
        if "car repair" in g_cat_lower or "auto" in g_cat_lower or "mehanik" in g_cat_lower:
            return "Auto Mechanic Shop"
        if "vulkanizer" in g_cat_lower or "tire" in g_cat_lower:
            return "Tire Service Shop"
        if "gym" in g_cat_lower or "fitness" in g_cat_lower:
            return "Fitness Center"
        return g_cat.strip().title()
        
    # 3. Check for type matching
    if types:
        types_lower = types.lower()
        if "dentist" in types_lower:
            return "Dental Clinic"
        if "beauty_salon" in types_lower or "hair_care" in types_lower:
            return "Beauty Salon"
        if "lawyer" in types_lower:
            return "Legal Services"
        if "locksmith" in types_lower:
            return "Locksmith Service"
        if "plumber" in types_lower:
            return "Plumbing Service"
        if "electrician" in types_lower:
            return "Electrical Services"
        if "restaurant" in types_lower:
            return "Restaurant"
        if "car_repair" in types_lower:
            return "Auto Mechanic Shop"
            
    # Default fallback
    return "Local Business"

def assign_archetype(category_name, merged):
    """
    Phase 5: Map normalized category or keywords to one of the ten archetypes.
    """
    cat_lower = category_name.lower()
    name_lower = (merged.get("company_name") or "").lower()
    
    # 1. emergency_service
    if any(k in cat_lower or k in name_lower for k in ["locksmith", "ključ", "kljuc", "towing", "šlep", "slep", "hitne intervencije", "hitna sluzba"]):
        return "emergency_service"
        
    # 2. beauty
    if any(k in cat_lower or k in name_lower for k in ["beauty", "salon", "hair", "nail", "nokt", "frizerski", "kozmeticki", "spa", "masaza", "massage", "negatela", "salon lepote"]):
        return "beauty"
        
    # 3. healthcare
    if any(k in cat_lower or k in name_lower for k in ["dentist", "stomatolog", "zub", "dental", "pedijatar", "ordinacija", "dr", "lekar", "medic", "ginekolog", "vet", "ambulanta", "lab", "biotest", "zdravstvena nega", "psiholog", "terapija"]):
        return "healthcare"
        
    # 4. food
    if any(k in cat_lower or k in name_lower for k in ["restoran", "pizz", "picerija", "caffe", "bar", "pub", "kafe", "food", "rostilj", "roštilj", "pekara", "krosti", "steak", "bistro", "kuhinja", "grill", "poslast", "sladoled", "fast food", "hrana", "kafana", "konoba"]):
        return "food"
        
    # 5. professional_services
    if any(k in cat_lower or k in name_lower for k in ["advokat", "lawyer", "kancelarija", "knjigovod", "agencija", "nekretnine", "notar", "prevod", "legal", "konsult"]):
        return "professional_services"
        
    # 6. home_improvement
    if any(k in cat_lower or k in name_lower for k in ["vodoinstalater", "plumb", "električar", "elektricar", "moler", "keramicar", "gips", "adaptacij", "klima", "air condition", "grejanje", "ciscenje", "selidbe", "krov", "stolarija", "bravar", "hitna služba", "fasada", "izolacija", "gradjevinski"]):
        return "home_improvement"
        
    # 7. automotive
    if any(k in cat_lower or k in name_lower for k in ["vulkanizer", "gume", "tire", "car repair", "auto", "mehanic", "servis", "taxi", "tehnicki pregled", "rent a car", "autoperionica", "pranje", "otkup automobila"]):
        return "automotive"
        
    # 8. fitness
    if any(k in cat_lower or k in name_lower for k in ["gym", "fitness", "teretana", "yoga", "trening"]):
        return "fitness"
        
    # 9. retail
    if any(k in cat_lower or k in name_lower for k in ["pet shop", "apoteka", "butik", "prodavnica", "market", "cvece", "cvećara", "shopp"]):
        return "retail"
        
    return "general_local_business"

def analyze_reviews(merged):
    """
    Phase 6: Analyze reviews strictly matching text evidence without inventing anything.
    """
    reviews = merged.get("reviews_text") or ""
    summaries = merged.get("review_summaries") or ""
    extracted_services = merged.get("extracted_services") or ""
    
    # Prepare defaults
    services_list = []
    compliments_list = []
    customer_language = []
    differentiators = []
    trust_signals = []
    strengths = []
    
    # 1. Parse services from extracted services field (Dataset C) if present
    if extracted_services and not pd.isna(extracted_services):
        services_list = [s.strip() for s in str(extracted_services).split(",") if s.strip()]
        
    # 2. Parse reviews from DB or Research CSV
    review_lines = []
    if reviews and not pd.isna(reviews):
        # Split reviews text by double newline or square brackets (which indicates review formats)
        review_lines = [r.strip() for r in re.split(r'\n\n|\[\d\*', str(reviews)) if r.strip()]
        
    # Standard keyword dictionaries to extract evidence from reviews
    praise_keywords = {
        "profesionalan": "Professional service",
        "ljubazn": "Polite and helpful staff",
        "brz": "Fast execution/response time",
        "povolj": "Reasonable pricing",
        "cist": "Clean and organized environment",
        "odlican": "Excellent overall experience",
        "odličan": "Excellent overall experience",
        "super": "Highly satisfying visit",
        "preporuk": "Highly recommended by customers",
        "najbolj": "Praised as the best in class"
    }
    
    found_praises = set()
    evidence_sentences = []
    
    for r in review_lines:
        # Simple sentence extraction
        sentences = re.split(r'[\.\!\?]', r)
        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            # Search for praise words
            s_lower = s_clean.lower()
            for kw, val in praise_keywords.items():
                if kw in s_lower:
                    found_praises.add(val)
                    if len(evidence_sentences) < 5:
                        evidence_sentences.append(s_clean)
                    break
                    
    # Compile parsed outputs
    compliments_list = list(found_praises)
    customer_language = [s for s in evidence_sentences if len(s) < 80]
    
    # Extract strengths
    if merged.get("rating"):
        trust_signals.append(f"High customer rating of {merged['rating']}/5.0")
    if merged.get("review_count"):
        trust_signals.append(f"Supported by a total of {merged['review_count']} reviews")
    if compliments_list:
        strengths.extend(compliments_list[:3])
        
    # Add differentiators if mentioned
    if "brz" in str(reviews).lower():
        differentiators.append("Fast turnaround and service efficiency")
    if "povolj" in str(reviews).lower():
        differentiators.append("Competitive and fair pricing structure")
        
    # If no reviews exist, fill in strictly neutral non-invented data
    if not review_lines:
        compliments_list = ["No specific client feedback was found in raw reviews"]
        customer_language = ["Customer reviews text is empty"]
        strengths = ["A waiting customer feedback verification"]
        trust_signals.append("Local business listed on Google Maps")
        
    # Gather services from category names if services list is empty
    if not services_list:
        services_list = [merged.get("google_category") or "General services"]
        
    return {
        "services": services_list,
        "compliments": compliments_list,
        "customer_language": customer_language,
        "differentiators": differentiators,
        "trust_signals": trust_signals,
        "strengths": strengths,
        "review_summary": str(summaries) if summaries and not pd.isna(summaries) else "Local business with stable customer ratings and reviews."
    }

def generate_website_strategy(archetype, merged, analysis):
    """
    Phase 7 to 10: Strategy, Sections, SEO, and Image Direction.
    """
    cfg = ARCHETYPE_CONFIG.get(archetype, ARCHETYPE_CONFIG["general_local_business"])
    
    # 1. Website details
    style = cfg["style"]
    goal = cfg["goal"]
    tone = cfg["tone"]
    sections = cfg["sections"]
    cta_label = cfg["cta_label"]
    
    # Adjust sections based on contact features
    has_phone = bool(merged.get("phone"))
    has_email = bool(merged.get("email"))
    
    # Adjust Emergency Callout section
    if archetype == "emergency_service" and not has_phone:
        # Move callout if no phone is present
        if "Emergency Callout" in sections:
            sections.remove("Emergency Callout")
            
    # Adjust Booking/Lead Form
    if "Booking Form" in sections and not (has_email or has_phone):
        sections.remove("Booking Form")
        sections.append("Contact")
        
    # 2. SEO Keywords
    city = "Novi Sad"
    cat_name = merged.get("google_category") or "Biznis"
    comp_name = merged.get("company_name") or "Biznis"
    
    primary_keywords = [
        f"{cat_name.lower()} {city.lower()}",
        f"{comp_name.lower()} {city.lower()}"
    ]
    secondary_keywords = [
        f"najbolji {cat_name.lower()}",
        "cene usluga",
        "profesionalni tim"
    ]
    location_keywords = [city, "Petrovaradin", "Veternik", "Vojvodina"]
    
    # Add review services to keywords
    if analysis["services"]:
        for s in analysis["services"][:2]:
            secondary_keywords.append(s.lower())
            
    seo_keywords = {
        "primary_keywords": primary_keywords,
        "secondary_keywords": secondary_keywords,
        "location_keywords": location_keywords
    }
    
    # 3. Image Direction
    image_direction = {
        "image_style": cfg["image_style"],
        "image_subjects": cfg["image_subjects"],
        "avoid_images": cfg["avoid_images"]
    }
    
    return {
        "website_style": style,
        "website_goal": goal,
        "website_tone": tone,
        "recommended_sections": sections,
        "cta_label": cta_label,
        "seo_keywords": seo_keywords,
        "image_direction": image_direction
    }

def compile_cta_bindings(merged, strategy):
    """
    Phase 11: Contact Data Injection.
    Generates exact primary/secondary CTA bindings without generating fake info.
    """
    phone = clean_phone_number(merged.get("phone", ""))
    email = merged.get("email", "")
    
    primary_cta = {}
    secondary_cta = {}
    
    if phone:
        primary_cta = {
            "label": strategy["cta_label"],
            "action": "phone",
            "binding": f"tel:{phone}"
        }
        if email:
            secondary_cta = {
                "label": "Email Us",
                "action": "email",
                "binding": f"mailto:{email}"
            }
        else:
            secondary_cta = {
                "label": "Our Location",
                "action": "scroll",
                "binding": "#contact"
            }
    elif email:
        primary_cta = {
            "label": strategy["cta_label"],
            "action": "email",
            "binding": f"mailto:{email}"
        }
        secondary_cta = {
            "label": "Our Location",
            "action": "scroll",
            "binding": "#contact"
        }
    else:
        # Fallback if no contact info exists
        primary_cta = {
            "label": "Contact Us",
            "action": "scroll",
            "binding": "#contact"
        }
        secondary_cta = {
            "label": "View Services",
            "action": "scroll",
            "binding": "#services"
        }
        
    return primary_cta, secondary_cta

def build_website_prompt(merged, category, archetype, analysis, strategy, primary_cta, secondary_cta):
    """
    Phase 12: Website Prompt Generation.
    Compiles a structured company-specific instruction prompt for the website generator.
    """
    prompt = f"""# AI Website Generation Prompt for {merged['company_name']}

You are a senior UX/UI designer and copywriter. Generate a high-converting, responsive website structure for "{merged['company_name']}", located at "{merged['address'] or 'Novi Sad, Serbia'}".

## Business Context
- **Archetype**: {archetype.upper()}
- **Target Category**: {category}
- **Tone**: {strategy['website_tone']}
- **Goal**: {strategy['website_goal']}
- **Style Direction**: {strategy['website_style']}

## Evidence-Based Content Assets (Reviews & Notes)
- **Extracted Services**: {', '.join(analysis['services'])}
- **Proven Strengths**: {', '.join(analysis['strengths'])}
- **Testimonial Signals**: {analysis['review_summary']}
- **Customer Language Phrases**:
{chr(10).join([f'  * "{ph.strip()}"' for ph in analysis['customer_language'][:3]])}

## Strategic SEO Setup
- **Primary Keywords**: {', '.join(strategy['seo_keywords']['primary_keywords'])}
- **Secondary Keywords**: {', '.join(strategy['seo_keywords']['secondary_keywords'])}
- **Location Constraints**: {', '.join(strategy['seo_keywords']['location_keywords'])}

## Recommended Layout Sections
{chr(10).join([f"{i+1}. {section}" for i, section in enumerate(strategy['recommended_sections'])])}

## Call-To-Action Binding Guidelines
- **Primary CTA**: "{primary_cta.get('label')}" binding to `{primary_cta.get('binding')}`
- **Secondary CTA**: "{secondary_cta.get('label')}" binding to `{secondary_cta.get('binding')}`

## Visual Guidelines
- **Image Aesthetic**: {strategy['image_direction']['image_style']}
- **Target Subjects**: {', '.join(strategy['image_direction']['image_subjects'])}
- **Avoid Images**: {', '.join(strategy['image_direction']['avoid_images'])}

---
*Note: Do not write code or HTML. Synthesize the text above into structural copy guidelines and clean layout blueprints for the site builder.*
"""
    return prompt.strip()

def process_pipeline(db_path, emails_path, research_path, output_path):
    print(f"Starting pipeline...")
    print(f"  Database path: {db_path}")
    print(f"  Emails path: {emails_path}")
    print(f"  Research path: {research_path}")
    print(f"  Output path: {output_path}")
    
    # Load input DataFrames
    df_b = load_csv_data(emails_path)
    df_c = load_csv_data(research_path)
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        sys.exit(1)
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Fetch all records from Dataset A
    try:
        cursor.execute("SELECT * FROM businesses")
        businesses_a = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error reading businesses table: {e}")
        conn.close()
        sys.exit(1)
        
    conn.close()
    
    print(f"Loaded {len(businesses_a)} businesses from Database.")
    print(f"Loaded {len(df_b)} email rows from {emails_path if emails_path else 'None'}.")
    print(f"Loaded {len(df_c)} research rows from {research_path if research_path else 'None'}.")
    
    unified_records = []
    match_counts = {"matched": 0, "review_required": 0, "unmatched": 0}
    
    for biz in businesses_a:
        # 1. Matching
        matched_b, matched_c, confidence, status = match_company(biz, df_b, df_c)
        match_counts[status] += 1
        
        # 2. Resolve SSoT
        merged = resolve_single_source_of_truth(biz, matched_b, matched_c)
        
        # 3. Category Detection
        category = detect_normalized_category(merged)
        
        # 4. Archetype Assignment
        archetype = assign_archetype(category, merged)
        
        # 5. Review Analysis
        analysis = analyze_reviews(merged)
        
        # 6. Strategy & Layout Generation
        strategy = generate_website_strategy(archetype, merged, analysis)
        
        # 7. CTA Bindings
        primary_cta, secondary_cta = compile_cta_bindings(merged, strategy)
        
        # 8. Compile Prompt
        prompt = build_website_prompt(merged, category, archetype, analysis, strategy, primary_cta, secondary_cta)
        
        # 9. Format JSON Profile
        profile = {
            "company_id": merged["company_id"],
            "company_name": merged["company_name"],
            "email": merged["email"],
            "phone": clean_phone_number(merged["phone"]),
            "address": merged["address"],
            "domain": merged["domain"],
            "category": category,
            "archetype": archetype,
            "website_style": strategy["website_style"],
            "website_goal": strategy["website_goal"],
            "website_tone": strategy["website_tone"],
            "primary_cta": primary_cta,
            "secondary_cta": secondary_cta,
            "recommended_sections": strategy["recommended_sections"],
            "services": analysis["services"],
            "usp": analysis["differentiators"] or analysis["strengths"][:2] or ["Local Quality Provider"],
            "review_summary": analysis["review_summary"],
            "seo_keywords": strategy["seo_keywords"],
            "image_direction": strategy["image_direction"],
            "website_prompt": prompt,
            "match_confidence": float(confidence),
            "match_status": status
        }
        
        unified_records.append(profile)
        
    # Write unified outputs to JSON
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(unified_records, f, ensure_ascii=False, indent=2)
        
    print(f"\nPipeline execution finished successfully.")
    print(f"  Total unified records: {len(unified_records)}")
    print(f"  Matching summary: Matched={match_counts['matched']}, Review Required={match_counts['review_required']}, Unmatched={match_counts['unmatched']}")
    print(f"  Output written to: {output_path}")

def load_csv_data(path):
    if not path or not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as e:
        print(f"  Warning: could not read CSV at {path}: {e}")
        return pd.DataFrame()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrichment & Prompt Generation Pipeline")
    parser.add_argument("--db", default="database/businesses.sqlite", help="Path to SQLite database")
    parser.add_argument("--emails", default="", help="Path to Email Discovery CSV (Dataset B)")
    parser.add_argument("--research", default="", help="Path to Research CSV (Dataset C)")
    parser.add_argument("--output", default="output/unified_companies.json", help="Path to output unified JSON file")
    
    args = parser.parse_args()
    
    process_pipeline(args.db, args.emails, args.research, args.output)
