#!/usr/bin/env python3
"""
Unified Client for Claude-Dash

Provides a single Anthropic SDK-compatible interface for both:
- Local inference via Ollama (using Anthropic Messages API format)
- Cloud inference via Claude API

Usage:
    from unified_client import UnifiedClient

    # Auto-routes based on config
    client = UnifiedClient()
    response = client.messages.create(
        model="gemma3:4b-it-qat",  # or "claude-sonnet-4-20250514"
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello"}]
    )

Note: Tool calling requires Claude API. Local models (gemma3) don't support tools.
"""

import os
import json
import requests
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, field
import sys

# Default configuration
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

# Tool calling not supported locally - use Claude API for tool tasks
TOOL_CAPABLE_MODELS = set()  # None installed locally

# Models for simple generation (fast, no tool support)
GENERATION_MODELS = {
    "gemma3:4b-it-qat", "gemma3:12b",
}


@dataclass
class ContentBlock:
    """Represents a content block in a message."""
    type: str
    text: Optional[str] = None
    id: Optional[str] = None
    name: Optional[str] = None
    input: Optional[Dict] = None
    thinking: Optional[str] = None

    def to_dict(self) -> Dict:
        d = {"type": self.type}
        if self.text is not None:
            d["text"] = self.text
        if self.id is not None:
            d["id"] = self.id
        if self.name is not None:
            d["name"] = self.name
        if self.input is not None:
            d["input"] = self.input
        if self.thinking is not None:
            d["thinking"] = self.thinking
        return d


@dataclass
class Usage:
    """Token usage information."""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Message:
    """Represents an API response message."""
    id: str
    type: str = "message"
    role: str = "assistant"
    model: str = ""
    content: List[ContentBlock] = field(default_factory=list)
    stop_reason: Optional[str] = None
    usage: Usage = field(default_factory=Usage)

    @property
    def text(self) -> str:
        """Get concatenated text from all text content blocks."""
        texts = []
        for block in self.content:
            if block.type == "text" and block.text:
                texts.append(block.text)
        return "\n".join(texts)

    @property
    def tool_calls(self) -> List[ContentBlock]:
        """Get all tool_use content blocks."""
        return [b for b in self.content if b.type == "tool_use"]

    @property
    def has_tool_use(self) -> bool:
        """Check if response contains tool calls."""
        return self.stop_reason == "tool_use" or len(self.tool_calls) > 0


class MessagesAPI:
    """Anthropic Messages API compatible interface."""

    def __init__(self, client: "UnifiedClient"):
        self.client = client

    def create(
        self,
        model: str,
        max_tokens: int,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[Dict] = None,
        stream: bool = False,
        temperature: Optional[float] = None,
        **kwargs
    ) -> Message:
        """
        Create a message using either Ollama or Claude API.

        Args:
            model: Model name (e.g., "gemma3:4b-it-qat" for Ollama, "claude-sonnet-4-20250514" for Claude)
            max_tokens: Maximum tokens to generate
            messages: List of message dicts with "role" and "content"
            system: Optional system prompt
            tools: Optional list of tool definitions
            tool_choice: Optional tool choice config
            stream: Whether to stream (not yet implemented)
            temperature: Optional temperature setting

        Returns:
            Message object with response
        """
        # Determine backend based on model name
        is_claude = model.startswith("claude-") or "anthropic" in model.lower()

        if is_claude:
            return self._call_claude(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
                system=system,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                **kwargs
            )
        else:
            return self._call_ollama(
                model=model,
                max_tokens=max_tokens,
                messages=messages,
                system=system,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                **kwargs
            )

    def _call_ollama(
        self,
        model: str,
        max_tokens: int,
        messages: List[Dict],
        system: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[Dict] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> Message:
        """Call Ollama using Anthropic Messages API format."""
        url = f"{self.client.ollama_url}/v1/messages"

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if temperature is not None:
            payload["temperature"] = temperature

        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": "ollama"
                },
                timeout=120
            )

            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("error", {}).get("message", response.text)
                raise Exception(f"Ollama error ({response.status_code}): {error_msg}")

            data = response.json()
            return self._parse_response(data)

        except requests.exceptions.ConnectionError:
            raise Exception(f"Cannot connect to Ollama at {self.client.ollama_url}. Is it running?")
        except requests.exceptions.Timeout:
            raise Exception("Ollama request timed out")

    def _call_claude(
        self,
        model: str,
        max_tokens: int,
        messages: List[Dict],
        system: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[Dict] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> Message:
        """Call Claude API."""
        if not self.client.anthropic_api_key:
            raise Exception("ANTHROPIC_API_KEY not set")

        url = f"{self.client.anthropic_base_url}/v1/messages"

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice
        if temperature is not None:
            payload["temperature"] = temperature

        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.client.anthropic_api_key,
                    "anthropic-version": "2023-06-01"
                },
                timeout=120
            )

            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get("error", {}).get("message", response.text)
                raise Exception(f"Claude API error ({response.status_code}): {error_msg}")

            data = response.json()
            return self._parse_response(data)

        except requests.exceptions.ConnectionError:
            raise Exception(f"Cannot connect to Claude API at {self.client.anthropic_base_url}")
        except requests.exceptions.Timeout:
            raise Exception("Claude API request timed out")

    def _parse_response(self, data: Dict) -> Message:
        """Parse API response into Message object."""
        content_blocks = []

        for block in data.get("content", []):
            content_blocks.append(ContentBlock(
                type=block.get("type", "text"),
                text=block.get("text"),
                id=block.get("id"),
                name=block.get("name"),
                input=block.get("input"),
                thinking=block.get("thinking")
            ))

        usage_data = data.get("usage", {})
        usage = Usage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0)
        )

        return Message(
            id=data.get("id", ""),
            type=data.get("type", "message"),
            role=data.get("role", "assistant"),
            model=data.get("model", ""),
            content=content_blocks,
            stop_reason=data.get("stop_reason"),
            usage=usage
        )


class UnifiedClient:
    """
    Unified client for local (Ollama) and cloud (Claude) inference.

    Provides Anthropic SDK-compatible interface that works with both backends.
    """

    def __init__(
        self,
        ollama_url: Optional[str] = None,
        anthropic_api_key: Optional[str] = None,
        anthropic_base_url: Optional[str] = None
    ):
        self.ollama_url = ollama_url or OLLAMA_URL
        self.anthropic_api_key = anthropic_api_key or ANTHROPIC_API_KEY
        self.anthropic_base_url = anthropic_base_url or ANTHROPIC_BASE_URL

        # Initialize sub-APIs
        self.messages = MessagesAPI(self)

        # Cache availability status
        self._ollama_available = None

    @property
    def ollama_available(self) -> bool:
        """Check if Ollama is available."""
        if self._ollama_available is not None:
            return self._ollama_available

        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            self._ollama_available = response.status_code == 200
        except:
            self._ollama_available = False

        return self._ollama_available

    def list_ollama_models(self) -> List[str]:
        """List available Ollama models."""
        if not self.ollama_available:
            return []

        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return [m["name"] for m in models]
        except:
            pass
        return []

    def get_best_model(self, require_tools: bool = False) -> str:
        """
        Get the best available model based on requirements.

        Args:
            require_tools: If True, only return models that support tool calling

        Returns:
            Model name string
        """
        available = set(self.list_ollama_models())

        if require_tools:
            # No local tool-capable models - use Claude
            if self.anthropic_api_key:
                return "claude-sonnet-4-20250514"
            raise Exception("Tool calling requires Claude API - no local tool-capable models installed")
        else:
            # For simple generation, prefer gemma3
            for model in ["gemma3:4b-it-qat", "gemma3:12b"]:
                if model in available:
                    return model

        # Default fallback
        if available:
            return list(available)[0]

        raise Exception("No models available")

    def health(self) -> Dict:
        """Get health status of all backends."""
        return {
            "ollama": {
                "available": self.ollama_available,
                "url": self.ollama_url,
                "models": self.list_ollama_models()
            },
            "claude": {
                "available": bool(self.anthropic_api_key),
                "url": self.anthropic_base_url
            }
        }


# Convenience function for simple generation
def generate(
    prompt: str,
    model: Optional[str] = None,
    system: Optional[str] = None,
    max_tokens: int = 1024
) -> str:
    """
    Simple generation helper.

    Args:
        prompt: The prompt text
        model: Model to use (auto-selects if not specified)
        system: Optional system prompt
        max_tokens: Max tokens to generate

    Returns:
        Generated text string
    """
    client = UnifiedClient()

    if model is None:
        model = client.get_best_model(require_tools=False)

    messages = [{"role": "user", "content": prompt}]

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=messages,
        system=system
    )

    return response.text


# Test
if __name__ == "__main__":
    client = UnifiedClient()

    print("=== Health Check ===")
    print(json.dumps(client.health(), indent=2))

    if client.ollama_available:
        print("\n=== Simple Generation Test ===")
        try:
            response = client.messages.create(
                model="gemma3:4b-it-qat",
                max_tokens=100,
                messages=[{"role": "user", "content": "Say 'unified client working' in exactly those words."}]
            )
            print(f"Response: {response.text}")
            print(f"Tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out")
        except Exception as e:
            print(f"Error: {e}")

        print("\n=== Tool Calling Test ===")
        print("Tool calling not supported locally - use Claude API")
    else:
        print("\nOllama not available, skipping tests")
