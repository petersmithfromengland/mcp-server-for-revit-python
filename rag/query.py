# -*- coding: utf-8 -*-
"""
RAG query interface.

Loads a pre-built ChromaDB vector store and exposes a ``search()``
function that the workflow planner calls.  The store and embedding
function are initialised lazily on first use.
"""

import os
from dataclasses import dataclass
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class RAGResult:
    """A single search result from the vector store."""

    text: str
    module: str
    name: str
    source_type: str  # "function" | "class_doc" | "module_doc" | "text_chunk"
    source_file: str
    distance: float  # cosine distance (0 = identical, 2 = opposite)


# ---------------------------------------------------------------------------
# Lazy singleton — loaded once per process
# ---------------------------------------------------------------------------

import threading

_collection = None
_embed_fn = None
_init_lock = threading.Lock()


def _get_collection(store_dir: str, embedding_model: str):
    """Return (or create) the ChromaDB collection singleton.

    Thread-safe: concurrent callers block until the first initialisation
    completes rather than each starting their own load.
    """
    global _collection, _embed_fn

    if _collection is not None:
        return _collection

    with _init_lock:
        # Re-check inside the lock — another thread may have finished while
        # this one was waiting.
        if _collection is not None:
            return _collection

        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        if not os.path.isdir(store_dir):
            raise FileNotFoundError(
                "Vector store not found at: {}\n"
                "Run 'python -m rag.indexer' to build the index first.".format(store_dir)
            )

        logger.info(
            "Initialising ChromaDB collection (store=%s, model=%s)",
            store_dir,
            embedding_model,
        )
        _embed_fn = SentenceTransformerEmbeddingFunction(model_name=embedding_model)
        client = chromadb.PersistentClient(path=store_dir)
        _collection = client.get_collection(
            name="duhast",
            embedding_function=_embed_fn,
        )
        logger.info("ChromaDB collection loaded: %d documents", _collection.count())

    return _collection


def prewarm(store_dir: str, embedding_model: str = "all-MiniLM-L6-v2") -> None:
    """Load the ChromaDB collection and embedding model into memory.

    Intended to be called once at server startup in a background thread so
    that the first tool call does not pay the cold-start cost.
    """
    logger.info("RAG prewarm starting (store=%s, model=%s)", store_dir, embedding_model)
    try:
        _get_collection(store_dir, embedding_model)
        logger.info("RAG prewarm complete")
    except Exception as exc:
        logger.warning("RAG prewarm failed: %s", exc)


def search(
    query: str,
    store_dir: str,
    embedding_model: str = "all-MiniLM-L6-v2",
    max_results: int = 8,
) -> List[RAGResult]:
    """Search the duHast vector store and return ranked results.

    Args:
        query: Natural language query string.
        store_dir: Path to the ChromaDB persistent directory.
        embedding_model: Must match the model used at index time.
        max_results: Maximum number of results to return.

    Returns:
        List of RAGResult, sorted by relevance (lowest distance first).
    """
    collection = _get_collection(store_dir, embedding_model)

    logger.debug(
        "Querying ChromaDB: query=%r, max_results=%d", query[:100], max_results
    )

    results = collection.query(
        query_texts=[query],
        n_results=max_results,
        include=["documents", "metadatas", "distances"],
    )

    items: list[RAGResult] = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(docs, metas, dists):
        items.append(
            RAGResult(
                text=doc,
                module=meta.get("module", ""),
                name=meta.get("name", ""),
                source_type=meta.get("type", ""),
                source_file=meta.get("source_file", ""),
                distance=dist,
            )
        )

    logger.debug(
        "Search returned %d results (best distance=%.3f)",
        len(items),
        items[0].distance if items else -1,
    )

    return items


def is_index_ready(store_dir: str) -> bool:
    """Check whether the vector store exists and has documents.

    Reuses the in-memory singleton when already loaded to avoid a second
    cold-start hit from creating another PersistentClient.
    """
    if not os.path.isdir(store_dir):
        logger.debug("is_index_ready: directory not found: %s", store_dir)
        return False

    # Fast path: singleton already loaded
    if _collection is not None:
        count = _collection.count()
        logger.debug("is_index_ready: collection has %d documents (singleton)", count)
        return count > 0

    # Slow path: lightweight check without loading the embedding model
    try:
        import chromadb

        client = chromadb.PersistentClient(path=store_dir)
        coll = client.get_collection("duhast")
        count = coll.count()
        logger.debug("is_index_ready: collection has %d documents", count)
        return count > 0
    except Exception as e:
        logger.warning("is_index_ready check failed: %s", e)
        return False
