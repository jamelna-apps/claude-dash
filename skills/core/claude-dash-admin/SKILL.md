---
name: claude-dash-admin
description: When user mentions "system health", "cleanup", "optimize claude-dash", "memory system", "indexes", "watcher", or wants to maintain the claude-dash infrastructure. Provides self-maintenance guidance.
---

# Claude-Dash Administration Framework

## When This Activates

This skill activates for system maintenance:
- Health checks and diagnostics
- Storage cleanup and optimization
- Index management
- Service troubleshooting

## System Components

### Core Services
| Service | Purpose | Check Command |
|---------|---------|---------------|
| **Watcher** | File monitoring, index updates | `ps aux \| grep watcher` |
| **Gateway** | MCP routing, caching | `ps aux \| grep gateway` |
| **Ollama** | Local LLM | `ollama list` |
| **Dashboard** | Visualization | Port 3333 |

### Storage Locations
```
~/.claude-dash/
├── projects/       # Project memory (indexes, summaries)
├── sessions/       # Session data, transcripts
├── learning/       # Corrections, preferences, calibration
├── mlx-tools/      # Local AI tools (Ollama-based)
├── skills/         # Skill definitions
├── logs/           # Service logs
├── indexes/        # HNSW search indexes
└── config.json     # Main configuration
```

## Health Checks

### Quick Health Check
```
memory_health action=status
```

### Full Diagnostic
```bash
# Check services
ps aux | grep -E "(watcher|gateway|ollama)"

# Check storage
du -sh ~/.claude-dash/*/

# Check recent errors
tail -20 ~/.claude-dash/logs/watcher-error.log

# Check gateway metrics
gateway_metrics format=summary
```

## Common Maintenance Tasks

### 1. Clean Up Storage
```bash
# Run session archival
python3 ~/.claude-dash/scripts/archive-sessions.py

# Run log rotation
~/.claude-dash/scripts/log-rotation.sh
```

### 2. Refresh Indexes
```bash
# Trigger HNSW rebuild
hnsw_status action=rebuild project=gyst

# Run freshness check
workers_run worker=freshness project=gyst
```

### 3. Consolidate Learning
```bash
# Run observation consolidation
workers_run worker=consolidate
```

### 4. Restart Services
```bash
# Restart watcher
~/.claude-dash/watcher/start-watcher.sh restart

# Restart gateway (via Claude settings or restart Claude)
```

## Troubleshooting

### "Memory search returns nothing"
1. Check if project is registered in config.json
2. Verify index files exist: `ls ~/.claude-dash/projects/{project}/`
3. Check watcher is running
4. Trigger reindex if needed

### "Hook is slow"
1. Check hook timeout in settings
2. Review inject-context.sh performance
3. Consolidate to single Python process (inject_all_context.py)

### "Watcher crashes"
1. Check watcher-error.log
2. Verify project paths exist
3. Check for permission issues

### "Ollama not responding"
1. Check: `ollama list`
2. Restart: `ollama serve`
3. Verify model exists: `ollama pull gemma3:4b-it-qat`

## Configuration

### Main Config (config.json)
```json
{
  "projects": [...],
  "watcher": {
    "enabled": true,
    "ignorePatterns": [...],
    "scanIntervalMs": 5000
  }
}
```

### Adding a New Project
```json
{
  "id": "project-id",
  "displayName": "Project Name",
  "path": "/full/path/to/project",
  "memoryPath": "projects/project-id"
}
```

## Performance Metrics

### Gateway Efficiency
```
gateway_metrics format=detailed
```
Shows:
- Cache hit rate (target: >50%)
- Local routing rate (higher = cheaper)
- Token savings

### Learning Status
```
learning_status component=all
```
Shows:
- Preferences learned
- Corrections recorded
- Confidence calibration

## Scheduled Maintenance

These run automatically via cron:
- **3 AM**: Log rotation
- **Background**: Watcher auto-updates

Manual periodic tasks:
- **Weekly**: Session archival
- **Monthly**: Review and clean old projects
- **As needed**: HNSW index rebuild

## Emergency Recovery

### Reset Project Memory
```bash
rm -rf ~/.claude-dash/projects/{project}/*
# Watcher will rebuild on next file change
```

### Reset All Indexes
```bash
hnsw_status action=rebuild-all
```

### Clear Corrupted State
```bash
# Backup first
cp -r ~/.claude-dash ~/.claude-dash.backup

# Then clear specific problematic data
rm ~/.claude-dash/sessions/observations.json
rm ~/.claude-dash/learning/corrections.json
```
