"""Central place for env-driven configuration. No secrets live here."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(Path.cwd() / ".env")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
MEMORY_DIR = Path(os.environ.get("WEALTH_PILOT_MEMORY_DIR", PROJECT_ROOT / ".wealth_pilot_memory"))


@dataclass(frozen=True)
class Settings:
    llm_provider: str = os.environ.get("LLM_PROVIDER", "mock")
    llm_model: str = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
    groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
    langfuse_public_key: str = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.environ.get("LANGFUSE_SECRET_KEY", "")
    langfuse_base_url: str = os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")


settings = Settings()
