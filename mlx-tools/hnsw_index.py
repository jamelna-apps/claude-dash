#!/usr/bin/env python3
"""
Persistent HNSW Index for Claude Memory

Provides O(log n) approximate nearest neighbor search instead of O(n) brute force.
Index is persisted to disk and loaded on demand.

Uses hnswlib - a fast, memory-efficient library for ANN search.
"""

import sys
import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import pickle

MLX_DIR = Path(__file__).parent
sys.path.insert(0, str(MLX_DIR))

MEMORY_ROOT = Path.home() / '.claude-dash'
INDEX_DIR = MEMORY_ROOT / 'indexes'

# Try to import hnswlib
try:
    import hnswlib
    HAS_HNSWLIB = True
except ImportError:
    HAS_HNSWLIB = False
    print("Warning: hnswlib not installed. Install with: pip install hnswlib", file=sys.stderr)


class HNSWIndex:
    """Persistent HNSW index for a project."""

    def __init__(self, project_id: str, dim: int = 768, max_elements: int = 10000):
        self.project_id = project_id
        self.dim = dim
        self.max_elements = max_elements

        self.index_path = INDEX_DIR / f"{project_id}.hnsw"
        self.metadata_path = INDEX_DIR / f"{project_id}.meta"

        self.index: Optional[hnswlib.Index] = None
        self.id_to_path: Dict[int, str] = {}  # Map internal IDs to file paths
        self.path_to_id: Dict[str, int] = {}  # Reverse lookup
        self.next_id = 0

        INDEX_DIR.mkdir(parents=True, exist_ok=True)

    def load(self) -> bool:
        """Load index from disk."""
        if not HAS_HNSWLIB:
            return False

        if not self.index_path.exists():
            return False

        try:
            self.index = hnswlib.Index(space='cosine', dim=self.dim)
            self.index.load_index(str(self.index_path), max_elements=self.max_elements)

            # Load metadata
            if self.metadata_path.exists():
                with open(self.metadata_path, 'rb') as f:
                    meta = pickle.load(f)
                    self.id_to_path = meta['id_to_path']
                    self.path_to_id = meta['path_to_id']
                    self.next_id = meta['next_id']

            return True
        except Exception as e:
            print(f"Error loading index: {e}", file=sys.stderr)
            return False

    def save(self):
        """Save index to disk."""
        if self.index is None:
            return

        self.index.save_index(str(self.index_path))

        # Save metadata
        with open(self.metadata_path, 'wb') as f:
            pickle.dump({
                'id_to_path': self.id_to_path,
                'path_to_id': self.path_to_id,
                'next_id': self.next_id
            }, f)

    def create(self):
        """Create a new empty index."""
        if not HAS_HNSWLIB:
            raise RuntimeError("hnswlib not installed")

        self.index = hnswlib.Index(space='cosine', dim=self.dim)
        self.index.init_index(
            max_elements=self.max_elements,
            ef_construction=200,  # Higher = better quality, slower build
            M=16  # Number of connections per element
        )
        self.index.set_ef(50)  # Query time accuracy/speed tradeoff

    def add(self, file_path: str, embedding: np.ndarray) -> int:
        """Add or update an embedding."""
        if self.index is None:
            self.create()

        # Check if file already exists
        if file_path in self.path_to_id:
            # Update existing - hnswlib doesn't support update, so we just add
            # The old vector will be orphaned but that's OK for now
            internal_id = self.path_to_id[file_path]
        else:
            internal_id = self.next_id
            self.next_id += 1

        # Ensure embedding is right shape
        if len(embedding.shape) == 1:
            embedding = embedding.reshape(1, -1)

        self.index.add_items(embedding, [internal_id])
        self.id_to_path[internal_id] = file_path
        self.path_to_id[file_path] = internal_id

        return internal_id

    def search(self, query_embedding: np.ndarray, k: int = 10) -> List[Tuple[str, float]]:
        """Search for k nearest neighbors."""
        if self.index is None or self.index.get_current_count() == 0:
            return []

        # Ensure embedding is right shape
        if len(query_embedding.shape) == 1:
            query_embedding = query_embedding.reshape(1, -1)

        # Search
        labels, distances = self.index.knn_query(query_embedding, k=min(k, self.index.get_current_count()))

        results = []
        for label, dist in zip(labels[0], distances[0]):
            if label in self.id_to_path:
                # Convert cosine distance to similarity
                similarity = 1 - dist
                results.append((self.id_to_path[label], float(similarity)))

        return results

    def remove(self, file_path: str):
        """Mark a file as removed (hnswlib doesn't support true deletion)."""
        if file_path in self.path_to_id:
            internal_id = self.path_to_id[file_path]
            del self.path_to_id[file_path]
            del self.id_to_path[internal_id]
            # Note: The vector is still in the index but won't be returned

    def count(self) -> int:
        """Get number of indexed items."""
        return len(self.id_to_path)

    def rebuild(self):
        """Rebuild index from scratch (use after many deletions)."""
        if not self.index:
            return

        # Get all current embeddings
        embeddings = []
        paths = []
        for path, internal_id in self.path_to_id.items():
            try:
                vec = self.index.get_items([internal_id])
                embeddings.append(vec[0])
                paths.append(path)
            except:
                pass

        if not embeddings:
            return

        # Create new index
        self.create()
        self.id_to_path = {}
        self.path_to_id = {}
        self.next_id = 0

        # Re-add all embeddings
        for path, emb in zip(paths, embeddings):
            self.add(path, np.array(emb))


def build_from_ollama_embeddings(project_id: str) -> HNSWIndex:
    """Build HNSW index from existing Ollama embeddings."""
    embeddings_path = MEMORY_ROOT / 'projects' / project_id / 'ollama_embeddings.json'

    if not embeddings_path.exists():
        print(f"No Ollama embeddings found for {project_id}")
        print(f"Run: mlx ollama-embed build {project_id}")
        return None

    embeddings_data = json.loads(embeddings_path.read_text())

    # Handle both old format (files at root) and new format (under 'embeddings' key)
    if 'embeddings' in embeddings_data:
        files_data = embeddings_data['embeddings']
        dim = embeddings_data.get('dim', 768)
    else:
        # Old format: files directly at root level
        files_data = embeddings_data
        dim = 768  # Default dimension for nomic-embed-text

    index = HNSWIndex(project_id, dim=dim)
    index.create()

    count = 0
    for file_path, data in files_data.items():
        # Skip metadata keys
        if file_path in ('dim', 'model', 'created_at'):
            continue

        embedding = None
        if isinstance(data, dict) and 'embedding' in data:
            embedding = data['embedding']
        elif isinstance(data, list):
            embedding = data

        if embedding:
            embedding = np.array(embedding, dtype=np.float32)
            if len(embedding) > 0:
                # Update dim if we see actual data
                if count == 0:
                    dim = len(embedding)
                    index = HNSWIndex(project_id, dim=dim)
                    index.create()
                index.add(file_path, embedding)
                count += 1

    index.save()
    print(f"Built HNSW index for {project_id}: {count} vectors, dim={dim}")
    return index


def search_project(project_id: str, query_embedding: List[float], k: int = 10) -> List[Dict]:
    """Search a project using HNSW index."""
    index = HNSWIndex(project_id)

    if not index.load():
        # Fall back to building from Ollama embeddings
        index = build_from_ollama_embeddings(project_id)
        if not index:
            return []

    query = np.array(query_embedding, dtype=np.float32)
    results = index.search(query, k)

    # Enhance results with file info
    from memory_db import get_connection
    conn = get_connection()

    enhanced = []
    for path, similarity in results:
        cursor = conn.execute("""
            SELECT summary, purpose, component_name
            FROM files
            WHERE project_id = ? AND path = ?
        """, (project_id, path))
        row = cursor.fetchone()

        enhanced.append({
            'file': path,
            'similarity': similarity,
            'summary': row['summary'] if row else None,
            'purpose': row['purpose'] if row else None
        })

    conn.close()
    return enhanced


def main():
    import argparse

    parser = argparse.ArgumentParser(description='HNSW Index Manager')
    parser.add_argument('command', choices=['build', 'search', 'stats', 'rebuild'])
    parser.add_argument('project', help='Project ID')
    parser.add_argument('query', nargs='?', help='Search query (for search command)')
    parser.add_argument('--limit', '-k', type=int, default=10, help='Number of results')

    args = parser.parse_args()

    if not HAS_HNSWLIB:
        print("Error: hnswlib not installed")
        print("Install with: pip install hnswlib")
        sys.exit(1)

    if args.command == 'build':
        build_from_ollama_embeddings(args.project)

    elif args.command == 'stats':
        index = HNSWIndex(args.project)
        if index.load():
            print(f"Project: {args.project}")
            print(f"Indexed files: {index.count()}")
            print(f"Dimension: {index.dim}")
        else:
            print(f"No index found for {args.project}")

    elif args.command == 'rebuild':
        index = HNSWIndex(args.project)
        if index.load():
            index.rebuild()
            index.save()
            print(f"Rebuilt index for {args.project}")
        else:
            print(f"No index found to rebuild")

    elif args.command == 'search':
        if not args.query:
            print("Error: search requires a query")
            sys.exit(1)

        # Get query embedding from Ollama
        try:
            from ollama_embeddings import get_embedding
            query_embedding = get_embedding(args.query)
        except Exception as e:
            print(f"Error getting query embedding: {e}")
            sys.exit(1)

        results = search_project(args.project, query_embedding, args.limit)

        for r in results:
            print(f"{r['file']} (similarity: {r['similarity']:.3f})")
            if r.get('purpose'):
                print(f"  {r['purpose']}")


if __name__ == '__main__':
    main()
