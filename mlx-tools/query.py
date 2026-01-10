#!/usr/bin/env python3
"""
MLX Query Helper for Claude

Single command that:
1. Classifies user intent
2. Searches relevant memory files using hybrid search (BM25 + semantic)
3. Returns concise, actionable results

This is designed to be called by Claude to get quick answers
without multiple file reads.

Usage:
  python query.py <project> "user question"
  python query.py <project> "user question" --hybrid  # Force hybrid search
"""

import json
import sys
import argparse
from pathlib import Path

# Add this directory to path for imports
MLX_DIR = Path(__file__).parent
if str(MLX_DIR) not in sys.path:
    sys.path.insert(0, str(MLX_DIR))

MEMORY_ROOT = Path.home() / ".claude-dash"

# Try to import hybrid search
try:
    from hybrid_search import hybrid_search as do_hybrid_search
    HAS_HYBRID = True
except ImportError:
    HAS_HYBRID = False

# Intent patterns (no MLX needed for basic classification)
INTENTS = {
    "find_file": {
        "keywords": ["where", "find", "locate", "which file", "screen", "component", "what file"],
        "search_fields": ["summary", "purpose", "componentName"],
        "memory_files": ["summaries.json"]
    },
    "find_function": {
        "keywords": ["function", "method", "handler", "how does", "implement", "where is.*defined"],
        "search_fields": ["name"],
        "memory_files": ["functions.json"]
    },
    "understand_schema": {
        "keywords": ["collection", "database", "firestore", "field", "data", "store", "schema"],
        "search_fields": ["fields", "relationships"],
        "memory_files": ["schema.json"]
    },
    "understand_navigation": {
        "keywords": ["navigation", "navigate", "flow", "screen.*to", "route", "go to"],
        "search_fields": ["navigatesTo", "reachableFrom"],
        "memory_files": ["graph.json"]
    },
    "find_related": {
        "keywords": ["related", "similar", "like", "same as", "also use"],
        "search_fields": ["imports", "hooks"],
        "memory_files": ["graph.json", "summaries.json"]
    }
}

def classify_intent(query):
    """Classify query intent using keywords."""
    query_lower = query.lower()
    scores = {}

    for intent, data in INTENTS.items():
        score = sum(1 for kw in data["keywords"] if kw in query_lower)
        if score > 0:
            scores[intent] = score

    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]
    return "find_file"  # Default

def extract_search_terms(query):
    """Extract likely search terms from query."""
    # Remove common words
    stopwords = {"where", "is", "the", "a", "an", "how", "does", "what", "which",
                 "find", "locate", "show", "me", "can", "you", "i", "do", "for",
                 "in", "to", "from", "with", "that", "this", "are", "was", "be"}
    words = query.lower().replace("?", "").replace("'", "").split()
    terms = [w for w in words if w not in stopwords and len(w) > 2]
    return terms

def search_summaries(project_id, terms, use_hybrid=True):
    """Search summaries for matching files.

    If hybrid search is available and enabled, uses BM25 + semantic search.
    Otherwise falls back to simple keyword matching.

    Returns tuple: (results, search_mode)
    """
    # Try hybrid search first (combines BM25 + semantic)
    if use_hybrid and HAS_HYBRID:
        query = " ".join(terms)
        try:
            hybrid_results = do_hybrid_search(project_id, query, top_k=10)
            # Convert to expected format
            results = [{
                "file": r["file"],
                "score": r.get("rrf_score", r.get("score", 0)),
                "matches": [],
                "summary": r.get("summary", ""),
                "purpose": r.get("purpose", ""),
                "component": None,
                "hybrid": True,
                "bm25_rank": r.get("bm25_rank"),
                "semantic_rank": r.get("semantic_rank"),
            } for r in hybrid_results]
            return results, "hybrid"
        except Exception as e:
            # Fall back to simple search on error
            pass

    # Fallback: Simple keyword search
    path = MEMORY_ROOT / "projects" / project_id / "summaries.json"
    if not path.exists():
        return [], "keyword"

    summaries = json.loads(path.read_text())
    results = []

    for file_path, data in summaries.get("files", {}).items():
        score = 0
        matches = []

        # Search in summary, purpose, componentName
        searchable = " ".join([
            str(data.get("summary", "")),
            str(data.get("purpose", "")),
            str(data.get("componentName", "")),
            file_path
        ]).lower()

        for term in terms:
            if term in searchable:
                score += 1
                matches.append(term)

        if score > 0:
            results.append({
                "file": file_path,
                "score": score,
                "matches": matches,
                "summary": data.get("summary", ""),
                "purpose": data.get("purpose", ""),
                "component": data.get("componentName")
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:10], "keyword"

def search_functions(project_id, terms):
    """Search functions index."""
    path = MEMORY_ROOT / "projects" / project_id / "functions.json"
    if not path.exists():
        return []

    functions = json.loads(path.read_text())
    results = []

    for func_name, locations in functions.get("functions", {}).items():
        for term in terms:
            if term in func_name.lower():
                for loc in locations:
                    results.append({
                        "function": func_name,
                        "file": loc["file"],
                        "line": loc["line"],
                        "type": loc.get("type", "function")
                    })

    return results[:10]

def search_schema(project_id, terms):
    """Search schema for collections."""
    path = MEMORY_ROOT / "projects" / project_id / "schema.json"
    if not path.exists():
        return []

    schema = json.loads(path.read_text())
    results = []

    for collection_name, data in schema.get("collections", {}).items():
        score = 0

        # Check collection name
        for term in terms:
            if term in collection_name.lower():
                score += 2
            # Check fields
            for field in data.get("fields", []):
                if term in field.lower():
                    score += 1

        if score > 0 and data.get("referencedIn"):
            results.append({
                "collection": collection_name,
                "score": score,
                "fields": data.get("fields", [])[:10],
                "usedIn": data.get("referencedIn", [])[:5]
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:5]

def search_navigation(project_id, terms):
    """Search navigation graph."""
    path = MEMORY_ROOT / "projects" / project_id / "graph.json"
    if not path.exists():
        return []

    graph = json.loads(path.read_text())
    results = []

    nav = graph.get("screenNavigation", {})
    for screen_name, data in nav.items():
        for term in terms:
            if term in screen_name.lower():
                results.append({
                    "screen": screen_name,
                    "path": data.get("path"),
                    "navigatesTo": data.get("navigatesTo", []),
                    "reachableFrom": data.get("reachableFrom", [])
                })

    return results[:5]

def query(project_id, user_query):
    """Main query function."""
    intent = classify_intent(user_query)
    terms = extract_search_terms(user_query)

    result = {
        "query": user_query,
        "intent": intent,
        "searchTerms": terms,
        "results": {},
        "searchMode": "keyword"  # Default, updated by search_summaries
    }

    # Search based on intent
    if intent == "find_file":
        files, mode = search_summaries(project_id, terms)
        result["results"]["files"] = files
        result["searchMode"] = mode
    elif intent == "find_function":
        result["results"]["functions"] = search_functions(project_id, terms)
    elif intent == "understand_schema":
        result["results"]["collections"] = search_schema(project_id, terms)
    elif intent == "understand_navigation":
        result["results"]["navigation"] = search_navigation(project_id, terms)
    else:
        # Search everything
        files, mode = search_summaries(project_id, terms)
        result["results"]["files"] = files[:5]
        result["searchMode"] = mode
        result["results"]["functions"] = search_functions(project_id, terms)[:5]

    return result

def format_results(result):
    """Format results for Claude to read."""
    output = []
    output.append(f"Query: {result['query']}")
    output.append(f"Intent: {result['intent']}")
    output.append(f"Search terms: {', '.join(result['searchTerms'])}")

    # Show search mode from result
    mode = result.get("searchMode", "keyword")
    if mode == "hybrid":
        output.append("Search mode: hybrid (BM25 + semantic)")
    else:
        output.append("Search mode: keyword")
    output.append("")

    files = result["results"].get("files", [])

    if files:
        output.append("=== Files Found ===")
        for f in files[:5]:
            # Build ranking info if available
            ranking = []
            if f.get("bm25_rank"):
                ranking.append(f"keyword#{f['bm25_rank']}")
            if f.get("semantic_rank"):
                ranking.append(f"semantic#{f['semantic_rank']}")
            rank_str = f" [{', '.join(ranking)}]" if ranking else ""

            output.append(f"  {f['file']}{rank_str}")
            if f.get('purpose'):
                output.append(f"    Purpose: {f['purpose']}")
            if f.get('summary'):
                output.append(f"    Summary: {f['summary'][:100]}...")
        output.append("")

    if "functions" in result["results"] and result["results"]["functions"]:
        output.append("=== Functions Found ===")
        for f in result["results"]["functions"][:5]:
            output.append(f"  {f['function']}() at {f['file']}:{f['line']}")
        output.append("")

    if "collections" in result["results"] and result["results"]["collections"]:
        output.append("=== Collections Found ===")
        for c in result["results"]["collections"]:
            output.append(f"  {c['collection']}")
            output.append(f"    Fields: {', '.join(c['fields'][:5])}...")
            output.append(f"    Used in: {', '.join(c['usedIn'][:3])}...")
        output.append("")

    if "navigation" in result["results"] and result["results"]["navigation"]:
        output.append("=== Navigation Found ===")
        for n in result["results"]["navigation"]:
            output.append(f"  {n['screen']} ({n['path']})")
            if n.get('navigatesTo'):
                output.append(f"    Goes to: {', '.join(n['navigatesTo'][:5])}")
            if n.get('reachableFrom'):
                output.append(f"    From: {', '.join(n['reachableFrom'][:5])}")
        output.append("")

    if not any(result["results"].values()):
        output.append("No results found. Try different search terms.")

    return "\n".join(output)

def main():
    parser = argparse.ArgumentParser(description="MLX Query Helper")
    parser.add_argument("project", help="Project ID")
    parser.add_argument("query", help="User query")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    result = query(args.project, args.query)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_results(result))

if __name__ == "__main__":
    main()
