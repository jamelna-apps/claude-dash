#!/usr/bin/env python3
"""
Cross-Project Search CLI

Search across ALL indexed projects using SQLite FTS5.
Finds files, functions, or observations matching the query.

Usage:
    python cross_search.py "authentication"              # Search files
    python cross_search.py "handleLogin" --type functions
    python cross_search.py "bug fix" --type observations
    python cross_search.py "firebase" --json
"""

import sys
import json
import argparse
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from memory_db import get_connection, cross_project_search


def search_functions_all(query: str, limit: int = 20):
    """Search functions across all projects."""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT fn.name, fn.line_number, fn.type, f.path, f.project_id, p.name as project_name
        FROM functions fn
        JOIN files f ON f.id = fn.file_id
        JOIN projects p ON p.id = f.project_id
        WHERE fn.name LIKE ?
        ORDER BY fn.name
        LIMIT ?
    """, (f'%{query}%', limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def search_observations_all(query: str, limit: int = 20):
    """Search observations (session notes) across all projects."""
    conn = get_connection()
    cursor = conn.execute("""
        SELECT o.*, p.name as project_name
        FROM observations_fts
        JOIN observations o ON observations_fts.rowid = o.id
        LEFT JOIN projects p ON p.id = o.project_id
        WHERE observations_fts MATCH ?
        ORDER BY o.created_at DESC
        LIMIT ?
    """, (query, limit))

    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def format_file_results(results):
    """Format file search results for display."""
    if not results:
        return "No files found."

    lines = ["=== Files Found ==="]
    for r in results:
        lines.append(f"\n[{r.get('project_name', r.get('project_id', '?'))}] {r['path']}")
        if r.get('summary'):
            lines.append(f"  Summary: {r['summary'][:80]}...")
        if r.get('purpose'):
            lines.append(f"  Purpose: {r['purpose'][:80]}...")

    return '\n'.join(lines)


def format_function_results(results):
    """Format function search results for display."""
    if not results:
        return "No functions found."

    lines = ["=== Functions Found ==="]
    for r in results:
        project = r.get('project_name', r.get('project_id', '?'))
        lines.append(f"\n[{project}] {r['name']}() at {r['path']}:{r['line_number']}")
        lines.append(f"  Type: {r.get('type', 'function')}")

    return '\n'.join(lines)


def format_observation_results(results):
    """Format observation search results for display."""
    if not results:
        return "No observations found."

    lines = ["=== Observations Found ==="]
    for r in results:
        project = r.get('project_name', r.get('project_id', 'global'))
        category = r.get('category', 'note')
        lines.append(f"\n[{project}] [{category}] {r.get('title', 'Untitled')}")
        if r.get('content'):
            lines.append(f"  {r['content'][:100]}...")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Search across all projects",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "--type", "-t",
        choices=["files", "functions", "observations"],
        default="files",
        help="What to search (default: files)"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=20,
        help="Max results (default: 20)"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    args = parser.parse_args()

    # Perform search based on type
    if args.type == "files":
        results = cross_project_search(args.query, args.limit)
        formatter = format_file_results
    elif args.type == "functions":
        results = search_functions_all(args.query, args.limit)
        formatter = format_function_results
    else:  # observations
        results = search_observations_all(args.query, args.limit)
        formatter = format_observation_results

    # Output
    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(f"\nCross-project search for: {args.query}")
        print(f"Type: {args.type}, Limit: {args.limit}")
        print("=" * 40)
        print(formatter(results))
        print(f"\nTotal: {len(results)} result(s)")


if __name__ == '__main__':
    main()
