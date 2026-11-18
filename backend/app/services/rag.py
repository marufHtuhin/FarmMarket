"""RAG-lite retrieval for the Krishi Bondhu assistant.

TF-IDF / cosine retrieval over the short markdown notes in docs/knowledge/,
using only scikit-learn (already a project dependency) plus a tiny loader.
The index is built lazily on first use and cached in memory; retrieval is
deterministic (ties break on document title).

`price_context` grounds the assistant in the latest stored PriceRecord rows
whose product name appears in the user's message, so prices are only ever
quoted from the database, never invented.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.orm import Session

from .. import models

DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "docs" / "knowledge"


def knowledge_dir() -> Path:
    override = os.getenv("KNOWLEDGE_DIR", "").strip()
    return Path(override) if override else DEFAULT_KNOWLEDGE_DIR


def _parse_doc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    lines = [ln.rstrip() for ln in text.splitlines()]
    title = path.stem
    body_lines: list[str] = []
    bullets: list[str] = []
    for ln in lines:
        if ln.startswith("# ") and title == path.stem:
            title = ln[2:].strip()
            continue
        if ln.lower().startswith("source:"):
            continue
        if ln.strip():
            body_lines.append(ln)
        if ln.startswith("- "):
            bullets.append(ln[2:].strip())
    body = "\n".join(body_lines)
    snippet = body[:400].strip()
    return {"title": title, "ref": path.name, "body": body,
            "snippet": snippet, "bullets": bullets}


def load_docs(directory: Path | None = None) -> list[dict]:
    """Load every *.md file in the knowledge directory, sorted by filename."""
    d = directory or knowledge_dir()
    if not d.is_dir():
        return []
    return [_parse_doc(p) for p in sorted(d.glob("*.md"))]


# --- Lazy in-memory TF-IDF index -------------------------------------------
_index: dict | None = None


def _get_index() -> dict | None:
    global _index
    if _index is not None:
        return _index
    docs = load_docs()
    if not docs:
        _index = {"docs": [], "matrix": None, "vectorizer": None}
        return _index
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity  # noqa: F401  (import guard)

    # English stop words are excluded: without them, common words ("what",
    # "is", "the") dominated the cosine score, so an unrelated question like
    # "What is the capital of France?" retrieved market-prices-explainer.md
    # at 0.25 — higher than some genuine matches — and the template reply
    # quoted its bullets as if they answered the question. Bangla tokens
    # are unaffected (the stop list is English-only; docs carry Bangla
    # titles such as টমেটো, so Bangla queries still match).
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform([f"{d['title']}\n{d['body']}" for d in docs])
    _index = {"docs": docs, "matrix": matrix, "vectorizer": vectorizer}
    return _index


def reset_index() -> None:
    """Drop the cached index (used by tests that point KNOWLEDGE_DIR elsewhere)."""
    global _index
    _index = None


def retrieve(query: str, top_k: int = 3) -> list[dict]:
    """Return the top_k most relevant docs as {title, ref, snippet, score}.

    Only docs with a cosine similarity above zero are returned, so an
    unrelated question yields an empty list instead of a random note.
    Deterministic: ties break on title.
    """
    query = (query or "").strip()
    if not query or top_k <= 0:
        return []
    idx = _get_index()
    if not idx["docs"] or idx["matrix"] is None:
        return []
    from sklearn.metrics.pairwise import cosine_similarity

    q_vec = idx["vectorizer"].transform([query])
    scores = cosine_similarity(q_vec, idx["matrix"])[0]
    ranked = sorted(
        ((float(scores[i]), idx["docs"][i]) for i in range(len(idx["docs"]))
         if scores[i] > 0),
        key=lambda pair: (-pair[0], pair[1]["title"]),
    )
    return [{"title": d["title"], "ref": d["ref"], "snippet": d["snippet"],
             "bullets": d["bullets"], "score": round(s, 4)}
            for s, d in ranked[:top_k]]


def price_context(db: Session, query: str, limit: int = 5) -> list[dict]:
    """Latest PriceRecord rows whose product name appears in the query.

    Matching is case-insensitive substring matching on the product name, so
    "tomato price" matches a record named "Tomato". Returns [] when no
    product name in the query has any stored price rows.
    """
    query_l = (query or "").lower()
    if not query_l.strip():
        return []
    names = {r[0] for r in db.query(models.PriceRecord.product_name).distinct().all()}
    matched = [n for n in names if n.lower() in query_l]
    if not matched:
        return []
    rows = (db.query(models.PriceRecord)
            .filter(models.PriceRecord.product_name.in_(matched))
            .order_by(models.PriceRecord.recorded_at.desc())
            .limit(limit).all())
    return [{"product_name": r.product_name, "district": r.district,
             "market_name": r.market_name, "price_per_unit": r.price_per_unit,
             "unit": r.unit, "source": r.source,
             "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None}
            for r in rows]
