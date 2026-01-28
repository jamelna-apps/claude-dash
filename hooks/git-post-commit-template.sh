#!/bin/bash

# Git Post-Commit Hook - Auto-syncs commits to project roadmap
#
# Installation:
#   cp ~/.claude-dash/hooks/git-post-commit-template.sh .git/hooks/post-commit
#   chmod +x .git/hooks/post-commit
#
# Or use the installer:
#   ~/.claude-dash/hooks/install-git-hook.sh [project-path]

MEMORY_ROOT="$HOME/.claude-dash"
GIT_ROADMAP_SYNC="$MEMORY_ROOT/memory/git_roadmap_sync.py"
PYTHON="/usr/bin/python3"

# Get repo root
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

# Only run if sync script exists
if [ ! -f "$GIT_ROADMAP_SYNC" ]; then
  exit 0
fi

# Detect project from config
CONFIG_FILE="$MEMORY_ROOT/config.json"
PROJECT_ID=""

if [ -f "$CONFIG_FILE" ]; then
  PROJECT_ID=$("$PYTHON" -c "
import sys, json
try:
    with open('$CONFIG_FILE') as f:
        config = json.load(f)
    for p in config.get('projects', []):
        if p.get('path', '').rstrip('/') == '$REPO_ROOT'.rstrip('/'):
            print(p.get('id', ''))
            break
except: pass
" 2>/dev/null)
fi

# Skip if no project detected
if [ -z "$PROJECT_ID" ]; then
  exit 0
fi

# Check if roadmap exists for this project
ROADMAP_FILE="$MEMORY_ROOT/projects/$PROJECT_ID/roadmap.json"
if [ ! -f "$ROADMAP_FILE" ]; then
  exit 0
fi

# Run sync in background (don't block commit)
nohup "$PYTHON" "$GIT_ROADMAP_SYNC" \
  --repo "$REPO_ROOT" \
  --project "$PROJECT_ID" \
  --last-commit-only \
  >> "$MEMORY_ROOT/logs/git-roadmap-sync.log" 2>&1 &

exit 0
