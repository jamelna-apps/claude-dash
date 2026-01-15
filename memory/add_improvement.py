#!/usr/bin/env python3
"""
Add Improvement - Helper to add ideas/issues to the improvements backlog

Usage:
    # Add an idea
    python3 add_improvement.py idea "Title" "Description" --priority high

    # Add a tech debt item
    python3 add_improvement.py debt "Title" "Description" --file path/to/file.py

    # Log an issue (from health checks or other scripts)
    python3 add_improvement.py issue "Title" "Description" --source health_check

    # Mark something as complete
    python3 add_improvement.py complete <id>

    # List pending items
    python3 add_improvement.py list [--all]
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
import hashlib

IMPROVEMENTS_PATH = Path.home() / '.claude-dash' / 'improvements.json'


def load_improvements():
    """Load the improvements file."""
    if not IMPROVEMENTS_PATH.exists():
        return {
            'version': 1,
            'lastReviewed': None,
            'ideas': [],
            'issues': [],
            'techDebt': [],
            'stats': {
                'totalIdeas': 0,
                'completedIdeas': 0,
                'pendingIssues': 0,
                'pendingDebt': 0
            }
        }
    return json.loads(IMPROVEMENTS_PATH.read_text())


def save_improvements(data):
    """Save the improvements file."""
    # Update stats
    data['stats'] = {
        'totalIdeas': len(data.get('ideas', [])),
        'completedIdeas': len([i for i in data.get('ideas', []) if i.get('status') == 'completed']),
        'pendingIssues': len([i for i in data.get('issues', []) if i.get('status') != 'resolved']),
        'pendingDebt': len([i for i in data.get('techDebt', []) if i.get('status') == 'pending'])
    }
    IMPROVEMENTS_PATH.write_text(json.dumps(data, indent=2))


def generate_id(title):
    """Generate a short ID from title."""
    slug = title.lower().replace(' ', '-')[:30]
    hash_suffix = hashlib.md5(title.encode()).hexdigest()[:4]
    return f"{slug}-{hash_suffix}"


def add_idea(title, description, priority='medium', source='session'):
    """Add a new improvement idea."""
    data = load_improvements()

    item = {
        'id': generate_id(title),
        'title': title,
        'description': description,
        'priority': priority,
        'status': 'pending',
        'source': source,
        'addedAt': datetime.now().isoformat()
    }

    # Check for duplicates
    existing_ids = [i['id'] for i in data.get('ideas', [])]
    if item['id'] in existing_ids:
        print(f"Similar idea already exists: {item['id']}")
        return False

    data['ideas'].append(item)
    save_improvements(data)
    print(f"Added idea: [{priority}] {title}")
    return True


def add_debt(title, description, file_path=None, priority='low'):
    """Add a tech debt item."""
    data = load_improvements()

    item = {
        'id': generate_id(title),
        'title': title,
        'description': description,
        'priority': priority,
        'status': 'pending',
        'addedAt': datetime.now().isoformat()
    }
    if file_path:
        item['file'] = file_path

    # Check for duplicates
    existing_ids = [i['id'] for i in data.get('techDebt', [])]
    if item['id'] in existing_ids:
        print(f"Similar debt item already exists: {item['id']}")
        return False

    data['techDebt'].append(item)
    save_improvements(data)
    print(f"Added tech debt: {title}")
    return True


def add_issue(title, description, source='unknown'):
    """Log an issue from health checks or other scripts."""
    data = load_improvements()

    item = {
        'id': generate_id(title),
        'title': title,
        'description': description,
        'status': 'open',
        'source': source,
        'detectedAt': datetime.now().isoformat()
    }

    # Check for duplicates
    existing_ids = [i['id'] for i in data.get('issues', [])]
    if item['id'] in existing_ids:
        # Update detection time for existing issue
        for issue in data['issues']:
            if issue['id'] == item['id']:
                issue['lastSeen'] = datetime.now().isoformat()
                save_improvements(data)
                return False

    data['issues'].append(item)
    save_improvements(data)
    print(f"Logged issue: {title}")
    return True


def mark_complete(item_id):
    """Mark an item as complete/resolved."""
    data = load_improvements()
    found = False

    for collection in ['ideas', 'techDebt', 'issues']:
        for item in data.get(collection, []):
            if item['id'] == item_id or item['title'].lower() == item_id.lower():
                if collection == 'issues':
                    item['status'] = 'resolved'
                else:
                    item['status'] = 'completed'
                item['completedAt'] = datetime.now().isoformat()
                found = True
                print(f"Marked as complete: {item['title']}")
                break
        if found:
            break

    if found:
        save_improvements(data)
    else:
        print(f"Item not found: {item_id}")

    return found


def list_items(show_all=False):
    """List pending items."""
    data = load_improvements()

    print("=== Pending Improvements ===\n")

    # Ideas
    pending_ideas = [i for i in data.get('ideas', [])
                     if show_all or i.get('status') == 'pending']
    if pending_ideas:
        print("Ideas:")
        for idea in sorted(pending_ideas, key=lambda x: {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}.get(x.get('priority', 'medium'), 2)):
            status = f"[{idea['priority']}]" if idea.get('status') == 'pending' else f"[{idea['status']}]"
            print(f"  {status} {idea['title']}")
            print(f"       ID: {idea['id']}")
        print()

    # Tech debt
    pending_debt = [i for i in data.get('techDebt', [])
                    if show_all or i.get('status') == 'pending']
    if pending_debt:
        print("Tech Debt:")
        for debt in pending_debt:
            file_info = f" ({debt['file']})" if debt.get('file') else ""
            print(f"  [{debt.get('priority', 'low')}] {debt['title']}{file_info}")
            print(f"       ID: {debt['id']}")
        print()

    # Issues
    open_issues = [i for i in data.get('issues', [])
                   if show_all or i.get('status') != 'resolved']
    if open_issues:
        print("Open Issues:")
        for issue in open_issues:
            print(f"  [{issue.get('source', 'unknown')}] {issue['title']}")
            print(f"       ID: {issue['id']}")
        print()

    # Stats
    stats = data.get('stats', {})
    print(f"Stats: {stats.get('completedIdeas', 0)} ideas completed, "
          f"{stats.get('pendingIssues', 0)} open issues, "
          f"{stats.get('pendingDebt', 0)} tech debt items")


def main():
    parser = argparse.ArgumentParser(description='Manage improvements backlog')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # idea command
    idea_parser = subparsers.add_parser('idea', help='Add an improvement idea')
    idea_parser.add_argument('title', help='Short title')
    idea_parser.add_argument('description', help='Description')
    idea_parser.add_argument('--priority', choices=['critical', 'high', 'medium', 'low'], default='medium')
    idea_parser.add_argument('--source', default='session')

    # debt command
    debt_parser = subparsers.add_parser('debt', help='Add a tech debt item')
    debt_parser.add_argument('title', help='Short title')
    debt_parser.add_argument('description', help='Description')
    debt_parser.add_argument('--file', help='Related file path')
    debt_parser.add_argument('--priority', choices=['critical', 'high', 'medium', 'low'], default='low')

    # issue command
    issue_parser = subparsers.add_parser('issue', help='Log an issue')
    issue_parser.add_argument('title', help='Short title')
    issue_parser.add_argument('description', help='Description')
    issue_parser.add_argument('--source', default='unknown')

    # complete command
    complete_parser = subparsers.add_parser('complete', help='Mark item as complete')
    complete_parser.add_argument('id', help='Item ID or title')

    # list command
    list_parser = subparsers.add_parser('list', help='List pending items')
    list_parser.add_argument('--all', action='store_true', help='Show all including completed')

    args = parser.parse_args()

    if args.command == 'idea':
        add_idea(args.title, args.description, args.priority, args.source)
    elif args.command == 'debt':
        add_debt(args.title, args.description, args.file, args.priority)
    elif args.command == 'issue':
        add_issue(args.title, args.description, args.source)
    elif args.command == 'complete':
        mark_complete(args.id)
    elif args.command == 'list':
        list_items(args.all)


if __name__ == '__main__':
    main()
