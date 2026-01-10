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


def load_ollama_embeddings(project_id: str) -> Optional[Dict]:
    """Load pre-computed Ollama embeddings if available"""
    embeddings_path = MEMORY_ROOT / 'projects' / project_id / 'ollama_embeddings.json'

    if embeddings_path.exists():
        return json.loads(embeddings_path.read_text())
    return None


def search_embeddings(project_id: str, query: str, top_k: int = 10) -> List[Dict]:
    """Search using Ollama embeddings (semantic)"""
    try:
        from ollama_embeddings import search
        return search(project_id, query, top_k)
    except Exception as e:
        # Embeddings not available
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

    Args:
        project_id: Project identifier
        query: Search query
        top_k: Number of results to return

    Returns:
        List of results with RRF scores
    """
    # Get more results from each source for better merging
    fetch_k = top_k * 2

    # BM25 search
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
        print("Usage: python hybrid_search.py <project> <query>")
        print("\nPerforms hybrid BM25 + semantic search")
        sys.exit(1)

    project_id = sys.argv[1]
    query = ' '.join(sys.argv[2:])

    results = hybrid_search(project_id, query)
    print(format_results(results, query))


if __name__ == '__main__':
    main()
