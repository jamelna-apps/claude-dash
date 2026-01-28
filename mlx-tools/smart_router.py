#!/usr/bin/env python3
"""
Smart Router - Intelligent Local/Cloud LLM Routing

Automatically routes queries to the best backend:
- Simple questions → Local Ollama (free, fast)
- Complex tasks → Claude Code CLI (powerful, paid)

Features:
- Project detection from current directory
- Context injection from memory system
- Tool-need detection (edit/write → Claude)
- Conversation history support

Usage:
    smart "your question"
    smart --project gyst "question"
    smart --force-local "question"
    smart --force-claude "question"
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path
from typing import Optional, Tuple, Dict, List
from datetime import datetime

# Add mlx-tools to path
sys.path.insert(0, str(Path(__file__).parent))

from complexity_router import (
    analyze_query_complexity,
    ComplexityLevel,
    Backend,
    ComplexityAnalysis
)

MEMORY_ROOT = Path.home() / '.claude-dash'
CONFIG_PATH = MEMORY_ROOT / 'config.json'
HISTORY_PATH = MEMORY_ROOT / 'smart_router_history.json'

# Keywords that indicate file operations (need Claude's tools)
TOOL_INDICATORS = [
    'edit', 'modify', 'change', 'update', 'fix',
    'create file', 'write file', 'add file', 'new file',
    'delete', 'remove', 'rename file',
    'commit', 'push', 'pull request', 'pr',
    'run test', 'execute', 'build', 'deploy',
    'install', 'npm', 'pip', 'yarn'
]

# Question patterns that work well locally
QUESTION_PATTERNS = [
    'what is', 'what does', 'what are',
    'how does', 'how do', 'how to',
    'where is', 'where are', 'where do',
    'why does', 'why is', 'why do',
    'explain', 'describe', 'show me',
    'find', 'search', 'look for', 'locate'
]


def load_config() -> Dict:
    """Load claude-dash config"""
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {'projects': []}


def detect_project() -> Optional[str]:
    """Detect project from current working directory"""
    cwd = Path.cwd()
    config = load_config()

    for project in config.get('projects', []):
        project_path = Path(project.get('path', '')).expanduser()
        try:
            # Check if cwd is inside project path
            cwd.relative_to(project_path)
            return project['id']
        except ValueError:
            continue

    return None


def needs_tools(query: str) -> bool:
    """Check if query likely needs Claude's tool capabilities"""
    query_lower = query.lower()
    return any(indicator in query_lower for indicator in TOOL_INDICATORS)


def is_pure_question(query: str) -> bool:
    """Check if query is a pure question (no action needed)"""
    query_lower = query.lower().strip()
    return any(query_lower.startswith(pattern) for pattern in QUESTION_PATTERNS)


def get_context(project_id: str, query: str) -> str:
    """Get relevant context from memory system"""
    context_parts = []
    project_dir = MEMORY_ROOT / 'projects' / project_id

    # Load project summaries for context
    summaries_path = project_dir / 'summaries.json'
    if summaries_path.exists():
        summaries = json.loads(summaries_path.read_text())
        context_parts.append(f"Project: {project_id}")
        context_parts.append(f"Files indexed: {len(summaries.get('files', {}))}")

    # Try hybrid search for relevant files
    try:
        from hybrid_search import hybrid_search
        results = hybrid_search(project_id, query, top_k=3)
        if results:
            context_parts.append("\nRelevant files:")
            for r in results:
                context_parts.append(f"- {r['file']}: {r.get('purpose', r.get('summary', ''))[:100]}")
    except Exception:
        pass

    # Load recent decisions
    decisions_path = project_dir / 'decisions.json'
    if decisions_path.exists():
        decisions = json.loads(decisions_path.read_text())
        recent = decisions.get('decisions', [])[:3]
        if recent:
            context_parts.append("\nRecent decisions:")
            for d in recent:
                context_parts.append(f"- {d.get('title', 'Untitled')}")

    return '\n'.join(context_parts)


def route_to_local(query: str, project_id: Optional[str], context: str, verbose: bool = False) -> str:
    """Send query to local Ollama via mlx tools"""
    mlx_path = Path(__file__).parent / 'mlx'

    if project_id:
        # Use RAG for project-aware responses
        cmd = [str(mlx_path), 'rag', project_id, query]
    else:
        # Use general ask without project context
        cmd = [str(mlx_path), 'ask', 'general', query]

    if verbose:
        print(f"[LOCAL] Running: {' '.join(cmd)}", file=sys.stderr)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.stdout.strip() or result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "Error: Local LLM timed out"
    except Exception as e:
        return f"Error: {e}"


def route_to_claude(query: str, project_id: Optional[str], verbose: bool = False) -> str:
    """Send query to Claude Code CLI"""
    cmd = ['claude', '--print', query]

    if verbose:
        print(f"[CLAUDE] Running: claude --print ...", file=sys.stderr)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        return result.stdout.strip() or result.stderr.strip()
    except FileNotFoundError:
        return "Error: Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
    except subprocess.TimeoutExpired:
        return "Error: Claude timed out"
    except Exception as e:
        return f"Error: {e}"


def smart_route(
    query: str,
    project_id: Optional[str] = None,
    force_local: bool = False,
    force_claude: bool = False,
    verbose: bool = False
) -> Tuple[str, str, str]:
    """
    Intelligently route query to best backend.

    Returns: (response, backend_used, reason)
    """
    # Auto-detect project if not specified
    if not project_id:
        project_id = detect_project()

    # Get context for the query
    context = ""
    if project_id:
        context = get_context(project_id, query)

    # Determine routing
    if force_local:
        backend = Backend.LOCAL
        reason = "Forced local"
    elif force_claude:
        backend = Backend.CLAUDE
        reason = "Forced Claude"
    elif needs_tools(query):
        # Tasks that need file operations should use Claude
        backend = Backend.CLAUDE
        reason = "Task requires tool use (edit/write/run)"
    elif is_pure_question(query):
        # Pure questions can often be handled locally
        analysis = analyze_query_complexity(query)
        if analysis.level.value <= ComplexityLevel.MODERATE.value:
            backend = Backend.LOCAL
            reason = f"Question can be answered locally (complexity: {analysis.level.name})"
        else:
            backend = Backend.CLAUDE
            reason = f"Complex question needs Claude (complexity: {analysis.level.name})"
    else:
        # Use complexity analysis for everything else
        analysis = analyze_query_complexity(query)
        backend = analysis.recommended_backend
        reason = analysis.reason

    # Route to appropriate backend
    if verbose:
        print(f"Project: {project_id or 'None detected'}", file=sys.stderr)
        print(f"Backend: {backend.value}", file=sys.stderr)
        print(f"Reason: {reason}", file=sys.stderr)
        print("---", file=sys.stderr)

    if backend == Backend.LOCAL:
        response = route_to_local(query, project_id, context, verbose)
    else:
        response = route_to_claude(query, project_id, verbose)

    return response, backend.value, reason


def save_to_history(query: str, backend: str, reason: str):
    """Save routing decision to history for analysis"""
    history = []
    if HISTORY_PATH.exists():
        try:
            history = json.loads(HISTORY_PATH.read_text())
        except:
            history = []

    history.append({
        'timestamp': datetime.now().isoformat(),
        'query': query[:200],  # Truncate long queries
        'backend': backend,
        'reason': reason
    })

    # Keep last 100 entries
    history = history[-100:]

    HISTORY_PATH.write_text(json.dumps(history, indent=2))


def show_stats():
    """Show routing statistics"""
    if not HISTORY_PATH.exists():
        print("No routing history yet.")
        return

    history = json.loads(HISTORY_PATH.read_text())

    local_count = sum(1 for h in history if h['backend'] == 'local')
    claude_count = sum(1 for h in history if h['backend'] == 'claude')
    total = len(history)

    print("Smart Router Statistics")
    print("=" * 40)
    print(f"Total queries: {total}")
    print(f"Local (free):  {local_count} ({local_count/total*100:.0f}%)")
    print(f"Claude (paid): {claude_count} ({claude_count/total*100:.0f}%)")
    print("")
    print("Recent routing decisions:")
    for h in history[-5:]:
        print(f"  [{h['backend'].upper():6}] {h['query'][:50]}...")


def main():
    parser = argparse.ArgumentParser(
        description='Smart Router - Intelligent Local/Cloud LLM Routing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  smart "what does the login function do?"     # Likely LOCAL
  smart "refactor auth across all screens"     # Likely CLAUDE
  smart --force-local "complex question"       # Force local
  smart --stats                                # Show routing stats
        """
    )

    parser.add_argument('query', nargs='*', help='The query to route')
    parser.add_argument('-p', '--project', help='Project ID (auto-detected if not specified)')
    parser.add_argument('-l', '--local', action='store_true', help='Force local processing')
    parser.add_argument('-c', '--claude', action='store_true', help='Force Claude API')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show routing details')
    parser.add_argument('--stats', action='store_true', help='Show routing statistics')
    parser.add_argument('--dry-run', action='store_true', help='Show routing decision without executing')

    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    if not args.query:
        parser.print_help()
        return

    query = ' '.join(args.query)

    if args.dry_run:
        # Just show what would happen
        project_id = args.project or detect_project()

        if args.local:
            print(f"Would route to: LOCAL (forced)")
        elif args.claude:
            print(f"Would route to: CLAUDE (forced)")
        elif needs_tools(query):
            print(f"Would route to: CLAUDE (needs tools)")
        else:
            analysis = analyze_query_complexity(query)
            print(f"Complexity: {analysis.level.name} (score: {analysis.score:.1f})")
            print(f"Would route to: {analysis.recommended_backend.value.upper()}")
            print(f"Reason: {analysis.reason}")

        print(f"Project: {project_id or 'None detected'}")
        return

    response, backend, reason = smart_route(
        query,
        project_id=args.project,
        force_local=args.local,
        force_claude=args.claude,
        verbose=args.verbose
    )

    # Save to history
    save_to_history(query, backend, reason)

    # Print response
    print(response)


if __name__ == '__main__':
    main()
