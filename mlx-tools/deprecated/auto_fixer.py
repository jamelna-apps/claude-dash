#!/usr/bin/env python3
"""
Auto Fixer for Claude Memory System
Applies automatic fixes to individual code issues.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional

class AutoFixer:
    """Apply automatic fixes to code issues."""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)

    def get_fix(self, issue: Dict) -> Dict[str, Any]:
        """Get fix information without applying it.

        Returns preview of what will be changed.
        """
        fix_type = issue.get("type") or issue.get("fix_type")
        file_path = self.project_path / issue.get("file", "")
        line_num = issue.get("line", 0)

        if not file_path.exists():
            return {
                "can_fix": False,
                "error": "File not found"
            }

        try:
            lines = file_path.read_text(encoding='utf-8').split('\n')

            if line_num < 1 or line_num > len(lines):
                return {
                    "can_fix": False,
                    "error": "Invalid line number"
                }

            original_line = lines[line_num - 1]

            # Get the fix action
            if fix_type == "console_log" or "console.log" in issue.get("message", "").lower():
                action = "comment_out"
                fixed_line = self._fix_console_log(original_line)
            elif fix_type == "unused_import":
                action = "remove"
                fixed_line = None  # Will remove entire line
            else:
                return {
                    "can_fix": False,
                    "error": f"No auto-fix available for type: {fix_type}"
                }

            if fixed_line == original_line and fixed_line is not None:
                return {
                    "can_fix": False,
                    "error": "Line doesn't match expected pattern"
                }

            return {
                "can_fix": True,
                "file": issue.get("file"),
                "line": line_num,
                "action": action,
                "original": original_line,
                "fixed": fixed_line,
                "preview": {
                    "before": original_line.strip(),
                    "after": fixed_line.strip() if fixed_line else "[line removed]"
                }
            }

        except Exception as e:
            return {
                "can_fix": False,
                "error": str(e)
            }

    def apply_fix(self, issue: Dict) -> Dict[str, Any]:
        """Apply fix for an issue.

        Returns result with success status.
        """
        fix_type = issue.get("type") or issue.get("fix_type")
        file_path = self.project_path / issue.get("file", "")
        line_num = issue.get("line", 0)

        if not file_path.exists():
            return {
                "success": False,
                "error": "File not found"
            }

        try:
            lines = file_path.read_text(encoding='utf-8').split('\n')

            if line_num < 1 or line_num > len(lines):
                return {
                    "success": False,
                    "error": "Invalid line number"
                }

            original_line = lines[line_num - 1]

            # Apply the appropriate fix
            if fix_type == "console_log" or "console.log" in issue.get("message", "").lower():
                fixed_line = self._fix_console_log(original_line)
                action = "commented_out"
            elif fix_type == "unused_import":
                fixed_line = None
                action = "removed"
            else:
                return {
                    "success": False,
                    "error": f"No auto-fix available for type: {fix_type}"
                }

            # Verify the fix was applicable
            if fixed_line == original_line and fixed_line is not None:
                return {
                    "success": False,
                    "error": "Line doesn't match expected pattern"
                }

            # Apply the change
            if fixed_line is None:
                # Remove the line
                lines.pop(line_num - 1)
            else:
                lines[line_num - 1] = fixed_line

            # Write back to file, preserving line endings
            file_path.write_text('\n'.join(lines), encoding='utf-8')

            return {
                "success": True,
                "file": issue.get("file"),
                "line": line_num,
                "action": action,
                "original": original_line.strip(),
                "fixed": fixed_line.strip() if fixed_line else "[removed]"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _fix_console_log(self, line: str) -> Optional[str]:
        """Fix console.log statement by commenting it out.

        Returns the fixed line or None if it should be removed.
        Preserves indentation.
        """
        # Check if line contains console statement
        if not re.search(r'console\.(log|warn|debug|info)\s*\(', line):
            return line  # Not a console statement, return unchanged

        # Safety: Don't remove console.error (important for error handling)
        if 'console.error' in line:
            return line

        # Safety: Don't remove if it looks like error handling
        if 'error' in line.lower() or 'err' in line.lower():
            return line

        # Get the indentation
        indent = len(line) - len(line.lstrip())

        # Comment out the line
        return ' ' * indent + '// REMOVED: ' + line.strip()


def main():
    import sys

    if len(sys.argv) < 3:
        print(json.dumps({
            "error": "Usage: python auto_fixer.py <project_path> <issue_json>"
        }))
        sys.exit(1)

    project_path = sys.argv[1]
    try:
        issue = json.loads(sys.argv[2])
    except json.JSONDecodeError as e:
        print(json.dumps({
            "error": f"Invalid JSON: {str(e)}"
        }))
        sys.exit(1)

    fixer = AutoFixer(project_path)

    # Check if we should just preview or actually apply
    action = sys.argv[3] if len(sys.argv) > 3 else "apply"

    if action == "preview":
        result = fixer.get_fix(issue)
    else:
        result = fixer.apply_fix(issue)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
