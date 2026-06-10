"""
Google Places API (New) async client.

Uses the v1 endpoints with field masks (the post-2025 API). Two calls:
  - places:searchText   -> discover place ids by category (max 60 / query)
  - places/{id}         -> full detail incl. website, phone, up to 5 reviews

Field masks are kept lean to stay in the cheaper SKU tier. Reviews are capped
by Google at 5 per place regardless of max_reviews_per_business.
"""

import asyncio
import logging
import ssl
import certifi

import aiohttp

LOG = logging.getLogger("parser")

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

# Lean masks. Add fields here only if you actually use them downstream — every
# extra field group can bump the request into a pricier SKU tier.
SEARCH_MASK = ",".join(
    [
        "places.id",
        "nextPageToken",
    ]
)
DETAILS_MASK = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "location",
        "primaryType",
        "primaryTypeDisplayName",
        "types",
        "nationalPhoneNumber",
        "internationalPhoneNumber",
        "websiteUri",
        "googleMapsUri",
        "rating",
        "userRatingCount",
        "businessStatus",
        "regularOpeningHours.weekdayDescriptions",
        "editorialSummary",
        "photos",
        "reviews",
    ]
)


class PlacesClient:
    def __init__(
        self,
        api_key,
        language_code="sr",
        region_code="RS",
        concurrency=5,
        request_delay=0.2,
        timeout=30,
    ):
        self.api_key = api_key
        self.language_code = language_code
        self.region_code = region_code
        self.delay = request_delay
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._sem = asyncio.Semaphore(concurrency)
        self._session = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self

    async def __aexit__(self, *exc):
        if self._session:
            await self._session.close()

    async def _post(self, url, body, field_mask):
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }
        for attempt in range(4):
            try:
                async with self._session.post(url, json=body, headers=headers) as r:
                    if r.status == 200:
                        return await r.json()
                    if r.status in (429, 500, 502, 503):
                        wait = 2**attempt
                        LOG.warning("HTTP %s, backing off %ss", r.status, wait)
                        await asyncio.sleep(wait)
                        continue
                    text = await r.text()
                    LOG.error("POST %s -> %s: %s", url, r.status, text[:300])
                    return None
            except aiohttp.ClientError as e:
                LOG.warning("network error %s (attempt %s)", e, attempt + 1)
                await asyncio.sleep(2**attempt)
        return None

    async def _get(self, url, field_mask):
        headers = {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }
        for attempt in range(4):
            try:
                async with self._session.get(url, headers=headers) as r:
                    if r.status == 200:
                        return await r.json()
                    if r.status in (429, 500, 502, 503):
                        await asyncio.sleep(2**attempt)
                        continue
                    text = await r.text()
                    LOG.error("GET %s -> %s: %s", url, r.status, text[:300])
                    return None
            except aiohttp.ClientError as e:
                LOG.warning("network error %s (attempt %s)", e, attempt + 1)
                await asyncio.sleep(2**attempt)
        return None

    async def search_ids(self, query, location_bias, max_pages=3):
        """Return a list of place ids for a category query (max ~60)."""
        ids = []
        page_token = None
        for _ in range(max_pages):
            body = {
                "textQuery": f"{query} {location_bias.get('hint', '')}".strip(),
                "languageCode": self.language_code,
                "regionCode": self.region_code,
                "maxResultCount": 20,
                "locationBias": {
                    "circle": {
                        "center": {
                            "latitude": location_bias["latitude"],
                            "longitude": location_bias["longitude"],
                        },
                        "radius": location_bias["radius_meters"],
                    }
                },
            }
            if page_token:
                body["pageToken"] = page_token
            data = await self._post(SEARCH_URL, body, SEARCH_MASK)
            await asyncio.sleep(self.delay)
            if not data:
                break
            for p in data.get("places", []):
                if p.get("id"):
                    ids.append(p["id"])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
            # Token needs a brief moment before it is valid.
            await asyncio.sleep(1.5)
        return ids

    async def get_details(self, place_id, max_reviews=50):
        """Fetch full detail for one place. Concurrency-limited."""
        async with self._sem:
            url = DETAILS_URL.format(place_id=place_id)
            data = await self._get(url, DETAILS_MASK)
            await asyncio.sleep(self.delay)
        if not data:
            return None
        return _normalize(data, place_id, max_reviews)


def _normalize(d, place_id, max_reviews):
    """Map a raw Places API detail response into our flat business dict."""
    name = (d.get("displayName") or {}).get("text")
    website = d.get("websiteUri")
    phone = d.get("nationalPhoneNumber") or d.get("internationalPhoneNumber")
    loc = d.get("location") or {}
    types = d.get("types") or []
    summary = (d.get("editorialSummary") or {}).get("text")

    reviews = d.get("reviews") or []
    review_texts, latest = [], None
    for rv in reviews[:max_reviews]:
        txt = ((rv.get("text") or {}).get("text") or "").strip()
        author = (rv.get("authorAttribution") or {}).get("displayName", "?")
        rating = rv.get("rating")
        when = rv.get("publishTime")
        if when and (latest is None or when > latest):
            latest = when
        if txt:
            review_texts.append(f"[{rating}* {author}] {txt}")

    hours = (
        "\n".join((d.get("regularOpeningHours") or {}).get("weekdayDescriptions", []))
        or None
    )

    return {
        "business_id": d.get("id") or place_id,
        "google_maps_url": d.get("googleMapsUri"),
        "business_name": name,
        "category": d.get("primaryTypeDisplayName", {}).get("text")
        if isinstance(d.get("primaryTypeDisplayName"), dict)
        else d.get("primaryType"),
        "subcategory": d.get("primaryType"),
        "phone": phone,
        "address": d.get("formattedAddress"),
        "rating": d.get("rating"),
        "review_count": d.get("userRatingCount") or 0,
        "website": website,
        "has_website": bool(website),
        "latest_review_date": latest,
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "description": summary,
        "reviews_text": "\n\n".join(review_texts) or None,
        "photo_count": len(d.get("photos") or []),
        "opening_hours": hours,
        "business_status": d.get("businessStatus"),
        "types_raw": ",".join(types),
    }
