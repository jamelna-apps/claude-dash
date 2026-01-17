#!/usr/bin/env python3
"""
Ollama Client for Claude Memory System

Provides LLM inference using local Ollama container.
Falls back gracefully if Ollama is not available.

Usage:
  from ollama_client import OllamaClient
  client = OllamaClient()
  response = client.generate("Summarize this code: ...")
  embedding = client.embed("code snippet")
"""

import json
import requests
from typing import Optional, List
import os

# Import config for task-based routing
try:
    from config import get_model_for_task, OLLAMA_URL, OLLAMA_CHAT_MODEL
except ImportError:
    # Fallback if config.py not available
    def get_model_for_task(task: str, fallback_to_default: bool = True) -> str:
        return os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    OLLAMA_URL = "http://localhost:11434"
    OLLAMA_CHAT_MODEL = "qwen2.5:7b"

class OllamaClient:
    def __init__(self, base_url: str = None, model: str = None, task: str = None):
        """
        Initialize Ollama client.

        Args:
            base_url: Ollama API base URL (default: http://localhost:11434)
            model: Explicit model to use (overrides task-based routing)
            task: Task identifier for automatic model selection (e.g., 'code_review', 'ui_analysis')
        """
        self.base_url = base_url or os.environ.get("OLLAMA_URL", OLLAMA_URL)

        # Model selection priority:
        # 1. Explicit model parameter
        # 2. Task-based routing
        # 3. Environment variable
        # 4. Default from config
        if model:
            self.model = model
        elif task:
            self.model = get_model_for_task(task)
        else:
            self.model = os.environ.get("OLLAMA_MODEL", OLLAMA_CHAT_MODEL)

        self.task = task
        self._available = None

    @property
    def available(self) -> bool:
        """Check if Ollama is available."""
        if self._available is not None:
            return self._available

        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            self._available = response.status_code == 200
        except requests.exceptions.ConnectionError:
            self._available = False
        except requests.exceptions.Timeout:
            self._available = False
        except requests.exceptions.RequestException as e:
            print(f"Ollama health check failed: {type(e).__name__}: {e}", file=__import__('sys').stderr)
            self._available = False

        return self._available

    def generate(self, prompt: str, system: str = None, stream: bool = False, images: List[str] = None) -> Optional[str]:
        """
        Generate text using Ollama LLM.

        Args:
            prompt: The text prompt
            system: Optional system message
            stream: Whether to stream the response
            images: Optional list of base64-encoded images (for vision models)
        """
        if not self.available:
            return None

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream
        }

        if system:
            payload["system"] = system

        if images:
            payload["images"] = images

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=60
            )

            if response.status_code == 200:
                return response.json().get("response", "")
            return None
        except Exception as e:
            print(f"Ollama generate error: {e}")
            return None

    def embed(self, text: str) -> Optional[List[float]]:
        """Get embedding for text using Ollama."""
        if not self.available:
            return None

        try:
            response = requests.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text
                },
                timeout=30
            )

            if response.status_code == 200:
                return response.json().get("embedding", [])
            return None
        except Exception as e:
            print(f"Ollama embed error: {e}")
            return None

    def batch_embed(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Get embeddings for multiple texts."""
        return [self.embed(text) for text in texts]

    def list_models(self) -> List[str]:
        """List available models."""
        if not self.available:
            return []

        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return [m["name"] for m in models]
            return []
        except requests.exceptions.RequestException:
            return []
        except (json.JSONDecodeError, KeyError):
            return []

    def health(self) -> dict:
        """Get Ollama health status."""
        return {
            "available": self.available,
            "url": self.base_url,
            "model": self.model,
            "models": self.list_models() if self.available else []
        }


# Quick test
if __name__ == "__main__":
    client = OllamaClient()
    health = client.health()
    print(json.dumps(health, indent=2))

    if client.available:
        print("\nTest generation:")
        response = client.generate("Say 'Ollama integration working!' in exactly those words.")
        print(f"Response: {response}")
