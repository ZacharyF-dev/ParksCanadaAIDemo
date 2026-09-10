from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path(
        os.environ.get("PARKS_CANADA_DB_PATH", PROJECT_ROOT / "data" / "parks_canada_booking.db")
    )
    seed_path: Path = Path(
        os.environ.get("PARKS_CANADA_SEED_PATH", PROJECT_ROOT / "data" / "parks_canada_seed_data.json")
    )
    host: str = os.environ.get("PARKS_CANADA_MCP_HOST", "127.0.0.1")
    port: int = int(os.environ.get("PARKS_CANADA_MCP_PORT", "8008"))


settings = Settings()
