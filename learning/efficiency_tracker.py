#!/usr/bin/env python3
"""
Efficiency Tracker - Measures Claude-Dash learning system effectiveness over time.

Tracks:
- Token savings from memory hits vs raw file reads
- Correction frequency (should decrease as system learns)
- First-attempt success rate
- Context injection usefulness
- Session startup time savings

Usage:
    python3 efficiency_tracker.py --record <metric> <value>
    python3 efficiency_tracker.py --report
    python3 efficiency_tracker.py --trends
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

MEMORY_ROOT = Path.home() / ".claude-dash"
METRICS_FILE = MEMORY_ROOT / "learning" / "efficiency_metrics.json"
CORRECTIONS_FILE = MEMORY_ROOT / "learning" / "corrections.json"
OUTCOMES_FILE = MEMORY_ROOT / "learning" / "outcomes.json"
SESSIONS_DIR = MEMORY_ROOT / "sessions"

def load_metrics():
    """Load metrics history."""
    if METRICS_FILE.exists():
        with open(METRICS_FILE) as f:
            return json.load(f)
    return {
        "daily": {},  # date -> metrics
        "weekly": {},  # week -> aggregated metrics
        "lifetime": {
            "total_sessions": 0,
            "total_corrections": 0,
            "total_memory_hits": 0,
            "total_file_reads_avoided": 0,
            "estimated_tokens_saved": 0,
            "first_attempt_successes": 0,
            "total_attempts": 0
        }
    }

def save_metrics(metrics):
    """Save metrics."""
    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(METRICS_FILE, 'w') as f:
        json.dump(metrics, f, indent=2)

def get_today():
    return datetime.now().strftime("%Y-%m-%d")

def get_week():
    return datetime.now().strftime("%Y-W%W")

def record_metric(metric_name, value, project_id=None):
    """Record a metric value."""
    metrics = load_metrics()
    today = get_today()
    week = get_week()

    # Initialize daily entry
    if today not in metrics["daily"]:
        metrics["daily"][today] = {
            "sessions": 0,
            "corrections": 0,
            "memory_hits": 0,
            "memory_misses": 0,
            "file_reads_avoided": 0,
            "tokens_saved": 0,
            "first_attempt_success": 0,
            "total_attempts": 0,
            "context_injections": 0,
            "useful_injections": 0
        }

    # Update metric
    if metric_name in metrics["daily"][today]:
        metrics["daily"][today][metric_name] += value

    # Update lifetime
    lifetime_map = {
        "sessions": "total_sessions",
        "corrections": "total_corrections",
        "memory_hits": "total_memory_hits",
        "file_reads_avoided": "total_file_reads_avoided",
        "tokens_saved": "estimated_tokens_saved",
        "first_attempt_success": "first_attempt_successes",
        "total_attempts": "total_attempts"
    }

    if metric_name in lifetime_map:
        metrics["lifetime"][lifetime_map[metric_name]] += value

    save_metrics(metrics)
    return metrics

def count_corrections():
    """Count total corrections from corrections.json."""
    if not CORRECTIONS_FILE.exists():
        return 0, {}

    with open(CORRECTIONS_FILE) as f:
        data = json.load(f)

    corrections = data.get("corrections", [])
    total = len(corrections)

    # Group by week
    by_week = defaultdict(int)
    for c in corrections:
        ts = c.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                week = dt.strftime("%Y-W%W")
                by_week[week] += 1
            except:
                pass

    return total, dict(by_week)

def count_outcomes():
    """Analyze outcomes from outcomes.json."""
    if not OUTCOMES_FILE.exists():
        return {"success": 0, "failure": 0, "partial": 0}, {}

    with open(OUTCOMES_FILE) as f:
        data = json.load(f)

    outcomes = data.get("outcomes", [])
    counts = {"success": 0, "failure": 0, "partial": 0}
    by_week = defaultdict(lambda: {"success": 0, "failure": 0, "partial": 0})

    for o in outcomes:
        outcome = o.get("outcome", "")
        if outcome in counts:
            counts[outcome] += 1

        ts = o.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                week = dt.strftime("%Y-W%W")
                if outcome in by_week[week]:
                    by_week[week][outcome] += 1
            except:
                pass

    return counts, dict(by_week)

def count_sessions():
    """Count sessions from transcripts."""
    transcripts_dir = SESSIONS_DIR / "transcripts"
    if not transcripts_dir.exists():
        return 0, {}

    sessions = list(transcripts_dir.glob("*.jsonl"))
    total = len(sessions)

    by_week = defaultdict(int)
    for s in sessions:
        try:
            # Get file modification time
            mtime = datetime.fromtimestamp(s.stat().st_mtime)
            week = mtime.strftime("%Y-W%W")
            by_week[week] += 1
        except:
            pass

    return total, dict(by_week)

def estimate_token_savings():
    """Estimate tokens saved by memory system."""
    metrics = load_metrics()

    # Rough estimates based on typical usage
    TOKENS_PER_FILE_READ = 1500  # Average file is ~1500 tokens
    TOKENS_PER_MEMORY_HIT = 200  # Memory summary is ~200 tokens
    TOKENS_PER_CONTEXT_INJECTION = 150  # Context blocks are ~150 tokens each

    # Calculate from daily metrics
    total_memory_hits = sum(
        d.get("memory_hits", 0)
        for d in metrics["daily"].values()
    )

    total_file_reads_avoided = sum(
        d.get("file_reads_avoided", 0)
        for d in metrics["daily"].values()
    )

    # Estimate savings
    saved_from_memory = total_memory_hits * (TOKENS_PER_FILE_READ - TOKENS_PER_MEMORY_HIT)
    saved_from_avoidance = total_file_reads_avoided * TOKENS_PER_FILE_READ

    return {
        "memory_hit_savings": saved_from_memory,
        "file_avoidance_savings": saved_from_avoidance,
        "total_estimated_savings": saved_from_memory + saved_from_avoidance,
        "memory_hits": total_memory_hits,
        "files_avoided": total_file_reads_avoided
    }

def calculate_efficiency_score():
    """Calculate overall efficiency score (0-100)."""
    total_corrections, corrections_by_week = count_corrections()
    outcomes, outcomes_by_week = count_outcomes()
    total_sessions, sessions_by_week = count_sessions()

    # Components of efficiency score
    scores = {}

    # 1. Success rate (40% weight)
    total_outcomes = outcomes["success"] + outcomes["failure"] + outcomes["partial"]
    if total_outcomes > 0:
        success_rate = (outcomes["success"] + 0.5 * outcomes["partial"]) / total_outcomes
        scores["success_rate"] = success_rate * 100
    else:
        scores["success_rate"] = 50  # Neutral if no data

    # 2. Correction rate improvement (30% weight)
    # Compare recent corrections to earlier corrections
    weeks = sorted(corrections_by_week.keys())
    if len(weeks) >= 2:
        recent_weeks = weeks[-2:]
        early_weeks = weeks[:2] if len(weeks) >= 4 else weeks[:1]

        recent_avg = sum(corrections_by_week[w] for w in recent_weeks) / len(recent_weeks)
        early_avg = sum(corrections_by_week[w] for w in early_weeks) / len(early_weeks)

        if early_avg > 0:
            improvement = (early_avg - recent_avg) / early_avg
            scores["correction_improvement"] = min(100, max(0, 50 + improvement * 50))
        else:
            scores["correction_improvement"] = 50
    else:
        scores["correction_improvement"] = 50

    # 3. Memory utilization (30% weight)
    metrics = load_metrics()
    total_memory_hits = sum(d.get("memory_hits", 0) for d in metrics["daily"].values())
    total_misses = sum(d.get("memory_misses", 0) for d in metrics["daily"].values())

    if total_memory_hits + total_misses > 0:
        hit_rate = total_memory_hits / (total_memory_hits + total_misses)
        scores["memory_utilization"] = hit_rate * 100
    else:
        scores["memory_utilization"] = 50

    # Weighted average
    overall = (
        scores["success_rate"] * 0.4 +
        scores["correction_improvement"] * 0.3 +
        scores["memory_utilization"] * 0.3
    )

    return {
        "overall": round(overall, 1),
        "components": scores,
        "data": {
            "total_sessions": total_sessions,
            "total_corrections": total_corrections,
            "outcomes": outcomes
        }
    }

def calculate_trends():
    """Calculate week-over-week trends."""
    total_corrections, corrections_by_week = count_corrections()
    outcomes, outcomes_by_week = count_outcomes()
    total_sessions, sessions_by_week = count_sessions()

    # Get all weeks
    all_weeks = set(corrections_by_week.keys()) | set(outcomes_by_week.keys()) | set(sessions_by_week.keys())
    weeks = sorted(all_weeks)[-8:]  # Last 8 weeks

    trends = []
    for week in weeks:
        sessions = sessions_by_week.get(week, 0)
        corrections = corrections_by_week.get(week, 0)
        week_outcomes = outcomes_by_week.get(week, {"success": 0, "failure": 0, "partial": 0})

        total_outcomes = week_outcomes["success"] + week_outcomes["failure"] + week_outcomes["partial"]
        success_rate = (week_outcomes["success"] / total_outcomes * 100) if total_outcomes > 0 else None

        corrections_per_session = (corrections / sessions) if sessions > 0 else None

        trends.append({
            "week": week,
            "sessions": sessions,
            "corrections": corrections,
            "corrections_per_session": round(corrections_per_session, 2) if corrections_per_session else None,
            "success_rate": round(success_rate, 1) if success_rate else None,
            "outcomes": week_outcomes
        })

    return trends

def generate_report():
    """Generate efficiency report."""
    efficiency = calculate_efficiency_score()
    trends = calculate_trends()
    token_savings = estimate_token_savings()

    report = []
    report.append("=" * 60)
    report.append("CLAUDE-DASH EFFICIENCY REPORT")
    report.append("=" * 60)
    report.append("")

    # Overall score
    score = efficiency["overall"]
    if score >= 80:
        grade = "A - Excellent"
    elif score >= 65:
        grade = "B - Good"
    elif score >= 50:
        grade = "C - Average"
    else:
        grade = "D - Needs improvement"

    report.append(f"Overall Efficiency Score: {score}/100 ({grade})")
    report.append("")

    # Component breakdown
    report.append("Component Scores:")
    for name, value in efficiency["components"].items():
        bar = "█" * int(value / 10) + "░" * (10 - int(value / 10))
        report.append(f"  {name:25} [{bar}] {value:.1f}")
    report.append("")

    # Stats
    data = efficiency["data"]
    report.append("Lifetime Statistics:")
    report.append(f"  Total sessions:     {data['total_sessions']}")
    report.append(f"  Total corrections:  {data['total_corrections']}")
    report.append(f"  Outcomes tracked:   {sum(data['outcomes'].values())}")
    report.append(f"    - Success:        {data['outcomes']['success']}")
    report.append(f"    - Partial:        {data['outcomes']['partial']}")
    report.append(f"    - Failure:        {data['outcomes']['failure']}")
    report.append("")

    # Token savings
    report.append("Estimated Token Savings:")
    report.append(f"  Memory hits:        {token_savings['memory_hits']} queries served from memory")
    report.append(f"  Files avoided:      {token_savings['files_avoided']} file reads skipped")
    report.append(f"  Tokens saved:       ~{token_savings['total_estimated_savings']:,}")
    report.append("")

    # Trends
    if trends:
        report.append("Weekly Trends (last 8 weeks):")
        report.append("-" * 60)
        report.append(f"{'Week':<12} {'Sessions':>10} {'Corrections':>12} {'Corr/Sess':>10} {'Success%':>10}")
        report.append("-" * 60)

        for t in trends:
            cps = f"{t['corrections_per_session']:.2f}" if t['corrections_per_session'] is not None else "-"
            sr = f"{t['success_rate']:.0f}%" if t['success_rate'] is not None else "-"
            report.append(f"{t['week']:<12} {t['sessions']:>10} {t['corrections']:>12} {cps:>10} {sr:>10}")

        report.append("")

        # Trend analysis
        if len(trends) >= 4:
            early = trends[:len(trends)//2]
            recent = trends[len(trends)//2:]

            early_cps = [t['corrections_per_session'] for t in early if t['corrections_per_session'] is not None]
            recent_cps = [t['corrections_per_session'] for t in recent if t['corrections_per_session'] is not None]

            if early_cps and recent_cps:
                early_avg = sum(early_cps) / len(early_cps)
                recent_avg = sum(recent_cps) / len(recent_cps)

                if recent_avg < early_avg:
                    improvement = (early_avg - recent_avg) / early_avg * 100
                    report.append(f"📉 Corrections per session decreased by {improvement:.0f}% (improving!)")
                elif recent_avg > early_avg:
                    increase = (recent_avg - early_avg) / early_avg * 100
                    report.append(f"📈 Corrections per session increased by {increase:.0f}%")
                else:
                    report.append("➡️  Correction rate stable")

    report.append("")
    report.append("=" * 60)

    return "\n".join(report)

def project_future_efficiency(weeks_ahead=12):
    """Project efficiency improvements based on current trends."""
    trends = calculate_trends()

    if len(trends) < 3:
        return "Not enough data to project future efficiency (need 3+ weeks)"

    # Calculate improvement rate
    corrections_per_session = [
        t['corrections_per_session']
        for t in trends
        if t['corrections_per_session'] is not None
    ]

    if len(corrections_per_session) < 2:
        return "Not enough correction data to project"

    # Simple linear regression
    n = len(corrections_per_session)
    x_mean = (n - 1) / 2
    y_mean = sum(corrections_per_session) / n

    numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(corrections_per_session))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        slope = 0
    else:
        slope = numerator / denominator

    intercept = y_mean - slope * x_mean

    # Project forward
    projections = []
    current_week = len(corrections_per_session) - 1
    current_cps = corrections_per_session[-1]

    for w in range(1, weeks_ahead + 1):
        projected_cps = max(0, intercept + slope * (current_week + w))
        improvement = ((current_cps - projected_cps) / current_cps * 100) if current_cps > 0 else 0
        projections.append({
            "weeks_ahead": w,
            "projected_corrections_per_session": round(projected_cps, 2),
            "improvement_from_now": round(improvement, 1)
        })

    report = []
    report.append("PROJECTED EFFICIENCY (based on current learning rate)")
    report.append("-" * 50)
    report.append(f"Current corrections/session: {current_cps:.2f}")
    report.append(f"Weekly improvement rate: {-slope:.3f} corrections/week")
    report.append("")

    milestones = [4, 8, 12]
    for w in milestones:
        if w <= weeks_ahead:
            p = projections[w-1]
            report.append(f"In {w} weeks: {p['projected_corrections_per_session']:.2f} corr/sess ({p['improvement_from_now']:+.0f}%)")

    # Estimate when we hit target
    target_cps = 0.5  # Target: 0.5 corrections per session
    if slope < 0 and current_cps > target_cps:
        weeks_to_target = (target_cps - intercept) / slope - current_week
        if weeks_to_target > 0:
            report.append("")
            report.append(f"Projected to reach {target_cps} corr/sess in ~{weeks_to_target:.0f} weeks")

    return "\n".join(report)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Track Claude-Dash efficiency")
    parser.add_argument("--record", nargs=2, metavar=("METRIC", "VALUE"),
                       help="Record a metric (sessions, corrections, memory_hits, etc.)")
    parser.add_argument("--report", action="store_true", help="Generate efficiency report")
    parser.add_argument("--trends", action="store_true", help="Show weekly trends")
    parser.add_argument("--project", type=int, metavar="WEEKS",
                       help="Project efficiency N weeks ahead")
    parser.add_argument("--score", action="store_true", help="Show efficiency score only")

    args = parser.parse_args()

    if args.record:
        metric, value = args.record
        try:
            value = float(value)
            record_metric(metric, value)
            print(f"Recorded: {metric} += {value}")
        except ValueError:
            print(f"Error: value must be a number")
            sys.exit(1)

    elif args.report:
        print(generate_report())

    elif args.trends:
        trends = calculate_trends()
        for t in trends:
            print(f"{t['week']}: {t['sessions']} sessions, {t['corrections']} corrections")

    elif args.project:
        print(project_future_efficiency(args.project))

    elif args.score:
        efficiency = calculate_efficiency_score()
        print(f"Efficiency Score: {efficiency['overall']}/100")

    else:
        # Default: show summary
        efficiency = calculate_efficiency_score()
        print(f"Efficiency Score: {efficiency['overall']}/100")
        print()
        print("Run with --report for full details")
        print("Run with --project 12 to see 12-week projection")

if __name__ == "__main__":
    main()
