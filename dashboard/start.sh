#!/bin/bash
# Start Claude Memory Dashboard

cd "$(dirname "$0")"

echo "Starting Claude Memory Dashboard..."
echo ""

# Check if port is in use
if lsof -i :3333 > /dev/null 2>&1; then
    echo "Dashboard already running at http://localhost:3333"
    open http://localhost:3333
    exit 0
fi

# Start server
node server.js &
SERVER_PID=$!

sleep 1

# Open browser
open http://localhost:3333

echo "Dashboard running at http://localhost:3333"
echo "Press Ctrl+C to stop"

# Wait for Ctrl+C
trap "kill $SERVER_PID 2>/dev/null; exit 0" INT
wait $SERVER_PID
