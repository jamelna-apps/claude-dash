#!/bin/bash
# Start Claude Memory Dashboard
# Handles port conflicts gracefully

cd "$(dirname "$0")"

# Find node in common locations
if command -v node &> /dev/null; then
    NODE_CMD="node"
elif [ -x "/opt/homebrew/bin/node" ]; then
    NODE_CMD="/opt/homebrew/bin/node"
elif [ -x "/usr/local/bin/node" ]; then
    NODE_CMD="/usr/local/bin/node"
else
    echo "ERROR: Node.js not found" >&2
    exit 1
fi

PREFERRED_PORT=3333
FALLBACK_PORT=3334
PID_FILE="$HOME/.claude-dash/dashboard/dashboard.pid"

# Function to check if a process is our dashboard
is_our_dashboard() {
    local port=$1
    local pid=$(lsof -ti :$port 2>/dev/null | head -1)
    if [ -n "$pid" ]; then
        # Check if it's a node process running our server
        if ps -p "$pid" -o command= 2>/dev/null | grep -q "server.js"; then
            return 0
        fi
    fi
    return 1
}

# Function to start dashboard on a port
start_dashboard() {
    local port=$1
    export PORT=$port
    $NODE_CMD server.js &
    local pid=$!
    echo $pid > "$PID_FILE"
    sleep 1

    if kill -0 $pid 2>/dev/null; then
        echo "Dashboard running at http://localhost:$port (PID: $pid)"
        return 0
    else
        echo "Failed to start dashboard on port $port"
        return 1
    fi
}

# Clean up stale PID file
cleanup_stale_pid() {
    if [ -f "$PID_FILE" ]; then
        local old_pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$old_pid" ] && ! kill -0 "$old_pid" 2>/dev/null; then
            rm -f "$PID_FILE"
        fi
    fi
}

echo "Starting Claude Memory Dashboard..."

# Clean up stale PID
cleanup_stale_pid

# Check if already running via PID file
if [ -f "$PID_FILE" ]; then
    existing_pid=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$existing_pid" ] && kill -0 "$existing_pid" 2>/dev/null; then
        echo "Dashboard already running (PID: $existing_pid)"
        exit 0
    fi
fi

# Try preferred port
if ! lsof -i :$PREFERRED_PORT > /dev/null 2>&1; then
    if start_dashboard $PREFERRED_PORT; then
        trap "kill $(cat $PID_FILE 2>/dev/null) 2>/dev/null; rm -f $PID_FILE; exit 0" INT TERM
        wait $(cat "$PID_FILE")
        exit 0
    fi
fi

# Check if preferred port is our dashboard
if is_our_dashboard $PREFERRED_PORT; then
    echo "Dashboard already running at http://localhost:$PREFERRED_PORT"
    exit 0
fi

# Try fallback port
echo "Port $PREFERRED_PORT in use, trying $FALLBACK_PORT..."
if ! lsof -i :$FALLBACK_PORT > /dev/null 2>&1; then
    if start_dashboard $FALLBACK_PORT; then
        trap "kill $(cat $PID_FILE 2>/dev/null) 2>/dev/null; rm -f $PID_FILE; exit 0" INT TERM
        wait $(cat "$PID_FILE")
        exit 0
    fi
fi

# Both ports in use
echo "ERROR: Both ports $PREFERRED_PORT and $FALLBACK_PORT are in use"
echo "Kill the processes using these ports and try again:"
echo "  lsof -i :$PREFERRED_PORT"
echo "  lsof -i :$FALLBACK_PORT"
exit 1
