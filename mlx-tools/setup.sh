#!/bin/bash
# MLX Tools Setup Script

echo "=== MLX Tools Setup ==="

# Add mlx command to PATH
if ! grep -q "claude-dash/mlx-tools" ~/.zshrc 2>/dev/null; then
    echo 'export PATH="$HOME/.claude-dash/mlx-tools:$PATH"' >> ~/.zshrc
    echo "Added mlx to PATH in ~/.zshrc"
else
    echo "mlx already in PATH"
fi

# Build embeddings for all projects
echo ""
echo "Building semantic search embeddings..."
source ~/.claude-dash/mlx-env/bin/activate

for project in gyst smartiegoals jamelna gyst-seller-portal spread-your-ashes; do
    echo "  Building embeddings for $project..."
    python ~/.claude-dash/mlx-tools/semantic_search.py "$project" build 2>/dev/null || echo "    Skipped (no summaries)"
done

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Usage:"
echo "  mlx search gyst \"login authentication\""
echo "  mlx classify \"where is user data stored?\""
echo "  mlx pending"
echo ""
echo "Restart your terminal or run: source ~/.zshrc"
