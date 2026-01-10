# Claude Memory System - Ollama Context Guide

You are an AI assistant with full access to the Claude Memory system. This document explains everything you need to know to understand and work with this system.

## System Overview

Claude Memory is a codebase intelligence platform that maintains persistent knowledge about software projects. It indexes code, tracks health metrics, records decisions, and enables semantic search across projects.

**Location:** `~/.claude-memory/`

## Projects Structure

Each project has a dedicated directory at `~/.claude-memory/projects/{project-id}/` containing:

| File | Description |
|------|-------------|
| `health.json` | Current code health metrics and issues |
| `health_history.json` | Historical health scores (last 100 entries) |
| `summaries.json` | File-by-file summaries with purpose, key logic, exports, imports |
| `schema.json` | Database collections, fields, relationships |
| `functions.json` | Index of all functions/methods with file paths and line numbers |
| `embeddings_v2.json` | Vector embeddings for semantic search |
| `ollama_embeddings.json` | Ollama-generated embeddings (nomic-embed-text) |
| `graph.json` | Component dependency graph and navigation flow |
| `features.json` | Feature inventory |
| `decisions.json` | Architectural decisions made during development |
| `observations.json` | Session observations and patterns learned |
| `preferences.json` | Project-specific coding conventions and rules |

---

## Health Score System (0-100)

The health score is a **composite metric** measuring code quality. Higher is better.

### Score Calculation

```
Base Score = 100 (from static analysis)

Deductions:
- Security issues: Variable penalty based on severity
- Performance issues: Variable penalty based on impact
- Maintenance issues: Variable penalty based on complexity
- Duplicate code penalty (logarithmic, max 10 points):
  * 10 duplicate pairs = -5 points
  * 50 duplicate pairs = -8 points
  * 100+ duplicate pairs = -10 points
- Dead code penalty (logarithmic, max 10 points):
  * 100 items = -5 points
  * 500 items = -7 points
  * 1000+ items = -10 points

Final Score = max(0, Base Score - All Penalties)
```

### Issue Categories

**Security Issues** (most critical)
- Hardcoded credentials or API keys
- SQL/NoSQL injection vulnerabilities
- XSS (Cross-Site Scripting) risks
- Insecure data handling
- Missing authentication checks

**Performance Issues**
- Unoptimized database queries
- Memory leaks
- Synchronous operations that should be async
- Missing caching opportunities
- Large bundle sizes

**Maintenance Issues**
- Complex functions (high cyclomatic complexity)
- Large files (1000+ lines)
- Deeply nested code
- Missing error handling
- Inconsistent naming conventions

**Duplicate Code**
- Repeated code blocks across files
- Copy-pasted logic that should be abstracted
- Detected using semantic similarity (embeddings)

**Dead Code**
- Unused exports
- Orphan files (no imports)
- Unused functions/methods
- Deprecated code not removed

### Score Interpretation

| Score | Rating | Meaning |
|-------|--------|---------|
| 90-100 | Excellent | Clean, well-maintained codebase |
| 75-89 | Good | Minor issues, generally healthy |
| 60-74 | Fair | Several areas need attention |
| 40-59 | Poor | Significant technical debt |
| 0-39 | Critical | Major refactoring needed |

### Health Data Example

```json
{
  "scan_type": "incremental",
  "timestamp": "2025-12-15T12:50:05.308883",
  "score": 97,
  "issues": {
    "security": [],
    "performance": [],
    "maintenance": [],
    "duplicates": [],
    "dead_code": [
      {"type": "unused_export", "file": "src/utils/helpers.ts", "name": "oldFunction"},
      {"type": "orphan_file", "file": "src/components/Deprecated.tsx"}
    ]
  },
  "summary": {
    "security": 0,
    "performance": 0,
    "duplicates": 0,
    "dead_code": 18
  }
}
```

---

## Data Files Explained

### summaries.json
Contains AI-generated summaries of each file:
```json
{
  "files": {
    "src/components/Login.tsx": {
      "summary": "React component for user authentication",
      "purpose": "Handles login form, validation, and Firebase auth",
      "key_logic": ["Form validation", "Firebase signInWithEmailAndPassword"],
      "exports": ["Login", "LoginProps"],
      "imports": ["firebase/auth", "react-hook-form"]
    }
  }
}
```

### schema.json
Database structure (Firebase/Firestore/MongoDB):
```json
{
  "collections": {
    "users": {
      "fields": {
        "email": {"type": "string", "required": true},
        "createdAt": {"type": "timestamp"},
        "profile": {"type": "map", "fields": {...}}
      },
      "relationships": {
        "orders": "one-to-many"
      }
    }
  }
}
```

### functions.json
Index for quick function lookup:
```json
{
  "functions": [
    {"name": "useAuth", "file": "src/hooks/useAuth.ts", "line": 15, "type": "hook"},
    {"name": "formatDate", "file": "src/utils/date.ts", "line": 8, "type": "function"}
  ]
}
```

### decisions.json
Architectural decisions record:
```json
{
  "decisions": [
    {
      "date": "2025-12-10",
      "title": "Use React Query for server state",
      "context": "Need caching and automatic refetching",
      "decision": "Adopted React Query v5",
      "consequences": "Removed custom fetch hooks"
    }
  ]
}
```

### observations.json
Session learnings and patterns:
```json
{
  "observations": [
    {
      "category": "bugfix",
      "date": "2025-12-15",
      "description": "Race condition in auth flow",
      "resolution": "Added loading state check before redirect"
    }
  ]
}
```

---

## Configuration

### config.json
Main configuration at `~/.claude-memory/config.json`:
```json
{
  "projects": {
    "gyst": {
      "path": "/Users/user/projects/gyst",
      "name": "GYST",
      "ignore": ["node_modules", ".git", "dist"]
    }
  },
  "watcher": {
    "enabled": true,
    "interval": 5000
  }
}
```

### global/preferences.json
Global conventions applied to all projects:
```json
{
  "conventions": [
    {
      "name": "Claude Memory First",
      "rule": "Always read Claude Memory before implementing",
      "priority": "critical"
    }
  ]
}
```

---

## How to Use This Information

When answering questions:

1. **About code health**: Reference health.json scores and explain what the numbers mean
2. **About code structure**: Use summaries.json to understand file purposes
3. **About data**: Reference schema.json for database structure
4. **About functions**: Use functions.json to locate code
5. **About decisions**: Check decisions.json for architectural context
6. **About past issues**: Search observations.json for patterns and fixes

When providing recommendations:

1. Check current health score before suggesting changes
2. Reference existing patterns from summaries.json
3. Consider project preferences from preferences.json
4. Look at health_history.json for trends
5. Reference past decisions to maintain consistency

---

## Available Tools

You can use these MCP tools to query the memory system:

- `memory_query` - Natural language questions about the codebase
- `memory_search` - Semantic search using embeddings
- `memory_similar` - Find files related to a given file
- `memory_health` - Get current health status or run scan
- `memory_functions` - Look up function definitions
- `memory_wireframe` - Get app structure/navigation data
- `memory_sessions` - Search past session observations

---

---

## Cross-Project Portfolio Intelligence

Beyond single-project analysis, Ollama can understand your entire project portfolio:

### Portfolio Overview
- 8 tracked projects with code intelligence
- Health comparisons across all projects
- Technology stack analysis
- Feature catalogs and overlap detection

### Available Portfolio Commands
```bash
mlx portfolio overview    # All projects summary
mlx portfolio health      # Health comparison
mlx portfolio tech        # Technology stacks
mlx portfolio features    # Feature catalog
mlx portfolio sessions    # Recent session activity
mlx portfolio patterns    # Patterns and learnings
mlx portfolio search <q>  # Search across all projects
mlx portfolio ask <q>     # Ask about portfolio
```

### Portfolio Data Available
- **Health comparison**: Scores, trends, and common issues
- **Tech stacks**: Frameworks, databases, languages per project
- **Session history**: 16+ sessions with observations
- **Patterns learned**: Decisions, bugfixes, gotchas
- **Cross-project search**: Semantic similarity across all code

---

## Version Information

- Embedding model: `nomic-embed-text` (768 dimensions)
- Chat model: `llama3.2:3b`
- Storage format: JSON files
- Update mechanism: Watcher service + manual scans
