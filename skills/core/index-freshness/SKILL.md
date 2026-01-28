---
name: index-freshness
description: When user mentions "stale", "outdated", "reindex", "sync", "refresh index", "embeddings outdated", or when search results seem wrong. Guides index maintenance decisions.
---

# Index Freshness Framework

## When This Activates

This skill activates when:
- Search results don't match reality
- User suspects indexes are stale
- After significant code changes
- Periodic maintenance checks

## What Gets Indexed

| Index Type | File | Contents |
|------------|------|----------|
| **Summaries** | `summaries.json` | File descriptions, purposes |
| **Functions** | `functions.json` | Function names, locations |
| **Embeddings** | `embeddings_v2.json` | Semantic vectors for search |
| **Schema** | `schema.json` | Database collections, fields |
| **Health** | `health.json` | Code quality metrics |

## Staleness Detection

### Indicators of Stale Indexes

1. **Search misses** - Can't find code you know exists
2. **Wrong summaries** - Descriptions don't match current code
3. **Missing functions** - New functions not in index
4. **Old health data** - Issues already fixed still showing

### Automatic Detection

The system checks:
```
Files modified since last scan:  15
Last health scan:               3 days ago
Last embedding update:          5 days ago
Git commits since index:        12
```

## Freshness Check Workflow

### 1. Check Last Update Times
```
memory_health action=status project=gyst
```

Returns:
- Last scan timestamp
- Files changed since
- Recommended action

### 2. Identify Changed Files
The system tracks:
- File modification times
- Git commits since last index
- Added/deleted/modified files

### 3. Decide: Incremental or Full Reindex

**Incremental** (fast, <20 files changed):
- Update only changed files
- Preserve unchanged embeddings

**Full Reindex** (slower, but thorough):
- When >20 files changed
- After major refactors
- If indexes seem corrupted

## Reindex Triggers

### Automatic (via Watcher)
- File saved → summary updated
- New file → added to index
- File deleted → removed from index

### Manual Triggers
```bash
# Check freshness
python3 ~/.claude-dash/mlx-tools/freshness_checker.py /path/to/project project-id

# Sync embeddings
python3 ~/.claude-dash/mlx-tools/embedding_sync.py project-id

# Full reindex (via watcher)
~/.claude-dash/watcher/start-watcher.sh reindex project-id
```

## When to Reindex

| Scenario | Action |
|----------|--------|
| Few files changed (<5) | Auto-handled by watcher |
| Moderate changes (5-20) | Incremental reindex |
| Major refactor (>20 files) | Full reindex |
| Search results wrong | Full reindex |
| After branch switch | Check + incremental |
| New project setup | Full index |

## Troubleshooting Stale Indexes

### "Search can't find X"
1. Check if file exists
2. Check if file is in summaries.json
3. Check file modification time vs index time
4. Trigger reindex if needed

### "Embeddings seem wrong"
1. Check embeddings_v2.json timestamp
2. Check if embedding provider changed
3. Consider full embedding regeneration

### "Health shows fixed issues"
1. Check last scan timestamp
2. Run new health scan
3. Clear old health.json and rescan

## MCP Tools

```
# Check health status (includes freshness)
memory_health action=status project=gyst

# Trigger scan
memory_health action=scan project=gyst

# Workers for maintenance
workers_run worker=freshness project=gyst
workers_run worker=consolidate
```

## Best Practices

1. **Let the watcher handle routine updates**
2. **Reindex after major refactors**
3. **Check freshness when search seems off**
4. **Don't reindex unnecessarily** - it takes resources

## Index File Sizes (Reference)

Typical sizes for a medium project:
```
summaries.json     ~500KB
functions.json     ~200KB
embeddings_v2.json ~5MB
health.json        ~50KB
```

If files seem too small, index may be incomplete.
