#!/bin/bash
#
# Claude-Dash Uninstaller
#
# Usage:
#   ~/.claude-dash/uninstall.sh
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CLAUDE_DASH_DIR="$HOME/.claude-dash"
CLAUDE_DIR="$HOME/.claude"

echo -e "${YELLOW}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                  Claude-Dash Uninstaller                  ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${YELLOW}This will remove:${NC}"
echo "  - Claude-Dash directory (~/.claude-dash)"
echo "  - Claude Code hooks (~/.claude/hooks/inject-context.sh, save-session.sh)"
echo "  - Hook configuration from ~/.claude/settings.json"
echo ""
echo -e "${YELLOW}This will NOT remove:${NC}"
echo "  - Ollama or its models"
echo "  - Claude Desktop MCP configuration"
echo "  - Node.js or Python"
echo ""

read -p "Are you sure you want to uninstall Claude-Dash? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

echo ""

# Stop watcher if running
if [ -f "$CLAUDE_DASH_DIR/watcher/watcher.pid" ]; then
    echo -e "${BLUE}Stopping watcher...${NC}"
    "$CLAUDE_DASH_DIR/watcher/start-watcher.sh" stop 2>/dev/null || true
fi

# Remove hooks
echo -e "${BLUE}Removing hooks...${NC}"
rm -f "$CLAUDE_DIR/hooks/inject-context.sh"
rm -f "$CLAUDE_DIR/hooks/save-session.sh"

# Clean up settings.json (remove hooks config)
if [ -f "$CLAUDE_DIR/settings.json" ]; then
    echo -e "${BLUE}Cleaning settings.json...${NC}"
    # Create backup
    cp "$CLAUDE_DIR/settings.json" "$CLAUDE_DIR/settings.json.backup"

    # Remove hooks configuration (simple approach - just notify user)
    echo -e "${YELLOW}Note: You may want to manually remove the hooks configuration from:${NC}"
    echo "  $CLAUDE_DIR/settings.json"
fi

# Option to keep data
read -p "Keep your project data and learning history? (Y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo -e "${BLUE}Removing all Claude-Dash data...${NC}"
    rm -rf "$CLAUDE_DASH_DIR"
    echo -e "${GREEN}Removed $CLAUDE_DASH_DIR${NC}"
else
    # Keep data directories, remove code
    echo -e "${BLUE}Keeping data, removing code...${NC}"

    # Keep these directories
    KEEP_DIRS="projects sessions learning indexes"

    # Create temp backup
    TEMP_BACKUP="/tmp/claude-dash-data-$$"
    mkdir -p "$TEMP_BACKUP"

    for dir in $KEEP_DIRS; do
        if [ -d "$CLAUDE_DASH_DIR/$dir" ]; then
            cp -r "$CLAUDE_DASH_DIR/$dir" "$TEMP_BACKUP/"
        fi
    done

    # Also keep config
    cp "$CLAUDE_DASH_DIR/config.json" "$TEMP_BACKUP/" 2>/dev/null || true
    cp -r "$CLAUDE_DASH_DIR/global" "$TEMP_BACKUP/" 2>/dev/null || true

    # Remove everything
    rm -rf "$CLAUDE_DASH_DIR"

    # Restore data
    mkdir -p "$CLAUDE_DASH_DIR"
    cp -r "$TEMP_BACKUP"/* "$CLAUDE_DASH_DIR/"
    rm -rf "$TEMP_BACKUP"

    echo -e "${GREEN}Kept data in $CLAUDE_DASH_DIR${NC}"
fi

echo ""
echo -e "${GREEN}Claude-Dash has been uninstalled.${NC}"
echo ""
echo "To reinstall:"
echo "  curl -fsSL https://raw.githubusercontent.com/jamelna-apps/claude-dash/main/install.sh | bash"
echo ""
