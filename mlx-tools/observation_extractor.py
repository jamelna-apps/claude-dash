#!/usr/bin/env python3
"""
Observation Extractor for Claude Memory System

Extracts categorized observations from session transcripts using local Ollama.
Zero API token cost - uses native Ollama with Metal GPU.

Usage:
  python observation_extractor.py <transcript_path> <project_id> [--session-id ID]

Categories:
  - decision: Technical choices made
  - pattern: Patterns discovered/applied
  - bugfix: Bugs fixed
  - gotcha: Tricky/unexpected things
  - feature: Features implemented
  - implementation: How something was built
"""

import json
import os
import sys
import argparse
import urllib.request
import tempfile
from pathlib import Path
from datetime import datetime

# Use centralized config
try:
    from config import OLLAMA_URL, OLLAMA_CHAT_MODEL as OLLAMA_MODEL, MEMORY_ROOT
except ImportError:
    MEMORY_ROOT = Path.home() / ".claude-dash"
    OLLAMA_URL = "http://localhost:11434"
    OLLAMA_MODEL = "gemma3:4b"

# Import pattern detector for learning
sys.path.insert(0, str(MEMORY_ROOT / "patterns"))
try:
    from detector import track_user_phrase, detect_mode, analyze_session_patterns
    HAS_PATTERN_DETECTOR = True
except ImportError:
    HAS_PATTERN_DETECTOR = False

OBSERVATION_CATEGORIES = [
    "decision",
    "pattern",
    "bugfix",
    "gotcha",
    "feature",
    "implementation"
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
            except json.JSONDecodeError:
                continue  # Skip malformed lines

    return messages


def extract_session_summary(messages):
    """Extract a summary of what happened in the session."""
    summary = {
        "user_requests": [],
        "assistant_actions": [],
        "files_created": [],
        "files_modified": [],
        "commands_run": [],
        "errors": [],
        "key_exchanges": []
    }

    for i, msg in enumerate(messages):
        msg_type = msg.get("type", "")

        # Handle both "human" (old format) and "user" (current format)
        if msg_type in ("human", "user"):
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip():
                if not content.startswith("<system"):
                    summary["user_requests"].append(content[:300])
            # Handle list content (newer transcript format)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text and not text.startswith("<system"):
                            summary["user_requests"].append(text[:300])
                            break  # Only take first text block per message

        elif msg_type == "assistant":
            content = msg.get("message", {}).get("content", [])

            # Extract text responses
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text = block.get("text", "")[:200]
                            if text and not text.startswith("I'll") and len(text) > 50:
                                summary["assistant_actions"].append(text)

                        elif block.get("type") == "tool_use":
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
                                desc = tool_input.get("description", "")
                                cmd = tool_input.get("command", "")[:80]
                                summary["commands_run"].append(desc or cmd)

    # Build key exchanges (user request + what was done)
    for i, req in enumerate(summary["user_requests"][:5]):
        if i < len(summary["assistant_actions"]):
            summary["key_exchanges"].append({
                "request": req[:150],
                "action": summary["assistant_actions"][i][:150] if i < len(summary["assistant_actions"]) else ""
            })

    return summary


def call_ollama(prompt, model=OLLAMA_MODEL):
    """Call local Ollama for extraction."""
    try:
        data = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 1000
            }
        }).encode('utf-8')

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get("response", "")

    except Exception as e:
        print(f"Ollama error: {e}")
        return None


def extract_with_ollama(summary):
    """Extract observations using Ollama."""

    # Build context
    context_parts = []

    if summary["user_requests"]:
        context_parts.append("USER REQUESTS:\n" + "\n".join(f"- {r[:150]}" for r in summary["user_requests"][:5]))

    if summary["files_created"]:
        context_parts.append("FILES CREATED:\n" + "\n".join(f"- {f}" for f in summary["files_created"][:8]))

    if summary["files_modified"]:
        context_parts.append("FILES MODIFIED:\n" + "\n".join(f"- {f}" for f in summary["files_modified"][:8]))

    if summary["commands_run"]:
        context_parts.append("COMMANDS RUN:\n" + "\n".join(f"- {c}" for c in summary["commands_run"][:5]))

    if summary["key_exchanges"]:
        exchanges = "\n".join(f"- Request: {e['request']}\n  Action: {e['action']}" for e in summary["key_exchanges"][:3])
        context_parts.append(f"KEY EXCHANGES:\n{exchanges}")

    context = "\n\n".join(context_parts)

    if not context.strip():
        return []

    prompt = f"""Analyze this coding session and extract meaningful observations.

SESSION CONTEXT:
{context}

Extract observations into these categories:
- decision: Technical choices made with reasoning (e.g., "Chose native Ollama over Docker for Metal GPU acceleration")
- pattern: Patterns discovered/applied (e.g., "Use host.docker.internal for Docker containers to reach host services")
- bugfix: Bugs found and fixed (e.g., "Fixed Firebase error by mounting serviceAccountKey.json")
- gotcha: Tricky/unexpected things (e.g., "Docker containers can't use Metal GPU on Mac")
- feature: Features implemented (e.g., "Added doc_query tool to gateway for document RAG")
- implementation: How something was built (e.g., "Integrated AnythingLLM with claude-dash gateway via REST API")

IMPORTANT:
- Focus on DECISIONS and LEARNINGS, not just file operations
- Each observation should be useful for future sessions
- Skip trivial file edits unless they represent a significant change

Respond with ONLY a valid JSON array:
[{{"category": "decision", "observation": "brief description", "files": ["file.js"]}}]

If no meaningful observations, return: []"""

    response = call_ollama(prompt)

    if not response:
        return []

    # Parse JSON from response
    try:
        import re
        # Find JSON array in response
        json_match = re.search(r'\[[\s\S]*?\]', response)
        if json_match:
            observations = json.loads(json_match.group())
            # Validate structure
            valid = []
            for obs in observations:
                if isinstance(obs, dict) and "category" in obs and "observation" in obs:
                    if obs["category"] in OBSERVATION_CATEGORIES:
                        valid.append({
                            "category": obs["category"],
                            "observation": obs["observation"],
                            "files": obs.get("files", [])
                        })
            return valid
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"JSON parse error: {e}")

    return []


def extract_simple(summary):
    """Fallback simple extraction if Ollama fails."""
    observations = []

    # Only extract meaningful items
    if summary["files_created"]:
        observations.append({
            "category": "implementation",
            "observation": f"Created {len(summary['files_created'])} files: {', '.join(Path(f).name for f in summary['files_created'][:3])}",
            "files": summary["files_created"][:5]
        })

    if summary["files_modified"]:
        observations.append({
            "category": "implementation",
            "observation": f"Modified {len(summary['files_modified'])} files: {', '.join(Path(f).name for f in summary['files_modified'][:3])}",
            "files": summary["files_modified"][:5]
        })

    # Extract from first user request as feature summary
    if summary["user_requests"]:
        observations.append({
            "category": "feature",
            "observation": f"Worked on: {summary['user_requests'][0][:100]}",
            "files": []
        })

    return observations


def save_observations(observations, project_id, session_id, summary):
    """Save observations to memory stores."""
    if not observations:
        return 0

    timestamp = datetime.utcnow().isoformat() + "Z"

    # Enrich observations with metadata
    for obs in observations:
        obs["sessionId"] = session_id
        obs["projectId"] = project_id
        obs["timestamp"] = timestamp

    # Update global observations
    global_obs_path = MEMORY_ROOT / "sessions" / "observations.json"
    global_obs_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        global_obs = json.loads(global_obs_path.read_text())
    except (json.JSONDecodeError, IOError, FileNotFoundError):
        global_obs = {"version": "1.0", "lastUpdated": None, "observations": []}

    global_obs["observations"].extend(observations)
    global_obs["observations"] = global_obs["observations"][-500:]  # Keep last 500
    global_obs["lastUpdated"] = timestamp
    # Atomic write: write to temp file, then rename
    temp_path = global_obs_path.with_suffix('.tmp')
    temp_path.write_text(json.dumps(global_obs, indent=2))
    temp_path.rename(global_obs_path)

    # Update per-project observations
    if project_id and project_id != "unknown":
        project_obs_path = MEMORY_ROOT / "projects" / project_id / "observations.json"
        project_obs_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            project_obs = json.loads(project_obs_path.read_text())
        except (json.JSONDecodeError, IOError, FileNotFoundError):
            project_obs = {"version": "1.0", "lastUpdated": None, "observations": []}

        project_obs["observations"].extend(observations)
        project_obs["observations"] = project_obs["observations"][-200:]  # Keep last 200 per project
        project_obs["lastUpdated"] = timestamp
        # Atomic write
        temp_path = project_obs_path.with_suffix('.tmp')
        temp_path.write_text(json.dumps(project_obs, indent=2))
        temp_path.rename(project_obs_path)

    # Auto-populate decisions.json for decision-type observations
    decisions = [o for o in observations if o["category"] == "decision"]
    if decisions and project_id and project_id != "unknown":
        decisions_path = MEMORY_ROOT / "projects" / project_id / "decisions.json"
        try:
            existing = json.loads(decisions_path.read_text())
        except (json.JSONDecodeError, IOError, FileNotFoundError):
            existing = {"version": "1.0", "project": project_id, "lastUpdated": None, "decisions": []}

        for d in decisions:
            existing["decisions"].append({
                "decision": d["observation"],
                "timestamp": timestamp,
                "sessionId": session_id,
                "files": d.get("files", [])
            })

        existing["decisions"] = existing["decisions"][-50:]  # Keep last 50
        existing["lastUpdated"] = timestamp
        # Atomic write
        temp_path = decisions_path.with_suffix('.tmp')
        temp_path.write_text(json.dumps(existing, indent=2))
        temp_path.rename(decisions_path)

    # Update session index
    index_path = MEMORY_ROOT / "sessions" / "index.json"
    try:
        index = json.loads(index_path.read_text())
    except (json.JSONDecodeError, IOError, FileNotFoundError):
        index = {"version": "1.0", "lastUpdated": None, "sessions": []}

    session_entry = {
        "sessionId": session_id,
        "projectId": project_id,
        "timestamp": timestamp,
        "observationCount": len(observations),
        "categories": list(set(o["category"] for o in observations)),
        "summary": summary["user_requests"][0][:100] if summary["user_requests"] else "No summary"
    }

    index["sessions"].append(session_entry)
    index["sessions"] = index["sessions"][-100:]  # Keep last 100
    index["lastUpdated"] = timestamp
    # Atomic write
    temp_path = index_path.with_suffix('.tmp')
    temp_path.write_text(json.dumps(index, indent=2))
    temp_path.rename(index_path)

    return len(observations)


def learn_patterns_from_session(messages, observations, project_id):
    """Learn conversational patterns from session outcomes."""
    if not HAS_PATTERN_DETECTOR:
        return

    print("  Learning patterns from session...")

    # Analyze user messages and detect modes
    user_messages = []
    for msg in messages:
        if msg.get("type") == "human":
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip() and not content.startswith("<system"):
                user_messages.append(content[:300])

    # Track each user message with its detected mode
    for msg in user_messages[:10]:  # Limit to first 10 to avoid excessive processing
        try:
            detection = detect_mode(msg, use_ollama=False)
            mode = detection.get("primary_mode")
            if mode:
                # Session completed successfully, so track as positive outcome
                track_user_phrase(msg, mode, outcome=True)
        except Exception as e:
            pass  # Don't fail extraction if pattern learning fails

    # Learn from observation categories
    for obs in observations:
        category = obs.get("category")
        observation_text = obs.get("observation", "")

        # Map observation categories to modes for learning
        category_to_mode = {
            "decision": "infrastructure",
            "bugfix": "debugging",
            "feature": "feature",
            "implementation": "feature",
            "pattern": "refactor",
            "gotcha": "debugging"
        }

        if category in category_to_mode:
            # Find user messages that might relate to this observation
            for msg in user_messages[:5]:
                # Simple heuristic: if observation keywords appear in user message
                obs_words = set(observation_text.lower().split())
                msg_words = set(msg.lower().split())
                overlap = obs_words & msg_words
                if len(overlap) >= 3:
                    track_user_phrase(msg, category_to_mode[category], outcome=True)
                    break

    print(f"  Pattern learning complete")


def main():
    parser = argparse.ArgumentParser(description="Extract observations from session")
    parser.add_argument("transcript_path", help="Path to session transcript JSONL")
    parser.add_argument("project_id", help="Project ID")
    parser.add_argument("--session-id", default="unknown", help="Session ID")
    parser.add_argument("--no-mlx", action="store_true", help="Legacy flag, ignored")
    parser.add_argument("--lightweight", action="store_true",
                        help="Use simple extraction only (skip Ollama for speed)")
    parser.add_argument("--output", "-o", type=str,
                        help="Output checkpoint to specific file instead of observations.json")
    args = parser.parse_args()

    print(f"[Observation Extractor] Session: {args.session_id}")
    if args.lightweight:
        print("  Mode: lightweight (skipping Ollama)")

    # Load transcript
    messages = load_transcript(args.transcript_path)
    print(f"  Loaded {len(messages)} messages")

    if len(messages) < 3:
        print("  Too few messages, skipping extraction")
        # If output file specified, write empty checkpoint
        if args.output:
            Path(args.output).write_text(json.dumps({
                "observations": [],
                "files_modified": [],
                "message_count": len(messages)
            }, indent=2))
        return

    # Build summary
    summary = extract_session_summary(messages)
    print(f"  Found {len(summary['user_requests'])} user requests, {len(summary['files_modified'])} files modified")

    # Extract observations
    if args.lightweight:
        # Lightweight mode: skip Ollama, use simple extraction only
        observations = extract_simple(summary)
        print(f"  Simple extraction: {len(observations)} observations")
    else:
        # Full mode: try Ollama extraction first
        observations = extract_with_ollama(summary)
        if observations:
            print(f"  Ollama extracted {len(observations)} observations")
        else:
            print("  Ollama extraction failed, using simple extraction")
            observations = extract_simple(summary)
            print(f"  Simple extraction: {len(observations)} observations")

    # Handle output
    if args.output:
        # Write to checkpoint file instead of observations.json
        checkpoint_data = {
            "observations": observations,
            "files_modified": summary.get("files_modified", []),
            "files_created": summary.get("files_created", []),
            "commands_run": summary.get("commands_run", [])[:10],
            "user_requests": [r[:150] for r in summary.get("user_requests", [])[:5]],
            "message_count": len(messages)
        }
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(checkpoint_data, indent=2))
        print(f"  Wrote checkpoint to: {args.output}")

        # Print observations for log
        for obs in observations:
            print(f"    [{obs['category']}] {obs['observation'][:80]}")
    elif observations:
        # Normal mode: save to observations.json
        saved = save_observations(observations, args.project_id, args.session_id, summary)
        print(f"  Saved {saved} observations")

        # Print observations for log
        for obs in observations:
            print(f"    [{obs['category']}] {obs['observation'][:80]}")

        # Learn patterns from this session (skip in lightweight mode)
        if not args.lightweight:
            learn_patterns_from_session(messages, observations, args.project_id)
    else:
        print("  No observations to save")


if __name__ == "__main__":
    main()
