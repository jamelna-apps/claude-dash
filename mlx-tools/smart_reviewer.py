#!/usr/bin/env python3
"""
Smart Code Reviewer - Token-efficient code review using local Ollama

Strategy:
1. First-pass: Local LLM (qwen2.5:7b by default) analyzes code (free, fast)
2. Outputs structured summary with issues categorized by severity
3. Only escalates to Claude when HIGH severity or complex issues found
4. Provides Claude-ready context that's 70-90% smaller than raw code

Usage:
  python smart_reviewer.py <file>                    # Local review only
  python smart_reviewer.py <file> --escalate         # Force escalate to Claude
  python smart_reviewer.py <file> --summary-only     # Just the summary for Claude
  python smart_reviewer.py --staged                  # Review git staged changes

Set REVIEW_MODEL env var to use a different model (e.g., qwen3:8b on 32GB+ systems)
"""

import sys
import json
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
import requests
import os

MEMORY_ROOT = Path.home() / '.claude-dash'
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')

# Use qwen2.5:7b for reliable fast reviews on 16GB RAM systems
# For 32GB+ systems with qwen3, set REVIEW_MODEL=qwen3:8b or qwen3:30b-a3b
REVIEW_MODEL = os.environ.get('REVIEW_MODEL', 'qwen2.5:7b')
FALLBACK_MODEL = 'qwen2.5:7b'


def get_available_model() -> str:
    """Check which Ollama model is available for review."""
    try:
        resp = requests.get(f'{OLLAMA_URL}/api/tags', timeout=5)
        if resp.status_code == 200:
            models = [m['name'] for m in resp.json().get('models', [])]

            # Check if preferred model is available
            if any(REVIEW_MODEL in m for m in models):
                return REVIEW_MODEL
            if any(FALLBACK_MODEL in m for m in models):
                return FALLBACK_MODEL
            # Try any qwen model
            qwen_models = [m for m in models if 'qwen' in m.lower()]
            if qwen_models:
                return qwen_models[0]
            # No suitable model found
            if models:
                print(f"Warning: No qwen model found. Available: {', '.join(models[:5])}", file=sys.stderr)
            else:
                print("Warning: No Ollama models installed. Run: ollama pull qwen2.5:7b", file=sys.stderr)
    except requests.exceptions.ConnectionError:
        print("Error: Ollama not running. Start with: ollama serve", file=sys.stderr)
    except Exception as e:
        print(f"Error checking Ollama: {e}", file=sys.stderr)
    return REVIEW_MODEL  # Return default, will fail with clear error if not available


def get_project_context() -> tuple:
    """Get current project from git root."""
    try:
        git_root = subprocess.check_output(
            ['git', 'rev-parse', '--show-toplevel'],
            stderr=subprocess.DEVNULL
        ).decode().strip()

        config_path = MEMORY_ROOT / 'config.json'
        if config_path.exists():
            config = json.loads(config_path.read_text())
            for project in config.get('projects', []):
                if project['path'] == git_root:
                    return project['id'], git_root

        return None, git_root
    except:
        return None, None


def get_staged_diff() -> str:
    """Get staged changes."""
    try:
        return subprocess.check_output(
            ['git', 'diff', '--staged'],
            stderr=subprocess.DEVNULL
        ).decode()
    except:
        return ""


def read_file(filepath: str) -> str:
    """Read a file."""
    try:
        return Path(filepath).read_text()
    except:
        return ""


def count_tokens_approx(text: str) -> int:
    """Approximate token count (rough estimate)."""
    return len(text) // 4


def analyze_code_structure(code: str, filepath: str = "") -> Dict:
    """Quick static analysis without LLM."""
    lines = code.split('\n')

    analysis = {
        'lines': len(lines),
        'tokens_approx': count_tokens_approx(code),
        'has_async': 'async ' in code or 'await ' in code,
        'has_try_catch': 'try' in code and ('catch' in code or 'except' in code),
        'has_console_log': 'console.log' in code or 'print(' in code,
        'has_todo': 'TODO' in code or 'FIXME' in code or 'HACK' in code,
        'has_secrets_pattern': any(p in code.lower() for p in ['password', 'secret', 'api_key', 'apikey', 'token']),
        'file_type': Path(filepath).suffix if filepath else 'unknown',
        'imports': [],
        'functions': [],
        'classes': [],
    }

    # Extract key elements
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('import ') or stripped.startswith('from '):
            analysis['imports'].append(stripped[:80])
        elif 'def ' in stripped or 'function ' in stripped or '=>' in stripped:
            # Extract function name
            if 'def ' in stripped:
                name = stripped.split('def ')[1].split('(')[0]
                analysis['functions'].append(name)
            elif 'function ' in stripped:
                name = stripped.split('function ')[1].split('(')[0]
                analysis['functions'].append(name)
        elif 'class ' in stripped:
            name = stripped.split('class ')[1].split('(')[0].split(':')[0]
            analysis['classes'].append(name)

    return analysis


def first_pass_review(code: str, context: str = "", model: str = None) -> Dict:
    """
    First-pass review using local Ollama model.
    Returns structured issues for potential Claude escalation.
    """
    model = model or get_available_model()

    # Optimized prompt for structured output
    code_snippet = code[:4000]  # Limit code size for faster processing

    prompt = f"""Review code briefly. Output JSON only, max 3 issues per category:

```
{code_snippet}
```

{{"high":[],"medium":[],"low":[],"summary":"brief","escalate":false}}"""

    try:
        response = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={
                'model': model,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': 0.1,  # Low temp for structured output
                    'num_predict': 1000  # Enough for complete JSON response
                }
            },
            timeout=180  # 3 min timeout for first model load
        )

        if response.status_code == 200:
            result = response.json().get('response', '').strip()

            # Try to parse JSON from response
            try:
                # Find JSON in response
                start = result.find('{')
                end = result.rfind('}') + 1
                if start >= 0 and end > start:
                    json_str = result[start:end]
                    parsed = json.loads(json_str)
                    # Normalize keys to match expected format
                    return {
                        'high_severity': parsed.get('high', parsed.get('high_severity', [])),
                        'medium_severity': parsed.get('medium', parsed.get('medium_severity', [])),
                        'low_severity': parsed.get('low', parsed.get('low_severity', [])),
                        'summary': parsed.get('summary', ''),
                        'needs_deep_review': parsed.get('escalate', parsed.get('needs_deep_review', False)),
                        'reason_for_deep_review': parsed.get('reason', parsed.get('reason_for_deep_review', ''))
                    }
            except json.JSONDecodeError as e:
                pass

            # Fallback: return as unstructured
            return {
                'high_severity': [],
                'medium_severity': [],
                'low_severity': [],
                'summary': result[:200] if result else 'No response',
                'needs_deep_review': True,
                'reason_for_deep_review': 'Could not parse structured response',
                'raw_response': result[:500] if result else ''
            }
    except Exception as e:
        return {
            'error': str(e),
            'high_severity': [],
            'medium_severity': [],
            'low_severity': [],
            'summary': f'Review failed: {e}',
            'needs_deep_review': True,
            'reason_for_deep_review': f'Local review failed: {e}'
        }


def generate_claude_summary(code: str, filepath: str, review_result: Dict, structure: Dict) -> str:
    """
    Generate a token-efficient summary for Claude.
    This is what gets sent to Claude instead of the full code.
    """
    high_issues = review_result.get('high_severity', [])
    medium_issues = review_result.get('medium_severity', [])

    summary_parts = [
        f"## Code Review Summary: {filepath}",
        f"**Lines:** {structure['lines']} | **Est. Tokens:** {structure['tokens_approx']}",
        f"**Type:** {structure['file_type']}",
        ""
    ]

    if structure['functions']:
        summary_parts.append(f"**Functions:** {', '.join(structure['functions'][:10])}")
    if structure['classes']:
        summary_parts.append(f"**Classes:** {', '.join(structure['classes'][:5])}")

    summary_parts.append("")
    summary_parts.append(f"### Local Review")
    summary_parts.append(f"**Assessment:** {review_result.get('summary', 'N/A')}")
    summary_parts.append("")

    if high_issues:
        summary_parts.append("### HIGH Severity Issues (need attention)")
        for issue in high_issues:
            summary_parts.append(f"- [{issue.get('type', 'issue')}] {issue.get('issue', '')} (line ~{issue.get('line', '?')})")

    if medium_issues:
        summary_parts.append("")
        summary_parts.append("### MEDIUM Severity Issues")
        for issue in medium_issues:
            summary_parts.append(f"- [{issue.get('type', 'issue')}] {issue.get('issue', '')}")

    if review_result.get('needs_deep_review'):
        summary_parts.append("")
        summary_parts.append(f"### Recommended for Deep Review")
        summary_parts.append(f"**Reason:** {review_result.get('reason_for_deep_review', 'Complex logic detected')}")

    # Include relevant code snippets only for high severity issues
    if high_issues and len(code) > 0:
        summary_parts.append("")
        summary_parts.append("### Relevant Code Snippets")
        lines = code.split('\n')
        for issue in high_issues[:3]:  # Max 3 snippets
            line_ref = issue.get('line', '')
            try:
                if '-' in str(line_ref):
                    start, end = map(int, str(line_ref).split('-'))
                else:
                    line_num = int(line_ref)
                    start, end = max(0, line_num - 3), min(len(lines), line_num + 3)

                snippet = '\n'.join(lines[start:end])
                summary_parts.append(f"```\n# Lines {start}-{end}\n{snippet}\n```")
            except:
                pass

    return '\n'.join(summary_parts)


def print_review_result(result: Dict, verbose: bool = False):
    """Pretty print the review result."""
    high = result.get('high_severity', [])
    medium = result.get('medium_severity', [])
    low = result.get('low_severity', [])

    # Header with counts
    print(f"\n{'='*60}")
    print(f"  HIGH: {len(high)}  |  MEDIUM: {len(medium)}  |  LOW: {len(low)}")
    print(f"{'='*60}")

    if result.get('summary'):
        print(f"\n{result['summary']}")

    if high:
        print(f"\n{'!'*3} HIGH SEVERITY {'!'*3}")
        for issue in high:
            print(f"  [{issue.get('type', '?')}] {issue.get('issue', '')} (line ~{issue.get('line', '?')})")

    if medium:
        print(f"\n{'*'*3} MEDIUM SEVERITY")
        for issue in medium:
            print(f"  [{issue.get('type', '?')}] {issue.get('issue', '')}")

    if low and verbose:
        print(f"\n{'.'*3} LOW SEVERITY")
        for issue in low:
            print(f"  - {issue.get('issue', '')}")
            if issue.get('suggestion'):
                print(f"    Suggestion: {issue['suggestion']}")

    if result.get('needs_deep_review'):
        print(f"\n>>> ESCALATE TO CLAUDE: {result.get('reason_for_deep_review', 'Complex review needed')}")
    else:
        print(f"\n No Claude escalation needed")

    print()


def main():
    args = sys.argv[1:]

    if not args or '--help' in args:
        print(__doc__)
        sys.exit(0)

    # Parse flags
    escalate = '--escalate' in args
    summary_only = '--summary-only' in args
    verbose = '--verbose' in args or '-v' in args
    staged = '--staged' in args

    # Remove flags from args
    args = [a for a in args if not a.startswith('-')]

    # Determine what to review
    if staged:
        code = get_staged_diff()
        if not code:
            print("No staged changes to review.")
            sys.exit(0)
        filepath = "staged changes"
    else:
        filepath = args[0] if args else None
        if not filepath:
            print("Error: Provide a file path or use --staged")
            sys.exit(1)
        code = read_file(filepath)
        if not code:
            print(f"Could not read: {filepath}")
            sys.exit(1)

    # Get project context
    project_id, git_root = get_project_context()
    context = ""
    if project_id:
        prefs_path = MEMORY_ROOT / 'projects' / project_id / 'preferences.json'
        if prefs_path.exists():
            prefs = json.loads(prefs_path.read_text())
            avoid = prefs.get('avoid', [])
            patterns = prefs.get('patterns', [])
            if avoid:
                context += f"Project rules - avoid: {', '.join(avoid)}\n"
            if patterns:
                context += f"Project patterns: {', '.join(patterns[:3])}\n"

    # Quick structure analysis
    structure = analyze_code_structure(code, filepath)

    if not summary_only:
        model = get_available_model()
        print(f"Reviewing: {filepath}")
        print(f"Model: {model}")
        if project_id:
            print(f"Project: {project_id}")
        print(f"Size: {structure['lines']} lines, ~{structure['tokens_approx']} tokens")

    # First pass review with local Ollama
    result = first_pass_review(code, context)

    if summary_only:
        # Output Claude-ready summary
        summary = generate_claude_summary(code, filepath, result, structure)
        print(summary)
    else:
        # Print human-readable result
        print_review_result(result, verbose)

        # Show token savings
        original_tokens = structure['tokens_approx']
        summary = generate_claude_summary(code, filepath, result, structure)
        summary_tokens = count_tokens_approx(summary)
        savings = ((original_tokens - summary_tokens) / original_tokens) * 100 if original_tokens > 0 else 0

        print(f"Token savings if escalated: {original_tokens} -> {summary_tokens} ({savings:.0f}% reduction)")

        if escalate or (result.get('needs_deep_review') and result.get('high_severity')):
            print("\n" + "="*60)
            print("CLAUDE-READY SUMMARY (copy this instead of full code):")
            print("="*60)
            print(summary)


if __name__ == '__main__':
    main()
