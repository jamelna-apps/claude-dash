#!/bin/bash
# Verification script for Claude-Dash Quality Improvements
# Run this to verify all changes are working correctly

set -e
PASS=0
FAIL=0

echo "=== Claude-Dash Quality Improvements Verification ==="
echo ""

# Test 1: Complexity router - commit message should go LOCAL
echo -n "1. Routing 'write commit message' → "
RESULT=$(python3 ~/.claude-dash/mlx-tools/complexity_router.py "write commit message" 2>/dev/null | grep "Recommended:")
if [[ "$RESULT" == *"LOCAL"* ]]; then
    echo "✓ LOCAL (correct)"
    ((PASS++))
else
    echo "✗ FAIL: Expected LOCAL, got: $RESULT"
    ((FAIL++))
fi

# Test 2: Complexity router - feature should go CLAUDE
echo -n "2. Routing 'add login feature' → "
RESULT=$(python3 ~/.claude-dash/mlx-tools/complexity_router.py "add login feature" 2>/dev/null | grep "Recommended:")
if [[ "$RESULT" == *"CLAUDE"* ]]; then
    echo "✓ CLAUDE (correct)"
    ((PASS++))
else
    echo "✗ FAIL: Expected CLAUDE, got: $RESULT"
    ((FAIL++))
fi

# Test 3: Complexity router - debug should go CLAUDE
echo -n "3. Routing 'debug intermittent crash' → "
RESULT=$(python3 ~/.claude-dash/mlx-tools/complexity_router.py "debug intermittent crash" 2>/dev/null | grep "Recommended:")
if [[ "$RESULT" == *"CLAUDE"* ]]; then
    echo "✓ CLAUDE (correct)"
    ((PASS++))
else
    echo "✗ FAIL: Expected CLAUDE, got: $RESULT"
    ((FAIL++))
fi

# Test 4: Agent context builder - implementation context
echo -n "4. Agent context builder (implement) → "
RESULT=$(python3 ~/.claude-dash/hooks/agent_context_builder.py gyst implement 2>/dev/null)
if [[ "$RESULT" == *"Learned Corrections"* ]] || [[ "$RESULT" == *"Preferred"* ]]; then
    echo "✓ Returns corrections/preferences"
    ((PASS++))
else
    echo "✗ FAIL: Missing expected sections"
    ((FAIL++))
fi

# Test 5: Agent context builder - planning context
echo -n "5. Agent context builder (plan) → "
RESULT=$(python3 ~/.claude-dash/hooks/agent_context_builder.py gyst plan 2>/dev/null)
if [[ "$RESULT" == *"Recent Decisions"* ]] || [[ "$RESULT" == *"Code Patterns"* ]]; then
    echo "✓ Returns decisions/patterns"
    ((PASS++))
else
    echo "✗ FAIL: Missing expected sections"
    ((FAIL++))
fi

# Test 6: Session context - has pending work function
echo -n "6. Session context functions exist → "
RESULT=$(python3 -c "from pathlib import Path; import sys; sys.path.insert(0, str(Path.home() / '.claude-dash/memory')); from session_context import get_pending_work, get_blockers; print('OK')" 2>/dev/null)
if [[ "$RESULT" == "OK" ]]; then
    echo "✓ get_pending_work, get_blockers defined"
    ((PASS++))
else
    echo "✗ FAIL: Functions not found"
    ((FAIL++))
fi

# Test 7: Roadmap has sprints format
echo -n "7. GYST roadmap has sprints array → "
if python3 -c "import json; d=json.load(open('$HOME/.claude-dash/projects/gyst/roadmap.json')); assert 'sprints' in d; print('OK')" 2>/dev/null; then
    echo "✓ sprints array present"
    ((PASS++))
else
    echo "✗ FAIL: sprints array missing"
    ((FAIL++))
fi

# Test 8: Tool descriptions updated
echo -n "8. Gateway server has NON-CRITICAL warnings → "
if grep -q "NON-CRITICAL" ~/.claude-dash/gateway/server.js 2>/dev/null; then
    echo "✓ Tool descriptions updated"
    ((PASS++))
else
    echo "✗ FAIL: NON-CRITICAL warning not found"
    ((FAIL++))
fi

# Test 9: CLAUDE.md has model strategy
echo -n "9. CLAUDE.md has Model Selection Strategy → "
if grep -q "Model Selection Strategy" ~/.claude/CLAUDE.md 2>/dev/null; then
    echo "✓ Section present"
    ((PASS++))
else
    echo "✗ FAIL: Section missing"
    ((FAIL++))
fi

# Test 10: Smart routing skill updated
echo -n "10. Smart routing skill updated → "
if grep -q "Local LLM is NOT for Critical Work" ~/.claude-dash/skills/core/smart-routing/SKILL.md 2>/dev/null; then
    echo "✓ Local LLM warning present"
    ((PASS++))
else
    echo "✗ FAIL: Warning missing"
    ((FAIL++))
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ $FAIL -eq 0 ]; then
    echo "All checks passed! ✓"
    exit 0
else
    echo "Some checks failed. Review the output above."
    exit 1
fi
