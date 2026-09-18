"""Unified LLM client interface."""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import os


class BaseLLMProvider(ABC):
    """Base class for LLM providers."""

    @abstractmethod
    def generate(
        self, prompt: str, max_tokens: int = 4096, temperature: float = 0.0, **kwargs
    ) -> str:
        """Generate completion from prompt."""
        pass

    @abstractmethod
    def generate_multiple(
        self, prompt: str, n: int = 3, max_tokens: int = 4096, temperature: float = 0.7, **kwargs
    ) -> List[Dict[str, Any]]:
        """Generate multiple completions."""
        pass


class LLMClient:
    """Unified LLM client supporting multiple providers."""

    def __init__(
        self,
        provider: str = "anthropic",
        model: str = "claude-sonnet-4-20250514",
        api_key: Optional[str] = None,
        **config,
    ):
        """
        Initialize LLM client.

        Args:
            provider: Provider name (anthropic, deepseek, openai)
            model: Model identifier
            api_key: API key (uses env var if not provided)
            **config: Additional provider-specific config
        """
        self.provider_name = provider
        self.model = model
        self.config = config

        # Get API key from parameter or environment
        self.api_key = api_key or self._get_api_key(provider)

        # Initialize provider
        self.provider = self._create_provider(provider, model, self.api_key, config)

    def _get_api_key(self, provider: str) -> str:
        """Get API key from environment variables."""
        env_vars = {
            "anthropic": "ANTHROPIC_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY",
        }

        env_var = env_vars.get(provider.lower())
        if not env_var:
            raise ValueError(f"Unknown provider: {provider}")

        api_key = os.environ.get(env_var)
        if not api_key:
            raise ValueError(f"{env_var} environment variable not set")

        return api_key

    def _create_provider(
        self, provider: str, model: str, api_key: str, config: Dict[str, Any]
    ) -> BaseLLMProvider:
        """Create provider instance."""
        from .providers import AnthropicProvider, DeepSeekProvider, OpenAIProvider

        providers = {
            "anthropic": AnthropicProvider,
            "deepseek": DeepSeekProvider,
            "openai": OpenAIProvider,
        }

        provider_class = providers.get(provider.lower())
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider}")

        return provider_class(model=model, api_key=api_key, **config)

    def generate(
        self, prompt: str, max_tokens: int = 4096, temperature: float = 0.0, **kwargs
    ) -> str:
        """
        Generate completion from prompt.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Provider-specific parameters

        Returns:
            Generated text
        """
        return self.provider.generate(
            prompt=prompt, max_tokens=max_tokens, temperature=temperature, **kwargs
        )

    def generate_multiple(
        self, prompt: str, n: int = 3, max_tokens: int = 4096, temperature: float = 0.7, **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple completions.

        Args:
            prompt: Input prompt
            n: Number of completions
            max_tokens: Maximum tokens per completion
            temperature: Sampling temperature
            **kwargs: Provider-specific parameters

        Returns:
            List of completions with metadata
        """
        return self.provider.generate_multiple(
            prompt=prompt, n=n, max_tokens=max_tokens, temperature=temperature, **kwargs
        )
