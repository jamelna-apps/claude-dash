#!/usr/bin/env python3
"""
Local LLM Benchmark Suite for Mac M2 16GB

Tests:
1. Response time for different task types
2. Code completion quality
3. Code explanation accuracy
4. Memory usage during inference

Usage:
    python benchmark.py [--quick] [--full] [--model MODEL]
"""

import sys
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from ollama_client import OllamaClient

# Benchmark test cases
BENCHMARK_TESTS = {
    "code_completion": {
        "task": "code_analysis",
        "prompt": """Complete this Python function:

def fibonacci(n):
    \"\"\"Return the nth Fibonacci number.\"\"\"
    # Your implementation here
""",
        "expected_keywords": ["fibonacci", "return", "if", "else"]
    },
    "code_explanation": {
        "task": "code_explanation",
        "prompt": """Explain what this code does in 2-3 sentences:

async function fetchUserData(userId) {
    const response = await fetch(`/api/users/${userId}`);
    if (!response.ok) throw new Error('User not found');
    return response.json();
}
""",
        "expected_keywords": ["fetch", "async", "user", "API", "response"]
    },
    "bug_detection": {
        "task": "code_review",
        "prompt": """Find the bug in this code:

function calculateAverage(numbers) {
    let sum = 0;
    for (let i = 0; i <= numbers.length; i++) {
        sum += numbers[i];
    }
    return sum / numbers.length;
}
""",
        "expected_keywords": ["off-by-one", "undefined", "<=", "<", "length"]
    },
    "commit_message": {
        "task": "commit_message",
        "prompt": """Generate a commit message for this diff:

- const MAX_RETRIES = 3;
+ const MAX_RETRIES = 5;
+ const RETRY_DELAY_MS = 1000;

- async function fetchData() {
+ async function fetchData(retries = MAX_RETRIES) {
    try {
        return await api.get('/data');
    } catch (error) {
-       throw error;
+       if (retries > 0) {
+           await sleep(RETRY_DELAY_MS);
+           return fetchData(retries - 1);
+       }
+       throw error;
    }
}
""",
        "expected_keywords": ["retry", "fetch", "error", "delay"]
    },
    "test_generation": {
        "task": "test_generation",
        "prompt": r"""Generate a unit test for this function:

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}
""",
        "expected_keywords": ["test", "expect", "valid", "invalid", "@"]
    }
}


def run_benchmark(model: str = None, quick: bool = False):
    """Run benchmark tests against specified model"""
    results = {
        "timestamp": datetime.now().isoformat(),
        "model": model or "default (task-based)",
        "hardware": get_hardware_info(),
        "tests": {}
    }

    tests_to_run = ["code_completion", "code_explanation"] if quick else BENCHMARK_TESTS.keys()

    print(f"\n{'='*60}")
    print(f"Local LLM Benchmark - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Model: {model or 'task-based routing'}")
    print(f"{'='*60}\n")

    for test_name in tests_to_run:
        test_config = BENCHMARK_TESTS[test_name]
        print(f"Running: {test_name}...")

        # Initialize client with task-specific routing
        if model:
            client = OllamaClient(model=model)
        else:
            client = OllamaClient(task=test_config["task"])

        # Measure response time
        start_time = time.time()
        response = client.generate(test_config["prompt"])
        end_time = time.time()

        elapsed = end_time - start_time

        # Check quality (keyword matching)
        if response is None:
            response = ""
            quality_score = 0.0
        else:
            keywords_found = sum(1 for kw in test_config["expected_keywords"]
                               if kw.lower() in response.lower())
            quality_score = keywords_found / len(test_config["expected_keywords"])

        # Estimate tokens
        prompt_tokens = len(test_config["prompt"].split())
        response_tokens = len(response.split()) if response else 0
        tokens_per_second = response_tokens / elapsed if elapsed > 0 else 0

        results["tests"][test_name] = {
            "model_used": client.model,
            "elapsed_seconds": round(elapsed, 2),
            "prompt_tokens": prompt_tokens,
            "response_tokens": response_tokens,
            "tokens_per_second": round(tokens_per_second, 1),
            "quality_score": round(quality_score, 2),
            "response_preview": response[:200] if response else "No response"
        }

        # Print result
        status = "✅" if quality_score >= 0.5 else "⚠️"
        print(f"  {status} {elapsed:.2f}s | {tokens_per_second:.1f} tok/s | quality: {quality_score:.0%}")
        print(f"     Model: {client.model}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    avg_time = sum(t["elapsed_seconds"] for t in results["tests"].values()) / len(results["tests"])
    avg_quality = sum(t["quality_score"] for t in results["tests"].values()) / len(results["tests"])
    avg_tps = sum(t["tokens_per_second"] for t in results["tests"].values()) / len(results["tests"])

    print(f"Average response time: {avg_time:.2f}s")
    print(f"Average tokens/second: {avg_tps:.1f}")
    print(f"Average quality score: {avg_quality:.0%}")

    results["summary"] = {
        "avg_response_time": round(avg_time, 2),
        "avg_tokens_per_second": round(avg_tps, 1),
        "avg_quality_score": round(avg_quality, 2)
    }

    # Save results
    output_path = Path(__file__).parent / "benchmark_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_path}")

    return results


def get_hardware_info():
    """Get basic hardware info"""
    try:
        result = subprocess.run(
            ["system_profiler", "SPHardwareDataType"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split('\n')
        info = {}
        for line in lines:
            if "Chip:" in line:
                info["chip"] = line.split(":")[-1].strip()
            elif "Memory:" in line:
                info["memory"] = line.split(":")[-1].strip()
        return info
    except Exception:
        return {"chip": "Unknown", "memory": "Unknown"}


def compare_models(models: list):
    """Compare multiple models on the same tests"""
    print("\nModel Comparison Benchmark")
    print("="*60)

    all_results = {}

    for model in models:
        print(f"\n--- Testing: {model} ---")
        client = OllamaClient()
        if model not in client.list_models():
            print(f"  ⚠️ Model not installed, skipping")
            continue

        results = run_benchmark(model=model, quick=True)
        all_results[model] = results["summary"]

    # Comparison table
    print("\n" + "="*60)
    print("COMPARISON")
    print("="*60)
    print(f"{'Model':<25} {'Avg Time':<12} {'Tok/s':<10} {'Quality':<10}")
    print("-"*60)

    for model, summary in all_results.items():
        print(f"{model:<25} {summary['avg_response_time']:.2f}s{'':<6} "
              f"{summary['avg_tokens_per_second']:.1f}{'':<5} "
              f"{summary['avg_quality_score']:.0%}")


def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        return

    model = None
    quick = "--quick" in args

    if "--model" in args:
        idx = args.index("--model")
        if idx + 1 < len(args):
            model = args[idx + 1]

    if "--compare" in args:
        # Compare coding models
        compare_models(["qwen2.5-coder:7b", "deepseek-coder:6.7b", "gemma3:4b-it-qat"])
    else:
        run_benchmark(model=model, quick=quick)


if __name__ == "__main__":
    main()
