#!/usr/bin/env python3
"""
Ollama Embeddings Builder for Claude-Dash

Builds embeddings for project files using Ollama's embedding model.
Used to create the embeddings file that HNSW index builds from.

Usage:
  python ollama_embeddings.py build <project>    # Build embeddings
  python ollama_embeddings.py search <project> <query>  # Semantic search
  python ollama_embeddings.py status <project>   # Check embedding status
"""

import json
import argparse
import urllib.request
import urllib.error
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

MEMORY_ROOT = Path.home() / ".claude-dash"
OLLAMA_URL = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"

# File extensions to embed
EMBEDDABLE_EXTENSIONS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.swift', '.kt', '.java',
    '.go', '.rs', '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php',
    '.vue', '.svelte', '.html', '.css', '.scss', '.json', '.yaml',
    '.yml', '.md', '.txt', '.sh', '.bash', '.zsh', '.sql'
}


def get_ollama_embedding(text: str, model: str = EMBEDDING_MODEL) -> Optional[List[float]]:
    """Get embedding from Ollama."""
    try:
        data = json.dumps({
            "model": model,
            "prompt": text[:8000]  # Truncate for safety
        }).encode('utf-8')

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/embeddings",
            data=data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode())
            return result.get("embedding")
    except urllib.error.URLError as e:
        print(f"  Ollama error: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  Error: {e}", file=sys.stderr)
        return None


def check_ollama() -> bool:
    """Check if Ollama is running and has embedding model."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
            if EMBEDDING_MODEL.split(":")[0] not in models:
                print(f"Warning: Embedding model '{EMBEDDING_MODEL}' not found.")
                print(f"Available models: {models}")
                print(f"Install with: ollama pull {EMBEDDING_MODEL}")
                return False
            return True
    except:
        print("Error: Ollama not running. Start with: ollama serve")
        return False


def get_project_config(project_id: str) -> Optional[Dict]:
    """Get project configuration."""
    config_path = MEMORY_ROOT / "config.json"
    if not config_path.exists():
        return None

    config = json.loads(config_path.read_text())
    for project in config.get("projects", []):
        if project.get("id") == project_id:
            return project
    return None


def get_project_files(project_path: Path, max_files: int = 500) -> List[Path]:
    """Get embeddable files from project."""
    files = []

    # Directories to skip
    skip_dirs = {
        'node_modules', '.git', 'dist', 'build', '.next', '.expo',
        'ios', 'android', 'Pods', '__pycache__', '.venv', 'venv',
        'coverage', '.vercel', '.turbo', '.cache'
    }

    for item in project_path.rglob('*'):
        if item.is_file():
            # Skip if in excluded directory
            if any(skip in item.parts for skip in skip_dirs):
                continue

            # Check extension
            if item.suffix.lower() in EMBEDDABLE_EXTENSIONS:
                files.append(item)

            if len(files) >= max_files:
                break

    return files


def read_file_content(file_path: Path, max_chars: int = 8000) -> str:
    """Read file content for embedding."""
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        return content[:max_chars]
    except:
        return ""


def build_embeddings(project_id: str, force: bool = False) -> bool:
    """Build embeddings for a project."""
    project_config = get_project_config(project_id)
    if not project_config:
        print(f"Error: Project '{project_id}' not found in config.json")
        return False

    project_path = Path(project_config.get("path", ""))
    if not project_path.exists():
        print(f"Error: Project path not found: {project_path}")
        return False

    project_dir = MEMORY_ROOT / "projects" / project_id
    embeddings_path = project_dir / "embeddings_v2.json"

    # Check if embeddings already exist
    if embeddings_path.exists() and not force:
        data = json.loads(embeddings_path.read_text())
        file_count = len(data.get("files", {}))
        print(f"Embeddings already exist for {project_id}: {file_count} files")
        print("Use --force to rebuild")
        return True

    # Check Ollama
    if not check_ollama():
        return False

    print(f"Building embeddings for {project_id}...")
    print(f"Project path: {project_path}")

    # Get files
    files = get_project_files(project_path)
    print(f"Found {len(files)} embeddable files")

    if not files:
        print("No files to embed")
        return False

    # Build embeddings
    embeddings_data = {
        "version": "2.0",
        "model": EMBEDDING_MODEL,
        "project": project_id,
        "created_at": datetime.now().isoformat(),
        "files": {}
    }

    dim = None
    success = 0
    failed = 0

    for i, file_path in enumerate(files):
        rel_path = str(file_path.relative_to(project_path))
        content = read_file_content(file_path)

        if not content.strip():
            continue

        print(f"  [{i+1}/{len(files)}] {rel_path}...", end=" ", flush=True)

        embedding = get_ollama_embedding(content)

        if embedding:
            embeddings_data["files"][rel_path] = {
                "embedding": embedding,
                "chars": len(content)
            }
            if dim is None:
                dim = len(embedding)
            success += 1
            print("OK")
        else:
            failed += 1
            print("FAILED")

    # Save embeddings
    if success > 0:
        embeddings_data["dim"] = dim
        embeddings_data["file_count"] = success

        project_dir.mkdir(parents=True, exist_ok=True)
        embeddings_path.write_text(json.dumps(embeddings_data, indent=2))

        print(f"\nSaved embeddings: {embeddings_path}")
        print(f"  Files: {success} embedded, {failed} failed")
        print(f"  Dimension: {dim}")

        # Trigger HNSW index rebuild
        print("\nBuilding HNSW index...")
        try:
            import subprocess
            venv_python = MEMORY_ROOT / "venv" / "bin" / "python"
            if venv_python.exists():
                subprocess.run([
                    str(venv_python),
                    str(MEMORY_ROOT / "mlx-tools" / "hnsw_index.py"),
                    "build", project_id
                ], check=True)
            else:
                subprocess.run([
                    "python3",
                    str(MEMORY_ROOT / "mlx-tools" / "hnsw_index.py"),
                    "build", project_id
                ], check=True)
        except Exception as e:
            print(f"Warning: HNSW build failed: {e}")

        return True
    else:
        print("No embeddings created")
        return False


def search_embeddings(project_id: str, query: str, top_k: int = 10) -> List[Dict]:
    """Search project using embeddings."""
    project_dir = MEMORY_ROOT / "projects" / project_id
    embeddings_path = project_dir / "embeddings_v2.json"

    if not embeddings_path.exists():
        print(f"No embeddings found. Run: python ollama_embeddings.py build {project_id}")
        return []

    # Get query embedding
    query_embedding = get_ollama_embedding(query)
    if not query_embedding:
        print("Failed to get query embedding")
        return []

    # Load embeddings
    data = json.loads(embeddings_path.read_text())
    files = data.get("files", {})

    # Calculate similarities
    def cosine_sim(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0
        return dot / (norm_a * norm_b)

    results = []
    for file_path, file_data in files.items():
        embedding = file_data.get("embedding", [])
        if embedding:
            score = cosine_sim(query_embedding, embedding)
            results.append({
                "file": file_path,
                "score": score
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


def status_embeddings(project_id: str):
    """Show embedding status for a project."""
    project_dir = MEMORY_ROOT / "projects" / project_id
    embeddings_path = project_dir / "embeddings_v2.json"

    if not embeddings_path.exists():
        print(f"No embeddings found for {project_id}")
        print(f"Run: python ollama_embeddings.py build {project_id}")
        return

    data = json.loads(embeddings_path.read_text())

    print(f"Project: {project_id}")
    print(f"Model: {data.get('model', 'unknown')}")
    print(f"Files: {data.get('file_count', len(data.get('files', {})))}")
    print(f"Dimension: {data.get('dim', 'unknown')}")
    print(f"Created: {data.get('created_at', 'unknown')}")


def main():
    parser = argparse.ArgumentParser(description="Ollama embeddings builder")
    parser.add_argument("command", choices=["build", "search", "status"],
                        help="Command to run")
    parser.add_argument("project", help="Project ID")
    parser.add_argument("query", nargs="?", help="Search query (for search command)")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Force rebuild embeddings")
    parser.add_argument("--top-k", "-k", type=int, default=10,
                        help="Number of results for search")

    args = parser.parse_args()

    if args.command == "build":
        success = build_embeddings(args.project, force=args.force)
        sys.exit(0 if success else 1)

    elif args.command == "search":
        if not args.query:
            print("Error: Search requires a query")
            sys.exit(1)

        results = search_embeddings(args.project, args.query, args.top_k)

        if results:
            print(f"\nTop {len(results)} results for '{args.query}':\n")
            for i, r in enumerate(results, 1):
                print(f"  {i}. {r['file']} (score: {r['score']:.4f})")
        else:
            print("No results found")

    elif args.command == "status":
        status_embeddings(args.project)


if __name__ == "__main__":
    main()
