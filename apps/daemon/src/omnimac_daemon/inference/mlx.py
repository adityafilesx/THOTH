"""MLX inference provider (Phase 5 slice 1).

In-process Apple MLX runtime. Pending live verification: requires the
`mlx_lm` package (absent by default on this machine). Every operation
raises a typed InferenceUnavailableError until it is installed, so a
missing runtime is a clean failure the fallback ladder handles — never a
silent success and never a cloud fallback.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from omnimac_daemon.inference.base import (
    InferenceRequest,
    InferenceResult,
    InferenceUnavailableError,
    ProviderHealth,
    _MetricsMixin,
)


class MLXInferenceProvider(_MetricsMixin):
    def __init__(self, model: str = "qwen3-4b-mlx") -> None:
        super().__init__()
        self._model = model

    @property
    def name(self) -> str:
        return "mlx"

    def _load(self) -> object:
        try:
            import mlx_lm  # type: ignore[import-not-found]
        except ImportError as exc:
            raise InferenceUnavailableError(
                "mlx_lm is not installed; run `uv add mlx-lm` to enable the MLX runtime (pending live verification)"
            ) from exc
        return mlx_lm

    async def generate(self, request: InferenceRequest) -> InferenceResult:
        self._load()  # raises InferenceUnavailableError when absent
        raise InferenceUnavailableError("mlx generation pending live verification")

    async def generate_stream(self, request: InferenceRequest) -> AsyncIterator[str]:
        self._load()
        raise InferenceUnavailableError("mlx streaming pending live verification")
        yield ""  # pragma: no cover - unreachable, satisfies AsyncIterator typing

    async def warm_up(self) -> None:
        self._load()

    async def unload(self) -> None:
        return None

    async def health(self) -> ProviderHealth:
        try:
            self._load()
        except InferenceUnavailableError as exc:
            return ProviderHealth(available=False, detail=str(exc), model_id=self._model)
        return ProviderHealth(available=True, detail="mlx_lm present", model_id=self._model)
