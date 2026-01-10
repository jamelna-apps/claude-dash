# Archived: MCP_DOCKER Server Configuration

**Archived:** 2026-01-07
**Status:** Removed (not in use)
**Reason:** Configuration was not persisted; replaced by claude-in-chrome for browser automation

## What It Was

MCP_DOCKER was an MCP server that provided browser automation and Docker-related tools. Based on session history, it exposed these tools:

### Browser Tools (Playwright-based)
- `browser_navigate` - Navigate to URLs
- `browser_click` - Click elements
- `browser_snapshot` - Take page snapshots
- `browser_take_screenshot` - Capture screenshots
- `browser_console_messages` - Read console output
- `browser_tabs` - Manage browser tabs
- `browser_close` - Close browser

### Docker/MCP Tools
- `mcp-find` - Find MCP servers
- `mcp-add` - Add MCP servers
- `mcp-exec` - Execute MCP commands
- `mcp-config-set` - Configure MCP settings

## Why It Failed

From debug log (2026-01-07):
```
MCP server "MCP_DOCKER": Starting connection with timeout of 30000ms
MCP server "MCP_DOCKER" Server stderr: Docker Desktop is not running
MCP server "MCP_DOCKER": Connection failed after 426ms: MCP error -32000: Connection closed
```

The server required Docker Desktop to be running.

## How to Restore (if needed)

If you need this functionality again, create `~/.claude/settings.json` or project-level `.mcp.json`:

```json
{
  "mcpServers": {
    "MCP_DOCKER": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-docker"]
    }
  }
}
```

Or for Playwright specifically:
```json
{
  "mcpServers": {
    "MCP_DOCKER": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-playwright"]
    }
  }
}
```

## Current Alternative

Browser automation is now handled by `claude-in-chrome` MCP server, which connects directly to Chrome via the Claude Code browser extension.
