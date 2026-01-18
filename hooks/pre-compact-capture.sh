#!/bin/bash

# PreCompact Hook - Captures learnings before context summarization
# Fires before Claude Code summarizes context (~95% usage or /compact command)
#
# This script ensures no learnings are lost when context is compacted.
# It extracts observations, decisions, and patterns before they get summarized.

CLAUDE_DASH="$HOME/.claude-dash"
CHECKPOINT_DIR="$CLAUDE_DASH/sessions/checkpoints"
EXTRACTOR="$CLAUDE_DASH/mlx-tools/observation_extractor.py"
LOG_FILE="$CLAUDE_DASH/logs/pre-compact.log"

# Ensure directories exist
mkdir -p "$CHECKPOINT_DIR"
mkdir -p "$CLAUDE_DASH/logs"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "PreCompact hook triggered"

# Read hook input from stdin (contains trigger info)
input=$(cat)

# Extract trigger type (auto or manual)
trigger_type=$(echo "$input" | grep -o '"type"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)".*/\1/' | tail -1)
if [ -z "$trigger_type" ]; then
    trigger_type="auto"
fi

log "Trigger type: $trigger_type"

# Detect current project
PROJECT_ROOT="$PWD"
CONFIG_FILE="$CLAUDE_DASH/config.json"

if [ -f "$CONFIG_FILE" ]; then
    PROJECT_ID=$(cat "$CONFIG_FILE" | grep -B2 "\"path\": \"$PROJECT_ROOT\"" | grep '"id"' | sed 's/.*"id": "\([^"]*\)".*/\1/' | head -1)
fi
if [ -z "$PROJECT_ID" ]; then
    PROJECT_ID=$(basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
fi

log "Project: $PROJECT_ID"

# Find the most recent transcript for this project
TRANSCRIPT_DIR="$HOME/.claude/projects"
TRANSCRIPT_PATH=""

# Search for project transcripts
for dir in "$TRANSCRIPT_DIR"/*; do
    if [ -d "$dir" ] && [[ "$dir" == *"$PROJECT_ROOT"* || "$dir" == *"$(echo "$PROJECT_ROOT" | tr '/' '-')"* ]]; then
        # Find most recent .jsonl file
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
    log "No transcript found, skipping extraction"
    echo '{"status": "skipped", "reason": "no_transcript"}'
    exit 0
fi

log "Transcript: $TRANSCRIPT_PATH"

TIMESTAMP=$(date +%s)
CHECKPOINT_FILE="$CHECKPOINT_DIR/pre-compact-$TIMESTAMP.json"
SESSION_ID=$(basename "$TRANSCRIPT_PATH" .jsonl)

# Run observation extraction in lightweight mode
if [ -f "$EXTRACTOR" ]; then
    log "Running observation extraction..."

    python3 "$EXTRACTOR" "$TRANSCRIPT_PATH" "$PROJECT_ID" \
        --session-id "$SESSION_ID" \
        --lightweight \
        --output "$CHECKPOINT_FILE" \
        2>> "$LOG_FILE"

    EXTRACT_STATUS=$?

    if [ $EXTRACT_STATUS -eq 0 ] && [ -f "$CHECKPOINT_FILE" ]; then
        log "Checkpoint saved: $CHECKPOINT_FILE"

        # Add metadata to checkpoint
        TEMP_FILE=$(mktemp)
        python3 << EOF > "$TEMP_FILE"
import json
import sys

try:
    with open("$CHECKPOINT_FILE", 'r') as f:
        data = json.load(f)
except:
    data = {"observations": []}

data["trigger"] = "$trigger_type"
data["trigger_type"] = "pre-compact"
data["project_id"] = "$PROJECT_ID"
data["session_id"] = "$SESSION_ID"
data["timestamp"] = "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Extract key info to preserve in summary
key_info = []
for obs in data.get("observations", []):
    if obs.get("category") in ["decision", "pattern", "gotcha"]:
        key_info.append(f"[{obs['category']}] {obs['observation'][:100]}")

data["key_context"] = key_info[:5]

print(json.dumps(data, indent=2))
EOF
        mv "$TEMP_FILE" "$CHECKPOINT_FILE"

        # Output context that should be preserved in the summary
        if [ -f "$CHECKPOINT_FILE" ]; then
            KEY_CONTEXT=$(python3 -c "import json; d=json.load(open('$CHECKPOINT_FILE')); print('\n'.join(d.get('key_context', [])))")
            if [ -n "$KEY_CONTEXT" ]; then
                echo '{"status": "captured", "inject_into_summary": "'
                echo "$KEY_CONTEXT" | head -5
                echo '"}'
            else
                echo '{"status": "captured", "observations": 0}'
            fi
        fi
    else
        log "Extraction failed with status $EXTRACT_STATUS"
        echo '{"status": "extraction_failed"}'
    fi
else
    log "Extractor not found: $EXTRACTOR"
    echo '{"status": "error", "reason": "extractor_not_found"}'
fi

log "PreCompact hook completed"
