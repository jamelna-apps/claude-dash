#!/bin/bash

# Claude Memory - Session End Hook
# Saves session state for continuity across sessions

MEMORY_ROOT="$HOME/.claude-dash"
SESSIONS_DIR="$MEMORY_ROOT/sessions"
CLAUDE_TODOS="$HOME/.claude/todos"

# Read hook input from stdin
INPUT=$(cat)

# Extract data from hook input
SESSION_ID=$(echo "$INPUT" | grep -o '"session_id"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: *"\([^"]*\)".*/\1/')
TRANSCRIPT_PATH=$(echo "$INPUT" | grep -o '"transcript_path"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: *"\([^"]*\)".*/\1/')
CWD=$(echo "$INPUT" | grep -o '"cwd"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: *"\([^"]*\)".*/\1/')
EXIT_REASON=$(echo "$INPUT" | grep -o '"reason"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: *"\([^"]*\)".*/\1/')

# Detect project
PROJECT_ROOT="${CWD:-$PWD}"
CONFIG_FILE="$MEMORY_ROOT/config.json"

get_project_id() {
  if [ -f "$CONFIG_FILE" ]; then
    # Try exact match first
    project_id=$(cat "$CONFIG_FILE" | python3 -c "
import sys, json
try:
    config = json.load(sys.stdin)
    for p in config.get('projects', []):
        if p.get('path', '').rstrip('/') == '$PROJECT_ROOT'.rstrip('/'):
            print(p.get('id', ''))
            break
except: pass
" 2>/dev/null)
    echo "$project_id"
  fi
}

PROJECT_ID=$(get_project_id)
if [ -z "$PROJECT_ID" ]; then
  PROJECT_ID=$(basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
fi

# Create project session directory
PROJECT_SESSION_DIR="$SESSIONS_DIR/$PROJECT_ID"
mkdir -p "$PROJECT_SESSION_DIR"

# Get current todos if they exist
TODOS_JSON="[]"
if [ -d "$CLAUDE_TODOS" ]; then
  # Find most recent todo file
  LATEST_TODO=$(ls -t "$CLAUDE_TODOS"/*.json 2>/dev/null | head -1)
  if [ -f "$LATEST_TODO" ]; then
    TODOS_JSON=$(cat "$LATEST_TODO")
  fi
fi

# Extract summary from transcript (last few user messages)
SUMMARY=""
if [ -f "$TRANSCRIPT_PATH" ]; then
  # Get last 5 user messages as context
  SUMMARY=$(cat "$TRANSCRIPT_PATH" | python3 -c "
import sys, json
messages = []
for line in sys.stdin:
    try:
        msg = json.loads(line.strip())
        if msg.get('type') == 'human':
            content = msg.get('message', {}).get('content', '')
            if isinstance(content, str) and content.strip():
                messages.append(content[:200])  # Truncate long messages
    except: pass
# Get last 5 messages
for m in messages[-5:]:
    print(m)
" 2>/dev/null)
fi

# Create session state file
SESSION_FILE="$PROJECT_SESSION_DIR/session.json"

cat > "$SESSION_FILE" << EOF
{
  "sessionId": "$SESSION_ID",
  "projectId": "$PROJECT_ID",
  "projectPath": "$PROJECT_ROOT",
  "savedAt": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "exitReason": "$EXIT_REASON",
  "todos": $TODOS_JSON,
  "recentPrompts": $(echo "$SUMMARY" | python3 -c "
import sys, json
prompts = [line.strip() for line in sys.stdin if line.strip()]
print(json.dumps(prompts))
" 2>/dev/null || echo '[]'),
  "transcriptPath": "$TRANSCRIPT_PATH"
}
EOF

# Also save a backup with timestamp for history
BACKUP_FILE="$PROJECT_SESSION_DIR/session-$(date +%Y%m%d-%H%M%S).json"
cp "$SESSION_FILE" "$BACKUP_FILE"

# Keep only last 10 backups (using find for safety)
find "$PROJECT_SESSION_DIR" -name "session-*.json" -type f -printf '%T@ %p\n' 2>/dev/null | \
  sort -rn | tail -n +11 | cut -d' ' -f2- | xargs -r rm -f 2>/dev/null || \
  # Fallback for macOS (doesn't have -printf)
  ls -t "$PROJECT_SESSION_DIR"/session-*.json 2>/dev/null | tail -n +11 | while read -r f; do rm -f "$f"; done 2>/dev/null

# === NEW: Session Memory with Observation Extraction ===

TRANSCRIPTS_DIR="$MEMORY_ROOT/sessions/transcripts"
mkdir -p "$TRANSCRIPTS_DIR"

# Archive the transcript
if [ -f "$TRANSCRIPT_PATH" ] && [ -n "$SESSION_ID" ]; then
  TRANSCRIPT_ARCHIVE="$TRANSCRIPTS_DIR/${SESSION_ID}.jsonl"
  cp "$TRANSCRIPT_PATH" "$TRANSCRIPT_ARCHIVE" 2>/dev/null
fi

# Extract observations using Ollama (runs in background to not block)
PYTHON="/usr/bin/python3"
EXTRACTOR="$MEMORY_ROOT/mlx-tools/observation_extractor.py"
SUMMARIZER="$MEMORY_ROOT/memory/summarizer.py"

# Ensure logs directory exists
mkdir -p "$MEMORY_ROOT/logs"

if [ -f "$EXTRACTOR" ] && [ -f "$TRANSCRIPT_PATH" ]; then
  # Run extraction in background using native Ollama (Metal GPU accelerated)
  nohup "$PYTHON" "$EXTRACTOR" "$TRANSCRIPT_PATH" "$PROJECT_ID" \
    --session-id "$SESSION_ID" \
    > "$MEMORY_ROOT/logs/extraction-${SESSION_ID}.log" 2>&1 &
fi

# Generate session summary for continuity
if [ -f "$SUMMARIZER" ] && [ -f "$TRANSCRIPT_PATH" ]; then
  nohup "$PYTHON" "$SUMMARIZER" "$TRANSCRIPT_PATH" "$PROJECT_ID" \
    --session-id "$SESSION_ID" \
    >> "$MEMORY_ROOT/logs/extraction-${SESSION_ID}.log" 2>&1 &
fi

# Clean up temp tool results buffer
TOOL_BUFFER_DIR="/tmp/claude-session-$SESSION_ID"
if [ -d "$TOOL_BUFFER_DIR" ]; then
  rm -rf "$TOOL_BUFFER_DIR" 2>/dev/null
fi

# === WEEKLY TRANSCRIPT COMPACTION ===
# Compress old transcripts to digests (saves ~99% space while preserving context)

COMPACTOR="$MEMORY_ROOT/memory/transcript_compactor.py"
LAST_COMPACT_FILE="$MEMORY_ROOT/.last_compaction"
COMPACT_INTERVAL_DAYS=7

should_compact() {
  if [ ! -f "$LAST_COMPACT_FILE" ]; then
    return 0  # Never compacted
  fi

  last_compact=$(cat "$LAST_COMPACT_FILE" 2>/dev/null)
  now=$(date +%s)
  interval=$((COMPACT_INTERVAL_DAYS * 86400))

  if [ $((now - last_compact)) -gt $interval ]; then
    return 0  # Time to compact
  fi

  return 1  # Not yet
}

if [ -f "$COMPACTOR" ] && should_compact; then
  echo "Running weekly transcript compaction..."
  nohup "$PYTHON" "$COMPACTOR" --compact-all --keep 10 \
    >> "$MEMORY_ROOT/logs/compaction.log" 2>&1 &
  date +%s > "$LAST_COMPACT_FILE"
fi

# === BACKGROUND WORKERS - Session End Triggers ===
# Run learning consolidation and health checks at session end

WORKERS="$MEMORY_ROOT/workers/background_workers.py"

if [ -f "$WORKERS" ]; then
  # Run consolidation to merge learning trajectories into patterns
  nohup "$PYTHON" "$WORKERS" consolidate \
    >> "$MEMORY_ROOT/logs/workers.log" 2>&1 &

  # Run freshness check to alert on stale indexes
  nohup "$PYTHON" "$WORKERS" freshness --project "$PROJECT_ID" \
    >> "$MEMORY_ROOT/logs/workers.log" 2>&1 &
fi

# === REASONING BANK - Record Session Learning ===
# If there were corrections in this session, record them

REASONING_BANK="$MEMORY_ROOT/learning/reasoning_bank.py"

if [ -f "$REASONING_BANK" ] && [ -f "$TRANSCRIPT_PATH" ]; then
  # Extract any corrections/learnings from the session
  nohup "$PYTHON" -c "
import sys
import json
sys.path.insert(0, '$MEMORY_ROOT/learning')
from reasoning_bank import consolidate_learning
# Run consolidation at session end
consolidate_learning(force=False)
" >> "$MEMORY_ROOT/logs/reasoning.log" 2>&1 &
fi

exit 0
