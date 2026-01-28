#!/usr/bin/env python3
"""
Roadmap Tracker - Analyzes session transcripts to detect completed tasks and update roadmaps.

Run at session end to:
1. Extract completed work from transcript
2. Match against roadmap tasks
3. Update task statuses
4. Log progress for weekly digest
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"


def load_transcript(transcript_path: str) -> list:
    """Load and parse JSONL transcript."""
    messages = []
    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    msg = json.loads(line.strip())
                    messages.append(msg)
                except json.JSONDecodeError:
                    continue
    except (IOError, FileNotFoundError):
        pass
    return messages


def extract_assistant_content(messages: list) -> str:
    """Extract all assistant messages as text."""
    content_parts = []
    for msg in messages:
        if msg.get("type") == "assistant":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        content_parts.append(block.get("text", ""))
            elif isinstance(content, str):
                content_parts.append(content)
    return "\n".join(content_parts)


def extract_completed_signals(text: str) -> list:
    """Extract signals that indicate task completion."""
    signals = []

    # Patterns that indicate completion
    completion_patterns = [
        r"(?:completed|finished|done|implemented|added|created|fixed|built|deployed)\s+([^.!?\n]{10,100})",
        r"(?:successfully|now)\s+(?:completed|working|implemented|deployed)\s+([^.!?\n]{10,100})",
        r"(?:task|feature|item)\s+['\"]([^'\"]+)['\"]\s+(?:is\s+)?(?:completed|done|finished)",
        r"marked\s+['\"]?([^'\"]+)['\"]?\s+as\s+completed",
        r"✓\s+([^.!?\n]{10,80})",
        r"\[completed\]\s+([^.!?\n]{10,80})",
    ]

    for pattern in completion_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        signals.extend(matches)

    # Also look for TodoWrite completions
    todo_completed_pattern = r'"status":\s*"completed"[^}]*"content":\s*"([^"]+)"'
    matches = re.findall(todo_completed_pattern, text)
    signals.extend(matches)

    return list(set(signals))


def match_task_to_roadmap(signal: str, roadmap: dict) -> dict | None:
    """Try to match a completion signal to a roadmap task."""
    signal_lower = signal.lower()
    signal_words = set(signal_lower.split())

    # Check current sprint items
    for item in roadmap.get("currentSprint", {}).get("items", []):
        title_lower = item.get("title", "").lower()
        title_words = set(title_lower.split())

        # Check for word overlap
        overlap = len(signal_words & title_words)
        if overlap >= 2 or signal_lower in title_lower or title_lower in signal_lower:
            return {"source": "sprint", "item": item}

    # Check backlog items
    for timeframe in ["shortTerm", "mediumTerm", "longTerm"]:
        items = roadmap.get("backlog", {}).get(timeframe, {}).get("items", [])
        for item in items:
            title_lower = item.get("title", "").lower()
            title_words = set(title_lower.split())

            overlap = len(signal_words & title_words)
            if overlap >= 2 or signal_lower in title_lower or title_lower in signal_lower:
                return {"source": f"backlog.{timeframe}", "item": item}

    return None


def update_roadmap(roadmap_path: str, updates: list) -> bool:
    """Apply updates to roadmap file."""
    try:
        with open(roadmap_path) as f:
            roadmap = json.load(f)

        modified = False

        for update in updates:
            source = update["source"]
            item_id = update["item"].get("id")

            if source == "sprint":
                for item in roadmap.get("currentSprint", {}).get("items", []):
                    if item.get("id") == item_id and item.get("status") != "completed":
                        item["status"] = "completed"
                        # Move to recently completed
                        roadmap.setdefault("recentlyCompleted", []).insert(0, {
                            "item": item["title"],
                            "completedDate": datetime.now().strftime("%Y-%m-%d"),
                            "version": roadmap.get("currentVersion", "?")
                        })
                        modified = True

            elif source.startswith("backlog."):
                timeframe = source.split(".")[1]
                items = roadmap.get("backlog", {}).get(timeframe, {}).get("items", [])
                for item in items:
                    if item.get("id") == item_id and item.get("status") != "completed":
                        item["status"] = "completed"
                        roadmap.setdefault("recentlyCompleted", []).insert(0, {
                            "item": item["title"],
                            "completedDate": datetime.now().strftime("%Y-%m-%d"),
                            "version": roadmap.get("currentVersion", "?")
                        })
                        modified = True

        if modified:
            roadmap["lastUpdated"] = datetime.now().isoformat()
            # Keep only last 10 recently completed
            roadmap["recentlyCompleted"] = roadmap.get("recentlyCompleted", [])[:10]

            with open(roadmap_path, "w") as f:
                json.dump(roadmap, f, indent=2)

        return modified

    except (json.JSONDecodeError, IOError) as e:
        print(f"Error updating roadmap: {e}", file=sys.stderr)
        return False


def log_progress(project_id: str, updates: list, detected_signals: list):
    """Log progress for weekly digest."""
    progress_log = MEMORY_ROOT / "logs" / "roadmap-progress.jsonl"

    entry = {
        "timestamp": datetime.now().isoformat(),
        "project": project_id,
        "detected_signals": detected_signals,
        "matched_tasks": [u["item"].get("title") for u in updates],
        "auto_completed": len(updates)
    }

    try:
        with open(progress_log, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except IOError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Track roadmap progress from session transcripts")
    parser.add_argument("--transcript", required=True, help="Path to transcript file")
    parser.add_argument("--project", required=True, help="Project ID")
    parser.add_argument("--roadmap", required=True, help="Path to roadmap.json")
    parser.add_argument("--dry-run", action="store_true", help="Don't modify files")

    args = parser.parse_args()

    # Load transcript
    messages = load_transcript(args.transcript)
    if not messages:
        print("No messages found in transcript")
        return

    # Extract assistant content
    content = extract_assistant_content(messages)
    if not content:
        print("No assistant content found")
        return

    # Extract completion signals
    signals = extract_completed_signals(content)
    if not signals:
        print("No completion signals detected")
        return

    print(f"Detected {len(signals)} completion signal(s)")

    # Load roadmap
    try:
        with open(args.roadmap) as f:
            roadmap = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading roadmap: {e}")
        return

    # Match signals to roadmap tasks
    updates = []
    for signal in signals:
        match = match_task_to_roadmap(signal, roadmap)
        if match:
            print(f"  Matched: '{signal}' -> {match['item'].get('title')}")
            updates.append(match)

    if not updates:
        print("No roadmap tasks matched")
        log_progress(args.project, [], signals)
        return

    # Apply updates
    if args.dry_run:
        print(f"Would update {len(updates)} task(s) (dry run)")
    else:
        if update_roadmap(args.roadmap, updates):
            print(f"Updated {len(updates)} task(s) in roadmap")
        else:
            print("No changes made to roadmap")

    # Log progress
    log_progress(args.project, updates, signals)


if __name__ == "__main__":
    main()
