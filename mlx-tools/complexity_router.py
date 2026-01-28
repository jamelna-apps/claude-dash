#!/usr/bin/env python3
"""
Complexity Router - Quality-First Model Selection

QUALITY OVER COST: Routes development tasks to Claude, not local.

Model Selection:
- Trivial non-dev (commit msgs) → Local OK
- Trivial/Simple dev → Claude (Haiku)
- Moderate/Complex → Claude (Sonnet)
- Advanced architecture → Claude (Opus)

Local Ollama is NOT for development work - only for:
- Commit messages
- PR descriptions
- Enchanted app queries
- Personal experimentation
"""

import re
import sys
import json
from pathlib import Path
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
from enum import Enum

try:
    from config import MEMORY_ROOT
except ImportError:
    MEMORY_ROOT = Path.home() / '.claude-dash'


class ComplexityLevel(Enum):
    """Task complexity levels"""
    TRIVIAL = 1    # Single-line fix, typo
    SIMPLE = 2     # Single-file, clear scope
    MODERATE = 3   # 2-3 files, some reasoning
    COMPLEX = 4    # Multi-file, architectural
    ADVANCED = 5   # System-wide, deep debugging


class Backend(Enum):
    """Available backends"""
    LOCAL = "local"      # Ollama (gemma3 only - for non-critical tasks)
    CLAUDE = "claude"    # Claude API (all real code work)


@dataclass
class ComplexityAnalysis:
    """Result of complexity analysis"""
    level: ComplexityLevel
    score: float  # 0-100
    factors: Dict[str, float]
    recommended_backend: Backend
    reason: str
    confidence: float  # 0-1


# Keywords indicating complexity
COMPLEXITY_INDICATORS = {
    # High complexity indicators (10 points each)
    'high': [
        'refactor', 'redesign', 'architect', 'migration', 'migrate',
        'performance issue', 'memory leak', 'race condition',
        'security vulnerability', 'production bug', 'intermittent',
        'across all', 'across multiple', 'system-wide', 'all files',
        'all screens', 'all components', 'everywhere', 'codebase-wide',
        'complex', 'tricky', 'difficult', 'strange', 'weird',
        'not sure why', 'randomly', 'sometimes', 'inconsistent',
        'breaking change', 'backward compatible', 'multi-step'
    ],
    # Medium complexity indicators (5 points each)
    'medium': [
        'add feature', 'implement', 'create', 'build', 'new feature',
        'update logic', 'change behavior', 'modify', 'extend',
        'debug', 'investigate', 'figure out', 'understand', 'analyze',
        'several files', 'multiple', 'few places', 'couple of',
        'integration', 'connect', 'api call', 'database'
    ],
    # Low complexity indicators (-3 points each)
    'low': [
        'fix typo', 'typo', 'rename', 'update text', 'change string',
        'add comment', 'format', 'lint', 'simple', 'easy',
        'single file', 'one function', 'quick', 'small', 'minor',
        'update import', 'add export', 'adjust', 'tweak'
    ]
}

# Task types with typical complexity
TASK_TYPE_COMPLEXITY = {
    # Typically simple
    'explain': ComplexityLevel.SIMPLE,
    'what does': ComplexityLevel.SIMPLE,
    'how does': ComplexityLevel.SIMPLE,
    'document': ComplexityLevel.SIMPLE,
    'comment': ComplexityLevel.TRIVIAL,
    'rename': ComplexityLevel.TRIVIAL,
    'format': ComplexityLevel.TRIVIAL,

    # Typically moderate
    'add': ComplexityLevel.MODERATE,
    'create': ComplexityLevel.MODERATE,
    'implement': ComplexityLevel.MODERATE,
    'update': ComplexityLevel.MODERATE,
    'fix bug': ComplexityLevel.MODERATE,

    # Typically complex
    'refactor': ComplexityLevel.COMPLEX,
    'redesign': ComplexityLevel.COMPLEX,
    'debug': ComplexityLevel.COMPLEX,
    'investigate': ComplexityLevel.COMPLEX,
    'performance': ComplexityLevel.COMPLEX,
    'security': ComplexityLevel.COMPLEX,
    'architecture': ComplexityLevel.ADVANCED,
    'migrate': ComplexityLevel.ADVANCED,
}


def analyze_query_complexity(query: str) -> ComplexityAnalysis:
    """
    Analyze the complexity of a query/task.

    Returns ComplexityAnalysis with recommended backend.
    """
    query_lower = query.lower()
    factors = {}

    # Factor 1: Keyword analysis (0-30 points)
    high_count = sum(1 for kw in COMPLEXITY_INDICATORS['high'] if kw in query_lower)
    medium_count = sum(1 for kw in COMPLEXITY_INDICATORS['medium'] if kw in query_lower)
    low_count = sum(1 for kw in COMPLEXITY_INDICATORS['low'] if kw in query_lower)

    keyword_score = min(30, high_count * 10 + medium_count * 5 - low_count * 3)
    factors['keywords'] = max(0, keyword_score)

    # Factor 2: Task type detection (0-25 points)
    task_score = 0
    detected_type = None
    for task_type, complexity in TASK_TYPE_COMPLEXITY.items():
        if task_type in query_lower:
            task_score = (complexity.value - 1) * 6.25  # Scale to 0-25
            detected_type = task_type
            break
    factors['task_type'] = task_score

    # Factor 3: Scope indicators (0-20 points)
    scope_score = 0
    if any(w in query_lower for w in ['all', 'every', 'entire', 'whole', 'system']):
        scope_score += 15
    if any(w in query_lower for w in ['multiple', 'several', 'many', 'various']):
        scope_score += 10
    if re.search(r'\d+\s*(file|component|module|function)s?', query_lower):
        match = re.search(r'(\d+)', query_lower)
        if match:
            count = int(match.group(1))
            scope_score += min(20, count * 5)
    factors['scope'] = min(20, scope_score)

    # Factor 4: Question complexity (0-15 points)
    question_score = 0
    if '?' in query:
        # Multiple questions
        question_count = query.count('?')
        question_score += min(10, question_count * 3)
        # Complex questions
        if any(w in query_lower for w in ['why does', 'how can', 'what if', 'should i']):
            question_score += 5
    factors['questions'] = min(15, question_score)

    # Factor 5: Context needs (0-10 points)
    context_score = 0
    if any(w in query_lower for w in ['context', 'background', 'history', 'related']):
        context_score += 5
    if any(w in query_lower for w in ['codebase', 'project', 'repository']):
        context_score += 5
    factors['context_needs'] = context_score

    # Calculate total score
    total_score = sum(factors.values())

    # Determine complexity level
    if total_score < 15:
        level = ComplexityLevel.TRIVIAL
    elif total_score < 30:
        level = ComplexityLevel.SIMPLE
    elif total_score < 50:
        level = ComplexityLevel.MODERATE
    elif total_score < 70:
        level = ComplexityLevel.COMPLEX
    else:
        level = ComplexityLevel.ADVANCED

    # Determine backend recommendation
    # QUALITY FIRST: Use Claude for all development work
    # Local is ONLY for trivial non-development tasks (commit messages, etc.)

    # Check if this is a trivial non-development task
    trivial_patterns = ['commit message', 'pr description', 'changelog']
    is_trivial_non_dev = any(p in query_lower for p in trivial_patterns)

    if is_trivial_non_dev and level == ComplexityLevel.TRIVIAL:
        backend = Backend.LOCAL
        reason = "Non-critical task (commit message/PR description) - local OK"
        confidence = 0.7
    elif level == ComplexityLevel.TRIVIAL:
        # Even trivial development tasks should use Claude (Haiku)
        backend = Backend.CLAUDE
        reason = "Use Claude (Haiku) for quick development tasks"
        confidence = 0.85
    elif level == ComplexityLevel.SIMPLE:
        backend = Backend.CLAUDE
        reason = "Use Claude (Sonnet) for development work"
        confidence = 0.9
    elif level == ComplexityLevel.MODERATE:
        backend = Backend.CLAUDE
        reason = "Use Claude (Sonnet) for moderate complexity tasks"
        confidence = 0.9
    elif level == ComplexityLevel.COMPLEX:
        backend = Backend.CLAUDE
        reason = "Use Claude (Sonnet) for complex development work"
        confidence = 0.95
    else:  # ADVANCED
        backend = Backend.CLAUDE
        reason = "Use Claude (Opus) for advanced architecture tasks"
        confidence = 0.98

    return ComplexityAnalysis(
        level=level,
        score=total_score,
        factors=factors,
        recommended_backend=backend,
        reason=reason,
        confidence=confidence
    )


def analyze_code_change_complexity(
    files_to_change: List[str],
    estimated_lines: int = 0,
    has_tests: bool = False
) -> ComplexityAnalysis:
    """
    Analyze complexity based on planned code changes.

    Args:
        files_to_change: List of files that will be modified
        estimated_lines: Estimated lines of code to write
        has_tests: Whether the change includes test updates
    """
    factors = {}

    # Factor 1: File count (0-40 points)
    file_count = len(files_to_change)
    if file_count == 1:
        factors['files'] = 5
    elif file_count <= 3:
        factors['files'] = 15
    elif file_count <= 5:
        factors['files'] = 25
    else:
        factors['files'] = min(40, 25 + (file_count - 5) * 3)

    # Factor 2: Line count (0-30 points)
    if estimated_lines < 20:
        factors['lines'] = 5
    elif estimated_lines < 50:
        factors['lines'] = 10
    elif estimated_lines < 100:
        factors['lines'] = 20
    else:
        factors['lines'] = min(30, 20 + (estimated_lines - 100) // 20)

    # Factor 3: File type diversity (0-15 points)
    extensions = set(Path(f).suffix for f in files_to_change)
    factors['diversity'] = min(15, len(extensions) * 5)

    # Factor 4: Test involvement (0-15 points)
    if has_tests:
        factors['tests'] = 10
        if any('test' in f.lower() for f in files_to_change):
            factors['tests'] = 15
    else:
        factors['tests'] = 0

    # Calculate total
    total_score = sum(factors.values())

    # Determine level
    if total_score < 20:
        level = ComplexityLevel.SIMPLE
    elif total_score < 40:
        level = ComplexityLevel.MODERATE
    elif total_score < 60:
        level = ComplexityLevel.COMPLEX
    else:
        level = ComplexityLevel.ADVANCED

    # Backend recommendation - ALWAYS Claude for code changes
    # Local is NEVER appropriate for code modifications
    if level == ComplexityLevel.SIMPLE:
        backend = Backend.CLAUDE
        reason = f"Use Claude (Sonnet) for {file_count} file change(s)"
        confidence = 0.9
    elif level == ComplexityLevel.MODERATE:
        backend = Backend.CLAUDE
        reason = f"Use Claude (Sonnet) for {file_count} file change(s)"
        confidence = 0.9
    else:  # COMPLEX or ADVANCED
        backend = Backend.CLAUDE
        reason = f"Use Claude (Sonnet/Opus) for multi-file change ({file_count} files)"
        confidence = 0.95

    return ComplexityAnalysis(
        level=level,
        score=total_score,
        factors=factors,
        recommended_backend=backend,
        reason=reason,
        confidence=confidence
    )


def get_routing_decision(
    query: str,
    files: Optional[List[str]] = None,
    force_local: bool = False,
    force_claude: bool = False
) -> Tuple[Backend, str]:
    """
    Get the routing decision for a task.

    Args:
        query: The task/query text
        files: Optional list of files involved
        force_local: Force local processing
        force_claude: Force Claude API

    Returns:
        Tuple of (Backend, reason)
    """
    if force_local:
        return Backend.LOCAL, "Forced local processing"
    if force_claude:
        return Backend.CLAUDE, "Forced Claude API"

    # Analyze query
    query_analysis = analyze_query_complexity(query)

    # If files provided, also analyze code change complexity
    if files:
        code_analysis = analyze_code_change_complexity(files)
        # Use the higher complexity
        if code_analysis.level.value > query_analysis.level.value:
            return code_analysis.recommended_backend, code_analysis.reason

    return query_analysis.recommended_backend, query_analysis.reason


def format_analysis(analysis: ComplexityAnalysis) -> str:
    """Format analysis for display"""
    lines = [
        f"Complexity: {analysis.level.name} (score: {analysis.score:.1f}/100)",
        f"Recommended: {analysis.recommended_backend.value.upper()}",
        f"Reason: {analysis.reason}",
        f"Confidence: {analysis.confidence:.0%}",
        "",
        "Factors:"
    ]

    for factor, score in sorted(analysis.factors.items(), key=lambda x: -x[1]):
        bar = '#' * int(score / 2)
        lines.append(f"  {factor:<15} {score:>5.1f} {bar}")

    return '\n'.join(lines)


def main():
    """CLI interface"""
    if len(sys.argv) < 2:
        print("Usage: python complexity_router.py <query>")
        print("       python complexity_router.py --files <file1> <file2> ...")
        print("")
        print("Examples:")
        print("  python complexity_router.py 'fix typo in login button'")
        print("  python complexity_router.py 'refactor authentication across all screens'")
        print("  python complexity_router.py --files src/auth.js src/login.js src/api.js")
        sys.exit(1)

    if sys.argv[1] == '--files':
        files = sys.argv[2:]
        analysis = analyze_code_change_complexity(files)
        print(f"Analyzing change to {len(files)} files...\n")
    else:
        query = ' '.join(sys.argv[1:])
        analysis = analyze_query_complexity(query)
        print(f"Query: {query}\n")

    print(format_analysis(analysis))


if __name__ == '__main__':
    main()
