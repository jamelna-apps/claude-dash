#!/usr/bin/env python3
"""
Ollama Client for Claude Memory System

Provides LLM inference using local Ollama.
Minimal setup: gemma3:4b-it-qat for generation, nomic-embed-text for embeddings.

Usage:
  from ollama_client import OllamaClient
  client = OllamaClient()
  response = client.generate("Summarize this code: ...")
  embedding = client.embed("code snippet")

Note: Tool calling requires Claude API - not supported locally.
"""

import json
import requests
from typing import Optional, List
import os

# Import config for task-based routing
try:
    from config import get_model_for_task, OLLAMA_URL, OLLAMA_CHAT_MODEL, model_supports_tools
except ImportError:
    # Fallback if config.py not available
    def get_model_for_task(task: str, fallback_to_default: bool = True) -> str:
        return os.environ.get("OLLAMA_MODEL", "gemma3:4b-it-qat")
    def model_supports_tools(model: str) -> bool:
        return False  # No tool-capable models installed locally
    OLLAMA_URL = "http://localhost:11434"
    OLLAMA_CHAT_MODEL = "gemma3:4b-it-qat"

def get_tool_model() -> str:
    """Tool calling not supported locally - returns None."""
    return None

# Re-export UnifiedClient for easy access
try:
    from unified_client import UnifiedClient, generate as unified_generate
except ImportError:
    UnifiedClient = None
    unified_generate = None

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

    # Context window sizes for models (in tokens)
    # Updated 2026-01-28: Minimal setup - only gemma3 + nomic-embed-text installed
    MODEL_CONTEXT_SIZES = {
        "gemma3:4b-it-qat": 131072,  # 128K - primary model for all local tasks
        "gemma3:12b": 131072,         # 128K (not installed, but supported)
    }

    def _get_default_context_size(self) -> int:
        """Get the default context window size for the current model."""
        # Check for exact match first
        if self.model in self.MODEL_CONTEXT_SIZES:
            return self.MODEL_CONTEXT_SIZES[self.model]

        # Check for partial match (e.g., "gemma3" matches "gemma3:4b-it-qat")
        for model_name, ctx_size in self.MODEL_CONTEXT_SIZES.items():
            base_model = model_name.split(":")[0]
            if self.model.startswith(base_model):
                return ctx_size

        # Default to 8192 for unknown models (safe default)
        return 8192

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

    def generate(self, prompt: str, system: str = None, stream: bool = False, images: List[str] = None, num_ctx: int = None) -> Optional[str]:
        """
        Generate text using Ollama LLM.

        Args:
            prompt: The text prompt
            system: Optional system message
            stream: Whether to stream the response
            images: Optional list of base64-encoded images (for vision models)
            num_ctx: Context window size (default: auto-selected based on model)
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

        # Set context window size - use model's full capacity when appropriate
        effective_num_ctx = num_ctx or self._get_default_context_size()
        if effective_num_ctx:
            payload["options"] = {"num_ctx": effective_num_ctx}

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120  # Increased timeout for larger contexts
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

    def chat_with_tools(
        self,
        messages: List[dict],
        tools: List[dict],
        model: str = None,
        max_tokens: int = 1024,
        system: str = None
    ):
        """
        Chat with tool calling support using Anthropic API format.

        NOTE: Tool calling is not supported locally. Use Claude API instead.

        Args:
            messages: List of message dicts with "role" and "content"
            tools: List of tool definitions
            model: Model to use (not supported locally)
            max_tokens: Max tokens to generate
            system: Optional system prompt

        Returns:
            Response object with .text, .tool_calls, .has_tool_use properties
        """
        if UnifiedClient is None:
            raise ImportError("unified_client not available")

        # Use tool-capable model by default
        if model is None:
            model = get_tool_model()

        client = UnifiedClient(ollama_url=self.base_url)
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            tools=tools,
            system=system
        )

    def generate_with_api(
        self,
        prompt: str,
        model: str = None,
        system: str = None,
        max_tokens: int = 1024
    ) -> str:
        """
        Generate using Anthropic Messages API format.

        This uses the newer /v1/messages endpoint instead of /api/generate.

        Args:
            prompt: The prompt text
            model: Model to use
            system: Optional system prompt
            max_tokens: Max tokens to generate

        Returns:
            Generated text
        """
        if UnifiedClient is None:
            # Fall back to native generate
            return self.generate(prompt, system=system)

        model = model or self.model
        client = UnifiedClient(ollama_url=self.base_url)

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            system=system
        )

        return response.text


# Quick test
if __name__ == "__main__":
    client = OllamaClient()
    health = client.health()
    print(json.dumps(health, indent=2))

    if client.available:
        print("\nTest generation:")
        response = client.generate("Say 'Ollama integration working!' in exactly those words.")
        print(f"Response: {response}")
