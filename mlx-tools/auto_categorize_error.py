#!/usr/bin/env python3
"""
Auto-Categorize Error - Uses local Ollama to analyze and categorize errors
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Import our Ollama client
sys.path.insert(0, str(Path(__file__).parent))
from ollama_client import OllamaClient

MEMORY_BASE = Path.home() / ".claude-dash"
PROJECTS_DIR = MEMORY_BASE / "projects"
ERROR_QUEUE = MEMORY_BASE / "error-queue"

CATEGORIES = {
    "prompt": {
        "ambiguous_instruction": "Could be interpreted multiple ways",
        "missing_constraints": "Didn't specify what NOT to do",
        "too_verbose": "Key requirements buried in walls of text",
        "implicit_expectations": "Requirements in head, not in prompt",
        "wrong_abstraction": "Too high-level or too detailed for task"
    },
    "context": {
        "context_rot": "Conversation too long, should have cleared",
        "stale_context": "Old information polluting responses",
        "missing_context": "Assumed Claude remembered something it didn't",
        "wrong_context": "Irrelevant info drowning signal"
    },
    "harness": {
        "subagent_context_loss": "Critical info didn't reach subagents",
        "wrong_agent_type": "Used wrong specialized agent for task",
        "no_guardrails": "Didn't constrain agent behavior",
        "missing_validation": "No check that output was correct"
    },
    "tool": {
        "wrong_command": "Incorrect command or syntax used",
        "missing_dependency": "Required package/tool not installed",
        "permission_error": "Insufficient permissions for operation",
        "path_error": "File or directory not found",
        "syntax_error": "Code syntax issue"
    }
}

CATEGORIZATION_PROMPT = """Analyze this error from an agentic coding session and categorize it.

ERROR CONTEXT:
- Trigger: {trigger}
- Pattern Matched: {pattern}
- User Prompt: {user_prompt}
- Tool Name: {tool_name}
- Tool Output: {tool_output}

CATEGORIES:
{categories}

Respond with ONLY a JSON object (no markdown, no explanation):
{{
  "category": "<main category>",
  "subcategory": "<specific subcategory>",
  "summary": "<1-2 sentence description of what went wrong>",
  "root_cause": "<what the user did wrong>",
  "prevention": "<what to do differently next time>"
}}
"""

def format_categories():
    """Format categories for prompt"""
    lines = []
    for cat, subcats in CATEGORIES.items():
        lines.append(f"\n{cat.upper()}:")
        for subcat, desc in subcats.items():
            lines.append(f"  - {subcat}: {desc}")
    return "\n".join(lines)

def categorize_error(error_data: dict) -> dict:
    """Use Ollama to categorize the error"""
    client = OllamaClient()

    # Check if Ollama is available
    if not client.available:
        # Fallback to simple categorization
        return simple_categorize(error_data)

    prompt = CATEGORIZATION_PROMPT.format(
        trigger=error_data.get('trigger', 'unknown'),
        pattern=error_data.get('pattern_matched', 'none'),
        user_prompt=error_data.get('user_prompt', '')[:500],
        tool_name=error_data.get('tool_name', 'none'),
        tool_output=error_data.get('tool_output', '')[:500],
        categories=format_categories()
    )

    try:
        response = client.generate(prompt, model="llama3.2:3b")

        # Parse JSON response
        # Clean up response - remove markdown if present
        response = response.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1]
            response = response.rsplit("```", 1)[0]

        result = json.loads(response)
        return result
    except Exception as e:
        # Fallback to simple categorization
        return simple_categorize(error_data)

def simple_categorize(error_data: dict) -> dict:
    """Simple rule-based categorization as fallback"""
    trigger = error_data.get('trigger', '')
    pattern = error_data.get('pattern_matched', '').lower()
    tool_output = error_data.get('tool_output', '').lower()

    # Determine category based on trigger and patterns
    if trigger == 'tool_failure':
        if 'permission' in tool_output:
            return {
                "category": "tool",
                "subcategory": "permission_error",
                "summary": "Permission denied during tool execution",
                "root_cause": "Insufficient permissions for the operation",
                "prevention": "Check file permissions or run with appropriate access"
            }
        elif 'not found' in tool_output or 'no such' in tool_output:
            return {
                "category": "tool",
                "subcategory": "path_error",
                "summary": "File or directory not found",
                "root_cause": "Path doesn't exist or typo in path",
                "prevention": "Verify paths before running commands"
            }
        elif 'syntax' in tool_output:
            return {
                "category": "tool",
                "subcategory": "syntax_error",
                "summary": "Syntax error in code or command",
                "root_cause": "Invalid syntax in generated code",
                "prevention": "Review code before execution"
            }
        else:
            return {
                "category": "tool",
                "subcategory": "wrong_command",
                "summary": "Tool command failed",
                "root_cause": "Command or syntax issue",
                "prevention": "Verify command before execution"
            }

    # Frustration signal categorization
    if 'not what i' in pattern or 'wrong' in pattern:
        return {
            "category": "prompt",
            "subcategory": "ambiguous_instruction",
            "summary": "Claude misunderstood the request",
            "root_cause": "Prompt could be interpreted multiple ways",
            "prevention": "Be more specific about exactly what you want"
        }
    elif 'already told' in pattern or 'i said' in pattern:
        return {
            "category": "context",
            "subcategory": "missing_context",
            "summary": "Claude forgot previous information",
            "root_cause": "Context was lost or not properly retained",
            "prevention": "Repeat key information or start fresh session"
        }
    elif 'undo' in pattern or 'revert' in pattern:
        return {
            "category": "prompt",
            "subcategory": "missing_constraints",
            "summary": "Claude made unwanted changes",
            "root_cause": "Didn't specify what NOT to do",
            "prevention": "Explicitly state constraints and boundaries"
        }

    return {
        "category": "prompt",
        "subcategory": "implicit_expectations",
        "summary": "Mismatch between expectation and result",
        "root_cause": "Requirements not fully specified",
        "prevention": "Make expectations explicit in the prompt"
    }

def save_categorized_error(error_data: dict, categorization: dict, project: str):
    """Save the categorized error to the project's errors.json"""
    errors_file = PROJECTS_DIR / project / "errors.json"
    errors_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing errors
    errors = []
    if errors_file.exists():
        with open(errors_file, 'r') as f:
            errors = json.load(f)

    # Create error entry
    timestamp = error_data.get('timestamp', datetime.now().strftime("%Y%m%d-%H%M%S"))
    error_entry = {
        "id": f"error-{timestamp}",
        "date": datetime.now().isoformat(),
        "project": project,
        "trigger": error_data.get('trigger'),
        "category": categorization.get('category'),
        "subcategory": categorization.get('subcategory'),
        "summary": categorization.get('summary'),
        "rootCause": categorization.get('root_cause'),
        "prevention": categorization.get('prevention'),
        "triggeringPrompt": error_data.get('user_prompt', '')[:500],
        "toolName": error_data.get('tool_name'),
        "toolOutput": error_data.get('tool_output', '')[:500],
        "patternMatched": error_data.get('pattern_matched'),
        "automated": True
    }

    errors.append(error_entry)

    with open(errors_file, 'w') as f:
        json.dump(errors, f, indent=2)

    return error_entry

def main():
    if len(sys.argv) < 2:
        print("Usage: auto_categorize_error.py <error_file>")
        sys.exit(1)

    error_file = Path(sys.argv[1])

    if not error_file.exists():
        print(f"Error file not found: {error_file}")
        sys.exit(1)

    # Load error data
    with open(error_file, 'r') as f:
        error_data = json.load(f)

    project = error_data.get('project', 'unknown')

    # Categorize with Ollama
    categorization = categorize_error(error_data)

    # Save to project errors
    saved = save_categorized_error(error_data, categorization, project)

    # Mark as processed and clean up
    error_data['status'] = 'processed'
    error_data['categorization'] = categorization
    with open(error_file, 'w') as f:
        json.dump(error_data, f, indent=2)

    # Optionally remove from queue after processing
    # error_file.unlink()

    print(f"Categorized error: {saved['id']} - {saved['category']}/{saved['subcategory']}")

if __name__ == "__main__":
    main()
