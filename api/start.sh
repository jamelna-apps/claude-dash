#!/bin/bash
#
# Claude-Dash API Server Startup Script
#
# Usage:
#   ./start.sh              - Start server on default port (5100)
#   ./start.sh --port 8080  - Start on custom port
#   ./start.sh status       - Check if server is running
#   ./start.sh stop         - Stop the server
#   ./start.sh logs         - Tail the logs
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$SCRIPT_DIR"
LOG_DIR="$HOME/.claude-dash/logs"
PID_FILE="$LOG_DIR/api-server.pid"
LOG_FILE="$LOG_DIR/api-server.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Use the mlx-env Python if available
if [ -f "$HOME/.claude-dash/mlx-env/bin/python3" ]; then
    PYTHON="$HOME/.claude-dash/mlx-env/bin/python3"
else
    PYTHON="python3"
fi

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Claude-Dash API Server is running (PID: $PID)"
            return 0
        else
            echo "Claude-Dash API Server is not running (stale PID file)"
            rm -f "$PID_FILE"
            return 1
        fi
    else
        echo "Claude-Dash API Server is not running"
        return 1
    fi
}

stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Stopping Claude-Dash API Server (PID: $PID)..."
            kill "$PID"
            sleep 2
            if ps -p "$PID" > /dev/null 2>&1; then
                echo "Force killing..."
                kill -9 "$PID"
            fi
            rm -f "$PID_FILE"
            echo "Stopped."
        else
            echo "Server not running (stale PID file)"
            rm -f "$PID_FILE"
        fi
    else
        echo "Server not running (no PID file)"
    fi
}

logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "No log file found at $LOG_FILE"
    fi
}

start() {
    # Check if already running
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Server already running (PID: $PID)"
            exit 1
        fi
        rm -f "$PID_FILE"
    fi

    # Parse arguments
    PORT=5100
    HOST="0.0.0.0"
    while [[ $# -gt 0 ]]; do
        case $1 in
            --port)
                PORT="$2"
                shift 2
                ;;
            --host)
                HOST="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    echo "Starting Claude-Dash API Server..."
    echo "  Python: $PYTHON"
    echo "  Host: $HOST"
    echo "  Port: $PORT"
    echo "  Log: $LOG_FILE"

    # Start server in background
    nohup "$PYTHON" "$API_DIR/server.py" --host "$HOST" --port "$PORT" >> "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"

    sleep 2

    # Check if started successfully
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Server started successfully (PID: $PID)"
        echo ""
        echo "Access via:"
        echo "  Local:     http://localhost:$PORT"
        echo "  Tailscale: http://$(hostname):$PORT"
        echo ""
        echo "For Enchanted, add a new server with URL:"
        echo "  http://$(hostname):$PORT/v1"
    else
        echo "Failed to start server. Check logs:"
        tail -20 "$LOG_FILE"
        exit 1
    fi
}

case "${1:-start}" in
    status)
        status
        ;;
    stop)
        stop
        ;;
    logs)
        logs
        ;;
    restart)
        stop
        sleep 1
        shift
        start "$@"
        ;;
    start|*)
        if [ "$1" = "start" ]; then
            shift
        fi
        start "$@"
        ;;
esac
