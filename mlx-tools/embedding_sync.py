#!/usr/bin/env python3
"""
Embedding Sync - Incremental embedding updates for file changes

Called by watcher.js when files are added/modified.
Updates embeddings_v2.json with new/updated file embeddings.

Usage:
    python3 embedding_sync.py <project_id> <file_path> [--delete]
"""

import json
import sys
from pathlib import Path
from typing import Optional

MEMORY_ROOT = Path.home() / '.claude-dash'

# Use the unified embedding provider
try:
    from embeddings import get_provider
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False


def get_file_content_for_embedding(file_path: str, summaries_path: Path) -> Optional[str]:
    """Get content to embed for a file (summary preferred, falls back to filename)."""
    try:
        if summaries_path.exists():
            summaries = json.loads(summaries_path.read_text())
            # Convert file path to relative
            relative_path = file_path
            for prefix in [str(Path.home()), '/']:
                if relative_path.startswith(prefix):
                    relative_path = relative_path.replace(prefix, '', 1)
                    break

            # Try to find file in summaries
            for key in [relative_path, file_path, Path(file_path).name]:
                if key in summaries.get('files', {}):
                    file_data = summaries['files'][key]
                    # Build embedding text from summary data
                    parts = []
                    if file_data.get('summary'):
                        parts.append(file_data['summary'])
                    if file_data.get('purpose'):
                        parts.append(file_data['purpose'])
                    if file_data.get('keyLogic'):
                        parts.append(file_data['keyLogic'])
                    if parts:
                        return ' '.join(parts)
    except (json.JSONDecodeError, IOError):
        pass

    # Fall back to filename
    return Path(file_path).stem.replace('_', ' ').replace('-', ' ')


def update_embedding(project_id: str, file_path: str, delete: bool = False) -> bool:
    """Update or remove embedding for a single file."""
    if not EMBEDDING_AVAILABLE:
        return False

    project_dir = MEMORY_ROOT / 'projects' / project_id
    embeddings_path = project_dir / 'embeddings_v2.json'
    summaries_path = project_dir / 'summaries.json'

    # Load existing embeddings
    embeddings = {'files': {}, 'lastUpdated': None}
    if embeddings_path.exists():
        try:
            embeddings = json.loads(embeddings_path.read_text())
        except (json.JSONDecodeError, IOError):
            pass

    # Normalize file path for key
    relative_path = file_path
    for prefix in [str(project_dir), str(Path.home()), '/']:
        if relative_path.startswith(prefix):
            relative_path = relative_path.replace(prefix, '', 1)
            if relative_path.startswith('/'):
                relative_path = relative_path[1:]
            break

    if delete:
        # Remove embedding
        if relative_path in embeddings.get('files', {}):
            del embeddings['files'][relative_path]
            embeddings['lastUpdated'] = __import__('datetime').datetime.now().isoformat()
            _atomic_write(embeddings_path, embeddings)
            return True
        return False

    # Get content for embedding
    content = get_file_content_for_embedding(file_path, summaries_path)
    if not content:
        return False

    # Generate embedding
    try:
        provider = get_provider()
        embedding = provider.embed_single(content).tolist()

        # Update embeddings file
        if 'files' not in embeddings:
            embeddings['files'] = {}

        embeddings['files'][relative_path] = {
            'embedding': embedding,
            'content_hash': hash(content),
            'updated_at': __import__('datetime').datetime.now().isoformat()
        }
        embeddings['lastUpdated'] = __import__('datetime').datetime.now().isoformat()

        _atomic_write(embeddings_path, embeddings)
        return True
    except Exception as e:
        print(f"Error generating embedding: {e}", file=sys.stderr)
        return False


def _atomic_write(file_path: Path, data: dict) -> None:
    """Write JSON atomically (write to temp, then rename)."""
    import os
    tmp_path = file_path.with_suffix('.tmp.' + str(os.getpid()))
    try:
        tmp_path.write_text(json.dumps(data, indent=2))
        tmp_path.rename(file_path)
    except Exception:
        try:
            tmp_path.unlink()
        except:
            pass
        raise


def main():
    if len(sys.argv) < 3:
        print("Usage: embedding_sync.py <project_id> <file_path> [--delete]")
        sys.exit(1)

    project_id = sys.argv[1]
    file_path = sys.argv[2]
    delete = '--delete' in sys.argv

    if not EMBEDDING_AVAILABLE:
        print("Embedding provider not available", file=sys.stderr)
        sys.exit(1)

    success = update_embedding(project_id, file_path, delete)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
