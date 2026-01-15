#!/usr/bin/env python3
"""
Hybrid Search for Claude Memory
Combines BM25 (keyword) + Ollama Embeddings (semantic) using RRF

Improves query accuracy by catching both:
- Exact matches (function names, acronyms, specific terms)
- Semantic matches (conceptually similar content)
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import sys

# Try to import rank_bm25, fall back to simple keyword if not available
try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False
    print("Warning: rank_bm25 not installed. Using simple keyword search.", file=sys.stderr)
    print("Install with: pip install rank-bm25", file=sys.stderr)

MEMORY_ROOT = Path.home() / '.claude-dash'

# Try to import SQLite for FTS5 search
try:
    from memory_db import get_connection
    HAS_SQLITE = True
except ImportError:
    HAS_SQLITE = False


def fts5_search(project_id: str, query: str, top_k: int = 20) -> List[Dict]:
    """Fast FTS5 search using SQLite (preferred over in-memory BM25)."""
    if not HAS_SQLITE:
        return []

    try:
        conn = get_connection()
        # FTS5 with BM25 ranking
        cursor = conn.execute("""
            SELECT f.path, f.summary, f.purpose, bm25(files_fts) as score
            FROM files_fts
            JOIN files f ON files_fts.rowid = f.id
            WHERE files_fts MATCH ? AND f.project_id = ?
            ORDER BY score
            LIMIT ?
        """, (query, project_id, top_k))

        results = []
        for row in cursor.fetchall():
            results.append({
                'file': row[0],
                'summary': row[1] or '',
                'purpose': row[2] or '',
                'score': abs(row[3]) if row[3] else 0  # BM25 returns negative scores
            })

        conn.close()
        return results
    except Exception as e:
        # Log error but don't fail - caller can fall back to in-memory BM25
        print(f"FTS5 search error: {type(e).__name__}: {e}", file=sys.stderr)
        return []


def tokenize(text: str) -> List[str]:
    """Simple tokenization for BM25"""
    # Lowercase and split on non-alphanumeric
    text = text.lower()
    tokens = re.findall(r'\b\w+\b', text)
    return tokens


class ProjectBM25Index:
    """BM25 index for a project's files"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.corpus: List[List[str]] = []
        self.file_paths: List[str] = []
        self.file_data: Dict[str, Dict] = {}
        self.bm25: Optional[BM25Okapi] = None
        self._build_index()

    def _build_index(self):
        """Build BM25 index from summaries.json"""
        summaries_path = MEMORY_ROOT / 'projects' / self.project_id / 'summaries.json'

        if not summaries_path.exists():
            return

        summaries = json.loads(summaries_path.read_text())
        files = summaries.get('files', {})

        for filepath, data in files.items():
            # Create searchable text (handle None values)
            text = ' '.join(filter(None, [
                filepath,
                data.get('summary', ''),
                data.get('purpose', ''),
                data.get('componentName'),
            ]))

            tokens = tokenize(text)
            self.corpus.append(tokens)
            self.file_paths.append(filepath)
            self.file_data[filepath] = data

        if self.corpus and HAS_BM25:
            self.bm25 = BM25Okapi(self.corpus)

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """Search using BM25"""
        if not self.corpus:
            return []

        query_tokens = tokenize(query)

        if HAS_BM25 and self.bm25:
            # Use BM25 scoring
            scores = self.bm25.get_scores(query_tokens)

            # Get top results
            scored_results = list(zip(self.file_paths, scores))
            scored_results.sort(key=lambda x: x[1], reverse=True)

            results = []
            for filepath, score in scored_results[:top_k]:
                if score > 0:
                    data = self.file_data[filepath]
                    results.append({
                        'file': filepath,
                        'score': float(score),
                        'summary': data.get('summary', ''),
                        'purpose': data.get('purpose', ''),
                    })

            return results
        else:
            # Fallback to simple keyword matching
            return self._simple_keyword_search(query_tokens, top_k)

    def _simple_keyword_search(self, query_tokens: List[str], top_k: int) -> List[Dict]:
        """Fallback keyword search when rank_bm25 not available"""
        results = []
        query_set = set(query_tokens)

        for filepath, tokens in zip(self.file_paths, self.corpus):
            # Count matching tokens
            matches = len(query_set & set(tokens))
            if matches > 0:
                data = self.file_data[filepath]
                results.append({
                    'file': filepath,
                    'score': float(matches),
                    'summary': data.get('summary', ''),
                    'purpose': data.get('purpose', ''),
                })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]


def load_embeddings_index(project_id: str) -> Optional[Dict]:
    """Load pre-computed embeddings if available (v2 preferred)"""
    # Try embeddings_v2 first (newer format)
    v2_path = MEMORY_ROOT / 'projects' / project_id / 'embeddings_v2.json'
    if v2_path.exists():
        return json.loads(v2_path.read_text())

    # Fall back to legacy ollama format
    legacy_path = MEMORY_ROOT / 'projects' / project_id / 'ollama_embeddings.json'
    if legacy_path.exists():
        return json.loads(legacy_path.read_text())

    return None


def search_embeddings(project_id: str, query: str, top_k: int = 10) -> List[Dict]:
    """Search using embeddings (semantic) - uses unified provider"""
    try:
        # Use new unified embeddings provider
        from embeddings import get_provider, similarity
        import numpy as np

        provider = get_provider()
        embeddings_data = load_embeddings_index(project_id)

        if not embeddings_data:
            return []

        # Get query embedding
        query_vec = provider.embed_single(query)

        # Search through indexed files
        files = embeddings_data.get('files', {})
        results = []

        for filepath, file_data in files.items():
            if 'embedding' not in file_data:
                continue

            file_vec = np.array(file_data['embedding'])
            score = similarity(query_vec, file_vec)

            results.append({
                'file': filepath,
                'score': score,
                'summary': file_data.get('summary', ''),
                'purpose': file_data.get('purpose', '')
            })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    except ImportError as e:
        # Missing dependency - log once and return empty
        print(f"Semantic search unavailable (missing module): {e}", file=sys.stderr)
        return []
    except Exception as e:
        # Log the error for debugging - semantic search is optional
        print(f"Semantic search error: {type(e).__name__}: {e}", file=sys.stderr)
        return []


def reciprocal_rank_fusion(
    bm25_results: List[Dict],
    semantic_results: List[Dict],
    k: int = 60
) -> List[Dict]:
    """
    Combine results using Reciprocal Rank Fusion (RRF)

    RRF(d) = sum(1 / (k + rank(d)))

    Args:
        bm25_results: Results from BM25 search
        semantic_results: Results from semantic/embedding search
        k: RRF constant (default 60, works well empirically)

    Returns:
        Merged results sorted by RRF score
    """
    score_map: Dict[str, Dict] = {}

    # Add BM25 results
    for rank, result in enumerate(bm25_results, 1):
        filepath = result['file']
        rrf_score = 1.0 / (k + rank)

        score_map[filepath] = {
            'file': filepath,
            'rrf_score': rrf_score,
            'bm25_rank': rank,
            'summary': result.get('summary', ''),
            'purpose': result.get('purpose', ''),
        }

    # Add/merge semantic results
    for rank, result in enumerate(semantic_results, 1):
        filepath = result['file']
        rrf_contribution = 1.0 / (k + rank)

        if filepath in score_map:
            score_map[filepath]['rrf_score'] += rrf_contribution
            score_map[filepath]['semantic_rank'] = rank
        else:
            score_map[filepath] = {
                'file': filepath,
                'rrf_score': rrf_contribution,
                'semantic_rank': rank,
                'summary': result.get('summary', ''),
                'purpose': result.get('purpose', ''),
            }

    # Sort by RRF score
    results = list(score_map.values())
    results.sort(key=lambda x: x['rrf_score'], reverse=True)

    return results


def hybrid_search(project_id: str, query: str, top_k: int = 10) -> List[Dict]:
    """
    Perform hybrid search combining BM25 + semantic embeddings

    Uses FTS5 (SQLite) for fast BM25 when available, falls back to in-memory.

    Args:
        project_id: Project identifier
        query: Search query
        top_k: Number of results to return

    Returns:
        List of results with RRF scores
    """
    # Get more results from each source for better merging
    fetch_k = top_k * 2

    # BM25 search - try FTS5 first (fast), fall back to in-memory
    bm25_results = fts5_search(project_id, query, fetch_k)
    if not bm25_results:
        # Fall back to in-memory BM25
        bm25_index = ProjectBM25Index(project_id)
        bm25_results = bm25_index.search(query, fetch_k)

    # Semantic search (if embeddings available)
    semantic_results = search_embeddings(project_id, query, fetch_k)

    # If only one source has results, return those
    if not bm25_results and not semantic_results:
        return []
    if not bm25_results:
        return semantic_results[:top_k]
    if not semantic_results:
        return bm25_results[:top_k]

    # Merge using RRF
    merged = reciprocal_rank_fusion(bm25_results, semantic_results)

    return merged[:top_k]


def find_similar_files(project_id: str, file_path: str, top_k: int = 5) -> List[Dict]:
    """
    Find files similar to the given file using embeddings.

    Args:
        project_id: Project identifier
        file_path: Path to the file to find similar files for
        top_k: Number of results to return

    Returns:
        List of similar files with similarity scores
    """
    embeddings_path = MEMORY_ROOT / 'projects' / project_id / 'embeddings_v2.json'

    if not embeddings_path.exists():
        return []

    try:
        embeddings = json.loads(embeddings_path.read_text())
        files = embeddings.get('files', {})

        # Normalize the input file path
        normalized_path = file_path.replace(str(MEMORY_ROOT), '').lstrip('/')
        for key in [file_path, normalized_path, Path(file_path).name]:
            if key in files:
                file_path = key
                break

        if file_path not in files or 'embedding' not in files[file_path]:
            return []

        import numpy as np
        target_vec = np.array(files[file_path]['embedding'])

        results = []
        for filepath, file_data in files.items():
            if filepath == file_path:  # Skip the file itself
                continue
            if 'embedding' not in file_data:
                continue

            file_vec = np.array(file_data['embedding'])
            # Cosine similarity
            score = float(np.dot(target_vec, file_vec) / (np.linalg.norm(target_vec) * np.linalg.norm(file_vec)))

            results.append({
                'file': filepath,
                'score': score,
                'summary': file_data.get('summary', ''),
                'purpose': file_data.get('purpose', '')
            })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    except Exception as e:
        print(f"Error finding similar files: {e}", file=sys.stderr)
        return []


def format_similar_results(results: List[Dict], source_file: str) -> str:
    """Format similar file results for display"""
    lines = [f"Files similar to: {source_file}\n"]

    if not results:
        lines.append("No similar files found.")
        return '\n'.join(lines)

    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['file']} (similarity: {r['score']:.3f})")
        if r.get('purpose'):
            lines.append(f"   Purpose: {r['purpose']}")
        elif r.get('summary'):
            lines.append(f"   {r['summary'][:80]}...")
        lines.append("")

    return '\n'.join(lines)


def format_results(results: List[Dict], query: str) -> str:
    """Format results for display"""
    lines = [f"Hybrid search for: {query}\n"]

    if not results:
        lines.append("No results found.")
        return '\n'.join(lines)

    for i, r in enumerate(results, 1):
        sources = []
        if 'bm25_rank' in r:
            sources.append(f"keyword#{r['bm25_rank']}")
        if 'semantic_rank' in r:
            sources.append(f"semantic#{r['semantic_rank']}")

        source_str = f"[{', '.join(sources)}]" if sources else ""
        score_str = f"(RRF: {r['rrf_score']:.4f})" if 'rrf_score' in r else ""

        lines.append(f"{i}. {r['file']} {source_str} {score_str}")

        if r.get('purpose'):
            lines.append(f"   Purpose: {r['purpose']}")
        elif r.get('summary'):
            lines.append(f"   {r['summary'][:80]}...")
        lines.append("")

    return '\n'.join(lines)


def main():
    """CLI interface"""
    if len(sys.argv) < 3:
        print("Usage: python hybrid_search.py <project> <query|similar> [file_path] [--limit N]")
        print("\nModes:")
        print("  <project> <query>           - Hybrid BM25 + semantic search")
        print("  <project> similar <file>    - Find similar files")
        print("\nOptions:")
        print("  --limit N                   - Limit results (default: 10 for search, 5 for similar)")
        sys.exit(1)

    project_id = sys.argv[1]

    # Parse --limit option
    limit = None
    args = sys.argv[2:]
    if '--limit' in args:
        idx = args.index('--limit')
        if idx + 1 < len(args):
            try:
                limit = int(args[idx + 1])
            except ValueError:
                pass
            args = args[:idx] + args[idx + 2:]

    # Check for "similar" mode
    if args and args[0] == 'similar':
        if len(args) < 2:
            print("Usage: python hybrid_search.py <project> similar <file_path>")
            sys.exit(1)
        file_path = args[1]
        top_k = limit or 5
        results = find_similar_files(project_id, file_path, top_k)
        print(format_similar_results(results, file_path))
    else:
        # Search mode
        query = ' '.join(args)
        top_k = limit or 10
        results = hybrid_search(project_id, query, top_k)
        print(format_results(results, query))


if __name__ == '__main__':
    main()
