"""
embed.py — Milestone 4: Embedding and retrieval.

Embeds the per-review chunks from ingest.py with sentence-transformers
(all-MiniLM-L6-v2) and stores them in a persistent ChromaDB collection, then
retrieves the top-k most similar chunks for a query — with optional metadata
filtering (e.g. only a specific course).

Build the index + run the evaluation queries:  python embed.py
"""

from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from ingest import chunk_text, load_documents

MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION_NAME = "rmp_reviews"
PERSIST_DIR = str(Path(__file__).parent / "chroma_db")
TOP_K = 8

# Load the embedding model once and reuse it (loading is the slow part).
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def get_client() -> chromadb.ClientAPI:
    return chromadb.PersistentClient(
        path=PERSIST_DIR, settings=Settings(anonymized_telemetry=False)
    )


# --- Embedding + storage --------------------------------------------------


def embed_and_store(
    chunks: list[tuple[str, dict]], reset: bool = True
) -> chromadb.Collection:
    """Embed (chunk_text, metadata) pairs and store them in ChromaDB.

    Uses cosine distance. Embeds with the same model used at query time so the
    vectors are comparable. Re-running with reset=True rebuilds from scratch.
    """
    client = get_client()
    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass  # collection didn't exist yet
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )

    texts = [c for c, _ in chunks]
    metadatas = [m for _, m in chunks]
    ids = [m["chunk_id"] for _, m in chunks]

    model = get_model()
    embeddings = model.encode(
        texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True
    ).tolist()

    collection.add(
        ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas
    )
    return collection


# --- Retrieval ------------------------------------------------------------


def retrieve(
    query: str,
    k: int = TOP_K,
    filters: dict | None = None,
    collection: chromadb.Collection | None = None,
) -> list[dict]:
    """Embed the query and return the top-k most similar chunks.

    `filters` is an optional ChromaDB metadata where-clause, e.g.
    {"course": "CS3000"} or {"professor": "Mark Fontenot"}.
    """
    if collection is None:
        collection = get_client().get_collection(COLLECTION_NAME)

    model = get_model()
    query_embedding = model.encode([query], normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=k,
        where=filters,
    )

    # Flatten ChromaDB's nested result lists into a simple list of dicts.
    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({"text": doc, "metadata": meta, "distance": dist})
    return hits


# --- Verification harness -------------------------------------------------

EVAL_QUERIES = [
    ("Who is better for CS1800 — Gregory Aloupis or Lucia Nunez?", None),
    ("What grades do students get in Akshar Varma's CS3000?", {"course": "CS3000"}),
    ("How difficult is Akshar Varma's CS3000?", {"course": "CS3000"}),
    ("Is Mark Fontenot's CS3200 worth taking?", {"course": "CS3200"}),
    ("Do students rate Mark Fontenot's CS3200 or CS3500 higher?",
     {"professor": "Mark Fontenot"}),
]


def main() -> None:
    print("Building index...")
    chunks = chunk_text(load_documents())
    collection = embed_and_store(chunks)
    print(f"Stored {collection.count()} chunks in ChromaDB at {PERSIST_DIR}\n")

    for query, filters in EVAL_QUERIES:
        print("=" * 70)
        print(f"Q: {query}")
        if filters:
            print(f"   (filter: {filters})")
        hits = retrieve(query, k=3, filters=filters)  # k=3 here just to keep output short
        for h in hits:
            m = h["metadata"]
            print(f"  [{h['distance']:.3f}] {m['professor']} {m['course']} "
                  f"(Q{m['quality']}/D{m['difficulty']}, grade {m['grade']})")
            snippet = h["text"].split(": ", 1)[-1][:110]
            print(f"          {snippet}...")
        print()


if __name__ == "__main__":
    main()
