#!/usr/bin/env python3
"""
Proactive Memory Assistant

Surfaces relevant context before you ask:
- Recent decisions about the file you're viewing
- Known gotchas for this code area
- Similar patterns in other projects
- Past errors and solutions
- Related session observations

Can be triggered by:
- File open hook
- Directory change
- Git branch switch
- Manual query
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

MLX_DIR = Path(__file__).parent
sys.path.insert(0, str(MLX_DIR))

from memory_db import (
    get_connection, search_files, search_functions,
    search_observations, find_similar_errors, cross_project_search
)

MEMORY_ROOT = Path.home() / '.claude-dash'


def get_file_context(project_id: str, file_path: str) -> Dict:
    """Get all relevant context for a file."""
    context = {
        'file': file_path,
        'project': project_id,
        'relevant_observations': [],
        'similar_files': [],
        'known_gotchas': [],
        'recent_decisions': [],
        'related_functions': [],
    }

    conn = get_connection()

    # Get file info from database
    cursor = conn.execute("""
        SELECT f.*, p.name as project_name
        FROM files f
        JOIN projects p ON p.id = f.project_id
        WHERE f.project_id = ? AND f.path = ?
    """, (project_id, file_path))
    file_info = cursor.fetchone()

    if file_info:
        context['summary'] = file_info['summary']
        context['purpose'] = file_info['purpose']

        # Get functions in this file
        cursor = conn.execute("""
            SELECT name, line_number, type FROM functions
            WHERE file_id = ?
            ORDER BY line_number
        """, (file_info['id'],))
        context['functions'] = [dict(row) for row in cursor.fetchall()]

    # Search for observations mentioning this file
    # Extract filename without path for broader search
    filename = Path(file_path).name
    file_stem = Path(file_path).stem

    # Search observations
    observations = search_observations(file_stem, project_id=project_id, limit=10)
    for obs in observations:
        if obs['category'] == 'gotcha':
            context['known_gotchas'].append({
                'title': obs['title'],
                'content': obs['content'][:200],
                'created_at': obs['created_at']
            })
        elif obs['category'] == 'decision':
            context['recent_decisions'].append({
                'title': obs['title'],
                'content': obs['content'][:200],
                'git_commit': obs.get('git_commit_start')
            })
        else:
            context['relevant_observations'].append({
                'category': obs['category'],
                'title': obs['title'],
                'content': obs['content'][:200]
            })

    # Find similar files in other projects
    if file_info and file_info.get('summary'):
        similar = cross_project_search(file_info['summary'][:100], limit=5)
        for s in similar:
            if s['project_id'] != project_id:  # Exclude same project
                context['similar_files'].append({
                    'project': s['project_id'],
                    'path': s['path'],
                    'purpose': s.get('purpose', '')
                })

    conn.close()
    return context


def get_directory_context(project_id: str, directory: str) -> Dict:
    """Get context for a directory/feature area."""
    context = {
        'directory': directory,
        'project': project_id,
        'files': [],
        'recent_changes': [],
        'key_decisions': [],
        'common_patterns': []
    }

    conn = get_connection()

    # Get files in this directory
    cursor = conn.execute("""
        SELECT path, summary, purpose, component_name
        FROM files
        WHERE project_id = ? AND path LIKE ?
        ORDER BY path
        LIMIT 20
    """, (project_id, f'{directory}%'))
    context['files'] = [dict(row) for row in cursor.fetchall()]

    # Get recent observations for this area
    observations = search_observations(directory, project_id=project_id, limit=10)
    for obs in observations:
        if obs['category'] == 'decision':
            context['key_decisions'].append({
                'title': obs['title'],
                'content': obs['content'][:200]
            })
        elif obs['category'] == 'pattern':
            context['common_patterns'].append({
                'title': obs['title'],
                'content': obs['content'][:200]
            })

    conn.close()
    return context


def get_error_context(error_type: str, error_message: str) -> Dict:
    """Get context for an error - have we seen this before?"""
    context = {
        'error_type': error_type,
        'error_message': error_message[:200],
        'similar_errors': [],
        'potential_solutions': []
    }

    similar = find_similar_errors(error_type, error_message)
    for err in similar:
        context['similar_errors'].append({
            'project': err['project_name'],
            'message': err['message'][:200],
            'file': err.get('file_path'),
            'occurred_at': err['occurred_at']
        })
        if err.get('solution'):
            context['potential_solutions'].append({
                'solution': err['solution'],
                'from_project': err['project_name']
            })

    return context


def get_startup_context(project_id: str) -> Dict:
    """Get context when starting work on a project."""
    context = {
        'project': project_id,
        'recent_sessions': [],
        'pending_decisions': [],
        'recent_gotchas': [],
        'stats': {}
    }

    conn = get_connection()

    # Get project stats
    cursor = conn.execute("""
        SELECT COUNT(*) as file_count FROM files WHERE project_id = ?
    """, (project_id,))
    context['stats']['files'] = cursor.fetchone()['file_count']

    cursor = conn.execute("""
        SELECT COUNT(*) as func_count FROM functions f
        JOIN files fi ON fi.id = f.file_id
        WHERE fi.project_id = ?
    """, (project_id,))
    context['stats']['functions'] = cursor.fetchone()['func_count']

    # Recent sessions
    cursor = conn.execute("""
        SELECT id, started_at, git_branch, git_commit_start, git_commit_end
        FROM sessions
        WHERE project_id = ?
        ORDER BY started_at DESC
        LIMIT 5
    """, (project_id,))
    context['recent_sessions'] = [dict(row) for row in cursor.fetchall()]

    # Recent gotchas (last 30 days)
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    cursor = conn.execute("""
        SELECT title, content, created_at
        FROM observations
        WHERE project_id = ? AND category = 'gotcha'
        AND created_at > ?
        ORDER BY created_at DESC
        LIMIT 5
    """, (project_id, thirty_days_ago))
    context['recent_gotchas'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return context


def get_branch_context(project_id: str, branch_name: str) -> Dict:
    """Get context for a git branch."""
    context = {
        'branch': branch_name,
        'project': project_id,
        'sessions_on_branch': [],
        'decisions': [],
        'changes': []
    }

    conn = get_connection()

    # Find sessions on this branch
    cursor = conn.execute("""
        SELECT s.id, s.started_at, s.git_commit_start, s.git_commit_end,
               COUNT(o.id) as observation_count
        FROM sessions s
        LEFT JOIN observations o ON o.session_id = s.id
        WHERE s.project_id = ? AND s.git_branch = ?
        GROUP BY s.id
        ORDER BY s.started_at DESC
        LIMIT 10
    """, (project_id, branch_name))
    context['sessions_on_branch'] = [dict(row) for row in cursor.fetchall()]

    # Get observations from those sessions
    session_ids = [s['id'] for s in context['sessions_on_branch']]
    if session_ids:
        placeholders = ','.join('?' * len(session_ids))
        cursor = conn.execute(f"""
            SELECT category, title, content, created_at
            FROM observations
            WHERE session_id IN ({placeholders})
            AND category IN ('decision', 'feature', 'bugfix')
            ORDER BY created_at DESC
            LIMIT 10
        """, session_ids)
        context['decisions'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return context


def format_context(context: Dict, verbose: bool = False) -> str:
    """Format context for display."""
    lines = []

    # File context
    if 'file' in context:
        lines.append(f"📄 Context for: {context['file']}")
        if context.get('summary'):
            lines.append(f"   Summary: {context['summary'][:100]}...")
        if context.get('purpose'):
            lines.append(f"   Purpose: {context['purpose']}")

        if context.get('known_gotchas'):
            lines.append("\n⚠️  Known Gotchas:")
            for g in context['known_gotchas'][:3]:
                lines.append(f"   • {g['title']}")
                if verbose:
                    lines.append(f"     {g['content']}")

        if context.get('recent_decisions'):
            lines.append("\n📝 Recent Decisions:")
            for d in context['recent_decisions'][:3]:
                lines.append(f"   • {d['title']}")
                if d.get('git_commit'):
                    lines.append(f"     (commit: {d['git_commit']})")

        if context.get('similar_files'):
            lines.append("\n🔗 Similar in other projects:")
            for s in context['similar_files'][:3]:
                lines.append(f"   • [{s['project']}] {s['path']}")

    # Directory context
    elif 'directory' in context:
        lines.append(f"📁 Context for: {context['directory']}")
        lines.append(f"   Files: {len(context.get('files', []))}")

        if context.get('key_decisions'):
            lines.append("\n📝 Key Decisions:")
            for d in context['key_decisions'][:3]:
                lines.append(f"   • {d['title']}")

        if context.get('common_patterns'):
            lines.append("\n🔄 Common Patterns:")
            for p in context['common_patterns'][:3]:
                lines.append(f"   • {p['title']}")

    # Error context
    elif 'error_type' in context:
        lines.append(f"❌ Error: {context['error_type']}")
        lines.append(f"   {context['error_message']}")

        if context.get('potential_solutions'):
            lines.append("\n💡 Potential Solutions (from past fixes):")
            for s in context['potential_solutions'][:3]:
                lines.append(f"   • [{s['from_project']}] {s['solution'][:150]}...")

        if context.get('similar_errors') and not context.get('potential_solutions'):
            lines.append("\n🔍 Similar errors seen before:")
            for e in context['similar_errors'][:3]:
                lines.append(f"   • [{e['project']}] {e['message'][:100]}...")

    # Startup context
    elif 'stats' in context:
        lines.append(f"🚀 Starting work on: {context['project']}")
        lines.append(f"   Indexed: {context['stats']['files']} files, {context['stats']['functions']} functions")

        if context.get('recent_gotchas'):
            lines.append("\n⚠️  Recent Gotchas (last 30 days):")
            for g in context['recent_gotchas'][:3]:
                lines.append(f"   • {g['title']}")

        if context.get('recent_sessions'):
            lines.append("\n📅 Recent Sessions:")
            for s in context['recent_sessions'][:3]:
                branch = s.get('git_branch', 'unknown')
                lines.append(f"   • {s['started_at'][:10]} on {branch}")

    # Branch context
    elif 'branch' in context:
        lines.append(f"🌿 Branch: {context['branch']}")
        lines.append(f"   Sessions: {len(context.get('sessions_on_branch', []))}")

        if context.get('decisions'):
            lines.append("\n📝 Work on this branch:")
            for d in context['decisions'][:5]:
                lines.append(f"   • [{d['category']}] {d['title']}")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Proactive Memory Assistant')
    parser.add_argument('project', nargs='?', help='Project ID')
    parser.add_argument('--file', '-f', help='Get context for a file')
    parser.add_argument('--dir', '-d', help='Get context for a directory')
    parser.add_argument('--error', '-e', nargs=2, metavar=('TYPE', 'MSG'),
                        help='Get context for an error')
    parser.add_argument('--branch', '-b', help='Get context for a git branch')
    parser.add_argument('--startup', '-s', action='store_true',
                        help='Get startup context for project')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    if args.file:
        if not args.project:
            print("Error: --file requires project ID")
            sys.exit(1)
        context = get_file_context(args.project, args.file)
    elif args.dir:
        if not args.project:
            print("Error: --dir requires project ID")
            sys.exit(1)
        context = get_directory_context(args.project, args.dir)
    elif args.error:
        context = get_error_context(args.error[0], args.error[1])
    elif args.branch:
        if not args.project:
            print("Error: --branch requires project ID")
            sys.exit(1)
        context = get_branch_context(args.project, args.branch)
    elif args.startup and args.project:
        context = get_startup_context(args.project)
    else:
        parser.print_help()
        sys.exit(1)

    if args.json:
        print(json.dumps(context, indent=2, default=str))
    else:
        print(format_context(context, verbose=args.verbose))


if __name__ == '__main__':
    main()
