"""The search index: full text (SQLite FTS5 here, Postgres full text in deploys) plus an offline hashed bag of words vector.

The vector is NOT a language model embedding. It counts word and word pair hashes and compares them by cosine. It stands in for embeddings so the demo runs
with no account. pgvector is not used (see docs/FACTS-AND-SOURCES.md). Results from both lists are merged with reciprocal rank fusion.
"""

from __future__ import annotations

import hashlib
import heapq
import math
from dataclasses import dataclass

from sqlalchemy import bindparam, select, text
from sqlalchemy.orm import Session

from lorefern.models import Chunk
from lorefern.synonyms import expand
from lorefern.textproc import stem, stems

DIM = 1024
_IDF_CACHE: dict = {}
MAX_VECTOR_SCAN = 20_000  # most passages (newest first) one question compares by word vector. Memory stays flat however many there are; beyond this the full text step still finds older ones.
MAX_CANDIDATES = 2_000  # most full text matches one question ranks
BM25_K1, BM25_B = 1.2, 0.75


def hashed_vec(tokens: list[str]) -> dict[str, float]:
    counts: dict[int, float] = {}
    grams = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
    for g in grams:
        h = int(hashlib.md5(g.encode()).hexdigest()[:8], 16) % DIM
        counts[h] = counts.get(h, 0.0) + 1.0
    vec = {k: 1.0 + math.log(v) for k, v in counts.items()}
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {str(k): round(v / norm, 5) for k, v in vec.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


@dataclass
class Hit:
    chunk_id: int
    document_id: int
    fused: float
    bm25: float
    cosine: float
    coverage: float = 0.0


def _is_sqlite(session: Session) -> bool:
    return session.get_bind().dialect.name == "sqlite"


def clear_cache() -> None:
    """Forget the stored word weights. Call it whenever chunk tags change without a rebuild (a retag): the weights are per visible set of tags."""
    _IDF_CACHE.clear()


def rebuild(session: Session) -> int:
    """Rebuild the full text index from the chunk table. Safe to call any time."""
    clear_cache()
    if not _is_sqlite(session):
        return session.scalar(select(text("count(*)")).select_from(Chunk)) or 0
    session.execute(text("DROP TABLE IF EXISTS cx_fts"))
    session.execute(text("CREATE VIRTUAL TABLE cx_fts USING fts5(body, chunk_id UNINDEXED, tokenize='unicode61')"))
    rows = session.execute(select(Chunk.id, Chunk.stems)).all()
    if rows:  # an install with no document yet has an empty index, and an empty batch is not a valid statement
        session.execute(text("INSERT INTO cx_fts(chunk_id, body) VALUES (:i, :b)"), [{"i": i, "b": b} for i, b in rows])
    return len(rows)


def _stats(session: Session, tags: tuple[str, ...]) -> tuple[dict[str, float], float, float]:
    """Word weights and the average passage length, from the chunks this audience may see only, so a restricted page never changes what a person's search does."""
    key = (id(session.get_bind()), tuple(sorted(tags)), session.scalar(select(text("count(*)")).select_from(Chunk)), session.scalar(select(text("coalesce(max(id),0)")).select_from(Chunk)))
    if key in _IDF_CACHE:
        return _IDF_CACHE[key]
    df: dict[str, int] = {}
    n = words = 0
    for (st,) in session.execute(select(Chunk.stems).where(Chunk.tag.in_(tags))):
        n += 1
        parts = st.split()
        words += len(parts)
        for w in set(parts):
            df[w] = df.get(w, 0) + 1
    idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
    res = (idf, math.log(1 + n + 0.5), (words / n) if n else 1.0)
    _IDF_CACHE.clear()
    _IDF_CACHE[key] = res
    return res


def idf_table(session: Session, tags: tuple[str, ...]) -> tuple[dict[str, float], float]:
    """Word weights from the chunks this audience may see only, so a restricted page never changes what a person's search does."""
    idf, max_idf, _ = _stats(session, tags)
    return idf, max_idf


def _bm25(idf: dict[str, float], avgdl: float, terms: list[str], stems_text: str) -> float:
    """Okapi BM25 of one passage, with the word weights and the average length of the passages this person may see (the full text index ranks with the statistics of every passage, restricted ones included)."""
    parts = stems_text.split()
    if not parts:
        return 0.0
    tf: dict[str, int] = {}
    for w in parts:
        tf[w] = tf.get(w, 0) + 1
    norm = BM25_K1 * (1 - BM25_B + BM25_B * len(parts) / max(avgdl, 1.0))
    return sum(idf.get(w, 0.0) * tf[w] * (BM25_K1 + 1) / (tf[w] + norm) for w in terms if w in tf)


def query_terms(session: Session, query: str, tags: tuple[str, ...], top: int = 7, soft: set[str] | frozenset = frozenset()) -> list[tuple[str, float]]:
    """The most telling words of the question, with weights. Words the knowledge base never uses count as telling too (it is what the person asks about)."""
    idf, max_idf = idf_table(session, tags)
    seen: dict[str, float] = {}
    base = stems(query)
    for w in expand(base):
        if len(w) < 3 and not w.isdigit():
            continue
        weight = 2.5 if w.isdigit() else min(idf.get(w, max_idf * 0.35), 3.2) * (1.0 if w in base else 0.6)
        seen[w] = weight * (0.35 if w in soft else 1.0)
    return sorted(seen.items(), key=lambda kv: -kv[1])[:top]


def coverage(session: Session, query: str, chunk_stems: str, tags: tuple[str, ...], soft: set[str] | frozenset = frozenset()) -> float:
    terms = query_terms(session, query, tags, soft=soft)
    if not terms:
        return 0.0
    have = set(chunk_stems.split())
    return sum(w for t, w in terms if t in have) / sum(w for _, w in terms)


def _scan_vectors(session: Session, tags: tuple[str, ...], qvec: dict[str, float], keep: int = 30) -> dict[int, float]:
    """The `keep` passages whose word vector is closest to the question, read in batches so memory does not grow with the index."""
    heap: list[tuple[float, int]] = []
    rows = session.execute(select(Chunk.id, Chunk.vec).where(Chunk.tag.in_(tags)).order_by(Chunk.id.desc()).limit(MAX_VECTOR_SCAN).execution_options(yield_per=500))
    for cid, vec in rows:
        c = cosine(qvec, vec or {})
        if c > 0:
            heapq.heappush(heap, (c, -cid))
            if len(heap) > keep:
                heapq.heappop(heap)
    return {-neg: c for c, neg in heap}


def search(session: Session, query: str, tags: tuple[str, ...], k: int = 6) -> list[Hit]:
    """Search only chunks whose tag is in `tags`. The filter is part of every query, in both the full text and the vector step."""
    if not tags:
        return []
    q = expand(stems(query))
    if not q:
        return []
    qvec = hashed_vec(q)
    bm: dict[int, float] = {}
    if _is_sqlite(session):
        terms = [w for w in dict.fromkeys(q) if w.isalnum()]
        match = " OR ".join(f'"{w}"' for w in terms)
        if match:
            sql = text("SELECT f.chunk_id, c.stems FROM cx_fts f JOIN cx_chunk c ON c.id = f.chunk_id WHERE cx_fts MATCH :m AND c.tag IN :tags ORDER BY c.id LIMIT :cap").bindparams(bindparam("tags", expanding=True))
            args = {"m": match, "tags": list(tags), "cap": MAX_CANDIDATES}
            try:
                rows_ = session.execute(sql, args).all()
            except Exception:  # index missing: build it once and retry
                rebuild(session)
                rows_ = session.execute(sql, args).all()
            idf, _, avgdl = _stats(session, tags)
            scored = sorted(((_bm25(idf, avgdl, terms, st), int(cid)) for cid, st in rows_), key=lambda x: (-x[0], x[1]))[:30]
            bm = {cid: score for score, cid in scored if score > 0}
    else:  # Postgres full text search on the stored stems (ts_rank looks at one passage only, so it needs no statistics of the whole index)
        tsq = " | ".join(w for w in dict.fromkeys(q) if w.isalnum())
        if tsq:
            for cid, score in session.execute(text("SELECT id, ts_rank(to_tsvector('simple', stems), to_tsquery('simple', :q)) AS r FROM cx_chunk WHERE tag IN :tags AND to_tsvector('simple', stems) @@ to_tsquery('simple', :q) ORDER BY r DESC LIMIT 30").bindparams(bindparam("tags", expanding=True)), {"q": tsq, "tags": list(tags)}):
                bm[int(cid)] = float(score)
    top_cos = _scan_vectors(session, tags, qvec)
    need = set(bm) | set(top_cos)
    info = {cid: (did, vec, st) for cid, did, vec, st in session.execute(select(Chunk.id, Chunk.document_id, Chunk.vec, Chunk.stems).where(Chunk.id.in_(need), Chunk.tag.in_(tags))).all()} if need else {}
    bm = {c: v for c, v in bm.items() if c in info}
    cos = {c: top_cos[c] if c in top_cos else cosine(qvec, info[c][1] or {}) for c in info}
    r_bm = {cid: i for i, cid in enumerate(sorted(bm, key=lambda c: (-bm[c], c)))}
    r_cos = {cid: i for i, cid in enumerate(sorted((c for c in top_cos if c in info), key=lambda c: (-top_cos[c], c)))}
    fused = {c: (1 / (60 + r_bm[c]) if c in r_bm else 0) + (1 / (60 + r_cos[c]) if c in r_cos else 0) for c in set(r_bm) | set(r_cos)}
    return [Hit(c, info[c][0], f, bm.get(c, 0.0), cos.get(c, 0.0), coverage(session, query, info[c][2], tags)) for c, f in sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]


def unmatched_terms(session: Session, query: str, tags: tuple[str, ...], soft: set[str] | frozenset = frozenset()) -> list[str]:
    """Meaningful words of the question that the visible documents never use and no synonym bridges. A question built around such a word is probably not covered."""
    from lorefern.synonyms import EXPAND

    idf, _ = idf_table(session, tags)
    generic = {stem(x) for x in "held hold happen happens make made give given take takes need needs must within often soon quick quickly long many much exactly really actually anyone someone everyone choose chose picked pick start started begin work works working allowed allow able".split()}
    return [w for w in stems(query) if len(w) >= 4 and not w.isdigit() and w not in idf and w not in EXPAND and w not in soft and w not in generic]
