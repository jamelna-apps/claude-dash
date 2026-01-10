#!/usr/bin/env python3
"""
Dead Code Detector for Claude Memory System
Finds unused exports, orphan files, and unreachable functions.
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Set, Any
from dataclasses import dataclass, asdict

@dataclass
class DeadCode:
    type: str  # "unused_export", "orphan_file", "unused_function"
    name: str
    file: str
    line: int
    confidence: str  # "high", "medium", "low"
    reason: str

class DeadCodeDetector:
    """Find dead code using import analysis."""

    def __init__(self, project_path: str, project_id: str):
        self.project_path = Path(project_path)
        self.project_id = project_id
        self.memory_root = Path.home() / ".claude-dash"

        # Load existing memory data
        self.functions = self._load_json("functions.json")
        self.summaries = self._load_json("summaries.json")

        # Load health config
        self.config_path = self.memory_root / "projects" / self.project_id / "health_config.json"
        self.config = self._load_config()

    def _load_json(self, filename: str) -> Dict:
        path = self.memory_root / "projects" / self.project_id / filename
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {}

    def _load_config(self) -> Dict:
        """Load health config with ignore patterns."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    return json.load(f)
            except:
                pass
        return {"ignore": {"dead_code": []}, "exclude_dirs": []}

    def _is_ignored(self, file_path: str, name: str = None) -> tuple:
        """Check if dead code item should be ignored. Returns (is_ignored, reason)."""
        import fnmatch
        ignore_rules = self.config.get("ignore", {}).get("dead_code", [])

        for rule in ignore_rules:
            # Check specific file
            if "file" in rule:
                if Path(file_path).name == rule["file"] or file_path == rule["file"]:
                    return True, rule.get("reason", "Ignored by config")

            # Check pattern
            if "pattern" in rule:
                if fnmatch.fnmatch(file_path, rule["pattern"]):
                    return True, rule.get("reason", "Ignored by config")

        return False, None

    def _get_ast_analysis(self, file_path: Path) -> Dict:
        """Get AST analysis for a file using Node.js analyzer."""
        import subprocess

        ast_analyzer = self.memory_root / "mlx-tools" / "ast_analyzer.js"

        try:
            result = subprocess.run(
                ["node", str(ast_analyzer), str(file_path)],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            return {}
        except:
            return {}

    def _build_import_graph_ast(self) -> Dict[str, Set[str]]:
        """Build import graph using AST analysis (more accurate)."""
        imports = {}

        for file_path in self._get_source_files():
            rel_path = str(file_path.relative_to(self.project_path))
            imports[rel_path] = set()

            analysis = self._get_ast_analysis(file_path)
            if not analysis or "error" in analysis:
                continue

            file_analysis = analysis.get(str(file_path), analysis)

            for imp in file_analysis.get("imports", []):
                source = imp.get("source", "")
                if source.startswith('.'):
                    resolved = self._resolve_import(file_path, source)
                    if resolved:
                        imports[rel_path].add(resolved)

            # Also track navigation references as "imports"
            for nav in file_analysis.get("navigation_refs", []):
                screen = nav.get("screen", "")
                if screen:
                    # Find screen file
                    for f in self._get_source_files():
                        if screen in f.stem:
                            imports[rel_path].add(str(f.relative_to(self.project_path)))

        return imports

    def detect(self) -> Dict[str, Any]:
        """Run dead code detection."""
        dead_code = []

        # Try AST-based analysis first (more accurate)
        try:
            imports = self._build_import_graph_ast()
        except Exception as e:
            # Fallback to regex-based analysis
            import sys
            print(f"AST analysis failed, using regex fallback: {e}", file=sys.stderr)
            imports = self._build_import_graph()

        exports = self._build_export_map()

        # Find unused exports
        dead_code.extend(self._find_unused_exports(imports, exports))

        # Find orphan files
        dead_code.extend(self._find_orphan_files(imports))

        # Find unused functions (from functions.json)
        dead_code.extend(self._find_unused_functions())

        return {
            "dead_code": [asdict(d) for d in dead_code],
            "summary": {
                "unused_exports": len([d for d in dead_code if d.type == "unused_export"]),
                "orphan_files": len([d for d in dead_code if d.type == "orphan_file"]),
                "unused_functions": len([d for d in dead_code if d.type == "unused_function"])
            }
        }

    def _build_import_graph(self) -> Dict[str, Set[str]]:
        """Build a map of file -> imported files."""
        imports = {}

        for file_path in self._get_source_files():
            rel_path = str(file_path.relative_to(self.project_path))
            imports[rel_path] = set()

            try:
                content = file_path.read_text(encoding='utf-8')

                # Match import/require statements
                patterns = [
                    r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
                    r'import\s*\([\'"]([^\'"]+)[\'"]\)',
                    r'require\s*\([\'"]([^\'"]+)[\'"]\)',
                ]

                for pattern in patterns:
                    for match in re.finditer(pattern, content):
                        imported = match.group(1)
                        # Resolve relative imports
                        if imported.startswith('.'):
                            resolved = self._resolve_import(file_path, imported)
                            if resolved:
                                imports[rel_path].add(resolved)

            except:
                pass

        return imports

    def _resolve_import(self, from_file: Path, import_path: str) -> str:
        """Resolve a relative import to a file path."""
        from_dir = from_file.parent

        # Handle relative paths
        if import_path.startswith('./'):
            import_path = import_path[2:]
        elif import_path.startswith('../'):
            parts = import_path.split('/')
            up_count = 0
            while parts and parts[0] == '..':
                parts.pop(0)
                up_count += 1
            from_dir = from_dir.parents[up_count - 1] if up_count > 0 else from_dir.parent
            import_path = '/'.join(parts)

        # Try different extensions
        extensions = ['', '.js', '.jsx', '.ts', '.tsx', '/index.js', '/index.ts']
        for ext in extensions:
            candidate = from_dir / (import_path + ext)
            if candidate.exists():
                try:
                    return str(candidate.relative_to(self.project_path))
                except:
                    pass

        return None

    def _build_export_map(self) -> Dict[str, List[Dict]]:
        """Build a map of file -> exported names."""
        exports = {}

        for file_path in self._get_source_files():
            rel_path = str(file_path.relative_to(self.project_path))
            exports[rel_path] = []

            try:
                content = file_path.read_text(encoding='utf-8')
                lines = content.split('\n')

                for i, line in enumerate(lines, 1):
                    # export const/let/var/function/class
                    match = re.match(r'export\s+(const|let|var|function|class|async function)\s+(\w+)', line)
                    if match:
                        exports[rel_path].append({"name": match.group(2), "line": i})

                    # export { name }
                    match = re.match(r'export\s*\{([^}]+)\}', line)
                    if match:
                        names = [n.strip().split(' as ')[0] for n in match.group(1).split(',')]
                        for name in names:
                            exports[rel_path].append({"name": name.strip(), "line": i})

                    # export default
                    if re.match(r'export\s+default\s+', line):
                        exports[rel_path].append({"name": "default", "line": i})

            except:
                pass

        return exports

    def _find_unused_exports(self, imports: Dict, exports: Dict) -> List[DeadCode]:
        """Find exports that are never imported."""
        dead = []

        # Build set of all imported files
        all_imported = set()
        for file_imports in imports.values():
            all_imported.update(file_imports)

        # Check each export
        for file_path, file_exports in exports.items():
            if not file_exports:
                continue

            # Skip entry points
            if any(entry in file_path for entry in ['index.', 'App.', 'main.', '_app.', '_document.']):
                continue

            # If file is never imported, all its exports are unused
            if file_path not in all_imported:
                is_ignored, ignore_reason = self._is_ignored(file_path)
                for exp in file_exports:
                    dead.append(DeadCode(
                        type="unused_export",
                        name=exp["name"],
                        file=file_path,
                        line=exp["line"],
                        confidence="low" if is_ignored else "medium",
                        reason=ignore_reason if is_ignored else "File is never imported"
                    ))

        return dead

    def _find_orphan_files(self, imports: Dict) -> List[DeadCode]:
        """Find files that are never imported and don't import anything."""
        dead = []

        all_imported = set()
        for file_imports in imports.values():
            all_imported.update(file_imports)

        for file_path, file_imports in imports.items():
            # Skip known entry points and configs
            if any(entry in file_path for entry in ['index.', 'App.', 'main.', 'config', 'test', 'spec', '.d.ts']):
                continue

            # Orphan: not imported and doesn't import much
            if file_path not in all_imported and len(file_imports) < 2:
                dead.append(DeadCode(
                    type="orphan_file",
                    name=file_path,
                    file=file_path,
                    line=1,
                    confidence="low",
                    reason="File is never imported and has few dependencies"
                ))

        return dead

    def _find_unused_functions(self) -> List[DeadCode]:
        """Find functions defined but potentially never called."""
        dead = []

        functions = self.functions.get("functions", {})

        # Count function name occurrences across all files
        name_counts = {}
        for name, locations in functions.items():
            # Skip common names and hooks
            if name.startswith('use') or name in ['render', 'constructor', 'componentDidMount']:
                continue
            name_counts[name] = len(locations)

        # Functions defined in only one place might be unused
        # (This is a heuristic - would need call graph for accuracy)
        for name, count in name_counts.items():
            if count == 1:
                locations = functions[name]
                dead.append(DeadCode(
                    type="unused_function",
                    name=name,
                    file=locations[0]["file"],
                    line=locations[0]["line"],
                    confidence="low",
                    reason="Function defined but no other references found"
                ))

        return dead

    def _get_source_files(self) -> List[Path]:
        """Get all source files, excluding configured directories."""
        extensions = {'.js', '.jsx', '.ts', '.tsx'}
        files = []
        # Merge default and config excludes
        config_excludes = set(self.config.get("exclude_dirs", []))
        exclude_dirs = {'node_modules', '.git', 'dist', 'build', '.next', '.worktrees'} | config_excludes

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


def main():
    import sys

    if len(sys.argv) < 3:
        print("Usage: python dead_code_detector.py <project_path> <project_id>")
        sys.exit(1)

    project_path = sys.argv[1]
    project_id = sys.argv[2]

    detector = DeadCodeDetector(project_path, project_id)
    results = detector.detect()

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
