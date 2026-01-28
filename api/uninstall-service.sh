#!/bin/bash
#
# Uninstall Claude-Dash API launchd service
#

PLIST_NAME="com.claude-dash.api.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "Uninstalling Claude-Dash API Service..."

if [ -f "$PLIST_DST" ]; then
    echo "Stopping service..."
    launchctl unload "$PLIST_DST" 2>/dev/null

    echo "Removing plist..."
    rm "$PLIST_DST"

    echo "Service uninstalled."
else
    echo "Service not installed (plist not found)."
fi

# Also stop any running server started manually
if [ -f "$HOME/.claude-dash/logs/api-server.pid" ]; then
    PID=$(cat "$HOME/.claude-dash/logs/api-server.pid")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping manually-started server (PID: $PID)..."
        kill "$PID"
    fi
    rm -f "$HOME/.claude-dash/logs/api-server.pid"
fi

echo "Done."
