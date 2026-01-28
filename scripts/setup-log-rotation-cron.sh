#!/bin/bash
# Setup daily log rotation cron job

SCRIPT="$HOME/.claude-dash/scripts/log-rotation.sh"
CRON_ENTRY="0 3 * * * $SCRIPT >> $HOME/.claude-dash/logs/rotation.log 2>&1"

# Check if cron entry already exists
if crontab -l 2>/dev/null | grep -q "log-rotation.sh"; then
    echo "Log rotation cron job already exists"
else
    # Add to crontab
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    echo "Added daily log rotation cron job (runs at 3 AM)"
fi

# Verify
echo "Current crontab entries for claude-dash:"
crontab -l 2>/dev/null | grep claude-dash || echo "  (none)"
