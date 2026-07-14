from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Daemon configuration. Values come from THOTH_* env vars / .env.

    Secrets never belong here: credentials live in the macOS Keychain.
    """

    model_config = SettingsConfigDict(env_prefix="THOTH_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 7710
    db_path: Path = Path("./data/thoth.db")
    log_dir: Path = Path("./data/logs")
    log_level: str = "INFO"

    trusted_workspaces: Annotated[list[str], NoDecode] = Field(default_factory=list)
    approval_ttl_seconds: int = 120
    max_retries_per_step: int = 2
    max_retries_per_task: int = 5

    planner: str = "mock"

    # Local inference (Phase 5.0). Default provider is the offline deterministic
    # floor; "llama.cpp" uses the loopback local server. Cloud is never a
    # default and never a silent fallback.
    inference_provider: str = "deterministic"  # deterministic | llama.cpp | mlx
    inference_model: str = "qwen3:4b"
    inference_endpoint: str = "http://127.0.0.1:11434"
    network_isolation: bool = False

    # Local voice (Phase 5.5). Missing runtimes are typed unavailable; no cloud
    # speech service is ever selected as fallback.
    whisper_executable: Path = Path("/opt/homebrew/bin/whisper-cli")
    whisper_model_path: Path = Path("./data/models/whisper/ggml-base.en.bin")
    whisper_executable_sha256: str | None = None
    whisper_model_sha256: str | None = None
    whisper_language: str = "en"
    voice_retain_transcripts: bool = False
    voice_correction_window_seconds: float = 3.0

    session_token: str | None = None
    session_token_path: Path = Path("./data/session.token")

    @field_validator("trusted_workspaces", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"
