"""
Self-Healing System for Claude-Dash

Automatically detects and fixes broken dependencies when resources are removed.

Components:
- Registry: Tracks resources and their dependents
- Analyzer: Finds impact when a resource is removed
- Fixer: Proposes and applies cascade fixes

Usage:
    from memory.self_healing import SelfHealer

    healer = SelfHealer()

    # Check what would break if we remove a model
    impact = healer.analyze_removal("ollama_model", "deepseek-coder:6.7b")

    # Get fix suggestions
    fixes = healer.suggest_fixes(impact, replacement="gemma3:4b-it-qat")

    # Apply fixes
    healer.apply_fixes(fixes, dry_run=False)
"""

from .registry import DependencyRegistry, Resource, ResourceType
from .analyzer import ImpactAnalyzer, Impact
from .fixer import CascadeFixer, Fix

class SelfHealer:
    """Main interface for self-healing operations."""

    def __init__(self):
        self.registry = DependencyRegistry()
        self.analyzer = ImpactAnalyzer(self.registry)
        self.fixer = CascadeFixer()

    def analyze_removal(self, resource_type: str, resource_id: str) -> list:
        """Analyze what would break if a resource is removed."""
        return self.analyzer.analyze(resource_type, resource_id)

    def suggest_fixes(self, impacts: list, replacement: str = None,
                      strategy: str = "replace") -> list:
        """Generate fix suggestions for the impacts."""
        return self.fixer.suggest(impacts, replacement, strategy)

    def apply_fixes(self, fixes: list, dry_run: bool = True) -> dict:
        """Apply fixes. Returns summary of changes."""
        return self.fixer.apply(fixes, dry_run)

    def check_health(self) -> dict:
        """Check overall system health for broken dependencies."""
        return self.analyzer.full_scan()

    def auto_heal(self, dry_run: bool = True) -> dict:
        """Automatically detect and fix all broken dependencies."""
        health = self.check_health()
        all_fixes = []

        for issue in health.get("broken", []):
            fixes = self.suggest_fixes([issue])
            all_fixes.extend(fixes)

        if all_fixes:
            return self.apply_fixes(all_fixes, dry_run)

        return {"status": "healthy", "fixes_needed": 0}


__all__ = [
    "SelfHealer",
    "DependencyRegistry",
    "Resource",
    "ResourceType",
    "ImpactAnalyzer",
    "Impact",
    "CascadeFixer",
    "Fix"
]
