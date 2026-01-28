#!/bin/bash

# Git Hook Installer - Installs roadmap sync hook in project repositories
#
# Usage:
#   ./install-git-hook.sh                    # Install in current directory
#   ./install-git-hook.sh /path/to/project   # Install in specified project
#   ./install-git-hook.sh --all              # Install in all registered projects

MEMORY_ROOT="$HOME/.claude-dash"
HOOK_TEMPLATE="$MEMORY_ROOT/hooks/git-post-commit-template.sh"
CONFIG_FILE="$MEMORY_ROOT/config.json"

install_hook() {
  local project_path="$1"
  local hooks_dir="$project_path/.git/hooks"
  local hook_file="$hooks_dir/post-commit"

  # Check if it's a git repo
  if [ ! -d "$project_path/.git" ]; then
    echo "  Skipping: Not a git repository"
    return 1
  fi

  # Create hooks dir if needed
  mkdir -p "$hooks_dir"

  # Check for existing hook
  if [ -f "$hook_file" ]; then
    # Check if it's our hook
    if grep -q "git_roadmap_sync" "$hook_file" 2>/dev/null; then
      echo "  Already installed"
      return 0
    else
      # Backup existing hook
      cp "$hook_file" "$hook_file.backup.$(date +%s)"
      echo "  Backed up existing hook"
    fi
  fi

  # Install hook
  cp "$HOOK_TEMPLATE" "$hook_file"
  chmod +x "$hook_file"
  echo "  Installed successfully"
  return 0
}

# Check template exists
if [ ! -f "$HOOK_TEMPLATE" ]; then
  echo "Error: Hook template not found at $HOOK_TEMPLATE"
  exit 1
fi

# Handle --all flag
if [ "$1" = "--all" ]; then
  echo "Installing git hooks in all registered projects..."

  if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file not found"
    exit 1
  fi

  # Get all project paths
  python3 -c "
import json
with open('$CONFIG_FILE') as f:
    config = json.load(f)
for p in config.get('projects', []):
    path = p.get('path', '')
    if path:
        print(path)
" | while read -r project_path; do
    if [ -n "$project_path" ]; then
      echo "Project: $project_path"
      install_hook "$project_path"
    fi
  done

  echo "Done!"
  exit 0
fi

# Single project installation
PROJECT_PATH="${1:-$(pwd)}"

# Resolve to absolute path
PROJECT_PATH=$(cd "$PROJECT_PATH" 2>/dev/null && pwd)
if [ -z "$PROJECT_PATH" ]; then
  echo "Error: Invalid project path"
  exit 1
fi

echo "Installing git hook in: $PROJECT_PATH"
install_hook "$PROJECT_PATH"
