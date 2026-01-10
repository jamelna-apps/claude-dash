#!/usr/bin/env python3
"""
MLX Embeddings V2 - Using dedicated embedding model

Uses Qwen3-Embedding for much better semantic search than LLM embeddings.
10x better similarity matching for finding related code.

Setup:
  pip install sentence-transformers
  # Model downloads automatically on first use

Usage:
  python embeddings_v2.py <project> build    # Build embeddings
  python embeddings_v2.py <project> search "query"
  python embeddings_v2.py <project> similar <file>
"""

import json
import sys
import argparse
import numpy as np
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"

# Try to use sentence-transformers (better) or fall back to mlx
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # Fast, good quality, 80MB
    USE_SENTENCE_TRANSFORMERS = True
except ImportError:
    USE_SENTENCE_TRANSFORMERS = False
    print("Note: Install sentence-transformers for better embeddings")
    print("  pip install sentence-transformers")

def get_model():
    """Load the embedding model."""
    if USE_SENTENCE_TRANSFORMERS:
        return SentenceTransformer(EMBEDDING_MODEL)
    else:
        # Fallback to MLX LLM embeddings
        from mlx_lm import load
        return load("mlx-community/Llama-3.2-3B-Instruct-4bit")

def get_embedding(model, text):
    """Get embedding for text."""
    if USE_SENTENCE_TRANSFORMERS:
        return model.encode(text, normalize_embeddings=True)
    else:
        # MLX fallback (less accurate)
        import mlx.core as mx
        model_obj, tokenizer = model
        tokens = tokenizer.encode(text[:512])
        input_ids = mx.array([tokens])
        embeddings = model_obj.model.embed_tokens(input_ids)
        embedding = mx.mean(embeddings, axis=1).squeeze()
        return np.array(embedding.tolist())

def get_batch_embeddings(model, texts):
    """Get embeddings for multiple texts at once (much faster)."""
    if USE_SENTENCE_TRANSFORMERS:
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    else:
        return [get_embedding(model, t) for t in texts]

def cosine_similarity(a, b):
    """Compute cosine similarity."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)

def build_embeddings(project_id, model):
    """Build embeddings for all file summaries."""
    summaries_path = MEMORY_ROOT / "projects" / project_id / "summaries.json"
    embeddings_path = MEMORY_ROOT / "projects" / project_id / "embeddings_v2.json"

    summaries = json.loads(summaries_path.read_text())

    # Prepare texts
    file_paths = []
    texts = []

    for file_path, data in summaries.get("files", {}).items():
        text_parts = [
            f"File: {file_path}",
            f"Summary: {data.get('summary', '')}",
            f"Purpose: {data.get('purpose', '')}",
            f"Functions: {', '.join(f['name'] for f in data.get('functions', []))}",
            f"Hooks: {', '.join(data.get('hooks', []))}",
        ]
        text = " | ".join(filter(None, text_parts))

        if text.strip():
            file_paths.append(file_path)
            texts.append(text[:1000])  # Limit length

    print(f"Building embeddings for {len(texts)} files...")

    # Batch encode (much faster)
    embeddings_array = get_batch_embeddings(model, texts)

    # Save
    embeddings = {
        "version": "2.0",
        "model": EMBEDDING_MODEL if USE_SENTENCE_TRANSFORMERS else "mlx-llm",
        "project": project_id,
        "files": {}
    }

    for i, file_path in enumerate(file_paths):
        embeddings["files"][file_path] = {
            "embedding": embeddings_array[i].tolist(),
            "text": texts[i][:300]
        }

    embeddings_path.write_text(json.dumps(embeddings))
    print(f"Saved to {embeddings_path}")

    return embeddings

def load_embeddings(project_id):
    """Load embeddings, prefer v2."""
    v2_path = MEMORY_ROOT / "projects" / project_id / "embeddings_v2.json"
    v1_path = MEMORY_ROOT / "projects" / project_id / "embeddings.json"

    if v2_path.exists():
        return json.loads(v2_path.read_text())
    elif v1_path.exists():
        return json.loads(v1_path.read_text())
    else:
        raise FileNotFoundError(f"No embeddings found. Run: python embeddings_v2.py {project_id} build")

def search(project_id, query, model, top_k=10):
    """Search for files matching query."""
    embeddings = load_embeddings(project_id)
    query_embedding = get_embedding(model, query)

    results = []
    for file_path, data in embeddings.get("files", {}).items():
        file_embedding = np.array(data["embedding"])
        similarity = cosine_similarity(query_embedding, file_embedding)
        results.append({
            "file": file_path,
            "similarity": float(similarity),
            "preview": data.get("text", "")[:150]
        })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]

def find_similar(project_id, target_file, top_k=10):
    """Find files similar to target."""
    embeddings = load_embeddings(project_id)

    if target_file not in embeddings.get("files", {}):
        raise ValueError(f"File not in embeddings: {target_file}")

    target_embedding = np.array(embeddings["files"][target_file]["embedding"])

    results = []
    for file_path, data in embeddings.get("files", {}).items():
        if file_path == target_file:
            continue
        file_embedding = np.array(data["embedding"])
        similarity = cosine_similarity(target_embedding, file_embedding)
        results.append({
            "file": file_path,
            "similarity": float(similarity)
        })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", help="Project ID")
    parser.add_argument("command", choices=["build", "search", "similar"])
    parser.add_argument("query", nargs="?", help="Search query or file path")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not args.json:
        print(f"Loading model...", file=sys.stderr)
    model = get_model()

    if args.command == "build":
        build_embeddings(args.project, model)

    elif args.command == "search":
        if not args.query:
            if args.json:
                print(json.dumps({"error": "search requires a query"}))
            else:
                print("Error: search requires a query")
            sys.exit(1)

        results = search(args.project, args.query, model, args.top)

        if args.json:
            print(json.dumps({"results": results}))
        else:
            print(f"\nResults for: '{args.query}'\n")
            for i, r in enumerate(results, 1):
                print(f"{i}. [{r['similarity']:.3f}] {r['file']}")
                print(f"   {r['preview']}...")
                print()

    elif args.command == "similar":
        if not args.query:
            if args.json:
                print(json.dumps({"error": "similar requires a file path"}))
            else:
                print("Error: similar requires a file path")
            sys.exit(1)

        try:
            results = find_similar(args.project, args.query, args.top)
            if args.json:
                print(json.dumps({"results": results}))
            else:
                print(f"\nFiles similar to: {args.query}\n")
                for i, r in enumerate(results, 1):
                    print(f"{i}. [{r['similarity']:.3f}] {r['file']}")
        except ValueError as e:
            if args.json:
                print(json.dumps({"error": str(e)}))
            else:
                print(f"Error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
