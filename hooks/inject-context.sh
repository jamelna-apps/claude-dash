#!/bin/bash

# Claude Memory - Prompt Submit Hook
# Injects relevant memory context before processing prompts
# Includes: Session continuity, pattern detection, semantic triggers, preferences

MEMORY_ROOT="$HOME/.claude-dash"
DETECTOR="$MEMORY_ROOT/patterns/detector.py"
SESSION_CONTEXT="$MEMORY_ROOT/memory/session_context.py"
SEMANTIC_TRIGGER="$MEMORY_ROOT/memory/semantic_triggers.py"
HEALTH_CHECK="$MEMORY_ROOT/memory/health_check.py"

# Learning systems
GIT_AWARENESS="$MEMORY_ROOT/learning/git_awareness.py"
CORRECTION_TRACKER="$MEMORY_ROOT/learning/correction_tracker.py"
PREFERENCE_LEARNER="$MEMORY_ROOT/learning/preference_learner.py"
CONFIDENCE_CAL="$MEMORY_ROOT/learning/confidence_calibration.py"

# Read hook input from stdin
input=$(cat)

# Track if this is the first message of the session
# Use MEMORY_ROOT instead of /tmp for persistence across system reboots
SESSION_MARKERS_DIR="$MEMORY_ROOT/.session-markers"
mkdir -p "$SESSION_MARKERS_DIR" 2>/dev/null
FIRST_MESSAGE_MARKER="$SESSION_MARKERS_DIR/claude-session-$$-$(date +%Y%m%d)"

# Clean up old markers (older than 1 day)
find "$SESSION_MARKERS_DIR" -name "claude-session-*" -mtime +1 -delete 2>/dev/null

# === HEALTH CHECK (first message only) ===
if [ ! -f "$FIRST_MESSAGE_MARKER" ] && [ -f "$HEALTH_CHECK" ]; then
  HEALTH_RESULT=$(python3 "$HEALTH_CHECK" --fix --quiet 2>/dev/null)
  if [ -n "$HEALTH_RESULT" ]; then
    echo "<health-check>"
    echo "$HEALTH_RESULT"
    echo "</health-check>"
  fi
fi

# Extract prompt text
prompt=$(echo "$input" | grep -o '"prompt"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/"prompt"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/' | head -1)

# Detect current project
PROJECT_ROOT="$PWD"
MEMORY_ROOT="$HOME/.claude-dash"
CONFIG_FILE="$MEMORY_ROOT/config.json"

get_project_id() {
  if [ -f "$CONFIG_FILE" ]; then
    project_id=$(cat "$CONFIG_FILE" | grep -B2 "\"path\": \"$PROJECT_ROOT\"" | grep '"id"' | sed 's/.*"id": "\([^"]*\)".*/\1/' | head -1)
    echo "$project_id"
  fi
}

PROJECT_ID=$(get_project_id)
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

  # Session continuity
  if [ -f "$SESSION_CONTEXT" ]; then
    SESSION_CTX=$(python3 "$SESSION_CONTEXT" --project "$PROJECT_ID" 2>/dev/null)
    if [ -n "$SESSION_CTX" ]; then
      echo "<session-continuity>"
      echo "$SESSION_CTX"
      echo "</session-continuity>"
    fi
  fi

  # === GIT AWARENESS (first message only) ===
  # Show what changed since last session
  if [ -f "$GIT_AWARENESS" ] && [ -d "$PROJECT_ROOT/.git" ]; then
    GIT_CTX=$(python3 "$GIT_AWARENESS" "$PROJECT_ROOT" --project "$PROJECT_ID" 2>/dev/null)
    if [ -n "$GIT_CTX" ]; then
      echo "<git-changes>"
      echo "$GIT_CTX"
      echo "</git-changes>"
    fi
  fi

  # === LEARNED PREFERENCES (first message only) ===
  if [ -f "$PREFERENCE_LEARNER" ]; then
    PREFS=$(python3 "$PREFERENCE_LEARNER" --get-preferences 2>/dev/null)
    if [ -n "$PREFS" ] && [ "$PREFS" != "No high-confidence preferences yet" ]; then
      echo "<learned-preferences>"
      echo "$PREFS"
      echo "</learned-preferences>"
    fi
  fi

  # === CONFIDENCE CALIBRATION (first message only) ===
  if [ -f "$CONFIDENCE_CAL" ]; then
    CAL=$(python3 "$CONFIDENCE_CAL" --weak-areas 2>/dev/null)
    if [ -n "$CAL" ] && [[ "$CAL" != "No weak areas"* ]]; then
      echo "<confidence-calibration>"
      echo "$CAL"
      echo "</confidence-calibration>"
    fi
  fi
fi

# === CORRECTION DETECTION ===
# Check if user is correcting Claude, and find relevant past corrections

if [ -f "$CORRECTION_TRACKER" ] && [ -n "$prompt" ]; then
  # Single Python call to detect, record, and find (more efficient)
  CORRECTION_RESULT=$(python3 -c "
import sys
sys.path.insert(0, '$MEMORY_ROOT/learning')
from correction_tracker import detect_correction, record_correction, find_relevant_corrections, format_corrections_for_injection

msg = '''$prompt'''
result = detect_correction(msg)
if result.get('is_correction'):
    record_correction(msg, project_id='$PROJECT_ID')
    past = find_relevant_corrections(msg, limit=3)
    if past:
        print(format_corrections_for_injection(past))
" 2>/dev/null)

  if [ -n "$CORRECTION_RESULT" ]; then
    echo "<past-corrections>"
    echo "$CORRECTION_RESULT"
    echo "</past-corrections>"
  fi
fi

# === SEMANTIC TRIGGERS ===
# Detect topic keywords and auto-fetch relevant memory

if [ -f "$SEMANTIC_TRIGGER" ] && [ -n "$prompt" ]; then
  SEMANTIC_CTX=$(python3 "$SEMANTIC_TRIGGER" "$prompt" --project "$PROJECT_ID" 2>/dev/null)
  if [ -n "$SEMANTIC_CTX" ]; then
    echo "<semantic-memory>"
    echo "$SEMANTIC_CTX"
    echo "</semantic-memory>"
  fi
fi

# === PATTERN DETECTION ===
# Detect conversation mode and inject relevant context guidance

if [ -f "$DETECTOR" ] && [ -n "$prompt" ] && [ ${#prompt} -gt 10 ]; then
  # Skip slash commands
  if [[ "$prompt" != /* ]]; then
    # Single Python call to detect and format (more efficient)
    PATTERN_OUTPUT=$(python3 -c "
import sys
sys.path.insert(0, '$MEMORY_ROOT/patterns')
from detector import detect_mode, get_mode_context, format_context_text, load_patterns

msg = '''$prompt'''
result = detect_mode(msg, use_ollama=False)
mode = result.get('primary_mode')
confidence = result.get('confidence', 0)

if mode and confidence >= 0.3:
    patterns = load_patterns()
    context = get_mode_context(mode, patterns)
    print(f'MODE:{mode}')
    print(f'CONF:{confidence}')
    print(format_context_text(context))
" 2>/dev/null)

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
