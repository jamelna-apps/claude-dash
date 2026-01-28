#!/usr/bin/env python3
"""
Reasoning Chains for Claude-Dash Learning System

Captures the full cognitive journey: observations → hypotheses → discoveries → resolutions.
Unlike reasoning_bank (which stores problem→solution mappings), this captures the WHY.

Usage:
    python reasoning_chains.py capture '{"trigger":"...", "steps":[...], "conclusion":"...", "outcome":"success"}'
    python reasoning_chains.py recall "current problem context" --domain docker --limit 5
    python reasoning_chains.py stats
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional
import hashlib
import argparse

MEMORY_ROOT = Path.home() / ".claude-dash"
LEARNING_DIR = MEMORY_ROOT / "learning"
CHAINS_FILE = LEARNING_DIR / "reasoning_chains.json"


def load_chains() -> Dict:
    """Load reasoning chains from disk."""
    if not CHAINS_FILE.exists():
        return {
            "version": "1.0",
            "chains": [],
            "lastUpdated": None
        }
    try:
        return json.loads(CHAINS_FILE.read_text())
    except Exception:
        return {"version": "1.0", "chains": [], "lastUpdated": None}


def save_chains(data: Dict):
    """Save reasoning chains to disk."""
    LEARNING_DIR.mkdir(parents=True, exist_ok=True)
    data["lastUpdated"] = datetime.now(timezone.utc).isoformat()
    CHAINS_FILE.write_text(json.dumps(data, indent=2))


def save_project_chain(project_id: str, chain: Dict):
    """Save chain to project-specific file."""
    project_dir = MEMORY_ROOT / "projects" / project_id
    project_file = project_dir / "reasoning_chains.json"

    if project_file.exists():
        try:
            data = json.loads(project_file.read_text())
        except Exception:
            data = {"version": "1.0", "chains": []}
    else:
        project_dir.mkdir(parents=True, exist_ok=True)
        data = {"version": "1.0", "chains": []}

    data["chains"].append(chain)
    # Keep last 200 per project
    if len(data["chains"]) > 200:
        data["chains"] = data["chains"][-200:]

    data["lastUpdated"] = datetime.now(timezone.utc).isoformat()
    project_file.write_text(json.dumps(data, indent=2))


def extract_key_terms(text: str) -> set:
    """Extract key terms from text for matching."""
    stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                 'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                 'can', 'need', 'to', 'of', 'in', 'for', 'on', 'with', 'at',
                 'by', 'from', 'as', 'into', 'that', 'this', 'it', 'its',
                 'and', 'but', 'or', 'not', 'no', 'yes', 'i', 'you', 'we'}
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    return {w for w in words if w not in stopwords}


def compute_similarity(text1: str, text2: str) -> float:
    """Compute Jaccard similarity between two texts."""
    terms1 = extract_key_terms(text1)
    terms2 = extract_key_terms(text2)
    if not terms1 or not terms2:
        return 0.0
    intersection = len(terms1 & terms2)
    union = len(terms1 | terms2)
    return intersection / union if union > 0 else 0.0


def capture_chain(chain_data: dict) -> dict:
    """
    Record a new reasoning chain.

    Args:
        chain_data: dict with keys:
          - trigger: What started this investigation
          - steps: List of {observation, interpretation, action?}
          - conclusion: Final decision/solution
          - outcome: success/partial/failure
          - domain: (optional) docker, auth, react, database, api, ui, performance, testing
          - project: (optional) Project ID
          - alternatives: (optional) List of {option, rejectedBecause}
          - constraints: (optional) List of strings
          - assumptions: (optional) List of strings
          - revisitWhen: (optional) List of strings
          - confidence: (optional) 0-1
    """
    chains = load_chains()

    # Generate unique ID
    chain_id = hashlib.md5(
        f"{chain_data['trigger']}_{datetime.now(timezone.utc).isoformat()}".encode()
    ).hexdigest()[:12]

    # Build chain record
    chain = {
        "id": chain_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "projectId": chain_data.get("project", "global"),
        "domain": chain_data.get("domain"),
        "trigger": chain_data["trigger"],
        "steps": chain_data["steps"],
        "conclusion": chain_data["conclusion"],
        "outcome": chain_data["outcome"],
        "alternatives": chain_data.get("alternatives", []),
        "constraints": chain_data.get("constraints", []),
        "assumptions": chain_data.get("assumptions", []),
        "revisitWhen": chain_data.get("revisitWhen", []),
        "confidence": chain_data.get("confidence", 0.8),
        "validated": False
    }

    chains["chains"].append(chain)

    # Keep last 500 chains globally
    if len(chains["chains"]) > 500:
        chains["chains"] = chains["chains"][-500:]

    save_chains(chains)

    # Also save to project-specific file if project specified
    if chain_data.get("project"):
        save_project_chain(chain_data["project"], chain)

    return {"captured": True, "id": chain_id}


def recall_chains(context: str, domain: str = None, project: str = None, limit: int = 5) -> List[Dict]:
    """
    Find relevant past reasoning chains.

    Uses term overlap scoring with bonuses for domain/project match.
    """
    chains = load_chains()

    # Also load project-specific chains if project specified
    all_chains = chains.get("chains", [])
    if project:
        project_file = MEMORY_ROOT / "projects" / project / "reasoning_chains.json"
        if project_file.exists():
            try:
                project_data = json.loads(project_file.read_text())
                # Deduplicate by ID
                existing_ids = {c["id"] for c in all_chains}
                for c in project_data.get("chains", []):
                    if c["id"] not in existing_ids:
                        all_chains.append(c)
            except Exception:
                pass

    if not all_chains:
        return []

    # Score chains by relevance
    scored = []
    context_terms = extract_key_terms(context)

    for chain in all_chains:
        score = 0.0

        # Domain match bonus
        if domain and chain.get("domain") == domain:
            score += 0.3

        # Project match bonus
        if project and chain.get("projectId") == project:
            score += 0.2

        # Trigger similarity
        trigger_terms = extract_key_terms(chain.get("trigger", ""))
        if trigger_terms and context_terms:
            trigger_overlap = len(context_terms & trigger_terms) / max(len(context_terms | trigger_terms), 1)
            score += trigger_overlap * 0.25

        # Conclusion similarity
        conclusion_terms = extract_key_terms(chain.get("conclusion", ""))
        if conclusion_terms and context_terms:
            conclusion_overlap = len(context_terms & conclusion_terms) / max(len(context_terms | conclusion_terms), 1)
            score += conclusion_overlap * 0.15

        # Steps similarity (check observation + interpretation text)
        steps_text = " ".join(
            f"{s.get('observation', '')} {s.get('interpretation', '')}"
            for s in chain.get("steps", [])
        )
        steps_terms = extract_key_terms(steps_text)
        if steps_terms and context_terms:
            steps_overlap = len(context_terms & steps_terms) / max(len(context_terms | steps_terms), 1)
            score += steps_overlap * 0.1

        # Successful outcomes preferred
        if chain.get("outcome") == "success":
            score += 0.05
        elif chain.get("outcome") == "failure":
            score -= 0.05

        # Validated chains preferred
        if chain.get("validated"):
            score += 0.05

        if score > 0.1:  # Minimum threshold
            scored.append({"chain": chain, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return [s["chain"] for s in scored[:limit]]


def format_for_injection(context: str, project: str = None, limit: int = 3) -> Optional[str]:
    """Format reasoning chains for context injection into prompts."""
    chains = recall_chains(context, project=project, limit=limit)

    if not chains:
        return None

    output = ["<past-reasoning-chains>"]
    for chain in chains:
        output.append(f"\n## {chain['trigger']}")
        output.append(f"**Conclusion:** {chain['conclusion']}")
        output.append("**Journey:**")
        for i, step in enumerate(chain.get("steps", []), 1):
            obs = step.get("observation", "")
            interp = step.get("interpretation", "")
            output.append(f"  {i}. {obs} → {interp}")
        if chain.get("revisitWhen"):
            output.append(f"**Revisit if:** {', '.join(chain['revisitWhen'])}")
        output.append("")

    output.append("</past-reasoning-chains>")
    return "\n".join(output)


def get_stats() -> Dict:
    """Get statistics about stored chains."""
    chains = load_chains()
    all_chains = chains.get("chains", [])

    # Count by domain
    by_domain = {}
    for c in all_chains:
        domain = c.get("domain") or "general"
        by_domain[domain] = by_domain.get(domain, 0) + 1

    # Count by outcome
    by_outcome = {}
    for c in all_chains:
        outcome = c.get("outcome", "unknown")
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1

    # Count by project
    by_project = {}
    for c in all_chains:
        proj = c.get("projectId", "global")
        by_project[proj] = by_project.get(proj, 0) + 1

    return {
        "total": len(all_chains),
        "byDomain": by_domain,
        "byOutcome": by_outcome,
        "byProject": by_project,
        "lastUpdated": chains.get("lastUpdated")
    }


def main():
    parser = argparse.ArgumentParser(description="Reasoning Chains")
    parser.add_argument("command", choices=["capture", "recall", "stats", "format"])
    parser.add_argument("data", nargs="?", help="JSON data (capture) or context string (recall/format)")
    parser.add_argument("--domain", "-d", help="Domain filter")
    parser.add_argument("--project", "-p", help="Project filter")
    parser.add_argument("--limit", "-l", type=int, default=5, help="Max results")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.command == "capture":
        if not args.data:
            print(json.dumps({"error": "JSON data required for capture"}))
            sys.exit(1)
        try:
            chain_data = json.loads(args.data)
            result = capture_chain(chain_data)
            print(json.dumps(result, indent=2))
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON: {e}"}))
            sys.exit(1)
        except KeyError as e:
            print(json.dumps({"error": f"Missing required field: {e}"}))
            sys.exit(1)

    elif args.command == "recall":
        if not args.data:
            print(json.dumps({"error": "Context string required for recall"}))
            sys.exit(1)
        chains = recall_chains(args.data, domain=args.domain, project=args.project, limit=args.limit)
        if args.json:
            print(json.dumps(chains, indent=2, default=str))
        else:
            if not chains:
                print("No relevant reasoning chains found.")
            else:
                print(f"=== Found {len(chains)} Relevant Chains ===")
                for i, chain in enumerate(chains, 1):
                    print(f"\n{i}. {chain['trigger']}")
                    print(f"   Conclusion: {chain['conclusion'][:100]}...")
                    print(f"   Steps: {len(chain.get('steps', []))}, Outcome: {chain.get('outcome', 'unknown')}")

    elif args.command == "format":
        if not args.data:
            print(json.dumps({"error": "Context string required for format"}))
            sys.exit(1)
        output = format_for_injection(args.data, project=args.project, limit=args.limit)
        if output:
            print(output)
        else:
            print("No relevant chains to inject.")

    elif args.command == "stats":
        stats = get_stats()
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
