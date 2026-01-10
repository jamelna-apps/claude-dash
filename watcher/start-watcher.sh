#!/bin/bash

WATCHER_DIR="$HOME/.claude-dash/watcher"
PID_FILE="$WATCHER_DIR/watcher.pid"
LOG_FILE="$WATCHER_DIR/watcher.log"

start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Watcher is already running (PID: $PID)"
            return 1
        fi
    fi

    echo "Starting Claude-Dash Watcher..."
    cd "$WATCHER_DIR"

    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo "Installing dependencies..."
        npm install
    fi

    # Start in background
    nohup node watcher.js > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Watcher started (PID: $(cat $PID_FILE))"
    echo "Log file: $LOG_FILE"
}

stop() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Stopping watcher (PID: $PID)..."
            kill "$PID"
            rm -f "$PID_FILE"
            echo "Watcher stopped."
        else
            echo "Watcher is not running."
            rm -f "$PID_FILE"
        fi
    else
        echo "Watcher is not running."
    fi
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "Watcher is running (PID: $PID)"
            echo "Recent log:"
            tail -10 "$LOG_FILE"
        else
            echo "Watcher is not running (stale PID file)"
            rm -f "$PID_FILE"
        fi
    else
        echo "Watcher is not running."
    fi
}

logs() {
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        echo "No log file found."
    fi
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
