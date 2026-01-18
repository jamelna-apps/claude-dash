#!/bin/bash

# Incremental Checkpoint Script - Lightweight session state capture
# Runs in background every N messages to protect against crashes
#
# This script captures minimal session state without blocking the main conversation.
# It's designed to be fast and non-disruptive.

CLAUDE_DASH="$HOME/.claude-dash"
CHECKPOINT_DIR="$CLAUDE_DASH/sessions/checkpoints"
COUNTER_FILE="$CLAUDE_DASH/sessions/message_counter"
LOG_FILE="$CLAUDE_DASH/logs/checkpoints.log"
EXTRACTOR="$CLAUDE_DASH/mlx-tools/observation_extractor.py"

# Ensure directories exist
mkdir -p "$CHECKPOINT_DIR"
mkdir -p "$CLAUDE_DASH/logs"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Read message count
MESSAGE_COUNT=$(cat "$COUNTER_FILE" 2>/dev/null || echo "0")
log "Checkpoint triggered at message $MESSAGE_COUNT"

# Detect current project
PROJECT_ROOT="$PWD"
CONFIG_FILE="$CLAUDE_DASH/config.json"

if [ -f "$CONFIG_FILE" ]; then
    PROJECT_ID=$(cat "$CONFIG_FILE" | grep -B2 "\"path\": \"$PROJECT_ROOT\"" | grep '"id"' | sed 's/.*"id": "\([^"]*\)".*/\1/' | head -1)
fi
if [ -z "$PROJECT_ID" ]; then
    PROJECT_ID=$(basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
fi

# Find current transcript
TRANSCRIPT_DIR="$HOME/.claude/projects"
TRANSCRIPT_PATH=""

# Search for project transcripts
for dir in "$TRANSCRIPT_DIR"/*; do
    if [ -d "$dir" ] && [[ "$dir" == *"$PROJECT_ROOT"* || "$dir" == *"$(echo "$PROJECT_ROOT" | tr '/' '-')"* ]]; then
        TRANSCRIPT_PATH=$(ls -t "$dir"/*.jsonl 2>/dev/null | head -1)
        break
    fi
done

# Fallback: try encoded path
if [ -z "$TRANSCRIPT_PATH" ]; then
    ENCODED_PATH=$(echo "$PROJECT_ROOT" | sed 's|/|-|g' | sed 's|^-||')
    if [ -d "$TRANSCRIPT_DIR/-$ENCODED_PATH" ]; then
        TRANSCRIPT_PATH=$(ls -t "$TRANSCRIPT_DIR/-$ENCODED_PATH"/*.jsonl 2>/dev/null | head -1)
    fi
fi

if [ -z "$TRANSCRIPT_PATH" ]; then
    log "No transcript found, skipping checkpoint"
    exit 0
fi

TIMESTAMP=$(date +%s)
CHECKPOINT_FILE="$CHECKPOINT_DIR/checkpoint-$TIMESTAMP.json"
SESSION_ID=$(basename "$TRANSCRIPT_PATH" .jsonl)

# Run lightweight extraction
if [ -f "$EXTRACTOR" ]; then
    log "Running lightweight extraction..."

    # Use --lightweight flag for faster extraction (skips Ollama, uses simple extraction)
    timeout 30 python3 "$EXTRACTOR" "$TRANSCRIPT_PATH" "$PROJECT_ID" \
        --session-id "$SESSION_ID" \
        --lightweight \
        --output "$CHECKPOINT_FILE" \
        2>> "$LOG_FILE"

    EXTRACT_STATUS=$?

    if [ $EXTRACT_STATUS -eq 0 ] && [ -f "$CHECKPOINT_FILE" ]; then
        # Add checkpoint metadata
        TEMP_FILE=$(mktemp)
        python3 << EOF > "$TEMP_FILE"
import json

try:
    with open("$CHECKPOINT_FILE", 'r') as f:
        data = json.load(f)
except:
    data = {"observations": []}

data["trigger"] = "incremental"
data["message_count"] = $MESSAGE_COUNT
data["project_id"] = "$PROJECT_ID"
data["session_id"] = "$SESSION_ID"
data["timestamp"] = "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

print(json.dumps(data, indent=2))
EOF
        mv "$TEMP_FILE" "$CHECKPOINT_FILE"
        log "Checkpoint saved: $CHECKPOINT_FILE ($(wc -c < "$CHECKPOINT_FILE") bytes)"
    else
        log "Extraction failed or timed out (status: $EXTRACT_STATUS)"
    fi
else
    # Fallback: create minimal checkpoint without extractor
    log "Extractor not found, creating minimal checkpoint"

    python3 << EOF > "$CHECKPOINT_FILE"
import json
from datetime import datetime
from pathlib import Path

checkpoint = {
    "trigger": "incremental",
    "message_count": $MESSAGE_COUNT,
    "project_id": "$PROJECT_ID",
    "session_id": "$SESSION_ID",
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "observations": []
}

# Read recent messages from transcript for minimal context
transcript_path = Path("$TRANSCRIPT_PATH")
if transcript_path.exists():
    recent_actions = []
    files_modified = []

    with open(transcript_path, 'r') as f:
        lines = f.readlines()[-50:]  # Last 50 messages
        for line in lines:
            try:
                msg = json.loads(line.strip())
                if msg.get("type") == "assistant":
                    content = msg.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                tool = block.get("name", "")
                                tool_input = block.get("input", {})
                                if tool == "Edit":
                                    fp = tool_input.get("file_path", "")
                                    if fp and fp not in files_modified:
                                        files_modified.append(fp)
                                elif tool == "Write":
                                    fp = tool_input.get("file_path", "")
                                    if fp:
                                        recent_actions.append(f"Created: {fp}")
            except:
                continue

    checkpoint["files_modified"] = files_modified[-10:]
    checkpoint["recent_actions"] = recent_actions[-5:]

print(json.dumps(checkpoint, indent=2))
EOF

    if [ -f "$CHECKPOINT_FILE" ]; then
        log "Minimal checkpoint saved"
    fi
fi

# Cleanup: keep only last 5 incremental checkpoints (preserve pre-compact ones)
CHECKPOINT_COUNT=$(ls -1 "$CHECKPOINT_DIR"/checkpoint-*.json 2>/dev/null | wc -l)
if [ "$CHECKPOINT_COUNT" -gt 5 ]; then
    log "Cleaning old checkpoints (keeping last 5)"
    ls -1t "$CHECKPOINT_DIR"/checkpoint-*.json 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null
fi

log "Checkpoint complete"
