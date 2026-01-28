#!/usr/bin/env python3
"""
Duplicate Code Finder for Claude Memory System
Uses embedding similarity to find duplicate/similar code.
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass, asdict
import re

# Default patterns to exclude from duplicate detection
# These are intentional architectural patterns, not actual duplicates
DEFAULT_EXCLUSIONS = [
    r'.*/index\.js$',          # Barrel exports
    r'.*/routes\.js$',         # Route definitions
    r'.*\.d\.ts$',             # TypeScript declarations
]

@dataclass
class DuplicatePair:
    file1: str
    file2: str
    similarity: float
    category: str  # "exact", "near", "similar"
    ignored: bool = False
    ignore_reason: str = None

class DuplicateFinder:
    """Find duplicate code using embedding similarity."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.memory_root = Path.home() / ".claude-dash"
        self.embeddings_path = self.memory_root / "projects" / project_id / "embeddings_v2.json"
        self.config_path = self.memory_root / "projects" / project_id / "health_config.json"
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load health config with ignore patterns."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    return json.load(f)
            except:
                pass
        return {"ignore": {"duplicates": []}, "thresholds": {}}

    def _is_ignored_pair(self, file1: str, file2: str) -> tuple:
        """Check if a file pair should be ignored. Returns (is_ignored, reason)."""
        ignore_rules = self.config.get("ignore", {}).get("duplicates", [])

        for rule in ignore_rules:
            # Check specific file pairs
            if "files" in rule:
                files = rule["files"]
                f1_name = Path(file1).name
                f2_name = Path(file2).name
                if (f1_name in files and f2_name in files):
                    return True, rule.get("reason", "Ignored by config")

            # Check patterns
            if "pattern" in rule:
                pattern = rule["pattern"]
                # Cross-directory pattern (e.g., "services/*/actions/" or "actions/*/components/")
                # Means: ignore if one file is in dir1 and other is in dir2
                if pattern.count("/") >= 2 and "*" in pattern:
                    parts = pattern.split("/")
                    dir1 = parts[0]
                    dir2 = parts[-1] if parts[-1] else parts[-2]
                    if (self._contains_dir(file1, dir1) and self._contains_dir(file2, dir2)) or \
                       (self._contains_dir(file1, dir2) and self._contains_dir(file2, dir1)):
                        return True, rule.get("reason", "Ignored by config")
                # Simple path pattern with "/" (both files must match respective parts)
                elif "/" in pattern and "*" not in pattern:
                    p1, p2 = pattern.split("/", 1)
                    if (self._matches_pattern(file1, p1) and self._matches_pattern(file2, p2)) or \
                       (self._matches_pattern(file1, p2) and self._matches_pattern(file2, p1)):
                        return True, rule.get("reason", "Ignored by config")
                else:
                    # Single pattern: ignore if BOTH files match (e.g., both are page.tsx)
                    if self._matches_pattern(file1, pattern) and self._matches_pattern(file2, pattern):
                        return True, rule.get("reason", "Ignored by config")

        return False, None

    def _contains_dir(self, filepath: str, dirname: str) -> bool:
        """Check if filepath contains the given directory name."""
        return f"/{dirname}/" in f"/{filepath}" or filepath.startswith(f"{dirname}/")

    def _matches_pattern(self, filename: str, pattern: str) -> bool:
        """Check if filename matches a simple glob pattern."""
        import fnmatch
        return fnmatch.fnmatch(Path(filename).name, pattern)

    def _should_exclude(self, filename: str) -> bool:
        """Check if file should be excluded from duplicate detection."""
        for pattern in DEFAULT_EXCLUSIONS:
            if re.match(pattern, filename):
                return True
        return False

    def find_duplicates(self, threshold: float = 0.8) -> Dict[str, Any]:
        """Find all duplicate/similar file pairs."""
        if not self.embeddings_path.exists():
            return {"error": "No embeddings found. Run: mlx build-embeddings " + self.project_id}

        with open(self.embeddings_path) as f:
            data = json.load(f)

        # Handle both old format (embeddings) and new format (files)
        files_data = data.get("files", {})
        if not files_data:
            files_data = data.get("embeddings", {})

        if not files_data:
            return {"pairs": [], "clusters": [], "total_pairs": 0, "by_category": {"exact": 0, "near": 0, "similar": 0}}

        # Extract embeddings from file data
        embeddings = {}
        for filename, file_info in files_data.items():
            if isinstance(file_info, dict) and "embedding" in file_info:
                embeddings[filename] = file_info["embedding"]
            elif isinstance(file_info, list):
                # Old format: direct embedding array
                embeddings[filename] = file_info

        # Calculate all pairwise similarities
        # Filter out excluded patterns (intentional architecture like routes.js, index.js)
        files = [f for f in embeddings.keys() if not self._should_exclude(f)]
        pairs = []

        for i, file1 in enumerate(files):
            vec1 = np.array(embeddings[file1])
            for j, file2 in enumerate(files[i+1:], i+1):
                vec2 = np.array(embeddings[file2])

                # Skip if dimensions don't match (mixed embedding models)
                if vec1.shape != vec2.shape:
                    continue

                # Cosine similarity
                norm1 = np.linalg.norm(vec1)
                norm2 = np.linalg.norm(vec2)
                if norm1 == 0 or norm2 == 0:
                    continue
                similarity = np.dot(vec1, vec2) / (norm1 * norm2)

                if similarity >= threshold:
                    is_ignored, ignore_reason = self._is_ignored_pair(file1, file2)
                    category = "exact" if similarity > 0.95 else "near" if similarity > 0.9 else "similar"
                    pairs.append(DuplicatePair(
                        file1=file1,
                        file2=file2,
                        similarity=round(float(similarity), 3),
                        category=category,
                        ignored=is_ignored,
                        ignore_reason=ignore_reason
                    ))

        # Sort by similarity (highest first)
        pairs.sort(key=lambda x: x.similarity, reverse=True)

        # Cluster similar files
        clusters = self._cluster_duplicates(pairs)

        # Filter ignored pairs for summary
        active_pairs = [p for p in pairs if not p.ignored]

        return {
            "pairs": [asdict(p) for p in pairs],
            "clusters": clusters,
            "total_pairs": len(active_pairs),  # Only count non-ignored
            "total_including_ignored": len(pairs),
            "by_category": {
                "exact": len([p for p in active_pairs if p.category == "exact"]),
                "near": len([p for p in active_pairs if p.category == "near"]),
                "similar": len([p for p in active_pairs if p.category == "similar"])
            }
        }

    def _cluster_duplicates(self, pairs: List[DuplicatePair]) -> List[List[str]]:
        """Group files into clusters of similar code."""
        if not pairs:
            return []

        # Build adjacency map
        adjacency = {}
        for pair in pairs:
            if pair.file1 not in adjacency:
                adjacency[pair.file1] = set()
            if pair.file2 not in adjacency:
                adjacency[pair.file2] = set()
            adjacency[pair.file1].add(pair.file2)
            adjacency[pair.file2].add(pair.file1)

        # Find connected components
        visited = set()
        clusters = []

        for file in adjacency:
            if file not in visited:
                cluster = []
                stack = [file]
                while stack:
                    current = stack.pop()
                    if current not in visited:
                        visited.add(current)
                        cluster.append(current)
                        stack.extend(adjacency[current] - visited)
                if len(cluster) > 1:
                    clusters.append(sorted(cluster))

        return clusters


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python duplicate_finder.py <project_id> [threshold]")
        sys.exit(1)

    project_id = sys.argv[1]
    threshold = float(sys.argv[2]) if len(sys.argv) > 2 else 0.8

    finder = DuplicateFinder(project_id)
    results = finder.find_duplicates(threshold)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
