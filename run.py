from __future__ import annotations

import threading
import time
import subprocess
import sys

import uvicorn

from app.config import settings
from app.dashboard import create_dashboard_app
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


def run_dashboard() -> None:
    uvicorn.run(create_dashboard_app(), host="127.0.0.1", port=8006, log_level="info")


def main() -> None:
    seed_if_empty()

    backend_thread = threading.Thread(target=run_backend, daemon=True)
    frontend_thread = threading.Thread(target=run_frontend, daemon=True)
    dashboard_thread = threading.Thread(target=run_dashboard, daemon=True)
    backend_thread.start()
    frontend_thread.start()
    dashboard_thread.start()
    processes = [
        subprocess.Popen([sys.executable, "-m", "chainlit", "run", "demos/jira_foundry_agent/src/jira_foundry_agent/chainlit_app.py", "--host", "127.0.0.1", "--port", "8002"]),
        subprocess.Popen([sys.executable, "-m", "markdown_rag_mcp.server"]),
        subprocess.Popen([sys.executable, "-m", "pc411_directory_mcp.server"]),
        subprocess.Popen([sys.executable, "-m", "chainlit", "run", "demos/knowledge_agent/src/knowledge_agent/chainlit_app.py", "--host", "127.0.0.1", "--port", "8007"]),
        subprocess.Popen([sys.executable, "-m", "chainlit", "run", "demos/workspace_agent/src/workspace_agent/chainlit_app.py", "--host", "127.0.0.1", "--port", "8005"]),
    ]

    print(f"Backend API + MCP: http://{settings.backend_host}:{settings.backend_port}")
    print(f"Frontend UI:       http://{settings.frontend_host}:{settings.frontend_port}")
    print("Foundry agent UI:  http://127.0.0.1:8002")
    print("Knowledge agent:   http://127.0.0.1:8007")
    print("Markdown RAG MCP:  http://127.0.0.1:8003/mcp")
    print("PC411 directory:   http://127.0.0.1:8004/mcp")
    print("Workspace agent:   http://127.0.0.1:8005")
    print("MCP dashboard:     http://127.0.0.1:8006")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
        for process in processes:
            process.terminate()


if __name__ == "__main__":
    main()