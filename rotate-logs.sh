#!/bin/bash
# Claude-Dash Log Rotation
# Rotates logs over 5MB, keeps 3 backups

MEMORY_ROOT="$HOME/.claude-dash"
MAX_SIZE=5242880  # 5MB in bytes
KEEP_BACKUPS=3

rotate_log() {
    local log_file="$1"

    if [ ! -f "$log_file" ]; then
        return
    fi

    local size=$(stat -f%z "$log_file" 2>/dev/null || stat -c%s "$log_file" 2>/dev/null)

    if [ "$size" -gt "$MAX_SIZE" ]; then
        echo "Rotating: $log_file ($size bytes)"

        # Remove oldest backup
        rm -f "${log_file}.${KEEP_BACKUPS}"

        # Shift existing backups
        for i in $(seq $((KEEP_BACKUPS - 1)) -1 1); do
            if [ -f "${log_file}.$i" ]; then
                mv "${log_file}.$i" "${log_file}.$((i + 1))"
            fi
        done

        # Rotate current log
        mv "$log_file" "${log_file}.1"

        # Create new empty log
        touch "$log_file"

        echo "  → Created ${log_file}.1"
    fi
}

echo "Claude-Dash Log Rotation"
echo "========================"
echo ""

# Rotate main logs
rotate_log "$MEMORY_ROOT/watcher/watcher.log"
rotate_log "$MEMORY_ROOT/watcher/watcher.error.log"
rotate_log "$MEMORY_ROOT/logs/dashboard.log"
rotate_log "$MEMORY_ROOT/logs/dashboard-error.log"
rotate_log "$MEMORY_ROOT/logs/db-sync.log"
rotate_log "$MEMORY_ROOT/logs/pattern-detection.log"

# Clean up old extraction logs (keep last 10)
if [ -d "$MEMORY_ROOT/logs" ]; then
    extraction_logs=$(ls -t "$MEMORY_ROOT/logs"/extraction-*.log 2>/dev/null | tail -n +11)
    if [ -n "$extraction_logs" ]; then
        echo "Cleaning old extraction logs..."
        echo "$extraction_logs" | xargs rm -f
        echo "  → Removed $(echo "$extraction_logs" | wc -l | tr -d ' ') old extraction logs"
    fi
fi

# Clean up old session markers
if [ -d "$MEMORY_ROOT/.session-markers" ]; then
    old_markers=$(find "$MEMORY_ROOT/.session-markers" -name "claude-session-*" -mtime +7 2>/dev/null)
    if [ -n "$old_markers" ]; then
        echo "Cleaning old session markers..."
        echo "$old_markers" | xargs rm -f
        echo "  → Removed $(echo "$old_markers" | wc -l | tr -d ' ') old markers"
    fi
fi

echo ""
echo "Log rotation complete."
