#!/usr/bin/env python3
"""
Unified Embedding Provider for Claude-Dash

Provides embeddings with automatic fallback chain:
1. Ollama (if running) - fastest, uses Metal GPU
2. sentence-transformers - reliable fallback
3. Simple TF-IDF - last resort, always works

Usage:
    from embeddings import get_embeddings, EmbeddingProvider

    provider = EmbeddingProvider()
    vectors = provider.embed(["text1", "text2"])
    similarity = provider.similarity(vec1, vec2)
"""

import os
import json
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple
import numpy as np

# Use centralized config
try:
    from config import OLLAMA_URL, OLLAMA_EMBED_MODEL as EMBEDDING_MODEL, cosine_similarity as _cosine_sim
except ImportError:
    import math
    OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
    EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")

    def _cosine_sim(vec1: list, vec2: list) -> float:
        """Fallback cosine similarity implementation."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

# Cache for embeddings to avoid recomputation
_embedding_cache = {}


class EmbeddingProvider:
    """Unified embedding provider with automatic fallback."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path.home() / ".claude-dash" / "indexes"
        self.backend = self._detect_backend()
        self._sentence_model = None

    def _detect_backend(self) -> str:
        """Detect best available embedding backend."""
        # Try Ollama first
        if self._check_ollama():
            return "ollama"

        # Try sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            return "sentence-transformers"
        except ImportError:
            pass

        # Fall back to TF-IDF
        return "tfidf"

    def _check_ollama(self) -> bool:
        """Check if Ollama is running and has embedding model."""
        try:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
            with urllib.request.urlopen(req, timeout=2) as response:
                data = json.loads(response.read().decode())
                models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                return EMBEDDING_MODEL.split(":")[0] in models
        except:
            return False

    def embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for texts using best available backend."""
        if self.backend == "ollama":
            return self._embed_ollama(texts)
        elif self.backend == "sentence-transformers":
            return self._embed_sentence_transformers(texts)
        else:
            return self._embed_tfidf(texts)

    def embed_single(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        # Check cache first
        cache_key = hash(text)
        if cache_key in _embedding_cache:
            return _embedding_cache[cache_key]

        result = self.embed([text])[0]
        _embedding_cache[cache_key] = result
        return result

    def _embed_ollama(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using Ollama."""
        embeddings = []
        for text in texts:
            try:
                data = json.dumps({
                    "model": EMBEDDING_MODEL,
                    "prompt": text[:8000]  # Truncate for safety
                }).encode('utf-8')

                req = urllib.request.Request(
                    f"{OLLAMA_URL}/api/embeddings",
                    data=data,
                    headers={"Content-Type": "application/json"}
                )

                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.loads(response.read().decode())
                    embeddings.append(result.get("embedding", []))
            except Exception as e:
                # Fallback to sentence-transformers for this text
                if self._sentence_model is None:
                    try:
                        from sentence_transformers import SentenceTransformer
                        self._sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
                    except:
                        embeddings.append([0.0] * 384)
                        continue
                embeddings.append(self._sentence_model.encode(text).tolist())

        return np.array(embeddings)

    def _embed_sentence_transformers(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using sentence-transformers."""
        if self._sentence_model is None:
            from sentence_transformers import SentenceTransformer
            self._sentence_model = SentenceTransformer('all-MiniLM-L6-v2')

        return self._sentence_model.encode(texts)

    def _embed_tfidf(self, texts: List[str]) -> np.ndarray:
        """Simple TF-IDF based embeddings (fallback)."""
        from collections import Counter
        import math

        # Build vocabulary
        all_tokens = []
        for text in texts:
            tokens = text.lower().split()
            all_tokens.extend(tokens)

        vocab = list(set(all_tokens))
        vocab_idx = {w: i for i, w in enumerate(vocab)}

        # Compute TF-IDF
        embeddings = []
        doc_freq = Counter(all_tokens)
        n_docs = len(texts)

        for text in texts:
            tokens = text.lower().split()
            tf = Counter(tokens)
            vec = np.zeros(min(len(vocab), 384))  # Limit dimension

            for token, count in tf.items():
                if token in vocab_idx and vocab_idx[token] < 384:
                    idf = math.log(n_docs / (1 + doc_freq[token]))
                    vec[vocab_idx[token]] = count * idf

            # Normalize
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm

            embeddings.append(vec)

        return np.array(embeddings)

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.

        Uses centralized implementation from config.py.
        """
        # Convert numpy arrays to lists for config.cosine_similarity
        vec1 = a.tolist() if hasattr(a, 'tolist') else list(a)
        vec2 = b.tolist() if hasattr(b, 'tolist') else list(b)
        return _cosine_sim(vec1, vec2)

    def search(self, query: str, documents: List[str], top_k: int = 5) -> List[Tuple[int, float]]:
        """Search documents by query similarity."""
        query_vec = self.embed_single(query)
        doc_vecs = self.embed(documents)

        scores = []
        for i, doc_vec in enumerate(doc_vecs):
            score = self.cosine_similarity(query_vec, doc_vec)
            scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]


# Module-level convenience functions
_provider = None

def get_provider() -> EmbeddingProvider:
    """Get or create the default embedding provider."""
    global _provider
    if _provider is None:
        _provider = EmbeddingProvider()
    return _provider

def embed(texts: List[str]) -> np.ndarray:
    """Generate embeddings using the default provider."""
    return get_provider().embed(texts)

def embed_single(text: str) -> np.ndarray:
    """Generate embedding for a single text."""
    return get_provider().embed_single(text)

def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return EmbeddingProvider.cosine_similarity(a, b)


if __name__ == "__main__":
    # Test the provider
    provider = EmbeddingProvider()
    print(f"Using backend: {provider.backend}")

    texts = ["Hello world", "Goodbye world", "Machine learning is cool"]
    embeddings = provider.embed(texts)
    print(f"Embedding shape: {embeddings.shape}")

    # Test similarity
    sim = provider.cosine_similarity(embeddings[0], embeddings[1])
    print(f"Similarity between 'Hello world' and 'Goodbye world': {sim:.4f}")
