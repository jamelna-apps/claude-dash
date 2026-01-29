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

# === OUTCOME TRACKING ===
# Infer session outcome from transcript and record for learning

OUTCOME_TRACKER="$MEMORY_ROOT/learning/outcome_tracker.py"
if [ -f "$OUTCOME_TRACKER" ] && [ -f "$TRANSCRIPT_PATH" ]; then
  # Infer outcome from transcript (look for error indicators vs success indicators)
  OUTCOME=$(cat "$TRANSCRIPT_PATH" | python3 -c "
import sys, json
error_indicators = ['error', 'failed', 'crash', 'bug', 'broken', 'not working', 'issue']
success_indicators = ['works', 'fixed', 'done', 'complete', 'thanks', 'perfect', 'great']
errors = 0
successes = 0
last_human_msg = ''
for line in sys.stdin:
    try:
        msg = json.loads(line.strip())
        text = ''
        if msg.get('type') == 'human':
            content = msg.get('message', {}).get('content', '')
            if isinstance(content, str):
                text = content.lower()
                last_human_msg = text
        elif msg.get('type') == 'assistant':
            content = msg.get('message', {}).get('content', [])
            if isinstance(content, list):
                text = ' '.join([c.get('text','') for c in content if c.get('type')=='text']).lower()
        for ind in error_indicators:
            if ind in text: errors += 1
        for ind in success_indicators:
            if ind in text: successes += 1
    except: pass
# Weight last message heavily
for ind in success_indicators:
    if ind in last_human_msg: successes += 3
for ind in error_indicators:
    if ind in last_human_msg: errors += 3
if successes > errors + 2:
    print('success')
elif errors > successes + 2:
    print('partial')
else:
    print('success')  # Default to success
" 2>/dev/null)

  # Record the outcome
  if [ -n "$OUTCOME" ]; then
    python3 "$OUTCOME_TRACKER" --record \
      --approach "session work on $PROJECT_ID" \
      --outcome "$OUTCOME" \
      --domain "session" \
      --context "Exit: $EXIT_REASON" \
      2>/dev/null &
  fi
fi

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
# FIXED: Use private temp directory instead of world-writable /tmp
TOOL_BUFFER_DIR="$MEMORY_ROOT/.tmp/claude-session-$SESSION_ID"
if [ -d "$TOOL_BUFFER_DIR" ]; then
  rm -rf "$TOOL_BUFFER_DIR" 2>/dev/null
fi

# === WEEKLY TRANSCRIPT COMPACTION ===
# Compress old transcripts to digests (saves ~99% space while preserving context)

COMPACTOR="$MEMORY_ROOT/memory/transcript_compactor.py"
LAST_COMPACT_FILE="$MEMORY_ROOT/.last_compaction"
COMPACT_LOCK_FILE="$MEMORY_ROOT/.compaction.lock"
COMPACT_INTERVAL_DAYS=7

should_compact() {
  if [ ! -f "$LAST_COMPACT_FILE" ]; then
    return 0  # Never compacted
  fi

  last_compact=$(cat "$LAST_COMPACT_FILE" 2>/dev/null || echo "0")
  # Validate last_compact is numeric
  if ! [ "$last_compact" -eq "$last_compact" ] 2>/dev/null; then
    last_compact=0
  fi

  now=$(date +%s)
  interval=$((COMPACT_INTERVAL_DAYS * 86400))

  if [ $((now - last_compact)) -gt $interval ]; then
    return 0  # Time to compact
  fi

  return 1  # Not yet
}

# FIXED: Use mkdir-based lock (atomic on all filesystems)
# More reliable than set -o noclobber on macOS
COMPACT_LOCK_DIR="${COMPACT_LOCK_FILE}.d"

acquire_compact_lock() {
  # Try to create lock directory atomically
  if mkdir "$COMPACT_LOCK_DIR" 2>/dev/null; then
    # Got the lock - write PID for debugging
    echo $$ > "$COMPACT_LOCK_DIR/pid"
    trap 'rm -rf "$COMPACT_LOCK_DIR"' EXIT
    return 0
  fi

  # Check if lock is stale (older than 1 hour)
  if [ -d "$COMPACT_LOCK_DIR" ]; then
    # Use Python for reliable cross-platform age calculation
    lock_age=$(python3 -c "
import os, time
try:
    mtime = os.path.getmtime('$COMPACT_LOCK_DIR')
    print(int(time.time() - mtime))
except:
    print(0)
" 2>/dev/null)

    if [ "$lock_age" -gt 3600 ]; then
      # Stale lock - try to remove and acquire
      rm -rf "$COMPACT_LOCK_DIR"
      if mkdir "$COMPACT_LOCK_DIR" 2>/dev/null; then
        echo $$ > "$COMPACT_LOCK_DIR/pid"
        trap 'rm -rf "$COMPACT_LOCK_DIR"' EXIT
        return 0
      fi
    fi
  fi

  return 1  # Lock held by another process
}

if [ -f "$COMPACTOR" ] && should_compact && acquire_compact_lock; then
  echo "Running weekly transcript compaction..."
  # Update timestamp FIRST to prevent other sessions from starting compaction
  date +%s > "$LAST_COMPACT_FILE"

  nohup "$PYTHON" "$COMPACTOR" --compact-all --keep 10 \
    >> "$MEMORY_ROOT/logs/compaction.log" 2>&1 &

  # Also run log rotation weekly
  LOG_ROTATOR="$MEMORY_ROOT/rotate-logs.sh"
  if [ -x "$LOG_ROTATOR" ]; then
    echo "Running weekly log rotation..."
    nohup "$LOG_ROTATOR" >> "$MEMORY_ROOT/logs/rotation.log" 2>&1 &
  fi

  # Lock will be released by trap on exit
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

# === REASONING BANK - Consolidate Learning ===
REASONING_BANK="$MEMORY_ROOT/learning/reasoning_bank.py"

if [ -f "$REASONING_BANK" ]; then
  nohup "$PYTHON" -c "
import sys
sys.path.insert(0, '$MEMORY_ROOT/learning')
from reasoning_bank import consolidate_learning
consolidate_learning(force=False)
" >> "$MEMORY_ROOT/logs/reasoning.log" 2>&1 &
fi

# === ROADMAP PROGRESS TRACKING ===
# Detect completed tasks from session and update roadmap
ROADMAP_TRACKER="$MEMORY_ROOT/memory/roadmap_tracker.py"
ROADMAP_FILE="$MEMORY_ROOT/projects/$PROJECT_ID/roadmap.json"

if [ -f "$ROADMAP_TRACKER" ] && [ -f "$ROADMAP_FILE" ] && [ -f "$TRANSCRIPT_PATH" ]; then
  nohup "$PYTHON" "$ROADMAP_TRACKER" \
    --transcript "$TRANSCRIPT_PATH" \
    --project "$PROJECT_ID" \
    --roadmap "$ROADMAP_FILE" \
    >> "$MEMORY_ROOT/logs/roadmap.log" 2>&1 &
fi

exit 0
