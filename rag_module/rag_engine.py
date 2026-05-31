# =============================================================================
# rag_module/rag_engine.py
# SurgiMind – Retrieval-Augmented Generation Module
#
# WHAT THIS DOES:
#   1. Loads .txt (and optionally .pdf) clinical guideline documents from
#      backend/knowledge_base/
#   2. Splits them into overlapping chunks (~500 chars)
#   3. Builds a TF-IDF vector store (pure Python + numpy – zero extra installs)
#   4. Automatically upgrades to ChromaDB + sentence-transformers if installed
#   5. Exposes a single public function:
#         retrieve_protocols(query, top_k=3) → list[RetrievedChunk]
#
# HOW TO INSTALL OPTIONAL UPGRADES (better accuracy):
#   pip install chromadb sentence-transformers
#   pip install pypdf          # only needed if you add .pdf files
#
# HOW TO USE:
#   from rag_module.rag_engine import retrieve_protocols, build_index
#   build_index()                              # call once at startup
#   results = retrieve_protocols("sepsis emergency high lactate", top_k=3)
#   for r in results:
#       print(r.source, r.score, r.text[:200])
#
# COMPATIBLE WITH:
#   backend/groq_service.py  – calls retrieve_protocols() to get RAG context
#   backend/routers/predict.py – orchestrates the full pipeline
# =============================================================================

from __future__ import annotations

import os
import re
import math
import json
import time
import hashlib
import logging
from pathlib import Path
from typing   import Optional
from dataclasses import dataclass, field

import numpy as np

# ── Logger ────────────────────────────────────────────────────────────────────
log = logging.getLogger("SurgiMind.RAG")
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE           = Path(__file__).resolve().parent
_PROJECT_ROOT   = _HERE.parent
KNOWLEDGE_BASE  = _PROJECT_ROOT / "backend" / "knowledge_base"
CHROMA_PERSIST  = _PROJECT_ROOT / "backend" / "chroma_db"

# ── Constants ──────────────────────────────────────────────────────────────────
CHUNK_SIZE    = 500    # characters per chunk
CHUNK_OVERLAP = 100    # character overlap between consecutive chunks
COLLECTION    = "surgimind_guidelines"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class DocumentChunk:
    """A single text chunk with provenance metadata."""
    chunk_id : str          # unique hash of the text
    text     : str          # chunk text content
    source   : str          # filename it came from
    title    : str = ""     # extracted TITLE line if present
    category : str = ""     # extracted CATEGORY line if present


@dataclass
class RetrievedChunk:
    """A chunk returned from retrieval with its similarity score."""
    text     : str
    source   : str
    title    : str
    category : str
    score    : float        # cosine similarity [0.0 – 1.0]

    def to_dict(self) -> dict:
        return {
            "text"    : self.text,
            "source"  : self.source,
            "title"   : self.title,
            "category": self.category,
            "score"   : round(self.score, 4),
        }

    def to_context_string(self) -> str:
        """Returns a formatted string ready for LLM prompt injection."""
        header = f"[Guideline: {self.title or self.source} | Relevance: {self.score:.2%}]"
        return f"{header}\n{self.text}"


# =============================================================================
# DOCUMENT LOADER
# =============================================================================

def _extract_metadata(text: str) -> tuple[str, str]:
    """Extracts TITLE and CATEGORY lines from the top of a guideline doc."""
    title = category = ""
    for line in text.splitlines()[:10]:
        if line.startswith("TITLE:"):
            title    = line.replace("TITLE:", "").strip()
        elif line.startswith("CATEGORY:"):
            category = line.replace("CATEGORY:", "").strip()
    return title, category


def _load_txt(path: Path) -> str:
    """Reads a plain-text file."""
    return path.read_text(encoding="utf-8", errors="replace")


def _load_pdf(path: Path) -> str:
    """
    Reads a PDF using pypdf (optional dependency).
    Falls back to empty string if pypdf is not installed.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages  = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)
    except ImportError:
        log.warning(f"pypdf not installed – skipping PDF: {path.name}. "
                    "Run: pip install pypdf")
        return ""
    except Exception as e:
        log.error(f"Failed to read PDF {path.name}: {e}")
        return ""


def _chunk_text(text: str, source: str, title: str, category: str) -> list[DocumentChunk]:
    """Splits document text into overlapping chunks."""
    text   = text.strip()
    chunks = []
    start  = 0

    while start < len(text):
        end       = min(start + CHUNK_SIZE, len(text))
        chunk_txt = text[start:end].strip()

        if len(chunk_txt) > 60:   # ignore tiny trailing fragments
            uid = hashlib.md5(chunk_txt.encode()).hexdigest()[:16]
            chunks.append(DocumentChunk(
                chunk_id = uid,
                text     = chunk_txt,
                source   = source,
                title    = title,
                category = category,
            ))
        start += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


def load_knowledge_base(kb_dir: Path = KNOWLEDGE_BASE) -> list[DocumentChunk]:
    """
    Scans kb_dir for .txt and .pdf files and returns all document chunks.

    Args:
        kb_dir: Path to knowledge_base directory

    Returns:
        List of DocumentChunk objects ready for indexing
    """
    if not kb_dir.exists():
        log.error(f"Knowledge base directory not found: {kb_dir}")
        return []

    all_chunks: list[DocumentChunk] = []

    # Process .txt files
    for txt_path in sorted(kb_dir.glob("*.txt")):
        text            = _load_txt(txt_path)
        title, category = _extract_metadata(text)
        chunks          = _chunk_text(text, txt_path.name, title, category)
        all_chunks.extend(chunks)
        log.info(f"Loaded {len(chunks):3d} chunks ← {txt_path.name}")

    # Process .pdf files (if pypdf available)
    for pdf_path in sorted(kb_dir.glob("*.pdf")):
        text            = _load_pdf(pdf_path)
        if text:
            title, category = _extract_metadata(text)
            chunks          = _chunk_text(text, pdf_path.name, title, category)
            all_chunks.extend(chunks)
            log.info(f"Loaded {len(chunks):3d} chunks ← {pdf_path.name}")

    log.info(f"Knowledge base: {len(all_chunks)} total chunks from {kb_dir}")
    return all_chunks


# =============================================================================
# VECTOR STORE – BACKEND SELECTION
# =============================================================================
# The system automatically picks the best available backend:
#   Priority 1: ChromaDB + sentence-transformers  (semantic, best accuracy)
#   Priority 2: sentence-transformers + numpy      (semantic, no persistence)
#   Priority 3: TF-IDF + numpy                    (lexical, zero extra installs)
# =============================================================================

class _TFIDFVectorStore:
    """
    Pure Python + numpy TF-IDF vector store.
    No extra pip installs required.
    Accurate enough for keyword-rich medical text.
    """

    def __init__(self):
        self._chunks    : list[DocumentChunk] = []
        self._vocab     : dict[str, int]      = {}
        self._idf       : np.ndarray          = np.array([])
        self._tfidf_mat : np.ndarray          = np.array([])   # shape: (n_chunks, vocab)
        self._built     : bool                = False

    # ── Text normalisation ────────────────────────────────────────────────────

    @staticmethod
    def _tokenise(text: str) -> list[str]:
        """Lowercase, remove punctuation, split on whitespace."""
        text   = text.lower()
        text   = re.sub(r"[^a-z0-9\s]", " ", text)
        tokens = text.split()
        # Simple medical stopword filter (keep clinical terms)
        stops  = {"the", "a", "an", "is", "are", "was", "were", "and",
                   "or", "of", "in", "to", "for", "with", "that", "this",
                   "be", "by", "on", "at", "from", "as", "it", "its"}
        return [t for t in tokens if t not in stops and len(t) > 1]

    # ── Index building ────────────────────────────────────────────────────────

    def build(self, chunks: list[DocumentChunk]) -> None:
        """Builds TF-IDF matrix from document chunks."""
        if not chunks:
            log.warning("No chunks to index.")
            return

        self._chunks = chunks
        n            = len(chunks)

        log.info(f"Building TF-IDF index over {n} chunks...")
        t0 = time.time()

        # ── Step 1: build vocabulary ──────────────────────────────────────────
        token_lists = [self._tokenise(c.text) for c in chunks]
        vocab_set   = {tok for toks in token_lists for tok in toks}
        self._vocab = {tok: i for i, tok in enumerate(sorted(vocab_set))}
        V           = len(self._vocab)

        # ── Step 2: term frequency matrix ─────────────────────────────────────
        tf_mat = np.zeros((n, V), dtype=np.float32)
        for i, toks in enumerate(token_lists):
            for tok in toks:
                if tok in self._vocab:
                    tf_mat[i, self._vocab[tok]] += 1
            # Normalise by document length
            total = tf_mat[i].sum()
            if total > 0:
                tf_mat[i] /= total

        # ── Step 3: inverse document frequency ───────────────────────────────
        df          = (tf_mat > 0).sum(axis=0).astype(np.float32)
        self._idf   = np.log((n + 1) / (df + 1)) + 1.0   # smooth IDF

        # ── Step 4: TF-IDF matrix (L2-normalised rows) ───────────────────────
        tfidf          = tf_mat * self._idf
        norms          = np.linalg.norm(tfidf, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._tfidf_mat = (tfidf / norms).astype(np.float32)

        self._built = True
        log.info(f"TF-IDF index ready: {n} chunks, {V} vocab terms "
                 f"({time.time()-t0:.2f}s)")

    # ── Query ─────────────────────────────────────────────────────────────────

    def query(self, text: str, top_k: int = 3) -> list[RetrievedChunk]:
        """Returns top-k most similar chunks for the query text."""
        if not self._built or len(self._chunks) == 0:
            log.warning("Index not built – call build() first.")
            return []

        # Embed query using the same TF-IDF vocabulary
        toks    = self._tokenise(text)
        q_vec   = np.zeros(len(self._vocab), dtype=np.float32)
        for tok in toks:
            if tok in self._vocab:
                q_vec[self._vocab[tok]] += 1

        q_vec  *= self._idf                    # apply IDF weights
        norm    = np.linalg.norm(q_vec)
        if norm == 0:
            log.warning("Query produced zero vector – no matching terms in vocabulary.")
            return []
        q_vec  /= norm                          # L2 normalise

        # Cosine similarity = dot product (both sides are L2-normalised)
        scores  = self._tfidf_mat @ q_vec       # shape: (n_chunks,)
        top_idx = np.argsort(-scores)[:top_k]

        results = []
        for idx in top_idx:
            chunk = self._chunks[idx]
            results.append(RetrievedChunk(
                text     = chunk.text,
                source   = chunk.source,
                title    = chunk.title,
                category = chunk.category,
                score    = float(scores[idx]),
            ))
        return results


class _SentenceTransformerStore:
    """
    Semantic vector store using sentence-transformers + numpy.
    Better accuracy than TF-IDF for paraphrased or partial queries.
    Install: pip install sentence-transformers
    """

    MODEL_NAME = "all-MiniLM-L6-v2"   # 22MB, fast, strong for medical text

    def __init__(self):
        from sentence_transformers import SentenceTransformer
        log.info(f"Loading sentence-transformer model: {self.MODEL_NAME}")
        self._model    : SentenceTransformer   = SentenceTransformer(self.MODEL_NAME)
        self._chunks   : list[DocumentChunk]   = []
        self._embeddings: Optional[np.ndarray] = None
        self._built    : bool                  = False

    def build(self, chunks: list[DocumentChunk]) -> None:
        self._chunks     = chunks
        texts            = [c.text for c in chunks]
        log.info(f"Embedding {len(texts)} chunks with {self.MODEL_NAME}…")
        t0               = time.time()
        embeddings       = self._model.encode(texts, show_progress_bar=True,
                                              batch_size=64, convert_to_numpy=True)
        # L2-normalise for cosine similarity via dot product
        norms            = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms==0]  = 1.0
        self._embeddings = (embeddings / norms).astype(np.float32)
        self._built      = True
        log.info(f"Semantic index ready: {len(chunks)} chunks ({time.time()-t0:.1f}s)")

    def query(self, text: str, top_k: int = 3) -> list[RetrievedChunk]:
        if not self._built:
            return []
        q    = self._model.encode([text], convert_to_numpy=True)
        q   /= (np.linalg.norm(q) + 1e-8)
        scores   = (self._embeddings @ q.T).flatten()
        top_idx  = np.argsort(-scores)[:top_k]
        results  = []
        for idx in top_idx:
            c = self._chunks[idx]
            results.append(RetrievedChunk(
                text=c.text, source=c.source, title=c.title,
                category=c.category, score=float(scores[idx])
            ))
        return results


class _ChromaDBStore:
    """
    Semantic vector store backed by ChromaDB (persistent on disk).
    Best option when chromadb + sentence-transformers are both installed.
    Install: pip install chromadb sentence-transformers
    """

    def __init__(self):
        import chromadb
        from chromadb.utils import embedding_functions
        CHROMA_PERSIST.mkdir(parents=True, exist_ok=True)
        self._client     = chromadb.PersistentClient(path=str(CHROMA_PERSIST))
        self._ef         = embedding_functions.SentenceTransformerEmbeddingFunction(
                               model_name="all-MiniLM-L6-v2"
                           )
        self._collection = self._client.get_or_create_collection(
                               name               = COLLECTION,
                               embedding_function = self._ef,
                               metadata           = {"hnsw:space": "cosine"},
                           )
        self._chunks: list[DocumentChunk] = []

    def build(self, chunks: list[DocumentChunk]) -> None:
        self._chunks = chunks
        existing     = self._collection.count()

        if existing >= len(chunks):
            log.info(f"ChromaDB collection already has {existing} vectors – skipping re-index.")
            return

        log.info(f"Indexing {len(chunks)} chunks into ChromaDB…")
        batch_size = 200
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            self._collection.upsert(
                ids        = [c.chunk_id for c in batch],
                documents  = [c.text     for c in batch],
                metadatas  = [{"source": c.source, "title": c.title,
                               "category": c.category} for c in batch],
            )
        log.info(f"ChromaDB index ready: {self._collection.count()} vectors")

    def query(self, text: str, top_k: int = 3) -> list[RetrievedChunk]:
        results = self._collection.query(
            query_texts = [text],
            n_results   = top_k,
        )
        out = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance → similarity
            score = 1.0 - dist
            out.append(RetrievedChunk(
                text     = doc,
                source   = meta.get("source",   ""),
                title    = meta.get("title",    ""),
                category = meta.get("category", ""),
                score    = score,
            ))
        return out


def _select_backend():
    """
    Auto-selects the best available vector store backend.
    Returns an uninitialised instance ready for .build()
    """
    try:
        import chromadb                               # noqa: F401
        from sentence_transformers import SentenceTransformer  # noqa: F401
        log.info("Backend selected: ChromaDB + sentence-transformers (semantic, persistent)")
        return _ChromaDBStore()
    except ImportError:
        pass

    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
        log.info("Backend selected: sentence-transformers + numpy (semantic, in-memory)")
        return _SentenceTransformerStore()
    except ImportError:
        pass

    log.info("Backend selected: TF-IDF + numpy (lexical, zero extra installs)")
    return _TFIDFVectorStore()


# =============================================================================
# SINGLETON ENGINE
# =============================================================================

_store  = None   # vector store instance (one per process)
_chunks : list[DocumentChunk] = []


def build_index(kb_dir: Path = KNOWLEDGE_BASE) -> None:
    """
    Loads the knowledge base and builds the vector index.
    Call ONCE at application startup (or before first retrieve_protocols call).

    Args:
        kb_dir: Path to directory containing .txt/.pdf guidelines
    """
    global _store, _chunks

    _chunks = load_knowledge_base(kb_dir)
    if not _chunks:
        log.error("No documents loaded. Place .txt or .pdf files in backend/knowledge_base/")
        return

    _store = _select_backend()
    _store.build(_chunks)
    log.info("RAG engine ready.")


def _ensure_built() -> None:
    """Lazily builds the index on first query if build_index() wasn't called."""
    if _store is None:
        log.info("Auto-building index on first query…")
        build_index()


# =============================================================================
# PUBLIC API
# =============================================================================

def retrieve_protocols(
    query  : str,
    top_k  : int = 3,
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    """
    Retrieves the top-k most relevant surgical guideline chunks for a query.

    Args:
        query     : Free-text clinical query, e.g.
                    "sepsis high lactate creatinine emergency surgery"
        top_k     : Number of results to return (default 3)
        min_score : Minimum similarity score threshold [0.0 – 1.0] (default 0.0)

    Returns:
        List of RetrievedChunk objects (ordered by descending relevance)

    Example:
        results = retrieve_protocols(
            "sepsis emergency high lactate elevated creatinine",
            top_k=3
        )
        for r in results:
            print(r.source, r.score, r.text[:300])
    """
    _ensure_built()

    if not query.strip():
        log.warning("Empty query passed to retrieve_protocols().")
        return []

    if _store is None:
        log.error("Vector store not initialised.")
        return []

    try:
        results = _store.query(query, top_k=top_k)
        # Apply minimum score filter
        results = [r for r in results if r.score >= min_score]
        log.info(f"Retrieved {len(results)} chunks for query: '{query[:60]}…'")
        return results

    except Exception as e:
        log.error(f"Retrieval failed: {e}")
        return []


def retrieve_protocols_as_context(
    query  : str,
    top_k  : int = 3,
) -> str:
    """
    Convenience wrapper: retrieves top-k chunks and returns them as a single
    formatted string ready to paste into an LLM prompt.

    Returns:
        str: Formatted multi-section context block
    """
    results = retrieve_protocols(query, top_k=top_k)

    if not results:
        return "No relevant surgical guidelines found in knowledge base."

    sections = []
    for i, r in enumerate(results, 1):
        sections.append(
            f"--- GUIDELINE {i} ---\n"
            f"Source   : {r.source}\n"
            f"Topic    : {r.title or 'General'}\n"
            f"Category : {r.category or 'Clinical Guidelines'}\n"
            f"Relevance: {r.score:.1%}\n\n"
            f"{r.text}"
        )

    return "\n\n".join(sections)


def retrieve_for_ml_output(ml_output: dict, top_k: int = 3) -> list[RetrievedChunk]:
    """
    Convenience wrapper that builds a query string directly from the structured
    ML model output dictionary.

    Args:
        ml_output: Dict from predict_risk() with keys:
                   risk_level, confidence, possible_concerns, clinical_text
        top_k    : Number of results to return

    Returns:
        List of RetrievedChunk objects

    Example:
        ml_output = {
            "risk_level"       : "HIGH",
            "confidence"       : "87%",
            "possible_concerns": ["Sepsis", "Advanced Age (>70)"],
            "clinical_text"    : "sepsis emergency male elderly high_severity_diagnosis"
        }
        results = retrieve_for_ml_output(ml_output)
    """
    # Build rich query from ML output fields
    parts = []

    risk = ml_output.get("risk_level", "")
    if risk:
        parts.append(f"{risk.lower()} risk")

    concerns = ml_output.get("possible_concerns", [])
    parts.extend([c.lower() for c in concerns])

    clinical_text = ml_output.get("clinical_text", "")
    if clinical_text:
        parts.append(clinical_text)

    query = " ".join(parts)
    return retrieve_protocols(query, top_k=top_k)


# =============================================================================
# CLI USAGE  –  python -m rag_module.rag_engine
# =============================================================================

if __name__ == "__main__":
    import sys

    print("\n" + "="*60)
    print("  SurgiMind RAG Engine – Self-Test")
    print("="*60)

    build_index()

    test_queries = [
        "sepsis high lactate creatinine emergency surgery",
        "cardiac arrest troponin elevated MI",
        "diabetes hyperglycaemia elective surgery glucose",
        "pneumonia respiratory failure oxygen saturation",
        "renal failure kidney creatinine urea",
    ]

    for q in test_queries:
        print(f"\n{'─'*55}")
        print(f"Query: {q}")
        print(f"{'─'*55}")
        results = retrieve_protocols(q, top_k=3)
        for i, r in enumerate(results, 1):
            print(f"  [{i}] {r.title or r.source}  |  score={r.score:.3f}")
            print(f"       {r.text[:120]}…")

    print("\n" + "="*60)
    print("  ML-output integration test")
    print("="*60)

    ml_sample = {
        "risk_level"       : "HIGH",
        "confidence"       : "91%",
        "possible_concerns": ["Sepsis", "Renal Failure"],
        "clinical_text"    : "sepsis emergency male elderly abnormal_lactate abnormal_creatinine",
    }

    results = retrieve_for_ml_output(ml_sample)
    print(f"\nML Output → {len(results)} guidelines retrieved:")
    for r in results:
        print(f"  • {r.title or r.source}  (score={r.score:.3f})")

    print("\n[RAG Self-Test Complete]\n")