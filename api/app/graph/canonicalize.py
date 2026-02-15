"""Entity name canonicalization and type normalization.

Ensures semantically identical entity names map to the same canonical string,
producing deterministic stable node IDs in the knowledge graph.

Examples:
    "Dog", "dog", "dogs", "dog.", " a dog " → canonical "dog"
"""

from __future__ import annotations

import re
import unicodedata

# ── Controlled entity type enum ──────────────────────────

_CANONICAL_TYPES: dict[str, str] = {
    # Person
    "person":       "Person",
    "people":       "Person",
    "individual":   "Person",
    "user":         "Person",
    "author":       "Person",
    "speaker":      "Person",
    # Org
    "org":          "Org",
    "organization": "Org",
    "organisation": "Org",
    "company":      "Org",
    "institution":  "Org",
    "agency":       "Org",
    "corporation":  "Org",
    "team":         "Org",
    "group":        "Org",
    # Place
    "place":        "Place",
    "location":     "Place",
    "city":         "Place",
    "country":      "Place",
    "region":       "Place",
    "state":        "Place",
    "continent":    "Place",
    "address":      "Place",
    # Project
    "project":      "Project",
    "product":      "Project",
    "app":          "Project",
    "application":  "Project",
    # Topic
    "topic":        "Topic",
    "subject":      "Topic",
    "concept":      "Topic",
    "category":     "Topic",
    "theme":        "Topic",
    # Technology
    "technology":   "Technology",
    "tech":         "Technology",
    "tool":         "Technology",
    "library":      "Technology",
    "framework":    "Technology",
    "language":     "Technology",
    "platform":     "Technology",
    "api":          "Technology",
    "sdk":          "Technology",
    # Component
    "component":    "Component",
    "system":       "Component",
    "service":      "Component",
    "module":       "Component",
    "microservice": "Component",
    # Other — fallback
    "other":        "Other",
}

# Types that are proper-noun-ish — do NOT singularize
_NO_SINGULARIZE_TYPES = {"Person", "Org", "Place", "Project"}

# Leading articles to strip
_LEADING_ARTICLES_RE = re.compile(r"^(a|an|the)\s+", re.IGNORECASE)

# Allowed "internal" punctuation: hyphens and apostrophes
_STRIP_PUNCT_RE = re.compile(r"[^\w\s\-']", re.UNICODE)

# Unicode fancy quotes / apostrophes → ASCII
_UNICODE_APOSTROPHES = str.maketrans({
    "\u2018": "'",   # '
    "\u2019": "'",   # '
    "\u201C": '"',   # "
    "\u201D": '"',   # "
    "\u2032": "'",   # ′
    "\u0060": "'",   # `
})


def normalize_entity_type(raw_type: str) -> str:
    """Map any raw entity type string to a controlled canonical type.

    >>> normalize_entity_type("Organization")
    'Org'
    >>> normalize_entity_type("City")
    'Place'
    >>> normalize_entity_type("xyzzy")
    'Other'
    """
    if not raw_type:
        return "Other"
    key = raw_type.strip().lower()
    return _CANONICAL_TYPES.get(key, "Other")


def canonicalize_entity_name(name: str | None, *, entity_type: str = "Other") -> str:
    """Produce a stable canonical form of an entity name.

    Rules applied in order:
    1. Return "" for None
    2. Strip whitespace
    3. Lowercase
    4. Replace unicode fancy apostrophes with ASCII '
    5. Remove surrounding quotes / brackets
    6. Remove punctuation except internal hyphen / apostrophe
    7. Collapse whitespace to single spaces
    8. Remove leading articles ("a ", "an ", "the ")
    9. Simple singularisation for non-proper-noun types
    10. Final strip

    >>> canonicalize_entity_name("  The Dogs! ", entity_type="Topic")
    'dog'
    >>> canonicalize_entity_name("John's", entity_type="Person")
    "john's"
    >>> canonicalize_entity_name("state-of-the-art", entity_type="Topic")
    'state-of-the-art'
    """
    if name is None:
        return ""

    # 2. strip
    s = name.strip()
    if not s:
        return ""

    # 3. lowercase
    s = s.lower()

    # 4. unicode apostrophes
    s = s.translate(_UNICODE_APOSTROPHES)

    # 5. remove surrounding quotes / brackets
    while len(s) >= 2 and (
        (s[0] == '"' and s[-1] == '"')
        or (s[0] == "'" and s[-1] == "'")
        or (s[0] == "(" and s[-1] == ")")
        or (s[0] == "[" and s[-1] == "]")
        or (s[0] == "{" and s[-1] == "}")
    ):
        s = s[1:-1].strip()

    # 6. remove punctuation except hyphens and apostrophes
    s = _STRIP_PUNCT_RE.sub("", s)

    # 7. collapse whitespace
    s = " ".join(s.split())

    # 8. remove leading articles
    s = _LEADING_ARTICLES_RE.sub("", s)

    # 9. simple singularisation (non-proper-noun types only)
    norm_type = normalize_entity_type(entity_type) if entity_type else "Other"
    if norm_type not in _NO_SINGULARIZE_TYPES:
        if len(s) > 3 and s.endswith("s") and not s.endswith("ss"):
            s = s[:-1]

    # 10. final strip
    return s.strip()


def choose_display_name(original_name: str, canonical_name: str, entity_type: str = "Other") -> str:
    """Pick a clean human-friendly display name.

    - Uses original if it's already clean (stripped equals something sensible).
    - Else title-cases the canonical for Topic/Other/Technology/Component.
    - For Person/Org/Place/Project keeps title-case of original.
    """
    if not original_name or not original_name.strip():
        return canonical_name.title() if canonical_name else ""

    cleaned = " ".join(original_name.strip().split())
    norm_type = normalize_entity_type(entity_type)

    if norm_type in ("Person", "Org", "Place", "Project"):
        return cleaned.title()

    # For Topic/Technology/Component/Other — keep original casing if clean,
    # else title-case canonical
    if cleaned and len(cleaned) >= 2:
        return cleaned
    return canonical_name.title() if canonical_name else cleaned
