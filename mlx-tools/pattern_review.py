#!/usr/bin/env python3
"""
Guardian Pattern Review for Claude-Dash

LLM-powered code validation against documented patterns.
Inspired by Cortex-TMS Guardian system.

Validates code against:
- PATTERNS.md (if exists)
- patterns from decisions.json
- project-specific conventions

Uses Claude Haiku for quality + speed + low cost (~$0.001/review).
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

import urllib.request

MEMORY_ROOT = Path.home() / ".claude-dash"
HAIKU_MODEL = "claude-haiku-4-5-20251001"  # Haiku 4.5 - fast, cheap, excellent quality
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:4b-it-qat"


def get_api_key() -> Optional[str]:
    """Get Anthropic API key from env file or environment."""
    # Try environment variable first
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    # Try .env file
    env_file = MEMORY_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY=") and not line.startswith("#"):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value

    return None


class PatternReviewer:
    """Review code against documented patterns using LLM."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_path = MEMORY_ROOT / "projects" / project_id
        self.config = self._load_config()
        self.patterns = self._load_patterns()

    def _load_config(self) -> Dict:
        """Load global config."""
        config_path = MEMORY_ROOT / "config.json"
        if config_path.exists():
            return json.loads(config_path.read_text())
        return {"projects": []}

    def _get_project_root(self) -> Optional[Path]:
        """Get project source root."""
        project_config = next(
            (p for p in self.config.get("projects", []) if p["id"] == self.project_id),
            None
        )
        if project_config:
            return Path(project_config.get("path", ""))
        return None

    def _load_patterns(self) -> List[Dict[str, str]]:
        """Load patterns from PATTERNS.md and decisions.json."""
        patterns = []

        project_root = self._get_project_root()

        # Try PATTERNS.md in project root
        if project_root:
            patterns_md = project_root / "PATTERNS.md"
            if patterns_md.exists():
                content = patterns_md.read_text()
                patterns.append({
                    "source": "PATTERNS.md",
                    "content": content[:5000]  # Limit size
                })

            # Also check docs/PATTERNS.md
            docs_patterns = project_root / "docs" / "PATTERNS.md"
            if docs_patterns.exists():
                content = docs_patterns.read_text()
                patterns.append({
                    "source": "docs/PATTERNS.md",
                    "content": content[:5000]
                })

        # Load from decisions.json
        decisions_path = self.project_path / "decisions.json"
        if decisions_path.exists():
            try:
                data = json.loads(decisions_path.read_text())
                decision_patterns = []
                for d in data.get("decisions", [])[:20]:  # Last 20 decisions
                    if d.get("rules"):
                        decision_patterns.extend(d["rules"])
                    elif d.get("summary"):
                        decision_patterns.append(d["summary"])

                if decision_patterns:
                    patterns.append({
                        "source": "decisions.json",
                        "content": "\n".join(f"- {p}" for p in decision_patterns)
                    })
            except:
                pass

        # Load from preferences.json
        prefs_path = self.project_path / "preferences.json"
        if prefs_path.exists():
            try:
                data = json.loads(prefs_path.read_text())
                pref_patterns = []

                for item in data.get("use", []):
                    pref_patterns.append(f"PREFER: {item}")
                for item in data.get("avoid", []):
                    pref_patterns.append(f"AVOID: {item}")
                for conv in data.get("conventions", []):
                    pref_patterns.append(f"CONVENTION: {conv}")

                if pref_patterns:
                    patterns.append({
                        "source": "preferences.json",
                        "content": "\n".join(pref_patterns)
                    })
            except:
                pass

        return patterns

    def _call_haiku(self, prompt: str, system: str = "") -> str:
        """Call Claude Haiku for LLM analysis.

        Cost: ~$0.001 per review (1/10th of a cent)
        Quality: Much better than local models
        Speed: 1-3 seconds

        Falls back to Ollama if no API key available.
        """
        api_key = get_api_key()

        if api_key and ANTHROPIC_AVAILABLE:
            try:
                client = anthropic.Anthropic(api_key=api_key)

                message = client.messages.create(
                    model=HAIKU_MODEL,
                    max_tokens=2000,
                    system=system,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )

                return message.content[0].text
            except anthropic.APIError as e:
                print(f"[WARN] Haiku API error, falling back to Ollama: {e}", file=sys.stderr)
            except Exception as e:
                print(f"[WARN] Haiku error, falling back to Ollama: {e}", file=sys.stderr)

        # Fallback to Ollama
        return self._call_ollama(prompt, system)

    def _call_ollama(self, prompt: str, system: str = "") -> str:
        """Fallback to local Ollama for LLM analysis."""
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 2000
            }
        }

        try:
            req = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(payload).encode('utf-8'),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get("response", "")
        except Exception as e:
            return f'{{"violations": [], "compliant": [], "error": "Ollama error: {e}"}}'

    def review_file(self, file_path: str, mode: str = "normal") -> Dict[str, Any]:
        """Review a file against patterns.

        Args:
            file_path: Path to the file to review
            mode: "normal" (all issues) or "safe" (high confidence only, >=70%)
        """
        project_root = self._get_project_root()
        if not project_root:
            return {"error": "Project root not found"}

        # Resolve file path
        full_path = Path(file_path)
        if not full_path.is_absolute():
            full_path = project_root / file_path

        if not full_path.exists():
            return {"error": f"File not found: {file_path}"}

        # Read file content
        try:
            code_content = full_path.read_text()
            if len(code_content) > 10000:
                code_content = code_content[:10000] + "\n... (truncated)"
        except Exception as e:
            return {"error": f"Could not read file: {e}"}

        if not self.patterns:
            return {
                "error": "No patterns found",
                "hint": "Create PATTERNS.md in your project root or add decisions to decisions.json"
            }

        # Build system prompt
        system_prompt = """You are a strict code reviewer. Your job is to find ANY patterns that don't match the documented conventions.

Review the code carefully and identify:
1. Code style issues (naming, formatting)
2. Architecture violations (wrong imports, wrong patterns)
3. Security concerns (hardcoded values, missing validation)
4. Missing best practices

Be thorough - it's better to flag potential issues than miss them.

For EACH issue found, provide JSON with:
- severity: "major" or "minor"
- line: line number where issue occurs
- pattern: which documented pattern it violates
- issue: what the specific problem is
- confidence: 0.0-1.0 how sure you are
- suggestion: how to fix it

Also list which patterns the code DOES follow correctly.

ALWAYS respond with valid JSON in this exact format:
{
  "violations": [
    {"severity": "major", "line": 45, "pattern": "naming convention", "issue": "variable uses camelCase instead of snake_case", "confidence": 0.9, "suggestion": "rename to snake_case"}
  ],
  "compliant": ["uses proper imports", "follows component structure"]
}

If code looks good, return empty arrays but ALWAYS include both keys."""

        # Build user prompt
        patterns_text = "\n\n".join(
            f"=== {p['source']} ===\n{p['content']}"
            for p in self.patterns
        )

        user_prompt = f"""Review this code against the following patterns:

{patterns_text}

=== CODE TO REVIEW ({file_path}) ===
{code_content}

Analyze and respond with JSON only."""

        # Call Haiku (falls back to Ollama if no API key)
        response = self._call_haiku(user_prompt, system_prompt)

        # Parse response
        try:
            # Try to extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                result = json.loads(json_str)
                # Include raw response snippet for debugging if no findings
                if not result.get("violations") and not result.get("compliant"):
                    result["debug"] = response[:300]
            else:
                result = {"violations": [], "compliant": [], "note": "No JSON found in response", "raw_response": response[:500]}
        except json.JSONDecodeError as e:
            result = {"violations": [], "compliant": [], "parse_error": str(e), "raw_response": response[:500]}

        # Filter by confidence in safe mode
        violations = result.get("violations", [])
        if mode == "safe":
            violations = [v for v in violations if v.get("confidence", 0) >= 0.7]

        # Calculate tokens used (estimate)
        tokens_used = (len(patterns_text) + len(code_content) + len(response)) // 4

        return {
            "file": str(file_path),
            "project": self.project_id,
            "mode": mode,
            "timestamp": datetime.now().isoformat(),
            "violations": violations,
            "compliant": result.get("compliant", []),
            "tokensUsed": tokens_used,
            "patternsLoaded": len(self.patterns)
        }


def main():
    if len(sys.argv) < 3:
        print("Usage: python pattern_review.py <project_id> <file_path> [mode]")
        print("Modes: normal (default), safe (high confidence only)")
        sys.exit(1)

    project_id = sys.argv[1]
    file_path = sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "normal"

    reviewer = PatternReviewer(project_id)
    result = reviewer.review_file(file_path, mode)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
