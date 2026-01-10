# Health Tool Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the code health tool into an accurate, auto-refreshing system with ignore lists, better detection, and an interactive dashboard UI.

**Architecture:** Python analyzers detect issues, Node.js server exposes REST API, vanilla JS dashboard renders interactive UI. Data persists in JSON files per project. AST parsing via Node.js subprocess for accuracy.

**Tech Stack:** Python 3.9+, Node.js, vanilla JS, Chart.js for trends, acorn for AST parsing

---

## Phase 1: Foundation

### Task 1: Create Freshness Checker

**Files:**
- Create: `~/.claude-memory/mlx-tools/freshness_checker.py`

**Step 1: Create the freshness checker module**

```python
#!/usr/bin/env python3
"""
Freshness Checker for Claude Memory System
Detects when analysis data is stale and needs refresh.
"""

import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

class FreshnessChecker:
    """Check if project analysis data is stale."""

    def __init__(self, project_path: str, project_id: str):
        self.project_path = Path(project_path)
        self.project_id = project_id
        self.memory_root = Path.home() / ".claude-memory"
        self.project_memory = self.memory_root / "projects" / project_id

    def get_last_scan_time(self) -> float:
        """Get timestamp of last health scan."""
        health_path = self.project_memory / "health.json"
        if health_path.exists():
            try:
                with open(health_path) as f:
                    data = json.load(f)
                    ts = data.get("timestamp")
                    if ts:
                        return datetime.fromisoformat(ts).timestamp()
            except:
                pass
        return 0

    def get_embeddings_time(self) -> float:
        """Get timestamp of embeddings file."""
        emb_path = self.project_memory / "embeddings_v2.json"
        if emb_path.exists():
            return emb_path.stat().st_mtime
        return 0

    def get_changed_files(self, since: float) -> List[str]:
        """Get files modified since timestamp."""
        changed = []
        extensions = {'.js', '.jsx', '.ts', '.tsx', '.py'}
        exclude_dirs = {'node_modules', '.git', 'dist', 'build', '.next', '.worktrees', '_archived'}

        def scan_dir(directory: Path):
            try:
                for item in directory.iterdir():
                    if item.is_dir():
                        if item.name not in exclude_dirs:
                            scan_dir(item)
                    elif item.suffix in extensions:
                        if item.stat().st_mtime > since:
                            changed.append(str(item.relative_to(self.project_path)))
            except PermissionError:
                pass

        scan_dir(self.project_path)
        return changed

    def get_git_changes(self, since: float) -> Dict[str, List[str]]:
        """Get git changes (added, deleted, modified) since timestamp."""
        result = {"added": [], "deleted": [], "modified": []}

        try:
            # Get timestamp as git date
            since_date = datetime.fromtimestamp(since).strftime("%Y-%m-%d %H:%M:%S")

            # Get commits since date
            cmd = ["git", "-C", str(self.project_path), "log",
                   f"--since={since_date}", "--name-status", "--pretty=format:"]
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)

            for line in output.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    status, filepath = parts[0], parts[1]
                    if status == 'A':
                        result["added"].append(filepath)
                    elif status == 'D':
                        result["deleted"].append(filepath)
                    elif status in ('M', 'R'):
                        result["modified"].append(filepath)
        except:
            pass

        return result

    def check(self) -> Dict[str, Any]:
        """Check staleness of all analysis data."""
        last_scan = self.get_last_scan_time()
        embeddings_time = self.get_embeddings_time()

        changed_files = self.get_changed_files(last_scan) if last_scan > 0 else []
        git_changes = self.get_git_changes(last_scan) if last_scan > 0 else {}

        # Determine staleness
        hours_since_scan = (datetime.now().timestamp() - last_scan) / 3600 if last_scan > 0 else float('inf')
        hours_since_embeddings = (datetime.now().timestamp() - embeddings_time) / 3600 if embeddings_time > 0 else float('inf')

        is_stale = (
            len(changed_files) > 0 or
            len(git_changes.get("added", [])) > 0 or
            len(git_changes.get("deleted", [])) > 0 or
            hours_since_scan > 24
        )

        embeddings_stale = (
            hours_since_embeddings > 24 or
            len(git_changes.get("added", [])) > 0 or
            len(git_changes.get("deleted", [])) > 0
        )

        return {
            "is_stale": is_stale,
            "embeddings_stale": embeddings_stale,
            "hours_since_scan": round(hours_since_scan, 1),
            "hours_since_embeddings": round(hours_since_embeddings, 1),
            "changed_files": changed_files[:20],  # Limit for display
            "changed_files_count": len(changed_files),
            "git_changes": git_changes,
            "recommendation": self._get_recommendation(is_stale, embeddings_stale, len(changed_files))
        }

    def _get_recommendation(self, is_stale: bool, embeddings_stale: bool, changed_count: int) -> str:
        """Get recommendation for what to refresh."""
        if not is_stale:
            return "none"
        if embeddings_stale or changed_count > 50:
            return "full"
        return "incremental"


def main():
    import sys
    if len(sys.argv) < 3:
        print("Usage: python freshness_checker.py <project_path> <project_id>")
        sys.exit(1)

    checker = FreshnessChecker(sys.argv[1], sys.argv[2])
    result = checker.check()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

**Step 2: Make executable and test**

Run: `chmod +x ~/.claude-memory/mlx-tools/freshness_checker.py`
Run: `python3 ~/.claude-memory/mlx-tools/freshness_checker.py /Users/jmelendez/Documents/Projects/WardrobeApp gyst`
Expected: JSON output showing staleness status

**Step 3: Commit**

```bash
git -C ~/.claude-memory add mlx-tools/freshness_checker.py
git -C ~/.claude-memory commit -m "feat(health): add freshness checker for staleness detection"
```

---

### Task 2: Create Health Config Schema

**Files:**
- Create: `~/.claude-memory/projects/gyst/health_config.json`

**Step 1: Create the config file with initial structure**

```json
{
  "version": "1.0",
  "lastUpdated": "2025-01-07T00:00:00Z",
  "ignore": {
    "duplicates": [
      {
        "pattern": "*Screen.js/*DetailScreen.js",
        "reason": "List/Detail screen pattern is intentional"
      },
      {
        "files": ["LoginScreen.js", "SignupScreen.js"],
        "reason": "Auth screens share intentional structure"
      },
      {
        "pattern": "use*.js/useFirestoreCollection.js",
        "reason": "Thin wrapper hooks around base hook"
      }
    ],
    "dead_code": [
      {
        "pattern": "scripts/*.js",
        "reason": "CLI scripts are entry points, not imported"
      },
      {
        "file": "App 2.js",
        "reason": "Git worktree artifact"
      }
    ],
    "performance": []
  },
  "thresholds": {
    "duplicate_similarity": 0.85,
    "dead_code_confidence": "medium"
  },
  "entry_points": [
    "App.js",
    "index.js",
    "src/navigation/**/*.js"
  ],
  "exclude_dirs": [
    "node_modules",
    ".worktrees",
    "_archived",
    "__tests__",
    "scripts"
  ]
}
```

**Step 2: Verify JSON is valid**

Run: `cat ~/.claude-memory/projects/gyst/health_config.json | jq .`
Expected: Pretty-printed JSON without errors

**Step 3: Commit**

```bash
git -C ~/.claude-memory add projects/gyst/health_config.json
git -C ~/.claude-memory commit -m "feat(health): add health config for gyst with ignore patterns"
```

---

### Task 3: Add Ignore List Support to Duplicate Finder

**Files:**
- Modify: `~/.claude-memory/mlx-tools/duplicate_finder.py`

**Step 1: Read current file and identify modification points**

The file needs:
1. Load health_config.json
2. Check ignore patterns before reporting duplicates
3. Add `is_ignored` flag to results

**Step 2: Update DuplicateFinder class**

Add after line 20 (after DEFAULT_EXCLUSIONS):

```python
class DuplicateFinder:
    """Find duplicate code using embedding similarity."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.memory_root = Path.home() / ".claude-memory"
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

            # Check patterns like "*Screen.js/*DetailScreen.js"
            if "pattern" in rule:
                pattern = rule["pattern"]
                if "/" in pattern:
                    p1, p2 = pattern.split("/")
                    if (self._matches_pattern(file1, p1) and self._matches_pattern(file2, p2)) or \
                       (self._matches_pattern(file1, p2) and self._matches_pattern(file2, p1)):
                        return True, rule.get("reason", "Ignored by config")

        return False, None

    def _matches_pattern(self, filename: str, pattern: str) -> bool:
        """Check if filename matches a simple glob pattern."""
        import fnmatch
        return fnmatch.fnmatch(Path(filename).name, pattern)
```

**Step 3: Update find_duplicates to use ignore list**

Modify the loop in find_duplicates (around line 82) to add ignore checking:

```python
                if similarity >= threshold:
                    is_ignored, ignore_reason = self._is_ignored_pair(file1, file2)
                    category = "exact" if similarity > 0.95 else "near" if similarity > 0.9 else "similar"
                    pairs.append(DuplicatePair(
                        file1=file1,
                        file2=file2,
                        similarity=round(float(similarity), 3),
                        category=category
                    ))
                    # Store ignore info separately
                    if is_ignored:
                        pairs[-1].ignored = True
                        pairs[-1].ignore_reason = ignore_reason
```

**Step 4: Update DuplicatePair dataclass**

```python
@dataclass
class DuplicatePair:
    file1: str
    file2: str
    similarity: float
    category: str  # "exact", "near", "similar"
    ignored: bool = False
    ignore_reason: str = None
```

**Step 5: Update return to exclude ignored from count**

```python
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
```

**Step 6: Test the changes**

Run: `python3 ~/.claude-memory/mlx-tools/duplicate_finder.py gyst`
Expected: Duplicates now show `ignored: true` for matched patterns, total_pairs excludes ignored

**Step 7: Commit**

```bash
git -C ~/.claude-memory add mlx-tools/duplicate_finder.py
git -C ~/.claude-memory commit -m "feat(health): add ignore list support to duplicate finder"
```

---

### Task 4: Add Ignore List Support to Dead Code Detector

**Files:**
- Modify: `~/.claude-memory/mlx-tools/dead_code_detector.py`

**Step 1: Add config loading to __init__**

After line 33:

```python
        self.config_path = self.memory_root / "projects" / self.project_id / "health_config.json"
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load health config with ignore patterns."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    return json.load(f)
            except:
                pass
        return {"ignore": {"dead_code": []}, "exclude_dirs": []}
```

**Step 2: Add ignore checking method**

```python
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
```

**Step 3: Update _find_unused_exports to check ignore list**

In the loop around line 182:

```python
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
```

**Step 4: Update exclude_dirs from config**

In _get_source_files, merge config exclude_dirs:

```python
    def _get_source_files(self) -> List[Path]:
        """Get all source files, excluding configured directories."""
        extensions = {'.js', '.jsx', '.ts', '.tsx'}
        files = []
        # Merge default and config excludes
        config_excludes = set(self.config.get("exclude_dirs", []))
        exclude_dirs = {'node_modules', '.git', 'dist', 'build', '.next', '.worktrees'} | config_excludes
```

**Step 5: Test**

Run: `python3 ~/.claude-memory/mlx-tools/dead_code_detector.py /Users/jmelendez/Documents/Projects/WardrobeApp gyst`
Expected: Scripts and _archived files should have lower confidence or be excluded

**Step 6: Commit**

```bash
git -C ~/.claude-memory add mlx-tools/dead_code_detector.py
git -C ~/.claude-memory commit -m "feat(health): add ignore list support to dead code detector"
```

---

### Task 5: Add API Endpoints for Ignore Management

**Files:**
- Modify: `~/.claude-memory/dashboard/server.js`

**Step 1: Add GET endpoint for health config**

After the health/scan endpoint (around line 1195), add:

```javascript
    // GET /api/projects/:id/health/config - get health config
    if (req.method === 'GET' && parts[1] === 'projects' && parts[2] && parts[3] === 'health' && parts[4] === 'config') {
      const projectId = parts[2];
      const configPath = path.join(MEMORY_ROOT, 'projects', projectId, 'health_config.json');

      if (fs.existsSync(configPath)) {
        const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
        res.end(JSON.stringify(config));
      } else {
        // Return default config
        res.end(JSON.stringify({
          version: "1.0",
          ignore: { duplicates: [], dead_code: [], performance: [] },
          thresholds: { duplicate_similarity: 0.85 },
          exclude_dirs: []
        }));
      }
      return;
    }

    // POST /api/projects/:id/health/ignore - add ignore rule
    if (req.method === 'POST' && parts[1] === 'projects' && parts[2] && parts[3] === 'health' && parts[4] === 'ignore') {
      const projectId = parts[2];
      const configPath = path.join(MEMORY_ROOT, 'projects', projectId, 'health_config.json');

      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        try {
          const { category, rule } = JSON.parse(body);

          // Load or create config
          let config = {
            version: "1.0",
            ignore: { duplicates: [], dead_code: [], performance: [] },
            thresholds: {}
          };

          if (fs.existsSync(configPath)) {
            config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
          }

          // Add rule to appropriate category
          if (!config.ignore[category]) {
            config.ignore[category] = [];
          }
          config.ignore[category].push(rule);
          config.lastUpdated = new Date().toISOString();

          // Save
          fs.writeFileSync(configPath, JSON.stringify(config, null, 2));

          res.end(JSON.stringify({ success: true, config }));
        } catch (e) {
          res.statusCode = 400;
          res.end(JSON.stringify({ error: e.message }));
        }
      });
      return;
    }

    // DELETE /api/projects/:id/health/ignore - remove ignore rule
    if (req.method === 'DELETE' && parts[1] === 'projects' && parts[2] && parts[3] === 'health' && parts[4] === 'ignore') {
      const projectId = parts[2];
      const configPath = path.join(MEMORY_ROOT, 'projects', projectId, 'health_config.json');

      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        try {
          const { category, index } = JSON.parse(body);

          if (!fs.existsSync(configPath)) {
            res.statusCode = 404;
            res.end(JSON.stringify({ error: 'No config found' }));
            return;
          }

          const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

          if (config.ignore[category] && config.ignore[category][index]) {
            config.ignore[category].splice(index, 1);
            config.lastUpdated = new Date().toISOString();
            fs.writeFileSync(configPath, JSON.stringify(config, null, 2));
            res.end(JSON.stringify({ success: true, config }));
          } else {
            res.statusCode = 404;
            res.end(JSON.stringify({ error: 'Rule not found' }));
          }
        } catch (e) {
          res.statusCode = 400;
          res.end(JSON.stringify({ error: e.message }));
        }
      });
      return;
    }
```

**Step 2: Add freshness check endpoint**

```javascript
    // GET /api/projects/:id/health/freshness - check data freshness
    if (req.method === 'GET' && parts[1] === 'projects' && parts[2] && parts[3] === 'health' && parts[4] === 'freshness') {
      const projectId = parts[2];
      const configPath = path.join(MEMORY_ROOT, 'config.json');
      const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      const project = config.projects.find(p => p.id === projectId);

      if (!project) {
        res.statusCode = 404;
        res.end(JSON.stringify({ error: 'Project not found' }));
        return;
      }

      const { spawn } = require('child_process');
      const mlxDir = path.join(MEMORY_ROOT, 'mlx-tools');

      const proc = spawn('python3', [
        path.join(mlxDir, 'freshness_checker.py'),
        project.path,
        projectId
      ], { cwd: mlxDir });

      let output = '';
      proc.stdout.on('data', data => output += data);
      proc.stderr.on('data', data => process.stderr.write(data));

      proc.on('close', code => {
        if (code === 0) {
          try {
            res.end(output);
          } catch (e) {
            res.end(JSON.stringify({ error: 'Parse error' }));
          }
        } else {
          res.statusCode = 500;
          res.end(JSON.stringify({ error: 'Freshness check failed' }));
        }
      });
      return;
    }
```

**Step 3: Test endpoints**

Run: `curl http://localhost:3333/api/projects/gyst/health/config`
Expected: JSON config

Run: `curl -X POST http://localhost:3333/api/projects/gyst/health/ignore -d '{"category":"duplicates","rule":{"files":["test1.js","test2.js"],"reason":"Test"}}'`
Expected: Success with updated config

Run: `curl http://localhost:3333/api/projects/gyst/health/freshness`
Expected: Freshness status JSON

**Step 4: Commit**

```bash
git -C ~/.claude-memory add dashboard/server.js
git -C ~/.claude-memory commit -m "feat(health): add API endpoints for ignore management and freshness"
```

---

### Task 6: Integrate Freshness Check into Health Scan

**Files:**
- Modify: `~/.claude-memory/mlx-tools/code_health.py`

**Step 1: Import freshness checker**

At top of file:

```python
from freshness_checker import FreshnessChecker
```

**Step 2: Add auto-refresh logic to run_quick_scan**

Before the static analysis (around line 37):

```python
    def run_quick_scan(self, incremental: bool = True) -> Dict[str, Any]:
        """Run fast static analysis with auto-refresh."""

        # Check freshness first
        freshness = FreshnessChecker(self.project_path, self.project_id)
        freshness_result = freshness.check()

        # Auto-rebuild embeddings if stale
        if freshness_result.get("embeddings_stale"):
            print("Embeddings are stale, rebuilding...", file=sys.stderr)
            self._rebuild_embeddings()

        mode = "incremental" if incremental else "full"
        # ... rest of method
```

**Step 3: Add rebuild_embeddings method**

```python
    def _rebuild_embeddings(self):
        """Rebuild embeddings for the project."""
        import subprocess
        mlx_env = self.memory_root / "mlx-env" / "bin" / "python3"
        embeddings_script = self.memory_root / "mlx-tools" / "embeddings_v2.py"

        try:
            subprocess.run([
                str(mlx_env),
                str(embeddings_script),
                self.project_id,
                "build"
            ], capture_output=True, timeout=120)
            print("Embeddings rebuilt successfully", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not rebuild embeddings: {e}", file=sys.stderr)
```

**Step 4: Add freshness info to results**

In the results dict:

```python
        results = {
            "scan_type": mode,
            "timestamp": datetime.now().isoformat(),
            "freshness": freshness_result,  # Add this
            "score": self._calculate_combined_score(static_results, duplicate_results, dead_code_results),
            # ... rest
        }
```

**Step 5: Test**

Run: `curl -X POST http://localhost:3333/api/projects/gyst/health/scan?full=true | jq '.freshness'`
Expected: Freshness info in scan results

**Step 6: Commit**

```bash
git -C ~/.claude-memory add mlx-tools/code_health.py
git -C ~/.claude-memory commit -m "feat(health): auto-rebuild stale embeddings during scan"
```

---

## Phase 2: Better Analysis

### Task 7: Create AST Analyzer Script (Node.js)

**Files:**
- Create: `~/.claude-memory/mlx-tools/ast_analyzer.js`

**Step 1: Create the AST analyzer**

```javascript
#!/usr/bin/env node
/**
 * AST Analyzer for Claude Memory System
 * Uses acorn to parse JS/JSX and extract detailed import/export/call info.
 */

const fs = require('fs');
const path = require('path');
const acorn = require('acorn');
const jsx = require('acorn-jsx');

const Parser = acorn.Parser.extend(jsx());

function parseFile(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const ast = Parser.parse(content, {
      ecmaVersion: 2022,
      sourceType: 'module',
      locations: true,
      allowHashBang: true,
      allowImportExportEverywhere: true,
      allowAwaitOutsideFunction: true,
    });
    return { success: true, ast, content };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

function extractImports(ast) {
  const imports = [];

  function walk(node) {
    if (!node || typeof node !== 'object') return;

    // Static imports: import X from 'Y'
    if (node.type === 'ImportDeclaration') {
      imports.push({
        type: 'static',
        source: node.source.value,
        line: node.loc?.start?.line,
        specifiers: node.specifiers?.map(s => ({
          type: s.type,
          imported: s.imported?.name || 'default',
          local: s.local?.name
        })) || []
      });
    }

    // Dynamic imports: import('X')
    if (node.type === 'ImportExpression') {
      imports.push({
        type: 'dynamic',
        source: node.source?.value || node.source?.quasis?.[0]?.value?.raw,
        line: node.loc?.start?.line
      });
    }

    // Require: require('X')
    if (node.type === 'CallExpression' &&
        node.callee?.name === 'require' &&
        node.arguments?.[0]?.value) {
      imports.push({
        type: 'require',
        source: node.arguments[0].value,
        line: node.loc?.start?.line
      });
    }

    // Walk children
    for (const key in node) {
      if (key === 'loc' || key === 'range') continue;
      const child = node[key];
      if (Array.isArray(child)) {
        child.forEach(walk);
      } else if (child && typeof child === 'object') {
        walk(child);
      }
    }
  }

  walk(ast);
  return imports;
}

function extractExports(ast) {
  const exports = [];

  function walk(node) {
    if (!node || typeof node !== 'object') return;

    // Named exports: export const X, export function Y
    if (node.type === 'ExportNamedDeclaration') {
      if (node.declaration) {
        const decl = node.declaration;
        if (decl.type === 'VariableDeclaration') {
          decl.declarations.forEach(d => {
            exports.push({
              type: 'named',
              name: d.id?.name,
              line: node.loc?.start?.line
            });
          });
        } else if (decl.id?.name) {
          exports.push({
            type: 'named',
            name: decl.id.name,
            line: node.loc?.start?.line
          });
        }
      }
      // export { X, Y }
      if (node.specifiers) {
        node.specifiers.forEach(s => {
          exports.push({
            type: 'named',
            name: s.exported?.name,
            local: s.local?.name,
            line: node.loc?.start?.line
          });
        });
      }
    }

    // Default export
    if (node.type === 'ExportDefaultDeclaration') {
      exports.push({
        type: 'default',
        name: node.declaration?.id?.name || node.declaration?.name || 'default',
        line: node.loc?.start?.line
      });
    }

    // Re-exports: export * from 'X'
    if (node.type === 'ExportAllDeclaration') {
      exports.push({
        type: 'reexport_all',
        source: node.source?.value,
        line: node.loc?.start?.line
      });
    }

    for (const key in node) {
      if (key === 'loc' || key === 'range') continue;
      const child = node[key];
      if (Array.isArray(child)) {
        child.forEach(walk);
      } else if (child && typeof child === 'object') {
        walk(child);
      }
    }
  }

  walk(ast);
  return exports;
}

function extractFunctionCalls(ast) {
  const calls = [];

  function walk(node, parentFunc = null) {
    if (!node || typeof node !== 'object') return;

    // Track current function context
    let currentFunc = parentFunc;
    if (node.type === 'FunctionDeclaration' ||
        node.type === 'FunctionExpression' ||
        node.type === 'ArrowFunctionExpression') {
      currentFunc = node.id?.name || parentFunc;
    }

    // Function calls
    if (node.type === 'CallExpression') {
      let name = null;
      if (node.callee?.name) {
        name = node.callee.name;
      } else if (node.callee?.property?.name) {
        name = node.callee.property.name;
      }

      if (name) {
        calls.push({
          name,
          line: node.loc?.start?.line,
          caller: currentFunc
        });
      }
    }

    for (const key in node) {
      if (key === 'loc' || key === 'range') continue;
      const child = node[key];
      if (Array.isArray(child)) {
        child.forEach(c => walk(c, currentFunc));
      } else if (child && typeof child === 'object') {
        walk(child, currentFunc);
      }
    }
  }

  walk(ast);
  return calls;
}

function extractNavigationRefs(ast, content) {
  const navRefs = [];

  // Pattern: navigation.navigate('ScreenName') or navigate('ScreenName')
  const navPattern = /(?:navigation\.)?navigate\s*\(\s*['"]([^'"]+)['"]/g;
  let match;
  while ((match = navPattern.exec(content)) !== null) {
    navRefs.push({
      screen: match[1],
      position: match.index
    });
  }

  return navRefs;
}

function analyzeFile(filePath) {
  const result = parseFile(filePath);

  if (!result.success) {
    return { error: result.error, file: filePath };
  }

  return {
    file: filePath,
    imports: extractImports(result.ast),
    exports: extractExports(result.ast),
    function_calls: extractFunctionCalls(result.ast),
    navigation_refs: extractNavigationRefs(result.ast, result.content)
  };
}

// CLI interface
if (require.main === module) {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.error('Usage: node ast_analyzer.js <file.js> [file2.js ...]');
    console.error('       node ast_analyzer.js --dir <directory>');
    process.exit(1);
  }

  if (args[0] === '--dir') {
    // Analyze entire directory
    const dir = args[1];
    const results = {};

    function scanDir(d) {
      for (const item of fs.readdirSync(d)) {
        const full = path.join(d, item);
        const stat = fs.statSync(full);

        if (stat.isDirectory()) {
          if (!['node_modules', '.git', 'dist', 'build'].includes(item)) {
            scanDir(full);
          }
        } else if (/\.(js|jsx|ts|tsx)$/.test(item)) {
          const rel = path.relative(dir, full);
          results[rel] = analyzeFile(full);
        }
      }
    }

    scanDir(dir);
    console.log(JSON.stringify(results, null, 2));
  } else {
    // Analyze specific files
    const results = {};
    for (const file of args) {
      results[file] = analyzeFile(file);
    }
    console.log(JSON.stringify(results, null, 2));
  }
}

module.exports = { analyzeFile, parseFile, extractImports, extractExports };
```

**Step 2: Install dependencies**

Run: `cd ~/.claude-memory/mlx-tools && npm init -y && npm install acorn acorn-jsx`

**Step 3: Make executable and test**

Run: `chmod +x ~/.claude-memory/mlx-tools/ast_analyzer.js`
Run: `node ~/.claude-memory/mlx-tools/ast_analyzer.js /Users/jmelendez/Documents/Projects/WardrobeApp/App.js`
Expected: JSON with imports, exports, function_calls, navigation_refs

**Step 4: Commit**

```bash
git -C ~/.claude-memory add mlx-tools/ast_analyzer.js mlx-tools/package.json mlx-tools/package-lock.json
git -C ~/.claude-memory commit -m "feat(health): add AST analyzer using acorn for accurate parsing"
```

---

### Task 8: Update Dead Code Detector to Use AST

**Files:**
- Modify: `~/.claude-memory/mlx-tools/dead_code_detector.py`

**Step 1: Add AST integration method**

```python
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
```

**Step 2: Update detect() to prefer AST**

```python
    def detect(self) -> Dict[str, Any]:
        """Run dead code detection."""
        dead_code = []

        # Try AST-based analysis first (more accurate)
        try:
            imports = self._build_import_graph_ast()
        except:
            imports = self._build_import_graph()

        exports = self._build_export_map()
        # ... rest unchanged
```

**Step 3: Test**

Run: `python3 ~/.claude-memory/mlx-tools/dead_code_detector.py /Users/jmelendez/Documents/Projects/WardrobeApp gyst | jq '.summary'`
Expected: Lower false positive count with AST analysis

**Step 4: Commit**

```bash
git -C ~/.claude-memory add mlx-tools/dead_code_detector.py
git -C ~/.claude-memory commit -m "feat(health): use AST analysis for more accurate dead code detection"
```

---

## Phase 3: Dashboard UI

### Task 9: Add Score Gauge Component

**Files:**
- Modify: `~/.claude-memory/dashboard/app.js`
- Modify: `~/.claude-memory/dashboard/styles.css`

**Step 1: Add renderScoreGauge function to app.js**

```javascript
function renderScoreGauge(score, container) {
  const color = score >= 80 ? '#22c55e' : score >= 60 ? '#eab308' : '#ef4444';
  const rotation = (score / 100) * 180;

  container.innerHTML = `
    <div class="score-gauge">
      <svg viewBox="0 0 200 120" class="gauge-svg">
        <!-- Background arc -->
        <path d="M 20 100 A 80 80 0 0 1 180 100"
              fill="none"
              stroke="#374151"
              stroke-width="20"
              stroke-linecap="round"/>
        <!-- Score arc -->
        <path d="M 20 100 A 80 80 0 0 1 180 100"
              fill="none"
              stroke="${color}"
              stroke-width="20"
              stroke-linecap="round"
              stroke-dasharray="${rotation * 2.8}, 500"
              class="gauge-fill"/>
      </svg>
      <div class="score-value" style="color: ${color}">${score}</div>
      <div class="score-label">${score >= 80 ? 'Good' : score >= 60 ? 'Fair' : 'Poor'}</div>
    </div>
  `;
}
```

**Step 2: Add gauge styles to styles.css**

```css
/* Score Gauge */
.score-gauge {
  position: relative;
  width: 200px;
  height: 140px;
  margin: 0 auto;
}

.gauge-svg {
  width: 100%;
  height: 100%;
}

.gauge-fill {
  transition: stroke-dasharray 0.5s ease-out;
}

.score-value {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 3rem;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

.score-label {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.9rem;
  color: #9ca3af;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
```

**Step 3: Update health panel to use gauge**

In the health panel rendering code:

```javascript
// Replace simple score display with gauge
const gaugeContainer = document.createElement('div');
gaugeContainer.className = 'gauge-container';
renderScoreGauge(healthData.score, gaugeContainer);
healthPanel.appendChild(gaugeContainer);
```

**Step 4: Commit**

```bash
git -C ~/.claude-memory add dashboard/app.js dashboard/styles.css
git -C ~/.claude-memory commit -m "feat(dashboard): add animated score gauge component"
```

---

### Task 10: Add Trend Chart Component

**Files:**
- Modify: `~/.claude-memory/dashboard/index.html`
- Modify: `~/.claude-memory/dashboard/app.js`
- Modify: `~/.claude-memory/dashboard/styles.css`

**Step 1: Add Chart.js to index.html**

```html
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
```

**Step 2: Add renderTrendChart function**

```javascript
function renderTrendChart(history, container) {
  const canvas = document.createElement('canvas');
  canvas.id = 'health-trend-chart';
  canvas.height = 150;
  container.innerHTML = '';
  container.appendChild(canvas);

  const ctx = canvas.getContext('2d');

  // Prepare data
  const labels = history.map(h => {
    const date = new Date(h.timestamp);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });
  const scores = history.map(h => h.score);

  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Health Score',
        data: scores,
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 3,
        pointHoverRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1f2937',
          titleColor: '#f3f4f6',
          bodyColor: '#d1d5db',
          borderColor: '#374151',
          borderWidth: 1
        }
      },
      scales: {
        y: {
          min: 0,
          max: 100,
          grid: { color: '#374151' },
          ticks: { color: '#9ca3af' }
        },
        x: {
          grid: { display: false },
          ticks: { color: '#9ca3af' }
        }
      }
    }
  });
}
```

**Step 3: Add trend chart styles**

```css
/* Trend Chart */
.trend-chart-container {
  background: #1f2937;
  border-radius: 8px;
  padding: 1rem;
  margin-top: 1rem;
}

.trend-chart-container h4 {
  margin: 0 0 0.5rem 0;
  color: #9ca3af;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
```

**Step 4: Fetch history and render**

```javascript
async function loadHealthHistory(projectId) {
  try {
    const res = await fetch(`/api/projects/${projectId}/health/history`);
    if (res.ok) {
      const history = await res.json();
      const container = document.getElementById('trend-chart-container');
      if (container && history.length > 1) {
        renderTrendChart(history, container);
      }
    }
  } catch (e) {
    console.error('Failed to load health history:', e);
  }
}
```

**Step 5: Add history API endpoint to server.js**

```javascript
    // GET /api/projects/:id/health/history - get health history
    if (req.method === 'GET' && parts[1] === 'projects' && parts[2] && parts[3] === 'health' && parts[4] === 'history') {
      const projectId = parts[2];
      const historyPath = path.join(MEMORY_ROOT, 'projects', projectId, 'health_history.json');

      if (fs.existsSync(historyPath)) {
        const history = JSON.parse(fs.readFileSync(historyPath, 'utf8'));
        res.end(JSON.stringify(history));
      } else {
        res.end(JSON.stringify([]));
      }
      return;
    }
```

**Step 6: Commit**

```bash
git -C ~/.claude-memory add dashboard/index.html dashboard/app.js dashboard/styles.css dashboard/server.js
git -C ~/.claude-memory commit -m "feat(dashboard): add health score trend chart"
```

---

### Task 11: Add Interactive Issue Cards

**Files:**
- Modify: `~/.claude-memory/dashboard/app.js`
- Modify: `~/.claude-memory/dashboard/styles.css`

**Step 1: Add renderIssueCard function**

```javascript
function renderIssueCard(issue, category, projectId) {
  const severityColors = {
    high: '#ef4444',
    medium: '#eab308',
    low: '#6b7280'
  };

  const severity = issue.confidence || issue.severity || 'medium';
  const color = severityColors[severity] || severityColors.medium;

  const card = document.createElement('div');
  card.className = 'issue-card';
  card.innerHTML = `
    <div class="issue-header">
      <span class="issue-severity" style="background: ${color}"></span>
      <span class="issue-type">${formatIssueType(issue.type || category)}</span>
      <span class="issue-file">${issue.file || issue.file1 || ''}</span>
    </div>
    <div class="issue-details">
      ${issue.code_snippet ? `<code class="issue-snippet">${escapeHtml(issue.code_snippet)}</code>` : ''}
      ${issue.reason ? `<p class="issue-reason">${issue.reason}</p>` : ''}
      ${issue.similarity ? `<p class="issue-similarity">Similarity: ${Math.round(issue.similarity * 100)}%</p>` : ''}
    </div>
    <div class="issue-actions">
      <button class="btn-ignore" data-category="${category}" data-issue='${JSON.stringify(issue)}'>
        Ignore
      </button>
      ${issue.fix_type === 'auto' ? `<button class="btn-fix" data-issue='${JSON.stringify(issue)}'>Fix</button>` : ''}
    </div>
  `;

  // Add ignore handler
  card.querySelector('.btn-ignore')?.addEventListener('click', async (e) => {
    const cat = e.target.dataset.category;
    const iss = JSON.parse(e.target.dataset.issue);

    await fetch(`/api/projects/${projectId}/health/ignore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        category: cat === 'duplicates' ? 'duplicates' : 'dead_code',
        rule: {
          file: iss.file || iss.file1,
          reason: 'Ignored from dashboard'
        }
      })
    });

    card.classList.add('ignored');
    showToast('Issue added to ignore list');
  });

  return card;
}

function formatIssueType(type) {
  return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
```

**Step 2: Add issue card styles**

```css
/* Issue Cards */
.issue-card {
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 0.75rem;
  transition: all 0.2s;
}

.issue-card:hover {
  border-color: #4b5563;
}

.issue-card.ignored {
  opacity: 0.5;
  border-style: dashed;
}

.issue-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
}

.issue-severity {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.issue-type {
  font-weight: 500;
  color: #f3f4f6;
}

.issue-file {
  color: #9ca3af;
  font-size: 0.85rem;
  font-family: 'JetBrains Mono', monospace;
  margin-left: auto;
}

.issue-details {
  padding-left: 1.5rem;
}

.issue-snippet {
  display: block;
  background: #111827;
  padding: 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  color: #d1d5db;
  overflow-x: auto;
  margin: 0.5rem 0;
}

.issue-reason {
  color: #9ca3af;
  font-size: 0.85rem;
  margin: 0.25rem 0;
}

.issue-similarity {
  color: #6b7280;
  font-size: 0.8rem;
}

.issue-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
  padding-left: 1.5rem;
}

.btn-ignore, .btn-fix {
  padding: 0.35rem 0.75rem;
  border-radius: 4px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-ignore {
  background: transparent;
  border: 1px solid #4b5563;
  color: #9ca3af;
}

.btn-ignore:hover {
  background: #374151;
  color: #f3f4f6;
}

.btn-fix {
  background: #3b82f6;
  border: none;
  color: white;
}

.btn-fix:hover {
  background: #2563eb;
}
```

**Step 3: Commit**

```bash
git -C ~/.claude-memory add dashboard/app.js dashboard/styles.css
git -C ~/.claude-memory commit -m "feat(dashboard): add interactive issue cards with ignore button"
```

---

### Task 12: Add Staleness Banner

**Files:**
- Modify: `~/.claude-memory/dashboard/app.js`
- Modify: `~/.claude-memory/dashboard/styles.css`

**Step 1: Add staleness banner rendering**

```javascript
function renderStalenessBanner(freshness, container, projectId) {
  if (!freshness.is_stale && freshness.hours_since_scan < 24) {
    container.innerHTML = '';
    return;
  }

  const hours = Math.round(freshness.hours_since_scan);
  const changedCount = freshness.changed_files_count || 0;

  container.innerHTML = `
    <div class="staleness-banner ${freshness.embeddings_stale ? 'severe' : ''}">
      <div class="staleness-icon">⚠️</div>
      <div class="staleness-message">
        <strong>Data is ${hours}+ hours old</strong>
        ${changedCount > 0 ? `<span>${changedCount} files changed</span>` : ''}
      </div>
      <button class="btn-refresh" onclick="triggerHealthScan('${projectId}', true)">
        Refresh Now
      </button>
    </div>
  `;
}
```

**Step 2: Add banner styles**

```css
/* Staleness Banner */
.staleness-banner {
  display: flex;
  align-items: center;
  gap: 1rem;
  background: #422006;
  border: 1px solid #854d0e;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
}

.staleness-banner.severe {
  background: #450a0a;
  border-color: #991b1b;
}

.staleness-icon {
  font-size: 1.25rem;
}

.staleness-message {
  flex: 1;
  color: #fef3c7;
}

.staleness-message strong {
  display: block;
}

.staleness-message span {
  font-size: 0.85rem;
  color: #fcd34d;
}

.btn-refresh {
  background: #d97706;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
}

.btn-refresh:hover {
  background: #b45309;
}
```

**Step 3: Commit**

```bash
git -C ~/.claude-memory add dashboard/app.js dashboard/styles.css
git -C ~/.claude-memory commit -m "feat(dashboard): add staleness warning banner"
```

---

## Phase 4: Polish

### Task 13: Add Auto-Fix for Console.log

**Files:**
- Create: `~/.claude-memory/mlx-tools/auto_fixer.py`
- Modify: `~/.claude-memory/dashboard/server.js`

**Step 1: Create auto_fixer.py**

```python
#!/usr/bin/env python3
"""
Auto Fixer for Claude Memory System
Applies automatic fixes to code issues.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional

class AutoFixer:
    """Apply automatic fixes to code issues."""

    def __init__(self, project_path: str):
        self.project_path = Path(project_path)

    def fix(self, issue: Dict) -> Dict[str, Any]:
        """Apply fix for an issue. Returns result with success status."""
        fix_type = issue.get("type") or issue.get("fix_type")

        fixers = {
            "console_log": self._fix_console_log,
            "unused_import": self._fix_unused_import,
        }

        fixer = fixers.get(fix_type)
        if fixer:
            return fixer(issue)

        return {"success": False, "error": f"No auto-fix for type: {fix_type}"}

    def _fix_console_log(self, issue: Dict) -> Dict[str, Any]:
        """Remove console.log statement."""
        file_path = self.project_path / issue["file"]
        line_num = issue["line"]

        if not file_path.exists():
            return {"success": False, "error": "File not found"}

        lines = file_path.read_text().split('\n')

        if line_num < 1 or line_num > len(lines):
            return {"success": False, "error": "Invalid line number"}

        # Get the line
        target_line = lines[line_num - 1]

        # Verify it's a console statement
        if not re.search(r'console\.(log|warn|error|debug|info)\s*\(', target_line):
            return {"success": False, "error": "Line doesn't contain console statement"}

        # Remove the line (or comment it out for safety)
        original = target_line
        lines[line_num - 1] = f"// REMOVED: {target_line.strip()}"

        # Write back
        file_path.write_text('\n'.join(lines))

        return {
            "success": True,
            "file": str(issue["file"]),
            "line": line_num,
            "original": original,
            "action": "commented_out"
        }

    def _fix_unused_import(self, issue: Dict) -> Dict[str, Any]:
        """Remove unused import statement."""
        file_path = self.project_path / issue["file"]
        name = issue.get("name")

        if not file_path.exists():
            return {"success": False, "error": "File not found"}

        content = file_path.read_text()

        # Pattern to match import statement containing the name
        pattern = rf"import\s+.*\b{re.escape(name)}\b.*from\s+['\"][^'\"]+['\"];\n?"

        new_content = re.sub(pattern, '', content)

        if new_content == content:
            return {"success": False, "error": "Could not find import to remove"}

        file_path.write_text(new_content)

        return {
            "success": True,
            "file": str(issue["file"]),
            "name": name,
            "action": "removed_import"
        }


def main():
    import sys

    if len(sys.argv) < 3:
        print("Usage: python auto_fixer.py <project_path> <issue_json>")
        sys.exit(1)

    project_path = sys.argv[1]
    issue = json.loads(sys.argv[2])

    fixer = AutoFixer(project_path)
    result = fixer.fix(issue)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

**Step 2: Add fix endpoint to server.js**

```javascript
    // POST /api/projects/:id/health/fix - apply auto-fix
    if (req.method === 'POST' && parts[1] === 'projects' && parts[2] && parts[3] === 'health' && parts[4] === 'fix') {
      const projectId = parts[2];
      const configPath = path.join(MEMORY_ROOT, 'config.json');
      const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      const project = config.projects.find(p => p.id === projectId);

      if (!project) {
        res.statusCode = 404;
        res.end(JSON.stringify({ error: 'Project not found' }));
        return;
      }

      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', () => {
        const { spawn } = require('child_process');
        const mlxDir = path.join(MEMORY_ROOT, 'mlx-tools');

        const proc = spawn('python3', [
          path.join(mlxDir, 'auto_fixer.py'),
          project.path,
          body
        ], { cwd: mlxDir });

        let output = '';
        proc.stdout.on('data', data => output += data);
        proc.stderr.on('data', data => process.stderr.write(data));

        proc.on('close', code => {
          if (code === 0) {
            res.end(output);
          } else {
            res.statusCode = 500;
            res.end(JSON.stringify({ error: 'Fix failed' }));
          }
        });
      });
      return;
    }
```

**Step 3: Add fix handler in app.js**

```javascript
// Add to issue card button handler
card.querySelector('.btn-fix')?.addEventListener('click', async (e) => {
  const iss = JSON.parse(e.target.dataset.issue);

  const res = await fetch(`/api/projects/${projectId}/health/fix`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(iss)
  });

  const result = await res.json();

  if (result.success) {
    card.classList.add('fixed');
    showToast(`Fixed: ${result.action}`);
  } else {
    showToast(`Fix failed: ${result.error}`, 'error');
  }
});
```

**Step 4: Commit**

```bash
git -C ~/.claude-memory add mlx-tools/auto_fixer.py dashboard/server.js dashboard/app.js
git -C ~/.claude-memory commit -m "feat(health): add auto-fix for console.log removal"
```

---

### Task 14: Final Integration and Testing

**Step 1: Update health panel to use all new components**

Update the loadHealthData function in app.js to integrate:
- Score gauge
- Trend chart
- Issue cards with actions
- Staleness banner

**Step 2: Add loading states**

```javascript
function showHealthLoading(container) {
  container.innerHTML = `
    <div class="health-loading">
      <div class="spinner"></div>
      <span>Analyzing codebase...</span>
    </div>
  `;
}
```

**Step 3: Test complete flow**

1. Open dashboard: `http://localhost:3333`
2. Select GYST project
3. Verify: Score gauge displays with animation
4. Verify: Trend chart shows history
5. Verify: Issue cards render with Ignore/Fix buttons
6. Verify: Clicking Ignore adds to config and grays out card
7. Verify: Clicking Fix on console.log issue removes it
8. Verify: Stale data shows warning banner
9. Verify: Refresh button triggers rescan

**Step 4: Final commit**

```bash
git -C ~/.claude-memory add -A
git -C ~/.claude-memory commit -m "feat(health): complete health tool redesign with all UI components"
```

---

## Summary

| Phase | Tasks | Key Deliverables |
|-------|-------|------------------|
| 1. Foundation | 1-6 | FreshnessChecker, health_config.json, ignore support |
| 2. Analysis | 7-8 | AST analyzer, improved dead code detection |
| 3. UI | 9-12 | Score gauge, trend chart, issue cards, staleness banner |
| 4. Polish | 13-14 | Auto-fix, integration testing |

**Total: 14 tasks**
