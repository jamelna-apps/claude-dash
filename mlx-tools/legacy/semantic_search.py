#!/usr/bin/env python3
"""
MLX Semantic Search for Claude Memory System

DEPRECATED: Use embeddings.py instead!
The unified EmbeddingProvider provides:
- Automatic backend detection (Ollama > sentence-transformers > TF-IDF)
- Consistent API across all backends
- Better fallback handling

This file is kept for backwards compatibility.
Use hybrid_search.py for searches - it uses the unified provider.

Original description:
Embeds file summaries and enables semantic search across the codebase.
Find related files even with different naming conventions.

Usage:
  source ~/.claude-dash/mlx-env/bin/activate
  python semantic_search.py <project-id> build     # Build embeddings
  python semantic_search.py <project-id> search "query"  # Search
  python semantic_search.py <project-id> similar <file>  # Find similar files
"""

import json
import sys
import argparse
import numpy as np
from pathlib import Path

try:
    from mlx_lm import load
    import mlx.core as mx
except ImportError:
    print("Error: mlx-lm not installed. Run: pip install mlx-lm")
    sys.exit(1)

MEMORY_ROOT = Path.home() / ".claude-dash"
DEFAULT_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"

def get_embedding(model, tokenizer, text, max_length=512):
    """Get embedding for text using mean pooling of hidden states."""
    # Truncate text
    tokens = tokenizer.encode(text[:2000])
    tokens = tokens[:max_length]

    # Get hidden states (using last layer)
    input_ids = mx.array([tokens])

    # Simple approach: use token embeddings directly
    embeddings = model.model.embed_tokens(input_ids)

    # Mean pooling
    embedding = mx.mean(embeddings, axis=1).squeeze()

    return np.array(embedding.tolist())

def cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def build_embeddings(project_id, model, tokenizer):
    """Build embeddings for all file summaries."""
    summaries_path = MEMORY_ROOT / "projects" / project_id / "summaries.json"
    embeddings_path = MEMORY_ROOT / "projects" / project_id / "embeddings.json"

    summaries = json.loads(summaries_path.read_text())

    embeddings = {
        "version": "1.0",
        "project": project_id,
        "model": DEFAULT_MODEL,
        "files": {}
    }

    files = summaries.get("files", {})
    total = len(files)

    print(f"Building embeddings for {total} files...")

    for i, (file_path, data) in enumerate(files.items()):
        # Create text representation
        text_parts = [
            f"File: {file_path}",
            f"Summary: {data.get('summary', '')}",
            f"Purpose: {data.get('purpose', '')}",
            f"Functions: {', '.join(f['name'] for f in data.get('functions', []))}",
            f"Hooks: {', '.join(data.get('hooks', []))}",
            f"Component: {data.get('componentName', '')}"
        ]
        text = " | ".join(filter(None, text_parts))

        if not text.strip():
            continue

        try:
            embedding = get_embedding(model, tokenizer, text)
            embeddings["files"][file_path] = {
                "embedding": embedding.tolist(),
                "text": text[:500]  # Store truncated text for reference
            }

            if (i + 1) % 20 == 0:
                print(f"  Progress: {i + 1}/{total}")
        except Exception as e:
            print(f"  Error embedding {file_path}: {e}")

    # Save embeddings
    embeddings_path.write_text(json.dumps(embeddings, indent=2))
    print(f"Saved embeddings to {embeddings_path}")

    return embeddings

def load_embeddings(project_id):
    """Load pre-computed embeddings."""
    path = MEMORY_ROOT / "projects" / project_id / "embeddings.json"
    if not path.exists():
        raise FileNotFoundError(f"Embeddings not found. Run: python semantic_search.py {project_id} build")
    return json.loads(path.read_text())

def search(project_id, query, model, tokenizer, top_k=10):
    """Search for files matching a query."""
    embeddings = load_embeddings(project_id)

    # Get query embedding
    query_embedding = get_embedding(model, tokenizer, query)

    # Calculate similarities
    results = []
    for file_path, data in embeddings.get("files", {}).items():
        file_embedding = np.array(data["embedding"])
        similarity = cosine_similarity(query_embedding, file_embedding)
        results.append({
            "file": file_path,
            "similarity": float(similarity),
            "preview": data.get("text", "")[:200]
        })

    # Sort by similarity
    results.sort(key=lambda x: x["similarity"], reverse=True)

    return results[:top_k]

def find_similar(project_id, target_file, top_k=10):
    """Find files similar to a given file."""
    embeddings = load_embeddings(project_id)

    if target_file not in embeddings.get("files", {}):
        raise ValueError(f"File not found in embeddings: {target_file}")

    target_embedding = np.array(embeddings["files"][target_file]["embedding"])

    # Calculate similarities
    results = []
    for file_path, data in embeddings.get("files", {}).items():
        if file_path == target_file:
            continue

        file_embedding = np.array(data["embedding"])
        similarity = cosine_similarity(target_embedding, file_embedding)
        results.append({
            "file": file_path,
            "similarity": float(similarity),
            "preview": data.get("text", "")[:200]
        })

    # Sort by similarity
    results.sort(key=lambda x: x["similarity"], reverse=True)

    return results[:top_k]

def main():
    parser = argparse.ArgumentParser(description="MLX Semantic Search")
    parser.add_argument("project_id", help="Project ID (e.g., 'gyst')")
    parser.add_argument("command", choices=["build", "search", "similar"],
                        help="Command to run")
    parser.add_argument("query", nargs="?", help="Search query or file path")
    parser.add_argument("--top", type=int, default=10, help="Number of results")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="MLX model")
    args = parser.parse_args()

    print(f"Loading model: {args.model}")
    model, tokenizer = load(args.model)

    if args.command == "build":
        build_embeddings(args.project_id, model, tokenizer)

    elif args.command == "search":
        if not args.query:
            print("Error: search requires a query")
            sys.exit(1)

        results = search(args.project_id, args.query, model, tokenizer, args.top)

        print(f"\nSearch results for: '{args.query}'\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r['similarity']:.3f}] {r['file']}")
            print(f"   {r['preview'][:100]}...")
            print()

    elif args.command == "similar":
        if not args.query:
            print("Error: similar requires a file path")
            sys.exit(1)

        results = find_similar(args.project_id, args.query, args.top)

        print(f"\nFiles similar to: {args.query}\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r['similarity']:.3f}] {r['file']}")
            print()

if __name__ == "__main__":
    main()
