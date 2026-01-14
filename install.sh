#!/bin/bash
#
# Claude-Dash Installer
# Persistent memory and learning systems for Claude Code
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/jamelna-apps/claude-dash/main/install.sh | bash
#
# Or clone and run:
#   git clone https://github.com/jamelna-apps/claude-dash.git ~/.claude-dash
#   ~/.claude-dash/install.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

CLAUDE_DASH_DIR="$HOME/.claude-dash"
CLAUDE_DIR="$HOME/.claude"
REPO_URL="https://github.com/jamelna-apps/claude-dash.git"

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                    Claude-Dash Installer                  ║"
echo "║     Persistent Memory & Learning Systems for Claude Code  ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Helper functions
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# =============================================================================
# Step 1: Check Prerequisites
# =============================================================================

echo -e "\n${BLUE}Step 1: Checking prerequisites...${NC}\n"

# Check macOS
if [[ "$(uname)" != "Darwin" ]]; then
    warn "Claude-Dash is optimized for macOS. Some features may not work on other platforms."
fi

# Check Node.js
if check_command node; then
    NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
    if [ "$NODE_VERSION" -ge 18 ]; then
        success "Node.js $(node -v) found"
    else
        warn "Node.js 18+ recommended (found $(node -v))"
    fi
else
    error "Node.js not found. Install from https://nodejs.org or run: brew install node"
fi

# Check Python
if check_command python3; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    success "Python $PYTHON_VERSION found"
else
    error "Python 3 not found. Install from https://python.org or run: brew install python"
fi

# Check Git
if check_command git; then
    success "Git found"
else
    error "Git not found. Install with: xcode-select --install"
fi

# Check Ollama
if check_command ollama; then
    success "Ollama found"
    OLLAMA_INSTALLED=true
else
    warn "Ollama not found. Learning features require Ollama."
    echo "    Install with: brew install ollama"
    OLLAMA_INSTALLED=false
fi

# =============================================================================
# Step 2: Clone or Update Repository
# =============================================================================

echo -e "\n${BLUE}Step 2: Setting up Claude-Dash...${NC}\n"

if [ -d "$CLAUDE_DASH_DIR/.git" ]; then
    info "Claude-Dash directory exists, updating..."
    cd "$CLAUDE_DASH_DIR"
    git pull origin main 2>/dev/null || warn "Could not pull updates"
    success "Updated Claude-Dash"
else
    if [ -d "$CLAUDE_DASH_DIR" ]; then
        warn "Directory exists but is not a git repo. Backing up..."
        mv "$CLAUDE_DASH_DIR" "$CLAUDE_DASH_DIR.backup.$(date +%Y%m%d%H%M%S)"
    fi
    info "Cloning Claude-Dash..."
    git clone "$REPO_URL" "$CLAUDE_DASH_DIR"
    success "Cloned Claude-Dash to $CLAUDE_DASH_DIR"
fi

cd "$CLAUDE_DASH_DIR"

# =============================================================================
# Step 3: Create Configuration Files
# =============================================================================

echo -e "\n${BLUE}Step 3: Setting up configuration...${NC}\n"

# Config file
if [ ! -f "$CLAUDE_DASH_DIR/config.json" ]; then
    if [ -f "$CLAUDE_DASH_DIR/config.example.json" ]; then
        cp "$CLAUDE_DASH_DIR/config.example.json" "$CLAUDE_DASH_DIR/config.json"
        success "Created config.json from example"
    else
        cat > "$CLAUDE_DASH_DIR/config.json" << 'CONFIGEOF'
{
  "version": "1.0",
  "projectsRoot": "",
  "watcher": {
    "enabled": true,
    "ignorePatterns": ["node_modules", ".git", "dist", "build", "__pycache__", ".next"],
    "scanIntervalMs": 5000
  },
  "projects": []
}
CONFIGEOF
        success "Created default config.json"
    fi
    info "Edit $CLAUDE_DASH_DIR/config.json to add your projects"
else
    success "config.json already exists"
fi

# Global preferences
mkdir -p "$CLAUDE_DASH_DIR/global"
if [ ! -f "$CLAUDE_DASH_DIR/global/preferences.json" ]; then
    if [ -f "$CLAUDE_DASH_DIR/global/preferences.example.json" ]; then
        cp "$CLAUDE_DASH_DIR/global/preferences.example.json" "$CLAUDE_DASH_DIR/global/preferences.json"
    else
        cat > "$CLAUDE_DASH_DIR/global/preferences.json" << 'PREFSEOF'
{
  "use": [],
  "avoid": [],
  "conventions": [],
  "patterns": []
}
PREFSEOF
    fi
    success "Created global/preferences.json"
else
    success "global/preferences.json already exists"
fi

# Create required directories
mkdir -p "$CLAUDE_DASH_DIR/projects"
mkdir -p "$CLAUDE_DASH_DIR/sessions/transcripts"
mkdir -p "$CLAUDE_DASH_DIR/sessions/digests"
mkdir -p "$CLAUDE_DASH_DIR/sessions/summaries"
mkdir -p "$CLAUDE_DASH_DIR/logs"
mkdir -p "$CLAUDE_DASH_DIR/indexes"
success "Created required directories"

# =============================================================================
# Step 4: Install Dependencies
# =============================================================================

echo -e "\n${BLUE}Step 4: Installing dependencies...${NC}\n"

# Node dependencies for watcher
if [ -d "$CLAUDE_DASH_DIR/watcher" ]; then
    info "Installing watcher dependencies..."
    cd "$CLAUDE_DASH_DIR/watcher"
    npm install --silent 2>/dev/null || npm install
    success "Installed watcher dependencies"
    cd "$CLAUDE_DASH_DIR"
fi

# Node dependencies for MCP server
if [ -d "$CLAUDE_DASH_DIR/mcp-server" ]; then
    info "Installing MCP server dependencies..."
    cd "$CLAUDE_DASH_DIR/mcp-server"
    npm install --silent 2>/dev/null || npm install
    success "Installed MCP server dependencies"
    cd "$CLAUDE_DASH_DIR"
fi

# Node dependencies for dashboard
if [ -d "$CLAUDE_DASH_DIR/dashboard" ]; then
    info "Installing dashboard dependencies..."
    cd "$CLAUDE_DASH_DIR/dashboard"
    npm install --silent 2>/dev/null || npm install
    success "Installed dashboard dependencies"
    cd "$CLAUDE_DASH_DIR"
fi

# Python virtual environment
if [ ! -d "$CLAUDE_DASH_DIR/mlx-env" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv "$CLAUDE_DASH_DIR/mlx-env"
    success "Created Python virtual environment"
fi

# Install Python dependencies
info "Installing Python dependencies..."
source "$CLAUDE_DASH_DIR/mlx-env/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet sentence-transformers 2>/dev/null || pip install sentence-transformers
deactivate
success "Installed Python dependencies"

# =============================================================================
# Step 5: Set Up Ollama Models
# =============================================================================

echo -e "\n${BLUE}Step 5: Setting up Ollama models...${NC}\n"

if [ "$OLLAMA_INSTALLED" = true ]; then
    # Check if Ollama is running
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        info "Starting Ollama..."
        ollama serve > /dev/null 2>&1 &
        sleep 3
    fi

    # Pull required models
    MODELS=("qwen2.5:7b" "nomic-embed-text")
    for model in "${MODELS[@]}"; do
        if ollama list 2>/dev/null | grep -q "$model"; then
            success "Model $model already installed"
        else
            info "Pulling $model (this may take a few minutes)..."
            ollama pull "$model" || warn "Could not pull $model"
        fi
    done
else
    warn "Skipping Ollama setup (not installed)"
    echo "    To enable learning features, install Ollama:"
    echo "    brew install ollama"
    echo "    ollama pull qwen2.5:7b"
    echo "    ollama pull nomic-embed-text"
fi

# =============================================================================
# Step 6: Set Up Claude Code Hooks
# =============================================================================

echo -e "\n${BLUE}Step 6: Setting up Claude Code hooks...${NC}\n"

# Create hooks directory
mkdir -p "$CLAUDE_DIR/hooks"

# Copy hooks
if [ -d "$CLAUDE_DASH_DIR/hooks" ]; then
    cp "$CLAUDE_DASH_DIR/hooks/inject-context.sh" "$CLAUDE_DIR/hooks/" 2>/dev/null || true
    cp "$CLAUDE_DASH_DIR/hooks/save-session.sh" "$CLAUDE_DIR/hooks/" 2>/dev/null || true
    chmod +x "$CLAUDE_DIR/hooks/"*.sh 2>/dev/null || true
    success "Installed hooks to $CLAUDE_DIR/hooks/"
fi

# Update Claude settings
SETTINGS_FILE="$CLAUDE_DIR/settings.json"
if [ -f "$SETTINGS_FILE" ]; then
    # Check if hooks are already configured
    if grep -q "inject-context.sh" "$SETTINGS_FILE" 2>/dev/null; then
        success "Hooks already configured in settings.json"
    else
        warn "settings.json exists but hooks not configured"
        echo "    Add this to $SETTINGS_FILE:"
        echo ""
        cat << 'HOOKJSON'
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "~/.claude/hooks/inject-context.sh"}]
    }],
    "Stop": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "~/.claude/hooks/save-session.sh"}]
    }]
  }
}
HOOKJSON
    fi
else
    # Create settings file
    cat > "$SETTINGS_FILE" << 'SETTINGSEOF'
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/inject-context.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/save-session.sh"
          }
        ]
      }
    ]
  }
}
SETTINGSEOF
    success "Created $SETTINGS_FILE with hooks configured"
fi

# =============================================================================
# Step 7: Set Up MCP Server
# =============================================================================

echo -e "\n${BLUE}Step 7: Setting up MCP server...${NC}\n"

# Get the correct node path
NODE_PATH=$(which node)

# Check for Claude Desktop config (macOS)
CLAUDE_DESKTOP_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
if [ -d "$HOME/Library/Application Support/Claude" ]; then
    if [ -f "$CLAUDE_DESKTOP_CONFIG" ]; then
        if grep -q "claude-dash" "$CLAUDE_DESKTOP_CONFIG" 2>/dev/null; then
            success "MCP server already configured in Claude Desktop"
        else
            warn "Claude Desktop config exists. Add this to mcpServers:"
            echo ""
            echo "    \"claude-dash\": {"
            echo "      \"command\": \"$NODE_PATH\","
            echo "      \"args\": [\"$CLAUDE_DASH_DIR/mcp-server/server.js\"]"
            echo "    }"
        fi
    else
        info "Claude Desktop detected. Creating MCP config..."
        cat > "$CLAUDE_DESKTOP_CONFIG" << MCPEOF
{
  "mcpServers": {
    "claude-dash": {
      "command": "$NODE_PATH",
      "args": ["$CLAUDE_DASH_DIR/mcp-server/server.js"]
    }
  }
}
MCPEOF
        success "Created Claude Desktop MCP config"
    fi
else
    info "Claude Desktop not found. MCP config instructions:"
    echo "    Add to your Claude settings (mcpServers section):"
    echo ""
    echo "    \"claude-dash\": {"
    echo "      \"command\": \"$NODE_PATH\","
    echo "      \"args\": [\"$CLAUDE_DASH_DIR/mcp-server/server.js\"]"
    echo "    }"
fi

# =============================================================================
# Step 8: Make Scripts Executable
# =============================================================================

echo -e "\n${BLUE}Step 8: Finalizing installation...${NC}\n"

# Make all Python scripts executable
find "$CLAUDE_DASH_DIR/learning" -name "*.py" -exec chmod +x {} \; 2>/dev/null || true
find "$CLAUDE_DASH_DIR/memory" -name "*.py" -exec chmod +x {} \; 2>/dev/null || true
find "$CLAUDE_DASH_DIR/patterns" -name "*.py" -exec chmod +x {} \; 2>/dev/null || true
find "$CLAUDE_DASH_DIR/mlx-tools" -name "*.py" -exec chmod +x {} \; 2>/dev/null || true

# Make shell scripts executable
find "$CLAUDE_DASH_DIR" -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true

success "Made scripts executable"

# =============================================================================
# Step 9: Run Health Check
# =============================================================================

echo -e "\n${BLUE}Step 9: Running health check...${NC}\n"

if [ -f "$CLAUDE_DASH_DIR/memory/health_check.py" ]; then
    python3 "$CLAUDE_DASH_DIR/memory/health_check.py" 2>/dev/null || warn "Health check reported issues"
fi

# =============================================================================
# Done!
# =============================================================================

echo -e "\n${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              Claude-Dash Installation Complete!           ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${BLUE}Next steps:${NC}"
echo ""
echo "1. Add your projects to the config:"
echo "   ${YELLOW}nano ~/.claude-dash/config.json${NC}"
echo ""
echo "2. Start the file watcher:"
echo "   ${YELLOW}~/.claude-dash/watcher/start-watcher.sh start${NC}"
echo ""
echo "3. Restart Claude Code to load the new hooks and MCP tools"
echo ""
echo "4. (Optional) Start the dashboard:"
echo "   ${YELLOW}~/.claude-dash/dashboard/start.sh${NC}"
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo "  Check health:     python3 ~/.claude-dash/memory/health_check.py"
echo "  Watcher status:   ~/.claude-dash/watcher/start-watcher.sh status"
echo "  View logs:        tail -f ~/.claude-dash/logs/*.log"
echo ""
echo -e "${GREEN}Enjoy Claude-Dash!${NC}"
echo ""
