"""
Category discovery system.

Maintains a queue of search terms. Seeds with a broad category list, then
expands recursively: whenever a discovered business exposes a Google place
type we have not searched yet, we turn that type into a search term and
enqueue it. Processed categories are persisted in SQLite so runs resume.
"""

from collections import deque

# Seed categories (the spec list + a wider net for a Serbian mid-size city).
SEED_CATEGORIES = [
    "restaurant", "cafe", "bakery", "bar", "fast food", "pizzeria",
    "dentist", "doctor", "pediatrician", "dermatologist", "physiotherapist",
    "plumber", "electrician", "locksmith", "hvac contractor", "painter",
    "lawyer", "notary", "accountant", "bookkeeper", "tax advisor",
    "hotel", "hostel", "apartment rental",
    "gym", "fitness center", "yoga studio", "pilates studio", "martial arts",
    "hair salon", "barber shop", "beauty salon", "nail salon", "spa",
    "tattoo studio", "cosmetics",
    "auto repair", "car wash", "tire shop", "car dealer", "car rental",
    "real estate agency", "insurance agency", "travel agency",
    "veterinarian", "pet shop", "pet grooming",
    "pharmacy", "optician", "medical laboratory",
    "contractor", "construction company", "architect", "interior designer",
    "furniture store", "florist", "jewelry store", "clothing store",
    "shoe store", "bookstore", "toy store", "bicycle shop",
    "photographer", "videographer", "printing service", "advertising agency",
    "marketing agency", "web design", "it services",
    "kindergarten", "language school", "driving school", "tutoring",
    "dry cleaner", "tailor", "shoe repair", "moving company", "courier",
    "event venue", "wedding venue", "catering", "nightclub",
    "butcher", "fish market", "grocery store", "wine shop", "confectionery",
]

# Google place types that are too generic / not useful as new search terms.
_IGNORED_TYPES = {
    "point_of_interest", "establishment", "store", "food", "health",
    "place_of_worship", "premise", "geocode", "political", "route",
}


class CategoryQueue:
    """FIFO queue of search terms with dedupe + recursive expansion."""

    def __init__(self, processed=None):
        self._seen = set()
        self._queue = deque()
        # Pre-load categories already processed in a prior run.
        for term in (processed or []):
            self._seen.add(self._norm(term))
        for term in SEED_CATEGORIES:
            self.add(term)

    @staticmethod
    def _norm(term: str) -> str:
        return term.strip().lower().replace("_", " ")

    def add(self, term: str) -> bool:
        """Enqueue a search term if unseen. Returns True if newly added."""
        if not term:
            return False
        key = self._norm(term)
        if key in self._seen:
            return False
        self._seen.add(key)
        self._queue.append(key)
        return True

    def expand_from_types(self, types) -> list:
        """Turn newly seen Google place types into search terms."""
        added = []
        for t in (types or []):
            if not t or t in _IGNORED_TYPES:
                continue
            term = t.replace("_", " ")
            if self.add(term):
                added.append(term)
        return added

    def __bool__(self):
        return bool(self._queue)

    def __len__(self):
        return len(self._queue)

    def pop(self):
        return self._queue.popleft()
