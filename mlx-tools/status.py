#!/usr/bin/env python3
"""
MLX Status - System health check

Shows status of:
- Ollama (local AI)
- Memory Dashboard
- Project memory files
- Embeddings index

Usage:
  python status.py
  python status.py --json
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
import requests

MEMORY_ROOT = Path.home() / ".claude-dash"

sys.path.insert(0, str(MEMORY_ROOT / "mlx-tools"))
from ollama_client import OllamaClient


def check_ollama() -> dict:
    """Check Ollama status."""
    client = OllamaClient()
    return client.health()


def check_dashboard() -> dict:
    """Check dashboard status."""
    try:
        response = requests.get("http://localhost:3333", timeout=2)
        return {
            "available": response.status_code == 200,
            "url": "http://localhost:3333",
            "status": response.status_code
        }
    except:
        return {
            "available": False,
            "url": "http://localhost:3333",
            "status": "unreachable"
        }


def check_projects() -> list:
    """Check project memory status."""
    config_path = MEMORY_ROOT / "config.json"
    if not config_path.exists():
        return []

    config = json.loads(config_path.read_text())
    projects = []

    for p in config.get("projects", []):
        project_dir = MEMORY_ROOT / "projects" / p["id"]

        # Check memory files
        files = {
            "summaries": (project_dir / "summaries.json").exists(),
            "functions": (project_dir / "functions.json").exists(),
            "schema": (project_dir / "schema.json").exists(),
            "graph": (project_dir / "graph.json").exists(),
            "embeddings": (project_dir / "embeddings_v2.json").exists() or (project_dir / "embeddings.json").exists(),
        }

        # Get file counts
        summaries_count = 0
        if files["summaries"]:
            try:
                summaries = json.loads((project_dir / "summaries.json").read_text())
                summaries_count = len(summaries.get("files", {}))
            except:
                pass

        projects.append({
            "id": p["id"],
            "name": p["displayName"],
            "path": p["path"],
            "files": files,
            "indexed_files": summaries_count,
            "ready": all([files["summaries"], files["functions"]])
        })

    return projects


def format_status(status: dict) -> str:
    """Format status for terminal output."""
    lines = []

    # Header
    lines.append("=" * 50)
    lines.append("  Claude Memory System Status")
    lines.append("=" * 50)
    lines.append("")

    # Ollama
    ollama = status["ollama"]
    icon = "✓" if ollama["available"] else "✗"
    lines.append(f"OLLAMA LOCAL AI")
    lines.append(f"  Status: {icon} {'Running' if ollama['available'] else 'Not Running'}")
    if ollama["available"]:
        lines.append(f"  URL: {ollama['url']}")
        lines.append(f"  Model: {ollama['model']}")
        if ollama.get("models"):
            lines.append(f"  Available: {', '.join(ollama['models'])}")
    lines.append("")

    # Dashboard
    dash = status["dashboard"]
    icon = "✓" if dash["available"] else "✗"
    lines.append(f"MEMORY DASHBOARD")
    lines.append(f"  Status: {icon} {'Running' if dash['available'] else 'Not Running'}")
    if dash["available"]:
        lines.append(f"  URL: {dash['url']}")
    lines.append("")

    # Projects
    lines.append(f"PROJECTS ({len(status['projects'])} registered)")
    for p in status["projects"]:
        icon = "✓" if p["ready"] else "○"
        lines.append(f"  {icon} {p['name']} ({p['id']})")
        lines.append(f"      Files indexed: {p['indexed_files']}")

        missing = [k for k, v in p["files"].items() if not v]
        if missing:
            lines.append(f"      Missing: {', '.join(missing)}")

    lines.append("")
    lines.append("-" * 50)

    # Quick commands
    if not ollama["available"]:
        lines.append("Start Ollama:  ./dev-env.sh start")
    if not dash["available"]:
        lines.append("Start Dashboard:  ./dev-env.sh start")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Check Claude Memory system status")
    parser.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    status = {
        "timestamp": datetime.now().isoformat(),
        "ollama": check_ollama(),
        "dashboard": check_dashboard(),
        "projects": check_projects()
    }

    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(format_status(status))


if __name__ == "__main__":
    main()
