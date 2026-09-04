from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("JIRA_AGENT_HOST", "127.0.0.1")
    port: int = int(os.getenv("JIRA_AGENT_PORT", "8002"))
    jira_mcp_url: str = os.getenv("JIRA_MCP_URL", "http://127.0.0.1:8000/mcp/")
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_chat_model: str = os.getenv("AZURE_OPENAI_CHAT_MODEL", "")

    def validate_model_settings(self) -> None:
        missing = [
            name
            for name, value in {
                "AZURE_OPENAI_ENDPOINT": self.azure_openai_endpoint,
                "AZURE_OPENAI_CHAT_MODEL": self.azure_openai_chat_model,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required settings: {', '.join(missing)}")


settings = Settings()
