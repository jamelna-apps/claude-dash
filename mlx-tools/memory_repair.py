#!/usr/bin/env python3
"""
Memory Repair Tool for Claude-Dash

Automatically repairs common memory system issues:
- Stale indexes → trigger reindex
- Orphaned embeddings → remove from HNSW
- Missing summaries → regenerate
- Corrupt JSON → restore from backup or regenerate
"""

import json
import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

MEMORY_ROOT = Path.home() / ".claude-dash"


class MemoryRepairer:
    """Handles automatic repair of memory system issues."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_path = MEMORY_ROOT / "projects" / project_id
        self.indexes_path = MEMORY_ROOT / "indexes"
        self.fixed: List[Dict[str, Any]] = []
        self.remaining: List[Dict[str, Any]] = []

    def check_status(self) -> Dict[str, Any]:
        """Check health status without repairing."""
        issues = []

        # Check HNSW index
        hnsw_index = self.indexes_path / f"{self.project_id}.hnsw"
        summaries_file = self.project_path / "summaries.json"

        if not summaries_file.exists():
            issues.append({"type": "missing_summary", "details": "No summaries.json found"})
        elif hnsw_index.exists():
            if hnsw_index.stat().st_mtime < summaries_file.stat().st_mtime:
                issues.append({"type": "stale_index", "details": "HNSW index is stale"})
        else:
            issues.append({"type": "missing_index", "details": "No HNSW index found"})

        # Check functions.json
        functions_file = self.project_path / "functions.json"
        if not functions_file.exists() and summaries_file.exists():
            issues.append({"type": "missing_functions", "details": "No functions.json found"})

        # Check for corrupt JSON
        json_files = ["summaries.json", "functions.json", "index.json", "decisions.json"]
        for filename in json_files:
            filepath = self.project_path / filename
            if filepath.exists():
                try:
                    json.loads(filepath.read_text())
                except json.JSONDecodeError:
                    issues.append({"type": "corrupt_json", "file": filename})

        # Check for orphaned embeddings
        embeddings_file = self.project_path / "embeddings.json"
        if embeddings_file.exists():
            config_path = MEMORY_ROOT / "config.json"
            if config_path.exists():
                config = json.loads(config_path.read_text())
                project_config = next(
                    (p for p in config.get("projects", []) if p["id"] == self.project_id),
                    None
                )
                if project_config:
                    project_root = Path(project_config.get("path", ""))
                    if project_root.exists():
                        try:
                            embeddings = json.loads(embeddings_file.read_text())
                            orphaned_count = 0
                            for file_path in embeddings.get("files", {}).keys():
                                if not (project_root / file_path).exists():
                                    orphaned_count += 1
                            if orphaned_count > 0:
                                issues.append({"type": "orphaned_embedding", "count": orphaned_count})
                        except:
                            pass

        status = "healthy" if not issues else "needs_repair"

        return {
            "status": status,
            "project": self.project_id,
            "timestamp": datetime.now().isoformat(),
            "issues": issues
        }

    def repair_all(self) -> Dict[str, Any]:
        """Run all repair checks and fix what we can."""
        self._repair_stale_indexes()
        self._repair_orphaned_embeddings()
        self._repair_missing_summaries()
        self._repair_corrupt_json()
        self._repair_missing_functions_index()

        return {
            "status": "repaired" if self.fixed else "healthy",
            "project": self.project_id,
            "timestamp": datetime.now().isoformat(),
            "fixed": self.fixed,
            "remaining": self.remaining
        }

    def _repair_stale_indexes(self):
        """Check and rebuild stale indexes."""
        # Check if index exists and is fresh
        hnsw_index = self.indexes_path / f"{self.project_id}.hnsw"
        summaries_file = self.project_path / "summaries.json"

        if not summaries_file.exists():
            self.remaining.append({
                "issue": "no_summaries",
                "message": "No summaries.json found - need full reindex"
            })
            return

        # Check freshness: index should be newer than summaries
        if hnsw_index.exists():
            index_mtime = hnsw_index.stat().st_mtime
            summaries_mtime = summaries_file.stat().st_mtime

            if index_mtime < summaries_mtime:
                # Index is stale - rebuild
                try:
                    self._rebuild_hnsw_index()
                    self.fixed.append({
                        "issue": "stale_index",
                        "file": str(hnsw_index),
                        "action": "reindexed"
                    })
                except Exception as e:
                    self.remaining.append({
                        "issue": "stale_index",
                        "file": str(hnsw_index),
                        "error": str(e)
                    })
        else:
            # No index - create it
            try:
                self._rebuild_hnsw_index()
                self.fixed.append({
                    "issue": "missing_index",
                    "file": str(hnsw_index),
                    "action": "created"
                })
            except Exception as e:
                self.remaining.append({
                    "issue": "missing_index",
                    "error": str(e)
                })

    def _rebuild_hnsw_index(self):
        """Rebuild HNSW index for the project."""
        hnsw_script = MEMORY_ROOT / "mlx-tools" / "hnsw_index.py"
        venv_python = MEMORY_ROOT / "mlx-env" / "bin" / "python3"
        python_cmd = str(venv_python) if venv_python.exists() else "python3"

        result = subprocess.run(
            [python_cmd, str(hnsw_script), "build", self.project_id],
            capture_output=True,
            timeout=120
        )

        if result.returncode != 0:
            raise Exception(result.stderr.decode() or "Build failed")

    def _repair_orphaned_embeddings(self):
        """Remove embeddings for files that no longer exist."""
        embeddings_file = self.project_path / "embeddings.json"
        if not embeddings_file.exists():
            return

        # Load config to get project path
        config_path = MEMORY_ROOT / "config.json"
        if not config_path.exists():
            return

        config = json.loads(config_path.read_text())
        project_config = next(
            (p for p in config.get("projects", []) if p["id"] == self.project_id),
            None
        )
        if not project_config:
            return

        project_root = Path(project_config.get("path", ""))
        if not project_root.exists():
            return

        try:
            embeddings = json.loads(embeddings_file.read_text())
            original_count = len(embeddings.get("files", {}))
            orphaned = []

            for file_path in list(embeddings.get("files", {}).keys()):
                full_path = project_root / file_path
                if not full_path.exists():
                    orphaned.append(file_path)
                    del embeddings["files"][file_path]

            if orphaned:
                # Save cleaned embeddings
                embeddings_file.write_text(json.dumps(embeddings, indent=2))
                self.fixed.append({
                    "issue": "orphaned_embeddings",
                    "count": len(orphaned),
                    "action": "removed",
                    "files": orphaned[:10]  # Show first 10
                })
        except Exception as e:
            self.remaining.append({
                "issue": "orphaned_embeddings",
                "error": str(e)
            })

    def _repair_missing_summaries(self):
        """Check for missing file summaries and regenerate."""
        summaries_file = self.project_path / "summaries.json"
        index_file = self.project_path / "index.json"

        if not index_file.exists():
            self.remaining.append({
                "issue": "no_index",
                "message": "No index.json found - run full indexer"
            })
            return

        try:
            index_data = json.loads(index_file.read_text())
            indexed_files = set(index_data.get("files", []))

            if not summaries_file.exists():
                # No summaries at all - trigger regeneration
                self._run_indexer()
                self.fixed.append({
                    "issue": "missing_summaries",
                    "count": len(indexed_files),
                    "action": "regenerated_all"
                })
                return

            summaries = json.loads(summaries_file.read_text())
            summarized_files = set(summaries.get("files", {}).keys())

            missing = indexed_files - summarized_files
            if missing:
                # Trigger incremental reindex
                self._run_indexer()
                self.fixed.append({
                    "issue": "missing_summaries",
                    "count": len(missing),
                    "action": "regenerated",
                    "files": list(missing)[:10]
                })
        except Exception as e:
            self.remaining.append({
                "issue": "missing_summaries",
                "error": str(e)
            })

    def _run_indexer(self):
        """Run the project indexer."""
        indexer_script = MEMORY_ROOT / "watcher" / "indexer.py"
        if not indexer_script.exists():
            indexer_script = MEMORY_ROOT / "mlx-tools" / "indexer.py"

        if not indexer_script.exists():
            raise Exception("Indexer script not found")

        venv_python = MEMORY_ROOT / "mlx-env" / "bin" / "python3"
        python_cmd = str(venv_python) if venv_python.exists() else "python3"

        result = subprocess.run(
            [python_cmd, str(indexer_script), self.project_id],
            capture_output=True,
            timeout=300
        )

        if result.returncode != 0:
            raise Exception(result.stderr.decode() or "Indexer failed")

    def _repair_corrupt_json(self):
        """Check for and repair corrupt JSON files."""
        json_files = [
            "summaries.json",
            "functions.json",
            "index.json",
            "decisions.json",
            "preferences.json",
            "embeddings.json"
        ]

        for filename in json_files:
            filepath = self.project_path / filename
            backup_path = self.project_path / f"{filename}.backup"

            if not filepath.exists():
                continue

            try:
                # Try to parse
                json.loads(filepath.read_text())
            except json.JSONDecodeError:
                # Corrupt - try to restore from backup
                if backup_path.exists():
                    try:
                        backup_data = json.loads(backup_path.read_text())
                        filepath.write_text(json.dumps(backup_data, indent=2))
                        self.fixed.append({
                            "issue": "corrupt_json",
                            "file": filename,
                            "action": "restored_from_backup"
                        })
                    except:
                        # Backup also corrupt - delete and let regenerate
                        filepath.unlink()
                        self.fixed.append({
                            "issue": "corrupt_json",
                            "file": filename,
                            "action": "deleted_for_regeneration"
                        })
                else:
                    # No backup - delete corrupt file
                    filepath.unlink()
                    self.fixed.append({
                        "issue": "corrupt_json",
                        "file": filename,
                        "action": "deleted_for_regeneration"
                    })

    def _repair_missing_functions_index(self):
        """Rebuild functions.json if missing."""
        functions_file = self.project_path / "functions.json"
        summaries_file = self.project_path / "summaries.json"

        if functions_file.exists():
            return

        if not summaries_file.exists():
            return  # Can't rebuild without summaries

        # Extract functions from summaries
        try:
            summaries = json.loads(summaries_file.read_text())
            functions = {"functions": {}, "lastUpdated": datetime.now().isoformat()}

            for file_path, data in summaries.get("files", {}).items():
                for func in data.get("functions", []):
                    func_name = func.get("name", "")
                    if func_name:
                        if func_name not in functions["functions"]:
                            functions["functions"][func_name] = []
                        functions["functions"][func_name].append({
                            "file": file_path,
                            "line": func.get("line", 1),
                            "type": func.get("type", "function")
                        })

            functions_file.write_text(json.dumps(functions, indent=2))
            self.fixed.append({
                "issue": "missing_functions_index",
                "action": "regenerated",
                "count": len(functions["functions"])
            })
        except Exception as e:
            self.remaining.append({
                "issue": "missing_functions_index",
                "error": str(e)
            })


def main():
    if len(sys.argv) < 2:
        print("Usage: python memory_repair.py <project_id> [status|repair|scan]")
        print("Actions:")
        print("  status  - Check health status (default)")
        print("  repair  - Auto-repair issues")
        print("  scan    - Same as status")
        sys.exit(1)

    project_id = sys.argv[1]
    action = sys.argv[2] if len(sys.argv) > 2 else "status"

    repairer = MemoryRepairer(project_id)

    if action in ["status", "scan"]:
        result = repairer.check_status()
    elif action == "repair":
        result = repairer.repair_all()
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
