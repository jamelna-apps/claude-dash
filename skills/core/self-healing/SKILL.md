# Self-Healing Skill

Auto-detect and fix broken dependencies when resources are removed from claude-dash.

## When This Activates

- User mentions removing a model, dependency, or resource
- User asks about impact of removing something
- System detects broken references after changes
- User mentions cleanup or deprecation

## Workflow

### 1. Before Removing a Resource

```bash
# Analyze what would break
mlx self-heal analyze <resource_id> [replacement]

# Example:
mlx self-heal analyze deepseek-coder:6.7b gemma3:4b-it-qat
```

This shows:
- All files that reference the resource
- Severity of each impact (critical/high/medium/low/info)
- Suggested fix strategy for each

### 2. Apply Fixes

```bash
# Preview changes (dry run - default)
mlx self-heal fix <resource_id> <replacement>

# Apply changes (creates backup first)
mlx self-heal fix <resource_id> <replacement> --apply
```

### 3. If Something Goes Wrong

```bash
# List available backups
mlx self-heal check

# Rollback to a backup
mlx self-heal rollback <backup_timestamp>
```

### 4. Routine Health Checks

```bash
# Check for broken dependencies
mlx self-heal check

# Sync registry with actual Ollama state
mlx self-heal sync
```

## MCP Tools Available

| Tool | Purpose |
|------|---------|
| `self_heal_check` | Check system health for broken dependencies |
| `self_heal_analyze` | Analyze impact of removing a resource |
| `self_heal_fix` | Apply cascade fixes (with dry_run option) |
| `self_heal_rollback` | Rollback from a backup |

## Best Practices

1. **Always analyze before removing** - Run impact analysis first
2. **Review the preview** - Check the dry-run output before applying
3. **Backups are automatic** - Every fix operation creates a backup
4. **High-confidence fixes only** - Fixes below 50% confidence are skipped by default
5. **Commit after healing** - Stage and commit the fixed files

## Example Session

User: "I want to remove the deepseek-coder model"

Claude should:
1. Run `self_heal_analyze` with resource_id="deepseek-coder:6.7b"
2. Show the impact summary
3. Ask user for replacement (suggest gemma3:4b-it-qat)
4. Run `self_heal_fix` with dry_run=true to preview
5. If user approves, run with dry_run=false
6. Suggest committing the changes

## Severity Levels

| Level | Meaning | Example |
|-------|---------|---------|
| CRITICAL | System won't work | config.py, gateway/server.js |
| HIGH | Major feature broken | Active tools, API handlers |
| MEDIUM | Some functionality affected | Secondary tools |
| LOW | Minor impact | Documentation, deprecated code |
| INFO | Just informational | Comments, docstrings |

## Integration with Memory System

The self-healing system integrates with:
- **Dependency Registry**: Tracks resources in `memory/dependency_registry.json`
- **Backups**: Stored in `backups/self_heal/`
- **MCP Gateway**: Tools available via claude-dash MCP server
- **CLI**: Available via `mlx self-heal` commands
