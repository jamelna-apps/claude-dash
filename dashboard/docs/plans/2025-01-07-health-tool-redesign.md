# Health Score Tool Redesign

## Goal

Transform the code health tool from a basic static analyzer with high false-positive rates into an accurate, actionable, and interactive system that developers actually trust and use.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Dashboard UI (React-like)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ Score    │ │ Trend    │ │ Issues   │ │ Quick Actions    │   │
│  │ Gauge    │ │ Chart    │ │ List     │ │ Fix | Ignore     │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Health API (server.js)                      │
│  /api/projects/:id/health/scan     - Trigger analysis           │
│  /api/projects/:id/health/status   - Get current state          │
│  /api/projects/:id/health/ignore   - Add to ignore list         │
│  /api/projects/:id/health/fix      - Apply auto-fix             │
│  /api/projects/:id/health/trends   - Get history data           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Analysis Engine (Python)                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Freshness       │  │ AST Analyzer    │  │ Duplicate       │ │
│  │ Checker         │  │ (acorn/babel)   │  │ Detector        │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Call Graph      │  │ Dead Code       │  │ Security        │ │
│  │ Builder         │  │ Analyzer        │  │ Scanner         │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Data Layer (JSON files)                       │
│  health.json         - Current scan results                     │
│  health_history.json - Score over time                          │
│  health_config.json  - Ignore lists, thresholds                 │
│  call_graph.json     - Function call relationships              │
│  ast_cache/          - Cached AST per file (by mtime)           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Freshness Checker

**Problem:** Embeddings and analysis data become stale when files change.

**Solution:**
```python
class FreshnessChecker:
    def check_staleness(self) -> Dict:
        """Compare file mtimes against last analysis timestamp."""
        last_scan = self.get_last_scan_time()
        changed_files = []

        for file in self.get_source_files():
            if file.stat().st_mtime > last_scan:
                changed_files.append(file)

        # Also check git for new/deleted files
        git_changes = self.get_git_changes_since(last_scan)

        return {
            "is_stale": len(changed_files) > 0 or len(git_changes) > 0,
            "changed_files": changed_files,
            "git_changes": git_changes,
            "last_scan": last_scan,
            "recommendation": "full" if len(changed_files) > 50 else "incremental"
        }
```

**Auto-refresh trigger:**
- On scan request, check staleness first
- If stale, rebuild embeddings for changed files only
- Show "Data is X hours old" warning in UI

### 2. AST-Based Import Analyzer

**Problem:** Regex-based import detection misses:
- Dynamic imports: `import('./module')`
- Re-exports: `export * from './utils'`
- Navigation references: `navigation.navigate('ScreenName')`
- Require with variables: `require(modulePath)`

**Solution:** Use AST parsing (acorn for JS, @babel/parser for JSX/TS)

```python
class ASTAnalyzer:
    def analyze_file(self, file_path: str) -> Dict:
        """Parse file and extract all references."""
        ast = self.parse(file_path)

        return {
            "imports": self.extract_imports(ast),        # Static imports
            "dynamic_imports": self.extract_dynamic(ast), # import()
            "exports": self.extract_exports(ast),         # All export types
            "function_calls": self.extract_calls(ast),    # fn() references
            "navigation_refs": self.extract_nav(ast),     # navigate('X')
            "jsx_components": self.extract_jsx(ast),      # <Component />
        }
```

**Benefits:**
- Catches `import()` dynamic imports
- Tracks `export * from` re-exports
- Finds React Navigation references
- Builds accurate dependency graph

### 3. Call Graph Builder

**Problem:** Current system only checks if a file is imported, not if specific functions are actually called.

**Solution:** Build function-level call graph

```python
class CallGraphBuilder:
    def build(self) -> Dict:
        """Build function call graph across codebase."""
        graph = {
            "functions": {},  # func_id -> {file, line, calls, called_by}
            "entry_points": [],  # App.js, index.js, etc.
        }

        for file in self.files:
            ast = self.parse(file)
            for func in self.extract_functions(ast):
                func_id = f"{file}:{func.name}"
                graph["functions"][func_id] = {
                    "file": file,
                    "line": func.line,
                    "name": func.name,
                    "calls": self.extract_calls_in_function(func),
                    "called_by": []  # Populated in second pass
                }

        # Second pass: populate called_by
        for func_id, func_data in graph["functions"].items():
            for called in func_data["calls"]:
                if called in graph["functions"]:
                    graph["functions"][called]["called_by"].append(func_id)

        return graph
```

**Dead code detection improvement:**
- Function is dead if: not in entry points AND called_by is empty
- Confidence levels based on call chain depth
- Exclude React lifecycle methods, hooks, etc.

### 4. Smart Duplicate Detection

**Problem:** Current embedding similarity flags:
- Intentional patterns (List/Detail screens)
- Thin wrappers around base code
- Similar structure with different logic

**Solution:** Multi-signal duplicate detection

```python
class SmartDuplicateFinder:
    def find_duplicates(self) -> List[Duplicate]:
        """Find duplicates using multiple signals."""
        candidates = []

        # Signal 1: Embedding similarity (existing)
        embedding_pairs = self.find_by_embedding(threshold=0.85)

        # Signal 2: Structural similarity (AST shape)
        for pair in embedding_pairs:
            ast1, ast2 = self.parse(pair.file1), self.parse(pair.file2)
            structural_sim = self.compare_ast_structure(ast1, ast2)

            # Signal 3: Name pattern detection
            is_list_detail = self.is_list_detail_pair(pair)
            is_create_edit = self.is_create_edit_pair(pair)
            is_wrapper = self.is_wrapper_pattern(pair)

            # Combine signals
            if is_list_detail or is_create_edit:
                pair.category = "intentional_pattern"
                pair.confidence = "low"
            elif is_wrapper:
                pair.category = "wrapper"
                pair.confidence = "low"
            elif structural_sim > 0.9 and pair.similarity > 0.95:
                pair.category = "exact"
                pair.confidence = "high"
            else:
                pair.category = "similar"
                pair.confidence = "medium"

            candidates.append(pair)

        return candidates

    def is_list_detail_pair(self, pair) -> bool:
        """Detect ListScreen/DetailScreen pattern."""
        patterns = [
            (r'(\w+)Screen', r'\1DetailScreen'),
            (r'(\w+)List', r'\1Detail'),
            (r'(\w+)s\.js', r'\1\.js'),  # Collections.js / Collection.js
        ]
        return any(self.matches_pattern(pair, p) for p in patterns)
```

### 5. Project-Specific Configuration

**New file: `health_config.json`**

```json
{
  "version": "1.0",
  "ignore": {
    "duplicates": [
      {"pattern": "*Screen.js/*DetailScreen.js", "reason": "List/Detail pattern"},
      {"files": ["LoginScreen.js", "SignupScreen.js"], "reason": "Auth screens intentionally similar"}
    ],
    "dead_code": [
      {"file": "src/constants/styleFilters.js", "reason": "Used via dynamic import"},
      {"pattern": "scripts/*.js", "reason": "CLI tools, not imported"}
    ],
    "security": []
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
    "__tests__",
    "scripts"
  ]
}
```

### 6. Auto-Fix System

**Fixable issues:**
- Console.log removal
- Unused imports cleanup
- Dead file archival
- Simple refactoring suggestions

```python
class AutoFixer:
    def get_fix(self, issue: Issue) -> Optional[Fix]:
        """Generate fix for an issue."""
        fixers = {
            "console_log": self.fix_console_log,
            "unused_import": self.fix_unused_import,
            "dead_file": self.fix_dead_file,
        }

        fixer = fixers.get(issue.type)
        if fixer:
            return fixer(issue)
        return None

    def fix_console_log(self, issue) -> Fix:
        """Remove console.log statement."""
        return Fix(
            type="remove_line",
            file=issue.file,
            line=issue.line,
            preview=f"Remove: {issue.code_snippet}",
            reversible=True
        )
```

### 7. Dashboard UI Improvements

**New components:**

1. **Score Gauge**
   - Circular progress with color gradient (red→yellow→green)
   - Animated transitions on score change
   - Click to see breakdown

2. **Trend Chart**
   - Line chart showing score over last 30 scans
   - Hover for details (date, score, major changes)
   - Annotations for significant events

3. **Issue Cards**
   - Expandable cards with code preview
   - "Ignore" button (adds to config)
   - "Fix" button (for auto-fixable issues)
   - Severity badges (critical/warning/info)
   - Filter by category

4. **Staleness Banner**
   - Shows when data is >1 day old
   - "Refresh Now" button
   - Auto-refresh toggle

**UI Mockup:**
```
┌────────────────────────────────────────────────────────────────────┐
│  Health Score                              [Refresh] [Settings]    │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│    ┌─────────┐         Score Trend (Last 30 Days)                 │
│    │   84    │    90 ┤     ╭──╮                                   │
│    │  ████   │    80 ┤ ───╯    ╰──────────────────                │
│    │  Good   │    70 ┤                                            │
│    └─────────┘    60 ┼────┬────┬────┬────┬────┬────               │
│                      Dec  Jan                                      │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│  Issues (12)                    [All ▾] [Critical] [Duplicates]   │
├────────────────────────────────────────────────────────────────────┤
│  ▸ 🔴 console.log in production     LoginScreen.js:45    [Fix]    │
│  ▸ 🟡 Similar code detected         useOutfits ↔ useWardrobe      │
│    │  Similarity: 89% | Wrapper pattern detected                  │
│    │  [View Diff] [Ignore Pattern]                                │
│  ▸ 🟡 Unused export                 styleFilters.js:6             │
│    │  STYLE_VIBE_OPTIONS - File never imported                    │
│    │  [View Usage] [Ignore] [Archive File]                        │
└────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: Foundation (2-3 hours)
- [ ] Add FreshnessChecker with auto-rebuild
- [ ] Create health_config.json structure
- [ ] Add ignore list support to existing analyzers
- [ ] Basic API endpoints for ignore/config

### Phase 2: Better Analysis (3-4 hours)
- [ ] Integrate AST parsing (use Node.js acorn via subprocess)
- [ ] Build basic call graph
- [ ] Improve dead code detection accuracy
- [ ] Add pattern detection for duplicates

### Phase 3: Dashboard UI (2-3 hours)
- [ ] Score gauge component
- [ ] Trend chart (using Chart.js or simple SVG)
- [ ] Expandable issue cards
- [ ] Ignore/Fix buttons with API integration

### Phase 4: Polish (1-2 hours)
- [ ] Auto-fix for console.log
- [ ] Staleness banner
- [ ] Settings modal for thresholds
- [ ] Loading states and error handling

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| False positive rate | ~40% | <10% |
| Scan time (incremental) | 5s | <2s |
| User actions to dismiss false positive | N/A (can't) | 1 click |
| Auto-fixable issues | 0% | 30% |
| Time to understand issue | ~30s | <10s |

---

## Files to Create/Modify

**New files:**
- `mlx-tools/freshness_checker.py`
- `mlx-tools/ast_analyzer.py` (or Node.js script)
- `mlx-tools/call_graph_builder.py`
- `mlx-tools/auto_fixer.py`
- `projects/{id}/health_config.json`
- `projects/{id}/call_graph.json`
- `dashboard/components/health-gauge.js`
- `dashboard/components/trend-chart.js`
- `dashboard/components/issue-card.js`

**Modified files:**
- `mlx-tools/code_health.py` - Integrate new analyzers
- `mlx-tools/dead_code_detector.py` - Use call graph
- `mlx-tools/duplicate_finder.py` - Add pattern detection
- `dashboard/server.js` - New API endpoints
- `dashboard/app.js` - New UI components
- `dashboard/styles.css` - New styles
- `dashboard/index.html` - Updated layout
