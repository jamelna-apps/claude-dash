#!/usr/bin/env python3
"""
MLX Observation Extractor for Claude Memory System

Extracts categorized observations from session data using local MLX models.
Zero API token cost.

Usage:
  source ~/.claude-dash/mlx-env/bin/activate
  python observation_extractor.py <transcript_path> <project_id> [--session-id ID]

Categories:
  - decision: Technical choices made
  - pattern: Patterns discovered/applied
  - bugfix: Bugs found and fixes applied
  - gotcha: Tricky/unexpected things
  - feature: Features implemented
  - implementation: How something was built
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# MLX imports - optional, falls back to simple extraction
try:
    from mlx_lm import load, generate
    HAS_MLX = True
except ImportError:
    HAS_MLX = False
    print("Warning: mlx-lm not available, using simple extraction")

MEMORY_ROOT = Path.home() / ".claude-dash"
DEFAULT_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"

OBSERVATION_CATEGORIES = [
    "decision",      # Technical choices made
    "pattern",       # Patterns discovered/applied
    "bugfix",        # Bugs found and how they were fixed
    "gotcha",        # Things that were tricky/unexpected
    "feature",       # Features implemented
    "implementation" # How something was built
]


def load_transcript(transcript_path):
    """Load session transcript from JSONL file."""
    messages = []
    path = Path(transcript_path)

    if not path.exists():
        return messages

    with open(path, 'r') as f:
        for line in f:
            try:
                msg = json.loads(line.strip())
                messages.append(msg)
            except:
                continue

    return messages


def load_tool_results(session_id):
    """Load buffered tool results for this session."""
    buffer_file = Path(f"/tmp/claude-session-{session_id}/tool_results.jsonl")
    results = []

    if buffer_file.exists():
        with open(buffer_file, 'r') as f:
            for line in f:
                try:
                    results.append(json.loads(line.strip()))
                except:
                    continue

    return results


def extract_session_summary(messages, tool_results):
    """Extract a summary of what happened in the session."""
    summary = {
        "user_requests": [],
        "files_created": [],
        "files_modified": [],
        "commands_run": [],
        "agents_used": [],
        "errors": []
    }

    for msg in messages:
        msg_type = msg.get("type", "")

        if msg_type == "human":
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip():
                # Skip system messages
                if not content.startswith("<system"):
                    summary["user_requests"].append(content[:200])

        # Parse assistant tool calls from the transcript
        elif msg_type == "assistant":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})

                        if tool_name == "Write":
                            file_path = tool_input.get("file_path", "")
                            if file_path:
                                summary["files_created"].append(file_path)

                        elif tool_name == "Edit":
                            file_path = tool_input.get("file_path", "")
                            if file_path and file_path not in summary["files_modified"]:
                                summary["files_modified"].append(file_path)

                        elif tool_name == "Bash":
                            cmd = tool_input.get("command", "")[:100]
                            desc = tool_input.get("description", cmd[:50])
                            if desc:
                                summary["commands_run"].append(desc)

                        elif tool_name == "Task":
                            desc = tool_input.get("description", "")
                            agent_type = tool_input.get("subagent_type", "")
                            if desc:
                                summary["agents_used"].append(f"{agent_type}: {desc}")

        # Also check for tool_result messages for errors
        elif msg_type == "tool_result":
            content = msg.get("content", "")
            if isinstance(content, str) and "error" in content.lower():
                summary["errors"].append(content[:100])

    # Also use tool_results buffer if available (legacy support)
    for result in tool_results:
        tool = result.get("tool", "")

        if tool == "Write":
            file_path = result.get("file", "")
            if file_path and file_path not in summary["files_created"]:
                summary["files_created"].append(file_path)
        elif tool == "Edit":
            file_path = result.get("file", "")
            if file_path and file_path not in summary["files_modified"]:
                summary["files_modified"].append(file_path)
        elif tool == "Bash":
            cmd = result.get("summary", "")
            if cmd and cmd not in summary["commands_run"]:
                summary["commands_run"].append(cmd)
        elif tool == "Task":
            task = result.get("summary", "")
            if task and task not in summary["agents_used"]:
                summary["agents_used"].append(task)

        if not result.get("success", True):
            summary["errors"].append(result.get("summary", ""))

    return summary


def generate_extraction_prompt(summary, tool_results):
    """Generate prompt for observation extraction."""
    # Build context from summary
    context_parts = []

    if summary["user_requests"]:
        context_parts.append(f"USER REQUESTS:\n" + "\n".join(f"- {r}" for r in summary["user_requests"][:5]))

    if summary["files_created"]:
        context_parts.append(f"FILES CREATED:\n" + "\n".join(f"- {f}" for f in summary["files_created"][:10]))

    if summary["files_modified"]:
        context_parts.append(f"FILES MODIFIED:\n" + "\n".join(f"- {f}" for f in summary["files_modified"][:10]))

    if summary["commands_run"]:
        context_parts.append(f"COMMANDS:\n" + "\n".join(f"- {c}" for c in summary["commands_run"][:5]))

    if summary["errors"]:
        context_parts.append(f"ERRORS ENCOUNTERED:\n" + "\n".join(f"- {e}" for e in summary["errors"][:5]))

    context = "\n\n".join(context_parts)

    return f"""Analyze this coding session and extract key observations.

SESSION CONTEXT:
{context}

Extract observations into these categories:
- decision: Technical choices made (e.g., "Used PID file locking to prevent duplicate processes")
- pattern: Patterns discovered/applied (e.g., "React components follow PascalCase naming")
- bugfix: Bugs fixed (e.g., "Fixed memory leak by cleaning up event listeners")
- gotcha: Tricky/unexpected things (e.g., "SQLite requires explicit commit in WAL mode")
- feature: Features implemented (e.g., "Added session memory with observation extraction")
- implementation: How something was built (e.g., "Hook captures PostToolUse events to buffer file")

Respond with ONLY a JSON array of observations:
[{{"category": "decision|pattern|bugfix|gotcha|feature|implementation", "observation": "brief description", "files": ["related/file.js"]}}]

If no meaningful observations, return: []"""


def extract_with_mlx(model, tokenizer, prompt):
    """Extract observations using MLX model."""
    response = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=800,
        temp=0.2
    )

    # Parse JSON from response
    try:
        import re
        # Find JSON array in response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            observations = json.loads(json_match.group())
            # Validate structure
            valid = []
            for obs in observations:
                if isinstance(obs, dict) and "category" in obs and "observation" in obs:
                    if obs["category"] in OBSERVATION_CATEGORIES:
                        valid.append(obs)
            return valid
    except Exception as e:
        print(f"Warning: Failed to parse MLX response: {e}")

    return []


def extract_simple(summary):
    """Simple rule-based extraction when MLX is not available."""
    observations = []

    # Extract from files created
    for f in summary["files_created"]:
        observations.append({
            "category": "implementation",
            "observation": f"Created file: {f}",
            "files": [f]
        })

    # Extract from files modified
    for f in summary["files_modified"]:
        observations.append({
            "category": "implementation",
            "observation": f"Modified file: {f}",
            "files": [f]
        })

    # Extract from errors (potential bugfixes)
    for e in summary["errors"]:
        observations.append({
            "category": "bugfix",
            "observation": f"Encountered issue: {e}",
            "files": []
        })

    # Extract from commands run
    for c in summary["commands_run"]:
        if c and len(c) > 10:  # Skip trivial commands
            observations.append({
                "category": "implementation",
                "observation": f"Command: {c[:100]}",
                "files": []
            })

    # Extract from agents used
    for a in summary["agents_used"]:
        if a:
            observations.append({
                "category": "feature",
                "observation": f"Used agent: {a[:100]}",
                "files": []
            })

    # Extract from user requests - summarize what was worked on
    if summary["user_requests"]:
        # Take the first substantial request as a feature summary
        for req in summary["user_requests"][:3]:
            if req and len(req) > 20:
                observations.append({
                    "category": "feature",
                    "observation": f"Worked on: {req[:150]}",
                    "files": []
                })
                break

    return observations


def save_observations(observations, project_id, session_id, session_summary):
    """Save observations to global and per-project stores."""
    timestamp = datetime.utcnow().isoformat() + "Z"

    # Enrich observations with metadata
    for obs in observations:
        obs["sessionId"] = session_id
        obs["projectId"] = project_id
        obs["timestamp"] = timestamp

    # Update global observations
    global_obs_path = MEMORY_ROOT / "sessions" / "observations.json"
    try:
        global_obs = json.loads(global_obs_path.read_text())
    except:
        global_obs = {"version": "1.0", "lastUpdated": None, "observations": []}

    global_obs["observations"].extend(observations)
    global_obs["lastUpdated"] = timestamp
    global_obs_path.write_text(json.dumps(global_obs, indent=2))

    # Update per-project observations if project exists
    if project_id:
        project_obs_path = MEMORY_ROOT / "projects" / project_id / "observations.json"
        project_obs_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            project_obs = json.loads(project_obs_path.read_text())
        except:
            project_obs = {"version": "1.0", "lastUpdated": None, "observations": []}

        project_obs["observations"].extend(observations)
        project_obs["lastUpdated"] = timestamp
        project_obs_path.write_text(json.dumps(project_obs, indent=2))

    # Update global session index
    index_path = MEMORY_ROOT / "sessions" / "index.json"
    try:
        index = json.loads(index_path.read_text())
    except:
        index = {"version": "1.0", "lastUpdated": None, "sessions": []}

    session_entry = {
        "sessionId": session_id,
        "projectId": project_id,
        "timestamp": timestamp,
        "observationCount": len(observations),
        "summary": session_summary["user_requests"][0][:100] if session_summary["user_requests"] else "No summary"
    }

    index["sessions"].append(session_entry)
    index["lastUpdated"] = timestamp

    # Keep only last 100 sessions in index
    index["sessions"] = index["sessions"][-100:]
    index_path.write_text(json.dumps(index, indent=2))

    # Auto-populate decisions.json
    decisions = [o for o in observations if o["category"] == "decision"]
    if decisions and project_id:
        decisions_path = MEMORY_ROOT / "projects" / project_id / "decisions.json"
        try:
            existing = json.loads(decisions_path.read_text())
        except:
            existing = {"decisions": [], "lastUpdated": None}

        for d in decisions:
            existing["decisions"].append({
                "decision": d["observation"],
                "timestamp": timestamp,
                "sessionId": session_id,
                "files": d.get("files", [])
            })

        existing["lastUpdated"] = timestamp
        decisions_path.write_text(json.dumps(existing, indent=2))

    return len(observations)


def main():
    parser = argparse.ArgumentParser(description="Extract observations from session")
    parser.add_argument("transcript_path", help="Path to session transcript JSONL")
    parser.add_argument("project_id", help="Project ID")
    parser.add_argument("--session-id", default="unknown", help="Session ID")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="MLX model to use")
    parser.add_argument("--no-mlx", action="store_true", help="Skip MLX, use simple extraction")
    args = parser.parse_args()

    print(f"Extracting observations for session {args.session_id}...")

    # Load data
    messages = load_transcript(args.transcript_path)
    tool_results = load_tool_results(args.session_id)

    print(f"  Loaded {len(messages)} messages, {len(tool_results)} tool results")

    # Build summary
    summary = extract_session_summary(messages, tool_results)

    # Extract observations
    observations = []

    if HAS_MLX and not args.no_mlx:
        try:
            print(f"  Loading MLX model: {args.model}")
            model, tokenizer = load(args.model)

            prompt = generate_extraction_prompt(summary, tool_results)
            observations = extract_with_mlx(model, tokenizer, prompt)
            print(f"  MLX extracted {len(observations)} observations")
        except Exception as e:
            print(f"  MLX extraction failed: {e}")
            observations = extract_simple(summary)
    else:
        observations = extract_simple(summary)
        print(f"  Simple extraction: {len(observations)} observations")

    # Save
    if observations:
        saved = save_observations(observations, args.project_id, args.session_id, summary)
        print(f"  Saved {saved} observations")
    else:
        print("  No observations to save")

    # Output observations for caller
    print(json.dumps(observations, indent=2))


if __name__ == "__main__":
    main()
