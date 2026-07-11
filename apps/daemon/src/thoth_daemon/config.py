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
