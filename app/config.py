from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    app_name: str = "Mini Jira MCP"
    db_path: Path = Path(os.environ.get("MINI_JIRA_DB_PATH", "mini_jira.db"))
    backend_host: str = os.environ.get("MINI_JIRA_BACKEND_HOST", "0.0.0.0")
    backend_port: int = int(os.environ.get("MINI_JIRA_BACKEND_PORT", "8000"))
    frontend_host: str = os.environ.get("MINI_JIRA_FRONTEND_HOST", "0.0.0.0")
    frontend_port: int = int(os.environ.get("MINI_JIRA_FRONTEND_PORT", "8001"))


settings = Settings()