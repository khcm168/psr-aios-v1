from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except (ImportError, ModuleNotFoundError):
    def load_dotenv() -> bool:
        env_path = Path(".env")
        if not env_path.exists():
            return False
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
        return True


def load_environment() -> None:
    load_dotenv()


@dataclass(frozen=True)
class Settings:
    project_name: str
    spreadsheet_id: str
    worksheet_name: str
    google_credentials_path: Path

    @classmethod
    def from_env(cls, require_google: bool = True) -> "Settings":
        load_environment()

        spreadsheet_id = (
            _env_any("GOOGLE_SHEET_ID", "N1_SOURCE_SPREADSHEET_ID", "SPREADSHEET_ID")
            if require_google
            else ""
        )
        credentials_path = (
            Path(_env_any("GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_FILE"))
            if require_google
            else Path()
        )

        return cls(
            project_name=os.getenv("PROJECT_NAME", "psr-aios-v1"),
            spreadsheet_id=spreadsheet_id,
            worksheet_name=os.getenv("GOOGLE_WORKSHEET_NAME", "log"),
            google_credentials_path=credentials_path,
        )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def _env_any(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    joined = " or ".join(names)
    raise RuntimeError(f"Missing required environment variable: {joined}")
