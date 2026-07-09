from __future__ import annotations

import threading
import time

import uvicorn

from app.config import settings
from app.mcp_server import create_backend_app
from app.seed import seed_if_empty
from app.web import create_web_app


def run_backend() -> None:
    uvicorn.run(
        create_backend_app(),
        host=settings.backend_host,
        port=settings.backend_port,
        log_level="info",
    )


def run_frontend() -> None:
    uvicorn.run(
        create_web_app(),
        host=settings.frontend_host,
        port=settings.frontend_port,
        log_level="info",
    )


def main() -> None:
    seed_if_empty()

    backend_thread = threading.Thread(target=run_backend, daemon=True)
    frontend_thread = threading.Thread(target=run_frontend, daemon=True)

    backend_thread.start()
    frontend_thread.start()

    print(f"Backend API + MCP: http://{settings.backend_host}:{settings.backend_port}")
    print(f"Frontend UI:       http://{settings.frontend_host}:{settings.frontend_port}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")


if __name__ == "__main__":
    main()