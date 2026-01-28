#!/usr/bin/env python3
"""
Auto-Refresh Worker - Automatically refresh stale indexes

Checks freshness and triggers re-indexing for stale projects.
Designed to run via launchd every 6 hours.

Usage:
    python3 auto_refresh.py           # Check and refresh if needed
    python3 auto_refresh.py --force   # Force refresh all
    python3 auto_refresh.py --dry-run # Show what would be refreshed
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

MEMORY_ROOT = Path.home() / '.claude-dash'
LOG_FILE = MEMORY_ROOT / 'logs' / 'auto_refresh.log'

# Staleness thresholds (days)
THRESHOLDS = {
    'summaries.json': 7,
    'functions.json': 7,
    'embeddings_v2.json': 14,
}


def log(message: str, level: str = "INFO"):
    """Log to file and stderr."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line, file=sys.stderr)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, 'a') as f:
            f.write(line + "\n")
    except IOError:
        pass


def get_projects() -> List[Dict]:
    """Get list of registered projects."""
    config_path = MEMORY_ROOT / 'config.json'
    if not config_path.exists():
        return []
    try:
        config = json.loads(config_path.read_text())
        return config.get('projects', [])
    except (json.JSONDecodeError, IOError):
        return []


def check_staleness(project_id: str) -> Dict[str, int]:
    """Check which files are stale for a project. Returns {filename: age_days}."""
    project_dir = MEMORY_ROOT / 'projects' / project_id
    stale = {}

    for filename, max_days in THRESHOLDS.items():
        filepath = project_dir / filename
        if filepath.exists():
            age_days = (datetime.now() - datetime.fromtimestamp(filepath.stat().st_mtime)).days
            if age_days > max_days:
                stale[filename] = age_days

    return stale


def refresh_summaries(project_id: str, project_path: str) -> bool:
    """Refresh summaries.json using ast-parser (structural extraction)."""
    log(f"Refreshing summaries for {project_id}")
    try:
        # Use ast-parser.js which generates both summaries.json and functions.json
        ast_parser = MEMORY_ROOT / 'watcher' / 'extractors' / 'ast-parser.js'
        if ast_parser.exists():
            result = subprocess.run(
                ['node', str(ast_parser), project_path, project_id],
                capture_output=True,
                timeout=300,
                cwd=str(MEMORY_ROOT / 'watcher' / 'extractors')
            )
            if result.returncode != 0:
                log(f"ast-parser stderr: {result.stderr.decode()[:500]}", "ERROR")
            return result.returncode == 0
    except Exception as e:
        log(f"Error refreshing summaries: {e}", "ERROR")
    return False


def refresh_functions(project_id: str, project_path: str) -> bool:
    """Refresh functions.json index using ast-parser."""
    log(f"Refreshing functions for {project_id}")
    try:
        # ast-parser.js generates both functions.json and summaries.json
        ast_parser = MEMORY_ROOT / 'watcher' / 'extractors' / 'ast-parser.js'
        if ast_parser.exists():
            result = subprocess.run(
                ['node', str(ast_parser), project_path, project_id],
                capture_output=True,
                timeout=120,
                cwd=str(MEMORY_ROOT / 'watcher' / 'extractors')
            )
            return result.returncode == 0

        # Fallback: touch the index to trigger watcher
        project_dir = MEMORY_ROOT / 'projects' / project_id
        index_file = project_dir / 'index.json'
        if index_file.exists():
            index_file.touch()
            return True
    except Exception as e:
        log(f"Error refreshing functions: {e}", "ERROR")
    return False


def refresh_embeddings(project_id: str) -> bool:
    """Refresh embeddings by running embedding sync."""
    log(f"Refreshing embeddings for {project_id}")
    try:
        embedding_sync = MEMORY_ROOT / 'mlx-tools' / 'embedding_sync.py'
        if embedding_sync.exists():
            result = subprocess.run(
                ['python3', str(embedding_sync), project_id, '--full'],
                capture_output=True,
                timeout=600,
                cwd=str(MEMORY_ROOT / 'mlx-tools')
            )
            return result.returncode == 0
    except Exception as e:
        log(f"Error refreshing embeddings: {e}", "ERROR")
    return False


def rebuild_hnsw(project_id: str) -> bool:
    """Rebuild HNSW index for faster semantic search."""
    log(f"Rebuilding HNSW index for {project_id}")
    try:
        hnsw_script = MEMORY_ROOT / 'mlx-tools' / 'hnsw_index.py'
        if hnsw_script.exists():
            result = subprocess.run(
                ['python3', str(hnsw_script), project_id, '--rebuild'],
                capture_output=True,
                timeout=300,
                cwd=str(MEMORY_ROOT / 'mlx-tools')
            )
            return result.returncode == 0
    except Exception as e:
        log(f"Error rebuilding HNSW: {e}", "ERROR")
    return False


def refresh_project(project_id: str, project_path: str, stale_files: Dict[str, int], dry_run: bool = False) -> Dict:
    """Refresh stale indexes for a project."""
    results = {"project": project_id, "refreshed": [], "failed": []}

    if dry_run:
        results["would_refresh"] = list(stale_files.keys())
        return results

    for filename in stale_files:
        success = False
        if filename == 'summaries.json':
            success = refresh_summaries(project_id, project_path)
        elif filename == 'functions.json':
            success = refresh_functions(project_id, project_path)
        elif filename == 'embeddings_v2.json':
            success = refresh_embeddings(project_id)
            if success:
                # Also rebuild HNSW after embeddings
                rebuild_hnsw(project_id)

        if success:
            results["refreshed"].append(filename)
        else:
            results["failed"].append(filename)

    return results


def run_auto_refresh(force: bool = False, dry_run: bool = False) -> Dict:
    """Main auto-refresh routine."""
    log("Starting auto-refresh check")

    projects = get_projects()
    if not projects:
        log("No projects configured")
        return {"status": "no_projects"}

    results = {
        "timestamp": datetime.now().isoformat(),
        "projects_checked": len(projects),
        "projects_refreshed": 0,
        "details": []
    }

    for project in projects:
        pid = project['id']
        ppath = project.get('path', '')

        if force:
            stale = {k: 999 for k in THRESHOLDS}  # Mark all as stale
        else:
            stale = check_staleness(pid)

        if stale:
            log(f"Project {pid} has stale files: {list(stale.keys())}")
            result = refresh_project(pid, ppath, stale, dry_run)
            results["details"].append(result)
            if result.get("refreshed"):
                results["projects_refreshed"] += 1
        else:
            log(f"Project {pid} is fresh")

    log(f"Auto-refresh complete: {results['projects_refreshed']}/{len(projects)} refreshed")

    # Save results
    state_file = MEMORY_ROOT / 'workers' / 'auto_refresh_state.json'
    try:
        state_file.write_text(json.dumps(results, indent=2))
    except IOError:
        pass

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto-refresh stale indexes")
    parser.add_argument("--force", action="store_true", help="Force refresh all indexes")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be refreshed")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    results = run_auto_refresh(force=args.force, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"\nAuto-Refresh Results:")
        print(f"  Projects checked: {results.get('projects_checked', 0)}")
        print(f"  Projects refreshed: {results.get('projects_refreshed', 0)}")
        for detail in results.get('details', []):
            pid = detail.get('project', 'unknown')
            refreshed = detail.get('refreshed', [])
            failed = detail.get('failed', [])
            would = detail.get('would_refresh', [])
            if would:
                print(f"\n  {pid}: would refresh {would}")
            elif refreshed or failed:
                print(f"\n  {pid}:")
                if refreshed:
                    print(f"    ✓ Refreshed: {refreshed}")
                if failed:
                    print(f"    ✗ Failed: {failed}")


if __name__ == "__main__":
    main()
