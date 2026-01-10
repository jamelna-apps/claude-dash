#!/usr/bin/env python3
"""
MLX Code Analyzer - Using code-specialized models

Uses DeepSeek-Coder for better code understanding:
- More accurate function detection
- Better code summaries
- Code smell detection
- Refactoring suggestions

Usage:
  python code_analyzer.py <project> analyze <file>   # Analyze a file
  python code_analyzer.py <project> explain <file>   # Explain code
  python code_analyzer.py <project> review <file>    # Code review
"""

import json
import sys
import argparse
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"
CODE_MODEL = "mlx-community/deepseek-coder-6.7b-instruct-hf-4bit-mlx"

# Check if model exists, fall back to Llama if not
def get_model():
    """Load the best available code model."""
    from mlx_lm import load

    try:
        print(f"Loading {CODE_MODEL}...")
        return load(CODE_MODEL)
    except Exception as e:
        print(f"Code model not found, using Llama...")
        return load("mlx-community/Llama-3.2-3B-Instruct-4bit")

def analyze_file(model, tokenizer, file_path, project_path):
    """Analyze a code file."""
    from mlx_lm import generate

    full_path = Path(project_path) / file_path
    if not full_path.exists():
        return {"error": f"File not found: {full_path}"}

    content = full_path.read_text()
    if len(content) > 10000:
        content = content[:10000] + "\n... [truncated]"

    prompt = f"""Analyze this code file and provide:
1. Main purpose (1 sentence)
2. Key functions and what they do
3. Dependencies and imports used
4. Potential issues or improvements

```
{content}
```

Respond in this JSON format:
{{"purpose": "...", "functions": [{{"name": "...", "does": "..."}}], "dependencies": [...], "issues": [...]}}"""

    response = generate(model, tokenizer, prompt=prompt, max_tokens=500, temp=0.1)

    try:
        import re
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
    except:
        pass

    return {"raw": response}

def explain_code(model, tokenizer, file_path, project_path):
    """Explain what code does in plain English."""
    from mlx_lm import generate

    full_path = Path(project_path) / file_path
    content = full_path.read_text()[:8000]

    prompt = f"""Explain this code in simple terms. What does it do? How does it work?

```
{content}
```

Explain in 3-5 sentences:"""

    return generate(model, tokenizer, prompt=prompt, max_tokens=300, temp=0.3)

def review_code(model, tokenizer, file_path, project_path):
    """Review code for issues and improvements."""
    from mlx_lm import generate

    full_path = Path(project_path) / file_path
    content = full_path.read_text()[:8000]

    prompt = f"""Review this code. Look for:
- Bugs or potential issues
- Performance problems
- Security concerns
- Code quality issues
- Suggestions for improvement

```
{content}
```

List the issues found (or say "No major issues" if clean):"""

    return generate(model, tokenizer, prompt=prompt, max_tokens=500, temp=0.2)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", help="Project ID")
    parser.add_argument("command", choices=["analyze", "explain", "review"])
    parser.add_argument("file", help="File path relative to project")
    args = parser.parse_args()

    # Get project path
    config = json.loads((MEMORY_ROOT / "config.json").read_text())
    project = next((p for p in config["projects"] if p["id"] == args.project), None)
    if not project:
        print(f"Project not found: {args.project}")
        sys.exit(1)

    model, tokenizer = get_model()

    if args.command == "analyze":
        result = analyze_file(model, tokenizer, args.file, project["path"])
        print(json.dumps(result, indent=2))

    elif args.command == "explain":
        result = explain_code(model, tokenizer, args.file, project["path"])
        print(result)

    elif args.command == "review":
        result = review_code(model, tokenizer, args.file, project["path"])
        print(result)

if __name__ == "__main__":
    main()
