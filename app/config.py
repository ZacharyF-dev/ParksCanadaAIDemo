from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    app_name: str = "Mini Jira MCP"
    db_path: Path = Path(os.environ.get("MINI_JIRA_DB_PATH", PROJECT_ROOT / "data" / "mini_jira.db"))
    backend_host: str = os.environ.get("MINI_JIRA_BACKEND_HOST", "127.0.0.1")
    backend_port: int = int(os.environ.get("MINI_JIRA_BACKEND_PORT", "8000"))
    frontend_host: str = os.environ.get("MINI_JIRA_FRONTEND_HOST", "127.0.0.1")
    frontend_port: int = int(os.environ.get("MINI_JIRA_FRONTEND_PORT", "8001"))


settings = Settings()