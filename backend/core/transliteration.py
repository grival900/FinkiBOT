"""Best-effort Latin -> Cyrillic transliteration for Macedonian ("latinica").

Students often type search queries in Latin script — no Cyrillic keyboard handy, e.g.
"bazi na podatoci" instead of "бази на податоци" — but the indexed content here is
essentially all Cyrillic, so an untransliterated Latin query embeds nothing close to
a semantic match. This isn't meant to be linguistically perfect (Macedonian latinica
digraphs are used inconsistently in the wild); it's specifically a search-recall aid.

`core/retrieval.py` uses this as an *extra* query variant alongside the original,
never a replacement — so genuine Latin-script terms (course names like "SQL", "Java")
still match normally through the unmodified original query.
"""

import re

# Longest patterns first so digraphs match before their component single letters
# fall through to the single-letter table below.
_DIGRAPHS = [
    ("nj", "њ"),
    ("lj", "љ"),
    ("gj", "ѓ"),
    ("kj", "ќ"),
    ("dz", "ѕ"),
    ("dj", "џ"),
    ("zh", "ж"),
    ("ch", "ч"),
    ("sh", "ш"),
]
_SINGLE = {
    "a": "а",
    "b": "б",
    "v": "в",
    "g": "г",
    "d": "д",
    "e": "е",
    "z": "з",
    "i": "и",
    "j": "ј",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "f": "ф",
    "h": "х",
    "c": "ц",
}
_MAP: dict[str, str] = dict(_DIGRAPHS) | _SINGLE
# Letters with no Macedonian equivalent (q, w, x, y) fall through unmapped via the
# `[a-z]` fallback + dict .get default, rather than being guessed at and possibly
# corrupting a genuine English/technical term mixed into the query.
_PATTERN = re.compile("|".join(re.escape(p) for p, _ in _DIGRAPHS) + "|[a-z]")

_CYRILLIC_RE = re.compile("[Ѐ-ӿ]")
_LATIN_RE = re.compile(r"[a-zA-Z]")


def transliterate_latin_to_cyrillic(text: str) -> str:
    return _PATTERN.sub(lambda m: _MAP.get(m.group(0), m.group(0)), text.lower())


def is_latin_only(text: str) -> bool:
    """True when `text` has Latin letters and no Cyrillic at all — the case where a
    literal (untransliterated) search would never semantically match this project's
    near-entirely-Cyrillic indexed content."""
    return bool(_LATIN_RE.search(text)) and not _CYRILLIC_RE.search(text)
