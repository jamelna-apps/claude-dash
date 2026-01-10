#!/usr/bin/env python3
"""
Session Search for Claude Memory System

Search across session observations and history.

Usage:
  python session_search.py "query" [--project PROJECT] [--category CATEGORY] [--limit N]
  python session_search.py --list-sessions [--project PROJECT]
  python session_search.py --session SESSION_ID

Examples:
  python session_search.py "authentication"
  python session_search.py "PID file" --category decision
  python session_search.py "hook" --project gyst
  python session_search.py --list-sessions
  python session_search.py --session abc123
"""

import json
import argparse
import re
from pathlib import Path
from datetime import datetime

MEMORY_ROOT = Path.home() / ".claude-dash"

OBSERVATION_CATEGORIES = [
    "decision",
    "pattern",
    "bugfix",
    "gotcha",
    "feature",
    "implementation"
]


def load_observations(project_id=None):
    """Load observations from global or project-specific store."""
    if project_id:
        obs_path = MEMORY_ROOT / "projects" / project_id / "observations.json"
    else:
        obs_path = MEMORY_ROOT / "sessions" / "observations.json"

    try:
        data = json.loads(obs_path.read_text())
        return data.get("observations", [])
    except:
        return []


def load_session_index():
    """Load the global session index."""
    index_path = MEMORY_ROOT / "sessions" / "index.json"
    try:
        data = json.loads(index_path.read_text())
        return data.get("sessions", [])
    except:
        return []


def load_transcript(session_id):
    """Load a specific session transcript."""
    transcript_path = MEMORY_ROOT / "sessions" / "transcripts" / f"{session_id}.jsonl"
    messages = []

    if transcript_path.exists():
        with open(transcript_path, 'r') as f:
            for line in f:
                try:
                    messages.append(json.loads(line.strip()))
                except:
                    continue

    return messages


def search_observations(query, observations, category=None):
    """Search observations by keyword."""
    results = []
    query_lower = query.lower()
    query_words = query_lower.split()

    for obs in observations:
        # Filter by category if specified
        if category and obs.get("category") != category:
            continue

        text = obs.get("observation", "").lower()
        files = " ".join(obs.get("files", [])).lower()
        combined = f"{text} {files}"

        # Score by number of query words matched
        score = sum(1 for word in query_words if word in combined)

        if score > 0:
            results.append({
                **obs,
                "_score": score
            })

    # Sort by score descending, then by timestamp descending
    results.sort(key=lambda x: (-x["_score"], x.get("timestamp", "")), reverse=False)
    results.sort(key=lambda x: x["_score"], reverse=True)

    return results


def format_observation(obs, verbose=False):
    """Format an observation for display."""
    category = obs.get("category", "unknown")
    text = obs.get("observation", "")
    files = obs.get("files", [])
    timestamp = obs.get("timestamp", "")[:10]  # Date only
    project = obs.get("projectId", "")

    # Category emoji
    emoji = {
        "decision": "🎯",
        "pattern": "🔄",
        "bugfix": "🐛",
        "gotcha": "⚠️",
        "feature": "✨",
        "implementation": "🔧"
    }.get(category, "📝")

    output = f"{emoji} [{category}] {text}"

    if verbose:
        if files:
            output += f"\n   Files: {', '.join(files)}"
        output += f"\n   Project: {project} | Date: {timestamp}"

    return output


def format_session(session):
    """Format a session entry for display."""
    session_id = session.get("sessionId", "unknown")[:8]
    project = session.get("projectId", "unknown")
    timestamp = session.get("timestamp", "")[:10]
    obs_count = session.get("observationCount", 0)
    summary = session.get("summary", "")[:60]

    return f"[{session_id}] {timestamp} | {project} | {obs_count} obs | {summary}"


def main():
    parser = argparse.ArgumentParser(description="Search session observations")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--project", "-p", help="Filter by project ID")
    parser.add_argument("--category", "-c", choices=OBSERVATION_CATEGORIES, help="Filter by category")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Max results")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show more details")
    parser.add_argument("--list-sessions", "-l", action="store_true", help="List recent sessions")
    parser.add_argument("--session", "-s", help="Show details for a specific session")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # List sessions mode
    if args.list_sessions:
        sessions = load_session_index()

        if args.project:
            sessions = [s for s in sessions if s.get("projectId") == args.project]

        sessions = sessions[-args.limit:]
        sessions.reverse()

        if args.json:
            print(json.dumps(sessions, indent=2))
        else:
            print(f"Recent sessions ({len(sessions)}):\n")
            for s in sessions:
                print(format_session(s))

        return

    # Show specific session
    if args.session:
        # Find session in index
        sessions = load_session_index()
        session = next((s for s in sessions if s.get("sessionId", "").startswith(args.session)), None)

        if not session:
            print(f"Session not found: {args.session}")
            return

        session_id = session.get("sessionId", "")

        # Get observations for this session
        all_obs = load_observations(args.project)
        session_obs = [o for o in all_obs if o.get("sessionId") == session_id]

        if args.json:
            print(json.dumps({
                "session": session,
                "observations": session_obs
            }, indent=2))
        else:
            print(f"\nSession: {session_id}")
            print(f"Project: {session.get('projectId', 'unknown')}")
            print(f"Date: {session.get('timestamp', '')[:19]}")
            print(f"Summary: {session.get('summary', 'No summary')}")
            print(f"\nObservations ({len(session_obs)}):")
            for obs in session_obs:
                print(f"  {format_observation(obs)}")

        return

    # Search mode
    if not args.query:
        parser.print_help()
        return

    observations = load_observations(args.project)

    if not observations:
        print("No observations found.")
        if args.project:
            print(f"  (Searched in project: {args.project})")
        return

    results = search_observations(args.query, observations, args.category)
    results = results[:args.limit]

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"Found {len(results)} results for '{args.query}':\n")
        for obs in results:
            print(format_observation(obs, args.verbose))
            print()


if __name__ == "__main__":
    main()
