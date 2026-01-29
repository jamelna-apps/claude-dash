#!/usr/bin/env python3
"""
Dependency Registry for Self-Healing System

Tracks resources and what depends on them. Resources include:
- Ollama models
- Python modules/functions
- Config keys
- External services

The registry can be:
1. Manually declared (for known dependencies)
2. Auto-discovered by scanning code
"""

import json
import re
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Set, Optional, Any
from enum import Enum
from datetime import datetime


class ResourceType(Enum):
    """Types of trackable resources."""
    OLLAMA_MODEL = "ollama_model"
    PYTHON_MODULE = "python_module"
    CONFIG_KEY = "config_key"
    ENV_VAR = "env_var"
    EXTERNAL_SERVICE = "external_service"
    FILE = "file"
    FUNCTION = "function"


@dataclass
class Resource:
    """A trackable resource in the system."""
    type: ResourceType
    id: str  # e.g., "deepseek-coder:6.7b", "config.OLLAMA_MODEL"
    description: str = ""
    required: bool = False  # If true, system won't work without it
    alternatives: List[str] = field(default_factory=list)  # Fallback options
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Dependent:
    """A file/location that depends on a resource."""
    file: str
    line: int
    column: int = 0
    context: str = ""  # The actual code/text
    match_type: str = "literal"  # literal, pattern, import


class DependencyRegistry:
    """
    Maintains the dependency graph for claude-dash.

    Stores:
    - Known resources and their metadata
    - What files depend on each resource
    - Patterns for auto-discovery
    """

    def __init__(self):
        self.memory_root = Path.home() / ".claude-dash"
        self.registry_path = self.memory_root / "memory" / "dependency_registry.json"
        self.resources: Dict[str, Resource] = {}
        self.dependents: Dict[str, List[Dependent]] = {}  # resource_id -> dependents
        self.discovery_patterns: Dict[str, List[str]] = {}

        self._load()
        self._init_default_patterns()

    def _load(self):
        """Load registry from disk."""
        if self.registry_path.exists():
            try:
                data = json.loads(self.registry_path.read_text())
                for r in data.get("resources", []):
                    res = Resource(
                        type=ResourceType(r["type"]),
                        id=r["id"],
                        description=r.get("description", ""),
                        required=r.get("required", False),
                        alternatives=r.get("alternatives", []),
                        metadata=r.get("metadata", {})
                    )
                    self.resources[res.id] = res

                self.discovery_patterns = data.get("patterns", {})
            except Exception as e:
                print(f"Warning: Could not load registry: {e}")

    def _save(self):
        """Persist registry to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0",
            "updated": datetime.now().isoformat(),
            "resources": [
                {
                    "type": r.type.value,
                    "id": r.id,
                    "description": r.description,
                    "required": r.required,
                    "alternatives": r.alternatives,
                    "metadata": r.metadata
                }
                for r in self.resources.values()
            ],
            "patterns": self.discovery_patterns
        }

        self.registry_path.write_text(json.dumps(data, indent=2))

    def _init_default_patterns(self):
        """Initialize default discovery patterns for common resources."""
        if not self.discovery_patterns:
            self.discovery_patterns = {
                # Ollama model patterns
                "ollama_model": [
                    r"['\"]([a-z0-9_-]+:[a-z0-9._-]+)['\"]",  # "model:tag"
                    r"OLLAMA_MODEL\s*=\s*['\"]([^'\"]+)['\"]",
                    r"model\s*=\s*['\"]([a-z0-9_-]+:[a-z0-9._-]+)['\"]",
                ],
                # Config key patterns
                "config_key": [
                    r"get_model_for_task\(['\"]([^'\"]+)['\"]",
                    r"TASK_MODEL_MAP\[['\"]([^'\"]+)['\"]",
                ],
                # Environment variable patterns
                "env_var": [
                    r"os\.environ\.get\(['\"]([^'\"]+)['\"]",
                    r"\$\{?([A-Z_]+)\}?",
                ],
            }
            self._save()

    def register(self, resource: Resource) -> None:
        """Register a resource."""
        self.resources[resource.id] = resource
        self._save()

    def unregister(self, resource_id: str) -> Optional[Resource]:
        """Unregister a resource. Returns the removed resource."""
        resource = self.resources.pop(resource_id, None)
        if resource:
            self._save()
        return resource

    def get(self, resource_id: str) -> Optional[Resource]:
        """Get a resource by ID."""
        return self.resources.get(resource_id)

    def list_resources(self, resource_type: ResourceType = None) -> List[Resource]:
        """List all resources, optionally filtered by type."""
        resources = list(self.resources.values())
        if resource_type:
            resources = [r for r in resources if r.type == resource_type]
        return resources

    def discover_ollama_models(self) -> List[Resource]:
        """Auto-discover installed Ollama models."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return []

            models = []
            for line in result.stdout.strip().split("\n")[1:]:  # Skip header
                if line.strip():
                    parts = line.split()
                    if parts:
                        model_name = parts[0]
                        size = parts[2] if len(parts) > 2 else "unknown"
                        models.append(Resource(
                            type=ResourceType.OLLAMA_MODEL,
                            id=model_name,
                            description=f"Ollama model ({size})",
                            metadata={"size": size, "discovered": True}
                        ))
            return models
        except Exception as e:
            print(f"Could not discover Ollama models: {e}")
            return []

    def find_dependents(self, resource_id: str, resource_type: str = None,
                        scan_paths: List[str] = None) -> List[Dependent]:
        """
        Find all files that reference a resource.

        Args:
            resource_id: The resource identifier (e.g., "deepseek-coder:6.7b")
            resource_type: Type hint for pattern selection
            scan_paths: Paths to scan (default: claude-dash directory)

        Returns:
            List of Dependent objects showing where the resource is used
        """
        if scan_paths is None:
            scan_paths = [str(self.memory_root)]

        dependents = []

        # Escape special regex characters in resource_id for literal matching
        escaped_id = re.escape(resource_id)

        # Build search patterns
        patterns = [escaped_id]  # Always search for literal

        # Add type-specific patterns
        if resource_type and resource_type in self.discovery_patterns:
            # These patterns are for discovery, not for finding this specific resource
            pass

        # Use ripgrep for fast searching
        for scan_path in scan_paths:
            try:
                result = subprocess.run(
                    [
                        "rg", "--json", "--no-heading",
                        "-g", "*.py", "-g", "*.js", "-g", "*.json", "-g", "*.md", "-g", "*.sh",
                        "-g", "!node_modules", "-g", "!*.pyc", "-g", "!__pycache__",
                        "-g", "!deprecated",  # Skip deprecated folder
                        escaped_id, scan_path
                    ],
                    capture_output=True, text=True, timeout=30
                )

                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("type") == "match":
                            match_data = data["data"]
                            file_path = match_data["path"]["text"]
                            line_num = match_data["line_number"]
                            context = match_data["lines"]["text"].strip()

                            # Skip if it's the registry itself
                            if "dependency_registry.json" in file_path:
                                continue

                            dependents.append(Dependent(
                                file=file_path,
                                line=line_num,
                                context=context,
                                match_type="literal"
                            ))
                    except json.JSONDecodeError:
                        continue

            except subprocess.TimeoutExpired:
                print(f"Search timed out for {scan_path}")
            except FileNotFoundError:
                # ripgrep not installed, fall back to grep
                dependents.extend(self._grep_fallback(escaped_id, scan_path))

        return dependents

    def _grep_fallback(self, pattern: str, scan_path: str) -> List[Dependent]:
        """Fallback to grep if ripgrep not available."""
        dependents = []
        try:
            result = subprocess.run(
                ["grep", "-rn", "--include=*.py", "--include=*.js",
                 "--include=*.json", "--include=*.md", "--include=*.sh",
                 pattern, scan_path],
                capture_output=True, text=True, timeout=30
            )

            for line in result.stdout.strip().split("\n"):
                if not line or "dependency_registry.json" in line:
                    continue
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    dependents.append(Dependent(
                        file=parts[0],
                        line=int(parts[1]),
                        context=parts[2].strip(),
                        match_type="literal"
                    ))
        except Exception:
            pass

        return dependents

    def sync_with_ollama(self) -> Dict[str, Any]:
        """
        Sync registry with actual Ollama state.
        Returns summary of changes.
        """
        installed = {m.id for m in self.discover_ollama_models()}
        registered = {
            r.id for r in self.resources.values()
            if r.type == ResourceType.OLLAMA_MODEL
        }

        added = []
        removed = []

        # Add newly installed models
        for model_id in installed - registered:
            self.register(Resource(
                type=ResourceType.OLLAMA_MODEL,
                id=model_id,
                description="Auto-discovered Ollama model",
                metadata={"discovered": True, "synced": datetime.now().isoformat()}
            ))
            added.append(model_id)

        # Mark removed models (but don't delete from registry - they might have dependents)
        for model_id in registered - installed:
            resource = self.resources.get(model_id)
            if resource:
                resource.metadata["removed"] = True
                resource.metadata["removed_at"] = datetime.now().isoformat()
                removed.append(model_id)

        self._save()

        return {
            "installed": list(installed),
            "added_to_registry": added,
            "marked_removed": removed
        }


# CLI interface
if __name__ == "__main__":
    import sys

    registry = DependencyRegistry()

    if len(sys.argv) < 2:
        print("Usage: registry.py <command> [args]")
        print("Commands: list, sync, find <resource_id>, register <type> <id>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        resources = registry.list_resources()
        if not resources:
            print("No resources registered. Run 'sync' to discover Ollama models.")
        for r in resources:
            status = "❌ REMOVED" if r.metadata.get("removed") else "✓"
            print(f"  {status} [{r.type.value}] {r.id}")
            if r.description:
                print(f"      {r.description}")

    elif cmd == "sync":
        result = registry.sync_with_ollama()
        print(f"Installed models: {result['installed']}")
        if result["added_to_registry"]:
            print(f"Added to registry: {result['added_to_registry']}")
        if result["marked_removed"]:
            print(f"Marked as removed: {result['marked_removed']}")

    elif cmd == "find" and len(sys.argv) > 2:
        resource_id = sys.argv[2]
        dependents = registry.find_dependents(resource_id)
        if not dependents:
            print(f"No files reference '{resource_id}'")
        else:
            print(f"Found {len(dependents)} reference(s) to '{resource_id}':")
            for d in dependents:
                print(f"  {d.file}:{d.line}")
                print(f"    {d.context[:100]}...")

    elif cmd == "register" and len(sys.argv) > 3:
        res_type = sys.argv[2]
        res_id = sys.argv[3]
        try:
            registry.register(Resource(
                type=ResourceType(res_type),
                id=res_id,
                description=sys.argv[4] if len(sys.argv) > 4 else ""
            ))
            print(f"Registered: {res_type}/{res_id}")
        except ValueError:
            print(f"Invalid type: {res_type}")
            print(f"Valid types: {[t.value for t in ResourceType]}")

    else:
        print(f"Unknown command: {cmd}")
