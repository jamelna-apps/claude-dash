#!/bin/bash
# Claude-Dash System Health Check
# Run this to verify all components are working properly

# Note: Don't use set -e as we want to continue even when checks fail

MEMORY_ROOT="$HOME/.claude-dash"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

passed=0
failed=0
warnings=0

check_pass() {
    echo -e "  ${GREEN}✓${NC} $1"
    passed=$((passed + 1))
}

check_fail() {
    echo -e "  ${RED}✗${NC} $1"
    failed=$((failed + 1))
}

check_warn() {
    echo -e "  ${YELLOW}!${NC} $1"
    warnings=$((warnings + 1))
}

echo "======================================"
echo "  Claude-Dash Health Check"
echo "======================================"
echo ""

# 1. Check directories
echo "Checking directories..."
for dir in projects sessions logs indexes gateway watcher mlx-tools; do
    if [ -d "$MEMORY_ROOT/$dir" ]; then
        check_pass "$dir/"
    else
        check_fail "$dir/ missing"
    fi
done
echo ""

# 2. Check watcher
echo "Checking watcher..."
if [ -f "$MEMORY_ROOT/watcher/watcher.pid" ]; then
    pid=$(cat "$MEMORY_ROOT/watcher/watcher.pid" 2>/dev/null)
    if kill -0 "$pid" 2>/dev/null; then
        check_pass "Watcher running (PID: $pid)"
    else
        check_warn "Watcher PID file exists but process not running"
    fi
else
    check_warn "Watcher not running (no PID file)"
fi
echo ""

# 3. Check Ollama
echo "Checking Ollama..."
if pgrep -x "ollama" > /dev/null; then
    check_pass "Ollama process running"
    # Check for embedding model
    if curl -s http://localhost:11434/api/tags 2>/dev/null | grep -q "nomic-embed-text"; then
        check_pass "nomic-embed-text model available"
    else
        check_warn "nomic-embed-text model not found (run: ollama pull nomic-embed-text)"
    fi
else
    check_fail "Ollama not running"
fi
echo ""

# 4. Check Python environment
echo "Checking Python environment..."
if [ -f "$MEMORY_ROOT/mlx-env/bin/python3" ]; then
    check_pass "Python venv exists"
    # Check key packages
    if "$MEMORY_ROOT/mlx-env/bin/python3" -c "import numpy" 2>/dev/null; then
        check_pass "numpy installed"
    else
        check_fail "numpy not installed"
    fi
    if "$MEMORY_ROOT/mlx-env/bin/python3" -c "import sentence_transformers" 2>/dev/null; then
        check_pass "sentence-transformers installed"
    else
        check_warn "sentence-transformers not installed (optional)"
    fi
else
    check_fail "Python venv not found"
fi
echo ""

# 5. Check SQLite database
echo "Checking database..."
if [ -f "$MEMORY_ROOT/memory.db" ]; then
    size=$(ls -lh "$MEMORY_ROOT/memory.db" | awk '{print $5}')
    check_pass "memory.db exists ($size)"
    # Check if tables exist
    tables=$(sqlite3 "$MEMORY_ROOT/memory.db" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null)
    if [ "$tables" -gt 0 ]; then
        check_pass "Database has $tables tables"
    else
        check_warn "Database has no tables (run migration)"
    fi
else
    check_fail "memory.db not found"
fi
echo ""

# 6. Check hooks
echo "Checking Claude hooks..."
if [ -f "$HOME/.claude/hooks/inject-context.sh" ]; then
    check_pass "inject-context.sh installed"
else
    check_warn "inject-context.sh not installed"
fi
if [ -f "$HOME/.claude/hooks/save-session.sh" ]; then
    check_pass "save-session.sh installed"
else
    check_warn "save-session.sh not installed"
fi
echo ""

# 7. Check config
echo "Checking configuration..."
if [ -f "$MEMORY_ROOT/config.json" ]; then
    projects=$(python3 -c "import json; print(len(json.load(open('$MEMORY_ROOT/config.json')).get('projects', [])))" 2>/dev/null)
    check_pass "config.json exists ($projects projects)"
else
    check_fail "config.json not found"
fi
echo ""

# 8. Check log sizes
echo "Checking logs..."
for log in watcher/watcher.log logs/dashboard.log logs/db-sync.log; do
    if [ -f "$MEMORY_ROOT/$log" ]; then
        size=$(ls -lh "$MEMORY_ROOT/$log" 2>/dev/null | awk '{print $5}')
        if [ -n "$size" ]; then
            # Check if over 10MB
            bytes=$(ls -l "$MEMORY_ROOT/$log" 2>/dev/null | awk '{print $5}')
            if [ "$bytes" -gt 10485760 ] 2>/dev/null; then
                check_warn "$log is large ($size) - consider rotating"
            else
                check_pass "$log ($size)"
            fi
        fi
    fi
done
echo ""

# Summary
echo "======================================"
echo "  Summary"
echo "======================================"
echo -e "  ${GREEN}Passed:${NC}   $passed"
echo -e "  ${YELLOW}Warnings:${NC} $warnings"
echo -e "  ${RED}Failed:${NC}   $failed"
echo ""

if [ $failed -gt 0 ]; then
    echo -e "${RED}Some checks failed. Run install.sh to fix.${NC}"
    exit 1
elif [ $warnings -gt 0 ]; then
    echo -e "${YELLOW}System operational with warnings.${NC}"
    exit 0
else
    echo -e "${GREEN}All systems operational!${NC}"
    exit 0
fi
