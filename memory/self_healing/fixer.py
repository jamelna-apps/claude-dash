#!/usr/bin/env python3
"""
Cascade Fixer for Self-Healing System

Applies fixes to code when resources are removed.
Supports dry-run mode for previewing changes.
"""

import json
import re
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

# Handle both package and direct execution
try:
    from .analyzer import Impact, Severity, FixStrategy
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from analyzer import Impact, Severity, FixStrategy


@dataclass
class Fix:
    """A proposed fix for an impact."""
    file: str
    line: int
    old_text: str
    new_text: str
    strategy: FixStrategy
    confidence: float  # 0-1, how confident we are this fix is correct
    explanation: str = ""
    applied: bool = False
    error: Optional[str] = None


@dataclass
class FixResult:
    """Result of applying fixes."""
    total: int
    applied: int
    skipped: int
    errors: int
    fixes: List[Fix]
    backup_path: Optional[str] = None


class CascadeFixer:
    """
    Applies cascade fixes when resources are removed.

    Features:
    - Dry-run mode for previewing changes
    - Automatic backups before applying
    - Smart replacement strategies
    - Rollback capability
    """

    def __init__(self):
        self.memory_root = Path.home() / ".claude-dash"
        self.backup_dir = self.memory_root / "backups" / "self_heal"

        # Replacement templates for common patterns
        self.replacement_templates = {
            # Model name in quotes
            r'["\']{}["\']': '"{replacement}"',
            # Model in assignment
            r'=\s*["\']{}["\']': '= "{replacement}"',
            # Model in dict/map
            r':\s*["\']{}["\']': ': "{replacement}"',
        }

    def suggest(self, impacts: List[Impact], replacement: str = None,
                strategy: str = "replace") -> List[Fix]:
        """
        Generate fix suggestions for a list of impacts.

        Args:
            impacts: List of Impact objects from analyzer
            replacement: What to replace the resource with
            strategy: Default strategy ("replace", "remove", "comment")

        Returns:
            List of Fix objects
        """
        fixes = []

        for impact in impacts:
            fix = self._generate_fix(impact, replacement, strategy)
            if fix:
                fixes.append(fix)

        return fixes

    def _generate_fix(self, impact: Impact, replacement: str = None,
                      default_strategy: str = "replace") -> Optional[Fix]:
        """Generate a fix for a single impact."""
        # Read the actual file content
        try:
            file_path = Path(impact.file)
            if not file_path.exists():
                return None

            lines = file_path.read_text().splitlines()
            if impact.line > len(lines):
                return None

            # Get the actual line (0-indexed)
            line_idx = impact.line - 1
            old_text = lines[line_idx]

        except Exception as e:
            return Fix(
                file=impact.file,
                line=impact.line,
                old_text=impact.context,
                new_text="",
                strategy=FixStrategy.MANUAL,
                confidence=0.0,
                explanation=f"Could not read file: {e}",
                error=str(e)
            )

        # Determine fix based on strategy
        strategy = impact.fix_strategy
        new_text = old_text
        confidence = 0.8

        if strategy == FixStrategy.REPLACE and replacement:
            # Simple string replacement
            new_text = old_text.replace(impact.resource_id, replacement)
            confidence = 0.95 if new_text != old_text else 0.0

        elif strategy == FixStrategy.REMOVE:
            # Comment out the line
            if old_text.strip().startswith("#"):
                # Already a comment, just update
                new_text = old_text.replace(impact.resource_id, f"[REMOVED: {impact.resource_id}]")
                confidence = 0.9
            else:
                # Comment it out
                indent = len(old_text) - len(old_text.lstrip())
                new_text = " " * indent + "# [REMOVED] " + old_text.lstrip()
                confidence = 0.7

        elif strategy == FixStrategy.UPDATE_CONFIG:
            # For config files, do a careful replacement
            if replacement:
                new_text = old_text.replace(impact.resource_id, replacement)
                confidence = 0.9
            else:
                # Mark as needing manual update
                new_text = old_text + "  # TODO: Update - resource removed"
                confidence = 0.5

        elif strategy == FixStrategy.COMMENT:
            indent = len(old_text) - len(old_text.lstrip())
            new_text = " " * indent + "# " + old_text.lstrip()
            confidence = 0.8

        else:
            # Manual intervention needed
            confidence = 0.0

        # Don't create a fix if nothing changed and strategy isn't manual
        if new_text == old_text and strategy != FixStrategy.MANUAL:
            return None

        explanation = self._generate_explanation(impact, old_text, new_text, strategy)

        return Fix(
            file=impact.file,
            line=impact.line,
            old_text=old_text,
            new_text=new_text,
            strategy=strategy,
            confidence=confidence,
            explanation=explanation
        )

    def _generate_explanation(self, impact: Impact, old_text: str,
                              new_text: str, strategy: FixStrategy) -> str:
        """Generate explanation for a fix."""
        rel_path = impact.file.replace(str(self.memory_root) + "/", "")

        if strategy == FixStrategy.REPLACE:
            return f"Replace '{impact.resource_id}' with '{impact.suggested_replacement}' in {rel_path}"
        elif strategy == FixStrategy.REMOVE:
            return f"Comment out reference to '{impact.resource_id}' in {rel_path}"
        elif strategy == FixStrategy.UPDATE_CONFIG:
            return f"Update config in {rel_path}"
        elif strategy == FixStrategy.COMMENT:
            return f"Comment out line in {rel_path}"
        else:
            return f"Manual fix needed in {rel_path}:{impact.line}"

    def preview(self, fixes: List[Fix]) -> str:
        """Generate a preview of all fixes."""
        if not fixes:
            return "No fixes to apply."

        lines = [
            "=" * 60,
            "FIX PREVIEW",
            "=" * 60,
            f"Total fixes: {len(fixes)}",
            ""
        ]

        # Group by file
        by_file = {}
        for fix in fixes:
            if fix.file not in by_file:
                by_file[fix.file] = []
            by_file[fix.file].append(fix)

        for file_path, file_fixes in by_file.items():
            rel_path = file_path.replace(str(self.memory_root) + "/", "")
            lines.append(f"\n📄 {rel_path} ({len(file_fixes)} changes)")
            lines.append("-" * 40)

            for fix in file_fixes:
                conf_icon = "✓" if fix.confidence >= 0.8 else "?" if fix.confidence >= 0.5 else "⚠"
                lines.append(f"\n  Line {fix.line} [{conf_icon} {fix.confidence:.0%}]:")
                lines.append(f"  - {fix.old_text.strip()[:60]}...")
                lines.append(f"  + {fix.new_text.strip()[:60]}...")

        # Summary
        high_conf = sum(1 for f in fixes if f.confidence >= 0.8)
        low_conf = sum(1 for f in fixes if f.confidence < 0.5)

        lines.append("\n" + "=" * 60)
        lines.append("SUMMARY")
        lines.append(f"  High confidence (≥80%): {high_conf}")
        lines.append(f"  Low confidence (<50%):  {low_conf}")

        return "\n".join(lines)

    def apply(self, fixes: List[Fix], dry_run: bool = True,
              min_confidence: float = 0.5) -> FixResult:
        """
        Apply fixes to files.

        Args:
            fixes: List of Fix objects to apply
            dry_run: If True, only preview changes without applying
            min_confidence: Minimum confidence to apply a fix

        Returns:
            FixResult with summary of what was done
        """
        result = FixResult(
            total=len(fixes),
            applied=0,
            skipped=0,
            errors=0,
            fixes=fixes
        )

        if dry_run:
            print(self.preview(fixes))
            print("\n[DRY RUN] No changes made. Use dry_run=False to apply.")
            return result

        # Create backup
        backup_path = self._create_backup(fixes)
        result.backup_path = str(backup_path) if backup_path else None

        # Group fixes by file for efficient processing
        by_file = {}
        for fix in fixes:
            if fix.file not in by_file:
                by_file[fix.file] = []
            by_file[fix.file].append(fix)

        # Apply fixes file by file
        for file_path, file_fixes in by_file.items():
            # Sort by line number descending to avoid offset issues
            file_fixes.sort(key=lambda f: f.line, reverse=True)

            try:
                path = Path(file_path)
                lines = path.read_text().splitlines()

                for fix in file_fixes:
                    if fix.confidence < min_confidence:
                        fix.applied = False
                        result.skipped += 1
                        continue

                    line_idx = fix.line - 1
                    if 0 <= line_idx < len(lines):
                        # Verify the line matches what we expect
                        if lines[line_idx] == fix.old_text:
                            lines[line_idx] = fix.new_text
                            fix.applied = True
                            result.applied += 1
                        else:
                            fix.error = "Line content changed since analysis"
                            result.errors += 1
                    else:
                        fix.error = "Line number out of range"
                        result.errors += 1

                # Write back
                path.write_text("\n".join(lines) + "\n")

            except Exception as e:
                for fix in file_fixes:
                    if not fix.applied and not fix.error:
                        fix.error = str(e)
                        result.errors += 1

        return result

    def _create_backup(self, fixes: List[Fix]) -> Optional[Path]:
        """Create backup of files that will be modified."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / timestamp
            backup_path.mkdir(parents=True, exist_ok=True)

            files_backed_up = set()
            for fix in fixes:
                if fix.file not in files_backed_up:
                    src = Path(fix.file)
                    if src.exists():
                        # Preserve directory structure
                        rel = src.relative_to(self.memory_root)
                        dst = backup_path / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        files_backed_up.add(fix.file)

            # Save fix manifest
            manifest = {
                "timestamp": timestamp,
                "files": list(files_backed_up),
                "fixes_count": len(fixes)
            }
            (backup_path / "manifest.json").write_text(json.dumps(manifest, indent=2))

            return backup_path

        except Exception as e:
            print(f"Warning: Could not create backup: {e}")
            return None

    def rollback(self, backup_path: str) -> bool:
        """
        Rollback changes from a backup.

        Args:
            backup_path: Path to the backup directory

        Returns:
            True if successful
        """
        try:
            backup = Path(backup_path)
            if not backup.exists():
                print(f"Backup not found: {backup_path}")
                return False

            manifest_path = backup / "manifest.json"
            if not manifest_path.exists():
                print("Invalid backup: no manifest.json")
                return False

            manifest = json.loads(manifest_path.read_text())

            for file_path in manifest["files"]:
                src = Path(file_path)
                rel = src.relative_to(self.memory_root)
                backup_file = backup / rel

                if backup_file.exists():
                    shutil.copy2(backup_file, src)
                    print(f"Restored: {rel}")

            print(f"\nRollback complete. {len(manifest['files'])} files restored.")
            return True

        except Exception as e:
            print(f"Rollback failed: {e}")
            return False

    def list_backups(self) -> List[Dict]:
        """List available backups."""
        backups = []

        if not self.backup_dir.exists():
            return backups

        for backup_path in sorted(self.backup_dir.iterdir(), reverse=True):
            manifest_path = backup_path / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text())
                    manifest["path"] = str(backup_path)
                    backups.append(manifest)
                except:
                    pass

        return backups


# CLI interface
if __name__ == "__main__":
    import sys
    from .analyzer import ImpactAnalyzer

    fixer = CascadeFixer()

    if len(sys.argv) < 2:
        print("Usage: fixer.py <command> [args]")
        print("Commands:")
        print("  fix <resource_id> <replacement> [--apply]  - Fix references")
        print("  backups                                     - List backups")
        print("  rollback <backup_path>                      - Rollback changes")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "fix" and len(sys.argv) > 3:
        resource_id = sys.argv[2]
        replacement = sys.argv[3]
        apply_changes = "--apply" in sys.argv

        # Analyze impacts
        analyzer = ImpactAnalyzer()
        impacts = analyzer.analyze("ollama_model", resource_id, replacement)

        if not impacts:
            print(f"No references found for: {resource_id}")
            sys.exit(0)

        # Generate fixes
        fixes = fixer.suggest(impacts, replacement)

        if not fixes:
            print("No fixes needed.")
            sys.exit(0)

        # Apply or preview
        result = fixer.apply(fixes, dry_run=not apply_changes)

        if apply_changes:
            print(f"\nApplied: {result.applied}, Skipped: {result.skipped}, Errors: {result.errors}")
            if result.backup_path:
                print(f"Backup: {result.backup_path}")

    elif cmd == "backups":
        backups = fixer.list_backups()
        if not backups:
            print("No backups found.")
        else:
            print("Available backups:")
            for b in backups:
                print(f"  {b['timestamp']} - {b['fixes_count']} fixes, {len(b['files'])} files")
                print(f"    Path: {b['path']}")

    elif cmd == "rollback" and len(sys.argv) > 2:
        backup_path = sys.argv[2]
        fixer.rollback(backup_path)

    else:
        print(f"Unknown command: {cmd}")
