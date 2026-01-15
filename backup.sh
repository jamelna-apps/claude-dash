#!/bin/bash
# Claude-Dash Backup Script
# Creates a timestamped backup of critical data

MEMORY_ROOT="$HOME/.claude-dash"
BACKUP_DIR="$MEMORY_ROOT/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="$BACKUP_DIR/claude-dash-$TIMESTAMP.tar.gz"

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

echo "Creating backup: $BACKUP_FILE"

# Critical data to backup
CRITICAL_FILES=(
    "config.json"
    "memory.db"
    "global/"
    "projects/"
    "sessions/observations.json"
    "sessions/digests/"
    "sessions/index.json"
    "sessions/summaries/"
    "learning/"
)

# Build file list
FILE_LIST=""
for file in "${CRITICAL_FILES[@]}"; do
    if [ -e "$MEMORY_ROOT/$file" ]; then
        FILE_LIST="$FILE_LIST $file"
    fi
done

# Create compressed backup
cd "$MEMORY_ROOT"
tar -czf "$BACKUP_FILE" $FILE_LIST 2>/dev/null

if [ $? -eq 0 ]; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "Backup created: $BACKUP_FILE ($SIZE)"

    # Keep only last 5 backups
    cd "$BACKUP_DIR"
    ls -t claude-dash-*.tar.gz 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null

    # Show backup inventory
    echo ""
    echo "Available backups:"
    ls -lh "$BACKUP_DIR"/claude-dash-*.tar.gz 2>/dev/null
else
    echo "Backup failed!"
    exit 1
fi
