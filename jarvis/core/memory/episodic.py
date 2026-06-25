"""
Tier 2 — Episodic Memory (Real RAG with Qdrant + SentenceTransformers)
-----------------------------------------------------------------------
Stores conversation summaries and important episodes as dense vectors.
Uses cosine similarity search + MMR-lite deduplication for diverse retrieval.

Storage backend : Qdrant (local on-disk, no server required)
Embedding model : all-MiniLM-L6-v2 (384-dim, free, runs locally)
Retrieval       : Dense vector search → score threshold → MMR dedup → top-K

Scaling path:
    Local dev  → QdrantClient(path="./data/qdrant_storage")
    Production → QdrantClient(url="https://your-cluster.qdrant.io", api_key=...)
"""
import atexit
import uuid
from datetime import datetime, timezone
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)
from sentence_transformers import SentenceTransformer

from core.config import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    QDRANT_COLLECTION,
    QDRANT_PATH,
    RAG_SCORE_THRESHOLD,
    RAG_TOP_K,
)

# ── Module-level singletons (lazy-initialized) ────────────────────────────────
_client: Optional[QdrantClient] = None
_embedder: Optional[SentenceTransformer] = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(path=QDRANT_PATH)
        existing = {c.name for c in _client.get_collections().collections}
        if QDRANT_COLLECTION not in existing:
            _client.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
        # Close the client explicitly BEFORE Python teardown to avoid
        # the "__del__ ImportError: sys.meta_path is None" shutdown error.
        atexit.register(_close_client)
    return _client


def _close_client() -> None:
    """Graceful cleanup called by atexit — runs before Python tears down imports."""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        # normalize_embeddings=True ensures cosine similarity == dot product
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


def embed(text: str) -> list[float]:
    return _get_embedder().encode(text, normalize_embeddings=True).tolist()


# ── Write ─────────────────────────────────────────────────────────────────────

def store_episode(content: str, topic: str = "conversation", metadata: dict | None = None) -> str:
    """
    Embed and store a new episode in Qdrant.
    Call this at the end of meaningful exchanges to build episodic memory.
    Returns the UUID of the stored point.
    """
    episode_id = str(uuid.uuid4())
    vector = embed(content)
    payload = {
        "content": content,
        "topic": topic,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **(metadata or {}),
    }
    _get_client().upsert(
        collection_name=QDRANT_COLLECTION,
        points=[PointStruct(id=episode_id, vector=vector, payload=payload)],
    )
    return episode_id


# ── Read ──────────────────────────────────────────────────────────────────────

def retrieve_episodes(
    query: str,
    top_k: int = RAG_TOP_K,
    score_threshold: float = RAG_SCORE_THRESHOLD,
) -> list[dict]:
    """
    Dense vector search with MMR-lite deduplication.

    Pipeline:
      1. Embed query → query_points() in Qdrant (fetch 2x top_k candidates)
      2. Filter: keep only hits with score >= score_threshold
      3. MMR-lite: skip hits whose text overlaps >85% with already-selected hits
      4. Return top_k results sorted by score desc

    NOTE: Uses query_points() — the modern API in qdrant-client >= 1.7
          (client.search() was removed in qdrant-client 1.18)
    """
    client = _get_client()

    # Skip retrieval if collection is empty.
    # NOTE: info.points_count can be None in qdrant-client >= 1.9 during
    # index optimization even when data exists. Use client.count() instead
    # which always returns an accurate count regardless of indexing state.
    try:
        count_result = client.count(collection_name=QDRANT_COLLECTION, exact=False)
        if count_result.count == 0:
            return []
    except Exception:
        return []

    query_vector = embed(query)

    # query_points returns a QueryResponse; .points is the list of ScoredPoint
    response = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        limit=top_k * 2,           # fetch extra candidates for MMR filtering
        score_threshold=score_threshold,
        with_payload=True,
    )
    raw_hits = response.points      # list[ScoredPoint]

    # MMR-lite: greedily select diverse results
    selected: list[dict] = []
    selected_texts: list[str] = []

    for hit in sorted(raw_hits, key=lambda h: h.score, reverse=True):
        content = hit.payload.get("content", "") if hit.payload else ""
        # Skip near-duplicate of already selected content
        if any(_jaccard(content, seen) > 0.85 for seen in selected_texts):
            continue
        selected.append({
            "content":    content,
            "score":      round(hit.score, 4),
            "topic":      hit.payload.get("topic", "general") if hit.payload else "general",
            "created_at": hit.payload.get("created_at", "") if hit.payload else "",
        })
        selected_texts.append(content)
        if len(selected) >= top_k:
            break

    return selected


def get_episode_count() -> int:
    """Return total number of stored episodes."""
    try:
        info = _get_client().get_collection(QDRANT_COLLECTION)
        return info.points_count if info.points_count is not None else 0
    except Exception:
        return 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity for MMR deduplication."""
    set_a, set_b = set(a.lower().split()), set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)
