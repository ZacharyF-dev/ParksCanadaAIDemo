from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path(os.getenv("PC411_DIRECTORY_DB_PATH", PROJECT_ROOT / "data" / "pc411_directory.db"))
    structure_path: Path = Path(os.getenv("PC411_STRUCTURE_PATH", PROJECT_ROOT / "PC411_Structure.html"))
    host: str = os.getenv("PC411_DIRECTORY_HOST", "127.0.0.1")
    port: int = int(os.getenv("PC411_DIRECTORY_PORT", "8004"))
    seed: int = int(os.getenv("PC411_DIRECTORY_SEED", "411"))


settings = Settings()
