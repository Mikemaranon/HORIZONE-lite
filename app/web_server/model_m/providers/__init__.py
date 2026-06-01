"""Provider exports.

Registered runtime providers are `mlx`, `ollama`, and `cloud`.
OpenAIProvider, AnthropicProvider, and GoogleProvider remain exported as
legacy direct-provider adapters for compatibility tests and migrations; new
remote provider configuration should go through CloudProvider.
"""

from .anthropic_provider import AnthropicProvider
from .cloud_provider import CloudProvider
from .base_provider import ModelProvider
from .google_provider import GoogleProvider
from .mlx_provider import MLXProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider

REGISTERED_PROVIDER_NAMES = ("mlx", "ollama", "cloud")
LEGACY_DIRECT_PROVIDER_NAMES = ("openai", "anthropic", "google")

__all__ = [
    "AnthropicProvider",
    "CloudProvider",
    "GoogleProvider",
    "LEGACY_DIRECT_PROVIDER_NAMES",
    "ModelProvider",
    "MLXProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "REGISTERED_PROVIDER_NAMES",
]
