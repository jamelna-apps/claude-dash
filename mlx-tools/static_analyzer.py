#!/usr/bin/env python3
"""
Static Code Analyzer for Claude Memory System
Performs instant analysis using AST parsing and pattern matching.
"""

import os
import re
import json
import ast
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass, asdict
from enum import Enum

class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class Issue:
    id: str
    severity: str
    category: str
    message: str
    file: str
    line: int
    code_snippet: str
    fix_type: str  # "auto", "semi-auto", "assisted", "manual"
    fix_description: str

class StaticAnalyzer:
    """Fast static analysis using patterns and AST."""

    def __init__(self, project_path: str, project_id: str):
        self.project_path = Path(project_path)
        self.project_id = project_id
        self.memory_root = Path.home() / ".claude-dash"
        self.issues: List[Issue] = []
        self.issue_counter = 0
        self.files_scanned = 0
        self.files_cached = 0

    def _load_memory_data(self) -> tuple:
        """Load index.json and previous health.json for incremental scanning."""
        project_memory = self.memory_root / "projects" / self.project_id

        # Load index for file modification times
        index = {}
        index_path = project_memory / "index.json"
        if index_path.exists():
            try:
                with open(index_path) as f:
                    index = json.load(f)
            except:
                pass

        # Load previous health results
        health = {}
        health_path = project_memory / "health.json"
        if health_path.exists():
            try:
                with open(health_path) as f:
                    health = json.load(f)
            except:
                pass

        return index, health

    def _get_file_mtime(self, file_path: Path) -> str:
        """Get file modification time as ISO string."""
        try:
            mtime = file_path.stat().st_mtime
            from datetime import datetime
            return datetime.fromtimestamp(mtime).isoformat()
        except:
            return ""

    def analyze(self, incremental: bool = True) -> Dict[str, Any]:
        """Run static analysis checks.

        Args:
            incremental: If True, only scan files changed since last scan.
                        Uses memory system for caching.
        """
        self.issues = []
        self.files_scanned = 0
        self.files_cached = 0

        # Load memory data for incremental scanning
        index, prev_health = self._load_memory_data()
        last_scan = prev_health.get("timestamp", "")
        cached_issues = []

        # Build map of previous issues by file
        prev_issues_by_file = {}
        if incremental and prev_health:
            for category in ["security", "performance", "maintenance"]:
                for issue in prev_health.get("issues", {}).get(category, []):
                    file_path = issue.get("file", "")
                    if file_path not in prev_issues_by_file:
                        prev_issues_by_file[file_path] = []
                    prev_issues_by_file[file_path].append(issue)

        # Get all JS/TS files
        all_files = self._get_source_files()
        current_files = {str(f.relative_to(self.project_path)) for f in all_files}

        for file_path in all_files:
            rel_path = str(file_path.relative_to(self.project_path))
            file_mtime = self._get_file_mtime(file_path)

            # Check if we can use cached results
            if incremental and last_scan and file_mtime < last_scan:
                # File hasn't changed - use cached issues
                if rel_path in prev_issues_by_file:
                    for cached in prev_issues_by_file[rel_path]:
                        self._add_issue(**{k: v for k, v in cached.items() if k != 'id'})
                self.files_cached += 1
            else:
                # File is new or changed - scan it
                self._analyze_file(file_path)
                self.files_scanned += 1

        return {
            "score": self._calculate_score(),
            "issues": [asdict(i) for i in self.issues],
            "summary": self._get_summary(),
            "incremental_stats": {
                "files_scanned": self.files_scanned,
                "files_cached": self.files_cached,
                "cache_hit_rate": f"{(self.files_cached / max(1, self.files_scanned + self.files_cached)) * 100:.1f}%"
            }
        }

    def _get_source_files(self) -> List[Path]:
        """Get all JavaScript/TypeScript source files, excluding node_modules during traversal."""
        extensions = {'.js', '.jsx', '.ts', '.tsx', '.py'}
        files = []
        exclude_dirs = {'node_modules', '.git', 'dist', 'build', '__pycache__', '.next', '.worktrees'}

        def scan_dir(directory: Path):
            try:
                for item in directory.iterdir():
                    if item.is_dir():
                        if item.name not in exclude_dirs:
                            scan_dir(item)
                    elif item.suffix in extensions:
                        files.append(item)
            except PermissionError:
                pass

        scan_dir(self.project_path)
        return files

    def _analyze_file(self, file_path: Path):
        """Analyze a single file for issues."""
        try:
            content = file_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            rel_path = str(file_path.relative_to(self.project_path))

            # Run all checks
            self._check_security_patterns(rel_path, content, lines)
            self._check_console_logs(rel_path, content, lines)
            self._check_todo_fixme(rel_path, content, lines)
            self._check_long_functions(rel_path, content, lines)

        except Exception as e:
            pass  # Skip files that can't be read

    def _check_security_patterns(self, file_path: str, content: str, lines: List[str]):
        """Check for security issues."""
        # (pattern, message, severity, fix_type, fix_description)
        patterns = [
            (r'password\s*[=:]\s*["\'][^"\']+["\']', "Hardcoded password", Severity.CRITICAL, "assisted", "Move to environment variable"),
            (r'api[_-]?key\s*[=:]\s*["\'][^"\']+["\']', "Hardcoded API key", Severity.CRITICAL, "assisted", "Move to environment variable"),
            (r'secret\s*[=:]\s*["\'][^"\']+["\']', "Hardcoded secret", Severity.CRITICAL, "assisted", "Move to environment variable"),
            (r'\beval\s*\(', "Use of eval() - code injection risk", Severity.HIGH, "auto", "Remove eval() call"),
            (r'dangerouslySetInnerHTML', "dangerouslySetInnerHTML - XSS risk", Severity.HIGH, "semi-auto", "Use safe rendering"),
            (r'innerHTML\s*=', "Direct innerHTML assignment - XSS risk", Severity.MEDIUM, "auto", "Use textContent instead"),
            (r'document\.write\s*\(', "document.write() usage", Severity.MEDIUM, "auto", "Remove document.write()"),
        ]

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith('//') or stripped.startswith('/*'):
                continue
            for pattern, message, severity, fix_type, fix_desc in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    self._add_issue(
                        severity=severity.value,
                        category="security",
                        message=message,
                        file=file_path,
                        line=i,
                        code_snippet=line.strip()[:100],
                        fix_type=fix_type,
                        fix_description=fix_desc
                    )

    def _check_console_logs(self, file_path: str, content: str, lines: List[str]):
        """Check for console.log statements (not in comments or catch blocks)."""
        in_catch_block = False
        brace_depth_at_catch = 0
        brace_depth = 0

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Track brace depth for catch block detection
            brace_depth += line.count('{') - line.count('}')

            # Detect entering a catch block
            if re.search(r'\bcatch\s*\(', line):
                in_catch_block = True
                brace_depth_at_catch = brace_depth

            # Detect exiting the catch block
            if in_catch_block and brace_depth < brace_depth_at_catch:
                in_catch_block = False

            # Skip if line is a comment (starts with // or /*)
            if stripped.startswith('//') or stripped.startswith('/*'):
                continue

            # Skip console statements inside catch blocks (they're for error handling)
            if in_catch_block:
                continue

            # Skip lines that reference 'error' or 'err' (likely error handling)
            if re.search(r'\b(error|err)\b', line, re.IGNORECASE):
                continue

            if re.search(r'\bconsole\.(log|debug|info)\s*\(', line):
                self._add_issue(
                    severity=Severity.LOW.value,
                    category="performance",
                    message="console.log in production code",
                    file=file_path,
                    line=i,
                    code_snippet=line.strip()[:100],
                    fix_type="auto",
                    fix_description="Remove console statement"
                )

    def _check_todo_fixme(self, file_path: str, content: str, lines: List[str]):
        """Check for TODO/FIXME comments."""
        for i, line in enumerate(lines, 1):
            if re.search(r'\b(TODO|FIXME|HACK|XXX)\b', line, re.IGNORECASE):
                self._add_issue(
                    severity=Severity.LOW.value,
                    category="maintenance",
                    message="Unresolved TODO/FIXME comment",
                    file=file_path,
                    line=i,
                    code_snippet=line.strip()[:100],
                    fix_type="manual",
                    fix_description="Address or remove comment"
                )

    def _check_long_functions(self, file_path: str, content: str, lines: List[str]):
        """Check for overly long functions (>50 lines)."""
        if not file_path.endswith('.py'):
            return

        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_lines = node.end_lineno - node.lineno + 1
                    if func_lines > 50:
                        self._add_issue(
                            severity=Severity.MEDIUM.value,
                            category="maintainability",
                            message=f"Function '{node.name}' is {func_lines} lines (>50)",
                            file=file_path,
                            line=node.lineno,
                            code_snippet=f"def {node.name}(...):",
                            fix_type="assisted",
                            fix_description="Consider breaking into smaller functions"
                        )
        except:
            pass

    def _add_issue(self, **kwargs):
        """Add an issue to the list."""
        self.issue_counter += 1
        self.issues.append(Issue(
            id=f"ISSUE-{self.issue_counter:04d}",
            **kwargs
        ))

    def _calculate_score(self) -> int:
        """Calculate health score (0-100).

        Uses capped penalties per severity to handle large codebases fairly:
        - Critical: up to 20 points total
        - High: up to 15 points total
        - Medium: up to 10 points total
        - Low: up to 15 points total (scaled logarithmically)
        """
        if not self.issues:
            return 100

        # Count by severity
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for issue in self.issues:
            sev = issue.severity
            if sev in counts:
                counts[sev] += 1

        # Calculate capped penalties
        import math
        penalty = 0

        # Critical: 10 pts each, max 20
        penalty += min(20, counts["critical"] * 10)

        # High: 5 pts each, max 15
        penalty += min(15, counts["high"] * 5)

        # Medium: 2 pts each, max 10
        penalty += min(10, counts["medium"] * 2)

        # Low: logarithmic scale, max 15
        # 10 issues = 5pts, 50 issues = 10pts, 200+ issues = 15pts
        if counts["low"] > 0:
            low_penalty = min(15, int(5 * math.log10(counts["low"] + 1)))
            penalty += low_penalty

        return max(0, 100 - penalty)

    def _get_summary(self) -> Dict[str, int]:
        """Get issue counts by category."""
        summary = {"security": 0, "performance": 0, "maintenance": 0, "maintainability": 0}
        for issue in self.issues:
            if issue.category in summary:
                summary[issue.category] += 1
        return summary


def main():
    import sys

    if len(sys.argv) < 3:
        print("Usage: python static_analyzer.py <project_path> <project_id> [--full]")
        sys.exit(1)

    project_path = sys.argv[1]
    project_id = sys.argv[2]
    incremental = "--full" not in sys.argv

    analyzer = StaticAnalyzer(project_path, project_id)
    results = analyzer.analyze(incremental=incremental)

    # Print stats to stderr
    stats = results.get("incremental_stats", {})
    if stats:
        import sys as sys2
        print(f"Scanned: {stats['files_scanned']} files, Cached: {stats['files_cached']} files ({stats['cache_hit_rate']} cache hit)", file=sys2.stderr)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
