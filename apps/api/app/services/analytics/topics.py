"""
Lightweight topic extraction from titles / captions.

No ML dependency: lower-case, strip emoji/punctuation, drop stop-words,
keep unigrams + bigrams. Bigrams that appear in >= 2 posts are preferred
over their component unigrams so "desk setup" beats "desk" and "setup".
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for", "with", "at", "by",
    "from", "as", "is", "are", "was", "were", "be", "been", "it", "its", "this", "that",
    "these", "those", "i", "im", "ive", "my", "me", "we", "our", "you", "your", "they",
    "their", "he", "she", "his", "her", "them", "us", "do", "does", "did", "done", "how",
    "what", "why", "when", "where", "who", "which", "than", "then", "so", "if", "not", "no",
    "yes", "up", "down", "out", "over", "under", "into", "about", "every", "all", "any",
    "just", "now", "new", "one", "two", "three", "five", "ten", "top", "vs", "via", "per",
    "get", "got", "go", "going", "make", "made", "need", "needs", "know", "still", "ever",
    "never", "more", "most", "less", "very", "really", "only", "also", "too", "can", "could",
    "should", "would", "will", "have", "has", "had", "here", "there", "here's", "heres",
    "day", "days", "hour", "hours", "minute", "minutes", "second", "seconds", "year", "years",
    "week", "month", "pov", "short", "shorts", "reel", "reels", "carousel", "video", "videos",
    "post", "part", "ep", "episode", "ft", "feat", "official", "full", "everything", "else",
    "things", "thing", "nobody", "anyone", "everyone", "someone", "who's", "who dis", "dis",
    "though", "like", "s", "t", "don", "didn", "ll", "re", "ve", "d", "m",
}

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'&+-]*")
_APOSTROPHE_SUFFIX = re.compile(r"'(s|ve|re|ll|d|m|t)$")
_MIN_LEN = 3

_KEEP_S = {"news", "lens", "series", "glass", "focus", "bonus", "plus", "canvas", "atlas", "bias", "chaos", "mess", "boss", "class"}


def stem(token: str) -> str:
    """Very small suffix stripper: editing/edited/edits -> edit, cameras -> camera, settings -> set."""
    t = token
    # plural first so "settings" and "setting" meet at the same stem
    if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")) and t not in _KEEP_S:
        t = t[:-1]
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 4 and t.endswith("ied"):
        t = t[:-3] + "y"
    elif len(t) > 5 and t.endswith("ing"):
        t = t[:-3]
        if len(t) > 3 and t[-1] == t[-2]:      # setting -> sett -> set
            t = t[:-1]
    elif len(t) > 4 and t.endswith("ed"):
        t = t[:-2]
        if len(t) > 3 and t[-1] == t[-2]:
            t = t[:-1]
    return t


def tokenize(text: str, surface: Optional[Counter] = None) -> List[str]:
    """Stemmed tokens. If *surface* is given, (stem, raw) occurrences are counted into it."""
    text = text.lower().replace("—", " ").replace("–", " ").replace("/", " ")
    tokens = []
    for raw in _TOKEN_RE.findall(text):
        raw = _APOSTROPHE_SUFFIX.sub("", raw).strip("'-+")
        if len(raw) < _MIN_LEN or raw.isdigit() or raw in STOPWORDS:
            continue
        st = stem(raw)
        if st in STOPWORDS or len(st) < _MIN_LEN:
            continue
        if surface is not None:
            surface[(st, raw)] += 1
        tokens.append(st)
    return tokens


class TopicLabels:
    """Maps stems back to the most common surface form *within one creator's corpus*."""

    def __init__(self, surface: Optional[Counter] = None):
        self._best: Dict[str, str] = {}
        if surface:
            for (st, raw), n in sorted(surface.items(), key=lambda kv: (kv[1], kv[0][1])):
                self._best[st] = raw  # last write wins → most frequent surface form

    def label(self, term: str) -> str:
        return " ".join(self._best.get(st, st) for st in term.split(" "))


def candidate_terms(text: str, surface: Optional[Counter] = None) -> List[str]:
    """Unigrams + bigrams (adjacent after stop-word removal) for one text."""
    toks = tokenize(text, surface)
    terms = list(dict.fromkeys(toks))  # unique, ordered
    for a, b in zip(toks, toks[1:]):
        terms.append(f"{a} {b}")
    return terms


def extract_topics(titles: Sequence[str], min_docs: int = 2, max_per_doc: int = 5) -> Tuple[List[List[str]], TopicLabels]:
    """
    Assign topics to each title.

    Returns (topics per title, label mapper). A term becomes a topic only if
    it appears in at least *min_docs* titles, which keeps one-off words from
    polluting the pattern analysis.
    """
    surface: Counter = Counter()
    per_doc = [candidate_terms(t, surface) for t in titles]
    df: Counter = Counter()
    for terms in per_doc:
        df.update(set(terms))

    eligible = {term for term, n in df.items() if n >= min_docs}

    result: List[List[str]] = []
    for terms in per_doc:
        chosen: List[str] = []
        # Prefer bigrams first (more specific), then unigrams not already covered by a chosen bigram
        bigrams = [t for t in terms if " " in t and t in eligible]
        bigrams.sort(key=lambda t: (-df[t], t))
        for bg in bigrams:
            if len(chosen) >= max_per_doc:
                break
            chosen.append(bg)
        # Unigrams are kept even when a bigram covers them: "edit" aggregates evidence
        # across "edit tips", "edit session", ... which is what the lift model needs.
        unigrams = [t for t in terms if " " not in t and t in eligible]
        unigrams.sort(key=lambda t: (-df[t], t))
        for ug in unigrams:
            if len(chosen) >= max_per_doc:
                break
            chosen.append(ug)
        result.append(chosen)
    return result, TopicLabels(surface)


def topic_document_frequency(topic_lists: Iterable[Sequence[str]]) -> Dict[str, int]:
    c: Counter = Counter()
    for topics in topic_lists:
        c.update(set(topics))
    return dict(c)
