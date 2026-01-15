#!/bin/bash
# Wrapper script for watcher - handles dynamic node path resolution
# This allows the launchd service to work on both Intel and Apple Silicon Macs

cd "$(dirname "$0")"

# Find node in common locations
if command -v node &> /dev/null; then
    NODE_PATH=$(command -v node)
elif [ -x "/opt/homebrew/bin/node" ]; then
    NODE_PATH="/opt/homebrew/bin/node"
elif [ -x "/usr/local/bin/node" ]; then
    NODE_PATH="/usr/local/bin/node"
elif [ -x "$HOME/.nvm/versions/node/$(ls -1 $HOME/.nvm/versions/node 2>/dev/null | tail -1)/bin/node" ]; then
    NODE_PATH="$HOME/.nvm/versions/node/$(ls -1 $HOME/.nvm/versions/node | tail -1)/bin/node"
else
    echo "ERROR: Node.js not found" >&2
    exit 1
fi

echo "Using Node.js at: $NODE_PATH"
exec "$NODE_PATH" watcher.js
