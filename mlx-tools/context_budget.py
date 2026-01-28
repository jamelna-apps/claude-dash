#!/usr/bin/env python3
"""
Context Budget Dashboard for Claude-Dash

Shows HOT/WARM/COLD tier breakdown with token counts and cost estimates.
Inspired by Cortex-TMS tiered memory approach.

HOT  = Always loaded (CLAUDE.md, decisions, preferences, roadmap)
WARM = On-demand indexed content (summaries, functions)
COLD = Full file content (rarely needed)
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

MEMORY_ROOT = Path.home() / ".claude-dash"

# Token estimation: ~4 chars per token (conservative estimate)
CHARS_PER_TOKEN = 4

# Claude pricing per 1M tokens (as of 2025)
PRICING = {
    "sonnet_input": 3.00,      # $3/1M input tokens
    "sonnet_output": 15.00,    # $15/1M output tokens
    "haiku_input": 0.25,       # $0.25/1M input tokens
    "haiku_output": 1.25,      # $1.25/1M output tokens
    "opus_input": 15.00,       # $15/1M input tokens
    "opus_output": 75.00       # $75/1M output tokens
}


def estimate_tokens(text: str) -> int:
    """Estimate token count from text."""
    if not text:
        return 0
    return len(text) // CHARS_PER_TOKEN


def get_file_tokens(filepath: Path) -> int:
    """Get token count for a file."""
    try:
        if filepath.exists():
            return estimate_tokens(filepath.read_text())
    except:
        pass
    return 0


def calculate_cost(tokens: int, sessions_per_day: int = 10, days_per_month: int = 20) -> Dict[str, str]:
    """Calculate estimated costs based on token usage."""
    # Assume typical session uses tokens as input + some output
    input_tokens = tokens
    output_tokens = tokens // 4  # Assume 25% output ratio

    # Per session cost (using Sonnet as default)
    per_session_input = (input_tokens / 1_000_000) * PRICING["sonnet_input"]
    per_session_output = (output_tokens / 1_000_000) * PRICING["sonnet_output"]
    per_session = per_session_input + per_session_output

    return {
        "perSession": f"${per_session:.3f}",
        "perDay": f"${per_session * sessions_per_day:.2f}",
        "perMonth": f"${per_session * sessions_per_day * days_per_month:.2f}"
    }


class ContextBudget:
    """Calculate context budget tiers for a project."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_path = MEMORY_ROOT / "projects" / project_id
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load global config."""
        config_path = MEMORY_ROOT / "config.json"
        if config_path.exists():
            return json.loads(config_path.read_text())
        return {"projects": []}

    def _get_project_root(self) -> Optional[Path]:
        """Get project source root."""
        project_config = next(
            (p for p in self.config.get("projects", []) if p["id"] == self.project_id),
            None
        )
        if project_config:
            return Path(project_config.get("path", ""))
        return None

    def calculate_hot_tier(self) -> Dict[str, Any]:
        """
        HOT tier: Always loaded at session start.
        - CLAUDE.md files
        - decisions.json
        - preferences.json
        - roadmap.json (current sprint)
        """
        files = []
        total_tokens = 0

        project_root = self._get_project_root()

        # Global CLAUDE.md
        global_claude = MEMORY_ROOT.parent / ".claude" / "CLAUDE.md"
        if global_claude.exists():
            tokens = get_file_tokens(global_claude)
            files.append({"path": "~/.claude/CLAUDE.md", "tokens": tokens})
            total_tokens += tokens

        # Project CLAUDE.md
        if project_root:
            project_claude = project_root / "CLAUDE.md"
            if project_claude.exists():
                tokens = get_file_tokens(project_claude)
                files.append({"path": str(project_claude.relative_to(Path.home())), "tokens": tokens})
                total_tokens += tokens

        # Decisions
        decisions = self.project_path / "decisions.json"
        if decisions.exists():
            tokens = get_file_tokens(decisions)
            files.append({"path": f"projects/{self.project_id}/decisions.json", "tokens": tokens})
            total_tokens += tokens

        # Preferences
        preferences = self.project_path / "preferences.json"
        if preferences.exists():
            tokens = get_file_tokens(preferences)
            files.append({"path": f"projects/{self.project_id}/preferences.json", "tokens": tokens})
            total_tokens += tokens

        # Global preferences
        global_prefs = MEMORY_ROOT / "global" / "preferences.json"
        if global_prefs.exists():
            tokens = get_file_tokens(global_prefs)
            files.append({"path": "global/preferences.json", "tokens": tokens})
            total_tokens += tokens

        # Roadmap (active sprint only, estimate ~20% of full roadmap)
        roadmap = self.project_path / "roadmap.json"
        if roadmap.exists():
            tokens = get_file_tokens(roadmap) // 5  # Only active sprint
            files.append({"path": f"projects/{self.project_id}/roadmap.json (active sprint)", "tokens": tokens})
            total_tokens += tokens

        return {
            "description": "Active context (CLAUDE.md, decisions, preferences)",
            "files": files,
            "tokens": total_tokens
        }

    def calculate_warm_tier(self) -> Dict[str, Any]:
        """
        WARM tier: On-demand indexed content.
        - summaries.json (file summaries)
        - functions.json (function index)
        - index.json (file structure)
        """
        files = []
        total_tokens = 0

        # Summaries
        summaries = self.project_path / "summaries.json"
        if summaries.exists():
            tokens = get_file_tokens(summaries)
            files.append({"path": f"projects/{self.project_id}/summaries.json", "tokens": tokens})
            total_tokens += tokens

        # Functions index
        functions = self.project_path / "functions.json"
        if functions.exists():
            tokens = get_file_tokens(functions)
            files.append({"path": f"projects/{self.project_id}/functions.json", "tokens": tokens})
            total_tokens += tokens

        # File index
        index = self.project_path / "index.json"
        if index.exists():
            tokens = get_file_tokens(index)
            files.append({"path": f"projects/{self.project_id}/index.json", "tokens": tokens})
            total_tokens += tokens

        # Graph/navigation
        graph = self.project_path / "graph.json"
        if graph.exists():
            tokens = get_file_tokens(graph)
            files.append({"path": f"projects/{self.project_id}/graph.json", "tokens": tokens})
            total_tokens += tokens

        return {
            "description": "On-demand (indexed summaries, functions)",
            "files": files,
            "tokens": total_tokens
        }

    def calculate_cold_tier(self) -> Dict[str, Any]:
        """
        COLD tier: Full file content (estimated from project).
        This would be the cost if we read every file without memory.
        """
        project_root = self._get_project_root()
        if not project_root or not project_root.exists():
            return {
                "description": "Full file content (rarely needed)",
                "tokens": 0,
                "note": "Project path not found"
            }

        total_tokens = 0
        file_count = 0

        # Estimate from index.json if available
        index_file = self.project_path / "index.json"
        if index_file.exists():
            try:
                index_data = json.loads(index_file.read_text())
                # Get file count from structure.totalFiles or files array
                file_count = index_data.get("structure", {}).get("totalFiles", 0)
                if file_count == 0:
                    file_count = len(index_data.get("files", []))
            except:
                pass

        # Get more accurate estimate from summaries
        summaries_file = self.project_path / "summaries.json"
        if summaries_file.exists():
            try:
                summaries = json.loads(summaries_file.read_text())
                actual_tokens = 0
                files_data = summaries.get("files", {})

                if file_count == 0:
                    file_count = len(files_data)

                for file_data in files_data.values():
                    # Each summary represents ~5% of actual file
                    summary_len = len(file_data.get("summary", ""))
                    actual_tokens += summary_len * 20  # Estimate full file is 20x summary

                if actual_tokens > 0:
                    total_tokens = actual_tokens
            except:
                pass

        # Fallback/minimum estimate: ~400 tokens per file average (typical for source files)
        # Actual source files are usually 100-1000 lines, ~400 tokens is conservative
        if file_count > 0:
            min_estimate = file_count * 400
            # Use the higher of calculated or minimum estimate
            total_tokens = max(total_tokens, min_estimate)

        return {
            "description": "Full file content (rarely needed)",
            "tokens": total_tokens,
            "fileCount": file_count
        }

    def calculate_savings(self, hot: int, warm: int, cold: int) -> Dict[str, Any]:
        """Calculate token savings from using memory system.

        Without memory system:
        - Every search/query requires reading full files (COLD tier)
        - Typical session might read 20-30 files fully

        With memory system:
        - HOT tier always loaded
        - Queries hit summaries/functions (WARM tier) first
        - Only read full files when necessary
        """
        # WITHOUT memory: typical session reads ~25 full files + context
        # Assume average ~600 tokens per file read
        files_read_without = 25
        typical_without = hot + (files_read_without * 600)

        # WITH memory: only HOT + targeted lookups (~5% of WARM for summaries/functions)
        typical_with = hot + (warm // 20)

        saved = typical_without - typical_with
        percentage = int((saved / typical_without) * 100) if typical_without > 0 else 0

        # Ensure we show meaningful savings
        if saved < 0:
            # If calculated savings are negative, estimate based on cold vs warm ratio
            # The warm tier should be much smaller than cold for actual files
            estimated_full_reads = cold if cold > 0 else warm * 3
            saved = estimated_full_reads - typical_with
            percentage = int((saved / estimated_full_reads) * 100) if estimated_full_reads > 0 else 0

        return {
            "thisSession": max(0, saved),
            "percentage": max(0, min(99, percentage))  # Cap at 99%
        }

    def get_budget(self) -> Dict[str, Any]:
        """Get complete context budget breakdown."""
        hot = self.calculate_hot_tier()
        warm = self.calculate_warm_tier()
        cold = self.calculate_cold_tier()

        savings = self.calculate_savings(hot["tokens"], warm["tokens"], cold["tokens"])
        costs = calculate_cost(hot["tokens"])

        return {
            "project": self.project_id,
            "timestamp": datetime.now().isoformat(),
            "tiers": {
                "hot": hot,
                "warm": warm,
                "cold": cold
            },
            "savings": savings,
            "costs": costs,
            "summary": {
                "hotTokens": hot["tokens"],
                "warmTokens": warm["tokens"],
                "coldTokens": cold["tokens"],
                "savingsPercentage": f"{savings['percentage']}%"
            }
        }


def main():
    if len(sys.argv) < 2:
        # Show budget for all projects
        config_path = MEMORY_ROOT / "config.json"
        if not config_path.exists():
            print(json.dumps({"error": "No config.json found"}))
            sys.exit(1)

        config = json.loads(config_path.read_text())
        results = []

        for project in config.get("projects", []):
            budget = ContextBudget(project["id"])
            result = budget.get_budget()
            results.append({
                "project": project["id"],
                "hot": result["tiers"]["hot"]["tokens"],
                "warm": result["tiers"]["warm"]["tokens"],
                "cold": result["tiers"]["cold"]["tokens"],
                "savings": result["summary"]["savingsPercentage"]
            })

        print(json.dumps({"projects": results}, indent=2))
    else:
        project_id = sys.argv[1]
        budget = ContextBudget(project_id)
        result = budget.get_budget()
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
