#!/usr/bin/env python3
"""
Transcript Compactor

Synthesizes session transcripts into compact digests before cleanup.
Preserves: decisions, patterns, file changes, key exchanges, observations.
Removes: verbose tool outputs, redundant text, system messages.

Usage:
  python transcript_compactor.py --compact-all --keep 10
  python transcript_compactor.py --compact /path/to/transcript.jsonl
"""

import json
import sys
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

MEMORY_ROOT = Path.home() / ".claude-dash"
TRANSCRIPTS_DIR = MEMORY_ROOT / "sessions" / "transcripts"
DIGESTS_DIR = MEMORY_ROOT / "sessions" / "digests"
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:7b"

# Target compression: ~50KB per digest (vs ~10MB+ per transcript)
MAX_DIGEST_SIZE = 50000


def load_transcript(path):
    """Load and parse transcript JSONL."""
    messages = []
    with open(path, 'r') as f:
        for line in f:
            try:
                msg = json.loads(line.strip())
                messages.append(msg)
            except (json.JSONDecodeError, ValueError):
                continue  # Skip malformed JSON lines
    return messages


def extract_user_requests(messages):
    """Extract user messages (the actual requests)."""
    requests = []
    for msg in messages:
        if msg.get("type") == "human":
            content = msg.get("message", {}).get("content", "")
            if isinstance(content, str) and content.strip():
                # Skip system injections
                if not content.startswith("<") and len(content) > 5:
                    requests.append({
                        "text": content[:500],  # Truncate long messages
                        "timestamp": msg.get("timestamp", "")
                    })
    return requests


def extract_file_operations(messages):
    """Extract file reads, writes, and edits."""
    operations = defaultdict(list)

    for msg in messages:
        if msg.get("type") != "assistant":
            continue

        content = msg.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue

            tool = block.get("name", "")
            input_data = block.get("input", {})

            if tool == "Read":
                fp = input_data.get("file_path", "")
                if fp:
                    operations["read"].append(Path(fp).name)

            elif tool == "Write":
                fp = input_data.get("file_path", "")
                if fp:
                    operations["created"].append(Path(fp).name)

            elif tool == "Edit":
                fp = input_data.get("file_path", "")
                old = input_data.get("old_string", "")[:100]
                new = input_data.get("new_string", "")[:100]
                if fp:
                    operations["edited"].append({
                        "file": Path(fp).name,
                        "change": f"{old[:50]}... → {new[:50]}..."
                    })

            elif tool == "Bash":
                cmd = input_data.get("command", "")[:200]
                if cmd and not cmd.startswith("cat "):
                    operations["commands"].append(cmd)

    # Deduplicate
    operations["read"] = list(set(operations["read"]))[:20]
    operations["created"] = list(set(operations["created"]))[:20]
    operations["commands"] = list(set(operations["commands"]))[:15]

    return dict(operations)


def extract_key_responses(messages):
    """Extract key assistant explanations and decisions."""
    responses = []

    for msg in messages:
        if msg.get("type") != "assistant":
            continue

        content = msg.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue

        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                # Look for substantive explanations (not just "Let me...")
                if len(text) > 100 and not text.startswith("Let me"):
                    # Extract first meaningful paragraph
                    paragraphs = text.split("\n\n")
                    for p in paragraphs:
                        if len(p) > 80 and not p.startswith("<") and not p.startswith("```"):
                            responses.append(p[:300])
                            break

    return responses[:10]  # Keep top 10 substantive responses


def extract_errors_and_fixes(messages):
    """Extract error messages and their resolutions."""
    errors = []

    for i, msg in enumerate(messages):
        if msg.get("type") != "tool_result":
            continue

        content = str(msg.get("content", ""))

        # Look for error indicators
        if any(term in content.lower() for term in ["error", "failed", "exception", "traceback"]):
            error_snippet = content[:300]

            # Look for fix in next few messages
            fix = None
            for j in range(i+1, min(i+5, len(messages))):
                next_msg = messages[j]
                if next_msg.get("type") == "assistant":
                    next_content = next_msg.get("message", {}).get("content", [])
                    if isinstance(next_content, list):
                        for block in next_content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text = block.get("text", "")
                                if "fix" in text.lower() or "solution" in text.lower():
                                    fix = text[:200]
                                    break

            errors.append({
                "error": error_snippet,
                "fix": fix
            })

    return errors[:5]


def generate_synthesis(user_requests, file_ops, responses, errors):
    """Use Ollama to synthesize a coherent session summary."""

    # Build context
    context_parts = []

    if user_requests:
        context_parts.append("USER REQUESTS:\n" + "\n".join(
            f"- {r['text'][:150]}" for r in user_requests[:8]
        ))

    if file_ops.get("created"):
        context_parts.append(f"FILES CREATED: {', '.join(file_ops['created'][:10])}")

    if file_ops.get("edited"):
        edits = [e["file"] for e in file_ops["edited"][:10]]
        context_parts.append(f"FILES EDITED: {', '.join(edits)}")

    if errors:
        context_parts.append("ERRORS ENCOUNTERED:\n" + "\n".join(
            f"- {e['error'][:100]}" for e in errors[:3]
        ))

    context = "\n\n".join(context_parts)

    if not context.strip():
        return None

    prompt = f"""Analyze this coding session and create a comprehensive summary.
Include: what was accomplished, key decisions made, problems solved, and any patterns or learnings.

SESSION DATA:
{context}

Write a detailed but concise summary (3-5 paragraphs) that captures the essential context someone would need to continue this work. Focus on WHAT and WHY, not step-by-step process.

Summary:"""

    try:
        data = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 500}
        }).encode('utf-8')

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get("response", "").strip()

    except Exception as e:
        print(f"  Ollama synthesis failed: {e}", file=sys.stderr)
        return None


def create_digest(transcript_path):
    """Create a compact digest from a transcript."""
    print(f"  Processing: {transcript_path.name}")

    messages = load_transcript(transcript_path)
    if len(messages) < 3:
        print(f"    Skipping (too few messages)")
        return None

    # Extract components
    user_requests = extract_user_requests(messages)
    file_ops = extract_file_operations(messages)
    responses = extract_key_responses(messages)
    errors = extract_errors_and_fixes(messages)

    print(f"    Found: {len(user_requests)} requests, {len(file_ops.get('edited', []))} edits, {len(errors)} errors")

    # Generate AI synthesis
    synthesis = generate_synthesis(user_requests, file_ops, responses, errors)

    # Build digest
    digest = {
        "source_transcript": transcript_path.name,
        "compacted_at": datetime.now(timezone.utc).isoformat(),
        "message_count": len(messages),
        "synthesis": synthesis,
        "user_requests": [r["text"] for r in user_requests[:10]],
        "files": {
            "read": file_ops.get("read", [])[:15],
            "created": file_ops.get("created", [])[:15],
            "edited": [e["file"] for e in file_ops.get("edited", [])][:15]
        },
        "commands": file_ops.get("commands", [])[:10],
        "key_responses": responses[:5],
        "errors_and_fixes": errors[:3]
    }

    return digest


def save_digest(digest, session_id):
    """Save digest to file."""
    DIGESTS_DIR.mkdir(parents=True, exist_ok=True)

    digest_path = DIGESTS_DIR / f"{session_id}.json"
    digest_path.write_text(json.dumps(digest, indent=2))

    size = digest_path.stat().st_size
    print(f"    Saved digest: {size/1024:.1f} KB")

    return digest_path


def compact_transcript(transcript_path):
    """Compact a single transcript."""
    transcript_path = Path(transcript_path)

    if not transcript_path.exists():
        print(f"  Not found: {transcript_path}")
        return None

    original_size = transcript_path.stat().st_size
    session_id = transcript_path.stem

    # Check if already compacted
    digest_path = DIGESTS_DIR / f"{session_id}.json"
    if digest_path.exists():
        print(f"  Already compacted: {session_id}")
        return digest_path

    # Create digest
    digest = create_digest(transcript_path)
    if not digest:
        return None

    # Save digest
    saved_path = save_digest(digest, session_id)

    # Calculate savings
    new_size = saved_path.stat().st_size
    savings = (1 - new_size / original_size) * 100
    print(f"    Compression: {original_size/1024:.0f} KB → {new_size/1024:.1f} KB ({savings:.0f}% reduction)")

    return saved_path


def compact_all(keep_recent=10, delete_originals=True):
    """Compact all transcripts except the N most recent."""
    if not TRANSCRIPTS_DIR.exists():
        print("No transcripts directory found")
        return

    # Get all transcripts sorted by modification time
    transcripts = sorted(
        TRANSCRIPTS_DIR.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    print(f"Found {len(transcripts)} transcripts")
    print(f"Keeping {keep_recent} most recent, compacting the rest\n")

    # Keep recent, compact older
    to_compact = transcripts[keep_recent:]

    if not to_compact:
        print("Nothing to compact")
        return

    total_original = 0
    total_compacted = 0
    deleted_count = 0

    for transcript in to_compact:
        original_size = transcript.stat().st_size
        total_original += original_size

        digest_path = compact_transcript(transcript)

        if digest_path:
            # FIXED: Validate digest before deleting original
            try:
                digest_size = digest_path.stat().st_size
                total_compacted += digest_size

                if delete_originals:
                    # Additional validation: ensure digest is valid JSON and has content
                    if digest_size < 50:  # Minimum reasonable digest size
                        print(f"    ⚠ Digest too small ({digest_size} bytes), keeping original")
                        continue

                    # Verify digest is readable
                    try:
                        with open(digest_path) as f:
                            digest_data = json.load(f)
                            if not digest_data.get('synthesis') and not digest_data.get('observations'):
                                print(f"    ⚠ Digest missing content, keeping original")
                                continue
                    except (json.JSONDecodeError, IOError) as e:
                        print(f"    ⚠ Digest validation failed: {e}, keeping original")
                        continue

                    transcript.unlink()
                    deleted_count += 1
                    print(f"    Deleted original transcript")
            except OSError as e:
                print(f"    ⚠ Error accessing digest: {e}")

        print()

    # Summary
    print("=" * 50)
    print(f"Compacted: {len(to_compact)} transcripts")
    print(f"Original size: {total_original / 1024 / 1024:.1f} MB")
    print(f"Digest size: {total_compacted / 1024 / 1024:.1f} MB")
    print(f"Space saved: {(total_original - total_compacted) / 1024 / 1024:.1f} MB")
    if delete_originals:
        print(f"Deleted: {deleted_count} original transcripts")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Compact session transcripts")
    parser.add_argument("--compact", help="Compact a specific transcript")
    parser.add_argument("--compact-all", action="store_true", help="Compact all old transcripts")
    parser.add_argument("--keep", type=int, default=10, help="Keep N most recent transcripts (default: 10)")
    parser.add_argument("--no-delete", action="store_true", help="Don't delete originals after compacting")
    args = parser.parse_args()

    if args.compact:
        compact_transcript(args.compact)
    elif args.compact_all:
        compact_all(keep_recent=args.keep, delete_originals=not args.no_delete)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
