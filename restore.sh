#!/bin/bash
# Claude-Dash Restore Script
# Restores from a backup file

MEMORY_ROOT="$HOME/.claude-dash"
BACKUP_DIR="$MEMORY_ROOT/backups"

if [ -z "$1" ]; then
    echo "Usage: restore.sh <backup-file>"
    echo ""
    echo "Available backups:"
    ls -lh "$BACKUP_DIR"/claude-dash-*.tar.gz 2>/dev/null
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    # Try backup directory
    BACKUP_FILE="$BACKUP_DIR/$1"
    if [ ! -f "$BACKUP_FILE" ]; then
        echo "Backup file not found: $1"
        exit 1
    fi
fi

echo "Restoring from: $BACKUP_FILE"
echo ""

# Confirm
read -p "This will overwrite current data. Continue? (y/N) " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "Aborted."
    exit 0
fi

# Create pre-restore backup
echo "Creating pre-restore backup..."
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
PRE_RESTORE="$BACKUP_DIR/pre-restore-$TIMESTAMP.tar.gz"
cd "$MEMORY_ROOT"
tar -czf "$PRE_RESTORE" config.json memory.db global/ projects/ sessions/ learning/ 2>/dev/null
echo "Pre-restore backup saved: $PRE_RESTORE"

# Restore
echo ""
echo "Restoring..."
tar -xzf "$BACKUP_FILE" -C "$MEMORY_ROOT"

if [ $? -eq 0 ]; then
    echo "Restore complete!"
    echo ""
    echo "Restored files:"
    tar -tzf "$BACKUP_FILE"
else
    echo "Restore failed!"
    echo "Pre-restore backup available at: $PRE_RESTORE"
    exit 1
fi
