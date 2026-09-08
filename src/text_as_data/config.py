"""Local defaults and OS-protected credentials. Never serialize secrets to disk."""
from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Literal

import keyring
from platformdirs import user_config_path, user_data_path
from pydantic import BaseModel, Field

_lock = RLock()
SERVICE = "Decifra"


class Settings(BaseModel):
    model: str = ""
    provider_mode: Literal["api_key", "cli"] = "cli"
    cli_command: str = "claude -p"
    cli_prompt_mode: Literal["stdin", "arg"] = "stdin"
    output_tokens_per_document: int = Field(default=256, ge=1, le=32000)
    input_usd_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_usd_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)


def config_path() -> Path:
    base = Path(os.environ["DECIFRA_CONFIG_DIR"]) if os.environ.get("DECIFRA_CONFIG_DIR") else user_config_path("Decifra", appauthor=False)
    return base / "settings.json"


def data_directory() -> Path:
    return Path(os.environ["DECIFRA_DATA_DIR"]) if os.environ.get("DECIFRA_DATA_DIR") else user_data_path("Decifra", appauthor=False)


def read_settings() -> Settings:
    with _lock:
        path = config_path()
        return Settings.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else Settings()


def save_settings(settings: Settings) -> None:
    with _lock:
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)


def api_key(vendor: str) -> str | None:
    value = os.environ.get(f"{vendor.upper()}_API_KEY")
    if value:
        return value
    try:
        return keyring.get_password(SERVICE, vendor)
    except Exception:
        return None


def credential_status(vendor: str) -> dict:
    value = api_key(vendor)
    return {"configured": bool(value), "source": "environment" if os.environ.get(f"{vendor.upper()}_API_KEY") else "keyring" if value else "none"}


def save_api_key(vendor: str, value: str) -> None:
    # Refuse insecure third-party backends rather than falling back to a text file.
    backend = keyring.get_keyring()
    module = type(backend).__module__
    if not module.startswith(("keyring.backends.Windows", "keyring.backends.macOS", "keyring.backends.SecretService", "keyring.backends.kwallet")):
        raise RuntimeError("OS credential storage is unavailable; use an environment variable or CLI mode.")
    if value.strip():
        keyring.set_password(SERVICE, vendor, value.strip())
    else:
        try:
            keyring.delete_password(SERVICE, vendor)
        except keyring.errors.PasswordDeleteError:
            pass
