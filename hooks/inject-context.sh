#!/bin/bash

# Claude Memory - Prompt Submit Hook
# Injects relevant memory context before processing prompts
# Includes: Session continuity, pattern detection, semantic triggers, preferences

MEMORY_ROOT="$HOME/.claude-dash"
DETECTOR="$MEMORY_ROOT/patterns/detector.py"
SESSION_CONTEXT="$MEMORY_ROOT/memory/session_context.py"
SEMANTIC_TRIGGER="$MEMORY_ROOT/memory/semantic_triggers.py"
SESSION_HEALTH="$MEMORY_ROOT/memory/session_health.py"
IMPROVEMENTS_FILE="$MEMORY_ROOT/improvements.json"

# Learning systems
GIT_AWARENESS="$MEMORY_ROOT/learning/git_awareness.py"
CORRECTION_TRACKER="$MEMORY_ROOT/learning/correction_tracker.py"
PREFERENCE_LEARNER="$MEMORY_ROOT/learning/preference_learner.py"
CONFIDENCE_CAL="$MEMORY_ROOT/learning/confidence_calibration.py"

# Load JSON helper if available
JSON_HELPER="$MEMORY_ROOT/hooks/json-helper.sh"
if [ -f "$JSON_HELPER" ]; then
  source "$JSON_HELPER"
fi

# Timeout helper - runs command with timeout, returns output or empty on timeout
# Usage: result=$(timeout_run 5 python3 script.py args)
# Default timeout for subprocess calls (seconds)
SUBPROCESS_TIMEOUT=5

timeout_run() {
  local timeout_secs="$1"
  shift

  local tmpfile=$(mktemp)

  # Run command in background, write output to temp file
  ( "$@" > "$tmpfile" 2>/dev/null ) &
  local pid=$!

  # Watchdog to kill after timeout
  ( sleep "$timeout_secs" && kill $pid 2>/dev/null ) &
  local watchdog=$!

  # Wait for command to finish
  wait $pid 2>/dev/null

  # Clean up watchdog
  kill $watchdog 2>/dev/null
  wait $watchdog 2>/dev/null

  # Return output
  cat "$tmpfile" 2>/dev/null
  rm -f "$tmpfile" 2>/dev/null
}

# Read hook input from stdin
input=$(cat)

# Track if this is the first message of the session
# Use MEMORY_ROOT instead of /tmp for persistence across system reboots
SESSION_MARKERS_DIR="$MEMORY_ROOT/.session-markers"
mkdir -p "$SESSION_MARKERS_DIR" 2>/dev/null
FIRST_MESSAGE_MARKER="$SESSION_MARKERS_DIR/claude-session-$$-$(date +%Y%m%d)"

# Clean up old markers (older than 1 day)
find "$SESSION_MARKERS_DIR" -name "claude-session-*" -mtime +1 -delete 2>/dev/null

# === SESSION HEALTH CHECK (first message only) ===
# Checks: services status, database health, recent errors, stale indexes, pending improvements
if [ ! -f "$FIRST_MESSAGE_MARKER" ] && [ -f "$SESSION_HEALTH" ]; then
  HEALTH_RESULT=$(timeout_run $SUBPROCESS_TIMEOUT python3 "$SESSION_HEALTH")
  if [ -n "$HEALTH_RESULT" ]; then
    echo "<system-health>"
    echo "$HEALTH_RESULT"
    echo "</system-health>"
  fi
fi

# Extract prompt text using JSON helper if available, fallback to grep/sed
if type json_get &>/dev/null; then
  prompt=$(echo "$input" | json_get "prompt")
else
  # Fallback: fragile grep/sed parsing (kept for compatibility)
  prompt=$(echo "$input" | grep -o '"prompt"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"prompt"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/' | head -1)
fi

# Detect current project
PROJECT_ROOT="$PWD"
CONFIG_FILE="$MEMORY_ROOT/config.json"

# Use JSON helper for project ID if available
if type get_project_id &>/dev/null; then
  PROJECT_ID=$(get_project_id "$PROJECT_ROOT")
else
  # Fallback: grep/sed parsing
  if [ -f "$CONFIG_FILE" ]; then
    PROJECT_ID=$(cat "$CONFIG_FILE" | grep -B2 "\"path\": \"$PROJECT_ROOT\"" | grep '"id"' | sed 's/.*"id": "\([^"]*\)".*/\1/' | head -1)
  fi
fi
if [ -z "$PROJECT_ID" ]; then
  PROJECT_ID=$(basename "$PROJECT_ROOT" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
fi

PROJECT_MEMORY="$MEMORY_ROOT/projects/$PROJECT_ID"

# Keywords that trigger memory injection
needs_schema=false
needs_mappings=false
needs_functions=false
needs_graph=false

# Check prompt for context keywords (case insensitive)
prompt_lower=$(echo "$prompt" | tr '[:upper:]' '[:lower:]')

# Database/schema keywords
if echo "$prompt_lower" | grep -qE "database|firestore|collection|schema|field|document"; then
  needs_schema=true
fi

# Screen/navigation keywords
if echo "$prompt_lower" | grep -qE "screen|navigate|tab|stack|route|page"; then
  needs_mappings=true
  needs_graph=true
fi

# Function/code keywords
if echo "$prompt_lower" | grep -qE "function|method|implement|create|add|feature|component"; then
  needs_functions=true
fi

# Inject relevant context
context_added=false

if [ "$needs_schema" = true ] && [ -f "$PROJECT_MEMORY/schema.json" ]; then
  echo "<memory-context type=\"schema\">"
  cat "$PROJECT_MEMORY/schema.json"
  echo "</memory-context>"
  context_added=true
fi

if [ "$needs_mappings" = true ] && [ -f "$PROJECT_MEMORY/mappings.json" ]; then
  echo "<memory-context type=\"mappings\">"
  cat "$PROJECT_MEMORY/mappings.json"
  echo "</memory-context>"
  context_added=true
fi

if [ "$needs_graph" = true ] && [ -f "$PROJECT_MEMORY/graph.json" ]; then
  echo "<memory-context type=\"navigation\">"
  # Only include navigation section to keep it concise
  cat "$PROJECT_MEMORY/graph.json" | head -100
  echo "</memory-context>"
  context_added=true
fi

if [ "$needs_functions" = true ] && [ -f "$PROJECT_MEMORY/functions.json" ]; then
  echo "<memory-context type=\"functions\">"
  # Include function index for lookups
  cat "$PROJECT_MEMORY/functions.json" | head -200
  echo "</memory-context>"
  context_added=true
fi

# Always inject preferences if they exist (they're usually small)
if [ -f "$PROJECT_MEMORY/preferences.json" ]; then
  prefs_size=$(wc -c < "$PROJECT_MEMORY/preferences.json")
  if [ "$prefs_size" -lt 2000 ]; then
    echo "<memory-context type=\"preferences\">"
    cat "$PROJECT_MEMORY/preferences.json"
    echo "</memory-context>"
  fi
fi

# === SESSION CONTINUITY ===
# On first message, inject last session context for continuity

if [ ! -f "$FIRST_MESSAGE_MARKER" ]; then
  touch "$FIRST_MESSAGE_MARKER"

  # Session continuity (with timeout)
  if [ -f "$SESSION_CONTEXT" ]; then
    SESSION_CTX=$(timeout_run $SUBPROCESS_TIMEOUT python3 "$SESSION_CONTEXT" --project "$PROJECT_ID")
    if [ -n "$SESSION_CTX" ]; then
      echo "<session-continuity>"
      echo "$SESSION_CTX"
      echo "</session-continuity>"
    fi
  fi

  # === GIT AWARENESS (first message only, with timeout) ===
  # Show what changed since last session
  if [ -f "$GIT_AWARENESS" ] && [ -d "$PROJECT_ROOT/.git" ]; then
    GIT_CTX=$(timeout_run $SUBPROCESS_TIMEOUT python3 "$GIT_AWARENESS" "$PROJECT_ROOT" --project "$PROJECT_ID")
    if [ -n "$GIT_CTX" ]; then
      echo "<git-changes>"
      echo "$GIT_CTX"
      echo "</git-changes>"
    fi
  fi

  # === LEARNED PREFERENCES (first message only, with timeout) ===
  if [ -f "$PREFERENCE_LEARNER" ]; then
    PREFS=$(timeout_run $SUBPROCESS_TIMEOUT python3 "$PREFERENCE_LEARNER" --get-preferences)
    if [ -n "$PREFS" ] && [ "$PREFS" != "No high-confidence preferences yet" ]; then
      echo "<learned-preferences>"
      echo "$PREFS"
      echo "</learned-preferences>"
    fi
  fi

  # === CONFIDENCE CALIBRATION (first message only, with timeout) ===
  if [ -f "$CONFIDENCE_CAL" ]; then
    CAL=$(timeout_run $SUBPROCESS_TIMEOUT python3 "$CONFIDENCE_CAL" --weak-areas)
    if [ -n "$CAL" ] && [[ "$CAL" != "No weak areas"* ]]; then
      echo "<confidence-calibration>"
      echo "$CAL"
      echo "</confidence-calibration>"
    fi
  fi
fi

# === CORRECTION DETECTION (with timeout) ===
# Check if user is correcting Claude, and find relevant past corrections

if [ -f "$CORRECTION_TRACKER" ] && [ -n "$prompt" ]; then
  # Write inline script to temp file for timeout support
  CORRECTION_SCRIPT=$(mktemp)
  cat > "$CORRECTION_SCRIPT" << 'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from correction_tracker import detect_correction, record_correction, find_relevant_corrections, format_corrections_for_injection

msg = sys.argv[2]
project_id = sys.argv[3]
result = detect_correction(msg)
if result.get('is_correction'):
    record_correction(msg, project_id=project_id)
    past = find_relevant_corrections(msg, limit=3)
    if past:
        print(format_corrections_for_injection(past))
PYEOF

  CORRECTION_RESULT=$(timeout_run $SUBPROCESS_TIMEOUT python3 "$CORRECTION_SCRIPT" "$MEMORY_ROOT/learning" "$prompt" "$PROJECT_ID")
  rm -f "$CORRECTION_SCRIPT" 2>/dev/null

  if [ -n "$CORRECTION_RESULT" ]; then
    echo "<past-corrections>"
    echo "$CORRECTION_RESULT"
    echo "</past-corrections>"
  fi
fi

# === REASONING BANK (with timeout) ===
# Query past learning trajectories for applicable solutions
# Uses RETRIEVE→JUDGE cycle to find relevant past learnings

REASONING_BANK="$MEMORY_ROOT/learning/reasoning_bank.py"

if [ -f "$REASONING_BANK" ] && [ -n "$prompt" ] && [ ${#prompt} -gt 20 ]; then
  # Detect domain from prompt keywords
  DOMAIN=""
  if echo "$prompt_lower" | grep -qE "docker|container|compose"; then
    DOMAIN="docker"
  elif echo "$prompt_lower" | grep -qE "auth|login|token|session|firebase"; then
    DOMAIN="auth"
  elif echo "$prompt_lower" | grep -qE "react|component|hook|state|props"; then
    DOMAIN="react"
  elif echo "$prompt_lower" | grep -qE "database|query|sql|firestore|collection"; then
    DOMAIN="database"
  elif echo "$prompt_lower" | grep -qE "api|endpoint|fetch|request|response"; then
    DOMAIN="api"
  fi

  REASONING_SCRIPT=$(mktemp)
  cat > "$REASONING_SCRIPT" << 'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from reasoning_bank import query_for_context, format_for_injection

context = sys.argv[2]
domain = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None

result = query_for_context(context, domain)
if result.get('applicable'):
    formatted = format_for_injection(context, domain)
    if formatted:
        print(formatted)
PYEOF

  REASONING_RESULT=$(timeout_run $SUBPROCESS_TIMEOUT python3 "$REASONING_SCRIPT" "$MEMORY_ROOT/learning" "$prompt" "$DOMAIN")
  rm -f "$REASONING_SCRIPT" 2>/dev/null

  if [ -n "$REASONING_RESULT" ]; then
    echo "<reasoning-bank>"
    echo "$REASONING_RESULT"
    echo "</reasoning-bank>"
  fi
fi

# === SEMANTIC TRIGGERS (with timeout) ===
# Detect topic keywords and auto-fetch relevant memory

if [ -f "$SEMANTIC_TRIGGER" ] && [ -n "$prompt" ]; then
  SEMANTIC_CTX=$(timeout_run $SUBPROCESS_TIMEOUT python3 "$SEMANTIC_TRIGGER" "$prompt" --project "$PROJECT_ID")
  if [ -n "$SEMANTIC_CTX" ]; then
    echo "<semantic-memory>"
    echo "$SEMANTIC_CTX"
    echo "</semantic-memory>"
  fi
fi

# === PATTERN DETECTION (with timeout) ===
# Detect conversation mode and inject relevant context guidance

if [ -f "$DETECTOR" ] && [ -n "$prompt" ] && [ ${#prompt} -gt 10 ]; then
  # Skip slash commands
  if [[ "$prompt" != /* ]]; then
    # Write inline script to temp file for timeout support
    PATTERN_SCRIPT=$(mktemp)
    cat > "$PATTERN_SCRIPT" << 'PYEOF'
import sys
sys.path.insert(0, sys.argv[1])
from detector import detect_mode, get_mode_context, format_context_text, load_patterns

msg = sys.argv[2]
result = detect_mode(msg, use_ollama=False)
mode = result.get('primary_mode')
confidence = result.get('confidence', 0)

if mode and confidence >= 0.3:
    patterns = load_patterns()
    context = get_mode_context(mode, patterns)
    print(f'MODE:{mode}')
    print(f'CONF:{confidence}')
    print(format_context_text(context))
PYEOF

    PATTERN_OUTPUT=$(timeout_run $SUBPROCESS_TIMEOUT python3 "$PATTERN_SCRIPT" "$MEMORY_ROOT/patterns" "$prompt")
    rm -f "$PATTERN_SCRIPT" 2>/dev/null

    if [ -n "$PATTERN_OUTPUT" ]; then
      MODE=$(echo "$PATTERN_OUTPUT" | grep "^MODE:" | cut -d: -f2)
      CONFIDENCE=$(echo "$PATTERN_OUTPUT" | grep "^CONF:" | cut -d: -f2)
      CONTEXT_TEXT=$(echo "$PATTERN_OUTPUT" | grep -v "^MODE:\|^CONF:")

      if [ -n "$CONTEXT_TEXT" ]; then
        echo "<pattern-context mode=\"$MODE\" confidence=\"$CONFIDENCE\">"
        echo "$CONTEXT_TEXT"
        echo "</pattern-context>"

        # Log detection for learning
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Mode: $MODE (${CONFIDENCE}) - ${prompt:0:50}" >> "$MEMORY_ROOT/logs/pattern-detection.log" 2>/dev/null
      fi
    fi
  fi
fi

exit 0
