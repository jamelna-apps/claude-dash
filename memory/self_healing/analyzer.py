#!/usr/bin/env python3
"""
Impact Analyzer for Self-Healing System

Analyzes what would break when a resource is removed and assesses severity.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from datetime import datetime

# Handle both package and direct execution
try:
    from .registry import DependencyRegistry, Resource, ResourceType, Dependent
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from registry import DependencyRegistry, Resource, ResourceType, Dependent


class Severity(Enum):
    """Impact severity levels."""
    CRITICAL = "critical"  # System won't work
    HIGH = "high"          # Major feature broken
    MEDIUM = "medium"      # Some functionality affected
    LOW = "low"            # Minor/cosmetic
    INFO = "info"          # Just informational (comments, docs)


class FixStrategy(Enum):
    """How to fix the impact."""
    REPLACE = "replace"      # Replace with alternative
    REMOVE = "remove"        # Remove the reference entirely
    COMMENT = "comment"      # Comment out the code
    UPDATE_CONFIG = "config" # Update configuration
    MANUAL = "manual"        # Requires manual intervention


@dataclass
class Impact:
    """A single impact from removing a resource."""
    resource_id: str
    file: str
    line: int
    context: str
    severity: Severity
    category: str  # "code", "config", "docs", "test"
    fix_strategy: FixStrategy
    suggested_replacement: Optional[str] = None
    explanation: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "resource_id": self.resource_id,
            "file": self.file,
            "line": self.line,
            "context": self.context,
            "severity": self.severity.value,
            "category": self.category,
            "fix_strategy": self.fix_strategy.value,
            "suggested_replacement": self.suggested_replacement,
            "explanation": self.explanation,
            "metadata": self.metadata
        }


class ImpactAnalyzer:
    """Analyzes the impact of removing a resource."""

    def __init__(self, registry: DependencyRegistry = None):
        self.registry = registry or DependencyRegistry()
        self.memory_root = Path.home() / ".claude-dash"

        # File patterns for categorization
        self.category_patterns = {
            "config": [r"config\.py", r"config\.json", r"preferences\.json", r"settings"],
            "test": [r"test_", r"_test\.py", r"\.test\.", r"__tests__"],
            "docs": [r"\.md$", r"README", r"CHANGELOG", r"docs/"],
            "code": [r"\.py$", r"\.js$", r"\.ts$"],
        }

        # Severity rules based on file/context
        self.severity_rules = [
            # Critical: Main config, core modules
            (Severity.CRITICAL, [r"config\.py", r"gateway/server\.js", r"__init__\.py"]),
            # High: Active tools, API
            (Severity.HIGH, [r"mlx-tools/.*\.py", r"api/.*\.py", r"hooks/"]),
            # Medium: Secondary tools
            (Severity.MEDIUM, [r"workers/", r"learning/"]),
            # Low: Docs, deprecated
            (Severity.LOW, [r"\.md$", r"deprecated/"]),
            # Info: Comments only
            (Severity.INFO, [r"#.*", r"//.*", r"/\*"]),
        ]

    def analyze(self, resource_type: str, resource_id: str,
                replacement: str = None) -> List[Impact]:
        """
        Analyze what would break if a resource is removed.

        Args:
            resource_type: Type of resource (e.g., "ollama_model")
            resource_id: The resource identifier
            replacement: Optional replacement to suggest

        Returns:
            List of Impact objects
        """
        # Find all dependents
        dependents = self.registry.find_dependents(resource_id, resource_type)

        impacts = []
        for dep in dependents:
            impact = self._assess_impact(resource_id, dep, replacement)
            impacts.append(impact)

        # Sort by severity (critical first)
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4
        }
        impacts.sort(key=lambda i: severity_order[i.severity])

        return impacts

    def _assess_impact(self, resource_id: str, dependent: Dependent,
                       replacement: str = None) -> Impact:
        """Assess the impact of a single dependent."""
        file_path = dependent.file
        context = dependent.context

        # Determine category
        category = self._categorize_file(file_path)

        # Determine severity
        severity = self._assess_severity(file_path, context)

        # Determine fix strategy
        fix_strategy = self._suggest_fix_strategy(category, context, replacement)

        # Generate explanation
        explanation = self._generate_explanation(
            resource_id, file_path, context, severity, category
        )

        return Impact(
            resource_id=resource_id,
            file=file_path,
            line=dependent.line,
            context=context,
            severity=severity,
            category=category,
            fix_strategy=fix_strategy,
            suggested_replacement=replacement,
            explanation=explanation,
            metadata={
                "match_type": dependent.match_type,
                "analyzed_at": datetime.now().isoformat()
            }
        )

    def _categorize_file(self, file_path: str) -> str:
        """Categorize a file based on its path/name."""
        for category, patterns in self.category_patterns.items():
            for pattern in patterns:
                if re.search(pattern, file_path):
                    return category
        return "code"  # Default

    def _assess_severity(self, file_path: str, context: str) -> Severity:
        """Assess the severity of an impact."""
        # Check if it's just a comment
        stripped = context.strip()
        if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("*"):
            return Severity.INFO

        # Check against severity rules
        for severity, patterns in self.severity_rules:
            for pattern in patterns:
                if re.search(pattern, file_path):
                    return severity

        return Severity.MEDIUM  # Default

    def _suggest_fix_strategy(self, category: str, context: str,
                              replacement: str = None) -> FixStrategy:
        """Suggest how to fix this impact."""
        # Documentation - just update text
        if category == "docs":
            return FixStrategy.REPLACE if replacement else FixStrategy.REMOVE

        # Config files - update configuration
        if category == "config":
            return FixStrategy.UPDATE_CONFIG

        # Code with replacement available
        if replacement:
            return FixStrategy.REPLACE

        # Comments - can just remove
        if context.strip().startswith(("#", "//", "*")):
            return FixStrategy.REMOVE

        # Default to manual if no clear strategy
        return FixStrategy.MANUAL

    def _generate_explanation(self, resource_id: str, file_path: str,
                              context: str, severity: Severity,
                              category: str) -> str:
        """Generate a human-readable explanation of the impact."""
        rel_path = file_path.replace(str(self.memory_root) + "/", "")

        if severity == Severity.CRITICAL:
            return f"CRITICAL: {rel_path} is a core file. Removing '{resource_id}' will break the system."
        elif severity == Severity.HIGH:
            return f"HIGH: {rel_path} uses '{resource_id}' for active functionality."
        elif severity == Severity.MEDIUM:
            return f"MEDIUM: {rel_path} references '{resource_id}' in {category} code."
        elif severity == Severity.LOW:
            return f"LOW: {rel_path} mentions '{resource_id}' in {category}."
        else:
            return f"INFO: {rel_path} contains a reference to '{resource_id}' (likely comment/doc)."

    def full_scan(self) -> Dict[str, Any]:
        """
        Perform a full health scan of the system.

        Checks:
        - Missing Ollama models that are referenced
        - Broken imports
        - Missing config keys
        """
        issues = {
            "broken": [],
            "warnings": [],
            "healthy": [],
            "scanned_at": datetime.now().isoformat()
        }

        # Sync with Ollama to find removed models
        sync_result = self.registry.sync_with_ollama()

        # Check for references to removed models
        for model_id in sync_result.get("marked_removed", []):
            dependents = self.registry.find_dependents(model_id)
            if dependents:
                for dep in dependents:
                    issues["broken"].append({
                        "type": "missing_model",
                        "resource": model_id,
                        "file": dep.file,
                        "line": dep.line,
                        "context": dep.context
                    })

        # Check for models that are referenced but not in registry
        # (This catches hardcoded model names that were never registered)
        common_models = [
            "deepseek-coder", "qwen2-math", "qwen3", "llava",
            "codellama", "mistral", "phi3"
        ]

        installed_models = set(sync_result.get("installed", []))

        for model_pattern in common_models:
            # Skip if any installed model matches this pattern
            if any(model_pattern in m for m in installed_models):
                continue

            # Search for references
            dependents = self.registry.find_dependents(model_pattern)
            for dep in dependents:
                # Skip if it's clearly a "don't use" or negative reference
                if any(neg in dep.context.lower() for neg in
                       ["not use", "don't use", "removed", "deprecated", "instead"]):
                    continue

                issues["warnings"].append({
                    "type": "potentially_missing_model",
                    "pattern": model_pattern,
                    "file": dep.file,
                    "line": dep.line,
                    "context": dep.context
                })

        # Count healthy resources
        for resource in self.registry.list_resources():
            if not resource.metadata.get("removed"):
                issues["healthy"].append(resource.id)

        return issues

    def generate_report(self, impacts: List[Impact]) -> str:
        """Generate a human-readable report of impacts."""
        if not impacts:
            return "No impacts found."

        lines = [
            "=" * 60,
            "IMPACT ANALYSIS REPORT",
            "=" * 60,
            f"Total impacts: {len(impacts)}",
            ""
        ]

        # Group by severity
        by_severity = {}
        for impact in impacts:
            sev = impact.severity.value
            if sev not in by_severity:
                by_severity[sev] = []
            by_severity[sev].append(impact)

        for severity in ["critical", "high", "medium", "low", "info"]:
            if severity in by_severity:
                lines.append(f"\n## {severity.upper()} ({len(by_severity[severity])})")
                lines.append("-" * 40)

                for impact in by_severity[severity]:
                    rel_path = impact.file.replace(str(self.memory_root) + "/", "")
                    lines.append(f"\n  {rel_path}:{impact.line}")
                    lines.append(f"  Context: {impact.context[:80]}...")
                    lines.append(f"  Fix: {impact.fix_strategy.value}")
                    if impact.suggested_replacement:
                        lines.append(f"  Replacement: {impact.suggested_replacement}")

        return "\n".join(lines)


# CLI interface
if __name__ == "__main__":
    import sys

    analyzer = ImpactAnalyzer()

    if len(sys.argv) < 2:
        print("Usage: analyzer.py <command> [args]")
        print("Commands:")
        print("  analyze <resource_id> [replacement]  - Analyze removal impact")
        print("  scan                                  - Full system health scan")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "analyze" and len(sys.argv) > 2:
        resource_id = sys.argv[2]
        replacement = sys.argv[3] if len(sys.argv) > 3 else None

        print(f"Analyzing impact of removing: {resource_id}")
        if replacement:
            print(f"Suggested replacement: {replacement}")
        print()

        impacts = analyzer.analyze("ollama_model", resource_id, replacement)
        print(analyzer.generate_report(impacts))

    elif cmd == "scan":
        print("Running full system health scan...")
        health = analyzer.full_scan()

        print(f"\n✓ Healthy resources: {len(health['healthy'])}")

        if health["broken"]:
            print(f"\n✗ Broken references: {len(health['broken'])}")
            for issue in health["broken"]:
                print(f"  - {issue['resource']} in {issue['file']}:{issue['line']}")

        if health["warnings"]:
            print(f"\n⚠ Warnings: {len(health['warnings'])}")
            for warn in health["warnings"][:5]:  # Show first 5
                print(f"  - {warn['pattern']} in {warn['file']}:{warn['line']}")

    else:
        print(f"Unknown command: {cmd}")
