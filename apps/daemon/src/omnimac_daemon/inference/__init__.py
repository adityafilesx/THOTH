"""Local-first inference (Phase 5 slice 1). Provider-neutral, planning-only.

The application runs fully without a cloud API key: the deterministic
provider is the always-available floor, the llama.cpp-family provider
talks to a loopback server, MLX is optional, and the Anthropic provider is
disabled by default and never a silent fallback.
"""

from omnimac_daemon.inference.anthropic_provider import AnthropicInferenceProvider
from omnimac_daemon.inference.base import (
    InferenceError,
    InferenceProvider,
    InferenceRequest,
    InferenceResult,
    InferenceUnavailableError,
    ProviderHealth,
    ProviderMetrics,
)
from omnimac_daemon.inference.deterministic import DeterministicInferenceProvider
from omnimac_daemon.inference.isolation import IsolationViolation, NetworkIsolationGuard
from omnimac_daemon.inference.llamacpp import LlamaCppInferenceProvider
from omnimac_daemon.inference.mlx import MLXInferenceProvider
from omnimac_daemon.inference.registry import ModelRegistry, ModelSpec

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
