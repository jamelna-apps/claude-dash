# Claude-Dash Tool Mapping Reference

> **CANONICAL SOURCE** - This file is the single source of truth for tool mapping.
> Both global and project CLAUDE.md files reference this document.

## Memory-First Tool Usage (MANDATORY)

You MUST use memory-first tools instead of direct filesystem operations for token efficiency and proper system operation.

### Required Tool Mapping

| Instead of...        | ALWAYS use...   | Why                                           |
|----------------------|-----------------|-----------------------------------------------|
| `Read`               | `smart_read`    | 60-95% token savings via cached summaries     |
| `Grep` (search)      | `memory_query`  | Pre-indexed hybrid search (BM25 + semantic)   |
| `Grep` (code)        | `smart_search`  | Memory-first code search with summaries       |
| `Glob`               | `memory_query`  | Indexed file search                           |
| `Bash` (read-only)   | `smart_exec`    | Cached command results                        |
| `Write` + reindex    | `smart_edit`    | Auto-triggers re-indexing                     |

### Workflow Pattern

1. **Search/Query**: `memory_query "where is X?"` → hybrid search
2. **Read File**: `smart_read path (detail: "summary")` → get overview first
3. **Only if needed**: `smart_read path (detail: "full")` → full content
4. **Never**: Direct `Read`, `Grep`, or `Glob` unless memory tools unavailable

### Verification

Run `gateway_metrics` to check compliance and token savings.

## MCP Tools Reference

### Primary (Memory-First)

| Tool | Purpose |
|------|---------|
| `smart_read` | Memory-first file reading (summary/functions/full) |
| `smart_search` | Memory-first code search with summaries |
| `smart_exec` | Cached command execution |
| `smart_edit` | Edit + auto-reindex |

### Memory Query

| Tool | Purpose |
|------|---------|
| `memory_query` | Natural language search (hybrid BM25 + semantic) |
| `memory_search` | Semantic search across files |
| `memory_functions` | Look up function definitions by name |
| `memory_similar` | Find files similar to a given file |
| `memory_health` | Check code health status (action: "status" or "repair") |
| `memory_sessions` | Search past session observations |
| `memory_roadmap` | Query/update project roadmaps |

### Learning Tools

| Tool | Purpose |
|------|---------|
| `reasoning_capture` | Record a reasoning chain (trigger → steps → conclusion) |
| `reasoning_recall` | Find past reasoning chains for similar situations |
| `reasoning_query` | Query reasoning bank for applicable solutions |
| `learning_status` | Check learning system status (preferences, corrections, etc.) |

### Cross-Project

| Tool | Purpose |
|------|---------|
| `project_query` | Query another project's memory without switching contexts |

### Code Quality & Budget

| Tool | Purpose |
|------|---------|
| `context_budget` | HOT/WARM/COLD tier breakdown with token counts and cost estimates |
| `pattern_review` | LLM-powered code validation against PATTERNS.md/decisions.json |

### Local AI (Non-Critical Only)

**IMPORTANT:** NOT recommended for development work.
Use for: Enchanted/mobile, commit messages, personal experimentation only.

| Tool | Purpose |
|------|---------|
| `local_ask` | NON-CRITICAL: commit messages, Enchanted API only |
| `local_review` | NOT for critical code - use Sonnet instead |

### Self-Healing Tools *(NEW)*

| Tool | Purpose |
|------|---------|
| `self_heal_check` | Check system health for broken dependencies |
| `self_heal_analyze` | Analyze impact of removing a resource |
| `self_heal_fix` | Apply cascade fixes (dry_run=true by default) |
| `self_heal_rollback` | Rollback changes from a backup |

### Utility

| Tool | Purpose |
|------|---------|
| `gateway_metrics` | View routing stats and token savings |

## Local LLM Usage (Non-Critical Only)

**DO NOT use local tools for development work.** Use Claude (Sonnet) instead.

| Task | Tool | Notes |
|------|------|-------|
| Commit messages | `local_ask` (mode: commit) | OK - non-critical |
| PR descriptions | `local_ask` | OK - non-critical |
| Enchanted queries | `local_ask` | OK - mobile API |
| **Code review** | **Use Sonnet** | NOT local_review |
| **Code explanation** | **Use Sonnet** | NOT local_ask |
| **Any development** | **Use Claude** | Quality matters |

**Decision Guide:**
- **Use Claude (Sonnet)**: ALL development work, debugging, architecture, code
- **Use Local**: ONLY commit messages, PR descriptions, Enchanted app queries

## MLX CLI Reference (Non-Critical Only)

**NOTE:** MLX/local AI is NOT for critical development work. Use Claude instead.

```bash
# Git operations (non-critical)
~/.claude-dash/mlx-tools/mlx commit           # Generate commit message (OK)
~/.claude-dash/mlx-tools/mlx pr [base]        # Generate PR description (OK)
```

### When to Use What

| Task | Tool | Model |
|------|------|-------|
| "Where is X?" | MCP `memory_query` | Haiku |
| "Find function Y" | MCP `memory_functions` | Haiku |
| "How does X work?" | Claude (Sonnet) | NOT local |
| Code review | Claude (Sonnet) | NOT local |
| Error analysis | Claude (Sonnet) | NOT local |
| Commit message | MLX `commit` | Local OK |

## Code Quality Tools

### Context Budget Dashboard

Shows HOT/WARM/COLD tier breakdown with token counts and cost estimates.

```
context_budget project=gyst

Returns:
{
  "tiers": {
    "hot": { "description": "Active context", "tokens": 3200 },
    "warm": { "description": "On-demand indexed", "tokens": 18500 },
    "cold": { "description": "Full file content", "tokens": 145000 }
  },
  "savings": { "thisSession": 12400, "percentage": 87 },
  "costs": { "perSession": "$0.008", "perDay": "$0.08", "perMonth": "$1.60" }
}
```

### Pattern Review (Guardian)

LLM-powered code validation against documented patterns (uses Haiku, falls back to Ollama).

```
pattern_review file=src/App.js project=gyst mode=safe

Returns:
{
  "violations": [
    { "severity": "major", "line": 45, "pattern": "theme colors",
      "issue": "Hardcoded #333", "confidence": 0.92, "suggestion": "Use theme.colors.text" }
  ],
  "compliant": ["prop-types defined", "default export used"]
}
```

**Sources validated:**
- `PATTERNS.md` (project root or docs/)
- `decisions.json` (learned patterns)
- `preferences.json` (avoid/use preferences)

**Modes:**
- `normal` - All issues
- `safe` - High confidence only (>=70%)

### Memory Health with Auto-Repair

Extended health check with repair capability.

```
memory_health action=repair project=gyst

Returns:
{
  "status": "repaired",
  "fixed": [
    { "issue": "stale_index", "file": "src/App.js", "action": "reindexed" },
    { "issue": "orphaned_embedding", "count": 3, "action": "removed" }
  ],
  "remaining": []
}
```

**Repair actions:**
- `stale_index` → Reindex file
- `orphaned_embedding` → Remove from HNSW
- `missing_summary` → Generate via smart_read
- `corrupt_json` → Restore or regenerate

## Reasoning Chains

Captures the full cognitive journey during debugging/investigation, not just the conclusion.

### Capturing a Chain

```
reasoning_capture {
  trigger: "Token tracking showed wrong values"
  steps: [
    {observation: "Today's Spend showed $387 instead of ~$160", interpretation: "Values being doubled"},
    {observation: "cli-watcher processes on startup", interpretation: "App restarts re-importing"},
    {observation: "No deduplication check", interpretation: "Duplicates accumulating"}
  ]
  conclusion: "Added deduplication check to tokens.repo.ts"
  outcome: "success"
  domain: "database"
  alternatives: [{option: "Clear DB on startup", rejectedBecause: "Would lose historical data"}]
  constraints: ["Must preserve existing data", "App may restart multiple times"]
  revisitWhen: ["Database schema changes", "New token sources added"]
  confidence: 0.95
}
```

### Recalling Chains

```
reasoning_recall context="dashboard shows wrong totals" domain=database limit=3
```

Returns past reasoning chains with similar context, ranked by relevance.

### Auto-Injection

Reasoning chains are automatically injected when prompts contain investigation keywords:
- `debug`, `fix`, `error`, `why`, `broken`, `wrong`, `issue`, `problem`, `investigate`

### CLI Usage

```bash
# Capture a chain
python3 ~/.claude-dash/learning/reasoning_chains.py capture '{"trigger":"...", "steps":[...], ...}'

# Recall chains
python3 ~/.claude-dash/learning/reasoning_chains.py recall "context" --domain database --limit 5

# View stats
python3 ~/.claude-dash/learning/reasoning_chains.py stats
```

## Self-Healing System *(NEW)*

Auto-detect and fix broken dependencies when resources are removed.

### Workflow

1. **Before removing a resource** - Analyze impact:
   ```
   self_heal_analyze resource_id="deepseek-coder:6.7b"
   ```

2. **Apply fixes** (preview first):
   ```
   self_heal_fix resource_id="old-model" replacement="gemma3:4b-it-qat" dry_run=true
   ```

3. **Apply for real** (creates backup):
   ```
   self_heal_fix resource_id="old-model" replacement="gemma3:4b-it-qat" dry_run=false
   ```

4. **Rollback if needed**:
   ```
   self_heal_rollback backup_id="20240128_103045"
   ```

### Severity Levels

| Level | Meaning | Example Files |
|-------|---------|---------------|
| CRITICAL | System won't work | config.py, gateway/server.js |
| HIGH | Major feature broken | Active tools, API handlers |
| MEDIUM | Some functionality affected | Secondary tools |
| LOW | Minor impact | Deprecated code, docs |
| INFO | Just informational | Comments, docstrings |

### CLI Usage

```bash
# Check for broken dependencies
~/.claude-dash/mlx-tools/mlx self-heal check

# Analyze impact
~/.claude-dash/mlx-tools/mlx self-heal analyze <resource_id> [replacement]

# Preview fixes
~/.claude-dash/mlx-tools/mlx self-heal fix <resource_id> <replacement>

# Apply fixes
~/.claude-dash/mlx-tools/mlx self-heal fix <resource_id> <replacement> --apply

# Rollback
~/.claude-dash/mlx-tools/mlx self-heal rollback <backup_timestamp>
```
