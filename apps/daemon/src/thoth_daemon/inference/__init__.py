"""Local-first inference (Phase 5 slice 1). Provider-neutral, planning-only.

The application runs fully without a cloud API key: the deterministic
provider is the always-available floor, the llama.cpp-family provider
talks to a loopback server, MLX is optional, and the Anthropic provider is
disabled by default and never a silent fallback.
"""

from thoth_daemon.inference.anthropic_provider import AnthropicInferenceProvider
from thoth_daemon.inference.base import (
    InferenceError,
    InferenceProvider,
    InferenceRequest,
    InferenceResult,
    InferenceUnavailableError,
    ProviderHealth,
    ProviderMetrics,
)
from thoth_daemon.inference.deterministic import DeterministicInferenceProvider
from thoth_daemon.inference.isolation import IsolationViolation, NetworkIsolationGuard
from thoth_daemon.inference.llamacpp import LlamaCppInferenceProvider
from thoth_daemon.inference.mlx import MLXInferenceProvider
from thoth_daemon.inference.registry import ModelRegistry, ModelSpec

__all__ = [
    "AnthropicInferenceProvider",
    "DeterministicInferenceProvider",
    "InferenceError",
    "InferenceProvider",
    "InferenceRequest",
    "InferenceResult",
    "InferenceUnavailableError",
    "IsolationViolation",
    "LlamaCppInferenceProvider",
    "MLXInferenceProvider",
    "ModelRegistry",
    "ModelSpec",
    "NetworkIsolationGuard",
    "ProviderHealth",
    "ProviderMetrics",
]
