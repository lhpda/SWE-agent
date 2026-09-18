"""LLM provider implementations."""

from typing import Dict, List, Any
import json

from .client import BaseLLMProvider


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    def __init__(self, model: str, api_key: str, **config):
        """Initialize Anthropic provider."""
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        self.client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=1)
        self.model = model
        self.config = config

    def generate(
        self, prompt: str, max_tokens: int = 4096, temperature: float = 0.0, **kwargs
    ) -> str:
        """Generate completion using Claude."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return response.content[0].text

    def generate_multiple(
        self, prompt: str, n: int = 3, max_tokens: int = 4096, temperature: float = 0.7, **kwargs
    ) -> List[Dict[str, Any]]:
        """Generate multiple completions."""
        results = []
        for i in range(n):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            results.append(
                {
                    "code": response.content[0].text,
                    "confidence": 0.8 - (i * 0.1),  # 降序置信度
                }
            )
        return results


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek provider."""

    def __init__(self, model: str, api_key: str, **config):
        """Initialize DeepSeek provider."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

        # DeepSeek uses OpenAI-compatible API
        self.client = OpenAI(
            api_key=api_key, base_url="https://api.deepseek.com", timeout=60.0, max_retries=1
        )
        self.model = model or "deepseek-chat"
        self.config = config

    def generate(
        self, prompt: str, max_tokens: int = 4096, temperature: float = 0.0, **kwargs
    ) -> str:
        """Generate completion using DeepSeek."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        return response.choices[0].message.content

    def generate_multiple(
        self, prompt: str, n: int = 3, max_tokens: int = 4096, temperature: float = 0.7, **kwargs
    ) -> List[Dict[str, Any]]:
        """Generate multiple completions.

        Note: DeepSeek doesn't support n>1, so we call the API multiple times.
        """
        results = []
        for i in range(n):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
            results.append(
                {
                    "code": response.choices[0].message.content,
                    "confidence": 0.8 - (i * 0.1),
                }
            )
        return results


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider."""

    def __init__(self, model: str, api_key: str, **config):
        """Initialize OpenAI provider."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

        self.client = OpenAI(api_key=api_key, timeout=60.0, max_retries=1)
        self.model = model or "gpt-4"
        self.config = config

    def generate(
        self, prompt: str, max_tokens: int = 4096, temperature: float = 0.0, **kwargs
    ) -> str:
        """Generate completion using OpenAI."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        return response.choices[0].message.content

    def generate_multiple(
        self, prompt: str, n: int = 3, max_tokens: int = 4096, temperature: float = 0.7, **kwargs
    ) -> List[Dict[str, Any]]:
        """Generate multiple completions."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            n=n,
            **kwargs,
        )
        results = []
        for i, choice in enumerate(response.choices):
            results.append(
                {
                    "code": choice.message.content,
                    "confidence": 0.8 - (i * 0.1),
                }
            )
        return results
