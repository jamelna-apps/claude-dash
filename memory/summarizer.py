#!/usr/bin/env python3
"""
Session Summarizer

Generates concise summaries of sessions for future context loading.
Uses Ollama for intelligent summarization.

Output stored in: ~/.claude-dash/sessions/summaries/{project_id}.json
"""

import json
import sys
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

MEMORY_ROOT = Path.home() / ".claude-dash"
SUMMARIES_DIR = MEMORY_ROOT / "sessions" / "summaries"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:7b"


def load_transcript(transcript_path):
    """Load session transcript."""
    messages = []
    path = Path(transcript_path)

    if not path.exists():
        return messages

    with open(path, 'r') as f:
        for line in f:
            try:
                msg = json.loads(line.strip())
                messages.append(msg)
            except (json.JSONDecodeError, ValueError):
                continue  # Skip malformed JSON lines

    return messages


def extract_conversation_content(messages):
    """Extract key content from conversation."""
    user_messages = []
    assistant_summaries = []
    files_touched = set()
    tools_used = set()

    for msg in messages:
        msg_type = msg.get("type", "")

        if msg_type == "human":
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip():
                if not content.startswith("<system"):
                    user_messages.append(content[:300])

        elif msg_type == "assistant":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text = block.get("text", "")[:200]
                            if text and len(text) > 30:
                                assistant_summaries.append(text)

                        elif block.get("type") == "tool_use":
                            tool_name = block.get("name", "")
                            tools_used.add(tool_name)

                            tool_input = block.get("input", {})
                            if tool_name in ["Write", "Edit", "Read"]:
                                fp = tool_input.get("file_path", "")
                                if fp:
                                    files_touched.add(Path(fp).name)

    return {
        "user_messages": user_messages,
        "assistant_summaries": assistant_summaries[:10],
        "files_touched": list(files_touched)[:10],
        "tools_used": list(tools_used)
    }


def generate_summary_with_ollama(content):
    """Use Ollama to generate a concise session summary."""

    # Build context
    context_parts = []

    if content["user_messages"]:
        context_parts.append("USER REQUESTS:\n" + "\n".join(f"- {m[:100]}" for m in content["user_messages"][:5]))

    if content["files_touched"]:
        context_parts.append(f"FILES WORKED ON: {', '.join(content['files_touched'][:8])}")

    if content["tools_used"]:
        context_parts.append(f"TOOLS USED: {', '.join(content['tools_used'][:8])}")

    context = "\n\n".join(context_parts)

    if not context.strip():
        return None

    prompt = f"""Summarize this coding session in 1-2 sentences. Focus on WHAT was accomplished, not the process.

SESSION:
{context}

Write a brief summary (1-2 sentences) that would help someone understand what was done.
Example: "Set up Docker Ollama integration and configured RAG system for document queries."

Summary:"""

    try:
        data = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 100}
        }).encode('utf-8')

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            summary = result.get("response", "").strip()

            # Clean up common artifacts
            summary = summary.replace("Summary:", "").strip()
            summary = summary.split("\n")[0]  # Take first line only

            return summary if len(summary) > 10 else None

    except Exception as e:
        print(f"Ollama summarization failed: {e}", file=sys.stderr)
        return None


def generate_simple_summary(content):
    """Fallback simple summary."""
    parts = []

    if content["user_messages"]:
        first_request = content["user_messages"][0][:80]
        parts.append(f"Worked on: {first_request}")

    if content["files_touched"]:
        parts.append(f"Files: {', '.join(content['files_touched'][:3])}")

    return ". ".join(parts) if parts else "Session with no significant changes."


def save_summary(project_id, session_id, summary, content):
    """Save summary to file."""
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)

    summary_file = SUMMARIES_DIR / f"{project_id}.json"

    # Load existing summaries
    try:
        existing = json.loads(summary_file.read_text())
    except (json.JSONDecodeError, FileNotFoundError, IOError):
        existing = {"project_id": project_id, "summaries": []}

    # Add new summary
    existing["summaries"].append({
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "summary": summary,
        "files_touched": content.get("files_touched", []),
        "tools_used": content.get("tools_used", [])
    })

    # Keep only last 20 summaries
    existing["summaries"] = existing["summaries"][-20:]
    existing["last_updated"] = datetime.now(timezone.utc).isoformat() + "Z"
    existing["summary"] = summary  # Current summary for quick access

    summary_file.write_text(json.dumps(existing, indent=2))

    return summary


def summarize_session(transcript_path, project_id, session_id="unknown"):
    """Main function to summarize a session."""
    print(f"[Summarizer] Generating summary for session {session_id}...")

    messages = load_transcript(transcript_path)
    if len(messages) < 3:
        print("  Too few messages, skipping summary")
        return None

    content = extract_conversation_content(messages)
    print(f"  Found {len(content['user_messages'])} user messages, {len(content['files_touched'])} files")

    # Try Ollama first
    summary = generate_summary_with_ollama(content)

    if summary:
        print(f"  Ollama summary: {summary[:80]}...")
    else:
        summary = generate_simple_summary(content)
        print(f"  Simple summary: {summary[:80]}...")

    # Save
    save_summary(project_id, session_id, summary, content)
    print(f"  Saved to summaries/{project_id}.json")

    return summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Summarize a session")
    parser.add_argument("transcript_path", help="Path to session transcript")
    parser.add_argument("project_id", help="Project ID")
    parser.add_argument("--session-id", default="unknown", help="Session ID")
    args = parser.parse_args()

    summary = summarize_session(args.transcript_path, args.project_id, args.session_id)
    if summary:
        print(f"\nSummary: {summary}")


if __name__ == "__main__":
    main()
