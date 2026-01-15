#!/bin/bash
# JSON Helper for Claude-Dash Hooks
#
# Provides safe JSON parsing functions using Python
# (more reliable than grep/sed chains)

# Extract a field from JSON input
# Usage: echo '{"foo":"bar"}' | json_get "foo"
json_get() {
    local field="$1"
    python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # Support nested fields like 'foo.bar.baz'
    for key in '$field'.split('.'):
        data = data.get(key, '') if isinstance(data, dict) else ''
    print(data if isinstance(data, str) else json.dumps(data))
except:
    print('')
" 2>/dev/null
}

# Get project ID from config.json for a given path
# Usage: project_id=$(get_project_id "/path/to/project")
get_project_id() {
    local project_path="$1"
    local config_file="${MEMORY_ROOT:-$HOME/.claude-dash}/config.json"

    if [ ! -f "$config_file" ]; then
        echo ""
        return
    fi

    python3 -c "
import sys, json
try:
    config = json.load(open('$config_file'))
    path = '$project_path'.rstrip('/')
    for p in config.get('projects', []):
        if p.get('path', '').rstrip('/') == path:
            print(p.get('id', ''))
            sys.exit(0)
    # No match found
    print('')
except Exception as e:
    print('', file=sys.stderr)
" 2>/dev/null
}

# Parse hook input JSON
# Usage: eval "$(parse_hook_input)"
# Sets: HOOK_SESSION_ID, HOOK_CWD, HOOK_TRANSCRIPT, etc.
parse_hook_input() {
    python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # Output shell variable assignments
    print('HOOK_SESSION_ID=\"%s\"' % data.get('session_id', ''))
    print('HOOK_CWD=\"%s\"' % data.get('cwd', ''))
    print('HOOK_TRANSCRIPT=\"%s\"' % data.get('transcript_path', ''))
    print('HOOK_REASON=\"%s\"' % data.get('reason', ''))
    print('HOOK_PROMPT=\"%s\"' % data.get('prompt', '').replace('\"', '\\\\\"')[:500])
except:
    # On error, output empty values
    print('HOOK_SESSION_ID=\"\"')
    print('HOOK_CWD=\"\"')
    print('HOOK_TRANSCRIPT=\"\"')
    print('HOOK_REASON=\"\"')
    print('HOOK_PROMPT=\"\"')
" 2>/dev/null
}

# Validate JSON file
# Usage: validate_json "/path/to/file.json"
validate_json() {
    local file="$1"
    python3 -c "
import sys, json
try:
    json.load(open('$file'))
    sys.exit(0)
except:
    sys.exit(1)
" 2>/dev/null
}
