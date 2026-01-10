#!/bin/bash
# Local Embeddings Server Launcher
#
# Usage:
#   ./start.sh              # Start with default BGE-M3 model
#   ./start.sh --reload     # Start with auto-reload for development
#
# Environment variables:
#   EMBEDDING_MODEL  - Model to use (default: BAAI/bge-m3)
#   PORT            - Port to run on (default: 8100)

set -e

cd "$(dirname "$0")"

# Activate MLX environment
source ~/.claude-memory/mlx-env/bin/activate

# Set defaults
export EMBEDDING_MODEL="${EMBEDDING_MODEL:-BAAI/bge-m3}"
export PORT="${PORT:-8100}"

echo "=============================================="
echo "  Local Embeddings Server"
echo "=============================================="
echo "  Model:  $EMBEDDING_MODEL"
echo "  Port:   $PORT"
echo "  URL:    http://localhost:$PORT"
echo "=============================================="

# Check if --reload flag passed
if [[ "$1" == "--reload" ]]; then
    echo "Starting with auto-reload..."
    uvicorn server:app --host 0.0.0.0 --port "$PORT" --reload
else
    echo "Starting server..."
    uvicorn server:app --host 0.0.0.0 --port "$PORT"
fi
