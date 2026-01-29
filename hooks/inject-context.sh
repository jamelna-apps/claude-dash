#!/bin/bash

# Claude Memory - Optimized Prompt Submit Hook
# Uses consolidated Python injector for ~80% latency reduction
# Backup of original: inject-context.sh.backup-YYYYMMDD

MEMORY_ROOT="$HOME/.claude-dash"
CONSOLIDATED_INJECTOR="$MEMORY_ROOT/hooks/inject_all_context.py"
JSON_HELPER="$MEMORY_ROOT/hooks/json-helper.sh"

# Load JSON helper if available
if [ -f "$JSON_HELPER" ]; then
  source "$JSON_HELPER"
fi

# Read hook input from stdin
input=$(cat)

# Extract prompt text
if type json_get &>/dev/null; then
  prompt=$(echo "$input" | json_get "prompt")
else
  prompt=$(echo "$input" | grep -o '"prompt"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"prompt"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/' | head -1)
fi

# Detect current project
PROJECT_ROOT="$PWD"
CONFIG_FILE="$MEMORY_ROOT/config.json"

if type get_project_id &>/dev/null; then
  PROJECT_ID=$(get_project_id "$PROJECT_ROOT")
else
  if [ -f "$CONFIG_FILE" ]; then
    PROJECT_ID=$(cat "$CONFIG_FILE" | grep -B2 "\"path\": \"$PROJECT_ROOT\"" | grep '"id"' | sed 's/.*"id": "\([^"]*\)".*/\1/' | head -1)
  fi
fi
if [ -z "$PROJECT_ID" ]; then
  PROJECT_ID=$(basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
fi

# Track first message of session (one marker per Claude process, not per shell)
SESSION_MARKERS_DIR="$MEMORY_ROOT/.session-markers"
mkdir -p "$SESSION_MARKERS_DIR" 2>/dev/null
# Use PPID (parent process ID) which is the Claude CLI process, not $$ (subshell PID)
FIRST_MESSAGE_MARKER="$SESSION_MARKERS_DIR/claude-session-$PPID"

# Clean up old markers (older than 6 hours instead of 1 day)
find "$SESSION_MARKERS_DIR" -name "claude-session-*" -mmin +360 -delete 2>/dev/null

# Determine if first message
FIRST_FLAG=""
if [ ! -f "$FIRST_MESSAGE_MARKER" ]; then
  touch "$FIRST_MESSAGE_MARKER"
  FIRST_FLAG="--first"
fi

# Run consolidated injector (single Python process)
if [ -f "$CONSOLIDATED_INJECTOR" ] && [ -n "$prompt" ]; then
  # Run with timeout if available (Linux), otherwise run directly (macOS)
  if command -v timeout &>/dev/null; then
    OUTPUT=$(timeout 5 python3 "$CONSOLIDATED_INJECTOR" "$prompt" "$PROJECT_ID" $FIRST_FLAG 2>/dev/null)
  else
    # macOS: run directly (Python script has internal timeouts)
    OUTPUT=$(python3 "$CONSOLIDATED_INJECTOR" "$prompt" "$PROJECT_ID" $FIRST_FLAG 2>/dev/null)
  fi
  if [ -n "$OUTPUT" ]; then
    echo "$OUTPUT"
  fi
fi

exit 0
