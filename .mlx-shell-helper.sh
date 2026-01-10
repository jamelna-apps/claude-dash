#!/bin/bash
#
# MLX Shell Helper - Natural Language Interface
# Source this in your ~/.zshrc or ~/.bashrc:
#   source ~/.claude-dash/.mlx-shell-helper.sh
#
# NOTE: Edit the project mappings below to match your registered projects.
#
# Usage:
#   ask where is the login screen
#   ask how does authentication work
#   ask similar to src/screens/LoginScreen.js
#

ask() {
  # Auto-detect project from current directory
  local project=""
  local cwd=$(pwd)

  # Map directory to project ID
  if [[ "$cwd" == *"WardrobeApp"* ]]; then
    project="gyst"
  elif [[ "$cwd" == *"gyst-seller-portal"* ]]; then
    project="gyst-seller-portal"
  elif [[ "$cwd" == *"jamelna"* ]]; then
    project="jamelna"
  elif [[ "$cwd" == *"smartiegoals"* ]]; then
    project="smartiegoals"
  elif [[ "$cwd" == *"spread-your-ashes"* ]]; then
    project="spread-your-ashes"
  elif [[ "$cwd" == *"conductor"* ]]; then
    project="conductor"
  elif [[ "$cwd" == *"codetale"* ]]; then
    project="codetale"
  elif [[ "$cwd" == *"AndroidGYST"* ]]; then
    project="android-gyst"
  elif [[ "$cwd" == *"Folio"* ]]; then
    project="folio"
  else
    echo "❌ Not in a recognized project directory"
    echo ""
    echo "Recognized projects:"
    echo "  • WardrobeApp/          → gyst"
    echo "  • gyst-seller-portal/   → gyst-seller-portal"
    echo "  • jamelna/              → jamelna"
    echo "  • smartiegoals/         → smartiegoals"
    echo "  • spread-your-ashes/    → spread-your-ashes"
    echo "  • conductor/            → conductor"
    echo "  • codetale/             → codetale"
    echo "  • AndroidGYST/          → android-gyst"
    echo "  • Folio/                → folio"
    return 1
  fi

  # Combine all arguments into query
  local query="$*"

  if [ -z "$query" ]; then
    echo "Usage: ask <question>"
    echo ""
    echo "Examples:"
    echo "  ask where is the login screen"
    echo "  ask how does authentication work"
    echo "  ask similar to src/file.js"
    echo "  ask what files use Firebase"
    return 1
  fi

  # Intent detection - route to appropriate MLX command
  if [[ "$query" =~ ^(where|find|locate) ]]; then
    # "where is X" / "find X" → mlx q
    echo "🔍 Searching for: $query"
    mlx q "$project" "$query"

  elif [[ "$query" =~ ^(how does|how do|explain|what does) ]]; then
    # "how does X work" → mlx rag
    echo "🧠 Understanding: $query"
    mlx rag "$project" "$query"

  elif [[ "$query" =~ ^similar ]]; then
    # "similar to file.js" → mlx similar
    local file=$(echo "$query" | sed 's/similar to //' | sed 's/similar //')
    echo "🔗 Finding files similar to: $file"
    mlx similar "$project" "$file"

  else
    # Default: use mlx q for general queries
    echo "🔍 Querying: $query"
    mlx q "$project" "$query"
  fi
}

# Shorthand aliases (optional)
alias q='ask'

# Show available commands
ask-help() {
  echo "MLX Shell Helper - Natural Language Interface"
  echo ""
  echo "Usage:"
  echo "  ask <question>          Natural language queries"
  echo "  q <question>            Shorthand for 'ask'"
  echo ""
  echo "Examples:"
  echo "  ask where is the login screen"
  echo "  ask how does authentication work"
  echo "  ask similar to src/screens/LoginScreen.js"
  echo "  ask what files use Firebase"
  echo "  q find handleSubmit function"
  echo ""
  echo "Auto-detects project from current directory:"
  echo "  WardrobeApp/          → gyst"
  echo "  gyst-seller-portal/   → gyst-seller-portal"
  echo "  jamelna/              → jamelna"
  echo "  smartiegoals/         → smartiegoals"
  echo "  spread-your-ashes/    → spread-your-ashes"
  echo "  conductor/            → conductor"
  echo "  codetale/             → codetale"
  echo "  AndroidGYST/          → android-gyst"
  echo "  Folio/                → folio"
}
