#!/usr/bin/env python3
"""
RAG Pipeline - Retrieval-Augmented Generation for codebase Q&A
Combines semantic search with LLM generation for accurate answers
"""

import json
import urllib.request
import sys
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

try:
    from config import OLLAMA_URL, OLLAMA_EMBED_MODEL as EMBEDDING_MODEL, MEMORY_ROOT, cosine_similarity
    from ollama_client import OllamaClient
    from hybrid_search import hybrid_search as _hybrid_search
    HAS_HYBRID = True
except ImportError:
    HAS_HYBRID = False
    _hybrid_search = None
    import math
    MEMORY_ROOT = Path.home() / '.claude-dash'
    OLLAMA_URL = 'http://localhost:11434'
    EMBEDDING_MODEL = 'nomic-embed-text'

    def cosine_similarity(vec1: list, vec2: list) -> float:
        """Fallback cosine similarity."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    class OllamaClient:
        def __init__(self, **kwargs):
            pass
        def generate(self, prompt, system=None):
            return "Error: OllamaClient not available"


class RAGPipeline:
    """Retrieval-Augmented Generation for code Q&A"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_dir = MEMORY_ROOT / 'projects' / project_id
        self.embeddings = self._load_embeddings()
        self.summaries = self._load_summaries()
        self.schema = self._load_schema()
        self.functions = self._load_functions()
        # Enhanced memory metadata
        self.health = self._load_health()
        self.decisions = self._load_decisions()
        self.observations = self._load_observations()
        self.preferences = self._load_preferences()

    def _load_embeddings(self) -> Dict:
        path = self.project_dir / 'ollama_embeddings.json'
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _load_summaries(self) -> Dict:
        path = self.project_dir / 'summaries.json'
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _load_schema(self) -> Dict:
        path = self.project_dir / 'schema.json'
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _load_functions(self) -> Dict:
        path = self.project_dir / 'functions.json'
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _load_health(self) -> Dict:
        path = self.project_dir / 'health.json'
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _load_decisions(self) -> Dict:
        path = self.project_dir / 'decisions.json'
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _load_observations(self) -> Dict:
        path = self.project_dir / 'observations.json'
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _load_preferences(self) -> Dict:
        path = self.project_dir / 'preferences.json'
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text"""
        data = json.dumps({
            'model': EMBEDDING_MODEL,
            'prompt': text[:8000]
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
        except:
            return []

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity using centralized implementation."""
        return cosine_similarity(a, b)

    def retrieve(self, query: str, top_k: int = 5, use_recency: bool = True) -> List[Dict]:
        """
        Retrieve relevant context for a query.

        Uses hybrid search (BM25 + semantic) when available, with optional
        recency weighting to boost recently modified files.
        """
        # Try hybrid search first (best quality)
        if HAS_HYBRID and _hybrid_search:
            try:
                results = _hybrid_search(self.project_id, query, top_k * 2)
                if results:
                    # Apply recency weighting if enabled
                    if use_recency:
                        results = self._apply_recency_weight(results)
                    return results[:top_k]
            except Exception as e:
                print(f"Hybrid search failed, falling back: {e}", file=sys.stderr)

        # Fallback to semantic-only search
        if not self.embeddings:
            return self._keyword_search(query, top_k)

        query_embedding = self._get_embedding(query)
        if not query_embedding:
            return self._keyword_search(query, top_k)

        results = []
        for filepath, data in self.embeddings.items():
            similarity = self._cosine_similarity(query_embedding, data['embedding'])
            results.append({
                'file': filepath,
                'score': similarity,
                'summary': data.get('summary', ''),
                'purpose': data.get('purpose', '')
            })

        results.sort(key=lambda x: x['score'], reverse=True)

        # Apply recency weighting
        if use_recency:
            results = self._apply_recency_weight(results)

        return results[:top_k]

    def _apply_recency_weight(self, results: List[Dict], decay_days: int = 30) -> List[Dict]:
        """
        Apply recency weighting to boost recently modified files.

        Files modified in the last `decay_days` get a boost that decays over time.
        Max boost: 20% for files modified today, decaying to 0% after decay_days.
        """
        # Get project root from config
        try:
            config_path = MEMORY_ROOT / 'config.json'
            if config_path.exists():
                config = json.loads(config_path.read_text())
                project_info = next((p for p in config.get('projects', [])
                                   if p['id'] == self.project_id), None)
                if project_info:
                    project_root = Path(project_info.get('path', ''))
                else:
                    return results
            else:
                return results
        except Exception:
            return results

        now = datetime.now()

        for result in results:
            filepath = result['file']
            full_path = project_root / filepath

            try:
                if full_path.exists():
                    mtime = datetime.fromtimestamp(full_path.stat().st_mtime)
                    days_old = (now - mtime).days

                    if days_old < decay_days:
                        # Linear decay: 20% boost at day 0, 0% at decay_days
                        recency_boost = 0.2 * (1 - days_old / decay_days)
                        original_score = result.get('score', 0) or result.get('rrf_score', 0)
                        result['score'] = original_score * (1 + recency_boost)
                        result['recency_days'] = days_old
            except Exception:
                pass

        # Re-sort by updated scores
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return results

    def _keyword_search(self, query: str, top_k: int) -> List[Dict]:
        """Fallback keyword search"""
        query_lower = query.lower()
        keywords = query_lower.split()

        results = []
        files = self.summaries.get('files', {})

        for filepath, data in files.items():
            text = f"{filepath} {data.get('summary', '')} {data.get('purpose', '')}".lower()
            score = sum(1 for kw in keywords if kw in text) / len(keywords)
            if score > 0:
                results.append({
                    'file': filepath,
                    'score': score,
                    'summary': data.get('summary', ''),
                    'purpose': data.get('purpose', '')
                })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]

    def get_context(self, query: str) -> str:
        """Build context string for LLM with full memory metadata"""
        retrieved = self.retrieve(query)
        query_lower = query.lower()

        context_parts = []

        # Add health context if query mentions health, score, quality, issues
        health_keywords = ['health', 'score', 'quality', 'issue', 'problem', 'bug', 'security', 'performance', 'dead code', 'duplicate']
        if any(kw in query_lower for kw in health_keywords):
            if self.health:
                context_parts.append("## Code Health Status")
                context_parts.append(f"Score: {self.health.get('score', 'N/A')}/100")
                context_parts.append(f"Last scan: {self.health.get('timestamp', 'unknown')}")
                summary = self.health.get('summary', {})
                context_parts.append(f"Issues: Security={summary.get('security', 0)}, Performance={summary.get('performance', 0)}, Duplicates={summary.get('duplicates', 0)}, Dead code={summary.get('dead_code', 0)}")

                # Score interpretation
                score = self.health.get('score', 0)
                if score >= 90:
                    rating = "Excellent - clean, well-maintained"
                elif score >= 75:
                    rating = "Good - minor issues"
                elif score >= 60:
                    rating = "Fair - needs attention"
                elif score >= 40:
                    rating = "Poor - significant tech debt"
                else:
                    rating = "Critical - major refactoring needed"
                context_parts.append(f"Rating: {rating}")

                # Add specific issues if available
                issues = self.health.get('issues', {})
                if issues.get('security'):
                    context_parts.append(f"\nSecurity Issues: {json.dumps(issues['security'][:3])}")
                if issues.get('performance'):
                    context_parts.append(f"\nPerformance Issues: {json.dumps(issues['performance'][:3])}")
                if issues.get('dead_code'):
                    context_parts.append(f"\nDead Code (sample): {json.dumps(issues['dead_code'][:5])}")

        # Add retrieved files
        context_parts.append("\n## Relevant Files")
        for r in retrieved:
            context_parts.append(f"\n### {r['file']}")
            if r['summary']:
                context_parts.append(f"Summary: {r['summary']}")
            if r['purpose']:
                context_parts.append(f"Purpose: {r['purpose']}")

        # Add schema context if query seems data-related
        data_keywords = ['database', 'collection', 'store', 'save', 'user', 'data', 'schema']
        if any(kw in query_lower for kw in data_keywords):
            if self.schema.get('collections'):
                context_parts.append("\n## Database Schema")
                for name, info in list(self.schema['collections'].items())[:5]:
                    fields = info.get('fields', [])
                    # Handle both list and dict formats
                    if isinstance(fields, dict):
                        field_names = list(fields.keys())[:10]
                    else:
                        field_names = fields[:10] if isinstance(fields, list) else []
                    context_parts.append(f"- {name}: {', '.join(field_names)}")

        # Add relevant functions
        func_keywords = ['function', 'method', 'how does', 'implement', 'call']
        if any(kw in query_lower for kw in func_keywords):
            functions = self.functions.get('functions', {})
            if functions:
                context_parts.append("\n## Relevant Functions")
                # Handle both dict and list formats
                if isinstance(functions, dict):
                    # New format: {func_name: [{file, line, ...}, ...]}
                    matching = []
                    for func_name, occurrences in functions.items():
                        if any(kw in func_name.lower() for kw in query_lower.split()):
                            if occurrences and isinstance(occurrences, list):
                                first = occurrences[0]
                                matching.append({
                                    'name': func_name,
                                    'file': first.get('file', 'unknown'),
                                    'line': first.get('line', '?')
                                })
                    for func in matching[:10]:
                        context_parts.append(f"- {func['name']} in {func['file']}:{func['line']}")
                elif isinstance(functions, list):
                    # Old format: [{name, file, line, ...}, ...]
                    matching = []
                    for func in functions[:100]:
                        name = func.get('name', '').lower()
                        if any(kw in name for kw in query_lower.split()):
                            matching.append(func)
                    for func in matching[:10]:
                        context_parts.append(f"- {func['name']} in {func.get('file', 'unknown')}:{func.get('line', '?')}")

        # Add decisions context
        decision_keywords = ['decision', 'why', 'chose', 'architecture', 'pattern', 'approach']
        if any(kw in query_lower for kw in decision_keywords):
            decisions = self.decisions.get('decisions', [])
            if decisions:
                context_parts.append("\n## Architectural Decisions")
                for dec in decisions[:5]:
                    context_parts.append(f"- {dec.get('title', 'Untitled')}: {dec.get('decision', 'No details')}")
                    if dec.get('context'):
                        context_parts.append(f"  Context: {dec.get('context')}")

        # Add observations context
        obs_keywords = ['bug', 'fix', 'issue', 'pattern', 'learned', 'gotcha', 'problem']
        if any(kw in query_lower for kw in obs_keywords):
            observations = self.observations.get('observations', [])
            if observations:
                context_parts.append("\n## Past Observations")
                for obs in observations[:5]:
                    context_parts.append(f"- [{obs.get('category', 'note')}] {obs.get('description', 'No description')}")
                    if obs.get('resolution'):
                        context_parts.append(f"  Resolution: {obs.get('resolution')}")

        # Add preferences context
        pref_keywords = ['convention', 'rule', 'preference', 'style', 'standard', 'should']
        if any(kw in query_lower for kw in pref_keywords):
            conventions = self.preferences.get('conventions', [])
            if conventions:
                context_parts.append("\n## Project Conventions")
                for conv in conventions[:5]:
                    context_parts.append(f"- {conv.get('name', 'Unnamed')}: {conv.get('rule', 'No rule')}")

        return '\n'.join(context_parts)

    def generate(self, query: str, context: str) -> str:
        """Generate answer using LLM with task-based routing"""
        # Initialize client with task='rag' for automatic model selection
        client = OllamaClient(task='rag')

        system_prompt = "You are a helpful assistant answering questions about a codebase. Use ONLY the context provided below to answer. If the answer isn't in the context, say so."

        prompt = f"""{context}

---

Question: {query}

Answer concisely and specifically. Reference file paths when relevant."""

        try:
            response = client.generate(prompt, system=system_prompt)
            return response if response else "No response generated"
        except Exception as e:
            return f"Error: {e}"

    def query(self, question: str, verbose: bool = False) -> str:
        """Full RAG pipeline: retrieve + generate"""
        context = self.get_context(question)

        if verbose:
            print("=== Retrieved Context ===")
            print(context[:1000])
            print("...\n")

        return self.generate(question, context)


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  mlx rag <project> <question>         # Ask a question")
        print("  mlx rag <project> -v <question>      # Verbose (show context)")
        print("")
        print("Examples:")
        print("  mlx rag gyst 'how does authentication work?'")
        print("  mlx rag gyst -v 'where is user data stored?'")
        sys.exit(1)

    project = sys.argv[1]
    verbose = '-v' in sys.argv

    if verbose:
        question = ' '.join([a for a in sys.argv[2:] if a != '-v'])
    else:
        question = ' '.join(sys.argv[2:])

    print(f"Project: {project}")
    print(f"Question: {question}")
    print("---")

    pipeline = RAGPipeline(project)
    answer = pipeline.query(question, verbose=verbose)

    print(answer)


if __name__ == '__main__':
    main()
