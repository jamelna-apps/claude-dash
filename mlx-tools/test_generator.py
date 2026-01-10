#!/usr/bin/env python3
"""
MLX Test Generator - Generate unit tests for code
"""

import sys
import json
import urllib.request
from pathlib import Path

MEMORY_ROOT = Path.home() / '.claude-dash'
OLLAMA_URL = 'http://localhost:11434'
MODEL = 'llama3.2:3b'

# Framework detection by extension
FRAMEWORKS = {
    '.js': ('Jest', 'describe/it blocks with expect()'),
    '.jsx': ('Jest + React Testing Library', 'render, screen, fireEvent'),
    '.ts': ('Jest', 'describe/it blocks with expect()'),
    '.tsx': ('Jest + React Testing Library', 'render, screen, fireEvent'),
    '.py': ('pytest', 'def test_* functions with assert'),
    '.go': ('Go testing', 'func Test* with t.Error'),
    '.rb': ('RSpec', 'describe/it blocks with expect()'),
    '.rs': ('Rust #[test]', '#[test] fn test_*'),
    '.java': ('JUnit', '@Test annotations'),
    '.swift': ('XCTest', 'func test* with XCTAssert'),
}


def detect_framework(filepath):
    """Detect testing framework from file extension"""
    ext = Path(filepath).suffix
    return FRAMEWORKS.get(ext, ('appropriate framework', 'standard test patterns'))


def get_project_test_patterns(project_id):
    """Get existing test patterns from project"""
    if not project_id:
        return ""

    # Check for existing test files
    summaries_path = MEMORY_ROOT / 'projects' / project_id / 'summaries.json'
    if summaries_path.exists():
        summaries = json.loads(summaries_path.read_text())
        test_files = [f for f in summaries.get('files', {}).keys()
                      if 'test' in f.lower() or 'spec' in f.lower()]
        if test_files:
            return f"Existing test files in project: {', '.join(test_files[:5])}"
    return ""


def generate_tests(code, filepath, framework, patterns):
    """Generate tests using Ollama"""
    framework_name, framework_style = framework

    prompt = f"""Generate comprehensive unit tests for this code.

Testing Framework: {framework_name}
Style: {framework_style}
{patterns}

Requirements:
1. Test all public functions/methods
2. Include edge cases (null, empty, boundary values)
3. Test error handling
4. Use descriptive test names
5. Add setup/teardown if needed

Source file: {filepath}
```
{code[:5000]}
```

Output ONLY the test code, no explanations. Make it ready to run."""

    data = json.dumps({
        'model': MODEL,
        'prompt': prompt,
        'stream': False
    }).encode()

    req = urllib.request.Request(
        f'{OLLAMA_URL}/api/generate',
        data=data,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            return result.get('response', '').strip()
    except Exception as e:
        return f"Error: {e}"


def get_project_id():
    """Get current project from git root"""
    import subprocess
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
                    return project['id']
    except:
        pass
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: mlx test <file> [--output <test_file>]")
        print("Example: mlx test src/utils.js --output src/__tests__/utils.test.js")
        sys.exit(1)

    filepath = sys.argv[1]
    output_file = None

    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_file = sys.argv[idx + 1]

    # Read source file
    try:
        code = Path(filepath).read_text()
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

    framework = detect_framework(filepath)
    project_id = get_project_id()
    patterns = get_project_test_patterns(project_id)

    print(f"Generating {framework[0]} tests for: {filepath}")
    if project_id:
        print(f"Project: {project_id}")
    print("---")

    tests = generate_tests(code, filepath, framework, patterns)

    if output_file:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        Path(output_file).write_text(tests)
        print(f"Tests written to: {output_file}")
    else:
        print(tests)


if __name__ == '__main__':
    main()
