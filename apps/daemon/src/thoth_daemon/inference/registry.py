"""Local model registry (Phase 5 slice 1).

Registry entries are DATA ONLY — models never auto-execute remote code.
Integrity hashes are computed from local model files; runtime-managed
models (e.g. server-pulled) record the runtime-reported digest.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    runtime: str  # llama.cpp | mlx | deterministic
    path: str | None = None
    quantization: str = ""
    memory_estimate_bytes: int = 0
    max_context: int = 0
    capabilities: list[str] = Field(default_factory=list)
    benchmark: dict[str, Any] = Field(default_factory=dict)
    license: str = ""
    integrity_hash: str = ""


class ModelRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: dict[str, ModelSpec] = Field(default_factory=dict)

    def add(self, spec: ModelSpec) -> None:
        self.models[spec.id] = spec

    def get(self, model_id: str) -> ModelSpec:
        if model_id not in self.models:
            raise KeyError(f"unknown model {model_id!r}")
        return self.models[model_id]

    def list(self) -> list[ModelSpec]:
        return list(self.models.values())

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> ModelRegistry:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def integrity_hash(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def default() -> ModelRegistry:
        """The candidate models Phase 5.0 benchmarks (Qwen3 family) plus the
        always-available deterministic floor. Benchmark results and integrity
        hashes are filled by slice 2 when models are pulled."""
        reg = ModelRegistry()
        reg.add(
            ModelSpec(
                id="deterministic",
                runtime="deterministic",
                capabilities=["json_schema", "streaming"],
                license="internal",
                max_context=0,
            )
        )
        reg.add(
            ModelSpec(
                id="qwen3:4b",
                runtime="llama.cpp",
                quantization="Q4_K_M",
                memory_estimate_bytes=2_600_000_000,
                max_context=32768,
                capabilities=["json_schema", "streaming", "tools"],
                license="apache-2.0",
            )
        )
        reg.add(
            ModelSpec(
                id="qwen3:8b",
                runtime="llama.cpp",
                quantization="Q4_K_M",
                memory_estimate_bytes=5_200_000_000,
                max_context=32768,
                capabilities=["json_schema", "streaming", "tools"],
                license="apache-2.0",
            )
        )
        return reg
