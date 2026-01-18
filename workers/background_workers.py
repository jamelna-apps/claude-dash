#!/usr/bin/env python3
"""
Background Workers for Claude-Dash

Auto-triggered workers for:
1. Freshness Checker - Alert on stale indexes
2. Schema Drift Detector - Check database schema consistency
3. Dead Code Detector - Find unused exports
4. Health Monitor - System health checks
5. Index Updater - Keep HNSW/SQLite fresh
6. Learning Consolidator - Run ReasoningBank consolidation
"""

import json
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict

MEMORY_ROOT = Path.home() / '.claude-dash'
WORKERS_DIR = MEMORY_ROOT / 'workers'
WORKERS_LOG = WORKERS_DIR / 'workers.log'
WORKERS_STATE = WORKERS_DIR / 'state.json'

WORKERS_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line, file=sys.stderr)
    try:
        with open(WORKERS_LOG, 'a') as f:
            f.write(line + "\n")
    except:
        pass


def load_state() -> Dict:
    if WORKERS_STATE.exists():
        try:
            return json.loads(WORKERS_STATE.read_text())
        except:
            pass
    return {"last_run": {}, "results": {}}


def save_state(state: Dict):
    WORKERS_STATE.write_text(json.dumps(state, indent=2, default=str))


def check_freshness(project_id: str = None) -> Dict:
    """Check if indexes are fresh enough."""
    config_path = MEMORY_ROOT / 'config.json'
    if not config_path.exists():
        return {"error": "No config found"}

    config = json.loads(config_path.read_text())
    projects = config.get('projects', [])
    if project_id:
        projects = [p for p in projects if p['id'] == project_id]

    stale = []
    for project in projects:
        pid = project['id']
        project_dir = MEMORY_ROOT / 'projects' / pid
        for filename, max_days in [('summaries.json', 7), ('functions.json', 7), ('embeddings_v2.json', 14)]:
            filepath = project_dir / filename
            if filepath.exists():
                age_days = (datetime.now() - datetime.fromtimestamp(filepath.stat().st_mtime)).days
                if age_days > max_days:
                    stale.append({"project": pid, "file": filename, "age_days": age_days})

    return {"stale": stale, "needs_attention": len(stale) > 0}


def run_health_check() -> Dict:
    """Run system health check."""
    health = {"timestamp": datetime.now().isoformat(), "services": {}, "issues": []}

    # Check Ollama
    try:
        result = subprocess.run(['curl', '-s', 'http://localhost:11434/api/tags'], capture_output=True, timeout=5)
        health["services"]["ollama"] = "running" if result.returncode == 0 else "down"
    except:
        health["services"]["ollama"] = "down"

    # Check database
    db_path = MEMORY_ROOT / 'memory.db'
    if db_path.exists():
        health["services"]["memory_db"] = {"size_mb": round(db_path.stat().st_size / (1024 * 1024), 2)}
    else:
        health["issues"].append("memory.db not found")

    return health


def consolidate_learning() -> Dict:
    """Run ReasoningBank consolidation."""
    try:
        sys.path.insert(0, str(MEMORY_ROOT / 'learning'))
        from reasoning_bank import consolidate_learning as rb_consolidate
        return rb_consolidate(force=False)
    except Exception as e:
        return {"error": str(e)}


def consolidate_checkpoints(project_id: str = None) -> Dict:
    """Merge incremental checkpoints into observations.json and clean up.

    This is called by the Stop hook after a session ends normally, or can be
    run manually to recover from crashes.
    """
    checkpoint_dir = MEMORY_ROOT / "sessions" / "checkpoints"
    if not checkpoint_dir.exists():
        return {"status": "no_checkpoint_dir"}

    # Find all checkpoint files
    checkpoints = sorted(checkpoint_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    if not checkpoints:
        return {"status": "no_checkpoints", "count": 0}

    log(f"Consolidating {len(checkpoints)} checkpoints")

    merged_observations = []
    files_modified = set()
    sessions_processed = set()

    for cp_path in checkpoints:
        try:
            checkpoint = json.loads(cp_path.read_text())

            # Track session
            session_id = checkpoint.get("session_id", "unknown")
            sessions_processed.add(session_id)

            # Merge observations
            for obs in checkpoint.get("observations", []):
                # Deduplicate by observation text
                obs_text = obs.get("observation", "")
                if obs_text and not any(o.get("observation") == obs_text for o in merged_observations):
                    merged_observations.append(obs)

            # Track files
            for f in checkpoint.get("files_modified", []):
                files_modified.add(f)

        except (json.JSONDecodeError, IOError) as e:
            log(f"Error reading checkpoint {cp_path}: {e}")
            continue

    # Save merged observations to global observations.json if there are new ones
    if merged_observations:
        global_obs_path = MEMORY_ROOT / "sessions" / "observations.json"
        try:
            existing = json.loads(global_obs_path.read_text())
        except (json.JSONDecodeError, IOError, FileNotFoundError):
            existing = {"version": "1.0", "lastUpdated": None, "observations": []}

        # Merge with existing, deduplicating
        existing_texts = {o.get("observation", "") for o in existing.get("observations", [])}
        for obs in merged_observations:
            if obs.get("observation", "") not in existing_texts:
                existing["observations"].append(obs)

        # Keep last 500
        existing["observations"] = existing["observations"][-500:]
        existing["lastUpdated"] = datetime.now().isoformat() + "Z"

        # Atomic write
        temp_path = global_obs_path.with_suffix('.tmp')
        temp_path.write_text(json.dumps(existing, indent=2))
        temp_path.rename(global_obs_path)

        log(f"Merged {len(merged_observations)} observations into observations.json")

    # Clean up old checkpoint files (keep last 3 for debugging)
    checkpoints_to_delete = checkpoints[:-3] if len(checkpoints) > 3 else []
    for cp_path in checkpoints_to_delete:
        try:
            cp_path.unlink()
        except OSError:
            pass

    # Reset message counter for next session
    counter_file = MEMORY_ROOT / "sessions" / "message_counter"
    try:
        counter_file.write_text("0")
    except IOError:
        pass

    return {
        "status": "consolidated",
        "checkpoints_processed": len(checkpoints),
        "observations_merged": len(merged_observations),
        "files_tracked": len(files_modified),
        "sessions": list(sessions_processed),
        "checkpoints_cleaned": len(checkpoints_to_delete)
    }


def run_worker(worker_name: str, **kwargs) -> Dict:
    """Run a specific worker."""
    workers = {
        "freshness": check_freshness,
        "health": run_health_check,
        "consolidate": consolidate_learning,
        "checkpoints": consolidate_checkpoints
    }
    if worker_name not in workers:
        return {"error": f"Unknown worker: {worker_name}"}

    state = load_state()
    start = datetime.now()
    try:
        result = workers[worker_name](**kwargs)
        result["_worker"] = worker_name
        result["_duration_ms"] = (datetime.now() - start).total_seconds() * 1000
        state["last_run"][worker_name] = start.isoformat()
        state["results"][worker_name] = result
        save_state(state)
        log(f"Worker {worker_name} completed")
        return result
    except Exception as e:
        return {"error": str(e)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Background workers")
    parser.add_argument("worker", choices=["freshness", "health", "consolidate", "checkpoints", "all"], default="health")
    parser.add_argument("--project", "-p")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.worker == "all":
        results = {w: run_worker(w) for w in ["health", "freshness", "consolidate", "checkpoints"]}
    else:
        kwargs = {"project_id": args.project} if args.project else {}
        results = {args.worker: run_worker(args.worker, **kwargs)}

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        for name, result in results.items():
            print(f"\n=== {name} ===")
            for k, v in result.items():
                if not k.startswith('_'):
                    print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
