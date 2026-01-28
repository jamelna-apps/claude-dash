#!/usr/bin/env python3
"""
Cleanup duplicate observations and sessions from claude-dash memory.
Run once to fix historical data, then the observation_extractor.py 
deduplication will prevent future duplicates.
"""

import json
from pathlib import Path
from collections import defaultdict

MEMORY_ROOT = Path.home() / ".claude-dash"

def cleanup_session_index():
    """Deduplicate session index entries."""
    index_path = MEMORY_ROOT / "sessions" / "index.json"
    if not index_path.exists():
        print("No session index found")
        return
    
    index = json.loads(index_path.read_text())
    sessions = index.get("sessions", [])
    original_count = len(sessions)
    
    # Keep only unique (sessionId, projectId) combinations, preferring latest
    seen = {}
    for s in sessions:
        key = (s["sessionId"], s["projectId"])
        # Keep the one with more observations or later timestamp
        if key not in seen or s.get("observationCount", 0) >= seen[key].get("observationCount", 0):
            seen[key] = s
    
    deduped = list(seen.values())
    deduped.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    deduped = deduped[:100]  # Keep last 100
    
    index["sessions"] = deduped
    index_path.write_text(json.dumps(index, indent=2))
    
    print(f"Session index: {original_count} -> {len(deduped)} entries")

def cleanup_observations(path, limit):
    """Deduplicate observations in a file."""
    if not path.exists():
        return
    
    data = json.loads(path.read_text())
    observations = data.get("observations", [])
    original_count = len(observations)
    
    # Deduplicate by (sessionId, projectId, observation text)
    seen = {}
    for obs in observations:
        key = (obs.get("sessionId"), obs.get("projectId"), obs.get("observation", "")[:100])
        if key not in seen:
            seen[key] = obs
    
    deduped = list(seen.values())
    deduped.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    deduped = deduped[:limit]
    
    data["observations"] = deduped
    path.write_text(json.dumps(data, indent=2))
    
    print(f"{path.name}: {original_count} -> {len(deduped)} observations")

def cleanup_reasoning_bank():
    """Deduplicate reasoning bank trajectories."""
    rb_path = MEMORY_ROOT / "learning" / "reasoning_bank.json"
    if not rb_path.exists():
        return
    
    data = json.loads(rb_path.read_text())
    trajectories = data.get("trajectories", [])
    original_count = len(trajectories)
    
    # Deduplicate by problem text (first 100 chars)
    seen = {}
    for traj in trajectories:
        key = traj.get("problem", "")[:100]
        if key not in seen:
            seen[key] = traj
    
    deduped = list(seen.values())
    data["trajectories"] = deduped[-500:]  # Keep last 500
    rb_path.write_text(json.dumps(data, indent=2))
    
    print(f"Reasoning bank: {original_count} -> {len(deduped)} trajectories")

def cleanup_corrections():
    """Deduplicate corrections."""
    corr_path = MEMORY_ROOT / "learning" / "corrections.json"
    if not corr_path.exists():
        return
    
    data = json.loads(corr_path.read_text())
    corrections = data.get("corrections", [])
    original_count = len(corrections)
    
    # Deduplicate by user_message (first 100 chars)
    seen = {}
    for corr in corrections:
        key = corr.get("user_message", "")[:100]
        if key not in seen:
            seen[key] = corr
    
    deduped = list(seen.values())
    data["corrections"] = deduped[-200:]  # Keep last 200
    corr_path.write_text(json.dumps(data, indent=2))
    
    print(f"Corrections: {original_count} -> {len(deduped)} entries")

def main():
    print("=== Claude-Dash Duplicate Cleanup ===\n")
    
    cleanup_session_index()
    cleanup_observations(MEMORY_ROOT / "sessions" / "observations.json", 500)
    
    # Cleanup per-project observations
    projects_dir = MEMORY_ROOT / "projects"
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                obs_path = project_dir / "observations.json"
                if obs_path.exists():
                    cleanup_observations(obs_path, 200)
    
    cleanup_reasoning_bank()
    cleanup_corrections()
    
    print("\n=== Cleanup Complete ===")

if __name__ == "__main__":
    main()
