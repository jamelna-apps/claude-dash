#!/usr/bin/env python3
"""
Freshness Checker for Claude Memory System
Detects when analysis data is stale and needs refresh.
"""

import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

class FreshnessChecker:
    """Check if project analysis data is stale."""

    def __init__(self, project_path: str, project_id: str):
        self.project_path = Path(project_path)
        self.project_id = project_id
        self.memory_root = Path.home() / ".claude-dash"
        self.project_memory = self.memory_root / "projects" / project_id

    def get_last_scan_time(self) -> float:
        """Get timestamp of last health scan."""
        health_path = self.project_memory / "health.json"
        if health_path.exists():
            try:
                with open(health_path) as f:
                    data = json.load(f)
                    ts = data.get("timestamp")
                    if ts:
                        return datetime.fromisoformat(ts).timestamp()
            except:
                pass
        return 0

    def get_embeddings_time(self) -> float:
        """Get timestamp of embeddings file."""
        emb_path = self.project_memory / "embeddings_v2.json"
        if emb_path.exists():
            return emb_path.stat().st_mtime
        return 0

    def get_changed_files(self, since: float) -> List[str]:
        """Get files modified since timestamp."""
        changed = []
        extensions = {'.js', '.jsx', '.ts', '.tsx', '.py'}
        exclude_dirs = {'node_modules', '.git', 'dist', 'build', '.next', '.worktrees', '_archived', '.venv', 'venv', 'env'}

        def scan_dir(directory: Path):
            try:
                for item in directory.iterdir():
                    if item.is_dir():
                        if item.name not in exclude_dirs:
                            scan_dir(item)
                    elif item.suffix in extensions:
                        if item.stat().st_mtime > since:
                            changed.append(str(item.relative_to(self.project_path)))
            except PermissionError:
                pass

        scan_dir(self.project_path)
        return changed

    def get_git_changes(self, since: float) -> Dict[str, List[str]]:
        """Get git changes (added, deleted, modified) since timestamp."""
        result = {"added": [], "deleted": [], "modified": []}

        try:
            # Get timestamp as git date
            since_date = datetime.fromtimestamp(since).strftime("%Y-%m-%d %H:%M:%S")

            # Get commits since date
            cmd = ["git", "-C", str(self.project_path), "log",
                   f"--since={since_date}", "--name-status", "--pretty=format:"]
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)

            for line in output.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    status, filepath = parts[0], parts[1]
                    if status == 'A':
                        result["added"].append(filepath)
                    elif status == 'D':
                        result["deleted"].append(filepath)
                    elif status in ('M', 'R'):
                        result["modified"].append(filepath)
        except:
            pass

        return result

    def check(self) -> Dict[str, Any]:
        """Check staleness of all analysis data."""
        last_scan = self.get_last_scan_time()
        embeddings_time = self.get_embeddings_time()

        changed_files = self.get_changed_files(last_scan) if last_scan > 0 else []
        git_changes = self.get_git_changes(last_scan) if last_scan > 0 else {}

        # Determine staleness (use -1 for "never" since JSON doesn't support Infinity)
        hours_since_scan = round((datetime.now().timestamp() - last_scan) / 3600, 1) if last_scan > 0 else -1
        hours_since_embeddings = round((datetime.now().timestamp() - embeddings_time) / 3600, 1) if embeddings_time > 0 else -1

        is_stale = (
            len(changed_files) > 0 or
            len(git_changes.get("added", [])) > 0 or
            len(git_changes.get("deleted", [])) > 0 or
            hours_since_scan < 0 or  # -1 means never scanned
            hours_since_scan > 24
        )

        embeddings_stale = (
            hours_since_embeddings < 0 or  # -1 means no embeddings
            hours_since_embeddings > 24 or
            len(git_changes.get("added", [])) > 0 or
            len(git_changes.get("deleted", [])) > 0
        )

        return {
            "is_stale": is_stale,
            "embeddings_stale": embeddings_stale,
            "hours_since_scan": hours_since_scan,
            "hours_since_embeddings": hours_since_embeddings,
            "changed_files": changed_files[:20],  # Limit for display
            "changed_files_count": len(changed_files),
            "git_changes": git_changes,
            "recommendation": self._get_recommendation(is_stale, embeddings_stale, len(changed_files))
        }

    def _get_recommendation(self, is_stale: bool, embeddings_stale: bool, changed_count: int) -> str:
        """Get recommendation for what to refresh."""
        if not is_stale:
            return "none"
        if embeddings_stale or changed_count > 50:
            return "full"
        return "incremental"


def main():
    import sys
    if len(sys.argv) < 3:
        print("Usage: python freshness_checker.py <project_path> <project_id>")
        sys.exit(1)

    checker = FreshnessChecker(sys.argv[1], sys.argv[2])
    result = checker.check()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
