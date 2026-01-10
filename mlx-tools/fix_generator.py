#!/usr/bin/env python3
"""
Fix Generator for Claude Memory System
Applies safe auto-fixes to code issues.

Usage:
  python fix_generator.py <project_path> <project_id> [options]

Options:
  --category <cat>   Filter by category (security, performance, maintenance)
  --severity <sev>   Filter by severity (critical, high, medium, low)
  --issue-id <id>    Fix a single issue by ID
  --all              Fix all auto-fixable issues (default)
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass
class FixResult:
    success: bool
    file: str
    line: int
    fix_type: str
    message: str

class FixGenerator:
    """Apply safe fixes to code issues."""

    def __init__(self, project_path: str, project_id: str):
        self.project_path = Path(project_path)
        self.project_id = project_id
        self.memory_root = Path.home() / ".claude-dash"
        self.health_path = self.memory_root / "projects" / project_id / "health.json"
        self.results: List[FixResult] = []
        self.files_modified = set()

    def apply_fixes(self, category: Optional[str] = None, severity: Optional[str] = None,
                    issue_id: Optional[str] = None) -> Dict[str, Any]:
        """Apply fixes with optional filters.

        Args:
            category: Filter by category (security, performance, maintenance)
            severity: Filter by severity (critical, high, medium, low)
            issue_id: Fix a single issue by ID
        """
        if not self.health_path.exists():
            return {"error": "No health data found. Run a scan first."}

        with open(self.health_path) as f:
            health_data = json.load(f)

        issues = health_data.get("issues", {})

        # Collect fixable issues with filters
        fixable_issues = []
        categories = [category] if category else ["security", "performance", "maintenance"]

        for cat in categories:
            for issue in issues.get(cat, []):
                # Must be auto-fixable
                if issue.get("fix_type") != "auto":
                    continue

                # Apply severity filter
                if severity and issue.get("severity") != severity:
                    continue

                # Apply issue ID filter
                if issue_id and issue.get("id") != issue_id:
                    continue

                fixable_issues.append(issue)

        if not fixable_issues:
            filter_desc = []
            if category:
                filter_desc.append(f"category={category}")
            if severity:
                filter_desc.append(f"severity={severity}")
            if issue_id:
                filter_desc.append(f"id={issue_id}")
            filter_str = ", ".join(filter_desc) if filter_desc else "all"
            return {"fixed": 0, "files_modified": 0, "message": f"No auto-fixable issues found ({filter_str})"}

        # Group issues by file for efficient processing
        issues_by_file = {}
        for issue in fixable_issues:
            file_path = issue["file"]
            if file_path not in issues_by_file:
                issues_by_file[file_path] = []
            issues_by_file[file_path].append(issue)

        # Process each file
        for file_path, file_issues in issues_by_file.items():
            self._fix_file(file_path, file_issues)

        return {
            "fixed": len([r for r in self.results if r.success]),
            "failed": len([r for r in self.results if not r.success]),
            "files_modified": len(self.files_modified),
            "filter": {"category": category, "severity": severity, "issue_id": issue_id},
            "details": [f"{r.file}:{r.line} - {r.message}" for r in self.results[:20]]
        }

    def apply_all_safe_fixes(self) -> Dict[str, Any]:
        """Apply all auto-fixable issues (legacy method)."""
        return self.apply_fixes()

    def _fix_file(self, rel_path: str, issues: List[Dict]):
        """Apply fixes to a single file."""
        full_path = self.project_path / rel_path

        if not full_path.exists():
            for issue in issues:
                self.results.append(FixResult(
                    success=False,
                    file=rel_path,
                    line=issue["line"],
                    fix_type=issue.get("message", "unknown"),
                    message=f"File not found: {rel_path}"
                ))
            return

        try:
            content = full_path.read_text(encoding='utf-8')
            lines = content.split('\n')
            modified = False

            # Sort issues by line number in reverse order (fix from bottom up)
            issues_sorted = sorted(issues, key=lambda x: x["line"], reverse=True)

            for issue in issues_sorted:
                line_num = issue["line"] - 1  # Convert to 0-indexed
                if 0 <= line_num < len(lines):
                    original_line = lines[line_num]
                    # Pass context (previous lines) for safety checks
                    context_before = lines[max(0, line_num-5):line_num]
                    fixed_line = self._apply_fix(original_line, issue, context_before)

                    if fixed_line != original_line:
                        if fixed_line is None:
                            # Remove the line entirely
                            lines.pop(line_num)
                        else:
                            lines[line_num] = fixed_line
                        modified = True
                        self.results.append(FixResult(
                            success=True,
                            file=rel_path,
                            line=issue["line"],
                            fix_type=issue.get("message", "unknown"),
                            message="Fixed"
                        ))
                    else:
                        self.results.append(FixResult(
                            success=False,
                            file=rel_path,
                            line=issue["line"],
                            fix_type=issue.get("message", "unknown"),
                            message="Could not apply fix"
                        ))

            if modified:
                # Write back the file
                full_path.write_text('\n'.join(lines), encoding='utf-8')
                self.files_modified.add(rel_path)

        except Exception as e:
            for issue in issues:
                self.results.append(FixResult(
                    success=False,
                    file=rel_path,
                    line=issue["line"],
                    fix_type=issue.get("message", "unknown"),
                    message=f"Error: {str(e)}"
                ))

    def _apply_fix(self, line: str, issue: Dict, context_before: List[str] = None) -> str:
        """Apply a specific fix to a line. Returns None to remove line.

        Args:
            line: The line to fix
            issue: The issue dict with message, severity, etc.
            context_before: Previous lines for context (to detect catch blocks)
        """
        message = issue.get("message", "").lower()
        indent = len(line) - len(line.lstrip())

        # Safety check: Don't modify lines inside catch blocks
        if context_before:
            # Look at last 3 lines for catch block indicators
            recent_context = '\n'.join(context_before[-3:]).lower()
            if 'catch' in recent_context or '} catch' in recent_context:
                # We're likely inside a catch block - don't remove error logging
                return line  # Leave unchanged

        # Fix console.log/debug/info statements - remove the line
        # But NEVER remove console.error (that's important for error handling)
        if "console.log" in message or "console.debug" in message or "console.info" in message:
            # Safety: Don't remove if it looks like error handling
            if 'error' in line.lower() or 'err' in line.lower():
                return line  # Leave error-related logging alone
            return None  # Remove the entire line

        # Fix eval() - comment it out with warning
        if "eval()" in message:
            return ' ' * indent + '// SECURITY: eval() removed - ' + line.strip()

        # Fix innerHTML - replace with textContent
        if "innerhtml" in message:
            fixed = re.sub(r'\.innerHTML\s*=', '.textContent =', line)
            if fixed != line:
                return fixed
            return ' ' * indent + '// SECURITY: innerHTML removed - ' + line.strip()

        # Fix document.write() - remove the line
        if "document.write()" in message:
            return None  # Remove the entire line

        # For other auto-fixes, comment out the problematic code
        return ' ' * indent + '// FIXME: ' + line.strip()


def main():
    parser = argparse.ArgumentParser(description="Fix code issues")
    parser.add_argument("project_path", help="Path to the project")
    parser.add_argument("project_id", help="Project ID")
    parser.add_argument("--category", choices=["security", "performance", "maintenance"],
                        help="Filter by category")
    parser.add_argument("--severity", choices=["critical", "high", "medium", "low"],
                        help="Filter by severity")
    parser.add_argument("--issue-id", help="Fix a single issue by ID")

    args = parser.parse_args()

    fixer = FixGenerator(args.project_path, args.project_id)
    results = fixer.apply_fixes(
        category=args.category,
        severity=args.severity,
        issue_id=args.issue_id
    )

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
