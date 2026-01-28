#!/bin/bash
#
# Install Claude-Dash API as a macOS launchd service
#
# This will:
# 1. Copy the plist to ~/Library/LaunchAgents
# 2. Load the service
# 3. Start the API server
#
# The server will auto-start on login.
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.claude-dash.api.plist"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "Installing Claude-Dash API Service..."
echo ""

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$HOME/Library/LaunchAgents"

# Create logs directory
mkdir -p "$HOME/.claude-dash/logs"

# Unload existing service if present
if launchctl list | grep -q "com.claude-dash.api"; then
    echo "Stopping existing service..."
    launchctl unload "$PLIST_DST" 2>/dev/null
fi

# Copy plist
echo "Installing plist to $PLIST_DST"
cp "$PLIST_SRC" "$PLIST_DST"

# Load service
echo "Loading service..."
launchctl load "$PLIST_DST"

# Check if it started
sleep 2
if launchctl list | grep -q "com.claude-dash.api"; then
    echo ""
    echo "Service installed and running!"
    echo ""
    echo "Commands:"
    echo "  Status:  launchctl list | grep claude-dash"
    echo "  Stop:    launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
    echo "  Start:   launchctl load ~/Library/LaunchAgents/$PLIST_NAME"
    echo "  Logs:    tail -f ~/.claude-dash/logs/api-server.log"
    echo ""
    echo "API Endpoints:"
    echo "  http://localhost:5100/health"
    echo "  http://localhost:5100/v1/models"
    echo "  http://localhost:5100/v1/chat/completions"
    echo ""
    echo "For Enchanted:"
    echo "  Server URL: http://$(hostname):5100/v1"
    echo "  Or use your Tailscale IP"
else
    echo ""
    echo "Warning: Service may not have started. Check logs:"
    echo "  tail -f ~/.claude-dash/logs/api-server.log"
fi
