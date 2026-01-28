#!/bin/bash
# Log Rotation for Claude-Dash
# Compresses logs >10MB, deletes compressed logs >7 days old

LOGS_DIR="$HOME/.claude-dash/logs"
MAX_SIZE_MB=10
MAX_AGE_DAYS=7

# Create logs dir if it doesn't exist
mkdir -p "$LOGS_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting log rotation..."

# Compress logs larger than MAX_SIZE_MB
find "$LOGS_DIR" -name "*.log" -type f | while read logfile; do
    size_mb=$(du -m "$logfile" 2>/dev/null | cut -f1)
    if [ "$size_mb" -gt "$MAX_SIZE_MB" ]; then
        echo "  Compressing: $(basename "$logfile") (${size_mb}MB)"
        # Rotate with timestamp
        timestamp=$(date +%Y%m%d-%H%M%S)
        mv "$logfile" "${logfile}.${timestamp}"
        gzip "${logfile}.${timestamp}"
        # Create fresh empty log
        touch "$logfile"
    fi
done

# Delete old compressed logs
deleted_count=0
find "$LOGS_DIR" -name "*.log.*.gz" -mtime +$MAX_AGE_DAYS -type f | while read oldlog; do
    echo "  Deleting old: $(basename "$oldlog")"
    rm -f "$oldlog"
    ((deleted_count++))
done

# Also clean up very old uncompressed rotated logs
find "$LOGS_DIR" -name "*.log.*" ! -name "*.gz" -mtime +1 -type f | while read stale; do
    echo "  Compressing stale: $(basename "$stale")"
    gzip "$stale"
done

# Report final state
total_size=$(du -sh "$LOGS_DIR" 2>/dev/null | cut -f1)
log_count=$(find "$LOGS_DIR" -name "*.log" -type f | wc -l)
archive_count=$(find "$LOGS_DIR" -name "*.gz" -type f | wc -l)

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Log rotation complete"
echo "  Total size: $total_size"
echo "  Active logs: $log_count"
echo "  Archives: $archive_count"
