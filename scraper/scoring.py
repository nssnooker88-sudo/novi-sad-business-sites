"""
Lead scoring engine. Pure functions, no I/O — easy to test and tweak.

Produces:
  is_active                  bool
  business_quality_score     0-100
  website_need_score         0-100
  purchase_probability_score 0-100
  lead_status                NO_WEBSITE | HAS_WEBSITE | INACTIVE | HIGH_PRIORITY
"""

import math
from datetime import datetime, timezone

# --- Website-need by category -------------------------------------------------
# Keyword -> base need score. Matched as substrings against category + types.
_NEED_KEYWORDS = {
    # High need (service businesses people search for before calling)
    "dentist": 90, "doctor": 85, "dermatolog": 88, "physiother": 85,
    "lawyer": 90, "notary": 85, "accountant": 85, "tax": 85, "bookkeep": 80,
    "plumber": 88, "electrician": 88, "locksmith": 90, "hvac": 88,
    "contractor": 85, "construction": 82, "architect": 85, "interior": 83,
    "auto repair": 85, "tire": 80, "car dealer": 82, "car rental": 85,
    "real estate": 90, "insurance": 85, "travel agency": 88,
    "veterinar": 85, "physician": 85, "clinic": 85, "laborator": 82,
    "moving": 85, "courier": 80, "photograph": 85, "videograph": 85,
    "wedding": 88, "catering": 85, "event": 82, "tattoo": 80,
    "web design": 70, "marketing": 78, "advertising": 78, "it services": 80,
    "driving school": 85, "language school": 82, "tutoring": 80,
    "hotel": 88, "hostel": 85, "apartment": 85, "spa": 80,
    # Medium need
    "restaurant": 60, "pizzeria": 60, "bakery": 55, "cafe": 50, "bar": 50,
    "gym": 65, "fitness": 65, "yoga": 62, "pilates": 62, "salon": 60,
    "barber": 55, "beauty": 60, "nail": 55, "florist": 60, "jewelry": 65,
    "clothing": 60, "shoe": 55, "furniture": 62, "optician": 70,
    "pharmacy": 60, "pet": 60, "vet": 80, "catering ": 80, "confection": 55,
    # Low need (walk-in / commodity)
    "fast food": 35, "kiosk": 15, "grocery": 35, "butcher": 35,
    "fish market": 35, "convenience": 25, "tobacco": 15,
}
_DEFAULT_NEED = 55


def _now():
    return datetime.now(timezone.utc)


def _parse_dt(value):
    """Parse an RFC3339 timestamp string into aware datetime, or None."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def is_active(business_status, latest_review_date, review_count, inactive_after_months=24):
    """A business is inactive if closed, never reviewed, or stale."""
    if business_status and business_status.upper() in (
        "CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"
    ):
        return False
    if not review_count or review_count <= 0:
        return False
    dt = _parse_dt(latest_review_date)
    if dt is not None:
        months_old = (_now() - dt).days / 30.44
        if months_old > inactive_after_months:
            return False
    return True


def business_quality_score(business):
    """0-100 composite of reviews, rating, completeness, phone, recency."""
    rc = business.get("review_count") or 0
    rating = business.get("rating") or 0.0
    phone = business.get("phone")
    addr = business.get("address")
    hours = business.get("opening_hours")
    desc = business.get("description")
    photos = business.get("photo_count") or 0

    # Review volume — log-scaled so 200+ reviews ~ full marks.
    review_pts = min(1.0, math.log10(rc + 1) / math.log10(200)) * 30

    # Rating — only meaningful with some reviews.
    rating_pts = (rating / 5.0) * 25 if rc > 0 else 0

    # Profile completeness.
    completeness = 0
    completeness += 6 if phone else 0
    completeness += 4 if addr else 0
    completeness += 5 if hours else 0
    completeness += 3 if desc else 0
    completeness += min(7, photos)  # up to 7 pts for photos

    # Recent activity.
    dt = _parse_dt(business.get("latest_review_date"))
    recency_pts = 0
    if dt is not None:
        months_old = (_now() - dt).days / 30.44
        if months_old <= 3:
            recency_pts = 15
        elif months_old <= 12:
            recency_pts = 10
        elif months_old <= 24:
            recency_pts = 5

    return round(min(100, review_pts + rating_pts + completeness + recency_pts))


def website_need_score(business):
    """0-100 estimate of how much this category benefits from a website."""
    haystack = " ".join(filter(None, [
        (business.get("category") or "").lower(),
        (business.get("subcategory") or "").lower(),
        (business.get("types_raw") or "").lower(),
    ]))
    best = None
    for kw, score in _NEED_KEYWORDS.items():
        if kw.strip() in haystack:
            best = score if best is None else max(best, score)
    base = best if best is not None else _DEFAULT_NEED

    # A busy, well-reviewed business gets a bit more value from a site.
    rc = business.get("review_count") or 0
    if rc >= 50:
        base += 5
    return round(min(100, base))


def purchase_probability_score(business, quality, need):
    """0-100 likelihood the owner buys a low-cost website."""
    score = 0
    # Biggest driver: they don't already have a site.
    score += 45 if not business.get("has_website") else 0
    # Real business with traction is reachable and has budget.
    score += quality * 0.25            # up to 25
    score += need * 0.20               # up to 20
    # Contactable.
    score += 10 if business.get("phone") else 0
    # Some recent activity signals an owner who cares.
    if (business.get("review_count") or 0) >= 5:
        score += 5
    # Already has a website -> low probability of buying another.
    if business.get("has_website"):
        score = min(score, 25)
    return round(max(0, min(100, score)))


def classify(business, need, purchase, active, hp_cfg):
    if not active:
        return "INACTIVE"
    if business.get("has_website"):
        return "HAS_WEBSITE"
    if (need > hp_cfg["min_website_need_score"]
            and purchase > hp_cfg["min_purchase_probability_score"]):
        return "HIGH_PRIORITY"
    return "NO_WEBSITE"


def score_business(business, inactive_after_months, hp_cfg):
    """Attach all scores to a business dict (mutates and returns it)."""
    active = is_active(
        business.get("business_status"),
        business.get("latest_review_date"),
        business.get("review_count"),
        inactive_after_months,
    )
    quality = business_quality_score(business)
    need = website_need_score(business)
    purchase = purchase_probability_score(business, quality, need)
    business["is_active"] = active
    business["business_quality_score"] = quality
    business["website_need_score"] = need
    business["purchase_probability_score"] = purchase
    business["lead_status"] = classify(business, need, purchase, active, hp_cfg)
    return business
