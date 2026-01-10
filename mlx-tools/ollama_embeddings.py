#!/usr/bin/env python3
"""
Ollama Embeddings - Generate embeddings using local Ollama
Uses nomic-embed-text for high-quality embeddings
"""

import json
import urllib.request
import numpy as np
from pathlib import Path
from typing import List, Dict
import sys

MEMORY_ROOT = Path.home() / '.claude-dash'
OLLAMA_URL = 'http://localhost:11434'
EMBEDDING_MODEL = 'nomic-embed-text'  # 768 dimensions, good quality


def check_model():
    """Check if embedding model is available"""
    try:
        req = urllib.request.Request(f'{OLLAMA_URL}/api/tags')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            models = [m['name'] for m in data.get('models', [])]
            return EMBEDDING_MODEL in models or f'{EMBEDDING_MODEL}:latest' in models
    except:
        return False


def pull_model():
    """Pull the embedding model"""
    print(f"Pulling {EMBEDDING_MODEL}...")
    import subprocess
    subprocess.run(['docker', 'exec', 'ollama', 'ollama', 'pull', EMBEDDING_MODEL])


def get_embedding(text: str) -> List[float]:
    """Get embedding for a single text"""
    data = json.dumps({
        'model': EMBEDDING_MODEL,
        'prompt': text[:8000]  # Truncate long texts
    }).encode()

    req = urllib.request.Request(
        f'{OLLAMA_URL}/api/embeddings',
        data=data,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result.get('embedding', [])
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return []


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors"""
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def get_files_from_db(project_id: str) -> Dict:
    """Get files from SQLite database."""
    db_path = MEMORY_ROOT / 'memory.db'
    if not db_path.exists():
        return {}

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT path, summary, purpose, component_name
        FROM files WHERE project_id = ?
    """, (project_id,))

    files = {}
    for row in cursor.fetchall():
        files[row['path']] = {
            'summary': row['summary'] or '',
            'purpose': row['purpose'] or '',
            'componentName': row['component_name']
        }

    conn.close()
    return files


def build_embeddings(project_id: str):
    """Build embeddings for a project's files"""
    # Try summaries.json first, then fall back to SQLite database
    summaries_path = MEMORY_ROOT / 'projects' / project_id / 'summaries.json'
    if summaries_path.exists():
        summaries = json.loads(summaries_path.read_text())
        files = summaries.get('files', {})
    else:
        # Fall back to SQLite database
        files = get_files_from_db(project_id)
        if not files:
            print(f"No files found for {project_id}")
            print(f"Run: mlx index-full -p {project_id}")
            return

    if not check_model():
        pull_model()

    print(f"Building embeddings for {len(files)} files...")

    embeddings = {}
    for i, (filepath, data) in enumerate(files.items()):
        # Create text representation
        text = f"{filepath}\n{data.get('summary', '')}\n{data.get('purpose', '')}"

        embedding = get_embedding(text)
        if embedding:
            embeddings[filepath] = {
                'embedding': embedding,
                'summary': data.get('summary', ''),
                'purpose': data.get('purpose', '')
            }

        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(files)} files")

    # Save embeddings
    output_path = MEMORY_ROOT / 'projects' / project_id / 'ollama_embeddings.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(embeddings, indent=2))
    print(f"Saved embeddings to {output_path}")


def search(project_id: str, query: str, top_k: int = 5) -> List[Dict]:
    """Search for similar files using embeddings"""
    embeddings_path = MEMORY_ROOT / 'projects' / project_id / 'ollama_embeddings.json'

    if not embeddings_path.exists():
        print(f"No embeddings found. Run: mlx ollama-embed build {project_id}")
        return []

    embeddings = json.loads(embeddings_path.read_text())

    # Get query embedding
    query_embedding = get_embedding(query)
    if not query_embedding:
        return []

    # Calculate similarities
    results = []
    for filepath, data in embeddings.items():
        similarity = cosine_similarity(query_embedding, data['embedding'])
        results.append({
            'file': filepath,
            'score': similarity,
            'summary': data.get('summary', ''),
            'purpose': data.get('purpose', '')
        })

    # Sort by similarity
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_k]


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  mlx ollama-embed build <project>     # Build embeddings")
        print("  mlx ollama-embed search <project> <query>  # Search")
        sys.exit(1)

    command = sys.argv[1]

    if command == 'build':
        if len(sys.argv) < 3:
            print("Usage: mlx ollama-embed build <project>")
            sys.exit(1)
        build_embeddings(sys.argv[2])

    elif command == 'search':
        if len(sys.argv) < 4:
            print("Usage: mlx ollama-embed search <project> <query>")
            sys.exit(1)
        project = sys.argv[2]
        query = ' '.join(sys.argv[3:])

        results = search(project, query)
        if results:
            print(f"\nTop matches for: {query}\n")
            for r in results:
                score_pct = int(r['score'] * 100)
                print(f"[{score_pct}%] {r['file']}")
                if r['summary']:
                    print(f"     {r['summary'][:80]}")
                print()
        else:
            print("No results found")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
