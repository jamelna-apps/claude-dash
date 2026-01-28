#!/bin/bash

# Backup original files
cp ~/.claude-dash/dashboard/index.html ~/.claude-dash/dashboard/index.html.backup
cp ~/.claude-dash/dashboard/app.js ~/.claude-dash/dashboard/app.js.backup
cp ~/.claude-dash/dashboard/styles.css ~/.claude-dash/dashboard/styles.css.backup

echo "✅ Backed up original files"
echo "📝 Token metrics enhancement has been documented in /tmp/token-metrics-update.txt"
echo ""
echo "To add the enhancements manually:"
echo "1. Open ~/.claude-dash/dashboard/index.html"
echo "2. Find line ~164 (after Ollama section </div>)"
echo "3. Insert the Token Savings Metrics section from /tmp/reports-enhancement.html"
echo "4. Add the JavaScript function from /tmp/token-metrics-update.txt to app.js"
echo "5. Restart dashboard: ~/.claude-dash/dashboard/start.sh restart"
echo ""
echo "The metrics will show:"
echo "  - Memory routing stats"
echo "  - Tokens used vs saved"
echo "  - Daily trends table"
echo "  - Monthly projections"
echo "  - Cost savings estimates"
