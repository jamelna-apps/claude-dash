#!/usr/bin/env python3
"""
ReasoningBank for Claude-Dash Learning System

Implements the RETRIEVE→JUDGE→DISTILL→CONSOLIDATE cycle from claude-flow:
1. RETRIEVE: Find similar past situations from corrections/decisions
2. JUDGE: Assess if past solution applies to current context
3. DISTILL: Extract generalizable patterns from specific instances
4. CONSOLIDATE: Update long-term memory with new patterns

This makes learning more systematic than just storing corrections.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional
from collections import defaultdict
import hashlib

MEMORY_ROOT = Path.home() / ".claude-dash"
LEARNING_DIR = MEMORY_ROOT / "learning"
REASONING_BANK_FILE = LEARNING_DIR / "reasoning_bank.json"


def load_reasoning_bank() -> Dict:
    """Load the reasoning bank."""
    if not REASONING_BANK_FILE.exists():
        return {
            "trajectories": [],
            "patterns": {},
            "confidence_scores": {},
            "last_consolidation": None
        }
    try:
        return json.loads(REASONING_BANK_FILE.read_text())
    except:
        return {"trajectories": [], "patterns": {}, "confidence_scores": {}}


def save_reasoning_bank(data: Dict):
    """Save the reasoning bank."""
    LEARNING_DIR.mkdir(parents=True, exist_ok=True)
    REASONING_BANK_FILE.write_text(json.dumps(data, indent=2))


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


# RETRIEVE: Find similar past situations
def retrieve_similar(context: str, domain: str = None, limit: int = 5) -> List[Dict]:
    """Find similar past learning trajectories."""
    bank = load_reasoning_bank()
    trajectories = bank.get("trajectories", [])
    if not trajectories:
        return []

    scored = []
    for traj in trajectories:
        if domain and traj.get("domain") != domain:
            continue
        traj_context = traj.get("context", "") + " " + traj.get("problem", "")
        similarity = compute_similarity(context, traj_context)
        if similarity > 0.1:
            scored.append({"trajectory": traj, "similarity": similarity})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:limit]


# JUDGE: Assess if past solution applies
def judge_applicability(past_trajectory: Dict, current_context: str,
                       current_domain: str = None) -> Dict:
    """Assess if a past solution applies to current situation."""
    past_context = past_trajectory.get("context", "")
    past_domain = past_trajectory.get("domain", "")
    domain_match = past_domain == current_domain if current_domain else True
    context_sim = compute_similarity(current_context, past_context)

    if domain_match and context_sim > 0.3:
        confidence = context_sim * 0.6 + (0.3 if domain_match else 0) + 0.1
        applicable = confidence > 0.4
    else:
        confidence = context_sim * 0.4
        applicable = False

    return {
        "applicable": applicable,
        "confidence": min(1.0, confidence),
        "domain_match": domain_match,
        "context_similarity": context_sim
    }


# DISTILL: Extract generalizable patterns
def distill_pattern(trajectories: List[Dict]) -> Optional[Dict]:
    """Extract a generalizable pattern from multiple trajectories."""
    if len(trajectories) < 2:
        return None

    # Use context OR problem text for trigger terms (fallback when context is empty)
    all_trigger_terms = []
    for t in trajectories:
        terms = extract_key_terms(t.get("context", ""))
        if not terms:  # Fallback to problem text
            terms = extract_key_terms(t.get("problem", ""))
        all_trigger_terms.append(terms)

    common_context = set.intersection(*all_trigger_terms) if all_trigger_terms and all(all_trigger_terms) else set()

    all_solution_terms = [extract_key_terms(t.get("solution", "")) for t in trajectories]
    common_solution = set.intersection(*all_solution_terms) if all_solution_terms and all(all_solution_terms) else set()

    if not common_context or not common_solution:
        return None

    domains = [t.get("domain") for t in trajectories if t.get("domain")]
    common_domain = domains[0] if domains and all(d == domains[0] for d in domains) else None

    pattern_key = f"{common_domain or 'general'}_{'-'.join(sorted(common_context)[:3])}"
    pattern_id = hashlib.md5(pattern_key.encode()).hexdigest()[:12]

    return {
        "id": pattern_id,
        "domain": common_domain,
        "trigger_terms": list(common_context)[:10],
        "solution_terms": list(common_solution)[:10],
        "description": f"When [{', '.join(list(common_context)[:5])}], try [{', '.join(list(common_solution)[:5])}]",
        "example_count": len(trajectories),
        "confidence": min(0.9, 0.5 + len(trajectories) * 0.1),
        "created_at": datetime.now(timezone.utc).isoformat()
    }


# CONSOLIDATE: Update long-term memory
def consolidate_learning(force: bool = False) -> Dict:
    """Merge patterns and update long-term memory."""
    bank = load_reasoning_bank()
    trajectories = bank.get("trajectories", [])
    stats = {"trajectories_processed": len(trajectories), "patterns_created": 0, "patterns_updated": 0}

    if len(trajectories) < 2:
        return {**stats, "skipped": True}

    by_domain = defaultdict(list)
    for traj in trajectories:
        by_domain[traj.get("domain", "general")].append(traj)

    for domain, domain_trajs in by_domain.items():
        if len(domain_trajs) < 2:
            continue

        clusters = []
        used = set()
        for i, traj in enumerate(domain_trajs):
            if i in used:
                continue
            cluster = [traj]
            used.add(i)
            for j, other in enumerate(domain_trajs):
                if j in used:
                    continue
                # Use context for similarity, fallback to problem text when context is empty
                traj_text = traj.get("context", "") or traj.get("problem", "")
                other_text = other.get("context", "") or other.get("problem", "")
                if compute_similarity(traj_text, other_text) > 0.3:  # Lowered threshold
                    cluster.append(other)
                    used.add(j)
            if len(cluster) >= 2:
                clusters.append(cluster)

        for cluster in clusters:
            pattern = distill_pattern(cluster)
            if pattern:
                if "patterns" not in bank:
                    bank["patterns"] = {}
                if pattern["id"] in bank["patterns"]:
                    stats["patterns_updated"] += 1
                else:
                    stats["patterns_created"] += 1
                bank["patterns"][pattern["id"]] = pattern

    bank["last_consolidation"] = datetime.now(timezone.utc).isoformat()
    save_reasoning_bank(bank)
    return stats


def record_trajectory(context: str, problem: str, solution: str,
                     domain: str = None, project_id: str = None) -> Dict:
    """Record a learning trajectory."""
    bank = load_reasoning_bank()
    traj_id = hashlib.md5(f"{context[:100]}_{datetime.now().isoformat()}".encode()).hexdigest()[:12]

    trajectory = {
        "id": traj_id,
        "context": context[:1000],
        "problem": problem[:500],
        "solution": solution[:500],
        "domain": domain,
        "project_id": project_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    bank.setdefault("trajectories", []).append(trajectory)
    if len(bank["trajectories"]) > 500:
        bank["trajectories"] = bank["trajectories"][-500:]

    save_reasoning_bank(bank)
    return trajectory


def query_for_context(context: str, domain: str = None) -> Dict:
    """Full RETRIEVE→JUDGE cycle for a given context."""
    similar = retrieve_similar(context, domain, limit=5)
    if not similar:
        return {"found": False, "message": "No similar past situations found"}

    applicable = []
    for s in similar:
        judgment = judge_applicability(s["trajectory"], context, domain)
        if judgment["applicable"]:
            applicable.append({
                "trajectory": s["trajectory"],
                "similarity": s["similarity"],
                "judgment": judgment
            })

    if not applicable:
        return {"found": True, "applicable": False, "similar_count": len(similar)}

    applicable.sort(key=lambda x: x["judgment"]["confidence"], reverse=True)
    return {
        "found": True,
        "applicable": True,
        "matches": applicable[:3],
        "recommendation": applicable[0]["trajectory"].get("solution")
    }


def format_for_injection(context: str, domain: str = None) -> Optional[str]:
    """Format reasoning bank results for context injection."""
    result = query_for_context(context, domain)
    if not result.get("applicable"):
        return None

    lines = ["[REASONING BANK - Past solutions that may apply]"]
    for match in result.get("matches", [])[:2]:
        traj = match["trajectory"]
        conf = match["judgment"]["confidence"]
        lines.append(f"\n  Problem: {traj.get('problem', '')[:100]}")
        lines.append(f"  Solution: {traj.get('solution', '')[:150]}")
        lines.append(f"  Confidence: {conf:.0%}")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ReasoningBank")
    parser.add_argument("command", choices=["record", "query", "consolidate", "stats"])
    parser.add_argument("context_arg", nargs="?", help="Context (positional)")
    parser.add_argument("--context", "-c", help="Context (keyword)")
    parser.add_argument("--problem", "-p")
    parser.add_argument("--solution", "-s")
    parser.add_argument("--domain", "-d")
    parser.add_argument("--limit", "-l", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    # Support both positional and keyword context
    context = args.context_arg or args.context

    if args.command == "record":
        traj = record_trajectory(context, args.problem, args.solution, args.domain)
        print(json.dumps(traj, indent=2) if args.json else f"Recorded: {traj['id']}")
    elif args.command == "query":
        if not context:
            print("Error: context required for query")
            sys.exit(1)
        result = query_for_context(context, args.domain)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            # Human-readable output
            if not result.get("applicable"):
                print("No applicable past solutions found.")
            else:
                print("=== Applicable Past Solutions ===")
                for i, match in enumerate(result.get("matches", [])[:args.limit], 1):
                    traj = match["trajectory"]
                    conf = match["judgment"]["confidence"]
                    print(f"\n{i}. {traj.get('problem', '')[:100]}")
                    print(f"   Solution: {traj.get('solution', '')[:200]}")
                    print(f"   Domain: {traj.get('domain', 'general')}, Confidence: {conf:.0%}")
    elif args.command == "consolidate":
        stats = consolidate_learning(force=True)
        print(json.dumps(stats, indent=2))
    elif args.command == "stats":
        bank = load_reasoning_bank()
        print(f"Trajectories: {len(bank.get('trajectories', []))}")
        print(f"Patterns: {len(bank.get('patterns', {}))}")
