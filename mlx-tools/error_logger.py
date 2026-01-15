#!/usr/bin/env python3
"""
Error Logger - Logs and queries agentic coding errors for learning
Integrates with the Claude memory system
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

MEMORY_BASE = Path.home() / ".claude-dash"
PROJECTS_DIR = MEMORY_BASE / "projects"

def get_errors_file(project_id: str) -> Path:
    """Get path to project's errors.json file"""
    return PROJECTS_DIR / project_id / "errors.json"

def load_errors(project_id: str) -> list:
    """Load existing errors for a project"""
    errors_file = get_errors_file(project_id)
    if errors_file.exists():
        with open(errors_file, 'r') as f:
            return json.load(f)
    return []

def save_errors(project_id: str, errors: list):
    """Save errors to project file"""
    errors_file = get_errors_file(project_id)
    errors_file.parent.mkdir(parents=True, exist_ok=True)
    with open(errors_file, 'w') as f:
        json.dump(errors, f, indent=2)

def log_error(project_id: str, error_data: dict) -> dict:
    """Log a new error"""
    errors = load_errors(project_id)

    # Generate ID
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    error_id = f"error-{timestamp}"

    # Build error entry
    error_entry = {
        "id": error_id,
        "date": datetime.now().isoformat(),
        "project": project_id,
        **error_data
    }

    errors.append(error_entry)
    save_errors(project_id, errors)

    return error_entry

def search_errors(query: str = None, project_id: str = None, category: str = None, limit: int = 10) -> list:
    """Search errors across projects"""
    results = []

    # Determine which projects to search
    if project_id:
        project_dirs = [PROJECTS_DIR / project_id]
    else:
        project_dirs = [d for d in PROJECTS_DIR.iterdir() if d.is_dir()]

    for project_dir in project_dirs:
        errors_file = project_dir / "errors.json"
        if not errors_file.exists():
            continue

        try:
            with open(errors_file, 'r') as f:
                errors = json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Corrupt errors.json in {project_dir}, skipping", file=__import__('sys').stderr)
            continue
        except IOError as e:
            print(f"Warning: Cannot read errors.json in {project_dir}: {e}", file=__import__('sys').stderr)
            continue

        for error in errors:
            # Filter by category
            if category and error.get('category') != category and error.get('subcategory') != category:
                continue

            # Filter by query
            if query:
                searchable = json.dumps(error).lower()
                if query.lower() not in searchable:
                    continue

            results.append(error)

    # Sort by date (newest first)
    results.sort(key=lambda x: x.get('date', ''), reverse=True)

    return results[:limit]

def get_error_stats(project_id: str = None) -> dict:
    """Get error statistics"""
    errors = search_errors(project_id=project_id, limit=1000)

    stats = {
        "total": len(errors),
        "by_category": {},
        "by_subcategory": {},
        "by_project": {},
        "recent": []
    }

    for error in errors:
        cat = error.get('category', 'unknown')
        subcat = error.get('subcategory', 'unknown')
        proj = error.get('project', 'unknown')

        stats['by_category'][cat] = stats['by_category'].get(cat, 0) + 1
        stats['by_subcategory'][subcat] = stats['by_subcategory'].get(subcat, 0) + 1
        stats['by_project'][proj] = stats['by_project'].get(proj, 0) + 1

    stats['recent'] = errors[:5]

    return stats

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  error_logger.py log <project> <json_data>  - Log new error")
        print("  error_logger.py search [query] [--project X] [--category Y]")
        print("  error_logger.py stats [--project X]")
        print("  error_logger.py list [--project X] [--limit N]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "log":
        if len(sys.argv) < 4:
            print("Usage: error_logger.py log <project> <json_data>")
            sys.exit(1)
        project = sys.argv[2]
        data = json.loads(sys.argv[3])
        result = log_error(project, data)
        print(json.dumps(result, indent=2))

    elif command == "search":
        query = None
        project = None
        category = None
        limit = 10

        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--project" and i + 1 < len(sys.argv):
                project = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--category" and i + 1 < len(sys.argv):
                category = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--limit" and i + 1 < len(sys.argv):
                limit = int(sys.argv[i + 1])
                i += 2
            else:
                query = sys.argv[i]
                i += 1

        results = search_errors(query=query, project_id=project, category=category, limit=limit)
        print(json.dumps(results, indent=2))

    elif command == "stats":
        project = None
        if len(sys.argv) > 2 and sys.argv[2] == "--project" and len(sys.argv) > 3:
            project = sys.argv[3]

        stats = get_error_stats(project_id=project)
        print(json.dumps(stats, indent=2))

    elif command == "list":
        project = None
        limit = 10

        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--project" and i + 1 < len(sys.argv):
                project = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--limit" and i + 1 < len(sys.argv):
                limit = int(sys.argv[i + 1])
                i += 2
            else:
                i += 1

        errors = search_errors(project_id=project, limit=limit)
        for error in errors:
            print(f"[{error['id']}] {error.get('category', '?')}/{error.get('subcategory', '?')}: {error.get('summary', 'No summary')[:60]}")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
