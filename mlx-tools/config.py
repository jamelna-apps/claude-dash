"""
Centralized configuration for claude-dash Python tools.

This module provides shared configuration used by all Python scripts,
eliminating hardcoded values and ensuring consistency.

Usage:
    from config import OLLAMA_URL, OLLAMA_MODEL, get_db_connection
"""

import os
from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================

MEMORY_ROOT = Path(os.environ.get('CLAUDE_DASH_ROOT', Path.home() / '.claude-dash'))
MLX_TOOLS = MEMORY_ROOT / 'mlx-tools'
PROJECTS_DIR = MEMORY_ROOT / 'projects'
SESSIONS_DIR = MEMORY_ROOT / 'sessions'
LOGS_DIR = MEMORY_ROOT / 'logs'
DB_PATH = MEMORY_ROOT / 'memory.db'

# =============================================================================
# OLLAMA CONFIGURATION
# =============================================================================

# Single source of truth for Ollama URL
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://localhost:11434')

# Models
OLLAMA_CHAT_MODEL = os.environ.get('OLLAMA_MODEL', 'gemma3:4b')
OLLAMA_EMBED_MODEL = os.environ.get('OLLAMA_EMBED_MODEL', 'nomic-embed-text')
OLLAMA_VLM_MODEL = os.environ.get('OLLAMA_VLM_MODEL', 'qwen3-vl:8b')  # Visual Language Model

# Timeouts (in seconds)
OLLAMA_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', '60'))
OLLAMA_EMBED_TIMEOUT = int(os.environ.get('OLLAMA_EMBED_TIMEOUT', '30'))

# =============================================================================
# SEARCH CONFIGURATION
# =============================================================================

DEFAULT_TOP_K = 10
MIN_KEYWORD_LENGTH = 3
BM25_K1 = 1.2
BM25_B = 0.75
SEMANTIC_WEIGHT = 0.4
BM25_WEIGHT = 0.6

# =============================================================================
# EMBEDDINGS CONFIGURATION
# =============================================================================

EMBEDDING_DIMENSION = 768  # nomic-embed-text dimension
MAX_EMBED_TEXT_LENGTH = 8000  # Characters to truncate before embedding
EMBEDDING_BATCH_SIZE = 32

# =============================================================================
# CODE REVIEW CONFIGURATION
# =============================================================================

MAX_CODE_LENGTH = 6000  # Max characters for code review
REVIEW_TEMPERATURE = 0.1
REVIEW_NUM_PREDICT = 1000

# =============================================================================
# TASK-BASED MODEL ROUTING
# =============================================================================

# Task categories and their preferred models
# Optimized for M2 16GB Mac Mini
TASK_MODEL_MAP = {
    # Code analysis tasks - use deepseek-coder (specialized for code)
    'code_review': 'deepseek-coder:6.7b',
    'code_analysis': 'deepseek-coder:6.7b',
    'code_explanation': 'deepseek-coder:6.7b',
    'static_analysis': 'deepseek-coder:6.7b',
    'test_generation': 'deepseek-coder:6.7b',

    # Documentation tasks - use phi3:mini (fast for simple text)
    'documentation': 'phi3:mini',
    'summarization': 'phi3:mini',
    'commit_message': 'phi3:mini',
    'pr_description': 'phi3:mini',

    # Reasoning/RAG tasks - use gemma3:4b (128K context + multimodal)
    'rag': 'gemma3:4b',
    'query': 'gemma3:4b',
    'ask': 'gemma3:4b',
    'planning': 'gemma3:4b',
    'architecture': 'gemma3:4b',

    # Error analysis - use deepseek-coder (code context matters)
    'error_analysis': 'deepseek-coder:6.7b',

    # Visual tasks - use qwen3-vl (specialized vision model)
    'ui_analysis': OLLAMA_VLM_MODEL,
    'screenshot_review': OLLAMA_VLM_MODEL,
    'design_assessment': OLLAMA_VLM_MODEL,
    'wireframe_analysis': OLLAMA_VLM_MODEL,
}

def get_model_for_task(task: str, fallback_to_default: bool = True) -> str:
    """
    Get the appropriate Ollama model for a given task.

    Args:
        task: Task identifier (e.g., 'code_review', 'ui_analysis')
        fallback_to_default: If True, falls back to OLLAMA_CHAT_MODEL if task not found

    Returns:
        Model name to use for the task

    Examples:
        >>> get_model_for_task('code_review')
        'gemma3:4b'
        >>> get_model_for_task('ui_analysis')  # When VLM is set
        'llava:13b'
        >>> get_model_for_task('unknown_task')
        'gemma3:4b'  # Falls back to default
    """
    model = TASK_MODEL_MAP.get(task)

    # If model is None (e.g., VLM not configured), fallback to default chat model
    if model is None and fallback_to_default:
        return OLLAMA_CHAT_MODEL

    # If task not found, return default if fallback enabled
    if model is None:
        return OLLAMA_CHAT_MODEL if fallback_to_default else None

    return model

def list_task_models() -> dict:
    """
    Get a summary of all task-to-model mappings.

    Returns:
        Dictionary of task categories to their assigned models
    """
    return {
        task: get_model_for_task(task)
        for task in TASK_MODEL_MAP.keys()
    }

def update_task_model(task: str, model: str) -> None:
    """
    Dynamically update a task's model assignment.

    Args:
        task: Task identifier
        model: Model name to assign

    Example:
        >>> update_task_model('code_review', 'deepseek-coder:33b')
    """
    TASK_MODEL_MAP[task] = model

# =============================================================================
# DATABASE CONNECTION
# =============================================================================

_db_connection = None

def get_db_connection():
    """Get a SQLite database connection with WAL mode enabled."""
    import sqlite3
    global _db_connection

    if _db_connection is None:
        _db_connection = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _db_connection.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        _db_connection.execute('PRAGMA journal_mode=WAL')
        _db_connection.execute('PRAGMA foreign_keys=ON')

    return _db_connection

def close_db_connection():
    """Close the database connection."""
    global _db_connection
    if _db_connection is not None:
        _db_connection.close()
        _db_connection = None

# =============================================================================
# OLLAMA CLIENT
# =============================================================================

def call_ollama_generate(prompt: str, model: str = None, timeout: int = None) -> str:
    """
    Call Ollama generate API with proper error handling.

    Args:
        prompt: The prompt to send
        model: Model to use (default: OLLAMA_CHAT_MODEL)
        timeout: Request timeout (default: OLLAMA_TIMEOUT)

    Returns:
        The generated response text

    Raises:
        OllamaError: If the request fails
    """
    import urllib.request
    import json

    model = model or OLLAMA_CHAT_MODEL
    timeout = timeout or OLLAMA_TIMEOUT

    data = json.dumps({
        'model': model,
        'prompt': prompt,
        'stream': False
    }).encode('utf-8')

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=data,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '')
    except urllib.error.URLError as e:
        raise OllamaError(f"Failed to connect to Ollama: {e}")
    except Exception as e:
        raise OllamaError(f"Ollama request failed: {e}")


def call_ollama_embed(text: str, model: str = None, timeout: int = None) -> list:
    """
    Get embeddings from Ollama.

    Args:
        text: Text to embed
        model: Model to use (default: OLLAMA_EMBED_MODEL)
        timeout: Request timeout (default: OLLAMA_EMBED_TIMEOUT)

    Returns:
        List of floats (embedding vector)

    Raises:
        OllamaError: If the request fails
    """
    import urllib.request
    import json

    model = model or OLLAMA_EMBED_MODEL
    timeout = timeout or OLLAMA_EMBED_TIMEOUT

    # Truncate text if too long
    if len(text) > MAX_EMBED_TEXT_LENGTH:
        text = text[:MAX_EMBED_TEXT_LENGTH]

    data = json.dumps({
        'model': model,
        'prompt': text
    }).encode('utf-8')

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embeddings",
        data=data,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('embedding', [])
    except urllib.error.URLError as e:
        raise OllamaError(f"Failed to connect to Ollama: {e}")
    except Exception as e:
        raise OllamaError(f"Ollama embedding request failed: {e}")


class OllamaError(Exception):
    """Exception raised when Ollama API calls fail."""
    pass


# =============================================================================
# COSINE SIMILARITY (shared utility)
# =============================================================================

def cosine_similarity(vec1: list, vec2: list) -> float:
    """
    Compute cosine similarity between two vectors.

    This is the SINGLE implementation to be used across all tools.
    Previously duplicated in 6+ files.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity score between -1 and 1
    """
    import math

    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


# =============================================================================
# LOGGING
# =============================================================================

import logging

def get_logger(name: str) -> logging.Logger:
    """Get a configured logger for a module."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger
