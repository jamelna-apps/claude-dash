#!/bin/bash
#
# Claude-Dash Event Handler Hook
#
# Called by webhook-listener.py when events are received.
# Can be customized to add additional actions per event type.
#
# Usage: on-event.sh <event_type> <project_id> [additional_args...]
#
# Event types:
#   git.push      - Git push received (full reindex)
#   file.change   - Files changed (incremental update)
#   build.complete - Build completed
#   manual.reindex - Manual reindex triggered
#

set -e

MEMORY_ROOT="$HOME/.claude-dash"
LOG_FILE="$MEMORY_ROOT/logs/on-event.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

EVENT_TYPE="$1"
PROJECT_ID="$2"
shift 2

log "Event received: $EVENT_TYPE for project $PROJECT_ID"

case "$EVENT_TYPE" in
    git.push)
        log "Handling git.push for $PROJECT_ID"
        # Could add: notify dashboard, update git stats, etc.
        ;;

    file.change)
        log "Handling file.change for $PROJECT_ID"
        # Could add: update specific indexes, check for schema changes, etc.
        ;;

    build.complete)
        log "Handling build.complete for $PROJECT_ID"
        # Could add: update function index, check for new exports, etc.
        ;;

    manual.reindex)
        log "Handling manual.reindex for $PROJECT_ID"
        # Full reindex requested
        ;;

    *)
        log "Unknown event type: $EVENT_TYPE"
        ;;
esac

log "Event handling complete: $EVENT_TYPE for $PROJECT_ID"
exit 0
