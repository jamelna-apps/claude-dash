#!/usr/bin/env python3
"""
Code Health Orchestrator for Claude Memory System
Combines all analyzers and manages health.json state.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# Import analyzers
from static_analyzer import StaticAnalyzer
from duplicate_finder import DuplicateFinder
from dead_code_detector import DeadCodeDetector
from freshness_checker import FreshnessChecker

class CodeHealthOrchestrator:
    """Orchestrate all code health analyzers."""

    def __init__(self, project_path: str, project_id: str):
        self.project_path = project_path
        self.project_id = project_id
        self.memory_root = Path.home() / ".claude-dash"
        self.health_path = self.memory_root / "projects" / project_id / "health.json"
        self.history_path = self.memory_root / "projects" / project_id / "health_history.json"

    def run_quick_scan(self, incremental: bool = True) -> Dict[str, Any]:
        """Run fast static analysis.

        Args:
            incremental: If True, only scan files changed since last scan.
        """
        mode = "incremental" if incremental else "full"
        print(f"Running {mode} scan...", file=sys.stderr)

        # Check freshness first
        freshness = FreshnessChecker(self.project_path, self.project_id)
        freshness_result = freshness.check()

        # Auto-rebuild embeddings if stale
        if freshness_result.get("embeddings_stale"):
            print("Embeddings are stale, rebuilding...", file=sys.stderr)
            self._rebuild_embeddings()

        # Static analysis (with incremental support)
        static = StaticAnalyzer(self.project_path, self.project_id)
        static_results = static.analyze(incremental=incremental)

        # Show incremental stats
        inc_stats = static_results.get("incremental_stats", {})
        if inc_stats:
            print(f"  Static: {inc_stats['files_scanned']} scanned, {inc_stats['files_cached']} cached ({inc_stats['cache_hit_rate']})", file=sys.stderr)

        # Duplicates (fast - uses precomputed embeddings)
        duplicates = DuplicateFinder(self.project_id)
        duplicate_results = duplicates.find_duplicates()
        print(f"  Duplicates: {duplicate_results.get('total_pairs', 0)} pairs found", file=sys.stderr)

        # Dead code (uses functions.json and summaries.json)
        dead_code = DeadCodeDetector(self.project_path, self.project_id)
        dead_code_results = dead_code.detect()
        print(f"  Dead code: {len(dead_code_results.get('dead_code', []))} items found", file=sys.stderr)

        # Combine results
        results = {
            "scan_type": mode,
            "timestamp": datetime.now().isoformat(),
            "freshness": freshness_result,
            "score": self._calculate_combined_score(static_results, duplicate_results, dead_code_results),
            "issues": {
                "security": [i for i in static_results["issues"] if i["category"] == "security"],
                "performance": [i for i in static_results["issues"] if i["category"] == "performance"],
                "maintenance": [i for i in static_results["issues"] if i["category"] == "maintenance"],
                "duplicates": duplicate_results.get("pairs", [])[:20],  # Top 20
                "dead_code": dead_code_results.get("dead_code", [])[:20]  # Top 20
            },
            "summary": {
                "security": len([i for i in static_results["issues"] if i["category"] == "security"]),
                "performance": len([i for i in static_results["issues"] if i["category"] == "performance"]),
                "duplicates": duplicate_results.get("total_pairs", 0),
                "dead_code": len(dead_code_results.get("dead_code", []))
            },
            "incremental_stats": inc_stats
        }

        # Save results
        self._save_results(results)

        return results

    def _calculate_combined_score(self, static: Dict, duplicates: Dict, dead_code: Dict) -> int:
        """Calculate overall health score.

        Combines static analysis score with duplicate and dead code penalties.
        Uses logarithmic scaling for large numbers to be fair to big codebases.
        """
        import math
        score = static.get("score", 100)

        # Penalize for duplicates (log scale, max 10 pts)
        # 10 pairs = 5pts, 50 pairs = 8pts, 100+ pairs = 10pts
        dup_count = duplicates.get("total_pairs", 0)
        if dup_count > 0:
            dup_penalty = min(10, int(5 * math.log10(dup_count + 1)))
            score -= dup_penalty

        # Penalize for dead code (log scale, max 10 pts)
        # 100 items = 5pts, 500 items = 7pts, 1000+ items = 10pts
        dead_count = len(dead_code.get("dead_code", []))
        if dead_count > 0:
            dead_penalty = min(10, int(3 * math.log10(dead_count + 1)))
            score -= dead_penalty

        return max(0, score)

    def _rebuild_embeddings(self):
        """Rebuild embeddings for the project."""
        import subprocess
        mlx_env = self.memory_root / "mlx-env" / "bin" / "python3"
        embeddings_script = self.memory_root / "mlx-tools" / "embeddings_v2.py"

        try:
            subprocess.run([
                str(mlx_env),
                str(embeddings_script),
                self.project_id,
                "build"
            ], capture_output=True, timeout=120)
            print("Embeddings rebuilt successfully", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not rebuild embeddings: {e}", file=sys.stderr)

    def _save_results(self, results: Dict):
        """Save results to health.json and update history."""
        # Ensure directory exists
        self.health_path.parent.mkdir(parents=True, exist_ok=True)

        # Save current health
        with open(self.health_path, 'w') as f:
            json.dump(results, f, indent=2)

        # Update history
        history = []
        if self.history_path.exists():
            with open(self.history_path) as f:
                history = json.load(f)

        history.append({
            "timestamp": results["timestamp"],
            "score": results["score"],
            "summary": results["summary"]
        })

        # Keep last 100 entries
        history = history[-100:]

        with open(self.history_path, 'w') as f:
            json.dump(history, f, indent=2)

    def get_health(self) -> Dict[str, Any]:
        """Get current health data."""
        if self.health_path.exists():
            with open(self.health_path) as f:
                return json.load(f)
        return {"error": "No health data. Run a scan first."}


def main():
    if len(sys.argv) < 3:
        print("Usage: python code_health.py <project_path> <project_id> [command] [--full]")
        print("Commands: scan (default), status")
        print("Options: --full  Force full rescan (ignore cache)")
        sys.exit(1)

    project_path = sys.argv[1]
    project_id = sys.argv[2]
    command = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith('-') else "scan"
    incremental = "--full" not in sys.argv

    orchestrator = CodeHealthOrchestrator(project_path, project_id)

    if command == "scan":
        results = orchestrator.run_quick_scan(incremental=incremental)
    elif command == "status":
        results = orchestrator.get_health()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
