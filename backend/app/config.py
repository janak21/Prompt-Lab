"""Application configuration.

Settings are resolved once at import time via a module-level ``settings`` singleton
(see bottom of file). Provider API keys is NEVER read from request bodies, never
logged, and never exposed by any endpoint -- only its *presence* is reported (see
``/api/health``).

Key resolution order:
1. ``ANTHROPIC_API_KEY`` already present in the process environment (e.g. exported by
   the shell, or injected by a deployment platform) wins outright.
2. Otherwise, walk up from the project root directory looking for a ``.env`` file that
   defines ``ANTHROPIC_API_KEY``, and load it. This lets a single ``.env`` living at a
   shared parent directory (e.g. the git checkout that contains several sibling
   projects) supply the key without every sub-project needing its own copy, and
   without hardcoding any particular path.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[2] is the promptlab/ project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _find_and_load_env() -> None:
    """Resolve provider keys independently from env / nearest parent .env files.

    Explicitly exported values win, including empty values. Other .env settings
    retain the same nearest-file precedence without mixing provider credentials.
    """
    import os

    credential_names = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")
    # Preserve .env settings as well as independently resolved credentials. Nearest
    # files win; an explicitly exported environment value always takes precedence.
    for directory in [PROJECT_ROOT, *PROJECT_ROOT.parents]:
        candidate = directory / ".env"
        if candidate.is_file():
            for name, value in dotenv_values(candidate).items():
                if name not in credential_names and value is not None:
                    os.environ.setdefault(name, value)
    for key_name in credential_names:
        if key_name in os.environ:
            continue
        for directory in [PROJECT_ROOT, *PROJECT_ROOT.parents]:
            candidate = directory / ".env"
            if candidate.is_file():
                values = dotenv_values(candidate)
                if values.get(key_name):
                    # Load only this credential; a nearer provider's .env must not
                    # prevent resolving the other provider from a parent directory.
                    os.environ[key_name] = values[key_name]
                    break


_find_and_load_env()


class Settings(BaseSettings):
    """Runtime configuration, sourced from the environment / .env files.

    ``anthropic_api_key`` is intentionally typed as ``str | None`` -- the app must be
    able to boot (e.g. to serve ``/api/health`` reporting the key as absent) even
    without a key configured.
    """

    model_config = SettingsConfigDict(extra="ignore")

    anthropic_api_key: str | None = Field(default=None, repr=False)
    openai_api_key: str | None = Field(default=None, repr=False)

    promptlab_db: str = "promptlab/promptlab.db"

    default_model: str = "claude-haiku-4-5"
    default_judge_model: str = "claude-sonnet-5"

    default_concurrency: int = 5
    max_concurrency: int = 20

    cors_origin: str = "http://localhost:5173"

    def db_path(self) -> Path:
        """Resolve the configured DB path to an absolute path.

        A relative path is resolved against ``PROJECT_ROOT``'s parent (i.e. the
        ``promptlab/`` directory itself, since the default value already begins with
        ``promptlab/``) -- more precisely, relative to the directory that contains the
        ``promptlab/`` project root, matching the default ``promptlab/promptlab.db``.
        """
        p = Path(self.promptlab_db)
        if p.is_absolute():
            return p
        return (PROJECT_ROOT.parent / p).resolve()


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance."""
    import os

    return Settings(anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"), openai_api_key=os.environ.get("OPENAI_API_KEY"))


settings = get_settings()
