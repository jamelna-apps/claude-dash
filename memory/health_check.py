#!/usr/bin/env python3
"""
Session Health Check

Verifies dependencies are working at session start.
Auto-fixes common issues when possible.

Usage:
  python health_check.py [--fix] [--quiet]
"""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

MEMORY_ROOT = Path.home() / ".claude-dash"

# Health check results
issues = []
fixes_applied = []
warnings = []


def check_ollama():
    """Check if Ollama is running and responsive."""
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/tags",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            models = [m['name'] for m in data.get('models', [])]

            if not models:
                warnings.append("Ollama running but no models installed")
                return False, "no_models"

            # Check for recommended models (gemma3 or phi3 for general tasks)
            has_chat_model = any(m.startswith(('gemma', 'phi3', 'qwen')) for m in models)
            if not has_chat_model:
                warnings.append(f"No chat model found. Available: {models}. Recommended: gemma3:4b")
                return True, "missing_chat_model"

            return True, "ok"
    except urllib.error.URLError:
        return False, "not_running"
    except Exception as e:
        return False, f"error: {e}"


def fix_ollama(status):
    """Attempt to fix Ollama issues."""
    if status == "not_running":
        # Try to start Ollama
        try:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            fixes_applied.append("Started Ollama service")
            return True
        except FileNotFoundError:
            issues.append("Ollama not installed. Install from https://ollama.ai")
            return False
        except Exception as e:
            issues.append(f"Failed to start Ollama: {e}")
            return False

    elif status == "no_models":
        issues.append("Ollama has no models. Run: ollama pull gemma3:4b")
        return False

    elif status == "missing_chat_model":
        warnings.append("Consider running: ollama pull gemma3:4b")
        return True  # Not critical

    return True


def check_memory_directories():
    """Verify memory directory structure exists."""
    required_dirs = [
        MEMORY_ROOT / "sessions",
        MEMORY_ROOT / "sessions" / "transcripts",
        MEMORY_ROOT / "sessions" / "digests",
        MEMORY_ROOT / "sessions" / "summaries",
        MEMORY_ROOT / "projects",
        MEMORY_ROOT / "global",
        MEMORY_ROOT / "patterns",
        MEMORY_ROOT / "memory",
        MEMORY_ROOT / "logs",
    ]

    missing = []
    for d in required_dirs:
        if not d.exists():
            missing.append(d)

    return len(missing) == 0, missing


def fix_memory_directories(missing):
    """Create missing directories."""
    for d in missing:
        try:
            d.mkdir(parents=True, exist_ok=True)
            fixes_applied.append(f"Created {d.relative_to(MEMORY_ROOT)}")
        except Exception as e:
            issues.append(f"Failed to create {d}: {e}")
    return True


def check_required_files():
    """Check for required Python scripts."""
    required_files = [
        (MEMORY_ROOT / "memory" / "session_context.py", "Session context loader"),
        (MEMORY_ROOT / "memory" / "semantic_triggers.py", "Semantic triggers"),
        (MEMORY_ROOT / "memory" / "summarizer.py", "Session summarizer"),
        (MEMORY_ROOT / "memory" / "transcript_compactor.py", "Transcript compactor"),
        (MEMORY_ROOT / "patterns" / "detector.py", "Pattern detector"),
        (MEMORY_ROOT / "patterns" / "patterns.json", "Pattern definitions"),
    ]

    missing = []
    for path, name in required_files:
        if not path.exists():
            missing.append((path, name))

    return len(missing) == 0, missing


def check_config():
    """Verify config.json exists and is valid."""
    config_path = MEMORY_ROOT / "config.json"

    if not config_path.exists():
        return False, "missing"

    try:
        data = json.loads(config_path.read_text())
        if "projects" not in data:
            return False, "invalid"
        return True, "ok"
    except json.JSONDecodeError:
        return False, "corrupt"
    except Exception as e:
        return False, f"error: {e}"


def fix_config(status):
    """Create or repair config."""
    config_path = MEMORY_ROOT / "config.json"

    if status in ["missing", "corrupt", "invalid"]:
        default_config = {
            "projects": [],
            "settings": {
                "autoIndex": True,
                "watcherEnabled": True
            }
        }
        try:
            config_path.write_text(json.dumps(default_config, indent=2))
            fixes_applied.append("Created default config.json")
            return True
        except Exception as e:
            issues.append(f"Failed to create config: {e}")
            return False

    return True


def check_hooks():
    """Verify Claude hooks are configured."""
    hooks_dir = Path.home() / ".claude" / "hooks"
    settings_path = Path.home() / ".claude" / "settings.json"

    problems = []

    # Check hooks directory
    if not hooks_dir.exists():
        problems.append("hooks_dir_missing")

    # Check hook scripts
    inject_hook = hooks_dir / "inject-context.sh"
    save_hook = hooks_dir / "save-session.sh"

    if not inject_hook.exists():
        problems.append("inject_hook_missing")
    elif not os.access(inject_hook, os.X_OK):
        problems.append("inject_hook_not_executable")

    if not save_hook.exists():
        problems.append("save_hook_missing")
    elif not os.access(save_hook, os.X_OK):
        problems.append("save_hook_not_executable")

    # Check settings.json has hooks configured
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
            if "hooks" not in settings:
                problems.append("hooks_not_configured")
        except (json.JSONDecodeError, IOError):
            problems.append("settings_invalid")
    else:
        problems.append("settings_missing")

    return len(problems) == 0, problems


def fix_hooks(problems):
    """Fix hook issues."""
    hooks_dir = Path.home() / ".claude" / "hooks"

    if "hooks_dir_missing" in problems:
        try:
            hooks_dir.mkdir(parents=True, exist_ok=True)
            fixes_applied.append("Created hooks directory")
        except Exception as e:
            issues.append(f"Failed to create hooks dir: {e}")

    # Fix executable permissions
    for hook_name in ["inject-context.sh", "save-session.sh"]:
        hook_path = hooks_dir / hook_name
        if hook_path.exists():
            try:
                os.chmod(hook_path, 0o755)
                if f"{hook_name.replace('.sh', '')}_not_executable" in problems:
                    fixes_applied.append(f"Made {hook_name} executable")
            except OSError as e:
                warnings.append(f"Failed to set permissions on {hook_name}: {e}")

    # Note issues that need manual intervention
    if "inject_hook_missing" in problems:
        issues.append("inject-context.sh hook missing - memory injection disabled")

    if "save_hook_missing" in problems:
        issues.append("save-session.sh hook missing - session saving disabled")

    if "hooks_not_configured" in problems or "settings_missing" in problems:
        issues.append("Hooks not configured in settings.json")

    return True


def check_disk_space():
    """Check available disk space."""
    try:
        import shutil
        total, used, free = shutil.disk_usage(MEMORY_ROOT)
        free_gb = free / (1024 ** 3)

        if free_gb < 1:
            return False, f"low_space_{free_gb:.1f}GB"
        elif free_gb < 5:
            warnings.append(f"Low disk space: {free_gb:.1f} GB free")
            return True, "low_warning"

        return True, "ok"
    except OSError:
        return True, "unknown"  # Can't check disk space


def check_logs_size():
    """Check if logs are getting too large."""
    logs_dir = MEMORY_ROOT / "logs"

    if not logs_dir.exists():
        return True, "no_logs"

    total_size = sum(f.stat().st_size for f in logs_dir.glob("*") if f.is_file())
    size_mb = total_size / (1024 * 1024)

    if size_mb > 100:
        return False, f"large_{size_mb:.0f}MB"
    elif size_mb > 50:
        warnings.append(f"Logs growing large: {size_mb:.0f} MB")
        return True, "warning"

    return True, "ok"


def fix_logs(status):
    """Clean up old logs."""
    if status.startswith("large_"):
        logs_dir = MEMORY_ROOT / "logs"

        # Keep only last 10 log files by date
        log_files = sorted(logs_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)

        deleted = 0
        for f in log_files[10:]:
            try:
                f.unlink()
                deleted += 1
            except OSError:
                pass  # Skip files that can't be deleted

        if deleted:
            fixes_applied.append(f"Deleted {deleted} old log files")

        return True

    return True


def run_health_check(auto_fix=True, quiet=False):
    """Run all health checks."""
    checks = [
        ("Ollama", check_ollama, fix_ollama),
        ("Memory directories", check_memory_directories, fix_memory_directories),
        ("Required files", check_required_files, None),
        ("Config", check_config, fix_config),
        ("Hooks", check_hooks, fix_hooks),
        ("Disk space", check_disk_space, None),
        ("Logs size", check_logs_size, fix_logs),
    ]

    all_ok = True

    for name, check_fn, fix_fn in checks:
        ok, status = check_fn()

        if not ok:
            all_ok = False

            if auto_fix and fix_fn:
                fix_fn(status)
            else:
                if isinstance(status, list):
                    for item in status:
                        issues.append(f"{name}: {item}")
                else:
                    issues.append(f"{name}: {status}")

    return all_ok


def format_report(quiet=False):
    """Format health check report."""
    lines = []

    if issues:
        lines.append("[HEALTH ISSUES]")
        for issue in issues:
            lines.append(f"  ! {issue}")

    if fixes_applied and not quiet:
        lines.append("[AUTO-FIXED]")
        for fix in fixes_applied:
            lines.append(f"  + {fix}")

    if warnings and not quiet:
        lines.append("[WARNINGS]")
        for warn in warnings:
            lines.append(f"  ~ {warn}")

    return "\n".join(lines) if lines else None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Health check for Claude memory system")
    parser.add_argument("--fix", action="store_true", default=True, help="Auto-fix issues (default)")
    parser.add_argument("--no-fix", action="store_true", help="Don't auto-fix")
    parser.add_argument("--quiet", action="store_true", help="Only output if issues found")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    auto_fix = not args.no_fix
    all_ok = run_health_check(auto_fix=auto_fix, quiet=args.quiet)

    if args.json:
        result = {
            "healthy": all_ok and len(issues) == 0,
            "issues": issues,
            "fixes_applied": fixes_applied,
            "warnings": warnings
        }
        print(json.dumps(result, indent=2))
    else:
        report = format_report(quiet=args.quiet)
        if report:
            print(report)
        elif not args.quiet:
            print("[HEALTH OK] All systems operational")

    sys.exit(0 if (all_ok and len(issues) == 0) else 1)


if __name__ == "__main__":
    main()
